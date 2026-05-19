"""Framework-agnostic polling strategy helpers for WiiM devices.

This module provides polling strategy recommendations and helpers for applications
managing their own polling loops. The strategy is based on the proven approach
used in the Home Assistant integration, but abstracted to be framework-agnostic.

Applications are responsible for managing their own polling loops. This module
provides recommendations for optimal intervals and conditional fetching logic.
"""

from __future__ import annotations

import time
from typing import Any

__all__ = [
    "PollingStrategy",
    "TrackChangeDetector",
    "fetch_parallel",
]


class PollingStrategy:
    """Polling strategy recommendations and helpers.

    This class provides framework-agnostic polling strategy recommendations
    based on device capabilities and state. Applications use these recommendations
    to manage their own polling loops.

    The strategy is based on a Tiered Polling approach:
    - **Tier 1 (Fast):** Playback status (Volume, Play State) - Poll every 1s.
    - **Tier 2 (Context):** Metadata, Output Mode - Poll on change/trigger.
    - **Tier 3 (Slow):** Device Info, Bluetooth, EQ - Poll rarely (60s+).

    **Per-Player Polling Principle:**
    Each player should be polled independently based on its own state. When managing
    multiple players:
    - Each player should have its own polling loop/coordinator
    - Each player should use its OWN `is_playing` state (not the group's or master's)
    - Idle players should use slower polling even if other players are playing
    - This prevents unnecessary fast polling of idle devices

    Example:
        ```python
        from pywiim import WiiMClient, PollingStrategy

        client = WiiMClient("192.168.1.100")
        capabilities = await client._detect_capabilities()
        strategy = PollingStrategy(capabilities)

        # Get recommended interval for THIS player
        role = "solo"
        is_playing = False  # THIS player's state, not the group's
        interval = strategy.get_optimal_interval(role, is_playing)
        print(f"Poll every {interval} seconds")

        # Check if Bluetooth/Device Info should be fetched (Lazy Polling)
        if strategy.should_fetch_configuration(last_config_fetch):
            await client.get_bluetooth_history()
        ```
    """

    # Polling interval constants (in seconds)
    FAST_POLL_INTERVAL = 1.0  # Active Playback / UI Responsiveness
    NORMAL_POLL_INTERVAL = 5.0  # Idle / Background
    CONFIGURATION_INTERVAL = 60.0  # Bluetooth, EQ presets, device info
    # Faster tier for user-toggled hardware (12V trigger, subwoofer) — light GETs, visible in HA/monitor
    HARDWARE_STATUS_INTERVAL = 15.0
    METADATA_CHECK_INTERVAL = 1.0  # Check for track changes

    # Legacy device intervals (longer for older devices)
    LEGACY_FAST_POLL_INTERVAL = 3.0  # Legacy devices during playback
    LEGACY_NORMAL_POLL_INTERVAL = 15.0  # Legacy devices when idle
    LEGACY_SLAVE_INTERVAL = 10.0  # Legacy slaves

    def __init__(self, capabilities: dict[str, Any]) -> None:
        """Initialize polling strategy with device capabilities.

        Args:
            capabilities: Device capabilities dictionary from capability detection.
        """
        self.capabilities = capabilities
        self._last_playing_time: float = 0.0  # Initialize to 0 (far in past) so startup uses normal polling

    def get_optimal_interval(
        self,
        role: str,
        is_playing: bool,
    ) -> float:
        """Get optimal polling interval based on device capabilities and state.

        **IMPORTANT: This method is per-player. Each player should be polled independently
        based on its own state, not the group's state.**

        The interval adapts based on:
        - Device type (WiiM vs Legacy)
        - Device role (master/slave/solo)
        - Playback state (playing vs idle) - **THIS player's state, not the group's**

        **Multi-Player Polling:**
        - Each player should have its own polling loop/coordinator
        - Each player should call this method with its OWN `is_playing` state
        - Do NOT use the master's playing state for all players in a group
        - Idle players should use slower polling even if other players are playing

        Args:
            role: Device role ("master", "slave", or "solo")
            is_playing: Whether **THIS device** is currently playing (not the group)

        Returns:
            Recommended polling interval in seconds
        """
        # Update last playing time
        if is_playing:
            self._last_playing_time = time.time()

        if self.capabilities.get("is_legacy_device", False):
            # Legacy devices need longer intervals
            if role == "slave":
                return self.LEGACY_SLAVE_INTERVAL
            elif is_playing:
                return self.LEGACY_FAST_POLL_INTERVAL
            else:
                return self.LEGACY_NORMAL_POLL_INTERVAL
        else:
            # Modern WiiM devices
            if role == "slave":
                # Slaves always follow master - check less frequently
                return self.NORMAL_POLL_INTERVAL  # 5 seconds

            if is_playing:
                # Playing: Fast poll for UI responsiveness
                return self.FAST_POLL_INTERVAL  # 1 second

            # Not playing: Check "Active Idle" window
            time_since_playing = time.time() - self._last_playing_time
            if time_since_playing < 30:  # 30 seconds
                # Active Idle: Recently paused, stay fast to catch resumed playback quickly
                return self.FAST_POLL_INTERVAL  # 1 second

            # Deep Idle: Not played for > 30 seconds
            return self.NORMAL_POLL_INTERVAL  # 5 seconds

    def should_fetch_configuration(
        self,
        last_fetch_time: float,
        force_refresh: bool = False,
        now: float | None = None,
    ) -> bool:
        """Check if configuration (Bluetooth, Device Info, EQ) should be fetched.

        Configuration data is static or low-volatility. Fetch rarely (every 60s)
        or on explicit triggers (force_refresh).

        Args:
            last_fetch_time: Timestamp of last configuration fetch
            force_refresh: Whether to force a refresh (e.g. user action)
            now: Current time (defaults to time.time())

        Returns:
            True if configuration should be fetched
        """
        if force_refresh:
            return True

        if now is None:
            now = time.time()

        # Always fetch on first check (None or 0 means never fetched)
        if last_fetch_time is None or last_fetch_time == 0:
            return True

        return (now - last_fetch_time) >= self.CONFIGURATION_INTERVAL

    def should_fetch_metadata(
        self,
        track_changed: bool,
        metadata_supported: bool | None,
    ) -> bool:
        """Check if metadata (Bitrate, Sample Rate) should be fetched.

        Metadata is only fetched when:
        - Track has changed (title, artist, source, artwork)
        - Device supports metadata endpoint

        Args:
            track_changed: Whether track has changed since last check
            metadata_supported: Whether device supports metadata endpoint

        Returns:
            True if metadata should be fetched
        """
        if metadata_supported is False:
            return False  # Endpoint not supported

        return track_changed

    def should_fetch_audio_output(
        self,
        last_fetch_time: float,
        source_changed: bool,
        audio_output_supported: bool | None,
        now: float | None = None,
    ) -> bool:
        """Check if audio output status should be fetched.

        Fetch logic:
        1. On Startup (last_fetch_time == 0)
        2. If Source Changed (Bluetooth -> Wifi)
        3. Every 60s (Background consistency)

        Args:
            last_fetch_time: Timestamp of last audio output fetch
            source_changed: Whether the input source has changed
            audio_output_supported: Whether device supports audio output endpoint
            now: Current time (defaults to time.time())

        Returns:
            True if audio output status should be fetched
        """
        if audio_output_supported is False:
            return False  # Endpoint not supported

        if source_changed:
            return True

        if now is None:
            now = time.time()

        # Always fetch on first check
        if last_fetch_time == 0:
            return True

        # Fallback: Consistency check every 60s
        return (now - last_fetch_time) >= self.CONFIGURATION_INTERVAL

    def should_fetch_eq_info(
        self,
        last_fetch_time: float,
        eq_supported: bool | None,
        now: float | None = None,
    ) -> bool:
        """Check if EQ info should be fetched.

        Fetch logic:
        1. On Startup (last_fetch_time == 0)
        2. Every 60s (Background consistency)
        3. Only if device supports EQ

        Args:
            last_fetch_time: Timestamp of last EQ info fetch
            eq_supported: Whether device supports EQ endpoint
            now: Current time (defaults to time.time())

        Returns:
            True if EQ info should be fetched
        """
        if eq_supported is False:
            return False  # Endpoint not supported

        if now is None:
            now = time.time()

        # Always fetch on first check (None or 0 means never fetched)
        if last_fetch_time is None or last_fetch_time == 0:
            return True

        # Fetch every 60s
        return (now - last_fetch_time) >= self.CONFIGURATION_INTERVAL

    def should_fetch_presets(
        self,
        last_fetch_time: float,
        presets_supported: bool | None,
        now: float | None = None,
    ) -> bool:
        """Check if preset stations should be fetched.

        Fetch logic:
        1. On Startup (last_fetch_time == 0)
        2. Every 60s (Background consistency)
        3. Only if device supports presets

        Args:
            last_fetch_time: Timestamp of last presets fetch
            presets_supported: Whether device supports presets endpoint
            now: Current time (defaults to time.time())

        Returns:
            True if presets should be fetched
        """
        if presets_supported is False:
            return False  # Endpoint not supported

        if now is None:
            now = time.time()

        # Always fetch on first check (None or 0 means never fetched)
        if last_fetch_time is None or last_fetch_time == 0:
            return True

        # Fetch every 60s
        return (now - last_fetch_time) >= self.CONFIGURATION_INTERVAL

    def should_fetch_subwoofer(
        self,
        last_fetch_time: float,
        subwoofer_supported: bool | None,
        now: float | None = None,
    ) -> bool:
        """Check if subwoofer status should be fetched.

        Fetch logic:
        1. On Startup (last_fetch_time == 0)
        2. Every 60s (Background consistency)
        3. Only if device supports subwoofer (WiiM Ultra with firmware 5.2+)

        Args:
            last_fetch_time: Timestamp of last subwoofer status fetch
            subwoofer_supported: True if supported, False if not, None if capability probe was inconclusive
            now: Current time (defaults to time.time())

        Returns:
            True if subwoofer status should be fetched
        """
        if subwoofer_supported is False:
            return False  # Endpoint not supported

        if now is None:
            now = time.time()

        # Always fetch on first check (None or 0 means never fetched)
        if last_fetch_time is None or last_fetch_time == 0:
            return True

        # Fetch every 60s
        return (now - last_fetch_time) >= self.CONFIGURATION_INTERVAL

    def should_fetch_trigger_out(
        self,
        last_fetch_time: float,
        trigger_out_supported: bool,
        now: float | None = None,
    ) -> bool:
        """Check if 12V trigger status should be fetched.

        Fetch logic:
        1. On startup (last_fetch_time == 0)
        2. Every 60s (background consistency)
        3. Only if device supports 12V trigger (static model class)

        Args:
            last_fetch_time: Timestamp of last trigger status fetch
            trigger_out_supported: From capabilities["supports_trigger_out"]
            now: Current time (defaults to time.time())

        Returns:
            True if trigger status should be fetched
        """
        if not trigger_out_supported:
            return False

        if now is None:
            now = time.time()

        if last_fetch_time is None or last_fetch_time == 0:
            return True

        return (now - last_fetch_time) >= self.CONFIGURATION_INTERVAL

    def should_fetch_led_indicator(
        self,
        last_fetch_time: float,
        led_supported: bool,
        now: float | None = None,
    ) -> bool:
        """Check if status LED (LED indicator) state should be fetched.

        Same cadence as other configuration-tier hardware reads (~60s).
        """
        if not led_supported:
            return False

        if now is None:
            now = time.time()

        if last_fetch_time is None or last_fetch_time == 0:
            return True

        return (now - last_fetch_time) >= self.CONFIGURATION_INTERVAL

    def should_fetch_device_info(
        self,
        last_fetch_time: float,
        now: float | None = None,
    ) -> bool:
        """Check if device info should be fetched.

        Fetch logic:
        1. On Startup (last_fetch_time == 0)
        2. Every 60s (Background consistency)

        Args:
            last_fetch_time: Timestamp of last device info fetch
            now: Current time (defaults to time.time())

        Returns:
            True if device info should be fetched
        """
        if now is None:
            now = time.time()

        # Always fetch on first check (None or 0 means never fetched)
        if last_fetch_time is None or last_fetch_time == 0:
            return True

        # Fetch every 60s
        return (now - last_fetch_time) >= self.CONFIGURATION_INTERVAL

    def should_fetch_multiroom(
        self,
        last_fetch_time: float,
        now: float | None = None,
    ) -> bool:
        """Check if multiroom info should be fetched.

        Fetch logic:
        1. On Startup (last_fetch_time == 0)
        2. Every 15s (More frequent than configuration data)

        Args:
            last_fetch_time: Timestamp of last multiroom fetch
            now: Current time (defaults to time.time())

        Returns:
            True if multiroom info should be fetched
        """
        if now is None:
            now = time.time()

        # Always fetch on first check
        if last_fetch_time == 0:
            return True

        # Fetch every 15s (more frequent than configuration)
        MULTIROOM_INTERVAL = 15.0
        return (now - last_fetch_time) >= MULTIROOM_INTERVAL


class TrackChangeDetector:
    """Detect track changes for metadata fetching.

    This helper tracks track metadata (title, artist, source, artwork) to
    detect when a track has changed. This is used to determine when metadata
    should be fetched (only on track changes, not every poll cycle).

    Example:
        ```python
        detector = TrackChangeDetector()

        # Check if track changed
        if detector.track_changed(title, artist, source, artwork):
            # Fetch metadata
            metadata = await client.get_meta_info()
        ```
    """

    def __init__(self) -> None:
        """Initialize track change detector."""
        self._last_track_info: tuple[str, str, str, str] | None = None

    def track_changed(
        self,
        title: str | None,
        artist: str | None,
        source: str | None,
        artwork: str | None,
    ) -> bool:
        """Check if track has changed.

        Args:
            title: Current track title
            artist: Current track artist
            source: Current source
            artwork: Current artwork URL

        Returns:
            True if track changed, False otherwise
        """
        current = (
            title or "",
            artist or "",
            source or "",
            artwork or "",
        )

        if self._last_track_info is None:
            self._last_track_info = current
            return True  # First time, consider it changed

        changed = current != self._last_track_info
        if changed:
            self._last_track_info = current

        return changed

    def reset(self) -> None:
        """Reset track change detector (clear last track info)."""
        self._last_track_info = None


async def fetch_parallel(
    *tasks: Any,
    return_exceptions: bool = True,
) -> list[Any]:
    """Execute multiple fetch tasks in parallel.

    This helper executes multiple async tasks in parallel using asyncio.gather.
    It's useful for conditional fetching where multiple endpoints may be fetched
    in the same poll cycle.

    Args:
        *tasks: Async tasks to execute
        return_exceptions: If True, return exceptions in results instead of raising

    Returns:
        List of results (or exceptions if return_exceptions=True)

    Example:
        ```python
        tasks = []
        tasks.append(client.get_player_status())

        if strategy.should_fetch_device_info(last_device_info):
            tasks.append(client.get_device_info_model())

        results = await fetch_parallel(*tasks)
        ```
    """
    import asyncio

    return await asyncio.gather(*tasks, return_exceptions=return_exceptions)
