"""UPnP client for WiiM/Linkplay devices.

Follows Samsung/DLNA pattern using async_upnp_client (DmrDevice pattern).
Framework-agnostic implementation for use in any Python application.
"""

from __future__ import annotations

import asyncio
import logging
import ssl
from collections.abc import Callable
from datetime import timedelta
from typing import Any, cast

from aiohttp import ClientError, ClientSession, TCPConnector
from async_upnp_client.aiohttp import AiohttpNotifyServer, AiohttpSessionRequester
from async_upnp_client.client import UpnpDevice
from async_upnp_client.client_factory import UpnpFactory
from async_upnp_client.exceptions import UpnpError, UpnpResponseError
from async_upnp_client.profiles.dlna import DmrDevice
from async_upnp_client.utils import async_get_local_ip

_LOGGER = logging.getLogger(__name__)


class UpnpClient:
    """UPnP client wrapper for WiiM devices using async-upnp-client.

    Provides SOAP action calls and service discovery for AVTransport
    and RenderingControl services. Framework-agnostic implementation.
    """

    def __init__(
        self,
        host: str,
        description_url: str,
        session: Any,
    ) -> None:
        """Initialize UPnP client.

        Args:
            host: Device hostname or IP
            description_url: URL to device description.xml
            session: aiohttp session for HTTP requests (reused when possible)
        """
        self.host = host
        self.description_url = description_url
        self.session = session  # External session to reuse when possible
        self._device: UpnpDevice | None = None
        self._dmr_device: DmrDevice | None = None  # DmrDevice wrapper for subscriptions (DLNA pattern)
        self._av_transport_service: Any | None = None
        self._rendering_control_service: Any | None = None
        self._content_directory_service: Any | None = None
        self._play_queue_service: Any | None = None
        self._notify_server: AiohttpNotifyServer | None = None
        self._internal_session: ClientSession | None = None  # Session we created internally (only if needed)

    @classmethod
    async def create(
        cls,
        host: str,
        description_url: str,
        session: ClientSession | None = None,
    ) -> UpnpClient:
        """Create and initialize UPnP client from description URL.

        Args:
            host: Device hostname or IP
            description_url: URL to device description.xml
            session: Optional aiohttp session (reused for HTTP operations,
                new session created only for HTTPS with special SSL config)

        Returns:
            Initialized UpnpClient instance
        """
        client = cls(host, description_url, session)
        await client._initialize()
        return client

    async def _initialize(self) -> None:
        """Initialize UPnP device and services."""
        try:
            # Use passed session for HTTP operations, create new session only for HTTPS with special SSL config
            if self.description_url.startswith("https://"):
                _LOGGER.info("Using HTTPS for UPnP description (self-signed cert support enabled)")
                # HTTPS with self-signed cert support - need special SSL config
                # Create new session with custom SSL context
                # Use executor to avoid blocking event loop (Python 3.13 detects blocking calls)
                ssl_context = await asyncio.to_thread(lambda: ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                ssl_context.set_ciphers("ALL:@SECLEVEL=0")
                connector = TCPConnector(ssl=ssl_context)
                session = ClientSession(connector=connector)
                self._internal_session = session  # Track for cleanup
            else:
                # HTTP - can reuse passed session if available
                if self.session is not None and not self.session.closed:
                    _LOGGER.debug("Reusing passed aiohttp session for UPnP HTTP operations")
                    session = self.session
                    self._internal_session = None  # Not our session, don't close it
                else:
                    _LOGGER.info("Using HTTP for UPnP description (no SSL needed)")
                    # No session provided or session is closed - create our own
                    connector = TCPConnector(ssl=False)
                    session = ClientSession(connector=connector)
                    self._internal_session = session  # Track for cleanup

            # DLNA pattern: with_sleep=True adds retry logic, timeout ensures we don't hang
            requester = AiohttpSessionRequester(session, with_sleep=True, timeout=10)

            # Create UPnP device from description.xml using factory (DLNA/DMR pattern)
            _LOGGER.info("Fetching UPnP device description from: %s", self.description_url)
            factory = UpnpFactory(requester, non_strict=True)

            # Add explicit timeout wrapper (5 seconds for description.xml fetch)
            try:
                async with asyncio.timeout(5):
                    self._device = await factory.async_create_device(self.description_url)
            except TimeoutError as timeout_err:
                _LOGGER.error(
                    "❌ Timeout fetching UPnP description from %s after 5 seconds - "
                    "device may not support UPnP properly",
                    self.description_url,
                )
                raise UpnpError(f"Timeout fetching UPnP description: {timeout_err}") from timeout_err

            _LOGGER.info(
                "✅ Successfully fetched and parsed UPnP device description for %s",
                self.host,
            )

            # Get AVTransport service
            if self._device is None:
                raise UpnpError("Device not initialized")
            self._av_transport_service = self._device.service("urn:schemas-upnp-org:service:AVTransport:1")

            # Get RenderingControl service
            self._rendering_control_service = self._device.service("urn:schemas-upnp-org:service:RenderingControl:1")

            # Get ContentDirectory service (for queue browsing) - optional
            try:
                self._content_directory_service = self._device.service(
                    "urn:schemas-upnp-org:service:ContentDirectory:1"
                )
            except KeyError:
                # ContentDirectory is optional - not all devices support it
                self._content_directory_service = None
                _LOGGER.debug(
                    "Device %s does not advertise ContentDirectory service - queue retrieval will not be available",
                    self.host,
                )

            # Get PlayQueue service (for playlist clearing) - optional, LinkPlay-specific
            try:
                self._play_queue_service = self._device.service("urn:schemas-wiimu-com:service:PlayQueue:1")
            except KeyError:
                # PlayQueue is optional - not all devices support it
                self._play_queue_service = None
                _LOGGER.debug(
                    "Device %s does not advertise PlayQueue service - playlist clearing via UPnP will not be available",
                    self.host,
                )

            if not self._av_transport_service:
                _LOGGER.warning(
                    "⚠️  Device %s does not advertise AVTransport service - UPnP eventing may not work",
                    self.host,
                )
            if not self._rendering_control_service:
                _LOGGER.warning(
                    "⚠️  Device %s does not advertise RenderingControl service - UPnP volume events may not work",
                    self.host,
                )
            if not self._content_directory_service:
                _LOGGER.info(
                    "ℹ️  Device %s does not advertise ContentDirectory service - queue retrieval will not be available",
                    self.host,
                )

            _LOGGER.info(
                "✅ UPnP client initialized for %s: AVTransport=%s, RenderingControl=%s, "
                "ContentDirectory=%s, PlayQueue=%s",
                self.host,
                self._av_transport_service is not None,
                self._rendering_control_service is not None,
                self._content_directory_service is not None,
                self._play_queue_service is not None,
            )

        except TimeoutError as err:
            _LOGGER.error(
                "❌ Timeout initializing UPnP client for %s after 5 seconds",
                self.host,
            )
            raise UpnpError(f"Timeout creating UPnP device: {err}") from err
        except ClientError as err:
            _LOGGER.error(
                "❌ Network error initializing UPnP client for %s: %s",
                self.host,
                err,
            )
            raise UpnpError(f"Network error creating UPnP device: {err}") from err
        except Exception as err:
            _LOGGER.error(
                "❌ Failed to initialize UPnP client for %s: %s (type: %s)",
                self.host,
                err,
                type(err).__name__,
            )
            raise UpnpError(f"Failed to create UPnP device: {err}") from err

    async def start_notify_server(
        self,
        callback_host: str | None = None,
        callback_port: int = 0,
    ) -> AiohttpNotifyServer:
        """Start the NOTIFY server for receiving event notifications.

        Args:
            callback_host: Host IP for callback URL (auto-detect if None)
            callback_port: Port for callback (0 = ephemeral)

        Returns:
            Started AiohttpNotifyServer instance
        """
        # Try to reuse passed session for notify server (used for subscription requests)
        # Only create new session if we need special SSL config or no session provided
        if self.session is not None and not self.session.closed:
            _LOGGER.debug("Reusing passed aiohttp session for UPnP notify server")
            session = self.session
        else:
            # Create notify server (DLNA/DMR pattern) with SSL disabled for self-signed certs
            # Use executor to avoid blocking event loop (Python 3.13 detects blocking calls)
            ssl_context = await asyncio.to_thread(lambda: ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            ssl_context.set_ciphers("ALL:@SECLEVEL=0")

            connector = TCPConnector(ssl=ssl_context)
            session = ClientSession(connector=connector)
        requester = AiohttpSessionRequester(session, with_sleep=True, timeout=10)

        # Get the correct local IP for callback URL
        if callback_host:
            # Use explicit host if provided
            event_ip = callback_host
            _LOGGER.info("Using explicit host IP for UPnP callback: %s", event_ip)
        else:
            # Try to auto-detect
            try:
                _, event_ip = await async_get_local_ip(f"http://{self.host}:49152", asyncio.get_event_loop())
                _LOGGER.info("Detected local IP for UPnP callback: %s", event_ip)
                # Warn if we're in a container network that might not be reachable
                if event_ip.startswith("172."):
                    _LOGGER.warning(
                        "⚠️  Detected container network IP %s - devices on your LAN may not be able to reach "
                        "this for UPnP events. Solutions: 1) Use 'network_mode: host' in Docker, "
                        "2) Add '--network=host' to devcontainer.json runArgs, "
                        "or 3) Pass the host's LAN IP via callback_host parameter.",
                        event_ip,
                    )
            except Exception as err:
                _LOGGER.warning("Could not detect local IP for UPnP callback: %s", err)
                event_ip = "0.0.0.0"

        source_ip = event_ip if callback_port == 0 else callback_host or event_ip

        self._notify_server = AiohttpNotifyServer(
            requester=requester,
            source=(source_ip, callback_port),
            loop=None,  # Use default event loop
        )

        await self._notify_server.async_start_server()

        # Get server info from the notify server instance
        server_host = getattr(self._notify_server, "host", "unknown")
        server_port = getattr(self._notify_server, "port", "unknown")
        callback_url = getattr(self._notify_server, "callback_url", None)

        # Enhanced callback URL logging with validation
        if callback_url:
            _LOGGER.info(
                "✅ Notify server started on %s:%s",
                server_host,
                server_port,
            )
            _LOGGER.info(
                "📡 UPnP callback URL: %s (this URL will be sent to devices in SUBSCRIBE requests)",
                callback_url,
            )

            # Detect and warn about unreachable container IPs
            is_unreachable = False
            unreachable_reason = None

            if server_host.startswith("172."):
                is_unreachable = True
                unreachable_reason = "container network IP (172.x.x.x)"
            elif server_host == "0.0.0.0":
                is_unreachable = True
                unreachable_reason = "wildcard binding (0.0.0.0) - devices cannot reach this"

            if is_unreachable:
                _LOGGER.error(
                    "⚠️  CRITICAL: Callback URL is using %s - devices on your LAN CANNOT reach this for UPnP events!",
                    unreachable_reason,
                )
                _LOGGER.error(
                    "   ➤ Solutions:",
                )
                _LOGGER.error(
                    "      1. Use 'network_mode: host' in docker-compose.yml",
                )
                _LOGGER.error(
                    "      2. Add '--network=host' to devcontainer.json runArgs",
                )
                _LOGGER.error(
                    "      3. Configure callback_host parameter with your host's LAN IP",
                )
                _LOGGER.error(
                    "      4. Use port forwarding to map callback port to host",
                )
                _LOGGER.error(
                    "   Application will fall back to HTTP polling, but real-time events will not work.",
                )
            else:
                _LOGGER.info(
                    "✓ Callback URL appears reachable",
                )
        else:
            _LOGGER.error("⚠️  CRITICAL: No callback_url from notify server - UPnP events will NOT work!")
            _LOGGER.error(
                "   This is likely a networking issue - devices cannot send NOTIFY events to the container",
            )
            _LOGGER.error(
                "   Check Docker networking configuration (use --network=host or configure port forwarding)",
            )

        # Create DmrDevice wrapper (DLNA pattern from Samsung/DLNA integrations)
        # This provides async_subscribe_services() method
        if self._device is None:
            raise UpnpError("Device not initialized")
        if self._notify_server is None:
            raise UpnpError("Notify server not started")
        self._dmr_device = DmrDevice(self._device, self._notify_server.event_handler)
        _LOGGER.info("DmrDevice wrapper created for %s", self.host)

        return self._notify_server

    async def unwind_notify_server(self) -> None:
        """Stop and clean up the NOTIFY server."""
        if self._notify_server:
            try:
                await self._notify_server.async_stop_server()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Error stopping notify server for %s: %s", self.host, err)
            finally:
                self._notify_server = None
                _LOGGER.debug("Notify server stopped for %s", self.host)

    async def close(self) -> None:
        """Close the UPnP client and clean up resources.

        Stops the notify server and closes the internal aiohttp session (only if we created it).
        Does not close externally-provided sessions.
        """
        # Stop notify server first
        await self.unwind_notify_server()

        # Close internal session (only if we created it, not if it was passed in)
        if self._internal_session and not self._internal_session.closed:
            try:
                await self._internal_session.close()
                _LOGGER.debug("Closed internal session for %s", self.host)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Error closing internal session for %s: %s", self.host, err)
            finally:
                self._internal_session = None

    @property
    def av_transport(self) -> Any:
        """Get AVTransport service."""
        return self._av_transport_service

    @property
    def rendering_control(self) -> Any:
        """Get RenderingControl service."""
        return self._rendering_control_service

    @property
    def content_directory(self) -> Any:
        """Get ContentDirectory service."""
        return self._content_directory_service

    @property
    def play_queue(self) -> Any:
        """Get PlayQueue service."""
        return self._play_queue_service

    @property
    def notify_server(self) -> AiohttpNotifyServer:
        """Get notify server instance."""
        if self._notify_server is None:
            raise RuntimeError("notify server not started")
        return self._notify_server

    async def async_subscribe(
        self,
        service_name: str,
        timeout: int = 1800,
        sub_callback: Any = None,
        renew_fail_callback: Any = None,
    ) -> Any:
        """Subscribe to UPnP service events (Samsung/DLNA pattern).

        Uses event_handler.async_subscribe() like DmrDevice does.
        See: async_upnp_client/profiles/dlna.py async_subscribe_services()

        Args:
            service_name: Name of service ("AVTransport" or "RenderingControl")
            timeout: Subscription timeout in seconds
            sub_callback: Callback function for events (signature: (service, state_variables))
            renew_fail_callback: Unused (renewal handled separately)

        Returns:
            Subscription object (for storing and managing callback)
        """
        # Map service name to attribute name
        service_attr_map = {
            "avtransport": "_av_transport_service",
            "renderingcontrol": "_rendering_control_service",
            "contentdirectory": "_content_directory_service",
            "play_queue": "_play_queue_service",
            "playqueue": "_play_queue_service",
        }
        service_attr = service_attr_map.get(service_name.lower())
        if not service_attr:
            raise UpnpError(f"Service {service_name} not available")

        service = getattr(self, service_attr)
        if not service:
            raise UpnpError(f"Service {service_name} not initialized")

        if not self._notify_server:
            raise UpnpError("Notify server not started")

        # Get notify server host/port using getattr to handle attribute access
        server_host = getattr(self._notify_server, "host", "localhost")
        server_port = getattr(self._notify_server, "port", 8000)

        callback_url = f"http://{server_host}:{server_port}/notify"

        # Log the subscription request with callback URL
        _LOGGER.info(
            "📨 Subscribing to %s service on %s",
            service_name,
            self.host,
        )
        _LOGGER.debug(
            "   → Using callback URL: %s (devices will send NOTIFY events to this URL)",
            callback_url,
        )
        _LOGGER.debug("   → Requested timeout: %d seconds", timeout)

        # Following DmrDevice pattern from dlna_dmr/samsungtv integrations:
        # 1. Set service.on_event callback BEFORE subscribing
        # 2. Call event_handler.async_subscribe(service, timeout=...) which returns (sid, timeout_timedelta)
        # See: /workspaces/core/homeassistant/components/dlna_dmr/media_player.py:391
        # and async_upnp_client/profiles/dlna.py async_subscribe_services()
        event_handler = self._notify_server.event_handler

        # Set callback on service (DmrDevice pattern: service.on_event is called by event_handler)
        if sub_callback:
            service.on_event = sub_callback

        # Subscribe - returns (sid, timeout_timedelta) tuple
        # event_handler.async_subscribe() expects timeout as timedelta, not int
        timeout_delta = timedelta(seconds=timeout)
        sid, timeout_timedelta = await event_handler.async_subscribe(
            service,
            timeout=timeout_delta,
        )

        # Convert timedelta to seconds
        granted_timeout = int(timeout_timedelta.total_seconds())

        # Create subscription wrapper for tracking SID and timeout
        class SubscriptionWrapper:
            """Wrapper for subscription info (Samsung/DLNA pattern compatibility)."""

            def __init__(self, sid: str, timeout: int, service_obj: Any):
                self.sid = sid
                self.timeout = timeout
                self.service = service_obj

            @property
            def callback(self):
                return getattr(self.service, "on_event", None)

            @callback.setter
            def callback(self, value):
                # Update service.on_event (DmrDevice pattern)
                self.service.on_event = value

        subscription = SubscriptionWrapper(sid, granted_timeout, service)

        _LOGGER.info(
            "✅ Successfully subscribed to %s on %s",
            service_name,
            self.host,
        )
        _LOGGER.info(
            "   → SID: %s",
            sid,
        )
        _LOGGER.info(
            "   → Timeout: %d seconds (requested %d, granted %d)",
            granted_timeout,
            timeout,
            granted_timeout,
        )
        _LOGGER.info(
            "   → Callback URL: %s",
            callback_url,
        )

        return subscription

    async def async_subscribe_services(
        self,
        event_callback: Any = None,
    ) -> None:
        """Subscribe to UPnP services (DLNA pattern).

        This follows the Samsung/DLNA pattern using DmrDevice.async_subscribe_services().

        Args:
            event_callback: Callback function for events (called with service and state_variables)
        """
        if not self._dmr_device:
            raise UpnpError("DmrDevice not initialized - call start_notify_server() first")

        try:
            # Set event callback
            if event_callback:
                self._dmr_device.on_event = event_callback

            # Subscribe to all services (DLNA pattern)
            _LOGGER.info("📨 Subscribing to all UPnP services using DmrDevice pattern for %s", self.host)
            callback_url = getattr(self._notify_server, "callback_url", "unknown")
            _LOGGER.debug("   → Using callback URL: %s", callback_url)

            await self._dmr_device.async_subscribe_services(auto_resubscribe=True)
            _LOGGER.info("✅ Successfully subscribed to UPnP services for %s (DLNA/DmrDevice pattern)", self.host)
            _LOGGER.debug(
                "   → Devices will send NOTIFY events to: %s",
                callback_url,
            )

        except UpnpResponseError as err:
            # Device rejected subscription - this is OK, we'll poll instead
            _LOGGER.debug("Device rejected subscription for %s: %r", self.host, err)
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Error subscribing to services for %s: %s", self.host, err)
            raise UpnpError(f"Failed to subscribe to services: {err}") from err

    async def async_renew(
        self,
        service_name: str,
        sid: str,
        timeout: int = 1800,
    ) -> tuple[str, int] | None:
        """Renew UPnP service subscription (Samsung/DLNA pattern).

        Uses event_handler.async_resubscribe() like DmrDevice does.
        See: async_upnp_client/profiles/dlna.py _async_resubscribe_services()

        Args:
            service_name: Name of service ("AVTransport" or "RenderingControl")
            sid: Subscription SID to renew
            timeout: New subscription timeout in seconds

        Returns:
            Tuple of (new_sid, timeout_timedelta) if successful, None otherwise
        """
        if not self._notify_server:
            _LOGGER.warning("Notify server not available for renewal")
            return None

        event_handler = self._notify_server.event_handler

        try:
            _LOGGER.debug(
                "🔄 Renewing subscription to %s on %s: SID=%s, timeout=%d seconds",
                service_name,
                self.host,
                sid,
                timeout,
            )
            # DmrDevice pattern: event_handler.async_resubscribe() returns (new_sid, timeout_timedelta)
            # event_handler.async_resubscribe() expects timeout as timedelta, not int
            timeout_delta = timedelta(seconds=timeout)
            new_sid, timeout_timedelta = await event_handler.async_resubscribe(
                sid,
                timeout=timeout_delta,
            )
            granted_timeout = int(timeout_timedelta.total_seconds())
            _LOGGER.info(
                "✅ Successfully renewed subscription to %s on %s: SID=%s->%s, expires=%d seconds",
                service_name,
                self.host,
                sid,
                new_sid,
                granted_timeout,
            )
            return (new_sid, granted_timeout)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "❌ Failed to renew subscription to %s on %s (SID=%s): %s",
                service_name,
                self.host,
                sid,
                err,
            )
            return None

    async def async_unsubscribe(
        self,
        service_name: str,
        sid: str,
    ) -> None:
        """Unsubscribe from UPnP service (Samsung/DLNA pattern).

        Uses event_handler.async_unsubscribe() like DmrDevice does.
        See: async_upnp_client/profiles/dlna.py async_unsubscribe_services()

        Args:
            service_name: Name of service ("AVTransport" or "RenderingControl")
            sid: Subscription SID to unsubscribe
        """
        if not self._notify_server:
            _LOGGER.warning("Notify server not available for unsubscribe")
            return

        event_handler = self._notify_server.event_handler

        try:
            _LOGGER.debug("Unsubscribing from %s on %s: SID=%s", service_name, self.host, sid)
            # DmrDevice pattern: event_handler.async_unsubscribe()
            await event_handler.async_unsubscribe(sid)
            _LOGGER.info("✅ Unsubscribed from %s on %s: SID=%s", service_name, self.host, sid)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("⚠️  Error unsubscribing from %s on %s (SID=%s): %s", service_name, self.host, sid, err)

    async def async_call_action(
        self,
        service_name: str,
        action: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call UPnP service action.

        Args:
            service_name: Name of service ("AVTransport", "RenderingControl", or "ContentDirectory")
            action: Action name (e.g., "Play", "Pause", "SetVolume", "Browse")
            arguments: Action arguments

        Returns:
            Action response as dict
        """
        # Normalize service name for attribute lookup
        service_name_lower = service_name.lower().replace(" ", "_")
        service_attr = f"_{service_name_lower}_service"
        service = getattr(self, service_attr, None)
        if not service:
            raise UpnpError(f"Service {service_name} not available")

        action_obj = service.action(action)
        if not action_obj:
            raise UpnpError(f"Action {action} not found in {service_name}")

        result = await action_obj.async_call(**arguments or {})

        return cast(dict[str, Any], result)

    async def get_media_info(self) -> dict[str, Any]:
        """Fetch current media info via GetMediaInfo UPnP action.

        This is a "pull" method that fetches the current media state on demand.
        Useful for:
        - Initial state when starting up
        - Debugging/diagnostics
        - Fallback when UPnP events fail

        Returns:
            Dictionary with media info:
            - CurrentURI: URI of currently playing media
            - CurrentURIMetaData: DIDL-Lite XML with title/artist/album/artwork
            - TrackSource: Source of the track (e.g., "spotify", "tunein")
            - NrTracks: Number of tracks
            - MediaDuration: Duration of current media
            - PlayMedium: Current play medium
            - RecordMedium: Current record medium
            - WriteStatus: Write status

        Raises:
            UpnpError: If AVTransport service is not available or action fails
        """
        if not self._av_transport_service:
            raise UpnpError("AVTransport service not available")

        try:
            result = await self.async_call_action(
                "av_transport",
                "GetMediaInfo",
                {"InstanceID": 0},
            )
            _LOGGER.debug("GetMediaInfo result: %s", result)
            return result
        except Exception as err:
            _LOGGER.warning("GetMediaInfo failed for %s: %s", self.host, err)
            raise UpnpError(f"GetMediaInfo failed: {err}") from err

    async def get_transport_info(self) -> dict[str, Any]:
        """Fetch current transport state via GetTransportInfo UPnP action.

        Returns:
            Dictionary with transport info:
            - CurrentTransportState: PLAYING, PAUSED_PLAYBACK, STOPPED, etc.
            - CurrentTransportStatus: OK, ERROR_OCCURRED, etc.
            - CurrentSpeed: Playback speed (1 = normal)

        Raises:
            UpnpError: If AVTransport service is not available or action fails
        """
        if not self._av_transport_service:
            raise UpnpError("AVTransport service not available")

        try:
            result = await self.async_call_action(
                "av_transport",
                "GetTransportInfo",
                {"InstanceID": 0},
            )
            _LOGGER.debug("GetTransportInfo result: %s", result)
            return result
        except Exception as err:
            _LOGGER.warning("GetTransportInfo failed for %s: %s", self.host, err)
            raise UpnpError(f"GetTransportInfo failed: {err}") from err

    async def get_position_info(self) -> dict[str, Any]:
        """Fetch current position info via GetPositionInfo UPnP action.

        Returns:
            Dictionary with position info:
            - Track: Current track number
            - TrackDuration: Duration of current track (HH:MM:SS format)
            - TrackMetaData: DIDL-Lite XML with track metadata
            - TrackURI: URI of current track
            - RelTime: Relative time position (HH:MM:SS format)
            - AbsTime: Absolute time position
            - RelCount: Relative counter position
            - AbsCount: Absolute counter position

        Raises:
            UpnpError: If AVTransport service is not available or action fails
        """
        if not self._av_transport_service:
            raise UpnpError("AVTransport service not available")

        try:
            result = await self.async_call_action(
                "av_transport",
                "GetPositionInfo",
                {"InstanceID": 0},
            )
            _LOGGER.debug("GetPositionInfo result: %s", result)
            return result
        except Exception as err:
            _LOGGER.warning("GetPositionInfo failed for %s: %s", self.host, err)
            raise UpnpError(f"GetPositionInfo failed: {err}") from err

    async def get_info_ex(self) -> dict[str, Any]:
        """Fetch extended transport/metadata via LinkPlay GetInfoEx UPnP action.

        Arylic and some generic LinkPlay devices expose rich playback metadata
        (including ``upnp:albumArtURI``) through this vendor extension instead of
        the HTTP ``getMetaInfo`` endpoint.

        Returns:
            Parsed response with transport fields and normalized metadata keys
            (``title``, ``artist``, ``album``, ``image_url``) when available.

        Raises:
            UpnpError: If AVTransport is unavailable or the action fails.
        """
        if not self._av_transport_service:
            raise UpnpError("AVTransport service not available")

        from .metadata import parse_getinfoex_response

        service_type = "urn:schemas-upnp-org:service:AVTransport:1"

        try:
            if self._av_transport_service.has_action("GetInfoEx"):
                result = await self.async_call_action(
                    "av_transport",
                    "GetInfoEx",
                    {"InstanceID": 0},
                )
                parsed = dict(result)
                track_metadata = parsed.get("TrackMetaData")
                if isinstance(track_metadata, str) and track_metadata.strip():
                    from .metadata import parse_didl_metadata

                    parsed.update(parse_didl_metadata(track_metadata))
                _LOGGER.debug("GetInfoEx result for %s: has_artwork=%s", self.host, bool(parsed.get("image_url")))
                if parsed.get("image_url"):
                    return parsed
                _LOGGER.debug("GetInfoEx action for %s returned no artwork; trying raw SOAP", self.host)
        except Exception as err:
            _LOGGER.debug("GetInfoEx via async_upnp_client failed for %s: %s", self.host, err)

        return await self._get_info_ex_raw(service_type, parse_getinfoex_response)

    async def _get_info_ex_raw(
        self,
        service_type: str,
        parse_response: Callable[[str], dict[str, Any]],
    ) -> dict[str, Any]:
        """Call LinkPlay GetInfoEx via raw SOAP when SCPD does not advertise it."""
        control_url = getattr(self._av_transport_service, "control_url", None)
        if not control_url:
            raise UpnpError("AVTransport control URL not available")

        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            "<s:Body>"
            f'<u:GetInfoEx xmlns:u="{service_type}">'
            "<InstanceID>0</InstanceID>"
            "</u:GetInfoEx>"
            "</s:Body></s:Envelope>"
        )
        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": f'"{service_type}#GetInfoEx"',
        }

        session = self.session
        if session is None or session.closed:
            connector = TCPConnector(ssl=False)
            session = ClientSession(connector=connector)
            close_session = True
        else:
            close_session = False

        try:
            async with session.post(control_url, data=body, headers=headers, ssl=False) as response:
                text = await response.text()
                if response.status != 200:
                    raise UpnpError(f"GetInfoEx failed with HTTP {response.status}")
                parsed = parse_response(text)
                if not parsed:
                    raise UpnpError("GetInfoEx returned empty response")
                _LOGGER.debug(
                    "GetInfoEx raw SOAP result for %s: has_artwork=%s",
                    self.host,
                    bool(parsed.get("image_url")),
                )
                return parsed
        except UpnpError:
            raise
        except Exception as err:
            raise UpnpError(f"GetInfoEx failed: {err}") from err
        finally:
            if close_session:
                await session.close()

    async def get_volume(self, channel: str = "Master") -> int:
        """Fetch current volume via GetVolume UPnP action.

        Useful for initial state or when UPnP events are not working.

        Args:
            channel: Audio channel ("Master", "LF", "RF"). Default "Master".

        Returns:
            Volume level (0-100)

        Raises:
            UpnpError: If RenderingControl service is not available or action fails
        """
        if not self._rendering_control_service:
            raise UpnpError("RenderingControl service not available")

        try:
            result = await self.async_call_action(
                "rendering_control",
                "GetVolume",
                {"InstanceID": 0, "Channel": channel},
            )
            volume = result.get("CurrentVolume", 0)
            _LOGGER.debug("GetVolume result for %s: %s", self.host, volume)
            return int(volume)
        except Exception as err:
            _LOGGER.warning("GetVolume failed for %s: %s", self.host, err)
            raise UpnpError(f"GetVolume failed: {err}") from err

    async def get_mute(self, channel: str = "Master") -> bool:
        """Fetch current mute state via GetMute UPnP action.

        Useful for initial state or when UPnP events are not working.

        Args:
            channel: Audio channel ("Master", "LF", "RF"). Default "Master".

        Returns:
            True if muted, False otherwise

        Raises:
            UpnpError: If RenderingControl service is not available or action fails
        """
        if not self._rendering_control_service:
            raise UpnpError("RenderingControl service not available")

        try:
            result = await self.async_call_action(
                "rendering_control",
                "GetMute",
                {"InstanceID": 0, "Channel": channel},
            )
            muted = result.get("CurrentMute", False)
            _LOGGER.debug("GetMute result for %s: %s", self.host, muted)
            return bool(muted)
        except Exception as err:
            _LOGGER.warning("GetMute failed for %s: %s", self.host, err)
            raise UpnpError(f"GetMute failed: {err}") from err

    async def get_control_device_info(self) -> dict[str, Any]:
        """Fetch current device state via GetControlDeviceInfo UPnP action.

        This action is specific to LinkPlay/Audio Pro firmware and returns full
        device state including PlayMode (current input source), volume, and mute,
        even when the device is idle. Useful for Audio Pro devices where the HTTP
        API does not reliably report the current input mode when idle.

        Returns:
            Dictionary with raw response fields, e.g.:
            - PlayMode: current input mode (int string, maps via MODE_MAP)
            - CurrentVolume: current volume level
            - CurrentMute: current mute state

        Raises:
            UpnpError: If RenderingControl service is not available or action fails
        """
        if not self._rendering_control_service:
            raise UpnpError("RenderingControl service not available")

        try:
            result = await self.async_call_action(
                "rendering_control",
                "GetControlDeviceInfo",
                {"InstanceID": 0},
            )
            _LOGGER.debug("GetControlDeviceInfo result for %s: %s", self.host, result)
            return result
        except Exception as err:
            _LOGGER.debug("GetControlDeviceInfo failed for %s: %s", self.host, err)
            raise UpnpError(f"GetControlDeviceInfo failed: {err}") from err

    async def get_device_capabilities(self) -> dict[str, Any]:
        """Fetch device capabilities via GetDeviceCapabilities UPnP action.

        Returns what media types and protocols the device supports.

        Returns:
            Dictionary with:
            - PlayMedia: Supported play media types
            - RecMedia: Supported record media types
            - RecQualityModes: Supported recording quality modes

        Raises:
            UpnpError: If AVTransport service is not available or action fails
        """
        if not self._av_transport_service:
            raise UpnpError("AVTransport service not available")

        try:
            result = await self.async_call_action(
                "av_transport",
                "GetDeviceCapabilities",
                {"InstanceID": 0},
            )
            _LOGGER.debug("GetDeviceCapabilities result for %s: %s", self.host, result)
            return result
        except Exception as err:
            _LOGGER.warning("GetDeviceCapabilities failed for %s: %s", self.host, err)
            raise UpnpError(f"GetDeviceCapabilities failed: {err}") from err

    async def get_current_transport_actions(self) -> list[str]:
        """Fetch currently available transport actions via GetCurrentTransportActions.

        Returns what actions are currently valid (e.g., can't Pause if already paused).

        Returns:
            List of available actions like ["Play", "Stop", "Pause", "Seek", "Next", "Previous"]

        Raises:
            UpnpError: If AVTransport service is not available or action fails
        """
        if not self._av_transport_service:
            raise UpnpError("AVTransport service not available")

        try:
            result = await self.async_call_action(
                "av_transport",
                "GetCurrentTransportActions",
                {"InstanceID": 0},
            )
            actions_str = result.get("Actions", "")
            actions = [a.strip() for a in actions_str.split(",") if a.strip()]
            _LOGGER.debug("GetCurrentTransportActions result for %s: %s", self.host, actions)
            return actions
        except Exception as err:
            _LOGGER.warning("GetCurrentTransportActions failed for %s: %s", self.host, err)
            raise UpnpError(f"GetCurrentTransportActions failed: {err}") from err

    async def get_full_state_snapshot(self) -> dict[str, Any]:
        """Fetch complete device state via UPnP for diagnostics.

        This is a convenience method that fetches all available state in one call.
        Intended for diagnostics and debugging - NOT for regular state updates
        (use HTTP polling + UPnP events for that).

        Returns:
            Dictionary with all available UPnP state:
            - transport: GetTransportInfo result (play state)
            - media: GetMediaInfo result (current URI, metadata)
            - position: GetPositionInfo result (position, duration)
            - volume: Current volume level (0-100)
            - muted: Current mute state
            - available_actions: List of valid transport actions
            - errors: Any errors encountered during fetch

        Note:
            Individual fetch errors are caught and reported in 'errors' dict
            rather than raising exceptions.
        """
        result: dict[str, Any] = {"errors": {}}

        # Fetch transport info (play state)
        try:
            result["transport"] = await self.get_transport_info()
        except Exception as err:
            result["transport"] = None
            result["errors"]["transport"] = str(err)

        # Fetch media info (what's playing)
        try:
            result["media"] = await self.get_media_info()
        except Exception as err:
            result["media"] = None
            result["errors"]["media"] = str(err)

        # Fetch position info
        try:
            result["position"] = await self.get_position_info()
        except Exception as err:
            result["position"] = None
            result["errors"]["position"] = str(err)

        # Fetch volume
        try:
            result["volume"] = await self.get_volume()
        except Exception as err:
            result["volume"] = None
            result["errors"]["volume"] = str(err)

        # Fetch mute state
        try:
            result["muted"] = await self.get_mute()
        except Exception as err:
            result["muted"] = None
            result["errors"]["muted"] = str(err)

        # Fetch available actions
        try:
            result["available_actions"] = await self.get_current_transport_actions()
        except Exception as err:
            result["available_actions"] = None
            result["errors"]["available_actions"] = str(err)

        # Clean up errors dict if empty
        if not result["errors"]:
            del result["errors"]

        return result

    async def browse_queue(
        self,
        object_id: str = "Q:0",
        starting_index: int = 0,
        requested_count: int = 0,
    ) -> dict[str, Any]:
        """Browse queue contents via ContentDirectory Browse action.

        Follows SoCo pattern: Uses Browse action to retrieve queue items.
        ObjectID "Q:0" is the standard queue identifier (Sonos uses this).

        **Availability Note:**
        ContentDirectory service is only available on:
        - WiiM Amp (when USB drive is connected)
        - WiiM Ultra (when USB drive is connected)

        Other WiiM devices do not expose ContentDirectory service.

        Args:
            object_id: Queue object ID (default "Q:0" for standard queue)
            starting_index: Starting index for pagination (0 = first item)
            requested_count: Number of items to retrieve (0 = all available)

        Returns:
            Dictionary with:
            - Result: DIDL-Lite XML string containing queue items
            - NumberReturned: Number of items returned
            - TotalMatches: Total number of items in queue
            - UpdateID: Update ID for change detection

        Raises:
            UpnpError: If ContentDirectory service is not available or action fails
        """
        if not self._content_directory_service:
            raise UpnpError("ContentDirectory service not available")

        try:
            result = await self.async_call_action(
                "ContentDirectory",
                "Browse",
                {
                    "ObjectID": object_id,
                    "BrowseFlag": "BrowseDirectChildren",
                    "Filter": "*",  # Get all properties
                    "StartingIndex": starting_index,
                    "RequestedCount": requested_count,
                    "SortCriteria": "",  # Default sorting
                },
            )
            _LOGGER.debug("Browse queue result for %s: %d items", self.host, result.get("NumberReturned", 0))
            return result
        except Exception as err:
            _LOGGER.warning("Browse queue failed for %s: %s", self.host, err)
            raise UpnpError(f"Browse queue failed: {err}") from err
