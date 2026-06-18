"""Main WiiM client facade.

This module provides the main WiiMClient class that composes all API mixins
into a single, unified interface for communicating with WiiM and LinkPlay devices.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
import xml.etree.ElementTree as ET
from typing import Any

from aiohttp import ClientSession

from .api.audio_settings import AudioSettingsAPI
from .api.base import BaseWiiMClient
from .api.bluetooth import BluetoothAPI
from .api.device import DeviceAPI
from .api.diagnostics import DiagnosticsAPI
from .api.eq import EQAPI
from .api.firmware import FirmwareAPI
from .api.group import GroupAPI
from .api.lms import LMSAPI
from .api.misc import MiscAPI
from .api.peq import PEQAPI
from .api.playback import PlaybackAPI
from .api.preset import PresetAPI
from .api.subwoofer import SubwooferAPI
from .api.timer import TimerAPI
from .capabilities import WiiMCapabilities, detect_device_capabilities
from .exceptions import (
    WiiMConnectionError,
    WiiMError,
    WiiMInvalidDataError,
    WiiMRequestError,
    WiiMResponseError,
    WiiMTimeoutError,
)
from .models import DeviceInfo

_LOGGER = logging.getLogger(__name__)


class WiiMClient(
    BluetoothAPI,
    AudioSettingsAPI,
    SubwooferAPI,
    LMSAPI,
    MiscAPI,
    DeviceAPI,
    PlaybackAPI,
    EQAPI,
    PEQAPI,
    GroupAPI,
    PresetAPI,
    DiagnosticsAPI,
    FirmwareAPI,
    TimerAPI,
    BaseWiiMClient,
):
    """Unified WiiM HTTP API client – modular with official and unofficial endpoints.

    This client includes both official WiiM HTTP API endpoints and unofficial
    reverse-engineered endpoints. The unofficial endpoints may not be available
    on all firmware versions or device models.

    The client automatically detects device capabilities and adapts its behavior
    accordingly. It supports multiple LinkPlay-based device vendors including:
    - WiiM devices (Pro, Mini, Amp, Ultra)
    - Arylic devices (Up2Stream, S10+)
    - Audio Pro devices (Addon C5/C10, MkII, W-Generation)
    - Generic LinkPlay devices

    Example:
        ```python
        import asyncio
        from pywiim import WiiMClient

        async def main():
            # Create client
            client = WiiMClient("192.168.1.100")

            # Detect capabilities (optional, done automatically on first request)
            device_info = await client.get_device_info_model()
            capabilities = await client._detect_capabilities()

            # Use the client
            status = await client.get_player_status()
            await client.set_volume(0.5)
            await client.play()

            # Clean up
            await client.close()

        asyncio.run(main())
        ```

    Args:
        host: Device hostname or IP address. May include port (e.g., "192.168.1.100:8080").
        port: Optional port override (default: 80 for HTTP, 443 for HTTPS).
        timeout: Network timeout in seconds (default: 5.0).
        ssl_context: Custom SSL context for advanced use cases.
        session: Optional shared aiohttp ClientSession for connection pooling.
        capabilities: Optional pre-detected device capabilities dict.
            If not provided, capabilities will be detected automatically on first use.

    Attributes:
        capabilities: Device capabilities dictionary (read-only).
        host: Device hostname or IP address (read-only).
        base_url: Base URL used for the last successful request (read-only).
    """

    def __init__(
        self,
        host: str,
        port: int | None = None,
        protocol: str | None = None,
        timeout: float = 5.0,
        ssl_context: ssl.SSLContext | None = None,
        session: ClientSession | None = None,
        capabilities: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the WiiM client.

        Args:
            host: Device hostname or IP address
            port: Optional port override. If None, will probe standard ports.
            protocol: Optional protocol override ("http" or "https"). If None, will probe both.
            timeout: Network timeout in seconds
            ssl_context: Custom SSL context for advanced use cases
            session: Optional shared aiohttp ClientSession
            capabilities: Optional pre-detected device capabilities
        """
        super().__init__(host, port, protocol, timeout, ssl_context, session, capabilities)

        # Capability detection system
        self._capability_detector = WiiMCapabilities()
        self._capabilities_detected = capabilities is not None
        self._detecting_capabilities = False  # Flag to prevent recursion
        # When True, a recoverable capability-detection failure logs at debug
        # instead of warning. Set by discovery probes (validate_device /
        # is_linkplay_device), where probing a non-LinkPlay device that fails to
        # answer is the expected, benign outcome -- not something to warn about.
        self._quiet_capabilities = False

    async def _detect_capabilities(self, force: bool = False) -> dict[str, Any]:
        """Detect device capabilities and update client configuration.

        This method is called automatically on first use if capabilities were not
        provided during initialization. It probes the device to determine:
        - Device type (WiiM, Arylic, Audio Pro, etc.)
        - Firmware version
        - Supported endpoints
        - Protocol preferences
        - Generation-specific quirks

        Args:
            force: When True, bypass the early return and re-run probing (used by
                :meth:`refresh_capabilities` so OTA firmware can change support flags).

        Returns:
            Dictionary of detected capabilities.

        Raises:
            WiiMError: If capability detection fails.
        """
        if self._capabilities_detected and not force:
            return self._capabilities

        try:
            # Get device info first (use base class method to avoid recursion)
            device_info = await BaseWiiMClient.get_device_info_model(self)

            # Detect capabilities using the capability detector
            capabilities = await self._capability_detector.detect_capabilities(self, device_info, force=force)

            # Ensure vendor is normalized (safety check)
            from .normalize import normalize_vendor

            if "vendor" in capabilities:
                capabilities["vendor"] = normalize_vendor(capabilities["vendor"])
            elif "vendor" not in capabilities or not capabilities.get("vendor"):
                # Fallback: detect vendor if missing
                from .capabilities import detect_vendor

                vendor = detect_vendor(device_info)
                capabilities["vendor"] = normalize_vendor(vendor)

            # Best-effort enrichment from UPnP description.xml.
            # This augments capabilities with advertised UPnP services and metadata.
            # It never blocks or fails capability detection if unavailable.
            upnp_caps = await self._safe_collect_upnp_description_capabilities()
            if upnp_caps:
                capabilities.update(upnp_caps)

            # Update client capabilities
            self._capabilities.update(capabilities)

            # Update timeout based on capabilities
            if "response_timeout" in capabilities:
                self.timeout = capabilities["response_timeout"]

            self._capabilities_detected = True

            # Now that the vendor/profile is known, correct the cached endpoint to the
            # device's preferred protocol (e.g. HTTP-first for Arylic). No-op for WiiM.
            await self._apply_protocol_preference()

            # Capabilities are already logged in capabilities.py with more detail
            # Only log at debug level here to avoid duplicate messages
            _LOGGER.debug(
                "Capabilities applied to client for %s: vendor=%s, generation=%s",
                self.host,
                capabilities.get("vendor", "unknown"),
                capabilities.get("audio_pro_generation", "unknown"),
            )

            return self._capabilities

        except Exception as err:
            # This path is recoverable: we fall back to static detection below.
            # During discovery probing of arbitrary LAN devices (a Yamaha AVR, a
            # TV, etc. handed over by HA's broad SSDP MediaRenderer matcher) this
            # failure is the expected outcome, so probe callers set
            # _quiet_capabilities to keep the log clean (see issue mjcumming/wiim#249).
            _LOGGER.log(
                logging.DEBUG if self._quiet_capabilities else logging.WARNING,
                "Failed to detect capabilities for %s: %s. Using defaults.",
                self.host,
                err,
            )
            # Fall back to static detection
            try:
                device_info = await BaseWiiMClient.get_device_info_model(self)
                capabilities = detect_device_capabilities(device_info)
                # Ensure vendor is set in static detection
                from .capabilities import detect_vendor
                from .normalize import normalize_vendor

                if "vendor" not in capabilities or not capabilities.get("vendor"):
                    vendor = detect_vendor(device_info)
                    capabilities["vendor"] = normalize_vendor(vendor)
                else:
                    capabilities["vendor"] = normalize_vendor(capabilities["vendor"])
                upnp_caps = await self._safe_collect_upnp_description_capabilities()
                if upnp_caps:
                    capabilities.update(upnp_caps)
                capabilities.setdefault("supports_subwoofer", False)
                self._capabilities.update(capabilities)
                self._capabilities_detected = True
                await self._apply_protocol_preference()
                return self._capabilities
            except Exception:
                # If even static detection fails, use empty capabilities
                self._capabilities_detected = True
                return self._capabilities

    async def refresh_capabilities(self, force: bool = True) -> dict[str, Any]:
        """Re-run capability detection including runtime probes (e.g. after firmware OTA).

        Args:
            force: When True (default), drop the detector cache for this device so
                probes such as getSubLPF run again.

        Returns:
            Updated capabilities dict (same object as :attr:`capabilities`).
        """
        device_info = await BaseWiiMClient.get_device_info_model(self)
        if force:
            self._capability_detector.invalidate_device(f"{self.host}:{device_info.uuid}")
        self._capabilities_detected = False
        return await self._detect_capabilities(force=force)

    async def _safe_collect_upnp_description_capabilities(self) -> dict[str, Any]:
        """Collect UPnP description.xml metadata without raising on errors."""
        try:
            return await self._collect_upnp_description_capabilities()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("UPnP description enrichment skipped for %s: %s", self.host, err)
            return {}

    async def _collect_upnp_description_capabilities(self) -> dict[str, Any]:
        """Fetch and parse UPnP description.xml to augment capabilities."""
        xml_text = await self._fetch_upnp_description_xml()
        if not xml_text:
            return {}
        parsed = self._parse_upnp_description_xml(xml_text)
        if parsed:
            _LOGGER.debug(
                "Collected UPnP description capabilities for %s: services=%d",
                self.host,
                len(parsed.get("upnp_service_types", [])),
            )
        return parsed

    async def _fetch_upnp_description_xml(self) -> str | None:
        """Best-effort fetch of UPnP description.xml with short timeout."""
        host_url = self._host_url
        preferred_scheme = "https" if self.is_https else "http"
        schemes = [preferred_scheme, "https" if preferred_scheme == "http" else "http"]
        ports = (49152, 59152)
        urls = [f"{scheme}://{host_url}:{port}/description.xml" for scheme in schemes for port in ports]

        for url in urls:
            try:
                request_kwargs: dict[str, Any] = {}
                if url.startswith("https://"):
                    request_kwargs["ssl"] = await self._get_ssl_context()
                else:
                    request_kwargs["ssl"] = False

                async with asyncio.timeout(2):
                    resp = await self._session_request("GET", url, **request_kwargs)
                    async with resp:
                        if resp.status != 200:
                            continue
                        text = await resp.text()
                        if text and "<root" in text and "device" in text:
                            return text
            except Exception:  # noqa: BLE001
                continue

        return None

    @staticmethod
    def _parse_upnp_description_xml(xml_text: str) -> dict[str, Any]:
        """Parse selected fields and service flags from UPnP description.xml."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return {}

        device = root.find(".//{*}device")
        if device is None:
            return {}

        def get_text(tag: str) -> str | None:
            el = device.find(f"{{*}}{tag}")
            if el is None or el.text is None:
                return None
            value = el.text.strip()
            return value or None

        service_types: list[str] = []
        for service in device.findall(".//{*}service"):
            service_type = service.find("{*}serviceType")
            if service_type is not None and service_type.text:
                value = service_type.text.strip()
                if value:
                    service_types.append(value)

        unique_service_types = sorted(set(service_types))
        service_set = set(unique_service_types)

        capabilities: dict[str, Any] = {
            "upnp_description_available": True,
            "upnp_service_types": unique_service_types,
            "upnp_has_playqueue": "urn:schemas-wiimu-com:service:PlayQueue:1" in service_set,
            "upnp_has_qplay": "urn:schemas-tencent-com:service:QPlay:1" in service_set,
            "upnp_has_content_directory": "urn:schemas-upnp-org:service:ContentDirectory:1" in service_set,
        }

        friendly_name = get_text("friendlyName")
        model_name = get_text("modelName")
        udn = get_text("UDN")
        if friendly_name:
            capabilities["upnp_friendly_name"] = friendly_name
        if model_name:
            capabilities["upnp_model_name"] = model_name
        if udn:
            capabilities["upnp_udn"] = udn

        return capabilities

    async def get_device_info_model(self) -> DeviceInfo:
        """Get device information as a Pydantic model.

        This method automatically triggers capability detection on first use
        if capabilities were not provided during initialization.

        Returns:
            DeviceInfo model with device information.

        Raises:
            WiiMError: If the request fails.
        """
        # Auto-detect capabilities on first use if not already detected
        if not self._capabilities_detected and not self._detecting_capabilities:
            # Use flag to prevent recursion instead of setting _capabilities_detected
            self._detecting_capabilities = True
            try:
                await self._detect_capabilities()
            except Exception:
                # If detection fails, reset flag and re-raise
                self._detecting_capabilities = False
                raise
            finally:
                self._detecting_capabilities = False

        # Call parent method (BaseWiiMClient)
        return await BaseWiiMClient.get_device_info_model(self)

    async def get_player_status(self) -> dict[str, Any]:
        """Get player status with automatic capability detection.

        This method automatically triggers capability detection on first use
        if capabilities were not provided during initialization.

        Returns:
            Dictionary with player status information.

        Raises:
            WiiMError: If the request fails.
        """
        # Auto-detect capabilities on first use if not already detected
        if not self._capabilities_detected and not self._detecting_capabilities:
            # Use flag to prevent recursion instead of setting _capabilities_detected
            self._detecting_capabilities = True
            try:
                await self._detect_capabilities()
            except Exception:
                # If detection fails, reset flag and re-raise
                self._detecting_capabilities = False
                raise
            finally:
                self._detecting_capabilities = False

        # Call parent method (BaseWiiMClient)
        return await BaseWiiMClient.get_player_status(self)

    async def close(self) -> None:
        """Close the client and clean up resources.

        This method should be called when the client is no longer needed.
        It closes the HTTP session and cleans up any resources.
        """
        await BaseWiiMClient.close(self)


# Export exceptions for convenience
__all__ = [
    "WiiMClient",
    "WiiMError",
    "WiiMRequestError",
    "WiiMResponseError",
    "WiiMTimeoutError",
    "WiiMConnectionError",
    "WiiMInvalidDataError",
]
