"""UPnP event handler for WiiM devices.

Follows Samsung/DLNA pattern using async_upnp_client (DmrDevice pattern).
Framework-agnostic implementation for use in any Python application.

Reference implementation: dlna_dmr/media_player.py:388-391

# pragma: allow-long-file upnp-eventer-cohesive
# This file exceeds the 600 LOC hard limit (727 lines) but is kept as a single
# cohesive unit because:
# 1. Single responsibility: UPnP event subscription and parsing
# 2. Well-organized: Clear sections for subscription, parsing, and metadata extraction
# 3. Tight coupling: All methods are UPnP event handling specific
# 4. Maintainable: Clear structure, follows DLNA DMR pattern
# 5. Natural unit: Represents one concept (UPnP event management)
# Splitting would add complexity without clear benefit.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from typing import Any
from urllib.parse import urlparse

from async_upnp_client.client import UpnpService, UpnpStateVariable
from async_upnp_client.exceptions import UpnpResponseError

from .client import UpnpClient

_LOGGER = logging.getLogger(__name__)

# Maps UPnP AVTransport PlaybackStorageMedium values to pywiim source names.
# Only physical inputs are listed; network sources (SONGLIST-NETWORK, etc.) are
# left unmapped so HTTP polling continues to own them.
_PLAYBACK_STORAGE_MEDIUM_MAP: dict[str, str] = {
    "RCA": "rca",
    "BLUETOOTH": "bluetooth",
    "LINE-IN": "line_in",
    "LINEIN": "line_in",
    "OPTICAL": "optical",
    "COAXIAL": "coaxial",
    "HDMI": "hdmi",
}


def _is_valid_url(url: str | None) -> bool:
    """Validate that a string is a valid HTTP/HTTPS URL.

    Args:
        url: URL string to validate

    Returns:
        True if valid HTTP/HTTPS URL, False otherwise
    """
    if not url or not isinstance(url, str):
        return False

    url = url.strip()
    if not url:
        return False

    try:
        result = urlparse(url)
        # Must have scheme (http/https) and netloc (domain/IP)
        return result.scheme in ("http", "https") and bool(result.netloc)
    except Exception:
        return False


class UpnpEventer:
    """Manage UPnP event subscriptions and process LastChange notifications.

    Reference pattern: dlna_dmr/media_player.py:388-391
    Uses DmrDevice.async_subscribe_services(auto_resubscribe=True) - handles renewals automatically.

    Framework-agnostic: Uses callback function instead of dispatcher for state updates.
    """

    def __init__(
        self,
        upnp_client: UpnpClient,
        state_manager: Any,  # State manager with apply_diff() method and play_state property
        device_uuid: str,
        state_updated_callback: Callable[[dict[str, Any], str], None] | Callable[[], None] | None = None,
    ) -> None:
        """Initialize UPnP eventer.

        Args:
            upnp_client: UPnP client instance
            state_manager: State manager with apply_diff() method and play_state property
            device_uuid: Device UUID for identification
            state_updated_callback: Optional callback function called when state is updated
        """
        self.upnp_client = upnp_client
        self.state_manager = state_manager
        self.device_uuid = device_uuid
        self.state_updated_callback = state_updated_callback

        # Event statistics (for diagnostics)
        # Note: We don't do "health tracking" - UPnP has no heartbeat, can't reliably detect if working
        self._last_notify_ts: float | None = None
        self._event_count = 0

        # Track availability check (following DLNA DMR pattern)
        # When empty state_variables detected, set this to trigger availability check
        # This is used for resubscription failure detection, not general health checking
        self.check_available: bool = False

    async def start(
        self,
        callback_host: str | None = None,
        callback_port: int = 0,
    ) -> None:
        """Start event subscriptions (reference: dlna_dmr/media_player.py:388-391).

        Args:
            callback_host: Host IP for callback URL (auto-detect if None)
            callback_port: Port for callback (0 = ephemeral)
        """
        # Start notify server first (required before subscriptions)
        await self.upnp_client.start_notify_server(
            callback_host=callback_host,
            callback_port=callback_port,
        )

        # Reference pattern: dlna_dmr/media_player.py:388-391
        # ONE LINE: auto_resubscribe=True handles all renewals internally
        subscription_start_time = time.time()
        _LOGGER.info(
            "📨 Subscribing to UPnP services for %s (DmrDevice pattern with auto_resubscribe=True)",
            self.upnp_client.host,
        )

        try:
            # Log callback URL for diagnostics
            callback_url = getattr(self.upnp_client.notify_server, "callback_url", None)
            if callback_url:
                _LOGGER.info(
                    "   → Callback URL: %s (devices will send NOTIFY events to this URL)",
                    callback_url,
                )
                # Validate callback URL reachability
                server_host = getattr(self.upnp_client.notify_server, "host", "unknown")
                if server_host.startswith("172.") or server_host == "0.0.0.0":
                    _LOGGER.error(
                        "   ⚠️  CRITICAL: Callback URL uses unreachable IP %s - devices on your LAN cannot reach this!",
                        server_host,
                    )
                    _LOGGER.error(
                        "      UPnP events will not arrive. Configure callback_host parameter with your host's LAN IP.",
                    )
            else:
                _LOGGER.error(
                    "   ⚠️  CRITICAL: No callback URL available - UPnP events will NOT work!",
                )

            # Reference pattern: Set callback and subscribe - auto_resubscribe handles everything
            if self.upnp_client._dmr_device is None:
                raise RuntimeError("DmrDevice not initialized")
            self.upnp_client._dmr_device.on_event = self._on_event
            await self.upnp_client._dmr_device.async_subscribe_services(auto_resubscribe=True)

            subscription_duration = time.time() - subscription_start_time
            _LOGGER.info(
                "✅ UPnP subscriptions established for %s (completed in %.2fs, auto_resubscribe=True handles renewals)",
                self.upnp_client.host,
                subscription_duration,
            )

        except UpnpResponseError as err:
            # Device rejected subscription - this is OK, we'll poll instead (reference pattern)
            subscription_duration = time.time() - subscription_start_time
            _LOGGER.debug(
                "Device rejected subscription for %s (after %.2fs): %r - will use polling",
                self.upnp_client.host,
                subscription_duration,
                err,
            )
            raise
        except Exception as err:  # noqa: BLE001
            subscription_duration = time.time() - subscription_start_time
            _LOGGER.error(
                "❌ Failed to subscribe to UPnP services for %s (after %.2fs): %s",
                self.upnp_client.host,
                subscription_duration,
                err,
            )
            _LOGGER.warning("   → Application will fall back to HTTP polling")
            raise

    async def async_unsubscribe(self) -> None:
        """Unsubscribe from all services and stop notify server (reference pattern)."""
        if self.upnp_client._dmr_device:
            try:
                self.upnp_client._dmr_device.on_event = None
                await self.upnp_client._dmr_device.async_unsubscribe_services()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Error unsubscribing services: %s", err)

        # Stop notify server
        await self.upnp_client.unwind_notify_server()

        _LOGGER.info("UPnP event subscriptions stopped for %s", self.upnp_client.host)

    def _on_event(
        self,
        service: UpnpService,
        state_variables: Sequence[UpnpStateVariable],
    ) -> None:
        """Handle UPnP events from DmrDevice (reference: dlna_dmr/media_player.py:510).

        Following DLNA DMR pattern: empty state_variables indicates resubscription failure.
        We mark subscriptions as failed and signal fallback to HTTP polling.
        """
        # Log event reception for debugging
        service_id = getattr(service, "service_id", "Unknown")
        _LOGGER.debug(
            "📡 UPnP event received from %s: service=%s, variables=%d",
            self.upnp_client.host,
            service_id,
            len(state_variables),
        )

        # Handle empty state_variables (resubscription failure indication)
        # Reference: dlna_dmr/media_player.py:514-516
        if not state_variables:
            # Gather diagnostic information to understand WHY resubscription failed
            service_id = getattr(service, "service_id", "Unknown")
            service_type = getattr(service, "service_type", "Unknown")
            callback_url = getattr(self.upnp_client.notify_server, "callback_url", "Unknown")
            time_since_last_event = time.time() - self._last_notify_ts if self._last_notify_ts else None
            event_count = self._event_count

            # Try to get subscription information from DmrDevice if available
            subscription_info: dict[str, Any] = {}
            try:
                if hasattr(self.upnp_client, "_dmr_device") and self.upnp_client._dmr_device:
                    dmr = self.upnp_client._dmr_device
                    # Check if we can access subscription state
                    if hasattr(dmr, "_subscriptions"):
                        subscription_info["has_subscriptions_dict"] = True
                        subscription_info["subscription_count"] = (
                            len(dmr._subscriptions) if isinstance(dmr._subscriptions, dict) else 0
                        )
                    # Check event handler state
                    if hasattr(dmr, "event_handler"):
                        eh = dmr.event_handler
                        if hasattr(eh, "_subscriptions"):
                            subscription_info["event_handler_subscriptions"] = (
                                len(eh._subscriptions) if isinstance(eh._subscriptions, dict) else 0
                            )
            except Exception as diag_err:
                subscription_info["diagnostic_error"] = str(diag_err)

            # Determine if this is a normal/expected empty event vs. a potential issue
            # ConnectionManager often sends empty initial notifications - this is normal because:
            #   - It tracks media format connections (SourceProtocolInfo, SinkProtocolInfo, etc.)
            #   - On startup, there may be no active connections to report
            #   - The service still sends the initial subscription confirmation with empty state
            # AVTransport/RenderingControl sending empty events after working = potential problem
            is_connection_manager = "ConnectionManager" in service_id
            is_early_lifecycle = event_count < 5 and (time_since_last_event is None or time_since_last_event < 5.0)
            is_expected_empty = is_connection_manager and is_early_lifecycle

            if is_expected_empty:
                # Normal behavior - log at DEBUG level
                _LOGGER.debug(
                    "ConnectionManager sent empty initial state for %s - this is normal. "
                    "ConnectionManager tracks media format connections (source/sink protocols) "
                    "which may be empty on startup when nothing is actively streaming.",
                    self.upnp_client.host,
                )
                # Don't set check_available for expected empty events
                return

            # Following DLNA DMR pattern: empty state_variables indicates resubscription issue
            # Set check_available flag to trigger availability check in next poll
            # Trust auto_resubscribe=True to recover - don't mark as failed
            if not self.check_available:
                # First time we detect this - log detailed warning with diagnostics
                _LOGGER.warning(
                    "⚠️  UPnP resubscription issue for %s (empty state_variables) - "
                    "will check device availability, trusting auto_resubscribe to recover",
                    self.upnp_client.host,
                )
                _LOGGER.warning("   📊 Diagnostic Information:")
                _LOGGER.warning("      Service: %s (%s)", service_id, service_type)
                _LOGGER.warning("      Callback URL: %s", callback_url)
                _LOGGER.warning("      Events received before issue: %d", event_count)
                if time_since_last_event:
                    _LOGGER.warning("      Time since last event: %.1f seconds", time_since_last_event)
                else:
                    _LOGGER.warning("      Time since last event: No events received yet")
                if subscription_info:
                    _LOGGER.warning("      Subscription state: %s", subscription_info)
                _LOGGER.warning("   💡 This warning typically indicates:")
                _LOGGER.warning("      - Device resubscription failed (subscription may have expired)")
                _LOGGER.warning("      - Multiple clients competing for limited device subscriptions")
                _LOGGER.warning("      - Network issue preventing callback delivery")
                _LOGGER.warning("   ℹ️  The library will continue polling and auto_resubscribe should recover.")

            # Set check_available flag (DLNA DMR pattern)
            self.check_available = True
            return

        # Extract service type from service.service_id
        service_id = service.service_id
        if "AVTransport" in service_id:
            service_type = "AVTransport"
        elif "RenderingControl" in service_id or "Rendering" in service_id:
            service_type = "RenderingControl"
        else:
            _LOGGER.debug("Unknown service type: %s", service_id)
            service_type = "Unknown"

        # Convert state_variables to dict (like original handle_notify received)
        variables_dict = {var.name: var.value for var in state_variables}

        # Track event statistics (count once per event, after validating it's not empty)
        self._event_count += 1
        self._last_notify_ts = time.time()

        # Clear check_available flag when receiving events (device is available)
        if self.check_available:
            _LOGGER.debug(
                "UPnP events resumed for %s - clearing availability check flag",
                self.upnp_client.host,
            )
            self.check_available = False

        _LOGGER.info(
            "📡 Received UPnP NOTIFY #%d from %s: service=%s, variables=%s",
            self._event_count,
            self.upnp_client.host,
            service_type,
            list(variables_dict.keys()),
        )
        # Log all variable values for debugging (especially to see if audio output mode changes are included)
        # Always log LastChange XML to see what variables are available
        if "LastChange" in variables_dict:
            last_change = variables_dict.get("LastChange", "")
            if last_change and isinstance(last_change, str):
                _LOGGER.debug(
                    "UPnP event LastChange XML for %s: %s",
                    self.upnp_client.host,
                    last_change[:500],  # First 500 chars to avoid huge logs
                )
        # Log summary of what changed (for debugging why events are sparse)
        if service_type == "AVTransport":
            has_position = any("Position" in var.name for var in state_variables)
            has_transport_state = any("TransportState" in var.name for var in state_variables)
            has_metadata = any("MetaData" in var.name for var in state_variables)
            _LOGGER.debug(
                "AVTransport event details: position=%s, transport_state=%s, metadata=%s",
                has_position,
                has_transport_state,
                has_metadata,
            )
        elif service_type == "RenderingControl":
            has_volume = any("Volume" in var.name for var in state_variables)
            has_mute = any("Mute" in var.name for var in state_variables)
            _LOGGER.debug(
                "RenderingControl event details: volume=%s, mute=%s",
                has_volume,
                has_mute,
            )

        # Parse LastChange XML (same as original)
        changes: dict[str, Any] = {}
        if "LastChange" in variables_dict:
            last_change = variables_dict["LastChange"]
            if last_change and isinstance(last_change, str):
                changes.update(self._parse_last_change(service_type, last_change))

        # Also handle individual variables (not just LastChange)
        # This is important for metadata which may come as CurrentTrackMetaData
        # NOTE: Spotify source requires UPnP events for metadata - HTTP API does not provide
        # metadata when Spotify is the active source. Without UPnP events, Spotify metadata will be unavailable.
        if service_type == "AVTransport":
            # Check current playback state before processing metadata
            # Only clear metadata if device is truly stopped/idle, not during transitions
            current_play_state = getattr(self.state_manager, "play_state", None)
            is_playing_or_transitioning = current_play_state and any(
                state in str(current_play_state).lower()
                for state in ["play", "playing", "transitioning", "load", "loading", "buffering"]
            )

            # Extract metadata from CurrentTrackMetaData if present
            if "CurrentTrackMetaData" in variables_dict:
                metadata = variables_dict["CurrentTrackMetaData"]
                if metadata and isinstance(metadata, str):
                    metadata_changes = self._parse_didl_metadata(
                        metadata,
                        allow_clear=not is_playing_or_transitioning,
                    )
                    changes.update(metadata_changes)
            # Also check AVTransportURIMetaData as fallback
            elif "AVTransportURIMetaData" in variables_dict:
                metadata = variables_dict["AVTransportURIMetaData"]
                if metadata and isinstance(metadata, str):
                    metadata_changes = self._parse_didl_metadata(
                        metadata,
                        allow_clear=not is_playing_or_transitioning,
                    )
                    changes.update(metadata_changes)

            # Handle TrackSource to update source field
            if "TrackSource" in variables_dict:
                changes["source"] = variables_dict["TrackSource"]

            # Fallback: use PlaybackStorageMedium when TrackSource is absent or empty.
            # Physical inputs (RCA, BLUETOOTH, etc.) set PlaybackStorageMedium but leave
            # TrackSource blank, so this is the only UPnP signal available for them.
            if not changes.get("source") and "PlaybackStorageMedium" in variables_dict:
                medium = str(variables_dict["PlaybackStorageMedium"]).upper()
                mapped = _PLAYBACK_STORAGE_MEDIUM_MAP.get(medium)
                if mapped:
                    changes["source"] = mapped
                    _LOGGER.debug("Source from PlaybackStorageMedium: %s -> %s", medium, mapped)

        # Apply diff to state (same as original)
        if changes:
            self.state_manager.apply_diff(changes)

        # Always call callback when events are received (not just when state changes)
        # This allows monitor to track that events are being received
        if self.state_updated_callback:
            try:
                # Pass event data to callback if it accepts parameters, otherwise call without args
                import inspect

                sig = inspect.signature(self.state_updated_callback)
                if len(sig.parameters) > 0:
                    self.state_updated_callback(variables_dict, service_type)  # type: ignore[call-arg]
                else:
                    self.state_updated_callback()  # type: ignore[call-arg]
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Error calling state_updated_callback: %s", err)

    def _parse_last_change(
        self,
        service_type: str,
        last_change_xml: str,
    ) -> dict[str, Any]:
        """Parse LastChange XML into state changes."""
        changes = {}

        try:
            from xml.etree import ElementTree as ET

            root = ET.fromstring(last_change_xml)

            # Parse Event XML structure
            # Handle namespace: XML may have xmlns="urn:schemas-upnp-org:metadata-1-0/AVT/"
            # Try to find InstanceID elements, handling both namespaced and non-namespaced XML
            instances = []
            if root.tag.endswith("Event") or "Event" in root.tag:
                # Root is the Event element - find InstanceID children
                # Try with namespace wildcard first
                instances = root.findall(".//{*}InstanceID")
                if not instances:
                    # Try direct children
                    instances = [child for child in root if child.tag.endswith("InstanceID")]
            else:
                # Event is nested - find Event first, then InstanceID
                events = root.findall(".//{*}Event")
                if not events:
                    events = root.findall(".//Event")
                for event in events:
                    instances.extend(event.findall(".//{*}InstanceID"))
                    if not instances:
                        instances.extend([child for child in event if child.tag.endswith("InstanceID")])

            for instance in instances:
                _ = instance.get("val", "0")  # Instance ID not currently used

                # Parse AVTransport service variables
                if service_type == "AVTransport":
                    playback_storage_medium: str | None = None
                    for var in list(instance):
                        # Strip namespace from tag name (e.g., {urn:...}TransportState -> TransportState)
                        var_name = var.tag.split("}")[-1] if "}" in var.tag else var.tag
                        var_value = var.get("val", "")

                        if var_name == "TransportState":
                            changes["play_state"] = var_value.lower().replace("_", " ")
                        elif var_name == "AbsoluteTimePosition":
                            # Position provided in UPnP events when track starts (in LastChange event)
                            # Not sent continuously during playback - only on track changes
                            changes["position"] = self._parse_time_position(var_value)  # type: ignore[assignment]
                        elif var_name == "RelativeTimePosition":
                            # Position provided in UPnP events when track starts (in LastChange event)
                            # Not sent continuously during playback - only on track changes
                            changes["position"] = self._parse_time_position(var_value)  # type: ignore[assignment]
                        elif var_name == "CurrentTrackDuration":
                            # Duration provided in UPnP events when track starts (in LastChange event)
                            # Not sent continuously during playback - only on track changes
                            changes["duration"] = self._parse_time_position(var_value)  # type: ignore[assignment]
                        elif var_name == "CurrentTrackMetaData":
                            # Parse DIDL-Lite metadata from LastChange XML
                            # Check if device is playing/transitioning before clearing metadata
                            current_play_state = changes.get("play_state") or getattr(
                                self.state_manager, "play_state", None
                            )
                            is_playing_or_transitioning = current_play_state and any(
                                state in str(current_play_state).lower()
                                for state in ["play", "playing", "transitioning", "load", "loading", "buffering"]
                            )
                            metadata_changes = self._parse_didl_metadata(
                                var_value, allow_clear=not is_playing_or_transitioning
                            )
                            changes.update(metadata_changes)
                        elif var_name == "AVTransportURIMetaData":
                            # Parse DIDL-Lite metadata from LastChange XML
                            # Check if device is playing/transitioning before clearing metadata
                            current_play_state = changes.get("play_state") or getattr(
                                self.state_manager, "play_state", None
                            )
                            is_playing_or_transitioning = current_play_state and any(
                                state in str(current_play_state).lower()
                                for state in ["play", "playing", "transitioning", "load", "loading", "buffering"]
                            )
                            metadata_changes = self._parse_didl_metadata(
                                var_value, allow_clear=not is_playing_or_transitioning
                            )
                            changes.update(metadata_changes)
                        elif var_name == "TrackSource":
                            changes["source"] = var_value
                        elif var_name == "PlaybackStorageMedium":
                            playback_storage_medium = var_value
                        elif var_name in ("AVTransportURI", "CurrentURI"):
                            # Extract stream URL for potential ICY metadata extraction
                            # Store in changes but don't expose as a property (internal use)
                            changes["_stream_uri"] = var_value
                            _LOGGER.debug("Extracted stream URI from UPnP: %s", var_value[:100] if var_value else None)

                    # Fallback: use PlaybackStorageMedium when TrackSource is absent or empty.
                    if not changes.get("source") and playback_storage_medium:
                        mapped = _PLAYBACK_STORAGE_MEDIUM_MAP.get(playback_storage_medium.upper())
                        if mapped:
                            changes["source"] = mapped
                            _LOGGER.debug(
                                "Source from PlaybackStorageMedium (LastChange): %s -> %s",
                                playback_storage_medium,
                                mapped,
                            )

                # Parse RenderingControl service variables
                elif service_type == "RenderingControl":
                    for var in list(instance):
                        # Strip namespace from tag name (e.g., {urn:...}Volume -> Volume)
                        var_name = var.tag.split("}")[-1] if "}" in var.tag else var.tag
                        var_value = var.get("val", "")
                        channel = var.get("channel", "")

                        if var_name == "Volume":
                            if channel == "Master" or not channel:
                                try:
                                    vol_int = int(var_value)
                                    # Keep volume scale consistent with HTTP parser (0-100).
                                    changes["volume"] = vol_int  # type: ignore[assignment]
                                except (ValueError, TypeError):
                                    pass
                        elif var_name == "Mute":
                            if channel == "Master" or not channel:
                                changes["muted"] = var_value.lower() == "1"  # type: ignore[assignment]
                        # Log any other RenderingControl variables we're not parsing
                        # (might include audio output mode changes)
                        else:
                            _LOGGER.debug(
                                "Unparsed RenderingControl variable: %s = %s",
                                var_name,
                                var_value,
                            )

                # Log any other variables we encounter (for discovering audio output mode changes)
                else:
                    _LOGGER.debug(
                        "Unparsed variable in %s service: %s = %s",
                        service_type,
                        var_name,
                        var_value,
                    )

        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Error parsing LastChange XML: %s", err)

        if changes:
            _LOGGER.debug("Parsed LastChange for %s: %s", service_type, changes)

        return changes

    def _parse_time_position(self, time_str: str) -> int | None:
        """Parse time position from UPnP format to seconds."""
        if not time_str or time_str == "NOT_IMPLEMENTED":
            return None

        try:
            return int(time_str)
        except ValueError:
            pass

        try:
            parts = time_str.split(":")
            if len(parts) == 3:
                hours, minutes, seconds = map(int, parts)
                return abs(hours * 3600 + minutes * 60 + seconds)
        except (ValueError, AttributeError):
            pass

        return None

    def _parse_didl_metadata(self, didl_xml: str, allow_clear: bool = True) -> dict[str, Any]:
        """Parse DIDL-Lite XML to extract track metadata.

        Extracts title, artist, album, and image_url from DIDL-Lite XML.
        Handles both standard UPnP namespaces and LinkPlay-specific namespaces.

        Args:
            didl_xml: DIDL-Lite XML string (may be HTML-encoded)
            allow_clear: If False, don't clear metadata fields when empty (for transitions)

        Returns:
            Dict with title, artist, album, image_url if found
        """
        changes: dict[str, Any] = {}

        if not didl_xml or didl_xml.strip() == "":
            return changes

        try:
            from html import unescape
            from xml.etree import ElementTree as ET

            # Unescape HTML entities (e.g., &lt; becomes <)
            didl_xml = unescape(didl_xml)

            # Parse XML
            root = ET.fromstring(didl_xml)

            # Define namespaces (both standard and LinkPlay-specific)
            namespaces = {
                "dc": "http://purl.org/dc/elements/1.1/",
                "upnp": "urn:schemas-upnp-org:metadata-1-0/upnp/",
                "song": "www.linkplay.com/song/",
                "": "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/",
            }

            # Find item element (may be in root or nested)
            item = root.find(".//item", namespaces)
            if item is None:
                # Try without namespace
                item = root.find(".//item")

            if item is None:
                _LOGGER.debug(
                    "No item element found in DIDL-Lite XML - %s metadata",
                    "clearing" if allow_clear else "preserving (device playing/transitioning)",
                )
                # Only clear metadata if explicitly allowed (device is stopped/idle)
                if allow_clear:
                    changes["title"] = None
                    changes["artist"] = None
                    changes["album"] = None
                    changes["image_url"] = None
                return changes

            # Extract title (dc:title)
            title_elem = item.find("dc:title", namespaces)
            if title_elem is None:
                title_elem = item.find(".//{http://purl.org/dc/elements/1.1/}title")
            if title_elem is not None and title_elem.text and title_elem.text.strip():
                changes["title"] = title_elem.text.strip()
            elif title_elem is not None and allow_clear:
                # Element exists but is empty - clear it only if allowed
                changes["title"] = None

            # Extract artist (upnp:artist)
            artist_elem = item.find("upnp:artist", namespaces)
            if artist_elem is None:
                artist_elem = item.find(".//{urn:schemas-upnp-org:metadata-1-0/upnp/}artist")
            if artist_elem is not None and artist_elem.text and artist_elem.text.strip():
                changes["artist"] = artist_elem.text.strip()
            elif artist_elem is not None and allow_clear:
                # Element exists but is empty - clear it only if allowed
                changes["artist"] = None

            # Extract album (upnp:album)
            album_elem = item.find("upnp:album", namespaces)
            if album_elem is None:
                album_elem = item.find(".//{urn:schemas-upnp-org:metadata-1-0/upnp/}album")
            if album_elem is not None and album_elem.text and album_elem.text.strip():
                changes["album"] = album_elem.text.strip()
            elif album_elem is not None and allow_clear:
                # Element exists but is empty - clear it only if allowed
                changes["album"] = None

            # Extract album art URI (upnp:albumArtURI) with URL validation
            art_elem = item.find("upnp:albumArtURI", namespaces)
            if art_elem is None:
                art_elem = item.find(".//{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI")
            if art_elem is not None and art_elem.text:
                image_url = art_elem.text.strip()
                # Validate URL: must be valid http/https and not placeholder values
                if image_url and image_url != "un_known" and _is_valid_url(image_url):
                    changes["image_url"] = image_url
                elif allow_clear:
                    # Invalid URL or placeholder - clear it only if allowed
                    if image_url and image_url != "un_known":
                        _LOGGER.debug("Invalid image URL in DIDL-Lite (not a valid URL): %s", image_url[:100])
                    changes["image_url"] = None
            elif art_elem is not None and allow_clear:
                # Element exists but is empty - clear it only if allowed
                changes["image_url"] = None

            if any(v is not None for v in changes.values()):
                _LOGGER.debug(
                    "Extracted metadata from DIDL-Lite: title=%s, artist=%s, album=%s, image_url=%s",
                    changes.get("title"),
                    changes.get("artist"),
                    changes.get("album"),
                    changes.get("image_url"),
                )
            else:
                _LOGGER.debug("DIDL-Lite XML contains empty metadata - clearing all fields")

        except ET.ParseError as err:
            _LOGGER.debug("Error parsing DIDL-Lite XML: %s (XML: %s)", err, didl_xml[:200])
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Error extracting metadata from DIDL-Lite: %s", err)

        return changes

    def get_subscription_stats(self) -> dict[str, Any]:
        """Get subscription statistics for diagnostics (following DLNA DMR pattern - no health checking).

        Note: We don't report "upnp_working" because UPnP has no heartbeat/keepalive.
        Events only happen on state changes, so we can't reliably detect if UPnP is working.
        """
        now = time.time()
        return {
            "total_events": self._event_count,
            "last_notify_ts": self._last_notify_ts,
            "time_since_last": now - self._last_notify_ts if self._last_notify_ts is not None else None,
            "check_available": self.check_available,
            # Note: We don't report "upnp_working" - it's unreliable (no heartbeat in UPnP)
        }

    @property
    def statistics(self) -> dict[str, Any]:
        """Get UPnP event statistics for diagnostics.

        Returns:
            Dictionary with UPnP statistics including:
            - event_count: Total number of events received
            - last_event_time: Timestamp of last event (Unix time)
            - time_since_last_event: Seconds since last event (None if no events)
            - check_available: Whether availability check is needed
            - device_uuid: Device UUID
            - device_host: Device hostname/IP
        """
        now = time.time()
        return {
            "event_count": self._event_count,
            "last_event_time": self._last_notify_ts,
            "time_since_last_event": now - self._last_notify_ts if self._last_notify_ts is not None else None,
            "check_available": self.check_available,
            "device_uuid": self.device_uuid,
            "device_host": self.upnp_client.host,
        }
