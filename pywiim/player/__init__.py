"""Player class - represents a single device that can be solo, master, or slave.

This module provides the Player class, which is a thin wrapper around WiiMClient
that adds group awareness, role management, and cached state with getter methods.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from ..api.constants import DISPLAY_DEFAULT_BRIGHTNESS
from ..api.subwoofer import SubwooferStatus
from ..client import WiiMClient
from ..models import DeviceInfo, PlayerStatus
from .audio import AudioConfiguration
from .base import PlayerBase
from .bluetooth import BluetoothControl
from .coverart import CoverArtManager
from .diagnostics import DiagnosticsCollector
from .groupops import GroupOperations
from .media import MediaControl, NotificationPlaybackResult
from .playback import PlaybackControl
from .properties import PlayerProperties
from .statemgr import StateManager
from .volume import VolumeControl

if TYPE_CHECKING:
    from ..group import Group
    from ..upnp.client import UpnpClient


class Player(PlayerBase):
    """Represents a single WiiM/LinkPlay device that can be solo, master, or slave.

    A Player is a thin wrapper around WiiMClient that adds group awareness,
    cached state, and convenient getter methods for accessing device information.
    The role (solo/master/slave) is computed from group membership, not stored.

    Volume and mute behavior in groups:
    - When a master calls set_volume() or set_mute(), changes propagate to ALL
      slaves proportionally (same absolute change in percentage points)
    - When a slave calls set_volume() or set_mute(), only that device changes
      (slaves have independent volume control in LinkPlay protocol)

    The Player caches status and device_info for efficient access via getter
    methods. Use refresh() to update the cache. The Player integrates with
    StateSynchronizer to merge HTTP polling and UPnP event data.

    Example:
        ```python
        player = Player(WiiMClient("192.168.1.100"))
        await player.refresh()

        print(player.volume_level)
        print(player.media_title)
        print(player.role)

        await player.set_volume(0.5)
        await player.play()
        ```

    Args:
        client: WiiMClient instance for this device.
        upnp_client: Optional UPnP client for queue management and events.
        on_state_changed: Optional callback function called when state is updated.
        player_finder: Optional callback to find Player objects by host/IP.
            Called as `player_finder(host)` and should return Player | None.
            Used to automatically link Player objects when groups are detected on refresh.
        all_players_finder: Optional callback to get all known Player objects.
            Called as `all_players_finder()` and should return list[Player].
            Used for cross-coordinator role inference in WiFi Direct multiroom,
            where slaves report as "solo" but can be identified via master's slave list.
    """

    def __init__(
        self,
        client: WiiMClient,
        upnp_client: UpnpClient | None = None,
        on_state_changed: Callable[[], None] | None = None,
        player_finder: Callable[[str], Any] | None = None,
        all_players_finder: Callable[[], list[Any]] | None = None,
    ) -> None:
        """Initialize a Player instance."""
        super().__init__(client, upnp_client, on_state_changed, player_finder, all_players_finder)

        # Initialize component managers
        self._state_mgr = StateManager(self)
        self._volume_ctrl = VolumeControl(self)
        self._media_ctrl = MediaControl(self)
        self._audio_config = AudioConfiguration(self)
        self._playback_ctrl = PlaybackControl(self)
        self._coverart_mgr = CoverArtManager(self)
        self._properties = PlayerProperties(self)
        self._group_ops = GroupOperations(self)
        self._diagnostics = DiagnosticsCollector(self)
        self._bluetooth_ctrl = BluetoothControl(self)

    # === State Management ===

    def apply_diff(self, changes: dict[str, Any]) -> bool:
        """Apply state changes from UPnP events."""
        return self._state_mgr.apply_diff(changes)

    def update_from_upnp(self, data: dict[str, Any]) -> None:
        """Update state from UPnP event data."""
        self._state_mgr.update_from_upnp(data)

    async def refresh(self, full: bool = False) -> None:
        """Refresh cached state from device.

        Args:
            full: If True, perform a full refresh including expensive endpoints (device info, EQ, BT).
                 If False (default), only fetch fast-changing status data (volume, playback).
        """
        await self._state_mgr.refresh(full=full)

    async def get_device_info(self) -> DeviceInfo:
        """Get device information (always queries device)."""
        return await self._state_mgr.get_device_info()

    async def get_status(self) -> PlayerStatus:
        """Get current player status (always queries device)."""
        return await self._state_mgr.get_status()

    async def get_play_state(self) -> str:
        """Get current playback state by querying device."""
        return await self._state_mgr.get_play_state()

    # === Volume Control ===

    async def set_volume(self, volume: float) -> None:
        """Set volume level (0.0-1.0)."""
        await self._volume_ctrl.set_volume(volume)

    async def set_mute(self, mute: bool) -> None:
        """Set mute state."""
        await self._volume_ctrl.set_mute(mute)

    async def get_volume(self) -> float | None:
        """Get current volume level by querying device."""
        return await self._volume_ctrl.get_volume()

    async def get_muted(self) -> bool | None:
        """Get current mute state by querying device."""
        return await self._volume_ctrl.get_muted()

    # === Media Control ===

    async def play(self) -> None:
        """Start playback (raw API call).

        Note: On streaming sources when paused, this may restart the track.
        Consider using resume() or media_play_pause() instead.
        """
        await self._media_ctrl.play()

    async def pause(self) -> None:
        """Pause playback (raw API call)."""
        await self._media_ctrl.pause()

    async def resume(self) -> None:
        """Resume playback from paused state (raw API call).

        Use this instead of play() when resuming paused content to avoid restarting.
        """
        await self._media_ctrl.resume()

    async def stop(self) -> None:
        """Stop playback (raw API call).

        Note: WiFi/Webradio sources may not stay stopped. Consider using pause() for web streams.
        """
        await self._media_ctrl.stop()

    async def media_play_pause(self) -> None:
        """Toggle play/pause state intelligently (Home Assistant compatible).

        Automatically uses resume() when paused to avoid restarting tracks.
        This is the recommended method for Home Assistant's media_play_pause service.
        """
        await self._media_ctrl.media_play_pause()

    async def next_track(self) -> None:
        """Skip to next track."""
        await self._media_ctrl.next_track()

    async def previous_track(self) -> None:
        """Skip to previous track."""
        await self._media_ctrl.previous_track()

    async def seek(self, position: int) -> None:
        """Seek to position in current track."""
        await self._media_ctrl.seek(position)

    async def play_url(self, url: str, enqueue: Literal["add", "next", "replace", "play"] = "replace") -> None:
        """Play a URL directly with optional enqueue support.

        Note: This is a fire-and-forget API. Invalid URLs won't raise exceptions.
        Check play_state after a few seconds to verify playback started.
        See MediaControl.play_url() for full documentation.
        """
        await self._media_ctrl.play_url(url, enqueue)

    async def play_playlist(self, playlist_url: str) -> None:
        """Play a playlist (M3U) URL."""
        await self._media_ctrl.play_playlist(playlist_url)

    async def play_notification(self, url: str, *, force_interrupt: bool = False) -> NotificationPlaybackResult:
        """Play a notification sound from URL.

        Uses native playPromptUrl on supported sources and automatically
        falls back to play_url on unsupported/unknown sources so notification
        audio is still heard.

        Args:
            url: URL to notification audio file.
            force_interrupt: If True, always use play_url so the notification
                is guaranteed audible (e.g. for TTS when prompt path fails).

        Returns:
            NotificationPlaybackResult with method_used and interruption hint.
        """
        return await self._media_ctrl.play_notification(url, force_interrupt=force_interrupt)

    async def add_to_queue(self, url: str, metadata: str = "") -> None:
        """Add URL to end of queue (requires UPnP client)."""
        await self._media_ctrl.add_to_queue(url, metadata)

    async def insert_next(self, url: str, metadata: str = "") -> None:
        """Insert URL after current track (requires UPnP client)."""
        await self._media_ctrl.insert_next(url, metadata)

    async def get_queue(
        self,
        object_id: str = "Q:0",
        starting_index: int = 0,
        requested_count: int = 0,
    ) -> list[dict[str, Any]]:
        """Get current queue contents (requires UPnP client with ContentDirectory service).

        **Note on Queue Information:**
        - **Queue count and position**: Available via HTTP API (`plicount`, `plicurr` in getPlayerStatus)
        - **Full queue contents**: Requires UPnP ContentDirectory service (see availability below)

        **ContentDirectory Availability:**
        ContentDirectory service is only available on:
        - WiiM Amp (when USB drive is connected)
        - WiiM Ultra (when USB drive is connected)

        Other WiiM devices (Mini, Pro, Pro Plus) do not expose ContentDirectory service
        as they function only as UPnP renderers, not media servers.

        Args:
            object_id: Queue object ID (default "Q:0" for standard queue)
            starting_index: Starting index for pagination (0 = first item)
            requested_count: Number of items to retrieve (0 = all available)

        Returns:
            List of queue item dictionaries, each containing:
            - media_content_id: Media URI (HA standard field name)
            - title: Track title (if available)
            - artist: Artist name (if available)
            - album: Album name (if available)
            - duration: Duration in seconds (if available)
            - position: Position in queue (0-based index)
            - image_url: Album art URL (if available)

        Raises:
            WiiMError: If UPnP client is not available, ContentDirectory service is not
                available, or queue retrieval fails

        Example:
            ```python
            queue = await player.get_queue()
            for item in queue:
                print(f"{item['position']}: {item.get('title', 'Unknown')} - {item.get('artist', 'Unknown')}")
            ```
        """
        return await self._media_ctrl.get_queue(object_id, starting_index, requested_count)

    async def play_queue(self, queue_position: int = 0) -> None:
        """Start playing from the queue at a specific position.

        Uses UPnP AVTransport Seek action with TRACK_NR unit to jump to queue position.

        Args:
            queue_position: 0-based index in queue to start playing (default: 0)

        Raises:
            WiiMError: If UPnP client is not available, queue position is invalid,
                or the seek action fails

        Example:
            ```python
            await player.play_queue(5)  # Play from position 5 in queue
            ```
        """
        await self._media_ctrl.play_queue(queue_position)

    async def remove_from_queue(self, queue_position: int = 0) -> None:
        """Remove an item from the queue at a specific position.

        Uses UPnP AVTransport RemoveTrackFromQueue action.

        Args:
            queue_position: 0-based index in queue to remove (default: 0)

        Raises:
            WiiMError: If UPnP client is not available, queue position is invalid,
                or the remove action fails

        Example:
            ```python
            await player.remove_from_queue(3)  # Remove item at position 3
            ```
        """
        await self._media_ctrl.remove_from_queue(queue_position)

    async def clear_queue(self) -> None:
        """Clear all items from the queue.

        Uses UPnP AVTransport RemoveAllTracksFromQueue action.

        Raises:
            WiiMError: If UPnP client is not available or the action fails

        Example:
            ```python
            await player.clear_queue()  # Remove all items from queue
            ```
        """
        await self._media_ctrl.clear_queue()

    async def play_preset(self, preset: int, index: int | None = None) -> None:
        """Play a preset by number, optionally starting at a track index.

        Args:
            preset: Preset number (1-based).
            index: Optional 1-based track index to start from (e.g. 1 = from beginning).
                When None, device resumes from last position.
        """
        await self._media_ctrl.play_preset(preset, index=index)

    async def clear_playlist(self) -> None:
        """Clear the current playlist."""
        await self._media_ctrl.clear_playlist()

    # === Audio Configuration ===

    async def set_source(self, source: str) -> None:
        """Set audio input source."""
        await self._audio_config.set_source(source)

    async def set_audio_output_mode(self, mode: str | int) -> None:
        """Set audio output mode by friendly name or integer."""
        await self._audio_config.set_audio_output_mode(mode)

    async def select_output(self, output: str) -> None:
        """Select output by name (hardware mode or specific BT device)."""
        await self._audio_config.select_output(output)

    async def set_led(self, enabled: bool) -> None:
        """Set LED on/off state."""
        await self._audio_config.set_led(enabled)

    async def set_led_brightness(self, brightness: int) -> None:
        """Set LED brightness level."""
        await self._audio_config.set_led_brightness(brightness)

    # === LED Indicator (ADR 005) ===

    async def get_led_indicator(self) -> bool:
        """Read LED indicator state (on/off). Updates ``led_indicator_on`` cache."""
        state = await self.client.get_led_indicator()
        self._led_indicator_on = state
        return state

    async def set_led_indicator(self, enabled: bool) -> None:
        """Set LED indicator on or off (LED_SWITCH_SET)."""
        await self.client.set_led_switch(enabled)
        self._led_indicator_on = enabled
        if self._on_state_changed:
            self._on_state_changed()

    async def get_channel_balance(self) -> float | None:
        """Read stereo channel balance from the device and refresh the player cache.

        Uses HTTP ``getChannelBalance`` when ``supports_channel_balance`` is true.
        There is no UPnP event for balance; integrations should rely on this call,
        periodic refresh during ``refresh()``, or optimistic updates after ``set_channel_balance``.

        Returns:
            Cached balance -1.0 (left) to 1.0 (right), or None if unsupported or unreadable.
        """
        if not self.supports_channel_balance:
            return None
        bal = await self._audio_config.get_channel_balance()
        if bal != self._channel_balance:
            self._channel_balance = bal
            if self._on_state_changed:
                self._on_state_changed()
        return self._channel_balance

    async def set_channel_balance(self, balance: float) -> None:
        """Set channel balance (left/right stereo balance)."""
        await self._audio_config.set_channel_balance(balance)

    async def sync_time(self, ts: int | None = None) -> None:
        """Synchronize device time."""
        await self._diagnostics.sync_time(ts)

    async def set_eq_preset(self, preset: str) -> None:
        """Set equalizer preset."""
        await self._audio_config.set_eq_preset(preset)

    async def set_eq_custom(self, eq_values: list[int]) -> None:
        """Set custom 10-band equalizer values."""
        await self._audio_config.set_eq_custom(eq_values)

    async def set_eq_enabled(self, enabled: bool) -> None:
        """Enable or disable the equalizer."""
        await self._audio_config.set_eq_enabled(enabled)

    async def get_eq(self) -> dict[str, Any]:
        """Get current equalizer band values."""
        return await self._audio_config.get_eq()

    async def get_eq_presets(self) -> list[str]:
        """Get list of available equalizer presets."""
        return await self._audio_config.get_eq_presets()

    async def get_eq_status(self) -> bool:
        """Get current equalizer enabled status."""
        return await self._audio_config.get_eq_status()

    async def get_multiroom_status(self) -> dict[str, Any]:
        """Get multiroom group status information."""
        return await self._audio_config.get_multiroom_status()

    async def get_audio_output_status(self) -> dict[str, Any] | None:
        """Get current audio output status."""
        return await self._audio_config.get_audio_output_status()

    async def get_meta_info(self) -> dict[str, Any]:
        """Get detailed metadata information about current track."""
        return await self._audio_config.get_meta_info()

    # === Subwoofer Control (WiiM Ultra with firmware 5.2+) ===

    async def get_subwoofer_status(self) -> SubwooferStatus | None:
        """Get current subwoofer configuration.

        Returns:
            SubwooferStatus with current settings, or None if not supported.
        """
        raw = await self.client.get_subwoofer_status_raw()
        if raw:
            self._subwoofer_status = raw
            return SubwooferStatus.from_dict(raw)
        return None

    async def set_subwoofer_enabled(self, enabled: bool) -> None:
        """Enable or disable subwoofer output.

        Args:
            enabled: True to enable subwoofer, False to disable.
        """
        await self.client.set_subwoofer_enabled(enabled)
        # Update cache optimistically
        if self._subwoofer_status:
            self._subwoofer_status["status"] = 1 if enabled else 0
        if self._on_state_changed:
            self._on_state_changed()

    async def set_subwoofer_level(self, level: int) -> None:
        """Set subwoofer level adjustment (-15 to +15 dB).

        Args:
            level: Level adjustment in dB.
        """
        await self.client.set_subwoofer_level(level)
        # Update cache optimistically
        if self._subwoofer_status:
            self._subwoofer_status["level"] = level
        if self._on_state_changed:
            self._on_state_changed()

    async def set_subwoofer_crossover(self, frequency: int) -> None:
        """Set subwoofer crossover frequency (30-250 Hz).

        Args:
            frequency: Crossover frequency in Hz.
        """
        await self.client.set_subwoofer_crossover(frequency)
        if self._subwoofer_status:
            self._subwoofer_status["cross"] = frequency
        if self._on_state_changed:
            self._on_state_changed()

    async def set_subwoofer_phase(self, phase: int) -> None:
        """Set subwoofer phase (0 or 180 degrees).

        Args:
            phase: Phase in degrees (0 or 180).
        """
        await self.client.set_subwoofer_phase(phase)
        if self._subwoofer_status:
            self._subwoofer_status["phase"] = phase
        if self._on_state_changed:
            self._on_state_changed()

    async def set_subwoofer_delay(self, delay_ms: int) -> None:
        """Set subwoofer delay adjustment (-200 to +200 ms).

        Args:
            delay_ms: Delay in milliseconds.
        """
        await self.client.set_subwoofer_delay(delay_ms)
        if self._subwoofer_status:
            self._subwoofer_status["sub_delay"] = delay_ms
        if self._on_state_changed:
            self._on_state_changed()

    # === Display (WiiM Ultra; ADR 005) ===

    async def set_display_enabled(
        self,
        enabled: bool,
        *,
        default_bright: int | None = None,
        auto_sense_enable: int | None = None,
    ) -> None:
        """Turn display/LCD on or off (WiiM Ultra only).

        The LCD uses ``setLightOperationBrightConfig`` (brightness + on/off), not the
        LED indicator API. When turning on, optional ``default_bright`` overrides
        the library default (full brightness on a 1–100 scale).

        Adaptive brightness (``auto_sense_enable``) defaults to enabled (1) when
        turning on; pass ``auto_sense_enable=0`` for a fixed brightness. This
        avoids the panel staying dark on some WiiM Ultra firmware (mjcumming/wiim#250).
        """
        await self.client.set_display_enabled(
            enabled,
            default_bright=default_bright,
            auto_sense_enable=auto_sense_enable,
        )

    async def set_display_config(
        self,
        *,
        auto_sense_enable: int = 0,
        default_bright: int = DISPLAY_DEFAULT_BRIGHTNESS,
        disable: int = 0,
    ) -> None:
        """Set display/LCD config (WiiM Ultra only). disable: 0=on, 1=off."""
        await self.client.set_display_config(
            auto_sense_enable=auto_sense_enable,
            default_bright=default_bright,
            disable=disable,
        )

    # === 12V Trigger (WiiM Ultra / Pro / Pro Plus) ===

    async def get_trigger_out_status(self) -> bool | None:
        """Get 12V trigger output status.

        Returns:
            True if trigger is on, False if off, or None if not supported.
        """
        status = await self.client.get_trigger_out_status()
        if status is not None:
            self._trigger_out_on = status
        return status

    async def set_trigger_out(self, on: bool) -> None:
        """Set 12V trigger output on or off.

        Args:
            on: True to turn trigger on, False to turn off.
        """
        await self.client.set_trigger_out(on)
        self._trigger_out_on = on
        if self._on_state_changed:
            self._on_state_changed()

    async def set_trigger_out_on(self) -> None:
        """Turn 12V trigger output on."""
        await self.set_trigger_out(True)

    async def set_trigger_out_off(self) -> None:
        """Turn 12V trigger output off."""
        await self.set_trigger_out(False)

    async def reboot(self) -> None:
        """Reboot the device."""
        await self._diagnostics.reboot()

    # === Firmware Updates (WiiM devices only) ===

    async def check_for_updates_wiim(self) -> dict[str, Any]:
        """Check for firmware updates (WiiM devices only).

        Uses the WiiM-specific getMvRemoteUpdateStartCheck command to search
        for available firmware updates.

        Returns:
            Dictionary containing update check results.

        Raises:
            WiiMError: If device is not a WiiM device or request fails.
        """
        return await self.client.check_for_updates_wiim()

    async def install_firmware_update(self) -> None:
        """Install firmware update (WiiM devices only).

        This method:
        1. Checks for available updates
        2. Downloads the update if available
        3. Installs the update automatically

        WARNING: DO NOT POWER OFF THE DEVICE DURING THIS PROCESS!
        The device will reboot automatically after installation completes.

        The installation process can take several minutes. The device may become
        unresponsive during installation. This is normal behavior.

        Raises:
            WiiMError: If device is not a WiiM device, no update is available,
                or the installation process fails.
        """
        await self.client.install_firmware_update()

    async def get_update_download_status(self) -> dict[str, Any]:
        """Get firmware update download status (WiiM devices only).

        Returns the download progress and status of the firmware update process.

        Returns:
            Dictionary containing download status information.

        Raises:
            WiiMError: If device is not a WiiM device or request fails.
        """
        return await self.client.get_update_download_status()

    async def get_update_install_status(self) -> dict[str, Any]:
        """Get firmware update installation status (WiiM devices only).

        Returns the installation progress and status of the firmware update process.

        Returns:
            Dictionary containing:
            - status: Installation state code (string)
            - progress: Installation progress percentage 0-100 (string)

        Raises:
            WiiMError: If device is not a WiiM device or request fails.
        """
        return await self.client.get_update_install_status()

    # === Playback Control ===

    async def set_shuffle(self, enabled: bool) -> None:
        """Set shuffle mode on or off, preserving current repeat state."""
        await self._playback_ctrl.set_shuffle(enabled)

    async def set_repeat(self, mode: str) -> None:
        """Set repeat mode, preserving current shuffle state."""
        await self._playback_ctrl.set_repeat(mode)

    # === Cover Art ===

    async def fetch_cover_art(self, url: str | None = None) -> tuple[bytes, str] | None:
        """Fetch cover art image from URL."""
        return await self._coverart_mgr.fetch_cover_art(url)

    async def get_cover_art_bytes(self, url: str | None = None) -> bytes | None:
        """Get cover art image bytes (convenience method)."""
        return await self._coverart_mgr.get_cover_art_bytes(url)

    # === Group Operations ===

    async def create_group(self) -> Group:
        """Create a new group with this player as master."""
        return await self._group_ops.create_group()

    async def join_group(self, master: Player) -> None:
        """Join this player to another player."""
        await self._group_ops.join_group(master)

    async def leave_group(self) -> None:
        """Leave the current group."""
        await self._group_ops.leave_group()

    # === Diagnostics ===

    async def get_diagnostics(self) -> dict[str, Any]:
        """Get comprehensive diagnostic information for this player."""
        return await self._diagnostics.get_diagnostics()

    async def get_multiroom_diagnostics(self) -> dict[str, Any]:
        """Get multiroom-specific diagnostic information.

        This method helps debug WiFi Direct multiroom linking issues by providing
        detailed information about:
        - This device's role and UUID
        - Linked Player objects (if any)
        - Raw device API group state
        - Available player_finder and all_players_finder callbacks
        - Analysis of potential linking issues

        Use this when multiroom groups aren't linking correctly, especially
        for WiFi Direct setups where slaves have internal 10.10.10.x IPs.

        Returns:
            Dictionary with multiroom diagnostic information including:
            - this_device: Identity and state info
            - callbacks: Which callbacks are set
            - group_object: Linked Player objects
            - api_group_info: Raw device API group state
            - api_slaves_info: Full slave list from API
            - all_known_players: All players from all_players_finder
            - linking_analysis: Issues and recommendations
        """
        return await self._diagnostics.get_multiroom_diagnostics()

    # === Bluetooth ===

    async def get_bluetooth_history(self) -> list[dict[str, Any]]:
        """Get Bluetooth connection history."""
        return await self._bluetooth_ctrl.get_bluetooth_history()

    async def connect_bluetooth_device(self, mac_address: str) -> None:
        """Connect to a Bluetooth device by MAC address."""
        await self._bluetooth_ctrl.connect_bluetooth_device(mac_address)

    async def disconnect_bluetooth_device(self) -> None:
        """Disconnect the currently connected Bluetooth device."""
        await self._bluetooth_ctrl.disconnect_bluetooth_device()

    async def get_bluetooth_pair_status(self) -> dict[str, Any]:
        """Get Bluetooth pairing status."""
        return await self._bluetooth_ctrl.get_bluetooth_pair_status()

    async def scan_for_bluetooth_devices(self, duration: int = 3) -> list[dict[str, Any]]:
        """Scan for nearby Bluetooth devices."""
        return await self._bluetooth_ctrl.scan_for_bluetooth_devices(duration)

    # === Timer and Alarm (WiiM only) ===

    async def set_sleep_timer(self, seconds: int) -> None:
        """Set sleep timer to stop playback after specified seconds.

        Args:
            seconds: Duration in seconds (0=immediate, -1=cancel)

        Note:
            WiiM devices only. See client.set_sleep_timer() for details.
        """
        await self.client.set_sleep_timer(seconds)

    async def get_sleep_timer(self) -> int:
        """Get remaining sleep timer seconds.

        Returns:
            Remaining seconds, or 0 if no timer active.

        Note:
            WiiM devices only.
        """
        return await self.client.get_sleep_timer()

    async def cancel_sleep_timer(self) -> None:
        """Cancel active sleep timer.

        Note:
            WiiM devices only.
        """
        await self.client.cancel_sleep_timer()

    async def set_alarm(
        self,
        alarm_id: int,
        trigger: int,
        operation: int,
        time: str,
        day: str | None = None,
        url: str | None = None,
    ) -> None:
        """Set or configure an alarm.

        Args:
            alarm_id: Alarm slot index (0-2)
            trigger: Trigger type (use ALARM_TRIGGER_* constants)
            operation: Operation type (use ALARM_OP_* constants)
            time: Alarm time in HHMMSS format (UTC)
            day: Day parameter (format depends on trigger type)
            url: Media URL or shell command (optional)

        Note:
            WiiM devices only. See client.set_alarm() for details.
        """
        await self.client.set_alarm(alarm_id, trigger, operation, time, day, url)

    async def get_alarm(self, alarm_id: int) -> dict[str, Any]:
        """Get specific alarm configuration.

        Args:
            alarm_id: Alarm slot index (0-2)

        Returns:
            Alarm configuration dictionary.

        Note:
            WiiM devices only.
        """
        return await self.client.get_alarm(alarm_id)

    async def get_alarms(self) -> list[dict[str, Any]]:
        """Get all alarm configurations (3 slots).

        Returns:
            List of 3 alarm configuration dictionaries.

        Note:
            WiiM devices only.
        """
        return await self.client.get_alarms()

    async def delete_alarm(self, alarm_id: int) -> None:
        """Delete (cancel) an alarm.

        Args:
            alarm_id: Alarm slot index (0-2)

        Note:
            WiiM devices only.
        """
        await self.client.delete_alarm(alarm_id)

    async def stop_current_alarm(self) -> None:
        """Stop currently ringing alarm.

        Note:
            WiiM devices only.
        """
        await self.client.stop_current_alarm()

    # === Properties (read-only) ===

    @property
    def device_name(self) -> str | None:
        """Device name from cached device info."""
        return self._properties.device_name

    @property
    def firmware_update_available(self) -> bool:
        """Whether a firmware update is available and ready to install.

        Returns True if version_update="1" (update downloaded and ready),
        False otherwise (no update or not ready).

        Note: Updates cannot be installed via API. If an update is available
        and downloaded, rebooting the device will install it. Use player.reboot()
        to trigger installation.
        """
        return self._properties.firmware_update_available

    @property
    def latest_firmware_version(self) -> str | None:
        """Latest available firmware version from device info.

        Returns the version string from NewVer field in getStatusEx,
        or None if not available.
        """
        return self._properties.latest_firmware_version

    @property
    def volume_level(self) -> float | None:
        """Current volume level (0.0-1.0) from cached status."""
        return self._properties.volume_level

    @property
    def is_muted(self) -> bool | None:
        """Current mute state from cached status."""
        return self._properties.is_muted

    @property
    def channel_balance(self) -> float | None:
        """Cached stereo channel balance (-1.0 left … 1.0 right), or None if unknown.

        Updated by ``get_channel_balance()``, ``set_channel_balance()``, and periodic ``refresh()``
        when the device supports channel balance.
        """
        return self._properties.channel_balance

    @property
    def play_state(self) -> str | None:
        """Current playback state from cached status."""
        return self._properties.play_state

    @property
    def is_playing(self) -> bool:
        """Whether device is currently playing (including buffering/loading).

        Returns True for any active playback state. Use this instead of
        checking play_state strings manually.
        """
        return self._properties.is_playing

    @property
    def is_paused(self) -> bool:
        """Whether device is paused."""
        return self._properties.is_paused

    @property
    def is_idle(self) -> bool:
        """Whether device is idle (no media loaded)."""
        return self._properties.is_idle

    @property
    def is_buffering(self) -> bool:
        """Whether device is buffering or loading media."""
        return self._properties.is_buffering

    @property
    def state(self) -> str:
        """Normalized playback state: 'playing', 'paused', 'idle', or 'buffering'.

        Maps directly to Home Assistant's MediaPlayerState values.
        """
        return self._properties.state

    @property
    def media_title(self) -> str | None:
        """Current track title from cached status."""
        return self._properties.media_title

    @property
    def media_artist(self) -> str | None:
        """Current track artist from cached status."""
        return self._properties.media_artist

    @property
    def media_album(self) -> str | None:
        """Current track album from cached status."""
        return self._properties.media_album

    @property
    def media_content_id(self) -> str | None:
        """Current media content identifier (URL if playing from URL)."""
        return self._properties.media_content_id

    @property
    def media_duration(self) -> int | None:
        """Current track duration in seconds from cached status."""
        return self._properties.media_duration

    @property
    def media_position(self) -> int | None:
        """Current playback position in seconds with hybrid estimation."""
        return self._properties.media_position

    @property
    def media_image_url(self) -> str | None:
        """Media image URL from cached status."""
        return self._properties.media_image_url

    @property
    def queue_count(self) -> int | None:
        """Total number of tracks in queue (from HTTP API plicount field)."""
        return self._properties.queue_count

    @property
    def queue_position(self) -> int | None:
        """Current track position in queue (from HTTP API plicurr field)."""
        return self._properties.queue_position

    @property
    def media_sample_rate(self) -> int | None:
        """Audio sample rate in Hz from metadata."""
        return self._properties.media_sample_rate

    @property
    def media_bit_depth(self) -> int | None:
        """Audio bit depth in bits from metadata."""
        return self._properties.media_bit_depth

    @property
    def media_bit_rate(self) -> int | None:
        """Audio bit rate in kbps from metadata."""
        return self._properties.media_bit_rate

    @property
    def media_codec(self) -> str | None:
        """Audio codec from status (e.g., 'flac', 'mp3', 'aac')."""
        return self._properties.media_codec

    @property
    def source(self) -> str | None:
        """Current source from cached status."""
        return self._properties.source

    @property
    def source_id(self) -> str | None:
        """Alias for `source` (stable catalog id)."""
        return self._properties.source_id

    @property
    def source_name(self) -> str | None:
        """Current source display name (UI-ready)."""
        return self._properties.source_name

    @property
    def shuffle_supported(self) -> bool:
        """Whether shuffle can be controlled by the device in current state."""
        return self._properties.shuffle_supported

    @property
    def repeat_supported(self) -> bool:
        """Whether repeat mode can be controlled by the device in current state."""
        return self._properties.repeat_supported

    @property
    def shuffle_state(self) -> bool | None:
        """Shuffle state, or None if not controlled by device."""
        return self._properties.shuffle_state

    @property
    def repeat_mode(self) -> str | None:
        """Repeat mode ('one', 'all', 'off'), or None if not controlled by device."""
        return self._properties.repeat_mode

    @property
    def eq_preset(self) -> str | None:
        """Current EQ preset from cached status."""
        return self._properties.eq_preset

    @property
    def shuffle(self) -> bool | None:
        """Shuffle state from cached status (alias for shuffle_state)."""
        return self._properties.shuffle

    @property
    def repeat(self) -> str | None:
        """Repeat mode from cached status (alias for repeat_mode)."""
        return self._properties.repeat

    @property
    def wifi_rssi(self) -> int | None:
        """Wi-Fi signal strength (RSSI) from cached status."""
        return self._properties.wifi_rssi

    @property
    def available_sources(self) -> list[str]:
        """Available input sources from cached device info.

        Returns:
            List of available source names, or empty list if unavailable.
        """
        return self._properties.available_sources

    @property
    def source_catalog(self) -> list[dict[str, Any]]:
        """Structured source catalog for integrations.

        Returns:
            List of source dictionaries with stable IDs, source type, selectability,
            capability flags, and current-source marker.
        """
        return self._properties.source_catalog

    @property
    def audio_output_mode(self) -> str | None:
        """Current audio output mode as friendly name."""
        return self._properties.audio_output_mode

    @property
    def audio_output_mode_int(self) -> int | None:
        """Current audio output mode as integer."""
        return self._properties.audio_output_mode_int

    @property
    def available_output_modes(self) -> list[str]:
        """Available audio output modes for this device."""
        return self._properties.available_output_modes

    @property
    def is_bluetooth_output_active(self) -> bool:
        """Check if Bluetooth output is currently active."""
        return self._properties.is_bluetooth_output_active

    @property
    def bluetooth_output_devices(self) -> list[dict[str, str]]:
        """Paired Bluetooth output devices (Audio Sinks only).

        Returns:
            List of dicts with keys: name, mac, connected

        Example:
            [
                {"name": "Sony SRS-XB43", "mac": "AA:BB:CC:DD:EE:FF", "connected": True},
                {"name": "JBL Tune 750", "mac": "11:22:33:44:55:66", "connected": False}
            ]
        """
        return self._properties.bluetooth_output_devices

    @property
    def available_outputs(self) -> list[str]:
        """All available outputs (hardware modes + paired BT devices).

        Returns:
            List of output names. Bluetooth devices are prefixed with "BT: "

        Example:
            ["Line Out", "Optical Out", "BT: Sony Speaker"]
        """
        return self._properties.available_outputs

    @property
    def eq_presets(self) -> list[str]:
        """Available EQ presets from cached state, with "Off" option first.

        Returns:
            List of EQ preset names with "Off" first, or empty list if not available.
            "Off" represents EQ disabled (audio passes through without EQ processing).

        Example:
            ["Off", "Flat", "Acoustic", "Bass", "Rock", "Jazz", "Custom"]
        """
        presets = self._eq_presets if self._eq_presets is not None else []
        if presets:
            return ["Off"] + presets
        return []

    @property
    def presets(self) -> list[dict[str, Any]] | None:
        """Preset stations (playback presets) from cached state.

        Returns:
            List of preset dictionaries with number, name, url, and picurl fields,
            or None if not available or presets not supported.

        Example:
            [
                {"number": 1, "name": "Radio Paradise", "url": "...", "picurl": "..."},
                {"number": 2, "name": "BBC Radio 1", "url": "...", "picurl": "..."}
            ]
        """
        return self._presets

    @property
    def metadata(self) -> dict[str, Any] | None:
        """Audio quality metadata from cached state.

        Contains bitrate, sample rate, codec information for current track.

        Returns:
            Dict with audio quality info, or None if not available.

        Example:
            {
                "bitrate": "320 kbps",
                "sample_rate": "44100",
                "codec": "mp3"
            }
        """
        return self._metadata

    @property
    def audio_output_status(self) -> dict[str, Any] | None:
        """Audio output status from cached state.

        Contains current audio output configuration.

        Returns:
            Dict with audio output info, or None if not available.
        """
        return self._audio_output_status

    @property
    def subwoofer_status(self) -> dict[str, Any] | None:
        """Subwoofer configuration from cached state.

        Only available on WiiM Ultra with firmware 5.2+.
        Updated every 60 seconds during polling.

        Returns:
            Dict with subwoofer settings, or None if not supported.
            Keys: status, plugged, cross, phase, level, sub_delay, main_filter, sub_filter, etc.
        """
        return self._subwoofer_status

    @property
    def subwoofer_enabled(self) -> bool | None:
        """Whether subwoofer output is enabled.

        Returns:
            True if enabled, False if disabled, None if not supported.
        """
        if self._subwoofer_status is None:
            return None
        return bool(self._subwoofer_status.get("status", 0) == 1)

    @property
    def subwoofer_level(self) -> int | None:
        """Subwoofer level adjustment in dB (-15 to +15).

        Returns:
            Level in dB, or None if not supported.
        """
        if self._subwoofer_status is None:
            return None
        return int(self._subwoofer_status.get("level", 0))

    @property
    def subwoofer_crossover(self) -> int | None:
        """Subwoofer crossover frequency in Hz (30-250).

        Returns:
            Crossover frequency in Hz, or None if not supported.
        """
        if self._subwoofer_status is None:
            return None
        return int(self._subwoofer_status.get("cross", 80))

    @property
    def supports_subwoofer(self) -> bool:
        """Whether subwoofer control is supported (probed via getSubLPF at capability detection)."""
        if not self.client:
            return False
        return self.client.capabilities.get("supports_subwoofer") is True

    @property
    def supports_trigger_out(self) -> bool:
        """Whether 12V trigger output is supported (WiiM Ultra / Pro / Pro Plus)."""
        if not self.client:
            return False
        return bool(self.client.capabilities.get("supports_trigger_out", False))

    @property
    def trigger_out_on(self) -> bool | None:
        """Cached 12V trigger state (True=on, False=off, None=unknown).

        Updated when get_trigger_out_status() or set_trigger_out() is called, and on
        configuration-tier refresh during player.refresh() (ADR 019).
        """
        return self._trigger_out_on

    @property
    def led_indicator_on(self) -> bool | None:
        """Cached status LED state (True=on, False=off, None=unknown).

        Updated when get_led_indicator() or set_led_indicator() is called, and on
        configuration-tier refresh when LED_SWITCH_GET is supported.
        """
        return self._led_indicator_on

    def upnp_health_status(self) -> dict[str, Any] | None:
        """UPnP event health statistics.

        Returns health tracking information if UPnP is enabled, None otherwise.

        Returns:
            Dictionary with health statistics:
            - is_healthy: bool - Whether UPnP events are working properly
            - miss_rate: float - Fraction of changes missed (0.0-1.0)
            - detected_changes: int - Total changes detected by polling
            - missed_changes: int - Changes polling saw but UPnP didn't
            - has_enough_samples: bool - Whether enough data for reliable health assessment

            None if UPnP is not enabled or health tracker not available.
        """
        return self._properties.upnp_health_status

    @property
    def upnp_is_healthy(self) -> bool | None:
        """Whether UPnP events are working properly.

        Returns:
            True if UPnP is healthy, False if degraded/failed, None if UPnP not enabled.
        """
        return self._properties.upnp_is_healthy

    @property
    def upnp_miss_rate(self) -> float | None:
        """UPnP event miss rate (0.0 = perfect, 1.0 = all missed).

        Returns:
            Fraction of changes missed by UPnP (0.0 to 1.0), or None if UPnP not enabled.
        """
        return self._properties.upnp_miss_rate

    # === Device Capabilities ===
    # These properties expose device capabilities for integrations (e.g., Home Assistant)
    # to check feature support before calling methods. Follows SoCo pattern.

    @property
    def supports_eq(self) -> bool:
        """Whether EQ control is supported."""
        return self._properties.supports_eq

    @property
    def supports_channel_balance(self) -> bool:
        """Whether stereo channel balance is supported (WiiM devices; probed at connect)."""
        return self._properties.supports_channel_balance

    @property
    def supports_presets(self) -> bool:
        """Whether preset/favorites are supported."""
        return self._properties.supports_presets

    @property
    def presets_full_data(self) -> bool:
        """Whether preset names/URLs are available (WiiM) or only count (LinkPlay).

        Returns:
            True if getPresetInfo works (WiiM devices) - can read preset names, URLs, etc.
            False if only preset_key available (LinkPlay devices) - only count available.
        """
        return self._properties.presets_full_data

    @property
    def supports_audio_output(self) -> bool:
        """Whether audio output mode control is supported."""
        return self._properties.supports_audio_output

    @property
    def supports_metadata(self) -> bool:
        """Whether metadata retrieval (getMetaInfo) is supported."""
        return self._properties.supports_metadata

    @property
    def supports_alarms(self) -> bool:
        """Whether alarm clock feature is supported."""
        return self._properties.supports_alarms

    @property
    def supports_sleep_timer(self) -> bool:
        """Whether sleep timer feature is supported."""
        return self._properties.supports_sleep_timer

    @property
    def supports_firmware_install(self) -> bool:
        """Whether firmware update installation via API is supported (WiiM devices only)."""
        return self._properties.supports_firmware_install

    @property
    def supports_led_control(self) -> bool:
        """Whether LED control is supported (primary setLED/setLEDBrightness API)."""
        return self._properties.supports_led_control

    @property
    def supports_led_switch(self) -> bool:
        """Whether Status Light (LED_SWITCH_SET) is supported."""
        return self._properties.supports_led_switch

    @property
    def supports_led_indicator(self) -> bool:
        """Whether LED indicator on/off is supported (ADR 005)."""
        return self._properties.supports_led_indicator

    @property
    def supports_display_config(self) -> bool:
        """Whether display/LCD on-off and brightness is supported (WiiM Ultra only)."""
        return self._properties.supports_display_config

    # === UPnP Capabilities ===

    @property
    def supports_upnp(self) -> bool:
        """Whether UPnP client is available for events and transport control."""
        return self._properties.supports_upnp

    @property
    def supports_queue_browse(self) -> bool:
        """Whether full queue retrieval is available (UPnP ContentDirectory).

        Only available on WiiM Amp and Ultra when a USB drive is connected.
        Most WiiM devices (Mini, Pro, Pro Plus) do not support this.
        """
        return self._properties.supports_queue_browse

    @property
    def supports_queue_add(self) -> bool:
        """Whether adding items to queue is supported (UPnP AVTransport).

        Available on most devices with UPnP support.
        """
        return self._properties.supports_queue_add

    @property
    def supports_queue_count(self) -> bool:
        """Whether queue count/position is available (HTTP API).

        Always True - available via plicount/plicurr in getPlayerStatus.
        """
        return self._properties.supports_queue_count

    @property
    def supports_next_track(self) -> bool:
        """Whether skip to next track is supported in current state.

        Returns True for most sources. Returns False for live radio streams
        and physical inputs (line-in, optical, etc.) where "next track" doesn't apply.

        IMPORTANT: Returns True even when queue_count is 0.
        Streaming services (Spotify, Amazon, etc.) manage their own queues
        and don't report via plicount, but next/previous commands still work.

        Home Assistant integrations should use this property for NEXT_TRACK feature,
        not queue_count which is unreliable for streaming services.
        """
        return self._properties.supports_next_track

    @property
    def supports_previous_track(self) -> bool:
        """Whether skip to previous track is supported in current state.

        Returns True for most sources. Returns False for live radio streams
        and physical inputs (line-in, optical, etc.) where "previous track" doesn't apply.

        IMPORTANT: Returns True even when queue_count is 0.
        Streaming services (Spotify, Amazon, etc.) manage their own queues
        and don't report via plicount, but next/previous commands still work.

        Home Assistant integrations should use this property for PREVIOUS_TRACK feature,
        not queue_count which is unreliable for streaming services.
        """
        return self._properties.supports_previous_track

    @property
    def supports_seek(self) -> bool:
        """Whether seeking within track is supported in current state.

        Returns False for live radio and physical inputs where seeking doesn't apply.
        """
        return self._properties.supports_seek

    # Aliases for WiiM HA integration compatibility (uses *_supported naming)
    @property
    def next_track_supported(self) -> bool:
        """Alias for supports_next_track (WiiM HA integration compatibility)."""
        return self._properties.next_track_supported

    @property
    def previous_track_supported(self) -> bool:
        """Alias for supports_previous_track (WiiM HA integration compatibility)."""
        return self._properties.previous_track_supported

    @property
    def seek_supported(self) -> bool:
        """Alias for supports_seek (WiiM HA integration compatibility)."""
        return self._properties.seek_supported

    @property
    def audio(self) -> AudioConfiguration:
        """Audio configuration manager.

        Provides access to audio-related methods:
        - select_output() - Select hardware output or Bluetooth device
        - set_source() - Set audio input source
        - set_audio_output_mode() - Set hardware output mode
        - set_led() - Control LED state
        - set_led_brightness() - Control LED brightness

        Returns:
            AudioConfiguration instance for audio control.
        """
        return self._audio_config


# Export Player class
__all__ = ["Player", "NotificationPlaybackResult"]
