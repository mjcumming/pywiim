"""Command-line tool for real-time WiiM player monitoring."""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from datetime import datetime
from typing import Any

from .. import __version__
from ..client import WiiMClient
from ..exceptions import WiiMConnectionError, WiiMError, WiiMRequestError
from ..models import DeviceInfo
from ..player import Player
from ..polling import PollingStrategy
from ..upnp.client import UpnpClient
from ..upnp.eventer import UpnpEventer
from ..upnp.health import UpnpHealthTracker

_LOGGER = logging.getLogger(__name__)


class PlayerMonitor:
    """Real-time player monitor with adaptive polling."""

    def __init__(self, player: Player) -> None:
        """Initialize monitor with a Player instance."""
        self.player = player
        self.running = False
        self.last_state: dict[str, Any] = {}
        self.last_device_info_check = 0.0
        self.last_multiroom_check = 0.0
        self.last_multiroom: dict[str, Any] | None = None
        self.previous_role: str | None = None  # Only for change detection, not state storage
        self.strategy: PollingStrategy | None = None
        self.upnp_client: UpnpClient | None = None
        self.upnp_eventer: UpnpEventer | None = None
        self.upnp_enabled = False
        self.upnp_event_count = 0
        self.last_upnp_event_time: float | None = None
        self._callback_host_override: str | None = None
        self.upnp_health_tracker: UpnpHealthTracker | None = None
        self.upnp_verbose = False  # Flag to enable verbose UPnP event logging

        # Statistics tracking
        self.start_time: float | None = None
        self.http_poll_count = 0
        self.state_change_count = 0
        self.error_count = 0
        self.poll_intervals: list[float] = []

        # TUI mode tracking
        self.use_tui = True  # Enable TUI by default
        self.tui_initialized = False
        self.recent_events: list[tuple[str, str]] = []  # (timestamp, message) - last 5 events
        self.max_events = 5

        # Cached data for TUI display (Player doesn't cache these, so we cache for display)
        self.last_eq_data: dict[str, Any] | None = None
        self.last_eq_check = 0.0
        self.last_group_info_check = 0.0  # Only track when to fetch, not the data itself
        self.last_group_info: Any | None = None  # Cached DeviceGroupInfo for display
        self.last_preset_count: int | None = None
        self.last_preset_check = 0.0
        self.last_audio_output_check = 0.0  # Track when to fetch audio output status
        self.last_trigger_out_check = 0.0  # Track when to fetch 12V trigger status
        self.last_subwoofer_check = 0.0  # Monitor-local subwoofer poll (faster than library tier)
        self.last_led_indicator_check = 0.0  # Monitor-local status LED poll
        # Faster than PollingStrategy.CONFIGURATION_INTERVAL (60s) for live testing in this CLI only.
        self.hardware_poll_interval = 10.0

    def _should_fetch_hardware_status(self, last_fetch_time: float, supported: bool, now: float) -> bool:
        """Whether to poll trigger/subwoofer/LED (monitor uses shorter interval than player.refresh)."""
        if not supported:
            return False
        if last_fetch_time is None or last_fetch_time == 0:
            return True
        return (now - last_fetch_time) >= self.hardware_poll_interval

    def _format_source_name(self, source: str) -> str:
        """Format source name for display, handling acronyms correctly.

        Args:
            source: Source name (e.g., "dlna", "line_in", "bluetooth")

        Returns:
            Formatted source name (e.g., "DLNA", "Line In", "Bluetooth")
        """
        # Known acronyms that should be uppercase
        acronyms = {"dlna", "usb", "hdmi", "rssi", "wifi"}

        # Replace underscores with spaces
        formatted = source.replace("_", " ")

        # Split into words
        words = formatted.split()

        # Format each word
        formatted_words = []
        for word in words:
            word_lower = word.lower()
            if word_lower in acronyms:
                # Acronyms should be all uppercase
                formatted_words.append(word_lower.upper())
            else:
                # Regular words: capitalize first letter
                formatted_words.append(word.capitalize())

        return " ".join(formatted_words)

    def _format_trigger_out_display(self) -> str | None:
        """Format 12V trigger line for monitor output, or None if unsupported."""
        if not self.player.supports_trigger_out:
            return None
        trigger_on = self.player.trigger_out_on
        if trigger_on is True:
            state_str = "ON"
        elif trigger_on is False:
            state_str = "OFF"
        else:
            state_str = "unknown"
        if self.last_trigger_out_check:
            age = int(time.time() - self.last_trigger_out_check)
            return f"12V Trigger: {state_str} (read {age}s ago)"
        return f"12V Trigger: {state_str}"

    def _format_led_indicator_display(self) -> str | None:
        """Format status LED line for monitor output, or None if unsupported."""
        if not self.player.supports_led_indicator:
            return None
        led_on = self.player.led_indicator_on
        if led_on is True:
            state_str = "ON"
        elif led_on is False:
            state_str = "OFF"
        else:
            state_str = "unknown"
        if self.last_led_indicator_check:
            age = int(time.time() - self.last_led_indicator_check)
            return f"Status LED: {state_str} (read {age}s ago)"
        return f"Status LED: {state_str}"

    def _detect_callback_host(self) -> str | None:
        """Detect the local network IP address for UPnP callback URL.

        Returns:
            IP address string, or None if detection fails
        """
        import socket

        # Use socket trick to get local IP address
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            detected_ip = s.getsockname()[0]
            s.close()

            # Return the detected IP (caller should validate if needed)
            return str(detected_ip)
        except Exception:
            pass

        return None

    def on_state_changed(self, source: str = "polling") -> None:
        """Callback when player state changes.

        Args:
            source: Source of the state change ("polling" or "upnp")
        """
        if not self.player.available:
            return

        # Note: UPnP event count is tracked in upnp_callback, not here
        # This method is called for both polling and UPnP state changes

        # Detect changes
        current_state = {
            "play_state": self.player.play_state,
            "volume": self.player.volume_level,
            "mute": self.player.is_muted,
            "source": self.player.source,
            "title": self.player.media_title,
            "artist": self.player.media_artist,
            "position": self.player.media_position,
            "duration": self.player.media_duration,
            "artwork": self.player.media_image_url,
            "shuffle": self.player.shuffle_state,
            "repeat": self.player.repeat_mode,
        }
        if self.player.supports_trigger_out:
            current_state["trigger_out"] = self.player.trigger_out_on
        if self.player.supports_subwoofer:
            current_state["subwoofer"] = self.player.subwoofer_enabled
        if self.player.supports_led_indicator:
            current_state["led_indicator"] = self.player.led_indicator_on

        # Track state changes
        if current_state != self.last_state:
            self.state_change_count += 1

        # Print changes (only show meaningful changes, not None -> None)
        changes = []
        for key, value in current_state.items():
            old_value = self.last_state.get(key)
            # Only report change if both values are meaningful or there's a real change
            if old_value != value and (value is not None or old_value is not None):
                old_str = str(old_value) if old_value is not None else "None"
                new_str = str(value) if value is not None else "None"
                changes.append(f"{key}: {old_str} → {new_str}")

        if changes:
            timestamp = datetime.now().strftime("%H:%M:%S")
            source_indicator = "📡 UPnP" if source == "upnp" else "🔄 HTTP"
            message = f"{source_indicator} State changed: {', '.join(changes[:3])}"  # Limit to first 3 changes
            self._add_event(timestamp, message)

            # In non-TUI mode, print to console
            if not self.use_tui:
                print("\r" + " " * 100 + "\r", end="", flush=True)
                print(f"[{timestamp}] {source_indicator} State changed:")
                for change in changes:
                    print(f"  • {change}")

        self.last_state = current_state

    async def setup(self) -> None:
        """Initialize monitor and detect capabilities."""
        print("🔧 Initializing monitor...")
        self.start_time = time.time()

        # Detect capabilities
        await self.player.client._detect_capabilities()
        self.strategy = PollingStrategy(self.player.client.capabilities)

        # Initialize UPnP event support
        try:
            device_info = await self.player.client.get_device_info_model()
            if device_info.uuid:
                # UPnP description URL is typically on port 49152
                description_url = f"http://{self.player.client.host}:49152/description.xml"

                # Create UPnP client using factory method
                # Pass client's session for connection pooling
                await self.player.client._ensure_session()
                client_session = getattr(self.player.client, "_session", None)
                self.upnp_client = await UpnpClient.create(
                    self.player.client.host,
                    description_url,
                    session=client_session,
                )

                # Initialize UPnP health tracker
                self.upnp_health_tracker = UpnpHealthTracker()

                # Create wrapper callback to mark UPnP events
                def upnp_callback(event_data: dict[str, Any] | None = None, service_type: str | None = None):
                    # Track that UPnP event was received (even if no state change)
                    self.upnp_event_count += 1
                    self.last_upnp_event_time = time.time()

                    # Log UPnP event reception
                    _LOGGER.info(
                        "📡 UPnP event #%d received from %s",
                        self.upnp_event_count,
                        self.player.host,
                    )

                    # Log full event data if verbose mode is enabled
                    if self.upnp_verbose and event_data is not None:
                        import json

                        try:
                            # Format event data as JSON for readability
                            event_json = json.dumps(event_data, indent=2, default=str)
                            _LOGGER.info(
                                "📡 UPnP event #%d full data (service=%s):\n%s",
                                self.upnp_event_count,
                                service_type or "Unknown",
                                event_json,
                            )
                        except Exception:
                            # Fallback to string representation if JSON serialization fails
                            _LOGGER.info(
                                "📡 UPnP event #%d full data (service=%s): %s",
                                self.upnp_event_count,
                                service_type or "Unknown",
                                str(event_data),
                            )

                    # Update health tracker with UPnP event data
                    if self.upnp_health_tracker:
                        upnp_state = {
                            "play_state": self.player.play_state,
                            "volume": self.player.volume_level,
                            "muted": self.player.is_muted,
                            "title": self.player.media_title,
                            "artist": self.player.media_artist,
                            "album": self.player.media_album,
                        }
                        self.upnp_health_tracker.on_upnp_event(upnp_state)

                    # Also call state changed callback
                    self.on_state_changed(source="upnp")

                # Create eventer with Player as state manager
                self.upnp_eventer = UpnpEventer(
                    self.upnp_client,
                    self.player,  # Player has apply_diff() method
                    device_info.uuid,
                    state_updated_callback=upnp_callback,
                )

                # Start UPnP subscriptions
                # Try to get LAN IP for callback
                callback_host: str | None = None
                if hasattr(self, "_callback_host_override") and self._callback_host_override:
                    callback_host = self._callback_host_override
                    print(f"   📡 Using specified callback host: {callback_host}")
                else:
                    detected_host = self._detect_callback_host()
                    callback_host = detected_host
                    if callback_host:
                        print(f"   📡 Detected callback host: {callback_host}")
                    else:
                        print("   ⚠️  Could not auto-detect callback host - UPnP events may not work")
                        print("      Use --callback-host <ip> to specify manually")

                await self.upnp_eventer.start(callback_host=callback_host)
                self.upnp_enabled = True

                # Log callback URL if available
                if self.upnp_client.notify_server:
                    callback_url = getattr(self.upnp_client.notify_server, "callback_url", None)
                    if callback_url:
                        print(f"   ✓ UPnP events enabled (callback: {callback_url})")
                    else:
                        print("   ✓ UPnP events enabled (callback URL not available)")
                else:
                    print("   ✓ UPnP events enabled")
        except Exception as e:
            # UPnP failed, continue with HTTP polling only
            print(f"   ⚠ UPnP events unavailable: {e}")
            self.upnp_enabled = False

        # Initial refresh (this automatically updates group state via _synchronize_group_state())
        try:
            await self.player.refresh()
        except (WiiMConnectionError, WiiMRequestError) as e:
            # Device is unreachable or connection failed - provide user-friendly error
            print(f"\n❌ Cannot connect to device at {self.player.host}")
            print(f"   Error: {e}")
            print("\n   Possible causes:")
            print("   • Device is powered off or unreachable on the network")
            print("   • Incorrect IP address or hostname")
            print("   • Network connectivity issues")
            print("   • Firewall blocking connections")
            raise  # Re-raise to exit with error code

        # Get initial preset count (if supported)
        if self.player.client.capabilities.get("supports_presets", False):
            try:
                self.last_preset_count = await self.player.client.get_max_preset_slots()
                self.last_preset_check = time.time()
            except Exception:
                pass  # Don't fail if preset count fetch fails

        # Get initial multiroom/grouping data for display
        # All LinkPlay devices support grouping, but request may fail due to network/device issues
        try:
            self.last_multiroom = await self.player.get_multiroom_status()
        except WiiMError:
            self.last_multiroom = {}  # Request failed, will retry in monitoring loop

        # Initial hardware reads (player.refresh uses ~60s tier; monitor polls faster for testing)
        now = time.time()
        if self.player.supports_trigger_out:
            try:
                await self.player.get_trigger_out_status()
                self.last_trigger_out_check = now
            except Exception:
                pass
        if self.player.supports_subwoofer:
            try:
                await self.player.get_subwoofer_status()
                self.last_subwoofer_check = now
            except Exception:
                pass
        if self.player.supports_led_indicator:
            try:
                await self.player.get_led_indicator()
                self.last_led_indicator_check = now
            except Exception:
                pass

        # Use player.role as source of truth (updated by refresh() via _synchronize_group_state())
        self.previous_role = self.player.role  # Initialize previous_role to avoid false positives
        self.last_group_info_check = time.time()  # Initialize check time

        self.on_state_changed()

        if self.use_tui:
            # Initialize TUI mode - clear screen and set up layout
            self._init_tui()
        else:
            # Print device info only in non-TUI mode (TUI will show it)
            device_info_print: DeviceInfo | None = self.player.device_info
            if device_info_print:
                print(f"\n📱 Device: {device_info_print.name} ({device_info_print.model})")
                print(f"   Firmware: {device_info_print.firmware}")
                print(f"   MAC: {device_info_print.mac}")
                print(f"   Vendor: {self.player.client.capabilities.get('vendor', 'unknown')}")
                if self.player.client.capabilities.get("supports_channel_balance"):
                    print("   Channel balance: HTTP get (refreshed with EQ interval in monitor; no UPnP)")
                if (
                    self.player.supports_trigger_out
                    or self.player.supports_subwoofer
                    or self.player.supports_led_indicator
                ):
                    print(
                        f"   Hardware poll: trigger/subwoofer/status LED every "
                        f"{self.hardware_poll_interval:.0f}s (library refresh ~60s)"
                    )
                if self.player.supports_trigger_out:
                    trigger_line = self._format_trigger_out_display()
                    if trigger_line:
                        print(f"   {trigger_line}")
                print(f"   Role: {self.player.role}")
                print(f"   pywiim: v{__version__}")

            print("\n" + "=" * 60)
            print("🎵 Real-time Player Monitor")
            print(f"pywiim v{__version__}")
            print("=" * 60)
            print("Press Ctrl+C to stop\n")

    async def monitor_loop(self) -> None:
        """Main monitoring loop with adaptive polling."""
        self.running = True

        while self.running:
            try:
                # Role is updated by player.refresh() via _synchronize_group_state()
                # Use player.role as source of truth (computed from group object)
                role = self.player.role
                is_playing = self.player.is_playing

                # Check UPnP health using change-based detection
                upnp_working = False
                if self.upnp_enabled and self.upnp_health_tracker:
                    upnp_working = self.upnp_health_tracker.is_healthy

                # Get optimal polling interval
                if self.strategy:
                    # Use strategy's interval (already handles playing state and idle timeout)
                    interval = self.strategy.get_optimal_interval(role, is_playing)

                    # Override: if playing without working UPnP, force 1 second polling
                    if is_playing and self.upnp_enabled and not upnp_working:
                        interval = 1.0
                else:
                    # Default: 1 second when playing, 5 seconds when idle
                    interval = 1.0 if is_playing else 5.0

                # Track polling intervals for statistics
                self.poll_intervals.append(interval)

                # Refresh player state (HTTP polling)
                # This automatically updates group state via _synchronize_group_state()
                _LOGGER.info("HTTP poll #%d (interval: %.1fs)", self.http_poll_count + 1, interval)
                # Use previous role from last group info if available, otherwise player.role
                if self.previous_role is not None:
                    old_role = self.previous_role
                elif self.last_group_info:
                    old_role = self.last_group_info.role
                else:
                    old_role = self.player.role

                # Perform lightweight refresh (Tier 1: Status only) by default
                # Full refresh (Tier 3) is handled by specific checks below or explicit full=True
                await self.player.refresh(full=False)
                self.http_poll_count += 1

                # Update health tracker with polling data (for change detection)
                if self.upnp_health_tracker:
                    poll_state = {
                        "play_state": self.player.play_state,
                        "volume": self.player.volume_level,
                        "muted": self.player.is_muted,
                        "title": self.player.media_title,
                        "artist": self.player.media_artist,
                        "album": self.player.media_album,
                    }
                    self.upnp_health_tracker.on_poll_update(poll_state)

                # Get role - use device API state (last_group_info) as authoritative source
                # This correctly shows master/slave even when Player objects aren't linked
                if self.last_group_info:
                    current_role = self.last_group_info.role
                else:
                    # Fallback to player.role if group info not available yet
                    current_role = self.player.role

                # Log position/progress if playing
                if self.player.is_playing and self.player.media_position is not None:
                    position = self.player.media_position
                    duration = self.player.media_duration
                    if duration and duration > 0:
                        progress_pct = (position / duration) * 100
                        pos_min = int(position // 60)
                        pos_sec = int(position % 60)
                        dur_min = int(duration // 60)
                        dur_sec = int(duration % 60)
                        _LOGGER.info(
                            "⏱️  Position: %02d:%02d / %02d:%02d (%.1f%%)",
                            pos_min,
                            pos_sec,
                            dur_min,
                            dur_sec,
                            progress_pct,
                        )
                    else:
                        pos_min = int(position // 60)
                        pos_sec = int(position % 60)
                        _LOGGER.info("⏱️  Position: %02d:%02d", pos_min, pos_sec)

                self.on_state_changed(source="polling")

                # Conditional fetching (less frequent data)
                now = time.time()

                # Device info (every 60s)
                if self.strategy and self.strategy.should_fetch_configuration(self.last_device_info_check, now=now):
                    await self.player.get_device_info()
                    self.last_device_info_check = now

                # Preset count (every 60s, if supported)
                if self.strategy and self.strategy.should_fetch_configuration(self.last_preset_check, now=now):
                    if self.player.client.capabilities.get("supports_presets", False):
                        try:
                            self.last_preset_count = await self.player.client.get_max_preset_slots()
                        except Exception:
                            pass  # Don't fail if preset count fetch fails
                    self.last_preset_check = now

                # Multiroom/grouping info (every 15s) is deprecated in favor of triggered updates
                # but we keep it here for monitoring display purposes (to populate slave list)
                # Using configuration interval (60s) instead of old 15s to reduce load
                if self.strategy and self.strategy.should_fetch_configuration(self.last_multiroom_check, now=now):
                    try:
                        self.last_multiroom = await self.player.get_multiroom_status()
                    except WiiMError:
                        # Request failed (network/device issue), keep last known state
                        if self.last_multiroom is None:
                            self.last_multiroom = {}
                    self.last_multiroom_check = now

                # Device group info (every 60s)
                # Used to get slave information even when slaves aren't linked to Player objects
                if self.strategy and self.strategy.should_fetch_configuration(self.last_group_info_check, now=now):
                    try:
                        self.last_group_info = await self.player.client.get_device_group_info()
                    except Exception:
                        # Request failed, keep last known state
                        pass
                    self.last_group_info_check = now

                # Fetch EQ settings (adaptive interval based on UPnP health)
                # When playing without UPnP events, fetch more frequently
                eq_interval = 30.0  # Default: every 30 seconds

                # If playing, check if UPnP is working
                if is_playing and self.upnp_enabled:
                    # If we haven't received UPnP events recently while playing, UPnP likely not working
                    if self.last_upnp_event_time:
                        time_since_last_upnp = now - self.last_upnp_event_time
                        # If playing for >5 seconds without UPnP events, assume UPnP not working
                        if time_since_last_upnp > 5.0:
                            eq_interval = 5.0  # Fetch EQ every 5 seconds when UPnP not working
                    elif self.upnp_event_count == 0:
                        # Never received any UPnP events - likely not working
                        eq_interval = 5.0

                # EQ + stereo channel balance on the same timer: both are HTTP-driven here.
                # Channel balance has no UPnP path — refresh periodically so the monitor stays
                # accurate when UPnP events are absent (e.g. some dev environments).
                if (now - self.last_eq_check) > eq_interval:
                    if self.player.client.capabilities.get("supports_eq", False):
                        try:
                            self.last_eq_data = await self.player.get_eq()
                            # Update player's cached EQ preset from status if available
                            # (EQ changes are reflected in status model's eq_preset field)
                        except Exception:
                            pass  # Don't fail if EQ fetch fails
                    if self.player.client.capabilities.get("supports_channel_balance", False):
                        try:
                            await self.player.get_channel_balance()
                        except Exception:
                            pass  # Don't fail if balance fetch fails
                    self.last_eq_check = now

                # Audio output status (every 60s, if supported)
                # This updates player's internal cache so audio_output_mode property works
                source_changed = False  # Monitor doesn't track source changes, use interval-based fetching
                if self.strategy and self.strategy.should_fetch_audio_output(
                    self.last_audio_output_check,
                    source_changed,
                    self.player.client.capabilities.get("supports_audio_output", False),
                    now,
                ):
                    if self.player.client.capabilities.get("supports_audio_output", False):
                        try:
                            await self.player.get_audio_output_status()
                            # Method automatically updates player's internal cache
                        except Exception:
                            pass  # Don't fail if audio output fetch fails
                    self.last_audio_output_check = now

                # 12V trigger + subwoofer (monitor-local fast poll for testing; not library CONFIGURATION_INTERVAL)
                if self._should_fetch_hardware_status(
                    self.last_trigger_out_check,
                    bool(self.player.supports_trigger_out),
                    now,
                ):
                    try:
                        status = await self.player.get_trigger_out_status()
                        if status is not None:
                            self.last_trigger_out_check = now
                    except Exception:
                        pass

                if self._should_fetch_hardware_status(
                    self.last_subwoofer_check,
                    bool(self.player.supports_subwoofer),
                    now,
                ):
                    try:
                        sub = await self.player.get_subwoofer_status()
                        if sub is not None:
                            self.last_subwoofer_check = now
                    except Exception:
                        pass

                if self._should_fetch_hardware_status(
                    self.last_led_indicator_check,
                    bool(self.player.supports_led_indicator),
                    now,
                ):
                    try:
                        await self.player.get_led_indicator()
                        self.last_led_indicator_check = now
                    except Exception:
                        pass

                # Check for role changes (player.role is updated by refresh() via _synchronize_group_state())
                role_changed = current_role != old_role

                if role_changed:
                    _LOGGER.debug(
                        "Role change detected: %s → %s (from player.role after refresh)",
                        old_role,
                        current_role,
                    )

                    timestamp = datetime.now().strftime("%H:%M:%S")

                    # Determine join/unjoin event type
                    if old_role == "solo" and current_role in ("master", "slave"):
                        # Joined a group
                        if current_role == "master":
                            # Get slave count from group object (Player manages this)
                            slave_count = len(self.player.group.slaves) if self.player.group else 0
                            message = f"👥 GROUP JOIN: Became MASTER (slaves: {slave_count})"
                        else:
                            # Get master info from group object (Player manages this)
                            master_info = (
                                self.player.group.master.name
                                if self.player.group and self.player.group.master
                                else "unknown"
                            )
                            message = f"👥 GROUP JOIN: Joined as SLAVE (master: {master_info})"
                    elif old_role in ("master", "slave") and current_role == "solo":
                        # Left a group
                        message = f"👥 GROUP UNJOIN: Left group (was {old_role.upper()})"
                    else:
                        # Role transition (master <-> slave)
                        message = f"👥 GROUP ROLE CHANGE: {old_role.upper()} → {current_role.upper()}"

                    # Add to recent events for TUI display
                    self._add_event(timestamp, message)

                    # In non-TUI mode, print to console
                    if not self.use_tui:
                        print("\r" + " " * 100 + "\r", end="", flush=True)
                        print(f"[{timestamp}] {message}")

                # Update previous_role for next change detection
                if role_changed:
                    self.previous_role = current_role

                # Display current status (use player.role as source of truth)
                self._display_status(current_role, interval)

                # Wait for next poll (use sleep_until_cancelled to handle Ctrl-C gracefully)
                try:
                    await asyncio.sleep(interval)
                except asyncio.CancelledError:
                    self.running = False
                    break

            except KeyboardInterrupt:
                self.running = False
                break
            except Exception as e:
                # Print error on new line, then continue
                print(f"\n⚠️  Error during monitoring: {e}")
                self.error_count += 1
                # Mark player as unavailable
                self.player._available = False
                await asyncio.sleep(5)  # Wait before retrying

    def _init_tui(self) -> None:
        """Initialize TUI mode - clear screen and draw initial layout."""
        # Clear screen and move cursor to top
        print("\033[2J\033[H", end="", flush=True)
        self.tui_initialized = True

        # Draw header
        print("=" * 80)
        print("🎵 WiiM Player Monitor".center(80))
        print(f"pywiim v{__version__}".center(80))
        print("=" * 80)
        print()  # Leave space for content

    def _add_event(self, timestamp: str, message: str) -> None:
        """Add event to recent events list (for TUI display)."""
        self.recent_events.append((timestamp, message))
        if len(self.recent_events) > self.max_events:
            self.recent_events.pop(0)

    def _display_status(self, role: str, interval: float) -> None:
        """Display current player status."""
        if self.use_tui and self.tui_initialized:
            self._display_tui(role, interval)
        else:
            self._display_line_status(role, interval)

    def _display_tui(self, role: str, interval: float) -> None:
        """Display comprehensive player status in TUI mode with fixed window layout."""
        import os

        # Get terminal width (default to 80 if can't determine)
        try:
            cols = os.get_terminal_size().columns
        except (OSError, AttributeError):
            cols = 80

        # Move cursor to line 5 (after header)
        print("\033[5;1H", end="", flush=True)

        # Clear from cursor to end of screen
        print("\033[J", end="", flush=True)

        if not self.player.available:
            print("❌ Device unavailable")
            return

        device_info = self.player.device_info
        status_model = self.player._status_model

        # ===== DEVICE INFO =====
        device_name = device_info.name if device_info else "Unknown"
        device_model = device_info.model if device_info else "Unknown"
        firmware = device_info.firmware if device_info else "Unknown"
        mac = device_info.mac if device_info else "Unknown"
        ip = self.player.host

        # Preset count (if available)
        preset_info = ""
        if self.last_preset_count is not None and self.last_preset_count > 0:
            preset_info = f"  |  Presets: {self.last_preset_count}"

        print(f"📱 {device_name} ({device_model})")
        print(f"   Firmware: {firmware}  |  MAC: {mac}  |  IP: {ip}  |  Role: {role.upper()}{preset_info}")
        print(f"   pywiim: v{__version__}")
        print()

        # ===== PLAYBACK STATUS =====
        # Use normalized state property for clean display
        state = self.player.state  # "playing", "paused", "idle", or "buffering"
        if state == "playing":
            state_icon = "▶️"
            state_text = "PLAYING"
        elif state == "paused":
            state_icon = "⏸️"
            state_text = "PAUSED"
        elif state == "buffering":
            state_icon = "⏳"
            state_text = "BUFFERING"
        else:  # idle
            state_icon = "⏹️"
            state_text = "IDLE"

        volume = self.player.volume_level
        volume_str = f"{volume:.0%}" if volume is not None else "?"
        mute_str = " 🔇" if self.player.is_muted else ""

        source = self.player.source or "none"
        if source != "none":
            source = " ".join(word.capitalize() for word in source.split())

        # Get mode from status model (for debugging mode=0 bug)
        mode_str = ""
        if self.player._status_model and hasattr(self.player._status_model, "mode"):
            mode_value = self.player._status_model.mode
            if mode_value is not None:
                mode_str = f"  |  mode={mode_value}"

        print(f"{state_icon} {state_text}  |  Volume: {volume_str}{mute_str}  |  Source: {source}{mode_str}")
        print()

        # ===== INPUT INFO =====
        current_source = self.player.source or "none"
        available_sources = self.player.available_sources
        device_info = self.player.device_info

        # Show current input if there is one
        if current_source != "none":
            current_source_display = self._format_source_name(current_source)
            print(f"📻 Input: {current_source_display}")
        else:
            print("📻 Input: None")

        # Show available inputs (only physical inputs that can be switched to)
        # Streaming services (spotify, amazon, dlna, etc.) are not user-selectable sources
        if available_sources:
            # Only show physical inputs (exclude streaming services)
            streaming_services = {
                "spotify",
                "amazon",
                "dlna",
                "airplay",
                "tidal",
                "qobuz",
                "deezer",
                "iheartradio",
                "pandora",
                "tunein",
                "wifi",
            }
            # Filter to physical inputs only, but include current source (marked as current)
            physical_inputs = [s for s in available_sources if s.lower() not in streaming_services]
            if physical_inputs:
                # Format inputs and mark current one
                formatted_inputs = []
                for s in physical_inputs[:5]:  # Limit to first 5 for display
                    formatted = self._format_source_name(s)
                    if s == current_source:
                        formatted += " (current)"
                    formatted_inputs.append(formatted)

                inputs_str = ", ".join(formatted_inputs)
                if len(physical_inputs) > 5:
                    inputs_str += f" (+{len(physical_inputs) - 5} more)"
                print(f"   Available: {inputs_str}")
        else:
            # Debug: Show why available_sources is None
            if device_info:
                print(f"   Debug: input_list={device_info.input_list}, plm_support={device_info.plm_support}")
            else:
                print("   Debug: device_info is None")

        # Always show plm_support and input_list for debugging
        if device_info:
            # Show input_list if available
            if device_info.input_list:
                print(f"   input_list: {', '.join(device_info.input_list)}")

            # Show plm_support with bit breakdown
            if device_info.plm_support is not None:
                try:
                    if isinstance(device_info.plm_support, str):
                        plm_value = (
                            int(device_info.plm_support.replace("0x", "").replace("0X", ""), 16)
                            if "x" in device_info.plm_support.lower()
                            else int(device_info.plm_support)
                        )
                    else:
                        plm_value = int(device_info.plm_support)

                    # Show bit breakdown (per Arylic/LinkPlay documentation)
                    # bit1=bit0, bit2=bit1, bit3=bit2, bit4=bit3, bit6=bit5, bit8=bit7, bit15=bit14
                    known_bits = []
                    if plm_value & (1 << 0):  # bit1: LineIn
                        known_bits.append("bit1:line_in")
                    if plm_value & (1 << 1):  # bit2: Bluetooth
                        known_bits.append("bit2:bluetooth")
                    if plm_value & (1 << 2):  # bit3: USB
                        known_bits.append("bit3:usb")
                    if plm_value & (1 << 3):  # bit4: Optical
                        known_bits.append("bit4:optical")
                    if plm_value & (1 << 5):  # bit6: Coaxial
                        known_bits.append("bit6:coaxial")
                    if plm_value & (1 << 7):  # bit8: LineIn 2
                        known_bits.append("bit8:line_in_2")
                    if plm_value & (1 << 14):  # bit15: USBDAC (informational only)
                        known_bits.append("bit15:usbdac")

                    # Check for unknown bits (may indicate new inputs like phono/HDMI on newer devices)
                    known_bit_positions = {0, 1, 2, 3, 5, 7, 14}
                    unknown_bits = []
                    for bit_pos in range(16):
                        if plm_value & (1 << bit_pos) and bit_pos not in known_bit_positions:
                            unknown_bits.append(f"bit{bit_pos + 1} (bit {bit_pos})")

                    bits_str = ", ".join(known_bits) if known_bits else "none"
                    if unknown_bits:
                        bits_str += f" | Unknown: {', '.join(unknown_bits)}"
                    print(f"   plm_support: {device_info.plm_support} (0x{plm_value:x}) → {bits_str}")
                except (ValueError, TypeError):
                    print(f"   plm_support: {device_info.plm_support} (parse error)")
        print()

        # ===== TRACK INFO =====
        if self.player.media_title and self.player.media_title.lower() not in ("unknown", "unknow", "none"):
            artist = self.player.media_artist or "Unknown Artist"
            album = self.player.media_album or None

            if artist.lower() not in ("unknown", "unknow", "none"):
                track_line = f"🎵 {artist} - {self.player.media_title}"
            else:
                track_line = f"🎵 {self.player.media_title}"

            if album and album.lower() not in ("unknown", "unknow", "none"):
                track_line += f" ({album})"

            print(track_line)

            # Position/Progress
            if self.player.media_position is not None and self.player.media_duration:
                pos_min = int(self.player.media_position // 60)
                pos_sec = int(self.player.media_position % 60)
                dur_min = int(self.player.media_duration // 60)
                dur_sec = int(self.player.media_duration % 60)

                progress_pct = (
                    (self.player.media_position / self.player.media_duration) * 100
                    if self.player.media_duration > 0
                    else 0
                )
                bar_width = min(50, cols - 25)
                filled = int(bar_width * progress_pct / 100)
                bar = "█" * filled + "░" * (bar_width - filled)

                print(f"⏱️  {pos_min:02d}:{pos_sec:02d} / {dur_min:02d}:{dur_sec:02d}  [{bar}] {progress_pct:.1f}%")

            # Audio Quality Info
            quality_parts = []
            # Check codec from status model directly as fallback
            codec = self.player.media_codec
            if not codec and self.player._status_model:
                codec = getattr(self.player._status_model, "codec", None)
            if codec:
                quality_parts.append(f"Codec: {codec.upper()}")
            if self.player.media_sample_rate:
                quality_parts.append(f"{self.player.media_sample_rate} Hz")
            if self.player.media_bit_depth:
                quality_parts.append(f"{self.player.media_bit_depth}-bit")
            if self.player.media_bit_rate:
                quality_parts.append(f"{self.player.media_bit_rate} kbps")

            if quality_parts:
                print(f"🎧 {' | '.join(quality_parts)}")
            print()
        else:
            print("🎵 No track information")
            # Still show audio quality if available, even without track title
            quality_parts = []
            # Check codec from status model directly as fallback
            codec = self.player.media_codec
            if not codec and self.player._status_model:
                codec = getattr(self.player._status_model, "codec", None)
            if codec:
                quality_parts.append(f"Codec: {codec.upper()}")
            if self.player.media_sample_rate:
                quality_parts.append(f"{self.player.media_sample_rate} Hz")
            if self.player.media_bit_depth:
                quality_parts.append(f"{self.player.media_bit_depth}-bit")
            if self.player.media_bit_rate:
                quality_parts.append(f"{self.player.media_bit_rate} kbps")

            if quality_parts:
                print(f"🎧 {' | '.join(quality_parts)}")
            print()

        # ===== ARTWORK URL =====
        # Always show artwork URL when available, even if no track info
        # Check both the property and the status model directly
        artwork_url = self.player.media_image_url
        if not artwork_url and self.player._status_model:
            # Fallback: check status model directly
            artwork_url = getattr(self.player._status_model, "entity_picture", None) or getattr(
                self.player._status_model, "cover_url", None
            )

        if artwork_url and artwork_url.strip():
            # Truncate long URLs for display
            max_url_len = min(70, cols - 10)
            if len(artwork_url) > max_url_len:
                display_url = artwork_url[: max_url_len - 3] + "..."
            else:
                display_url = artwork_url
            print(f"🖼️  Artwork URL: {display_url}")
            print()

        # ===== AUDIO SETTINGS =====
        audio_settings = []

        # EQ Preset - get from EQ data first (most accurate), fallback to status model
        eq_preset = None
        if self.last_eq_data and isinstance(self.last_eq_data, dict):
            # Try multiple field names for current preset (as per diagnostics.py)
            eq_preset = (
                self.last_eq_data.get("Name")
                or self.last_eq_data.get("name")
                or self.last_eq_data.get("preset")
                or self.last_eq_data.get("EQPreset")
                or self.last_eq_data.get("eq_preset")
            )

        # Fallback to status model if EQ data doesn't have preset
        if not eq_preset:
            eq_preset = self.player.eq_preset

        if eq_preset:
            # Normalize preset name (handle case variations)
            eq_preset_lower = str(eq_preset).lower()
            # Map common variations
            if "hip" in eq_preset_lower and "hop" in eq_preset_lower:
                eq_preset = "Hip-Hop"
            elif eq_preset_lower == "flat":
                eq_preset = "Flat"
            else:
                # Capitalize first letter of each word
                eq_preset = " ".join(word.capitalize() for word in str(eq_preset).split())
            audio_settings.append(f"EQ: {eq_preset}")

        # EQ Custom bands (if available)
        if self.last_eq_data and isinstance(self.last_eq_data, dict):
            eq_bands = self.last_eq_data.get("eq", [])
            if isinstance(eq_bands, list) and len(eq_bands) == 10:
                # Show EQ bands as a compact visualization
                eq_str = " ".join(f"{b:+2d}" for b in eq_bands[:5])  # First 5 bands
                audio_settings.append(f"EQ Bands: [{eq_str} ...]")

        if self.player.supports_channel_balance:
            bal = self.player.channel_balance
            if bal is not None:
                audio_settings.append(f"Balance: {bal:+.2f} (L=-1 R=+1)")
            else:
                audio_settings.append("Balance: —")

        # Audio Output Mode - show current and available
        output_mode = self.player.audio_output_mode
        available_outputs = self.player.available_outputs
        if output_mode or available_outputs:
            if output_mode:
                # Show current output, mark it in available list if present
                if available_outputs and output_mode in available_outputs:
                    # Format available outputs, marking current one
                    formatted_outputs = []
                    for out in available_outputs[:4]:  # Limit to first 4 for display
                        formatted = out.replace("_", " ").title()
                        if out == output_mode:
                            formatted += " (current)"
                        formatted_outputs.append(formatted)
                    outputs_str = ", ".join(formatted_outputs)
                    if len(available_outputs) > 4:
                        outputs_str += f" (+{len(available_outputs) - 4} more)"
                    audio_settings.append(f"Output: {outputs_str}")
                else:
                    # Current output not in available list (shouldn't happen, but handle gracefully)
                    audio_settings.append(f"Output: {output_mode}")
            elif available_outputs:
                # No current output but have available outputs
                outputs_str = ", ".join(out.replace("_", " ").title() for out in available_outputs[:4])
                if len(available_outputs) > 4:
                    outputs_str += f" (+{len(available_outputs) - 4} more)"
                audio_settings.append(f"Outputs: {outputs_str}")

        # Available Input Sources
        available_sources = self.player.available_sources
        if available_sources:
            sources_str = ", ".join(s.replace("_", " ").title() for s in available_sources[:4])
            if len(available_sources) > 4:
                sources_str += f" (+{len(available_sources) - 4} more)"
            audio_settings.append(f"Inputs: {sources_str}")

        if audio_settings:
            print("🔊 " + "  |  ".join(audio_settings))
            print()

        # ===== HARDWARE (12V TRIGGER / SUBWOOFER) =====
        hardware_parts = []
        trigger_line = self._format_trigger_out_display()
        if trigger_line:
            hardware_parts.append(trigger_line)
        led_line = self._format_led_indicator_display()
        if led_line:
            hardware_parts.append(led_line)
        if self.player.supports_subwoofer and self.player.subwoofer_status:
            sub = self.player.subwoofer_status
            enabled = sub.get("status", 0) == 1
            cross = sub.get("cross", 0)
            hardware_parts.append(f"Subwoofer: {'On' if enabled else 'Off'}, {cross}Hz")
        if hardware_parts:
            print("🔌 " + "  |  ".join(hardware_parts))
            print()

        # ===== PLAYBACK SETTINGS =====
        playback_settings = []

        # Shuffle (decoded from loop_mode bit 2, or from direct shuffle field)
        # Returns None for external sources (AirPlay, Bluetooth, etc.)
        if self.player.shuffle_supported:
            shuffle = self.player.shuffle_state
            if shuffle is not None:
                playback_settings.append(f"Shuffle: {'ON' if shuffle else 'OFF'}")
        else:
            # Shuffle controlled by source device/app, not WiiM device
            playback_settings.append("Shuffle: N/A (controlled by source)")

        # Repeat (decoded from loop_mode bits 0-1, or from direct repeat field)
        # Returns None for external sources (AirPlay, Bluetooth, etc.)
        if self.player.repeat_supported:
            repeat = self.player.repeat_mode
            if repeat:
                repeat_display = {"one": "One", "all": "All", "off": "Off"}.get(repeat, repeat.title())
                playback_settings.append(f"Repeat: {repeat_display}")
        else:
            # Repeat controlled by source device/app, not WiiM device
            playback_settings.append("Repeat: N/A (controlled by source)")

        # Note: loop_mode is not displayed separately since shuffle and repeat already show the info
        # loop_mode is a bit flag that encodes both shuffle and repeat:
        #   bit 0 (1) = repeat_one, bit 1 (2) = repeat_all, bit 2 (4) = shuffle
        # Examples: 0=normal, 1=repeat_one, 2=repeat_all, 4=shuffle, 5=shuffle+repeat_one, 6=shuffle+repeat_all

        if playback_settings:
            print("🎛️  " + "  |  ".join(playback_settings))
            print()

        # ===== PRESET STATIONS =====
        presets = self.player.presets
        if presets:
            print("📻 Preset Stations:")
            # Show up to 10 presets, with names if available
            for preset in presets[:10]:
                preset_num = preset.get("number", "?")
                preset_name = preset.get("name", "Unnamed")
                # Show preset number and name
                print(f"   Preset {preset_num}: {preset_name}")
            if len(presets) > 10:
                print(f"   ... and {len(presets) - 10} more presets")
            print()
        elif self.player.client.capabilities.get("supports_presets", False):
            # Device supports presets but none are configured
            print("📻 Preset Stations: None configured")
            print()

        # ===== GROUPING INFO =====
        if role != "solo":
            group_lines = []

            # Use player.group as source of truth (Player manages this)
            if self.player.group:
                if role == "master":
                    # Get slave info from group object (Player manages this)
                    slave_count = len(self.player.group.slaves)
                    if slave_count > 0:
                        # Get slave hosts from group object
                        slave_hosts = [slave.host for slave in self.player.group.slaves]
                        group_lines.append(f"👥 Master with {slave_count} slave{'s' if slave_count != 1 else ''}")
                        if slave_hosts:
                            slaves_str = ", ".join(slave_hosts[:3])
                            if len(slave_hosts) > 3:
                                slaves_str += f" (+{len(slave_hosts) - 3} more)"
                            group_lines.append(f"   Slaves: {slaves_str}")
                    else:
                        # Group object has no linked slaves, but device API might report slaves
                        # (e.g., if player_finder not available or slaves not linked yet)
                        # Use cached device group info from monitor loop
                        if (
                            self.last_group_info
                            and self.last_group_info.slave_count > 0
                            and self.last_group_info.slave_hosts
                        ):
                            slave_count = self.last_group_info.slave_count
                            slave_hosts = self.last_group_info.slave_hosts
                            group_lines.append(f"👥 Master with {slave_count} slave{'s' if slave_count != 1 else ''}")
                            slaves_str = ", ".join(slave_hosts[:3])
                            if len(slave_hosts) > 3:
                                slaves_str += f" (+{len(slave_hosts) - 3} more)"
                            group_lines.append(f"   Slaves: {slaves_str}")
                        else:
                            # Master with no slaves (group may be forming or slaves disconnected)
                            group_lines.append("👥 Master")

                elif role == "slave":
                    # Get master info from group object (Player manages this)
                    master = self.player.group.master
                    master_info = master.name if master.name else master.host
                    group_lines.append(f"👥 Slave of: {master_info}")
            else:
                # Fallback: group object not available, try to get info from device API
                if role == "master":
                    # Use cached device group info to show slaves if available
                    if (
                        self.last_group_info
                        and self.last_group_info.slave_count > 0
                        and self.last_group_info.slave_hosts
                    ):
                        slave_count = self.last_group_info.slave_count
                        slave_hosts = self.last_group_info.slave_hosts
                        group_lines.append(f"👥 Master with {slave_count} slave{'s' if slave_count != 1 else ''}")
                        slaves_str = ", ".join(slave_hosts[:3])
                        if len(slave_hosts) > 3:
                            slaves_str += f" (+{len(slave_hosts) - 3} more)"
                        group_lines.append(f"   Slaves: {slaves_str}")
                    else:
                        group_lines.append("👥 Master")
                elif role == "slave":
                    # Try to get master info from cached device group info
                    if self.last_group_info and self.last_group_info.master_host:
                        master_info = self.last_group_info.master_host
                        group_lines.append(f"👥 Slave of: {master_info}")
                    else:
                        group_lines.append("👥 Slave")

            if group_lines:
                for line in group_lines:
                    print(line)
                print()

        # ===== GROUP DEBUG INFO =====
        # Show compact grouping debug info (useful for troubleshooting role detection)
        debug_parts = []

        # Group field from device_info (0=solo, non-0=in group)
        if self.player.device_info:
            group_val = self.player.device_info.group
            debug_parts.append(f"group={group_val}")

        # Multiroom version (wmrm protocol version)
        if self.last_multiroom:
            wmrm_ver = self.last_multiroom.get("wmrm_version", "?")
            slaves_count = self.last_multiroom.get("slaves", 0)
            debug_parts.append(f"slaves={slaves_count}")
            debug_parts.append(f"wmrm={wmrm_ver}")

        # Note: Device API returns master_uuid for slaves, not master_ip
        # We don't display it here since we already show "👥 Slave of: ..." above

        # Slave list (only shown if master with slaves)
        if role == "master":
            if self.last_group_info and self.last_group_info.slave_hosts:
                slaves_str = ", ".join(self.last_group_info.slave_hosts[:3])
                if len(self.last_group_info.slave_hosts) > 3:
                    slaves_str += f" +{len(self.last_group_info.slave_hosts) - 3}"
                debug_parts.append(f"slave_hosts=[{slaves_str}]")

        # Player group object status (only useful in multi-player contexts)
        # In single-player monitor mode, this is less meaningful
        if self.player.group and self.player.group.size > 1:
            debug_parts.append(f"group_obj=linked({self.player.group.size})")

        if debug_parts:
            print(f"🔍 {role.upper()}: {' | '.join(debug_parts)}")
            print()

        # ===== NETWORK INFO =====
        network_info = []

        # WiFi RSSI
        if status_model and hasattr(status_model, "wifi_rssi") and status_model.wifi_rssi is not None:
            rssi = status_model.wifi_rssi
            signal_str = "Excellent" if rssi > -50 else "Good" if rssi > -70 else "Fair" if rssi > -80 else "Poor"
            network_info.append(f"WiFi: {rssi} dBm ({signal_str})")

        # WiFi Channel
        if status_model and hasattr(status_model, "wifi_channel") and status_model.wifi_channel is not None:
            network_info.append(f"Channel: {status_model.wifi_channel}")

        if network_info:
            print("📶 " + "  |  ".join(network_info))
            print()

        # ===== CONNECTION STATUS =====
        connection_info = []

        # Polling interval
        connection_info.append(f"Polling: {interval:.1f}s")

        # HTTP poll count
        if self.http_poll_count > 0:
            connection_info.append(f"Polls: {self.http_poll_count}")

        # UPnP health status with visual indicators
        if self.upnp_enabled:
            if self.upnp_health_tracker:
                stats = self.upnp_health_tracker.statistics
                if stats["has_enough_samples"]:
                    # Have enough data to make health assessment
                    if stats["is_healthy"]:
                        status_icon = "🟢"
                        status_text = "HEALTHY"
                    else:
                        status_icon = "🔴"
                        status_text = "DEGRADED"

                    connection_info.append(
                        f"UPnP: {status_icon} {status_text} "
                        f"({stats['detected_changes'] - stats['missed_changes']}/{stats['detected_changes']} caught, "
                        f"{stats['miss_rate'] * 100:.0f}% miss)"
                    )
                else:
                    # Not enough data yet, show event count
                    if self.upnp_event_count > 0:
                        connection_info.append(f"UPnP: ⚪ LEARNING ({self.upnp_event_count} events)")
                    else:
                        connection_info.append("UPnP: ⚪ LEARNING (waiting for changes)")
            else:
                # Fallback: no health tracker
                if self.upnp_event_count > 0:
                    connection_info.append(f"UPnP: {self.upnp_event_count} events")
                else:
                    connection_info.append("UPnP: enabled")
        else:
            connection_info.append("UPnP: disabled")

        # State changes
        if self.state_change_count > 0:
            connection_info.append(f"Changes: {self.state_change_count}")

        print(f"📡 {'  |  '.join(connection_info)}")
        print()

        # ===== RECENT EVENTS =====
        print("─" * min(80, cols))
        print("Recent Events:")
        if self.recent_events:
            for timestamp, message in self.recent_events[-self.max_events :]:
                # Truncate long messages
                max_msg_len = cols - 15
                if len(message) > max_msg_len:
                    message = message[: max_msg_len - 3] + "..."
                print(f"  [{timestamp}] {message}")
        else:
            print("  (no events yet)")

        # Footer
        print("─" * min(80, cols))
        print("Press Ctrl+C to stop")

        # Move cursor to bottom (so it doesn't interfere with display)
        print(f"\033[{30};1H", end="", flush=True)

    def _display_line_status(self, role: str, interval: float) -> None:
        """Display status in single-line mode (legacy)."""
        if not self.player.available:
            print("\r❌ Device unavailable" + " " * 80, end="", flush=True)
            return

        # Build status line
        status_parts = []

        # Play state - use normalized state property
        state = self.player.state  # "playing", "paused", "idle", or "buffering"
        if state == "playing":
            status_parts.append("▶️  PLAYING")
        elif state == "paused":
            status_parts.append("⏸️  PAUSED")
        elif state == "buffering":
            status_parts.append("⏳  BUFFERING")
        else:  # idle
            status_parts.append("⏹️  IDLE")

        # Volume
        volume = self.player.volume_level
        if volume is not None:
            mute_indicator = "🔇" if self.player.is_muted else ""
            status_parts.append(f"Vol: {volume:.0%}{mute_indicator}")
        else:
            status_parts.append("Vol: ?")

        if self.player.supports_channel_balance:
            bal = self.player.channel_balance
            if bal is not None:
                status_parts.append(f"Bal {bal:+.2f}")
            else:
                status_parts.append("Bal —")

        trigger_line = self._format_trigger_out_display()
        if trigger_line:
            # Compact for single-line mode: "Trigger ON" / "Trigger OFF"
            compact = trigger_line.replace("12V Trigger: ", "Trigger ").split(" (read")[0]
            status_parts.append(compact)

        led_line = self._format_led_indicator_display()
        if led_line:
            compact_led = led_line.replace("Status LED: ", "LED ").split(" (read")[0]
            status_parts.append(compact_led)

        # Source (capitalize properly)
        source = self.player.source or "none"
        if source != "none":
            # Capitalize first letter of each word
            source = " ".join(word.capitalize() for word in source.split())
        status_parts.append(f"Source: {source}")

        # Track info
        if self.player.media_title and self.player.media_title.lower() not in ("unknown", "unknow", "none"):
            title = self.player.media_title
            artist = self.player.media_artist or "Unknown Artist"
            if artist.lower() not in ("unknown", "unknow", "none"):
                status_parts.append(f"🎵 {artist} - {title}")
            else:
                status_parts.append(f"🎵 {title}")

            # Position
            if self.player.media_position is not None and self.player.media_duration:
                pos_min = self.player.media_position // 60
                pos_sec = self.player.media_position % 60
                dur_min = self.player.media_duration // 60
                dur_sec = self.player.media_duration % 60
                status_parts.append(f"⏱️  {pos_min:02d}:{pos_sec:02d}/{dur_min:02d}:{dur_sec:02d}")

        # Artwork URL (always show when available, even if no track info)
        # Check both the property and the status model directly
        artwork_url = self.player.media_image_url
        if not artwork_url and self.player._status_model:
            # Fallback: check status model directly
            artwork_url = getattr(self.player._status_model, "entity_picture", None) or getattr(
                self.player._status_model, "cover_url", None
            )

        if artwork_url and artwork_url.strip():
            # Truncate long URLs for display
            max_url_len = 50
            if len(artwork_url) > max_url_len:
                artwork_url = artwork_url[: max_url_len - 3] + "..."
            status_parts.append(f"🖼️  {artwork_url}")

        # Role
        if role != "solo":
            status_parts.append(f"👥 {role.upper()}")

        # Polling interval and connection info
        connection_parts = [f"poll: {interval:.1f}s"]

        # UPnP event count (informational only, not health indicator)
        if self.upnp_enabled:
            if self.upnp_event_count > 0:
                connection_parts.append(f"UPnP: {self.upnp_event_count}")
            else:
                connection_parts.append("UPnP: on")
        else:
            connection_parts.append("UPnP: off")

        status_parts.append(f"📡 {' | '.join(connection_parts)}")

        # Print status line (overwrite previous line, clear to end)
        status_line = " | ".join(status_parts)
        print(f"\r{status_line:<100}", end="", flush=True)

    async def stop(self) -> None:
        """Stop monitoring."""
        self.running = False

        # Clear TUI if active
        if self.use_tui and self.tui_initialized:
            print("\033[2J\033[H", end="", flush=True)

        # Stop UPnP subscriptions
        if self.upnp_eventer:
            try:
                await self.upnp_eventer.async_unsubscribe()
            except Exception:
                pass

        if self.upnp_client:
            try:
                await self.upnp_client.unwind_notify_server()
            except Exception:
                pass

        await self.player.client.close()

    def print_statistics(self) -> None:
        """Print monitoring statistics summary."""
        if self.start_time is None:
            return

        duration = time.time() - self.start_time
        duration_min = int(duration // 60)
        duration_sec = int(duration % 60)

        print("\n" + "=" * 60)
        print("📊 Monitoring Statistics")
        print("=" * 60)

        # Duration
        print(f"⏱️  Duration: {duration_min}m {duration_sec}s")

        # HTTP Polling
        avg_interval = sum(self.poll_intervals) / len(self.poll_intervals) if self.poll_intervals else 0
        print("\n📡 HTTP Polling:")
        print(f"   • Total polls: {self.http_poll_count}")
        print(f"   • Average interval: {avg_interval:.2f}s")
        if self.poll_intervals:
            print(f"   • Interval range: {min(self.poll_intervals):.2f}s - {max(self.poll_intervals):.2f}s")

        # UPnP Events
        if self.upnp_enabled:
            print("\n📨 UPnP Events:")
            print(f"   • Total events received: {self.upnp_event_count}")
            if self.last_upnp_event_time and self.start_time:
                time_since_last = time.time() - self.last_upnp_event_time
                if time_since_last < 60:
                    print(f"   • Last event: {int(time_since_last)}s ago")
                else:
                    print(f"   • Last event: {int(time_since_last // 60)}m {int(time_since_last % 60)}s ago")
            if self.upnp_event_count > 0 and duration > 0:
                events_per_min = (self.upnp_event_count / duration) * 60
                print(f"   • Average rate: {events_per_min:.1f} events/min")
            if self.upnp_client:
                print("   • Status: ✅ Subscribed")
            else:
                print("   • Status: ❌ Not available")
        else:
            print("\n📨 UPnP Events: ❌ Not enabled")

        # State Changes
        print("\n🔄 State Changes:")
        print(f"   • Total changes detected: {self.state_change_count}")
        if self.http_poll_count > 0:
            change_rate = (self.state_change_count / self.http_poll_count) * 100
            print(f"   • Change rate: {change_rate:.1f}% of polls")

        # Errors
        if self.error_count > 0:
            print(f"\n⚠️  Errors: {self.error_count}")
        else:
            print("\n✅ Errors: None")

        # Device Status
        print("\n📱 Device Status:")
        trigger_line = self._format_trigger_out_display()
        if trigger_line:
            print(f"   • {trigger_line}")
        led_line = self._format_led_indicator_display()
        if led_line:
            print(f"   • {led_line}")
        print(f"   • Available: {'✅' if self.player.available else '❌'}")
        if self.player.device_info:
            print(f"   • Name: {self.player.device_info.name}")
            print(f"   • Model: {self.player.device_info.model}")
        if self.player.play_state:
            print(f"   • Play state: {self.player.play_state}")

        print("=" * 60)


async def main() -> int:
    """Main entry point for monitor CLI."""
    import argparse
    import logging

    parser = argparse.ArgumentParser(
        description="Real-time WiiM player monitor with UPnP event support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  wiim-monitor 192.168.1.68

  # Specify callback host for UPnP
  wiim-monitor 192.168.1.68 --callback-host 192.168.1.254

  # Enable verbose logging for debugging
  wiim-monitor 192.168.1.68 --verbose
  wiim-monitor 192.168.1.68 --log-level DEBUG

  # Enable verbose UPnP event logging (shows full event JSON/XML)
  wiim-monitor 192.168.1.68 --upnp-verbose

  # Faster trigger/subwoofer polling while testing against the WiiM app (default 10s)
  wiim-monitor 192.168.1.68 --hardware-poll 5
        """,
    )
    parser.add_argument(
        "device_ip",
        help="Device IP address or hostname",
    )
    parser.add_argument(
        "--callback-host",
        help="IP address for UPnP callback URL (auto-detected if not specified)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging (equivalent to --log-level INFO)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="WARNING",
        help="Set logging level (default: WARNING)",
    )
    parser.add_argument(
        "--no-tui",
        action="store_true",
        help="Disable TUI mode (use scrolling log instead of fixed window)",
    )
    parser.add_argument(
        "--upnp-verbose",
        action="store_true",
        help="Enable verbose UPnP event logging (shows full event JSON/XML data)",
    )
    parser.add_argument(
        "--hardware-poll",
        type=float,
        default=10.0,
        metavar="SECONDS",
        help="Poll 12V trigger, subwoofer, and status LED every N seconds in this CLI (default: 10). "
        "Does not change library/HA refresh (~60s).",
    )

    args = parser.parse_args()
    device_ip = args.device_ip
    callback_host_override = args.callback_host
    use_tui = not args.no_tui

    # Configure logging
    log_level = logging.INFO if args.verbose else getattr(logging, args.log_level)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    _LOGGER = logging.getLogger(__name__)

    # Create client and player
    client = WiiMClient(device_ip)
    player = Player(client, on_state_changed=None)  # We'll handle callbacks in monitor

    monitor = PlayerMonitor(player)
    monitor.player._on_state_changed = monitor.on_state_changed  # Set callback
    monitor.use_tui = use_tui  # Set TUI mode preference
    monitor.upnp_verbose = args.upnp_verbose  # Set UPnP verbose logging flag
    monitor.hardware_poll_interval = max(1.0, float(args.hardware_poll))

    # Store callback host override for use in setup
    if callback_host_override:
        monitor._callback_host_override = callback_host_override
    else:
        monitor._callback_host_override = None

    try:
        await monitor.setup()
        await monitor.monitor_loop()
        # Print statistics if loop exits normally
        monitor.print_statistics()
        return 0
    except KeyboardInterrupt:
        print("\n\n⚠️  Monitoring stopped by user (Ctrl+C)")
        # Print statistics on Ctrl-C
        monitor.print_statistics()
        return 0
    except (WiiMConnectionError, WiiMRequestError):
        # Connection errors are already handled in setup() with user-friendly messages
        # Just exit cleanly without showing traceback
        return 1
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        # Clean up resources
        try:
            await monitor.stop()
        except Exception as cleanup_err:
            _LOGGER.debug("Error during cleanup: %s", cleanup_err)
        try:
            await client.close()
        except Exception as cleanup_err:
            _LOGGER.debug("Error closing client: %s", cleanup_err)


def cli_main() -> None:
    """CLI entry point."""
    sys.exit(asyncio.run(main()))


if __name__ == "__main__":
    cli_main()
