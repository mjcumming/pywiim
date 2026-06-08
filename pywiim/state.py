"""State synchronization for merging HTTP polling and UPnP event data.

This module provides state synchronization that intelligently merges data from
HTTP polling and UPnP events, handling conflicts, stale data, and missing sources.

# pragma: allow-long-file state-synchronization-cohesive
# This file exceeds the 600 LOC hard limit (1097 lines) but is kept as a single
# cohesive unit because:
# 1. Single responsibility: State synchronization logic (HTTP + UPnP merging)
# 2. Well-organized: Clear sections for StateSynchronizer and GroupStateSynchronizer
# 3. Tight coupling: All classes work together for state management
# 4. Maintainable: Clear structure, follows state synchronization design pattern
# 5. Natural unit: Represents one concept (state synchronization)
# Splitting would add complexity without clear benefit.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .metadata import is_valid_image_url, is_valid_metadata_value

if TYPE_CHECKING:
    from .models import GroupState
    from .profiles import DeviceProfile

_LOGGER = logging.getLogger(__name__)

# Freshness windows (seconds) for considering data "fresh"
FRESHNESS_WINDOWS: dict[str, float] = {
    "play_state": 5.0,  # Changes frequently
    "position": 2.0,  # Changes very frequently
    "volume": 10.0,  # Changes less frequently
    "muted": 10.0,  # Changes less frequently
    "title": 30.0,  # Changes less frequently
    "artist": 30.0,
    "album": 30.0,
    "image_url": 30.0,
    "source": 60.0,  # Changes rarely
    "duration": 30.0,
}

# Source priority: which source to prefer when both are available
# First in list has higher priority
SOURCE_PRIORITY: dict[str, list[str]] = {
    # Real-time fields: UPnP preferred (more timely)
    "play_state": ["upnp", "http"],  # UPnP events are immediate
    "volume": ["upnp", "http"],  # UPnP volume changes are immediate
    "muted": ["upnp", "http"],
    # Position/Duration: UPnP provides initial values on track start, local timer estimates during playback
    # Note: UPnP events include position/duration when a new track starts (in LastChange event)
    # But UPnP does NOT send continuous position updates during playback - only on track changes
    # During playback: position is estimated locally using a timer, with periodic HTTP polling to correct drift
    "position": ["upnp", "http"],  # UPnP on track start, local timer estimates, HTTP polls periodically to correct
    "duration": ["upnp", "http"],  # UPnP on track start, HTTP polls periodically
    # Metadata: UPnP preferred when it has a sane value (fast for track changes; required for Spotify),
    # HTTP supplements/fills gaps (e.g., Bluetooth AVRCP via getMetaInfo, missing artwork fields).
    "title": ["upnp", "http"],
    "artist": ["upnp", "http"],
    "album": ["upnp", "http"],
    "image_url": ["upnp", "http"],
    # Source: HTTP preferred (more accurate)
    "source": ["http", "upnp"],
}

# Source timeouts (seconds) for marking source as unavailable
SOURCE_TIMEOUTS: dict[str, float] = {
    "http": 30.0,  # HTTP poll timeout
    "upnp": 300.0,  # UPnP event timeout (longer - events only on changes)
}

# Playing states that indicate device is active
PLAYING_STATES = ["play", "playing", "transitioning", "loading", "buffering", "load"]

# Transition states that indicate device is changing tracks/states
TRANSITION_STATES = ["load", "loading", "transitioning", "buffering"]

# UPnP state mapping to standard values
UPNP_STATE_MAP: dict[str, str] = {
    "playing": "play",
    "paused playback": "pause",
    "paused": "pause",
    "stopped": "pause",  # Modern UX: stop == pause
    "no media present": "idle",
    "transitioning": "buffering",
    "loading": "buffering",
}

# Standard play state values
STANDARD_PLAY_STATES = {
    "play": "play",
    "playing": "play",
    "pause": "pause",
    "paused": "pause",
    "paused playback": "pause",
    "stop": "pause",  # Modern UX: stop == pause (position maintained either way)
    "stopped": "pause",  # Modern UX: stop == pause (position maintained either way)
    "idle": "idle",
    "none": "idle",  # HTTP API uses "none" for idle
    "no media present": "idle",
    "load": "buffering",
    "loading": "buffering",
    "transitioning": "buffering",
    "buffering": "buffering",
}


def normalize_play_state(state: str | None) -> str | None:
    """Normalize play state to standard values.

    Handles variations from HTTP API and UPnP events.

    Args:
        state: Raw play state value from HTTP or UPnP

    Returns:
        Normalized play state value
    """
    if not state:
        return None

    state_lower = state.lower().replace("_", " ")
    return STANDARD_PLAY_STATES.get(state_lower, state_lower)


@dataclass
class TimestampedField:
    """A field value with source and timestamp information."""

    value: Any
    source: str  # "http" or "upnp"
    timestamp: float
    confidence: float = 1.0  # 0.0-1.0, based on source reliability and freshness

    def is_fresh(self, field_name: str, now: float | None = None) -> bool:
        """Check if field is fresh based on freshness window."""
        if now is None:
            now = time.time()
        freshness_window = FRESHNESS_WINDOWS.get(field_name, 10.0)
        age = now - self.timestamp
        return age < freshness_window

    def age(self, now: float | None = None) -> float:
        """Get age of field in seconds."""
        if now is None:
            now = time.time()
        return now - self.timestamp


@dataclass
class SynchronizedState:
    """Merged state from HTTP and UPnP sources."""

    # Transport state
    play_state: TimestampedField | None = None
    position: TimestampedField | None = None
    duration: TimestampedField | None = None

    # Media metadata
    title: TimestampedField | None = None
    artist: TimestampedField | None = None
    album: TimestampedField | None = None
    image_url: TimestampedField | None = None

    # Volume and mute
    volume: TimestampedField | None = None
    muted: TimestampedField | None = None

    # Source
    source: TimestampedField | None = None

    # Source health tracking
    http_last_update: float | None = None
    upnp_last_update: float | None = None
    http_available: bool = True
    upnp_available: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary with values only."""
        result: dict[str, Any] = {}
        for field_name in [
            "play_state",
            "position",
            "duration",
            "title",
            "artist",
            "album",
            "image_url",
            "volume",
            "muted",
            "source",
        ]:
            field_value = getattr(self, field_name)
            # Always include field in dict, even if None (needed for metadata updates)
            if field_value:
                result[field_name] = field_value.value
            else:
                result[field_name] = None

        # Add source health info
        result["_source_health"] = {
            "http_available": self.http_available,
            "upnp_available": self.upnp_available,
            "http_last_update": self.http_last_update,
            "upnp_last_update": self.upnp_last_update,
        }

        return result


class StateSynchronizer:
    """Synchronize state from HTTP and UPnP sources with conflict resolution.

    The synchronizer can operate in two modes:

    1. **Profile-driven** (recommended): When a DeviceProfile is provided, the
       synchronizer uses the profile's state_sources configuration to determine
       which source is authoritative for each field. This eliminates guessing
       and makes behavior explicit and predictable.

    2. **Legacy/fallback**: When no profile is provided, the synchronizer uses
       the global SOURCE_PRIORITY dict with freshness-based conflict resolution.
       This maintains backward compatibility but may have subtle bugs on devices
       with specific requirements (e.g., Audio Pro MkII needs UPnP for play_state).

    Example with profile:
        ```python
        from pywiim.profiles import get_device_profile

        profile = get_device_profile(device_info)
        synchronizer = StateSynchronizer(profile=profile)

        # For Audio Pro MkII, profile.state_sources.play_state == "upnp"
        # So the synchronizer will always prefer UPnP for play_state
        ```
    """

    def __init__(self, profile: DeviceProfile | None = None):
        """Initialize state synchronizer.

        Args:
            profile: Optional device profile that defines which source is
                authoritative for each state field. When provided, the
                synchronizer uses explicit source selection instead of
                freshness-based conflict resolution.
        """
        self._http_state: dict[str, TimestampedField] = {}
        self._upnp_state: dict[str, TimestampedField] = {}
        self._merged_state = SynchronizedState()
        self._last_merge_time: float = 0.0
        self._profile = profile

    def set_profile(self, profile: DeviceProfile) -> None:
        """Set or update the device profile.

        This can be called after initialization when the device profile
        becomes available (e.g., after capability detection completes).

        Args:
            profile: Device profile defining source preferences
        """
        self._profile = profile
        _LOGGER.debug(
            "StateSynchronizer profile set: %s (play_state=%s, volume=%s)",
            profile.display_name,
            profile.state_sources.play_state,
            profile.state_sources.volume,
        )

    @property
    def profile(self) -> DeviceProfile | None:
        """Get the current device profile."""
        return self._profile

    def _get_preferred_source(self, field_name: str) -> str:
        """Get the preferred source for a field from profile or global default.

        Args:
            field_name: Name of the state field

        Returns:
            Preferred source: "http", "upnp", or "latest"
        """
        if self._profile is not None:
            # Profile-driven: use explicit configuration
            sources = self._profile.state_sources
            source_map = {
                "play_state": sources.play_state,
                "volume": sources.volume,
                "muted": sources.mute,
                "position": sources.position,
                "duration": sources.duration,
                "source": sources.source,
                "title": sources.title,
                "artist": sources.artist,
                "album": sources.album,
                "image_url": sources.image_url,
            }
            return source_map.get(field_name, "http")

        # No profile: use global priority (legacy behavior)
        priority = SOURCE_PRIORITY.get(field_name, ["upnp", "http"])
        return priority[0]

    def update_from_http(
        self,
        data: dict[str, Any],
        timestamp: float | None = None,
        source: str = "http",
        force_metadata_update: bool = False,
    ) -> None:
        """Update state from HTTP polling data.

        Args:
            data: Dictionary with state fields from HTTP API
            timestamp: Timestamp of the update (defaults to now)
            source: Source identifier for the update. Defaults to "http" for normal
                HTTP polling. Use "propagated" when state is propagated from master
                to slave in a group.
            force_metadata_update: Apply metadata fields even when transport is paused/idle.
                Use for explicit enrichment probes that return valid metadata for the current
                paused track; normal status polling should leave this False.
        """
        ts = timestamp or time.time()

        # Extract transport state
        if "play_state" in data:
            # Normalize HTTP play state (handles "none" → "idle")
            normalized_state = normalize_play_state(data["play_state"])
            self._http_state["play_state"] = TimestampedField(
                value=normalized_state,
                source=source,
                timestamp=ts,
            )

        if "position" in data:
            position_value = data.get("position")
            self._http_state["position"] = TimestampedField(
                value=position_value,
                source=source,
                timestamp=ts,
            )

        if "duration" in data:
            self._http_state["duration"] = TimestampedField(
                value=data.get("duration"),
                source=source,
                timestamp=ts,
            )

        # Extract volume and mute
        # Only update if value is not None (preserve existing values when API doesn't return volume)
        # This prevents clearing volume when some devices (e.g., Audio Pro) don't return volume
        # in status when grouped, or when API returns None explicitly
        if "volume" in data and data.get("volume") is not None:
            self._http_state["volume"] = TimestampedField(
                value=data.get("volume"),
                source=source,
                timestamp=ts,
            )

        if "muted" in data and data.get("muted") is not None:
            self._http_state["muted"] = TimestampedField(
                value=data.get("muted"),
                source=source,
                timestamp=ts,
            )

        # Extract source
        if "source" in data:
            self._http_state["source"] = TimestampedField(
                value=data.get("source"),
                source=source,
                timestamp=ts,
            )

        # Extract metadata (preserve if playing)
        if force_metadata_update or not self._should_clear_metadata():
            for field_name in ["title", "artist", "album", "image_url"]:
                if field_name in data:
                    value = data.get(field_name)
                    # Always update if field is present in data (even if None)
                    # This ensures metadata gets populated when available
                    # If value is None/empty, we still update to track that HTTP doesn't have it
                    # (but existing metadata from other sources will be preserved via merge)
                    self._http_state[field_name] = TimestampedField(
                        value=value,
                        source=source,
                        timestamp=ts,
                    )

        self._merged_state.http_last_update = ts
        self._merge_state()

    def update_from_upnp(
        self,
        data: dict[str, Any],
        timestamp: float | None = None,
        force_metadata_update: bool = False,
    ) -> None:
        """Update state from UPnP event data.

        Args:
            data: Dictionary with state fields from UPnP event
            timestamp: Timestamp of the update (defaults to now)
            force_metadata_update: Apply metadata fields even when transport is paused/idle.
                Use for explicit enrichment probes like GetInfoEx; ordinary UPnP events should
                leave this False so metadata-free stop/idle updates do not clear current fields.
        """
        ts = timestamp or time.time()

        # Extract transport state
        if "play_state" in data:
            # Normalize UPnP play state (handles "PAUSED_PLAYBACK" → "pause")
            normalized_state = normalize_play_state(data["play_state"])
            self._upnp_state["play_state"] = TimestampedField(
                value=normalized_state,
                source="upnp",
                timestamp=ts,
            )

        if "position" in data:
            position_value = data.get("position")
            self._upnp_state["position"] = TimestampedField(
                value=position_value,
                source="upnp",
                timestamp=ts,
            )

        if "duration" in data:
            self._upnp_state["duration"] = TimestampedField(
                value=data.get("duration"),
                source="upnp",
                timestamp=ts,
            )

        # Extract volume and mute
        if "volume" in data:
            self._upnp_state["volume"] = TimestampedField(
                value=data.get("volume"),
                source="upnp",
                timestamp=ts,
            )

        if "muted" in data:
            self._upnp_state["muted"] = TimestampedField(
                value=data.get("muted"),
                source="upnp",
                timestamp=ts,
            )

        # Extract source
        if "source" in data:
            self._upnp_state["source"] = TimestampedField(
                value=data.get("source"),
                source="upnp",
                timestamp=ts,
            )

        # Extract metadata (preserve if playing)
        if force_metadata_update or not self._should_clear_metadata():
            for field_name in ["title", "artist", "album", "image_url"]:
                if field_name in data:
                    value = data.get(field_name)
                    # Always update if field is present in data (even if None)
                    # This ensures metadata gets populated when available
                    # If value is None/empty, we still update to track that UPnP doesn't have it
                    # (but existing metadata from other sources will be preserved via merge)
                    self._upnp_state[field_name] = TimestampedField(
                        value=value,
                        source="upnp",
                        timestamp=ts,
                    )

        self._merged_state.upnp_last_update = ts
        self._merge_state()

    def _merge_state(self) -> None:
        """Merge HTTP and UPnP state using conflict resolution rules."""
        now = time.time()

        # Update source availability first (needed for conflict resolution)
        self._update_source_availability(now)

        # Merge each field
        for field_name in [
            "play_state",
            "position",
            "duration",
            "volume",
            "muted",
            "title",
            "artist",
            "album",
            "image_url",
            "source",
        ]:
            http_field = self._http_state.get(field_name)
            upnp_field = self._upnp_state.get(field_name)

            merged_field = self._resolve_conflict(
                http_field,
                upnp_field,
                field_name,
                now,
            )

            setattr(self._merged_state, field_name, merged_field)

        self._last_merge_time = now

    def _resolve_conflict(
        self,
        http_field: TimestampedField | None,
        upnp_field: TimestampedField | None,
        field_name: str,
        now: float,
    ) -> TimestampedField | None:
        """Resolve conflict between HTTP and UPnP data.

        When a device profile is set, uses explicit source selection based on
        the profile's state_sources configuration. Otherwise falls back to
        freshness-based conflict resolution (legacy behavior).

        Args:
            http_field: HTTP field value (may be None)
            upnp_field: UPnP field value (may be None)
            field_name: Name of the field
            now: Current timestamp

        Returns:
            Resolved field value (may be None)
        """
        # If only one source has data, use it (regardless of profile)
        if not http_field and not upnp_field:
            return None
        if not http_field:
            return upnp_field
        if not upnp_field:
            return http_field

        # Both present - resolve conflict using profile or legacy logic
        http_fresh = http_field.is_fresh(field_name, now)
        upnp_fresh = upnp_field.is_fresh(field_name, now)
        upnp_available = self._merged_state.upnp_available

        # Get preferred source from profile (or legacy global priority)
        preferred_source = self._get_preferred_source(field_name)

        # Profile-driven resolution (when profile is set)
        if self._profile is not None:
            return self._resolve_with_profile(
                http_field,
                upnp_field,
                field_name,
                preferred_source,
                http_fresh,
                upnp_fresh,
                upnp_available,
                now,
            )

        # Legacy resolution (no profile)
        return self._resolve_legacy(
            http_field,
            upnp_field,
            field_name,
            http_fresh,
            upnp_fresh,
            upnp_available,
            now,
        )

    def _resolve_with_profile(
        self,
        http_field: TimestampedField,
        upnp_field: TimestampedField,
        field_name: str,
        preferred_source: str,
        http_fresh: bool,
        upnp_fresh: bool,
        upnp_available: bool,
        now: float,
    ) -> TimestampedField:
        """Resolve conflict using device profile configuration.

        Profile-driven resolution is simple and predictable:
        1. Use the preferred source if it has data
        2. Fall back to the other source if preferred is unavailable/stale
        3. For metadata, apply special handling to preserve non-empty values

        Args:
            http_field: HTTP field value
            upnp_field: UPnP field value
            field_name: Name of the field
            preferred_source: "http", "upnp", or "latest" from profile
            http_fresh: Whether HTTP data is fresh
            upnp_fresh: Whether UPnP data is fresh
            upnp_available: Whether UPnP is currently receiving events
            now: Current timestamp

        Returns:
            Resolved field value
        """
        # Handle "latest" preference (use most recent regardless of source)
        if preferred_source == "latest":
            chosen = upnp_field if upnp_field.timestamp > http_field.timestamp else http_field
            _LOGGER.debug(
                "State merge [profile]: field=%s, chose=%s (latest, profile=%s)",
                field_name,
                chosen.source,
                self._profile.display_name if self._profile else "none",
            )
            return chosen

        # Determine primary and fallback based on preference
        if preferred_source == "upnp":
            primary, fallback = upnp_field, http_field
            primary_fresh, fallback_fresh = upnp_fresh, http_fresh
            # IMPORTANT: In profile-driven mode, don't use coarse global UPnP availability
            # as a hard gate for UPnP-preferred real-time fields. UPnP has no heartbeat,
            # and the global availability timeout can flip false between event bursts.
            # Freshness already protects us from stale values.
            primary_available = True
        else:  # "http" (default)
            primary, fallback = http_field, upnp_field
            primary_fresh, fallback_fresh = http_fresh, upnp_fresh
            primary_available = True  # HTTP is always "available" if we got data

        # For metadata fields, apply special handling
        # Prefer "propagated" source over others for metadata (master is authoritative)
        if field_name in ["title", "artist", "album", "image_url"]:
            # If http_field is propagated and has a value, prefer it over UPnP for metadata
            if (
                http_field.source == "propagated"
                and self._is_valid_metadata_value(http_field.value, field_name)
                and upnp_field
            ):
                _LOGGER.debug(
                    "State merge [profile]: field=%s, chose=propagated (master metadata authoritative)",
                    field_name,
                )
                return http_field

            # Policy: UPnP wins for metadata when it has a sane value and is available/fresh.
            # HTTP is a supplement/fallback for gaps/unsupported metadata paths.
            if upnp_available and upnp_fresh and self._is_valid_metadata_value(upnp_field.value, field_name):
                _LOGGER.debug(
                    "State merge [profile]: field=%s, chose=upnp (metadata, has value)",
                    field_name,
                )
                return upnp_field

            # If UPnP doesn't have a sane value, prefer HTTP if it does (and is fresh).
            if http_fresh and self._is_valid_metadata_value(http_field.value, field_name):
                _LOGGER.debug(
                    "State merge [profile]: field=%s, chose=http (metadata, upnp empty/invalid)",
                    field_name,
                )
                return http_field

            return self._resolve_metadata_with_profile(
                primary,
                fallback,
                field_name,
                primary_fresh,
                fallback_fresh,
            )

        # Non-metadata: use primary if available and fresh, else fallback
        if primary_available and primary_fresh:
            _LOGGER.debug(
                "State merge [profile]: field=%s, chose=%s (preferred=%s, fresh)",
                field_name,
                primary.source,
                preferred_source,
            )
            return primary

        if fallback_fresh:
            _LOGGER.debug(
                "State merge [profile]: field=%s, chose=%s (fallback, primary %s stale/unavailable)",
                field_name,
                fallback.source,
                preferred_source,
            )
            return fallback

        # Both stale - use primary anyway (profile says it's authoritative)
        _LOGGER.debug(
            "State merge [profile]: field=%s, chose=%s (preferred=%s, both stale)",
            field_name,
            primary.source,
            preferred_source,
        )
        return primary

    def _resolve_metadata_with_profile(
        self,
        primary: TimestampedField,
        fallback: TimestampedField,
        field_name: str,
        primary_fresh: bool,
        fallback_fresh: bool,
    ) -> TimestampedField:
        """Resolve metadata field using profile with value preservation.

        For metadata, we prioritize non-empty values to prevent clearing
        valid metadata with empty updates.

        Args:
            primary: Primary source field (per profile preference)
            fallback: Fallback source field
            field_name: Name of the metadata field
            primary_fresh: Whether primary data is fresh
            fallback_fresh: Whether fallback data is fresh

        Returns:
            Resolved metadata field
        """
        # If primary has a sane value, use it
        if self._is_valid_metadata_value(primary.value, field_name):
            _LOGGER.debug(
                "State merge [profile]: field=%s, chose=%s (metadata, has value)",
                field_name,
                primary.source,
            )
            return primary

        # Primary empty/invalid - if fallback has a sane value and is fresh, use it
        if self._is_valid_metadata_value(fallback.value, field_name) and fallback_fresh:
            _LOGGER.debug(
                "State merge [profile]: field=%s, chose=%s (metadata, primary empty, fallback has value)",
                field_name,
                fallback.source,
            )
            return fallback

        # Both empty or fallback stale - preserve existing if we have it
        existing_merged: TimestampedField | None = getattr(self._merged_state, field_name, None)
        if existing_merged is not None and self._is_valid_metadata_value(existing_merged.value, field_name):
            _LOGGER.debug(
                "State merge [profile]: field=%s, preserving existing (both sources empty)",
                field_name,
            )
            return existing_merged

        # No existing - use primary (even if empty)
        _LOGGER.debug(
            "State merge [profile]: field=%s, chose=%s (metadata, no existing value)",
            field_name,
            primary.source,
        )
        return primary

    def _resolve_legacy(
        self,
        http_field: TimestampedField,
        upnp_field: TimestampedField,
        field_name: str,
        http_fresh: bool,
        upnp_fresh: bool,
        upnp_available: bool,
        now: float,
    ) -> TimestampedField:
        """Resolve conflict using legacy freshness-based logic.

        This is the original conflict resolution used when no profile is set.
        Kept for backward compatibility.

        Args:
            http_field: HTTP field value
            upnp_field: UPnP field value
            field_name: Name of the field
            http_fresh: Whether HTTP data is fresh
            upnp_fresh: Whether UPnP data is fresh
            upnp_available: Whether UPnP is currently receiving events
            now: Current timestamp

        Returns:
            Resolved field value
        """
        # Check if UPnP is actually working (receiving events)
        # If UPnP is not available, consider its data stale even if within freshness window
        if not upnp_available:
            _LOGGER.debug(
                "State merge [legacy]: field=%s, chose=http (upnp not available, age=%.1fs)",
                field_name,
                upnp_field.age(now),
            )
            return http_field

        # If one is stale, use the fresh one
        if http_fresh and not upnp_fresh:
            _LOGGER.debug(
                "State merge [legacy]: field=%s, chose=http (upnp stale: age=%.1fs)",
                field_name,
                upnp_field.age(now),
            )
            return http_field
        if upnp_fresh and not http_fresh:
            _LOGGER.debug(
                "State merge [legacy]: field=%s, chose=upnp (http stale: age=%.1fs)",
                field_name,
                http_field.age(now),
            )
            return upnp_field

        # Both fresh - for metadata, prefer propagated over UPnP (master is authoritative)
        if field_name in ["title", "artist", "album", "image_url"]:
            # Prefer propagated source for metadata (master is authoritative for slaves)
            # But only if propagated has a value (don't prefer None over existing values)
            if http_field.source == "propagated" and self._is_valid_metadata_value(http_field.value, field_name):
                _LOGGER.debug(
                    "State merge [legacy]: field=%s, chose=propagated (master metadata authoritative)",
                    field_name,
                )
                return http_field
            if self._is_valid_metadata_value(upnp_field.value, field_name):
                _LOGGER.debug(
                    "State merge [legacy]: field=%s, chose=upnp (metadata, has value, both fresh)",
                    field_name,
                )
                return upnp_field
            elif self._is_valid_metadata_value(http_field.value, field_name):
                _LOGGER.debug(
                    "State merge [legacy]: field=%s, chose=http (metadata, UPnP empty, HTTP has value)",
                    field_name,
                )
                return http_field
            else:
                # Both empty - preserve existing
                existing_merged: TimestampedField | None = getattr(self._merged_state, field_name, None)
                if existing_merged is not None and self._is_valid_metadata_value(existing_merged.value, field_name):
                    _LOGGER.debug(
                        "State merge [legacy]: field=%s, preserving existing (both sources empty)",
                        field_name,
                    )
                    return existing_merged
                # Use most recent empty value
                if upnp_field.timestamp > http_field.timestamp:
                    return upnp_field
                return http_field

        # Non-metadata: use global priority
        priority = SOURCE_PRIORITY.get(field_name, ["upnp", "http"])
        if priority[0] == "upnp" and upnp_fresh:
            _LOGGER.debug(
                "State merge [legacy]: field=%s, chose=upnp (priority, both fresh)",
                field_name,
            )
            return upnp_field
        if priority[0] == "http" and http_fresh:
            _LOGGER.debug(
                "State merge [legacy]: field=%s, chose=http (priority, both fresh)",
                field_name,
            )
            return http_field

        # Use most recent
        if upnp_field.timestamp > http_field.timestamp:
            _LOGGER.debug(
                "State merge [legacy]: field=%s, chose=upnp (most recent)",
                field_name,
            )
            return upnp_field

        _LOGGER.debug(
            "State merge [legacy]: field=%s, chose=http (most recent)",
            field_name,
        )
        return http_field

    def _should_clear_metadata(self) -> bool:
        """Determine if metadata should be cleared.

        Metadata should only be cleared if device is confirmed stopped.
        """
        # Check current play state from merged state
        play_state = self._merged_state.play_state
        if play_state:
            play_state_value = play_state.value
            if play_state_value:
                # Don't clear if device is playing or transitioning
                if any(state in str(play_state_value).lower() for state in PLAYING_STATES):
                    return False

        # Check HTTP and UPnP play states
        http_play_state = self._http_state.get("play_state")
        upnp_play_state = self._upnp_state.get("play_state")

        http_playing = False
        if http_play_state and http_play_state.value:
            http_playing = any(state in str(http_play_state.value).lower() for state in PLAYING_STATES)

        upnp_playing = False
        if upnp_play_state and upnp_play_state.value:
            upnp_playing = any(state in str(upnp_play_state.value).lower() for state in PLAYING_STATES)

        # Only clear if both sources confirm stopped
        return not http_playing and not upnp_playing

    def _has_metadata(self) -> bool:
        """Check if we currently have any metadata."""
        # Check if we have title or artist (main metadata fields)
        if self._merged_state.title or self._merged_state.artist:
            return True
        return False

    def _update_source_availability(self, now: float) -> None:
        """Update source availability flags."""
        # HTTP is available if we got data recently
        if self._merged_state.http_last_update:
            self._merged_state.http_available = (now - self._merged_state.http_last_update) < SOURCE_TIMEOUTS["http"]
        else:
            self._merged_state.http_available = False

        # UPnP is available if we got events recently
        # Note: UPnP has no heartbeat, so we use adaptive timeout:
        # - When playing: shorter timeout (5 seconds) - we expect continuous events
        # - When idle: longer timeout (300 seconds) - events only on state changes
        if self._merged_state.upnp_last_update:
            # Check if device is playing
            play_state = self._merged_state.play_state
            is_playing = False
            if play_state and play_state.value:
                is_playing = any(state in str(play_state.value).lower() for state in PLAYING_STATES)

            # Use shorter timeout when playing (expect continuous events)
            upnp_timeout = 5.0 if is_playing else SOURCE_TIMEOUTS["upnp"]
            self._merged_state.upnp_available = (now - self._merged_state.upnp_last_update) < upnp_timeout
        else:
            self._merged_state.upnp_available = False

    @staticmethod
    def _is_valid_metadata_value(val: Any, field_name: str | None = None) -> bool:
        """Field-aware metadata validity check (centralized in pywiim.metadata)."""
        if field_name == "image_url":
            return is_valid_image_url(val)
        return is_valid_metadata_value(val)

    def get_merged_state(self) -> dict[str, Any]:
        """Get current merged state as dictionary.

        Returns raw device position without estimation. Home Assistant
        integration handles position advancement based on updated_at timestamp.

        Returns:
            Dictionary with state values and source health info
        """
        return self._merged_state.to_dict()

    def get_state_object(self) -> SynchronizedState:
        """Get current merged state object.

        Returns:
            SynchronizedState object with full timestamp information
        """
        return self._merged_state


class GroupStateSynchronizer:
    """Synchronize group state from multiple devices (master + slaves).

    This class merges synchronized state from individual devices into a complete
    GroupState. Each device should have its own StateSynchronizer that merges
    HTTP + UPnP data. This class then aggregates those synchronized states.

    State Aggregation Rules:
    - Playback state: From master (authoritative)
    - Position: From master (synced across group)
    - Metadata: From master (shared across group)
    - Volume: MAX of all devices (master + slaves)
    - Mute: ALL devices muted (master + slaves)
    """

    def __init__(self):
        """Initialize group state synchronizer."""
        self._master_state: SynchronizedState | None = None
        self._slave_states: dict[str, SynchronizedState] = {}  # host -> state
        self._last_update: float = 0.0

    def update_master_state(self, state: SynchronizedState) -> None:
        """Update master device's synchronized state.

        Args:
            state: SynchronizedState from master device's StateSynchronizer
        """
        self._master_state = state
        self._last_update = time.time()

    def update_slave_state(self, host: str, state: SynchronizedState) -> None:
        """Update a slave device's synchronized state.

        Args:
            host: Slave device hostname/IP
            state: SynchronizedState from slave device's StateSynchronizer
        """
        self._slave_states[host] = state
        self._last_update = time.time()

    def remove_slave(self, host: str) -> None:
        """Remove a slave device from group state.

        Args:
            host: Slave device hostname/IP to remove
        """
        if host in self._slave_states:
            del self._slave_states[host]
            self._last_update = time.time()

    def clear(self) -> None:
        """Clear all group state."""
        self._master_state = None
        self._slave_states.clear()
        self._last_update = 0.0

    def build_group_state(
        self,
        master_host: str,
        slave_hosts: list[str],
    ) -> GroupState:  # GroupState imported via TYPE_CHECKING
        """Build complete group state from synchronized device states.

        Args:
            master_host: Master device hostname/IP
            slave_hosts: List of slave device hostnames/IPs

        Returns:
            GroupState model with complete group information
        """
        from .models import GroupDeviceState, GroupState

        if not self._master_state:
            raise ValueError("Master state not available")

        now = time.time()
        master_dict = self._master_state.to_dict()

        # Master is authoritative for playback state
        play_state = master_dict.get("play_state")
        position = master_dict.get("position")
        duration = master_dict.get("duration")
        source = master_dict.get("source")
        title = master_dict.get("title")
        artist = master_dict.get("artist")
        album = master_dict.get("album")

        # Aggregate volume and mute from all devices
        volumes: list[float] = []
        mutes: list[bool] = []

        # Add master volume/mute
        if master_dict.get("volume") is not None:
            volumes.append(master_dict["volume"])
        if master_dict.get("muted") is not None:
            mutes.append(master_dict["muted"])

        # Build master device state
        master_device_state = GroupDeviceState(
            host=master_host,
            role="master",
            volume=master_dict.get("volume"),
            mute=master_dict.get("muted"),
            play_state=play_state,
            position=position,
            duration=duration,
            source=source,
            title=title,
            album=album,
            last_updated=now,
        )

        # Add slave volumes/mutes and build slave states
        slave_states_list: list[GroupDeviceState] = []
        for slave_host in slave_hosts:
            slave_state = self._slave_states.get(slave_host)
            if slave_state:
                slave_dict = slave_state.to_dict()
                slave_states_list.append(
                    GroupDeviceState(
                        host=slave_host,
                        role="slave",
                        volume=slave_dict.get("volume"),
                        mute=slave_dict.get("muted"),
                        play_state=slave_dict.get("play_state"),
                        position=slave_dict.get("position"),
                        duration=slave_dict.get("duration"),
                        source=slave_dict.get("source"),
                        title=slave_dict.get("title"),
                        album=slave_dict.get("album"),
                        last_updated=now,
                    )
                )

                # Aggregate volume/mute
                if slave_dict.get("volume") is not None:
                    volumes.append(slave_dict["volume"])
                if slave_dict.get("muted") is not None:
                    mutes.append(slave_dict["muted"])

        # Calculate group volume (MAX) and mute (ALL)
        group_volume = max(volumes) if volumes else None
        group_muted = all(mutes) if mutes else None

        return GroupState(
            master_host=master_host,
            slave_hosts=slave_hosts,
            master_state=master_device_state,
            slave_states=slave_states_list,
            play_state=play_state,
            position=position,
            duration=duration,
            source=source,
            title=title,
            artist=artist,
            album=album,
            volume_level=group_volume,
            is_muted=group_muted,
            created_at=now,
            last_updated=now,
        )


__all__ = [
    "StateSynchronizer",
    "GroupStateSynchronizer",
    "SynchronizedState",
    "TimestampedField",
    "FRESHNESS_WINDOWS",
    "SOURCE_PRIORITY",
    "SOURCE_TIMEOUTS",
    "PLAYING_STATES",
    "TRANSITION_STATES",
    "UPNP_STATE_MAP",
    "STANDARD_PLAY_STATES",
    "normalize_play_state",
]
