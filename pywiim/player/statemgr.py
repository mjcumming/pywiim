"""State management - refresh, UPnP integration, state synchronization.

# pragma: allow-long-file statemgr-cohesive
# This file exceeds the 600 LOC hard limit (643 lines) but is kept as a single
# cohesive unit because:
# 1. Single responsibility: Player state management, refresh, and UPnP integration
# 2. Well-organized: Clear sections for refresh logic, state synchronization, and UPnP handling
# 3. Tight coupling: All methods work together for state management
# 4. Maintainable: Clear structure, follows state management design pattern
# 5. Natural unit: Represents one concept (player state management)
# Splitting would add complexity without clear benefit.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

import aiohttp

from ..api.constants import MODE_MAP
from ..exceptions import WiiMTimeoutError
from ..metadata import is_valid_metadata_value
from ..polling import PollingStrategy
from ..state import PLAYING_STATES, normalize_play_state
from .debounce import PlayStateDebouncer
from .stream_enricher import StreamEnricher

if TYPE_CHECKING:
    from ..models import DeviceInfo, PlayerStatus
    from . import Player

_LOGGER = logging.getLogger(__name__)

# UPnP retry cooldown - wait this many seconds between failed creation attempts
UPNP_RETRY_COOLDOWN = 60.0

# Standard sources that shouldn't be cleared when checking for multiroom/master names
STANDARD_SOURCES = {
    "spotify",
    "tidal",
    "amazon",
    "qobuz",
    "deezer",
    "wifi",
    "bluetooth",
    "linein",
    "coax",
    "optical",
    "usb",
    "airplay",
    "dlna",
    "unknown",
}


class StateManager:
    """Manages player state refresh and UPnP integration."""

    def __init__(self, player: Player) -> None:
        """Initialize state manager.

        Args:
            player: Parent Player instance.
        """
        self.player = player

        # Play state debouncing to smooth track changes
        self._play_state_debouncer = PlayStateDebouncer(player)

        # Stream enrichment for raw URL playback
        self._stream_enricher = StreamEnricher(player)

        # Track last EQ preset to detect changes (trigger full EQ info fetch)
        self._last_eq_preset: str | None = None

        # Track last source to detect source changes (for audio output fetching)
        self._last_source: str | None = None

        # Polling strategy for periodic fetching decisions
        self._polling_strategy: PollingStrategy | None = None

    def apply_diff(self, changes: dict[str, Any]) -> bool:
        """Apply state changes from UPnP events.

        Args:
            changes: Dictionary with state fields from UPnP event.

        Returns:
            True if state changed, False otherwise.
        """
        if not changes:
            return False

        # Track if state actually changed
        old_state = {
            "play_state": self.player.play_state,
            "volume": self.player.volume_level,
            "muted": self.player.is_muted,
            "title": self.player.media_title,
            "position": self.player.media_position,
        }
        old_play_state = old_state["play_state"]

        # Update from UPnP
        self.update_from_upnp(changes)

        # Check if state changed
        new_state = {
            "play_state": self.player.play_state,
            "volume": self.player.volume_level,
            "muted": self.player.is_muted,
            "title": self.player.media_title,
            "position": self.player.media_position,
        }
        new_play_state = new_state["play_state"]

        # Handle position timer based on play state changes
        if old_play_state != new_play_state:
            # Check if transitioning from playing to paused/stopped
            was_playing = old_play_state and any(s in str(old_play_state).lower() for s in PLAYING_STATES)
            is_playing = new_play_state and any(s in str(new_play_state).lower() for s in PLAYING_STATES)

            _LOGGER.info(
                "🎵 Play state changed: %s -> %s (was_playing=%s, is_playing=%s)",
                old_play_state,
                new_play_state,
                was_playing,
                is_playing,
            )

        return old_state != new_state

    def update_from_upnp(self, data: dict[str, Any]) -> None:
        """Update state from UPnP event data.

        Args:
            data: Dictionary with state fields from UPnP event.
        """
        # SLAVE RULE (strict):
        # In slave mode we NEVER accept slave-local playback/metadata (HTTP or UPnP).
        # Slaves only contribute their own volume/mute. All playback + media metadata
        # must come from the master via propagation; if master has no data, there is no data.
        #
        # This prevents transient/incorrect slave UPnP metadata (common during source switches)
        # from overwriting propagated master state.
        if self.player.is_slave:
            # Normalize mute key if needed
            if "muted" not in data and "mute" in data:
                data = dict(data)
                data["muted"] = data.get("mute")

            allowed_keys = {"volume", "muted"}
            filtered = {k: v for k, v in data.items() if k in allowed_keys}
            if not filtered:
                return
            data = filtered

        # Handle debounce for play state to smooth track changes
        # Devices often report STOPPED/PAUSED briefly between tracks
        if "play_state" in data:
            raw_state = data["play_state"]

            new_state = normalize_play_state(raw_state)
            current_state = self.player.play_state

            # Check if currently playing (or loading/transitioning)
            is_playing = current_state and any(s in str(current_state).lower() for s in PLAYING_STATES)

            # Check if new state is pause/stop or buffering
            # We debounce buffering too, to avoid UI flashes during track transitions
            is_interruption = new_state is not None and new_state in ("pause", "stop", "idle", "buffering")

            if is_playing and is_interruption and new_state is not None:
                # Transitioning Play -> Pause/Buffering: Debounce it
                # Don't apply play_state immediately, schedule it
                self._play_state_debouncer.schedule_state_change(new_state)

                # Make a copy without play_state to apply other changes immediately
                data_copy = data.copy()
                del data_copy["play_state"]
                self.player._state_synchronizer.update_from_upnp(data_copy)
                return

            elif new_state in ("play", "playing"):
                # Transitioning to Play: Cancel any pending state update and apply immediately
                self._play_state_debouncer.cancel_pending()
                _LOGGER.debug("Track change detected (Play -> Play), cancelled pending state update")

        self.player._state_synchronizer.update_from_upnp(data)

        # Update UPnP health tracker with UPnP event data
        if self.player._upnp_health_tracker:
            # Convert volume to int (0-100) if it's a float (0.0-1.0)
            volume = data.get("volume")
            if isinstance(volume, float) and 0.0 <= volume <= 1.0:
                volume = int(volume * 100)
            elif volume is not None:
                volume = int(volume)

            upnp_state = {
                "play_state": data.get("play_state"),
                "volume": volume,
                "muted": data.get("muted"),
                "title": data.get("title"),
                "artist": data.get("artist"),
                "album": data.get("album"),
            }
            self.player._upnp_health_tracker.on_upnp_event(upnp_state)

        # Get merged state and update cached models
        # CRITICAL: Always get fresh merged state after UPnP update to ensure
        # properties are updated before callbacks fire
        merged = self.player._state_synchronizer.get_merged_state()

        # Update cached status_model with merged state
        # IMPORTANT: Update ALL fields from merged state, not just changed ones.
        # This ensures properties (media_title, media_artist, etc.) are current
        # when callbacks fire, even if the UPnP event didn't include metadata.
        if self.player._status_model:
            # Update fields from merged state (always update, even if None)
            for field_name in ["play_state", "position", "duration", "source"]:
                if field_name in merged:
                    setattr(self.player._status_model, field_name, merged.get(field_name))

            # Update volume and mute
            if "volume" in merged:
                vol = merged.get("volume")
                if vol is not None:
                    if isinstance(vol, float) and 0.0 <= vol <= 1.0:
                        self.player._status_model.volume = int(vol * 100)
                    else:
                        self.player._status_model.volume = int(vol)
                # Note: We don't set to None here to preserve existing value if merged state has None

            if "muted" in merged:
                muted_val = merged.get("muted")
                if muted_val is not None:
                    self.player._status_model.mute = muted_val

            # Update metadata - ALWAYS update from merged state to ensure
            # properties reflect latest data when callbacks fire
            for field_name in ["title", "artist", "album"]:
                if field_name in merged:
                    # Always update, even if None (merged state is source of truth)
                    setattr(self.player._status_model, field_name, merged.get(field_name))

            if "image_url" in merged:
                image_url = merged.get("image_url")
                self.player._status_model.entity_picture = image_url
                self.player._status_model.cover_url = image_url

        # Detect track changes and fetch artwork immediately if missing.
        # Compute the edge synchronously here (single latch consumer for this UPnP-event
        # wave) and pass it into the deferred task, so a concurrent poll's
        # check_track_changed can't swallow the edge before the task runs.
        try:
            loop = asyncio.get_event_loop()
            upnp_track_changed = self.player._coverart_mgr.check_track_changed(merged)
            loop.create_task(
                self.player._coverart_mgr.enrich_metadata_on_track_change(merged, track_changed=upnp_track_changed)
            )
        except RuntimeError:
            # No event loop (sync context) - will fetch on next poll
            _LOGGER.debug("No event loop available, metadata enrichment will be fetched on next poll")

        # If this is a master, propagate metadata to all linked slaves
        if self.player.is_master and self.player._group and self.player._group.slaves:
            self.player._group_ops.propagate_metadata_to_slaves()

    async def refresh(self, full: bool = False) -> None:
        """Refresh cached state from device.

        Args:
            full: If True, perform a full refresh including expensive endpoints (device info, EQ, BT).
                 If False (default), only fetch fast-changing status data (volume, playback).

        Note:
            On first refresh (when _last_refresh is None), automatically performs a full refresh
            to ensure all state is populated (device info, EQ presets, audio output, etc.).

        Slave Optimization:
            For slave devices in multi-room groups, we only fetch device status (getStatusEx),
            not player status. Playback state (track, position, etc.) comes from the master
            via propagation. This reduces API calls and avoids issues with devices that don't
            respond to player status requests when in slave mode.
        """
        # CRITICAL: On startup (first refresh), always do a full refresh
        # This ensures the player is "ready for use" with all properties populated
        if self.player._last_refresh is None:
            full = True

        try:
            # Start UPnP client creation in background (non-blocking)
            # This avoids blocking refresh() for 5+ seconds during UPnP init.
            # UPnP will be available for metadata/events once creation completes.
            # If it fails, we retry after UPNP_RETRY_COOLDOWN seconds.
            now = time.time()
            if not self.player._upnp_client:
                time_since_last_attempt = now - self.player._last_upnp_attempt
                if time_since_last_attempt >= UPNP_RETRY_COOLDOWN:
                    asyncio.create_task(self.player._ensure_upnp_client())

            # Core refresh - behavior depends on role (from previous cycle)
            # Slaves: getStatusEx (volume, mute, group) - playback comes from master
            # Masters/Solo: getPlayerStatusEx (full playback state)
            status = await self._refresh_core_status()

            # Detect the track-change edge ONCE per refresh. check_track_changed mutates
            # a single-shot latch (_last_track_signature); calling it from more than one
            # consumer in the same cycle lets the first caller swallow the edge and starves
            # the rest (this is what silently disabled the stale-artwork refresh). Compute
            # it here and thread the value through every consumer below.
            merged_for_track = self.player._state_synchronizer.get_merged_state()
            track_changed = self.player._coverart_mgr.check_track_changed(merged_for_track)

            # Device info - only on full refresh or first time (not needed every poll)
            if full or self.player._device_info is None:
                await self._refresh_device_info()
                # If the full refresh just established a new profile that prefers UPnP for source,
                # _refresh_core_status() ran before the profile was set and skipped
                # GetControlDeviceInfo. Re-seed the source now that the profile is known.
                await self._seed_source_after_profile()

            # Trigger-based fetching (skip for slaves - they get data from master)
            if not self.player.is_slave:
                await self._handle_triggers(status, track_changed)

            # Periodic data refresh (skip expensive endpoints for slaves)
            await self._refresh_periodic_data(full, status, track_changed)

            # Finalize (includes role detection for NEXT cycle)
            await self._finalize_refresh(track_changed)

        except Exception as err:
            self._handle_refresh_error(err)

    async def _refresh_core_status(self) -> PlayerStatus:
        """Fetch core player status and update state synchronizer.

        For slaves in multi-room groups, we use getStatusEx (device status) instead of
        getPlayerStatusEx. Playback state (track, position, etc.) comes from the master
        via propagation. We only need volume/mute/group from slaves.

        Returns:
            PlayerStatus model from device.
        """
        # SLAVE OPTIMIZATION: Use capability-configured status endpoint for slaves
        # Slaves get playback state from master via propagation. We only need:
        # - Volume/mute (can be independent per-slave)
        # - Group membership (to detect if we leave the group)
        #
        # Note: HCN_BWD03 slaves in multiroom mode don't respond to getPlayerStatus
        # (timeout). Fall back to getStatusEx which works for these devices.

        if self.player.is_slave:
            try:
                status_dict = await self.player.client.get_player_status()
            except (TimeoutError, WiiMTimeoutError, aiohttp.ServerTimeoutError):
                # HCN_BWD03 slaves in multiroom mode timeout on getPlayerStatus
                # Fall back to getStatusEx which works for these devices
                device_type = self.player.client._capabilities.get("device_type", "")
                if device_type == "HCN_BWD03":
                    _LOGGER.debug(
                        "HCN_BWD03 slave %s: getPlayerStatus timed out in multiroom mode, falling back to getStatusEx",
                        self.player.host,
                    )
                    status_dict = await self.player.client.get_status()
                else:
                    # Re-raise timeout for other devices
                    raise

            # Get existing status model to preserve playback fields from master propagation
            status = self.player._status_model
            if status is None:
                from ..models import PlayerStatus

                status = PlayerStatus.model_construct()  # Empty status, fields populated below

            # Update volume/mute/group from device status (these are slave-specific)
            if "volume" in status_dict:
                vol = status_dict.get("volume")
                if vol is not None:
                    status.volume = int(vol) if not isinstance(vol, int) else vol
            if "mute" in status_dict:
                status.mute = status_dict.get("mute")
            if "group" in status_dict:
                status.group = status_dict.get("group")

            # Try UPnP for more accurate volume (slaves can have independent volume)
            # Skip if UPnP is marked unhealthy to avoid stressing the device's UPnP server
            # during mode/source transitions. See: https://github.com/mjcumming/wiim/issues/157
            if (
                self.player._upnp_client
                and self.player._upnp_client.rendering_control
                and self.player.upnp_is_healthy is not False
            ):
                try:
                    volume_from_upnp = await self.player._upnp_client.get_volume()
                    mute_from_upnp = await self.player._upnp_client.get_mute()
                    if volume_from_upnp is not None:
                        status.volume = volume_from_upnp
                    if mute_from_upnp is not None:
                        status.mute = mute_from_upnp
                except Exception as err:
                    _LOGGER.debug("UPnP GetVolume failed for slave %s: %s", self.player.host, err)

            self.player._status_model = status
            self.player._last_refresh = time.time()
            self.player._available = True
            return status

        # MASTERS/SOLO: Full player status polling (getPlayerStatusEx)
        status = await self.player.client.get_player_status_model()

        # Try UPnP GetVolume first if available, fallback to HTTP
        # Skip if UPnP is marked unhealthy to avoid stressing the device's UPnP server
        # during mode/source transitions. See: https://github.com/mjcumming/wiim/issues/157
        upnp_volume: int | None = None
        upnp_mute: bool | None = None
        upnp_source: str | None = None

        if (
            self.player._upnp_client
            and self.player._upnp_client.rendering_control
            and self.player.upnp_is_healthy is not False
        ):
            try:
                upnp_volume = await self.player._upnp_client.get_volume()
                upnp_mute = await self.player._upnp_client.get_mute()
                _LOGGER.debug(
                    "Got volume from UPnP for %s: volume=%s, mute=%s",
                    self.player.client.host,
                    upnp_volume,
                    upnp_mute,
                )
            except Exception as err:
                _LOGGER.debug(
                    "UPnP GetVolume failed for %s: %s (falling back to HTTP)",
                    self.player.client.host,
                    err,
                )

            # Poll source via GetControlDeviceInfo for devices that prefer UPnP for source
            # (e.g. Audio Pro MkII: HTTP getStatusEx returns mode=0 when idle, masking actual input).
            # Skip when HTTP already returned a valid streaming source to avoid an unnecessary round-trip.
            http_source = status.source if status else None
            if (
                self.player._profile is not None
                and self.player._profile.state_sources.source == "upnp"
                and http_source in (None, "idle")
            ):
                try:
                    info = await self.player._upnp_client.get_control_device_info()
                    play_mode = info.get("PlayMode")
                    if play_mode is not None:
                        mapped = MODE_MAP.get(str(play_mode))
                        if mapped and mapped != "idle":
                            upnp_source = mapped
                            _LOGGER.debug(
                                "Got source from UPnP GetControlDeviceInfo for %s: PlayMode=%s -> %s",
                                self.player.client.host,
                                play_mode,
                                upnp_source,
                            )
                except Exception as err:
                    _LOGGER.debug(
                        "UPnP GetControlDeviceInfo failed for %s: %s",
                        self.player.client.host,
                        err,
                    )

        # Update StateSynchronizer with HTTP data
        status_dict = status.model_dump(exclude_none=False) if status else {}
        if "entity_picture" in status_dict:
            status_dict["image_url"] = status_dict.pop("entity_picture")
        for field_name in ["title", "artist", "album", "image_url"]:
            if field_name not in status_dict:
                status_dict[field_name] = None

        # Override volume/mute/source with UPnP values if available (UPnP preferred)
        if upnp_volume is not None:
            status_dict["volume"] = upnp_volume
        if upnp_mute is not None:
            status_dict["muted"] = upnp_mute
        if upnp_source is not None:
            status_dict["source"] = upnp_source

        self.player._state_synchronizer.update_from_http(status_dict)

        # Update UPnP health tracker with HTTP poll data
        if self.player._upnp_health_tracker:
            # Convert volume to int (0-100) if it's a float (0.0-1.0)
            volume = status_dict.get("volume")
            if isinstance(volume, float) and 0.0 <= volume <= 1.0:
                volume = int(volume * 100)
            elif volume is not None:
                volume = int(volume)

            poll_state = {
                "play_state": status_dict.get("play_state"),
                "volume": volume,
                "muted": status_dict.get("muted"),
                "title": status_dict.get("title"),
                "artist": status_dict.get("artist"),
                "album": status_dict.get("album"),
            }
            self.player._upnp_health_tracker.on_poll_update(poll_state)

        # Preserve optimistic source if new status doesn't have one (e.g., when mode=0 is ignored)
        # This prevents optimistic sources set by set_source() from being cleared when device reports mode=0
        # See: https://github.com/mjcumming/wiim/issues/138
        if status and not status.source and self.player._status_model and self.player._status_model.source:
            # Preserve existing source - device may have reported mode=0 which correctly doesn't set source="idle"
            # but we should keep the optimistic source that was set by set_source()
            status.source = self.player._status_model.source

        # Preserve optimistic source if it was recently set
        # Device status endpoint may return stale source data after a switch
        source_preservation_window = 5.0  # seconds to preserve optimistic source
        if (
            status
            and self.player._status_model
            and self.player._status_model.source
            and self.player._last_source_set_time > 0
            and (time.time() - self.player._last_source_set_time) < source_preservation_window
        ):
            # Recently set source via set_source() - preserve the optimistic value
            status.source = self.player._status_model.source

        # Preserve optimistic EQ preset if it was recently set
        # Device status endpoint returns stale EQ data for a long time after a change
        # (sometimes 30+ seconds). This prevents refresh() from overwriting the correct
        # optimistic value with stale data.
        eq_preservation_window = 60.0  # seconds to preserve optimistic EQ preset
        if (
            status
            and self.player._status_model
            and self.player._status_model.eq_preset
            and self.player._last_eq_preset_set_time > 0
            and (time.time() - self.player._last_eq_preset_set_time) < eq_preservation_window
        ):
            # Recently set EQ preset via set_eq_preset() - preserve the optimistic value
            status.eq_preset = self.player._status_model.eq_preset

        # Preserve optimistic loop_mode (shuffle/repeat) if it was recently set
        # Device status endpoint may return stale loop_mode data after a change.
        loop_mode_preservation_window = 60.0  # seconds to preserve optimistic loop_mode
        if (
            status
            and self.player._status_model
            and self.player._status_model.loop_mode is not None
            and self.player._last_loop_mode_set_time > 0
            and (time.time() - self.player._last_loop_mode_set_time) < loop_mode_preservation_window
        ):
            # Recently set loop_mode via set_shuffle()/set_repeat() - preserve the optimistic value
            status.loop_mode = self.player._status_model.loop_mode

        self.player._status_model = status

        # Update state synchronizer with preserved optimistic values
        # This ensures the synchronizer (which properties read from) has the correct optimistic state
        # even if the HTTP poll returned stale data
        optimistic_updates = {}
        if (
            status
            and self.player._status_model
            and self.player._status_model.source
            and self.player._last_source_set_time > 0
            and (time.time() - self.player._last_source_set_time) < source_preservation_window
        ):
            # Update synchronizer with preserved optimistic source
            optimistic_updates["source"] = self.player._status_model.source

        if (
            status
            and self.player._status_model
            and self.player._status_model.eq_preset
            and self.player._last_eq_preset_set_time > 0
            and (time.time() - self.player._last_eq_preset_set_time) < eq_preservation_window
        ):
            # Update synchronizer with preserved optimistic EQ preset
            optimistic_updates["eq_preset"] = self.player._status_model.eq_preset

        if optimistic_updates:
            # Update state synchronizer with preserved optimistic values
            # Use source="optimistic" to distinguish from HTTP polling data
            self.player._state_synchronizer.update_from_http(optimistic_updates, source="optimistic")

        # Enrich metadata if playing a stream
        await self._stream_enricher.enrich_if_needed(status)

        self.player._last_refresh = time.time()
        self.player._available = True

        return status

    async def _refresh_device_info(self) -> None:
        """Fetch device info and update profile."""
        device_info = await self.player.client.get_device_info_model()
        self.player._device_info = device_info
        # Update device profile when device_info changes
        self.player._update_profile_from_device_info()

    async def _seed_source_after_profile(self) -> None:
        """Seed source via GetControlDeviceInfo after profile is established on full refresh.

        _refresh_core_status() runs before device info is fetched, so on the initial full
        refresh the profile isn't set yet and GetControlDeviceInfo is skipped. This method
        re-runs the source poll once the profile is known, so the source is correct
        immediately after startup rather than waiting for the first incremental refresh.
        """
        if (
            self.player._profile is None
            or self.player._profile.state_sources.source != "upnp"
            or not self.player._upnp_client
            or not self.player._upnp_client.rendering_control
            or self.player.source not in (None, "idle")
        ):
            return

        try:
            info = await self.player._upnp_client.get_control_device_info()
            play_mode = info.get("PlayMode")
            if play_mode is not None:
                mapped = MODE_MAP.get(str(play_mode))
                if mapped and mapped != "idle":
                    self.player._state_synchronizer.update_from_http({"source": mapped})
                    _LOGGER.debug(
                        "Seeded source from GetControlDeviceInfo after profile set for %s: PlayMode=%s -> %s",
                        self.player.client.host,
                        play_mode,
                        mapped,
                    )
        except Exception as err:
            _LOGGER.debug(
                "GetControlDeviceInfo source seed failed for %s: %s",
                self.player.client.host,
                err,
            )

    async def _handle_triggers(self, status: PlayerStatus, track_changed: bool) -> None:
        """Handle trigger-based fetching (track change, source change, EQ change).

        Args:
            status: Current player status.
            track_changed: Whether the track changed this refresh cycle (computed once
                by :meth:`refresh` and shared across all consumers).
        """
        # Initialize polling strategy if needed (uses device capabilities)
        if self._polling_strategy is None:
            self._polling_strategy = PollingStrategy(self.player.client.capabilities)

        # Detect EQ preset change (trigger full EQ info fetch)
        current_eq_preset = status.eq_preset if status else None
        eq_preset_changed = self._last_eq_preset is not None and current_eq_preset != self._last_eq_preset
        # Initialize on first run (don't trigger fetch on first detection)
        if self._last_eq_preset is None:
            self._last_eq_preset = current_eq_preset
        elif eq_preset_changed:
            self._last_eq_preset = current_eq_preset

        # Detect source change (trigger audio output fetch)
        current_source = status.source if status else None
        source_changed = self._last_source is not None and current_source != self._last_source
        # Initialize on first run
        if self._last_source is None:
            self._last_source = current_source
        elif source_changed:
            self._last_source = current_source

        # Check if we need to enrich metadata (title/artist are Unknown - common with Bluetooth AVRCP)
        status_title = status.title if status else None
        status_artist = status.artist if status else None
        needs_metadata_enrichment = (not is_valid_metadata_value(status_title)) or (
            not is_valid_metadata_value(status_artist)
        )

        if track_changed or needs_metadata_enrichment:
            # Track changed OR metadata needs enrichment (Bluetooth AVRCP case)
            try:
                metadata = await self.player.client.get_meta_info()
                self.player._metadata = metadata if metadata else None
                # Track last successful/attempted getMetaInfo fetch so periodic refresh
                # doesn't immediately re-fetch in the same refresh cycle.
                self.player._last_metadata_check = time.time()

                # Apply title/artist/album from getMetaInfo when status values are "Unknown"
                # This is critical for Bluetooth AVRCP sources where getPlayerStatusEx returns "Unknown"
                # but getMetaInfo has the actual track info
                if metadata and "metaData" in metadata:
                    meta_data = metadata["metaData"]
                    update: dict[str, Any] = {}

                    # Extract and apply title if status has invalid value
                    meta_title = meta_data.get("title")
                    if (
                        meta_title
                        and is_valid_metadata_value(meta_title)
                        and (not is_valid_metadata_value(status_title))
                    ):
                        update["title"] = meta_title
                        update["Title"] = meta_title
                        if status:
                            status.title = meta_title

                    # Extract and apply artist if status has invalid value
                    meta_artist = meta_data.get("artist")
                    if (
                        meta_artist
                        and is_valid_metadata_value(meta_artist)
                        and (not is_valid_metadata_value(status_artist))
                    ):
                        update["artist"] = meta_artist
                        update["Artist"] = meta_artist
                        if status:
                            status.artist = meta_artist

                    # Extract and apply album if status has invalid value
                    status_album = status.album if status else None
                    meta_album = meta_data.get("album")
                    if (
                        meta_album
                        and is_valid_metadata_value(meta_album)
                        and (not is_valid_metadata_value(status_album))
                    ):
                        update["album"] = meta_album
                        update["Album"] = meta_album
                        if status:
                            status.album = meta_album

                    if update:
                        _LOGGER.debug("Applied metadata from getMetaInfo: %s", update)
                        # Update state synchronizer
                        self.player._state_synchronizer.update_from_http(update, timestamp=time.time())
            except Exception as err:
                _LOGGER.debug("Failed to fetch metadata for %s: %s", self.player.host, err)
                self.player._metadata = None

        # EQ Info - Fetch full EQ state when preset changes
        # When EQ preset changes in status, fetch full EQ info (band values, enabled status)
        if eq_preset_changed and self.player.client.capabilities.get("supports_eq", False):
            try:
                _ = (
                    await self.player.client.get_eq()
                )  # Fetch EQ data (currently not cached, but available for callbacks)
                _LOGGER.debug("EQ preset changed to %s, fetched full EQ info", current_eq_preset)
            except Exception as err:
                _LOGGER.debug("Failed to fetch EQ info after preset change for %s: %s", self.player.host, err)

    async def _refresh_periodic_data(self, full: bool, status: PlayerStatus, track_changed: bool) -> None:
        """Refresh periodic data (audio output, EQ presets, presets, BT history).

        Args:
            full: Whether this is a full refresh.
            status: Current player status.
            track_changed: Whether the track changed this refresh cycle (computed once
                by :meth:`refresh` and shared across all consumers).
        """
        now = time.time()

        # Detect source change
        current_source = status.source if status else None
        source_changed = self._last_source is not None and current_source != self._last_source

        # getMetaInfo (Audio Quality Metadata) - Fetch on startup, full refresh, track change,
        # or periodically while playing (every 60s).
        #
        # Rationale:
        # - Bitrate/sample rate/bit depth live ONLY in getMetaInfo, not in getPlayerStatusEx.
        # - Track-change detection can miss first track (signature not yet established) and
        #   some radio sources where title/artist are stable.
        # - Periodic refresh while playing ensures integrations see these fields reliably.
        is_playing = bool(status and status.play_state and status.play_state in PLAYING_STATES)
        # Skip entirely on devices that don't implement getMetaInfo (e.g. some Arylic models
        # that return "unknown command"); otherwise we'd call it every poll for nothing.
        # See https://github.com/mjcumming/wiim/issues/248
        should_fetch_metainfo = self.player.supports_metadata and (
            full
            or self.player._metadata is None
            or (
                is_playing
                and self._polling_strategy
                and self._polling_strategy.should_fetch_configuration(self.player._last_metadata_check, now=now)
            )
        )
        if should_fetch_metainfo and hasattr(self.player.client, "get_meta_info"):
            try:
                meta_info = await self.player.client.get_meta_info()
                self.player._metadata = meta_info if meta_info else None
            except Exception as err:
                _LOGGER.debug("Failed to fetch getMetaInfo metadata for %s: %s", self.player.host, err)
                self.player._metadata = None
            finally:
                self.player._last_metadata_check = now

        # Audio Output Status - Fetch on first refresh, full refresh, source change, or periodically (every 60s)
        # CRITICAL: Fetch on startup (when None) so audio_output_mode property works immediately
        # Source changes may indicate output mode changes (e.g., Bluetooth -> WiFi)
        # Periodic fetch ensures output mode stays current even without activity
        audio_output_supported = self.player.client.capabilities.get("supports_audio_output", False)
        should_fetch_audio_output = (
            full
            or self.player._audio_output_status is None
            or source_changed
            or (
                self._polling_strategy
                and self._polling_strategy.should_fetch_audio_output(
                    self.player._last_audio_output_check,
                    source_changed,
                    audio_output_supported,
                    now=now,
                )
            )
        )
        if should_fetch_audio_output and audio_output_supported:
            try:
                # Use player-level method which automatically updates the cache
                audio_output_status = await self.player.get_audio_output_status()
                if audio_output_status is None:
                    # API call failed - clear cached state to avoid showing stale information
                    self.player._audio_output_status = None
                self.player._last_audio_output_check = now
            except Exception as err:
                _LOGGER.debug("Failed to fetch audio output status for %s: %s", self.player.host, err)
                # Clear cached state on exception to avoid showing stale information
                self.player._audio_output_status = None

        # EQ Preset List - Fetch on full refresh, track change, or periodically (every 60s)
        # Track changes may indicate preset changes (user switched to different preset/station)
        # Periodic fetch ensures list stays current even without activity
        eq_supported = self.player.client.capabilities.get("supports_eq", False)
        should_fetch_eq_presets = (
            full
            or track_changed
            or (
                self._polling_strategy
                and self._polling_strategy.should_fetch_eq_info(
                    self.player._last_eq_presets_check, eq_supported, now=now
                )
            )
        )
        if should_fetch_eq_presets and eq_supported:
            try:
                eq_presets = await self.player.client.get_eq_presets()
                self.player._eq_presets = eq_presets if eq_presets else None
                self.player._last_eq_presets_check = now
            except Exception as err:
                _LOGGER.debug("Failed to fetch EQ presets for %s: %s", self.player.host, err)
                self.player._eq_presets = None

        # EQ Enabled Status - Fetch on full refresh, track change, or periodically (every 60s)
        # This determines whether to show "Off" or the actual preset in sound_mode.
        should_fetch_eq_status = (
            full
            or track_changed
            or (
                self._polling_strategy
                and self._polling_strategy.should_fetch_eq_info(
                    self.player._last_eq_status_check, eq_supported, now=now
                )
            )
        )
        if should_fetch_eq_status and eq_supported:
            try:
                eq_enabled = await self.player.client.get_eq_status()
                self.player._eq_enabled = eq_enabled
                self.player._last_eq_status_check = now
            except Exception as err:
                _LOGGER.debug("Failed to fetch EQ status for %s: %s", self.player.host, err)
                # Don't clear - keep previous value if fetch fails

        # Channel balance (WiiM HTTP getChannelBalance only; no UPnP event path)
        cb_supported = self.player.client.capabilities.get("supports_channel_balance", False)
        should_fetch_channel_balance = full or (
            self._polling_strategy
            and self._polling_strategy.should_fetch_eq_info(
                self.player._last_channel_balance_check, cb_supported, now=now
            )
        )
        if should_fetch_channel_balance and cb_supported:
            try:
                await self.player.get_channel_balance()
            except Exception as err:
                _LOGGER.debug("Failed to fetch channel balance for %s: %s", self.player.host, err)
            finally:
                self.player._last_channel_balance_check = now

        # Preset Stations (playback presets) - Fetch on full refresh, track change, or periodically (every 60s)
        # Track changes may indicate preset changes (user switched to different preset/station)
        # Periodic fetch ensures preset names stay current even without activity (fixes issue #118)
        presets_supported = self.player.client.capabilities.get("supports_presets", False)
        should_fetch_presets = (
            full
            or track_changed
            or (
                self._polling_strategy
                and self._polling_strategy.should_fetch_presets(
                    self.player._last_presets_check, presets_supported, now=now
                )
            )
        )
        if should_fetch_presets and presets_supported:
            try:
                presets = await self.player.client.get_presets()
                self.player._presets = presets if presets else []
                self.player._last_presets_check = now
            except Exception as err:
                _LOGGER.debug("Failed to fetch presets for %s: %s", self.player.host, err)
                self.player._presets = []

        # Bluetooth History (paired devices) - Fetch on full refresh, track change, or periodically (every 60s)
        # Track changes may indicate BT device changes (user connected/disconnected device)
        # Periodic fetch ensures BT device list stays current even without activity
        should_fetch_bt = (
            full
            or track_changed
            or (
                self._polling_strategy
                and self._polling_strategy.should_fetch_configuration(self.player._last_bt_history_check, now=now)
            )
        )
        if should_fetch_bt:
            try:
                bluetooth_history = await self.player.client.get_bluetooth_history()
                self.player._bluetooth_history = bluetooth_history if bluetooth_history else []
                self.player._last_bt_history_check = now
            except Exception as err:
                _LOGGER.debug("Failed to fetch Bluetooth history for %s: %s", self.player.host, err)
                self.player._bluetooth_history = []

        # Subwoofer status — supports_subwoofer is set in capabilities detection (getSubLPF probe).
        # Here we only refresh the cached dict when support is True or still unknown (None).
        subwoofer_supported = self.player.client.capabilities.get("supports_subwoofer")
        should_fetch_subwoofer = full or (
            self._polling_strategy
            and self._polling_strategy.should_fetch_subwoofer(
                self.player._last_subwoofer_check, subwoofer_supported, now=now
            )
        )
        if should_fetch_subwoofer and subwoofer_supported is not False:
            try:
                subwoofer_status = await self.player.client.get_subwoofer_status_raw()
                if subwoofer_status is not None:
                    self.player._subwoofer_status = subwoofer_status
                    self.player._last_subwoofer_check = now
                    if subwoofer_supported is None:
                        self.player.client._capabilities["supports_subwoofer"] = True
            except Exception as err:
                _LOGGER.debug("Failed to fetch subwoofer status for %s: %s", self.player.host, err)

        # 12V trigger — supports_trigger_out from static model (ADR 016/019); configuration-tier read.
        trigger_out_supported = bool(self.player.client.capabilities.get("supports_trigger_out", False))
        should_fetch_trigger_out = full or (
            self._polling_strategy
            and self._polling_strategy.should_fetch_trigger_out(
                self.player._last_trigger_out_check, trigger_out_supported, now=now
            )
        )
        if should_fetch_trigger_out and trigger_out_supported:
            try:
                trigger_on = await self.player.get_trigger_out_status()
                if trigger_on is not None:
                    self.player._last_trigger_out_check = now
            except Exception as err:
                _LOGGER.debug("Failed to fetch 12V trigger status for %s: %s", self.player.host, err)

        # Status LED — supports_led_switch from device class (ADR 005); read via LED_SWITCH_GET when available
        led_supported = bool(self.player.client.capabilities.get("supports_led_switch", False))
        should_fetch_led = full or (
            self._polling_strategy
            and self._polling_strategy.should_fetch_led_indicator(
                self.player._last_led_indicator_check, led_supported, now=now
            )
        )
        if should_fetch_led and led_supported:
            try:
                await self.player.get_led_indicator()
                self.player._last_led_indicator_check = now
            except Exception as err:
                _LOGGER.debug("Failed to fetch LED indicator status for %s: %s", self.player.host, err)

    async def _finalize_refresh(self, track_changed: bool) -> None:
        """Finalize refresh: sync group state, enrich metadata, propagate, notify.

        Args:
            track_changed: Whether the track changed this refresh cycle (computed once
                by :meth:`refresh`). Passed explicitly because check_track_changed has
                already consumed the latch earlier in this cycle.
        """
        # Synchronize group state from device state
        from .groupops import GroupOperations

        await GroupOperations(self.player)._synchronize_group_state()

        # HTTP polling path: enrich artwork/metadata on track change (refreshes a valid
        # but stale previous-track URL) or when artwork/metadata is missing.
        merged = self.player._state_synchronizer.get_merged_state()
        await self.player._coverart_mgr.enrich_metadata_on_track_change(merged, track_changed=track_changed)

        # If this is a master, propagate enriched metadata to all linked slaves.
        if self.player.is_master and self.player._group and self.player._group.slaves:
            self.player._group_ops.propagate_metadata_to_slaves()

        # Notify callback
        if self.player._on_state_changed:
            try:
                self.player._on_state_changed()
            except Exception as err:
                _LOGGER.debug("Error calling on_state_changed callback for %s: %s", self.player.host, err)

    def _handle_refresh_error(self, err: Exception) -> None:
        """Handle refresh errors.

        Args:
            err: Exception that occurred during refresh.
        """
        device_context = f"host={self.player.host}"
        if self.player._device_info:
            device_context += f", model={self.player._device_info.model}, firmware={self.player._device_info.firmware}"
        _LOGGER.warning("Failed to refresh state for %s: %s", device_context, err)
        self.player._available = False
        raise

    async def get_device_info(self) -> DeviceInfo:
        """Get device information (always queries device)."""
        return await self.player.client.get_device_info_model()

    async def get_status(self) -> PlayerStatus:
        """Get current player status (always queries device)."""
        return await self.player.client.get_player_status_model()

    async def get_play_state(self) -> str:
        """Get current playback state by querying device."""
        status = await self.get_status()
        return status.play_state or "stop"
