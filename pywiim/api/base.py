"""WiiM HTTP API core client.

This module provides the base HTTP transport layer for communicating with WiiM devices.
It handles protocol detection, SSL/TLS, retry logic, and response parsing.

# pragma: allow-long-file base-client-cohesive
# This file exceeds the 600 LOC hard limit (1020 lines) but is kept as a single
# cohesive unit because:
# 1. Single responsibility: HTTP transport layer and core client functionality
# 2. Well-organized: Clear sections for transport, protocol detection, and parsing
# 3. Tight coupling: Transport and client logic are tightly integrated
# 4. Maintainable: Clear structure, follows base client design pattern
# 5. Natural unit: Represents one concept (HTTP API client foundation)
# While splitting transport from client logic is possible, the integration is
# so tight that splitting would add complexity and import overhead without clear benefit.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import ssl
import time
from typing import Any, NamedTuple
from urllib.parse import quote

import aiohttp
from aiohttp import ClientSession

from ..exceptions import (
    WiiMConnectionError,
    WiiMError,
    WiiMRequestError,
    WiiMResponseError,
)
from ..models import DeviceInfo, PlayerStatus
from .audio_pro import validate_audio_pro_response
from .constants import (
    API_ENDPOINT_STATUS,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    PROBE_ASYNC_TIMEOUT,
    PROBE_TIMEOUT_CONNECT,
    PROBE_TIMEOUT_TOTAL,
)
from .parser import parse_player_status
from .ssl import create_wiim_ssl_context

_LOGGER = logging.getLogger(__name__)

HEADERS: dict[str, str] = {"Connection": "close"}


class ApiResponse(NamedTuple):
    """Unified response from base API requests.

    All requests return this shape. Callers use .parsed for JSON data or .raw
    for non-JSON body text. Base does not raise for non-JSON; only for transport failures.
    """

    parsed: dict[str, Any] | list[Any] | None  # JSON object or array when body was valid JSON
    raw: str | None  # Response body as text when not JSON (or when exposing body)


class BaseWiiMClient:
    """Base WiiM HTTP API client – transport & player-status parser only.

    This class provides the core HTTP transport layer for communicating with WiiM devices.
    It handles protocol detection (HTTP/HTTPS), SSL/TLS configuration, retry logic, and
    response parsing. High-level API methods are provided by mixin classes.
    """

    def __init__(
        self,
        host: str,
        port: int | None = None,
        protocol: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        ssl_context: ssl.SSLContext | None = None,
        session: ClientSession | None = None,
        capabilities: dict[str, Any] | None = None,
    ) -> None:
        """Instantiate the client.

        Args:
            host: Device hostname or IP. A trailing ":<port>" is respected.
            port: Optional port override. If None, will probe standard ports.
            protocol: Optional protocol override ("http" or "https"). If None, will probe both.
            timeout: Network timeout (seconds).
            ssl_context: Custom SSL context (tests/advanced use-cases only).
            session: Optional shared *aiohttp* session.
            capabilities: Device capabilities for firmware-specific handling.
        """
        self._discovered_port: bool = False
        self._user_specified_port: int | None = port  # Track user intent
        self._user_specified_protocol: str | None = protocol  # Track user intent

        if ":" in host and not host.startswith("["):
            # Check if this is an IPv6 address or "host:port" format
            try:
                # Try to parse as IPv6 address
                ipaddress.IPv6Address(host)
                # If successful, it's a pure IPv6 address
                self._host = host
                self.port = port if port is not None else DEFAULT_PORT
            except ipaddress.AddressValueError:
                # Not a valid IPv6 address, check if it's "host:port" format
                try:
                    host_part, port_part = host.rsplit(":", 1)
                    self.port = int(port_part)
                    self._host = host_part
                    self._discovered_port = True
                except (ValueError, TypeError):
                    self._host = host
                    self.port = port if port is not None else DEFAULT_PORT
        elif host.startswith("[") and "]:" in host:
            # Handle IPv6 address with port in brackets: [2001:db8::1]:8080
            try:
                bracket_end = host.find("]:")
                if bracket_end > 0:
                    ipv6_part = host[1:bracket_end]  # Remove brackets
                    port_part = host[bracket_end + 2 :]  # Skip "]:"
                    self._host = ipv6_part
                    self.port = int(port_part)
                    self._discovered_port = True
                else:
                    self._host = host
                    self.port = port if port is not None else DEFAULT_PORT
            except (ValueError, TypeError):
                self._host = host
                self.port = port if port is not None else DEFAULT_PORT
        else:
            self._host = host
            self.port = port if port is not None else DEFAULT_PORT

        # Normalise host for URL contexts (IPv6 needs brackets).
        self._host_url = f"[{self._host}]" if ":" in self._host and not self._host.startswith("[") else self._host

        # Use firmware-specific timeout if provided
        self.timeout = capabilities.get("response_timeout", timeout) if capabilities else timeout
        self.ssl_context = ssl_context
        self._session = session
        self._capabilities = capabilities or {}

        # Endpoint cache (set once, never cleared automatically)
        # Format: "https://192.168.1.115:443" or None if not yet discovered
        self._endpoint: str | None = None
        self._endpoint_tested: bool = False  # Track if we've completed initial probe

        # Internal helpers for parser bookkeeping.
        self._last_track: str | None = None
        self._last_play_mode: str | None = None
        self._verify_ssl_default: bool = True

        # Basic mutex to avoid concurrent protocol-probe races.
        self._lock = asyncio.Lock()

        # Optional metrics collection (enabled by default, can be disabled)
        self._metrics_enabled = True
        self._total_requests = 0
        self._successful_requests = 0
        self._failed_requests = 0
        self._timeout_count = 0
        self._connection_error_count = 0
        self._request_times: list[float] = []  # Last 100 request times
        self._error_history: list[dict[str, Any]] = []  # Last 20 errors
        self._last_error: dict[str, Any] | None = None

    async def _ensure_session(self) -> None:
        """Create aiohttp session bound to current loop if needed."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)

    @staticmethod
    def _is_loop_closed_error(err: RuntimeError) -> bool:
        """Return True if the RuntimeError indicates a closed event loop."""
        return "Event loop is closed" in str(err)

    async def _handle_loop_closed_session(self, err: RuntimeError) -> None:
        """Reset client session when its originating event loop was closed."""
        _LOGGER.debug("Detected closed event loop for %s session: %s", self.host, err)
        if self._session is not None:
            try:
                await self._session.close()
            except Exception as close_err:  # noqa: BLE001
                _LOGGER.debug("Ignoring error while closing session for %s: %s", self.host, close_err)
        self._session = None

    async def _session_request(self, method: str, url: str, **kwargs: Any) -> aiohttp.ClientResponse:
        """Perform session request with automatic recovery when event loop closes."""
        await self._ensure_session()
        attempt = 0

        while True:
            attempt += 1
            if self._session is None:
                raise RuntimeError("session not started")

            try:
                start = time.time()
                _LOGGER.debug("HTTP start host=%s attempt=%d %s %s", self.host, attempt, method, url)
                response = await self._session.request(method, url, **kwargs)
                elapsed = (time.time() - start) * 1000
                _LOGGER.debug(
                    "HTTP done host=%s status=%s %.1fms %s %s",
                    self.host,
                    getattr(response, "status", "unknown"),
                    elapsed,
                    method,
                    url,
                )
                return response
            except RuntimeError as err:
                if not self._is_loop_closed_error(err):
                    _LOGGER.warning(
                        "HTTP runtime error host=%s attempt=%d %s %s: %s",
                        self.host,
                        attempt,
                        method,
                        url,
                        err,
                    )
                    raise

                # Reset session and retry once with a fresh loop/session
                await self._handle_loop_closed_session(err)
                await self._ensure_session()

                if attempt >= 2:
                    _LOGGER.error(
                        "HTTP loop closed twice host=%s %s %s: %s",
                        self.host,
                        method,
                        url,
                        err,
                    )
                    # Reset session before raising error
                    await self._handle_loop_closed_session(err)
                    # Convert to WiiMConnectionError for consistent error handling
                    from ..exceptions import WiiMConnectionError

                    raise WiiMConnectionError(
                        f"Event loop closed while requesting {url}: {err}",
                        endpoint=url,
                        last_error=err,
                    ) from err

    @property
    def capabilities(self) -> dict[str, Any]:
        """Expose device capabilities for entity setup."""
        return self._capabilities

    @property
    def host(self) -> str:
        """Host address (IP or hostname)."""
        return self._host

    @property
    def base_url(self) -> str | None:
        """Base URL used for the last successful request."""
        return self._endpoint

    @property
    def discovered_endpoint(self) -> str | None:
        """Discovered endpoint (protocol://host:port) or None if not yet probed."""
        return self._endpoint

    @property
    def is_https(self) -> bool:
        """True if using HTTPS protocol."""
        return self._endpoint is not None and self._endpoint.startswith("https://")

    @property
    def discovered_port(self) -> int | None:
        """Discovered port number or None if not yet probed."""
        if self._endpoint:
            from urllib.parse import urlparse

            parsed = urlparse(self._endpoint)
            return parsed.port
        return None

    def enable_metrics(self, enabled: bool = True) -> None:
        """Enable or disable metrics collection.

        Args:
            enabled: True to enable metrics collection, False to disable.
        """
        self._metrics_enabled = enabled

    @property
    def api_stats(self) -> dict[str, Any]:
        """Get API request statistics.

        Returns:
            Dictionary with request statistics including:
            - total_requests: Total number of requests made
            - successful_requests: Number of successful requests
            - failed_requests: Number of failed requests
            - timeout_count: Number of timeout errors
            - connection_error_count: Number of connection errors
            - success_rate: Success rate (0.0-1.0)
            - avg_latency_ms: Average request latency in milliseconds
            - last_error: Last error information (if any)
            - error_history: Last 20 errors
        """
        if not self._metrics_enabled:
            return {"metrics_enabled": False}

        success_rate = self._successful_requests / self._total_requests if self._total_requests > 0 else 0.0

        avg_latency_ms = None
        if self._request_times:
            avg_latency_ms = sum(self._request_times) / len(self._request_times) * 1000

        return {
            "metrics_enabled": True,
            "total_requests": self._total_requests,
            "successful_requests": self._successful_requests,
            "failed_requests": self._failed_requests,
            "timeout_count": self._timeout_count,
            "connection_error_count": self._connection_error_count,
            "success_rate": success_rate,
            "avg_latency_ms": avg_latency_ms,
            "last_error": self._last_error,
            "error_history": self._error_history.copy(),
        }

    @property
    def connection_stats(self) -> dict[str, Any]:
        """Get connection quality statistics.

        Returns:
            Dictionary with connection statistics including:
            - avg_latency_ms: Average request latency in milliseconds
            - success_rate: Request success rate (0.0-1.0)
            - total_requests: Total number of requests
            - failed_requests: Number of failed requests
            - timeout_count: Number of timeout errors
            - connection_error_count: Number of connection errors
            - established_endpoint: Current working endpoint (if any)
        """
        if not self._metrics_enabled:
            return {"metrics_enabled": False}

        success_rate = self._successful_requests / self._total_requests if self._total_requests > 0 else 0.0

        avg_latency_ms = None
        if self._request_times:
            avg_latency_ms = sum(self._request_times) / len(self._request_times) * 1000

        return {
            "metrics_enabled": True,
            "avg_latency_ms": avg_latency_ms,
            "success_rate": success_rate,
            "total_requests": self._total_requests,
            "failed_requests": self._failed_requests,
            "timeout_count": self._timeout_count,
            "connection_error_count": self._connection_error_count,
            "established_endpoint": self._endpoint,
        }

    # ------------------------------------------------------------------
    # SSL Context Management -------------------------------------------
    # ------------------------------------------------------------------

    async def _get_ssl_context(self) -> ssl.SSLContext:
        """Return a permissive SSL context able to talk to WiiM devices.

        For Audio Pro MkII devices, also loads client certificate for mutual TLS authentication.
        Uses executor for blocking SSL operations to avoid blocking the event loop.
        """
        if self.ssl_context is not None:
            return self.ssl_context

        new_ssl_context = await create_wiim_ssl_context(self.ssl_context)
        if new_ssl_context is None:
            raise RuntimeError("Failed to create SSL context")
        self.ssl_context = new_ssl_context
        return self.ssl_context

    # ------------------------------------------------------------------
    # Request Methods ---------------------------------------------------
    # ------------------------------------------------------------------

    async def _request(
        self,
        endpoint: str,
        method: str = "GET",
        **kwargs: Any,
    ) -> ApiResponse:
        """Perform an HTTP(S) request with smart protocol fallback and firmware-specific handling.

        Protocol fallback strategy:
        1. Try established endpoint first (fast-path)
        2. Only do full probe if no established endpoint exists
        3. After successful connection, stick with working protocol/port
        4. Apply firmware-specific error handling and retries
        """
        await self._ensure_session()

        kwargs.setdefault("headers", HEADERS)

        # Use firmware-specific retry logic
        retry_count = self._capabilities.get("retry_count", 3)
        is_legacy_device = self._capabilities.get("is_legacy_device", False)

        if retry_count <= 0:
            raise ValueError("retry_count must be greater than 0")

        for attempt in range(retry_count):
            start_time = time.time() if self._metrics_enabled else None
            try:
                result = await self._request_with_protocol_fallback(endpoint, method, **kwargs)

                # Validate response for legacy firmware
                if is_legacy_device:
                    generation = self._capabilities.get("audio_pro_generation", "original")
                    _LOGGER.debug(
                        "Validating response for legacy device %s (generation: %s) on %s",
                        self.host,
                        generation,
                        endpoint,
                    )
                    result = self._validate_legacy_response(result, endpoint)

                # Track successful request
                if self._metrics_enabled and start_time:
                    elapsed = time.time() - start_time
                    self._total_requests += 1
                    self._successful_requests += 1
                    # Keep last 100 request times
                    self._request_times.append(elapsed)
                    if len(self._request_times) > 100:
                        self._request_times.pop(0)

                return result

            except (aiohttp.ClientError, WiiMConnectionError) as err:
                # Track error metrics
                if self._metrics_enabled and start_time:
                    elapsed = time.time() - start_time
                    self._total_requests += 1
                    self._failed_requests += 1
                    # Keep last 100 request times (even for failures)
                    self._request_times.append(elapsed)
                    if len(self._request_times) > 100:
                        self._request_times.pop(0)

                    # Track specific error types
                    if isinstance(err, (asyncio.TimeoutError, aiohttp.ServerTimeoutError)):
                        self._timeout_count += 1
                    elif isinstance(err, (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError)):
                        self._connection_error_count += 1

                    # Track error in history
                    error_info = {
                        "timestamp": time.time(),
                        "endpoint": endpoint,
                        "error_type": type(err).__name__,
                        "error_message": str(err),
                        "attempt": attempt + 1,
                        "latency_ms": elapsed * 1000,
                    }
                    self._last_error = error_info
                    self._error_history.append(error_info)
                    # Keep last 20 errors
                    if len(self._error_history) > 20:
                        self._error_history.pop(0)

                if attempt == retry_count - 1:
                    # Get comprehensive device info for enhanced error context
                    device_info = {}
                    try:
                        if hasattr(self, "_capabilities") and self._capabilities:
                            caps = self._capabilities
                            device_info = {
                                "firmware_version": caps.get("firmware_version", "unknown"),
                                "device_model": caps.get("device_type", "unknown"),
                                "device_name": caps.get("device_name", "unknown"),
                                "is_wiim_device": caps.get("is_wiim_device", False),
                                "is_legacy_device": caps.get("is_legacy_device", False),
                                "supports_metadata": caps.get("supports_metadata", False),
                                "supports_audio_output": caps.get("supports_audio_output", False),
                            }
                    except Exception:  # noqa: BLE001
                        pass  # Device info not available, continue without it

                    raise WiiMRequestError(
                        f"Request failed after {retry_count} attempts: {err}",
                        endpoint=endpoint,
                        attempts=retry_count,
                        last_error=err,
                        device_info=device_info,
                    ) from err

                # Exponential backoff for retries (longer for legacy devices)
                backoff_delay = 0.5 * (2**attempt)
                if is_legacy_device:
                    backoff_delay *= 2  # Double delay for legacy devices

                _LOGGER.debug(
                    "Request attempt %d/%d failed for %s, retrying in %.1fs: %s",
                    attempt + 1,
                    retry_count,
                    self._host,
                    backoff_delay,
                    err,
                )
                await asyncio.sleep(backoff_delay)

        # This should never be reached due to retry_count check, but mypy needs it
        raise RuntimeError("Unexpected code path in _request")

    async def _request_with_protocol_fallback(
        self,
        endpoint: str,
        method: str = "GET",
        **kwargs: Any,
    ) -> ApiResponse:
        """Perform HTTP(S) request with permanent endpoint caching.

        Protocol discovery strategy:
        1. If cached endpoint exists, use it (never auto-reprobe on failure)
        2. If no cached endpoint, probe once respecting user intent
        3. Connection failures are transient - re-raise, don't reprobe
        4. Manual reprobe() method available for firmware updates

        Raises:
            WiiMConnectionError: On connection/protocol errors
            WiiMResponseError: On invalid responses
        """
        # Use longer timeout for Bluetooth connection operations (30 seconds)
        is_bluetooth_connection = "connectbta2dpsynk" in endpoint.lower()
        request_timeout = 30.0 if is_bluetooth_connection else self.timeout

        # Fast-path: use cached endpoint (NEVER auto-clear on failure)
        if self._endpoint:
            from urllib.parse import urlsplit

            try:
                p = urlsplit(self._endpoint)
                # Handle IPv6 addresses properly
                hostname = p.hostname
                if hostname and ":" in hostname and not hostname.startswith("["):
                    hostname = f"[{hostname}]"
                url = f"{p.scheme}://{hostname}:{p.port}{endpoint}"

                # Configure SSL for HTTPS
                if p.scheme == "https":
                    kwargs["ssl"] = await self._get_ssl_context()
                else:
                    kwargs.pop("ssl", None)

                if self._session is None:
                    raise RuntimeError("session not started")

                async with asyncio.timeout(request_timeout):
                    resp = await self._session_request(method, url, **kwargs)
                    async with resp:
                        resp.raise_for_status()
                        text = await resp.text()

                        # Single response shape: parse JSON in one place; never raise for non-JSON
                        if not text or text.strip() == "":
                            _LOGGER.debug("Empty response from device for %s", endpoint)
                            return ApiResponse(parsed=None, raw="")

                        if text.strip() == "OK":
                            return ApiResponse(parsed=None, raw="OK")

                        try:
                            data = json.loads(text)
                            return ApiResponse(parsed=data, raw=None)
                        except json.JSONDecodeError:
                            # Non-JSON body (e.g. "unknown command") - return raw; callers handle
                            return ApiResponse(parsed=None, raw=text)

            except RuntimeError as err:
                if self._is_loop_closed_error(err):
                    raise WiiMConnectionError(
                        f"Event loop closed while requesting {self._endpoint}{endpoint}: {err}",
                        endpoint=f"{self._endpoint}{endpoint}",
                        last_error=err,
                    ) from err
                raise
            except (WiiMResponseError, WiiMRequestError):
                # Re-raise response/request errors as-is (don't wrap)
                raise
            except Exception as err:
                # Connection failure - DO NOT clear cache, just re-raise
                _LOGGER.debug("Request to %s%s failed (transient): %s", self._endpoint, endpoint, err)

                # Get device info for error context
                device_info = {}
                try:
                    if self._capabilities:
                        device_info = {
                            "firmware_version": self._capabilities.get("firmware_version", "unknown"),
                            "device_model": self._capabilities.get("device_type", "unknown"),
                            "device_name": self._capabilities.get("device_name", "unknown"),
                        }
                except Exception:  # noqa: BLE001
                    pass

                raise WiiMConnectionError(
                    f"Request to {self._endpoint}{endpoint} failed: {err}",
                    endpoint=f"{self._endpoint}{endpoint}",
                    last_error=err,
                    device_info=device_info,
                ) from err

        # No cached endpoint - need to probe (one time only)
        await self._probe_and_cache_endpoint(endpoint, method, request_timeout, **kwargs)

        # Retry with discovered endpoint
        return await self._request_with_protocol_fallback(endpoint, method, **kwargs)

    async def _probe_and_cache_endpoint(
        self,
        test_endpoint: str,
        method: str = "GET",
        timeout: float = 5.0,
        **kwargs: Any,
    ) -> None:
        """Probe protocol/port combinations and cache the working endpoint.

        Respects user-specified protocol/port. Only probes when no cached endpoint exists.

        Raises:
            WiiMConnectionError: If no working endpoint found
        """
        if self._endpoint:
            return  # Already cached

        _LOGGER.debug("Probing protocols for %s", self._host)

        # Get SSL context for HTTPS attempts
        ssl_ctx = await self._get_ssl_context()

        # Build list of protocol/port combinations to try
        protocols_to_try = self._build_probe_list()

        # Use probe timeout constants - max() ensures mTLS handshakes have sufficient time
        # even if caller specifies a shorter timeout (Audio Pro Link2 needs this)
        probe_timeout = aiohttp.ClientTimeout(connect=PROBE_TIMEOUT_CONNECT, total=max(PROBE_TIMEOUT_TOTAL, timeout))

        last_error: Exception | None = None
        tried: list[str] = []

        for protocol, port in protocols_to_try:
            host_for_url = f"[{self._host}]" if ":" in self._host and not self._host.startswith("[") else self._host
            base_url = f"{protocol}://{host_for_url}:{port}"
            url = base_url + test_endpoint

            # Configure SSL for HTTPS
            test_kwargs = kwargs.copy()
            if protocol == "https":
                test_kwargs["ssl"] = ssl_ctx
            else:
                test_kwargs.pop("ssl", None)
            test_kwargs["timeout"] = probe_timeout

            tried.append(url)

            try:
                await self._ensure_session()
                async with asyncio.timeout(PROBE_ASYNC_TIMEOUT):
                    resp = await self._session_request(method, url, **test_kwargs)
                    async with resp:
                        resp.raise_for_status()
                        text = await resp.text()

                        # Valid response - cache this endpoint
                        if text and (text.strip() == "OK" or text.strip().startswith("{")):
                            self._endpoint = base_url
                            # Keep self.port aligned with the cached endpoint. Discovery and the
                            # integration read client.port to persist protocol/port, so a stale
                            # default (443) would mis-persist HTTPS for an HTTP endpoint. See wiim#248.
                            self.port = port
                            self._endpoint_tested = True
                            _LOGGER.debug("Discovered working endpoint: %s (cached permanently)", self._endpoint)
                            return

            except Exception as err:
                _LOGGER.debug("Probe failed for %s: %s", url, err)
                last_error = err
                continue

        # No working endpoint found - craft user-friendly message for connectivity vs protocol
        device_info = {}
        try:
            if self._capabilities:
                device_info = {
                    "firmware_version": self._capabilities.get("firmware_version", "unknown"),
                    "device_model": self._capabilities.get("device_model", "unknown"),
                }
        except Exception:  # noqa: BLE001
            pass

        message = self._format_probe_failure_message(last_error, tried)
        raise WiiMConnectionError(
            message,
            endpoint=test_endpoint,
            attempts=len(tried),
            last_error=last_error,
            device_info=device_info,
        )

    async def _apply_protocol_preference(self) -> None:
        """Switch the cached endpoint to the vendor's preferred protocol when beneficial.

        The initial probe is HTTPS-first because WiiM hardware only listens on HTTPS:443.
        Some LinkPlay devices (Arylic/Up2Stream/generic) also answer on HTTPS:443 but with a
        very slow embedded TLS handshake (~250-450ms), while plain HTTP:80 is ~10x faster.
        Because the device vendor is only known *after* the first request (which already cached
        an endpoint), we correct the choice here once capabilities are known.

        Only a HTTPS->HTTP downgrade is performed, and only when the device's profile prefers
        HTTP *and* plain HTTP actually returns a valid response. Anything else keeps the cached
        endpoint untouched, so WiiM (HTTPS-only) is never affected.

        See: https://github.com/mjcumming/wiim/issues/248
        """
        # Never override an explicit user choice.
        if self._user_specified_protocol or self._user_specified_port:
            return
        if not self._endpoint:
            return

        priority = self._capabilities.get("protocol_priority") or []
        preferred = priority[0] if priority else None
        current = "https" if self._endpoint.startswith("https://") else "http"

        # Only act on the beneficial case: profile prefers HTTP but we cached HTTPS.
        if preferred != "http" or current != "https":
            return

        host_for_url = f"[{self._host}]" if ":" in self._host and not self._host.startswith("[") else self._host
        candidate = f"http://{host_for_url}:80"
        test_url = candidate + "/httpapi.asp?command=getStatusEx"
        probe_timeout = aiohttp.ClientTimeout(connect=PROBE_TIMEOUT_CONNECT, total=PROBE_TIMEOUT_TOTAL)

        try:
            await self._ensure_session()
            async with asyncio.timeout(PROBE_ASYNC_TIMEOUT):
                resp = await self._session_request("GET", test_url, timeout=probe_timeout)
                async with resp:
                    resp.raise_for_status()
                    text = await resp.text()
                    if text and (text.strip() == "OK" or text.strip().startswith("{")):
                        _LOGGER.info(
                            "Switching %s from %s to faster HTTP endpoint %s (profile prefers HTTP)",
                            self._host,
                            self._endpoint,
                            candidate,
                        )
                        self._endpoint = candidate
                        self.port = 80
                        return
            _LOGGER.debug(
                "HTTP preference probe for %s did not return a valid body; keeping %s",
                self._host,
                self._endpoint,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug(
                "HTTP preference probe failed for %s, keeping %s: %s",
                self._host,
                self._endpoint,
                err,
            )

    def _is_connectivity_error(self, err: Exception | None) -> bool:
        """Return True if the error indicates device unreachable (not protocol mismatch)."""
        if err is None:
            return True  # Unknown - treat as connectivity
        err_str = str(err).lower()
        # Connection refused, couldn't connect, network unreachable, timeout
        if any(
            phrase in err_str
            for phrase in (
                "connection refused",
                "couldn't connect",
                "cannot connect",
                "network is unreachable",
                "no route to host",
                "connection reset",
                "timed out",
                "timeout",
            )
        ):
            return True
        # aiohttp.ClientConnectorError typically means connection failed
        if isinstance(err, (aiohttp.ClientConnectorError, aiohttp.ClientError)):
            return True
        if isinstance(err, (asyncio.TimeoutError, aiohttp.ServerTimeoutError)):
            return True
        return False

    def _format_probe_failure_message(self, last_error: Exception | None, tried: list[str]) -> str:
        """Format user-friendly error message for probe failure.

        When all probes fail due to connectivity (device unreachable), use a clear
        message that helps users diagnose network issues rather than protocol selection.
        """
        if self._is_connectivity_error(last_error):
            return (
                f"Device unreachable at {self._host}. "
                f"Connection failed on all attempted protocols. "
                f"Check that the device is powered on, connected to your network, "
                f"and that your host can reach {self._host} (e.g. WSL2/firewall may block access)."
            )
        # Protocol/SSL/response mismatch - keep technical detail
        return f"No working protocol/port found for {self._host}. Tried: {', '.join(tried)}"

    def _build_probe_list(self) -> list[tuple[str, int]]:
        """Build list of protocol/port combinations to probe.

        Respects user-specified protocol/port preferences.

        Returns:
            List of (protocol, port) tuples to try in order
        """
        # Case 1: User specified both protocol and port
        if self._user_specified_protocol and self._user_specified_port:
            _LOGGER.debug(
                "Using user-specified protocol=%s, port=%d", self._user_specified_protocol, self._user_specified_port
            )
            return [(self._user_specified_protocol, self._user_specified_port)]

        # Case 2: User specified port only
        # Try user's port first (respect intent), but fall back to standard probe list if it fails
        if self._user_specified_port:
            # Build list starting with user's port, then standard combinations
            probe_list = []

            if self._user_specified_port == 443:
                # Port 443 implies HTTPS - try that first
                probe_list.append(("https", 443))
            elif self._user_specified_port == 80:
                # Port 80 implies HTTP - try that first
                probe_list.append(("http", 80))
            else:
                # Non-standard port - try both protocols on that port
                probe_list.extend(
                    [
                        ("https", self._user_specified_port),
                        ("http", self._user_specified_port),
                    ]
                )

            # After trying user's port, fall back to standard probe combinations
            # This ensures we figure it out even if user specified wrong port
            standard_list = self._build_standard_probe_list()
            for protocol, port in standard_list:
                if (protocol, port) not in probe_list:  # Avoid duplicates
                    probe_list.append((protocol, port))

            _LOGGER.debug(
                "User specified port=%d, trying user port first, then standard combinations: %s",
                self._user_specified_port,
                probe_list,
            )
            return probe_list

        # Case 3: User specified protocol only (try standard ports for that protocol)
        if self._user_specified_protocol:
            _LOGGER.debug("Using user-specified protocol=%s, trying standard ports", self._user_specified_protocol)
            if self._user_specified_protocol == "https":
                return [
                    ("https", 443),
                    ("https", 4443),
                    ("https", 8443),
                ]
            else:  # http
                return [
                    ("http", 80),
                    ("http", 8080),
                ]

        # Case 4: User specified nothing - probe standard combinations
        return self._build_standard_probe_list()

    def _build_standard_probe_list(self) -> list[tuple[str, int]]:
        """Build standard protocol/port combinations to probe.

        This is used both when no port is specified and as a fallback
        when a user-specified port fails.

        Returns:
            List of (protocol, port) tuples to try in order
        """
        # Use preferred ports from capabilities if specified (Audio Pro MkII)
        preferred_ports = self._capabilities.get("preferred_ports", [])

        if preferred_ports:
            _LOGGER.debug("Using preferred ports from capabilities: %s", preferred_ports)
            return [("https", port) for port in preferred_ports]

        https_combos = [
            ("https", 443),  # WiiM default
            ("https", 4443),  # Audio Pro MkII
            ("https", 8443),  # Alternative HTTPS
        ]
        http_combos = [
            ("http", 80),  # HTTP fallback
            ("http", 8080),  # Alternative HTTP
        ]

        # Honor the device profile's protocol preference when the vendor is already known
        # (e.g. a client constructed with cached Arylic capabilities → HTTP-first). This is
        # what makes the *discovered/persisted* endpoint correct: the coordinator/poll client
        # is created with cached capabilities but skips _detect_capabilities (and therefore
        # _apply_protocol_preference), so the probe order itself must respect protocol_priority.
        # When the vendor is not yet known (cold first probe, no capabilities), fall back to
        # HTTPS-first because WiiM only listens on HTTPS:443; _apply_protocol_preference then
        # corrects the choice once capabilities are detected. See wiim#248.
        priority = self._capabilities.get("protocol_priority") or []
        if priority and priority[0] == "http":
            _LOGGER.debug("Probing HTTP-first per capabilities protocol_priority for %s", self._host)
            return http_combos + https_combos

        # Standard probe list: Try HTTPS first (more common on WiiM devices)
        return https_combos + http_combos

    # ------------------------------------------------------------------
    # Legacy Response Validation ----------------------------------------
    # ------------------------------------------------------------------

    def _validate_legacy_response(
        self,
        response: ApiResponse,
        endpoint: str,
    ) -> ApiResponse:
        """Handle malformed responses from older firmware.

        Args:
            response: API response wrapper (parsed/raw)
            endpoint: API endpoint that was called

        Returns:
            ApiResponse with validated parsed dict for legacy devices
        """
        input_val: dict[str, Any] | str = response.parsed if isinstance(response.parsed, dict) else (response.raw or "")
        validated = validate_audio_pro_response(
            input_val,
            endpoint,
            self.host,
            self._capabilities,
        )
        return ApiResponse(parsed=validated, raw=response.raw)

    # ------------------------------------------------------------------
    # Public API Methods -----------------------------------------------
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying *aiohttp* session."""
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def reprobe(self) -> None:
        """Manually clear endpoint cache and reprobe protocol/port.

        Call this after:
        - Firmware updates
        - Device factory reset
        - Manual device configuration changes

        Raises:
            WiiMConnectionError: If no working endpoint found after reprobe
        """
        _LOGGER.info("Manual reprobe requested for %s", self._host)
        self._endpoint = None
        self._endpoint_tested = False

        # Reprobe by making a status request (will trigger discovery)
        try:
            await self.get_player_status()
            _LOGGER.info("Reprobe complete: %s", self._endpoint)
        except Exception as e:
            _LOGGER.error("Reprobe failed for %s: %s", self._host, e)
            raise

    async def validate_connection(self) -> bool:
        """Return *True* if *getPlayerStatusEx* answers successfully."""
        try:
            await self.get_player_status()
            return True
        except WiiMError:
            return False

    async def get_device_name(self) -> str:
        """Return device-reported *DeviceName* or the raw IP if unavailable."""
        try:
            status = await self.get_player_status()
            name = status.get("DeviceName")
            if name and isinstance(name, str):
                return str(name.strip())
            info = await self.get_device_info()
            name = info.get("DeviceName") or info.get("device_name")
            if name and isinstance(name, str):
                return str(name.strip())
        except WiiMError:
            _LOGGER.debug("Falling back to IP for device name of %s", self._host)
        return str(self._host)

    async def get_status(self) -> dict[str, Any]:
        """Return normalised output of *getStatusEx* (device-level info)."""
        r = await self._request(API_ENDPOINT_STATUS)
        vendor = self._capabilities.get("vendor")
        data = r.parsed if isinstance(r.parsed, dict) else {}
        parsed, self._last_track = parse_player_status(
            data,
            self._last_track,
            vendor,
            loop_mode_scheme=self._capabilities.get("loop_mode_scheme"),
        )
        return parsed

    async def get_device_info(self) -> dict[str, Any]:
        """Lightweight wrapper around *getStatusEx* (raw JSON)."""
        try:
            r = await self._request(API_ENDPOINT_STATUS)
            if isinstance(r.parsed, dict):
                return r.parsed
            return {"raw": r.raw}
        except WiiMError as err:
            _LOGGER.debug("get_device_info failed: %s", err)
            return {}

    async def get_player_status(self) -> dict[str, Any]:
        """Return parsed output of getPlayerStatusEx with device-specific fallbacks.

        Endpoint selection is capability-driven:
        - Standard devices: getPlayerStatusEx
        - Audio Pro MkII: getStatusEx (doesn't support getPlayerStatusEx)
        - HCN_BWD03: getPlayerStatus (getStatusEx returns system info, not player status)

        Note: For HCN_BWD03 devices in multi-room mode, Slave devices may not respond to
        direct status requests. The integration's polling coordinator should handle this
        by deriving slave status from the Master's group state.
        """
        try:
            # Select endpoint based on capabilities (no device-specific checks here)
            endpoint = self._capabilities.get("status_endpoint")
            if endpoint:
                # Device has a specific status endpoint configured
                _LOGGER.debug("Using capability-configured status endpoint: %s", endpoint)
            elif self._capabilities.get("supports_player_status_ex", True):
                # Standard devices use getPlayerStatusEx
                endpoint = "/httpapi.asp?command=getPlayerStatusEx"
            else:
                # Fallback to getStatusEx
                endpoint = "/httpapi.asp?command=getStatusEx"
                _LOGGER.debug("Using getStatusEx fallback endpoint")

            try:
                r = await self._request(endpoint)
                # Raw HTTP response available for debugging if needed, but not logged
                # to avoid spam on every poll cycle
            except WiiMRequestError as primary_err:
                # If getPlayerStatusEx fails, try getStatusEx as fallback
                # Skip fallback if we're already using a specific configured endpoint
                if not self._capabilities.get("status_endpoint") and endpoint.endswith("getPlayerStatusEx"):
                    fallback_endpoint = "/httpapi.asp?command=getStatusEx"
                    _LOGGER.debug(
                        "Primary status endpoint failed (%s); retrying with fallback %s",
                        endpoint,
                        fallback_endpoint,
                    )
                    r = await self._request(fallback_endpoint)
                    # Fallback succeeded - raw response available for debugging if needed
                else:
                    raise primary_err

            data = r.parsed if isinstance(r.parsed, dict) else {}
            parsed, self._last_track = parse_player_status(
                data,
                self._last_track,
                self._capabilities.get("vendor"),
                loop_mode_scheme=self._capabilities.get("loop_mode_scheme"),
            )

            # If artwork is missing or invalid and device supports getMetaInfo, try to fetch it
            entity_picture = parsed.get("entity_picture")
            from .constants import DEFAULT_WIIM_LOGO_URL

            # Check if we have valid artwork (not default logo, not invalid values)
            has_valid_artwork = (
                entity_picture
                and str(entity_picture).strip()
                and str(entity_picture).strip().lower() not in ("unknow", "unknown", "un_known", "none", "")
                and str(entity_picture).strip() != DEFAULT_WIIM_LOGO_URL
            )

            if not has_valid_artwork:
                # Check if get_meta_info method is available (from PlaybackAPI mixin) and the
                # device actually implements it (issue #248 - skip "unknown command" devices).
                if self._capabilities.get("supports_metadata", True) and hasattr(self, "get_meta_info"):
                    try:
                        meta_info = await self.get_meta_info()
                        if meta_info and "metaData" in meta_info:
                            meta_data = meta_info["metaData"]
                            # Extract artwork URL from getMetaInfo response
                            # Try various field names that might contain artwork
                            artwork_url = (
                                meta_data.get("cover")
                                or meta_data.get("cover_url")
                                or meta_data.get("albumart")
                                or meta_data.get("albumArtURI")
                                or meta_data.get("albumArtUri")
                                or meta_data.get("albumarturi")
                                or meta_data.get("art_url")
                                or meta_data.get("artwork_url")
                                or meta_data.get("pic_url")
                            )

                            # Validate artwork URL
                            if artwork_url and str(artwork_url).strip() not in (
                                "unknow",
                                "unknown",
                                "un_known",
                                "",
                                "none",
                            ):
                                # Basic URL validation
                                if "http" in str(artwork_url).lower() or str(artwork_url).startswith("/"):
                                    # Add cache-busting parameter
                                    title = parsed.get("title", "")
                                    artist = parsed.get("artist", "")
                                    album = parsed.get("album", "")
                                    cache_key = f"{title}-{artist}-{album}"
                                    if cache_key:
                                        encoded = quote(cache_key)
                                        sep = "&" if "?" in artwork_url else "?"
                                        artwork_url = f"{artwork_url}{sep}cache={encoded}"
                                    parsed["entity_picture"] = artwork_url
                                    _LOGGER.debug("Merged artwork URL from getMetaInfo: %s", artwork_url)
                    except Exception as meta_err:
                        # getMetaInfo failed - not critical, continue without artwork
                        _LOGGER.debug("Failed to fetch artwork from getMetaInfo: %s", meta_err)

            return parsed
        except Exception as err:
            # Log specific error types for debugging
            error_str = str(err).lower()
            if "404" in error_str:
                _LOGGER.debug("getPlayerStatusEx not supported by device at %s", self.host)
            elif "timeout" in error_str:
                _LOGGER.debug("Timeout getting player status from %s", self.host)
            else:
                _LOGGER.debug("get_player_status failed: %s", err)
            raise

    # ------------------------------------------------------------------
    # Typed Wrappers (Pydantic) ----------------------------------------
    # ------------------------------------------------------------------

    async def get_device_info_model(self) -> DeviceInfo:
        """Return :class:`DeviceInfo` parsed by *pydantic*."""
        return DeviceInfo.model_validate(await self.get_device_info())

    async def get_player_status_model(self) -> PlayerStatus:
        """Return :class:`PlayerStatus` parsed by *pydantic*."""
        return PlayerStatus.model_validate(await self.get_player_status())
