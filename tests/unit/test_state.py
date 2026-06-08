"""Unit tests for state synchronization.

Tests StateSynchronizer and GroupStateSynchronizer for merging HTTP and UPnP data.
"""

from __future__ import annotations

import time

import pytest

from pywiim.state import (
    StateSynchronizer,
    SynchronizedState,
    TimestampedField,
    normalize_play_state,
)


class TestNormalizePlayState:
    """Test play state normalization."""

    def test_normalize_play_state_standard(self):
        """Test normalizing standard play states."""
        assert normalize_play_state("play") == "play"
        assert normalize_play_state("pause") == "pause"
        assert normalize_play_state("stop") == "pause"  # Modern UX: stop maps to pause

    def test_normalize_play_state_variations(self):
        """Test normalizing play state variations."""
        assert normalize_play_state("playing") == "play"
        assert normalize_play_state("paused") == "pause"
        assert normalize_play_state("stopped") == "pause"  # Modern UX: stopped maps to pause
        assert normalize_play_state("idle") == "idle"

    def test_normalize_play_state_upnp(self):
        """Test normalizing UPnP play states."""
        assert normalize_play_state("PAUSED_PLAYBACK") == "pause"
        assert normalize_play_state("NO_MEDIA_PRESENT") == "idle"

    def test_normalize_play_state_none(self):
        """Test normalizing None play state."""
        assert normalize_play_state(None) is None

    def test_normalize_play_state_unknown(self):
        """Test normalizing unknown play state."""
        result = normalize_play_state("unknown_state")
        assert result is not None  # Returns normalized lowercase


class TestTimestampedField:
    """Test TimestampedField dataclass."""

    def test_timestamped_field_creation(self):
        """Test creating TimestampedField."""
        field = TimestampedField(value="test", source="http", timestamp=1000.0)

        assert field.value == "test"
        assert field.source == "http"
        assert field.timestamp == 1000.0
        assert field.confidence == 1.0

    def test_is_fresh(self):
        """Test checking if field is fresh."""
        now = time.time()
        field = TimestampedField(value="test", source="http", timestamp=now - 1.0)

        assert field.is_fresh("play_state", now) is True  # 1s < 5s window

    def test_is_stale(self):
        """Test checking if field is stale."""
        now = time.time()
        field = TimestampedField(value="test", source="http", timestamp=now - 10.0)

        assert field.is_fresh("play_state", now) is False  # 10s > 5s window

    def test_age(self):
        """Test getting field age."""
        now = time.time()
        field = TimestampedField(value="test", source="http", timestamp=now - 5.0)

        assert abs(field.age(now) - 5.0) < 0.1


class TestStateSynchronizer:
    """Test StateSynchronizer class."""

    def test_init(self):
        """Test StateSynchronizer initialization."""
        sync = StateSynchronizer()

        assert sync._http_state == {}
        assert sync._upnp_state == {}
        assert sync._merged_state is not None

    def test_update_from_http(self):
        """Test updating from HTTP data."""
        sync = StateSynchronizer()

        http_data = {
            "play_state": "play",
            "volume": 50,
            "muted": False,
            "title": "Test Song",
            "position": 120,
        }

        sync.update_from_http(http_data)

        assert "play_state" in sync._http_state
        assert sync._http_state["play_state"].value == "play"
        assert sync._merged_state.http_last_update is not None

    def test_update_from_upnp(self):
        """Test updating from UPnP data."""
        sync = StateSynchronizer()

        upnp_data = {
            "play_state": "playing",
            "volume": 0.75,
            "muted": False,
        }

        sync.update_from_upnp(upnp_data)

        assert "play_state" in sync._upnp_state
        assert sync._upnp_state["play_state"].value == "play"  # Normalized
        assert sync._merged_state.upnp_last_update is not None

    def test_merge_state_http_only(self):
        """Test merging state when only HTTP data available."""
        sync = StateSynchronizer()

        sync.update_from_http({"play_state": "play", "volume": 50})
        merged = sync.get_merged_state()

        assert merged["play_state"] == "play"
        assert merged["volume"] == 50

    def test_merge_state_upnp_only(self):
        """Test merging state when only UPnP data available."""
        sync = StateSynchronizer()

        sync.update_from_upnp({"play_state": "playing", "volume": 0.75})
        merged = sync.get_merged_state()

        assert merged["play_state"] == "play"  # Normalized
        assert merged["volume"] == 0.75

    def test_merge_state_conflict_fresh_upnp(self):
        """Test merging when both sources present, UPnP is fresh."""
        sync = StateSynchronizer()

        now = time.time()
        # HTTP data is stale
        sync.update_from_http({"play_state": "pause"}, timestamp=now - 10.0)
        # UPnP data is fresh
        sync.update_from_upnp({"play_state": "play"}, timestamp=now)

        merged = sync.get_merged_state()

        # Should prefer fresh UPnP
        assert merged["play_state"] == "play"

    def test_merge_state_conflict_priority(self):
        """Test merging using source priority."""
        sync = StateSynchronizer()

        now = time.time()
        # Both fresh, use priority
        sync.update_from_http({"play_state": "pause"}, timestamp=now)
        sync.update_from_upnp({"play_state": "play"}, timestamp=now)

        merged = sync.get_merged_state()

        # play_state priority is ["upnp", "http"], so should use UPnP
        assert merged["play_state"] == "play"

    def test_merge_state_metadata_priority(self):
        """Test merging metadata - UPnP preferred when both fresh (fires on track changes)."""
        sync = StateSynchronizer()

        now = time.time()
        # Set play state first so metadata is preserved
        sync.update_from_http({"play_state": "play", "title": "HTTP Title"}, timestamp=now)
        sync.update_from_upnp({"play_state": "play", "title": "UPnP Title"}, timestamp=now)

        merged = sync.get_merged_state()

        # Metadata: prefer UPnP when both fresh (UPnP fires immediately on track changes)
        # HTTP may have stale metadata (e.g., Spotify only sends metadata via UPnP)
        assert merged["title"] == "UPnP Title"

    def test_get_merged_state(self):
        """Test getting merged state as dictionary."""
        sync = StateSynchronizer()

        sync.update_from_http({"play_state": "play", "volume": 50})
        merged = sync.get_merged_state()

        assert isinstance(merged, dict)
        assert "play_state" in merged
        assert "_source_health" in merged
        assert merged["_source_health"]["http_available"] is True

    def test_get_state_object(self):
        """Test getting merged state object."""
        sync = StateSynchronizer()

        sync.update_from_http({"play_state": "play"})
        state_obj = sync.get_state_object()

        assert isinstance(state_obj, SynchronizedState)
        assert state_obj.play_state is not None
        assert state_obj.play_state.value == "play"

    def test_update_from_http_preserves_volume_when_none(self):
        """Test that update_from_http preserves existing volume when HTTP returns None."""
        sync = StateSynchronizer()

        # First, set volume from UPnP
        sync.update_from_upnp({"volume": 50, "muted": False})
        merged1 = sync.get_merged_state()
        assert merged1["volume"] == 50

        # Then, HTTP poll returns None for volume (e.g., grouped device)
        # Should preserve existing volume, not clear it
        sync.update_from_http({"play_state": "play", "volume": None, "muted": None})
        merged2 = sync.get_merged_state()

        # Volume should still be 50 (from UPnP), not None
        assert merged2["volume"] == 50
        # Mute should still be False (from UPnP), not None
        assert merged2["muted"] is False

    def test_update_from_http_preserves_mute_when_none(self):
        """Test that update_from_http preserves existing mute when HTTP returns None."""
        sync = StateSynchronizer()

        # First, set mute from UPnP
        sync.update_from_upnp({"volume": 50, "muted": True})
        merged1 = sync.get_merged_state()
        assert merged1["muted"] is True

        # Then, HTTP poll returns None for mute
        # Should preserve existing mute, not clear it
        sync.update_from_http({"play_state": "play", "muted": None})
        merged2 = sync.get_merged_state()

        # Mute should still be True (from UPnP), not None
        assert merged2["muted"] is True

    def test_update_from_http_updates_volume_when_provided(self):
        """Test that update_from_http updates volume when HTTP provides a value."""
        sync = StateSynchronizer()

        # First, set volume from UPnP (stale - older timestamp)
        import time

        old_time = time.time() - 20.0  # 20 seconds ago (stale)
        sync.update_from_upnp({"volume": 50}, timestamp=old_time)
        merged1 = sync.get_merged_state()
        assert merged1["volume"] == 50

        # Then, HTTP poll returns a new volume value (fresh)
        # Should update to HTTP value since UPnP is stale
        sync.update_from_http({"volume": 75})
        merged2 = sync.get_merged_state()

        # Volume should be updated to 75 (from HTTP, since UPnP is stale)
        assert merged2["volume"] == 75

    def test_update_from_http_handles_missing_volume_key(self):
        """Test that update_from_http handles missing volume key (not in dict at all)."""
        sync = StateSynchronizer()

        # First, set volume from UPnP
        sync.update_from_upnp({"volume": 50})
        merged1 = sync.get_merged_state()
        assert merged1["volume"] == 50

        # Then, HTTP poll doesn't include volume key at all
        # Should preserve existing volume
        sync.update_from_http({"play_state": "play"})
        merged2 = sync.get_merged_state()

        # Volume should still be 50 (from UPnP)
        assert merged2["volume"] == 50


class TestGroupStateSynchronizer:
    """Test GroupStateSynchronizer class."""

    def test_init(self):
        """Test GroupStateSynchronizer initialization."""
        from pywiim.state import GroupStateSynchronizer

        sync = GroupStateSynchronizer()

        assert sync._master_state is None
        assert sync._slave_states == {}
        assert sync._last_update == 0.0

    def test_update_master_state(self):
        """Test updating master state."""
        from pywiim.state import GroupStateSynchronizer, SynchronizedState

        sync = GroupStateSynchronizer()
        master_state = SynchronizedState()
        master_state.play_state = TimestampedField(value="play", source="http", timestamp=time.time())

        sync.update_master_state(master_state)

        assert sync._master_state == master_state
        assert sync._last_update > 0

    def test_update_slave_state(self):
        """Test updating slave state."""
        from pywiim.state import GroupStateSynchronizer, SynchronizedState

        sync = GroupStateSynchronizer()
        slave_state = SynchronizedState()
        slave_state.volume = TimestampedField(value=0.5, source="http", timestamp=time.time())

        sync.update_slave_state("192.168.1.101", slave_state)

        assert "192.168.1.101" in sync._slave_states
        assert sync._slave_states["192.168.1.101"] == slave_state

    def test_remove_slave(self):
        """Test removing slave state."""
        from pywiim.state import GroupStateSynchronizer, SynchronizedState

        sync = GroupStateSynchronizer()
        slave_state = SynchronizedState()
        sync.update_slave_state("192.168.1.101", slave_state)

        sync.remove_slave("192.168.1.101")

        assert "192.168.1.101" not in sync._slave_states

    def test_clear(self):
        """Test clearing all state."""
        from pywiim.state import GroupStateSynchronizer, SynchronizedState

        sync = GroupStateSynchronizer()
        master_state = SynchronizedState()
        sync.update_master_state(master_state)
        sync.update_slave_state("192.168.1.101", SynchronizedState())

        sync.clear()

        assert sync._master_state is None
        assert len(sync._slave_states) == 0
        assert sync._last_update == 0.0

    def test_build_group_state(self):
        """Test building group state from synchronized states."""
        from pywiim.state import GroupStateSynchronizer, SynchronizedState, TimestampedField

        sync = GroupStateSynchronizer()

        # Create master state
        master_state = SynchronizedState()
        master_state.play_state = TimestampedField(value="play", source="http", timestamp=time.time())
        master_state.volume = TimestampedField(value=0.5, source="http", timestamp=time.time())
        master_state.muted = TimestampedField(value=False, source="http", timestamp=time.time())
        master_state.title = TimestampedField(value="Test Song", source="http", timestamp=time.time())
        sync.update_master_state(master_state)

        # Create slave state
        slave_state = SynchronizedState()
        slave_state.volume = TimestampedField(value=0.75, source="http", timestamp=time.time())
        slave_state.muted = TimestampedField(value=True, source="http", timestamp=time.time())
        sync.update_slave_state("192.168.1.101", slave_state)

        group_state = sync.build_group_state("192.168.1.100", ["192.168.1.101"])

        assert group_state.master_host == "192.168.1.100"
        assert group_state.slave_hosts == ["192.168.1.101"]
        assert group_state.play_state == "play"
        assert group_state.volume_level == 0.75  # Max of 0.5 and 0.75
        assert group_state.is_muted is False  # Not all muted (master=False, slave=True)

    def test_build_group_state_no_master(self):
        """Test building group state when master state not available."""
        from pywiim.state import GroupStateSynchronizer

        sync = GroupStateSynchronizer()

        with pytest.raises(ValueError, match="Master state not available"):
            sync.build_group_state("192.168.1.100", [])


class TestStateSynchronizerWithProfile:
    """Test StateSynchronizer with device profile configuration."""

    def test_init_with_profile(self):
        """Test initializing with a profile."""
        from pywiim.profiles import PROFILES

        profile = PROFILES["audio_pro_mkii"]
        sync = StateSynchronizer(profile=profile)

        assert sync.profile == profile
        assert sync._profile == profile

    def test_set_profile(self):
        """Test setting profile after initialization."""
        from pywiim.profiles import PROFILES

        sync = StateSynchronizer()
        assert sync.profile is None

        profile = PROFILES["wiim"]
        sync.set_profile(profile)

        assert sync.profile == profile

    def test_get_preferred_source_with_profile(self):
        """Test _get_preferred_source uses profile config."""
        from pywiim.profiles import PROFILES

        # Audio Pro MkII requires UPnP for play_state
        profile = PROFILES["audio_pro_mkii"]
        sync = StateSynchronizer(profile=profile)

        assert sync._get_preferred_source("play_state") == "upnp"
        assert sync._get_preferred_source("volume") == "upnp"
        assert sync._get_preferred_source("title") == "http"

    def test_get_preferred_source_without_profile(self):
        """Test _get_preferred_source uses global priority without profile."""
        sync = StateSynchronizer()

        # Without profile, uses global SOURCE_PRIORITY
        # play_state priority is ["upnp", "http"], so first is "upnp"
        assert sync._get_preferred_source("play_state") == "upnp"

    def test_wiim_profile_uses_http(self):
        """Test WiiM profile uses UPnP for real-time volume/mute fields."""
        from pywiim.profiles import PROFILES

        profile = PROFILES["wiim"]
        sync = StateSynchronizer(profile=profile)

        assert sync._get_preferred_source("play_state") == "upnp"
        assert sync._get_preferred_source("volume") == "upnp"
        assert sync._get_preferred_source("muted") == "upnp"

    def test_mkii_profile_uses_upnp_for_transport(self):
        """Test Audio Pro MkII profile uses UPnP for transport state."""
        from pywiim.profiles import PROFILES

        profile = PROFILES["audio_pro_mkii"]
        sync = StateSynchronizer(profile=profile)

        # Transport state uses UPnP (HTTP doesn't provide it on MkII)
        assert sync._get_preferred_source("play_state") == "upnp"
        assert sync._get_preferred_source("volume") == "upnp"
        assert sync._get_preferred_source("muted") == "upnp"

        # Metadata still uses HTTP
        assert sync._get_preferred_source("title") == "http"
        assert sync._get_preferred_source("artist") == "http"

    def test_profile_driven_conflict_resolution(self):
        """Test that profile-driven resolution uses preferred source."""
        from pywiim.profiles import PROFILES

        # WiiM profile prefers UPnP for play_state
        profile = PROFILES["wiim"]
        sync = StateSynchronizer(profile=profile)

        now = time.time()
        # Both sources fresh with different values
        sync.update_from_http({"play_state": "pause"}, timestamp=now)
        sync.update_from_upnp({"play_state": "play"}, timestamp=now)

        merged = sync.get_merged_state()

        # WiiM profile prefers UPnP for play_state
        assert merged["play_state"] == "play"

    def test_mkii_profile_resolution_prefers_upnp(self):
        """Test MkII profile prefers UPnP for play_state."""
        from pywiim.profiles import PROFILES

        profile = PROFILES["audio_pro_mkii"]
        sync = StateSynchronizer(profile=profile)

        now = time.time()
        # Both sources fresh with different values
        sync.update_from_http({"play_state": "pause"}, timestamp=now)
        sync.update_from_upnp({"play_state": "play"}, timestamp=now)

        merged = sync.get_merged_state()

        # MkII profile prefers UPnP for play_state
        assert merged["play_state"] == "play"

    def test_wiim_profile_volume_prefers_upnp_when_both_fresh(self):
        """Test WiiM profile prefers UPnP for volume when both sources are fresh."""
        from pywiim.profiles import PROFILES

        profile = PROFILES["wiim"]
        sync = StateSynchronizer(profile=profile)

        now = time.time()
        sync.update_from_http({"volume": 16}, timestamp=now)
        sync.update_from_upnp({"volume": 75}, timestamp=now + 0.1)

        merged = sync.get_merged_state()
        assert merged["volume"] == 75

    def test_wiim_profile_volume_uses_upnp_even_when_http_is_fresh(self):
        """Test WiiM profile prevents stale-but-fresh HTTP from overriding newer UPnP volume."""
        from pywiim.profiles import PROFILES

        profile = PROFILES["wiim"]
        sync = StateSynchronizer(profile=profile)

        now = time.time()
        # HTTP is within freshness window (10s), but represents an older value.
        sync.update_from_http({"volume": 16}, timestamp=now - 5.0)
        # New UPnP event has the latest value.
        sync.update_from_upnp({"volume": 55}, timestamp=now)

        merged = sync.get_merged_state()
        assert merged["volume"] == 55

    def test_wiim_profile_upnp_preferred_ignores_coarse_upnp_availability_timeout(self):
        """Fresh UPnP value should still win for UPnP-preferred fields in profile mode.

        Regression case: when playing, global UPnP availability may flip false after 5s
        without events. That coarse health signal should not override a fresh UPnP field
        for UPnP-preferred fields like volume/play_state.
        """
        from pywiim.profiles import PROFILES

        profile = PROFILES["wiim"]
        sync = StateSynchronizer(profile=profile)

        now = time.time()
        # Keep device in "playing" mode so UPnP availability uses the short timeout path.
        sync.update_from_http({"play_state": "play"}, timestamp=now - 1.0)

        # HTTP and UPnP volume are both within freshness window (10s), but UPnP is newer.
        sync.update_from_http({"volume": 16}, timestamp=now - 9.0)
        sync.update_from_upnp({"volume": 55}, timestamp=now - 6.0)

        # Under old behavior, upnp_available=false while playing could force HTTP fallback.
        merged = sync.get_merged_state()
        assert merged["volume"] == 55

    def test_profile_fallback_when_preferred_unavailable(self):
        """Test fallback to other source when preferred is unavailable."""
        from pywiim.profiles import PROFILES

        # MkII prefers UPnP for play_state
        profile = PROFILES["audio_pro_mkii"]
        sync = StateSynchronizer(profile=profile)

        now = time.time()
        # Only HTTP data available
        sync.update_from_http({"play_state": "pause"}, timestamp=now)

        merged = sync.get_merged_state()

        # Should fall back to HTTP since no UPnP data
        assert merged["play_state"] == "pause"

    def test_legacy_resolution_without_profile(self):
        """Test legacy resolution still works when no profile set."""
        sync = StateSynchronizer()  # No profile

        now = time.time()
        # HTTP stale, UPnP fresh
        sync.update_from_http({"play_state": "pause"}, timestamp=now - 10.0)
        sync.update_from_upnp({"play_state": "play"}, timestamp=now)

        merged = sync.get_merged_state()

        # Legacy: should prefer fresh UPnP
        assert merged["play_state"] == "play"

    def test_metadata_uses_non_empty_value(self):
        """Test metadata uses non-empty value from either source."""
        from pywiim.profiles import PROFILES

        profile = PROFILES["wiim"]
        sync = StateSynchronizer(profile=profile)

        now = time.time()

        # HTTP has empty metadata, UPnP has values
        sync.update_from_http(
            {
                "play_state": "play",
                "title": None,
            },
            timestamp=now,
        )

        sync.update_from_upnp(
            {
                "play_state": "play",
                "title": "UPnP Title",
            },
            timestamp=now,
        )

        merged = sync.get_merged_state()

        # Even though WiiM prefers HTTP, UPnP has a value so use it
        assert merged["title"] == "UPnP Title"

    def test_metadata_prefers_primary_when_both_have_values(self):
        """Test metadata prefers UPnP when both have sane values (HTTP supplements)."""
        from pywiim.profiles import PROFILES

        profile = PROFILES["wiim"]  # HTTP preferred
        sync = StateSynchronizer(profile=profile)

        now = time.time()

        sync.update_from_http(
            {
                "play_state": "play",
                "title": "HTTP Title",
            },
            timestamp=now,
        )

        sync.update_from_upnp(
            {
                "play_state": "play",
                "title": "UPnP Title",
            },
            timestamp=now,
        )

        merged = sync.get_merged_state()

        # Policy: UPnP wins for metadata when it has a sane value; HTTP supplements
        assert merged["title"] == "UPnP Title"

    def test_metadata_falls_back_to_http_when_upnp_is_invalid(self):
        """If UPnP metadata is placeholder/invalid, fall back to HTTP when it has a sane value."""
        from pywiim.profiles import PROFILES

        profile = PROFILES["wiim"]
        sync = StateSynchronizer(profile=profile)

        now = time.time()
        sync.update_from_http({"play_state": "play", "title": "HTTP Title"}, timestamp=now)
        sync.update_from_upnp({"play_state": "play", "title": "Unknown"}, timestamp=now)

        merged = sync.get_merged_state()
        assert merged["title"] == "HTTP Title"

    def test_image_url_rejects_un_known_and_non_http_urls(self):
        """image_url should ignore known sentinels and non-http(s) values."""
        sync = StateSynchronizer()
        now = time.time()

        # Establish playing so metadata isn't cleared
        sync.update_from_http({"play_state": "play"}, timestamp=now)

        # HTTP has a valid URL
        sync.update_from_http({"image_url": "https://example.com/cover.jpg"}, timestamp=now)
        assert sync.get_merged_state()["image_url"] == "https://example.com/cover.jpg"

        # UPnP tries to overwrite with sentinel/invalid values: should be ignored by merge
        sync.update_from_upnp({"image_url": "un_known"}, timestamp=now)
        assert sync.get_merged_state()["image_url"] == "https://example.com/cover.jpg"

        sync.update_from_upnp({"image_url": "http://192.168.1.2:49152/un_known"}, timestamp=now)
        assert sync.get_merged_state()["image_url"] == "https://example.com/cover.jpg"

        sync.update_from_upnp({"image_url": "file:///tmp/cover.jpg"}, timestamp=now)
        assert sync.get_merged_state()["image_url"] == "https://example.com/cover.jpg"

    def test_upnp_artwork_survives_metadata_free_pause_event(self):
        """GetInfoEx artwork should survive a later UPnP pause event without metadata."""
        from pywiim.profiles import PROFILES

        sync = StateSynchronizer(profile=PROFILES["wiim"])
        now = time.time()
        artwork_url = "https://example.com/getinfoex-art.jpg"

        # Arylic HTTP status often has track text but no artwork.
        sync.update_from_http(
            {
                "play_state": "play",
                "title": "Song",
                "artist": "Artist",
                "album": "Album",
                "image_url": None,
            },
            timestamp=now,
        )

        # LinkPlay GetInfoEx is a UPnP call and supplies artwork for the same track.
        sync.update_from_upnp(
            {
                "title": "Song",
                "artist": "Artist",
                "album": "Album",
                "image_url": artwork_url,
            },
            timestamp=now + 0.1,
        )
        assert sync.get_merged_state()["image_url"] == artwork_url

        # The pause debouncer later writes only play_state via UPnP. It must not
        # clear the still-valid artwork for the paused track.
        sync.update_from_upnp({"play_state": "pause"}, timestamp=now + 0.6)

        merged = sync.get_merged_state()
        assert merged["play_state"] == "pause"
        assert merged["image_url"] == artwork_url

    def test_forced_upnp_artwork_update_applies_while_paused(self):
        """Explicit GetInfoEx enrichment should apply artwork for the current paused track."""
        from pywiim.profiles import PROFILES

        sync = StateSynchronizer(profile=PROFILES["wiim"])
        now = time.time()
        artwork_url = "https://example.com/paused-getinfoex-art.jpg"

        sync.update_from_http(
            {
                "play_state": "pause",
                "title": "Song",
                "artist": "Artist",
                "album": "Album",
                "image_url": None,
            },
            timestamp=now,
        )
        assert sync.get_merged_state().get("image_url") is None

        sync.update_from_upnp(
            {
                "title": "Song",
                "artist": "Artist",
                "album": "Album",
                "image_url": artwork_url,
            },
            timestamp=now + 0.1,
            force_metadata_update=True,
        )

        merged = sync.get_merged_state()
        assert merged["play_state"] == "pause"
        assert merged["title"] == "Song"
        assert merged["artist"] == "Artist"
        assert merged["album"] == "Album"
        assert merged["image_url"] == artwork_url

    def test_metadata_preservation_from_merged_state(self):
        """Test metadata is preserved from merged state when both sources empty."""
        from pywiim.profiles import PROFILES

        profile = PROFILES["wiim"]
        sync = StateSynchronizer(profile=profile)

        now = time.time()

        # First update with metadata (this sets merged state)
        sync.update_from_http(
            {
                "play_state": "play",
                "title": "Good Song",
            },
            timestamp=now,
        )

        # Verify it's there
        merged = sync.get_merged_state()
        assert merged["title"] == "Good Song"

        # Now update with ONLY play_state (don't include title at all)
        # This shouldn't overwrite the existing title
        sync.update_from_http(
            {
                "play_state": "play",
            },
            timestamp=now + 1,
        )

        merged = sync.get_merged_state()
        # Title should still be there since we didn't provide a new one
        assert merged["title"] == "Good Song"

    def test_propagated_source_preferred_for_metadata(self):
        """Test that propagated source is preferred over UPnP for metadata fields."""
        sync = StateSynchronizer()

        now = time.time()
        # Set play_state first so metadata is preserved
        sync.update_from_http({"play_state": "play"}, timestamp=now)
        # Master propagates metadata to slave
        sync.update_from_http(
            {"title": "Master Track", "artist": "Master Artist"},
            timestamp=now,
            source="propagated",
        )
        # Slave also receives its own UPnP event
        sync.update_from_upnp(
            {"title": "Slave Track", "artist": "Slave Artist"},
            timestamp=now,
        )

        merged = sync.get_merged_state()

        # Propagated state (from master) should win over slave's own UPnP event
        assert merged["title"] == "Master Track"
        assert merged["artist"] == "Master Artist"

    def test_propagated_source_preferred_for_metadata_with_profile(self):
        """Test that propagated source is preferred even with device profile."""
        from pywiim.profiles import PROFILES

        profile = PROFILES["wiim"]
        sync = StateSynchronizer(profile=profile)

        now = time.time()
        # Set play_state first so metadata is preserved
        sync.update_from_http({"play_state": "play"}, timestamp=now)
        # Master propagates metadata to slave
        sync.update_from_http(
            {"title": "Master Track", "artist": "Master Artist"},
            timestamp=now,
            source="propagated",
        )
        # Slave also receives its own UPnP event
        sync.update_from_upnp(
            {"title": "Slave Track", "artist": "Slave Artist"},
            timestamp=now,
        )

        merged = sync.get_merged_state()

        # Propagated state (from master) should win over slave's own UPnP event
        # even though profile might prefer HTTP for metadata
        assert merged["title"] == "Master Track"
        assert merged["artist"] == "Master Artist"

    def test_propagated_source_race_condition(self):
        """Test race condition: propagated state vs slave's own HTTP refresh."""
        sync = StateSynchronizer()

        now = time.time()
        # Set play_state first so metadata is preserved
        sync.update_from_http({"play_state": "play"}, timestamp=now - 5.0)
        # Slave receives its own HTTP refresh (stale data)
        sync.update_from_http(
            {"title": "Old Track", "artist": "Old Artist"},
            timestamp=now - 5.0,
            source="http",
        )
        # Master propagates fresh metadata (simulating race condition)
        sync.update_from_http(
            {"title": "Master Track", "artist": "Master Artist"},
            timestamp=now,
            source="propagated",
        )

        merged = sync.get_merged_state()

        # Propagated state should win (master is authoritative)
        assert merged["title"] == "Master Track"
        assert merged["artist"] == "Master Artist"

    def test_propagated_source_metadata_empty_values(self):
        """Test that propagated empty values are handled correctly."""
        sync = StateSynchronizer()

        now = time.time()
        # Set play_state first so metadata is preserved
        sync.update_from_http({"play_state": "play"}, timestamp=now - 1.0)
        # Set initial metadata from UPnP (slave's own event)
        sync.update_from_upnp(
            {"title": "Existing Track", "artist": "Existing Artist"},
            timestamp=now - 1.0,
        )
        # Master propagates empty metadata
        # Note: When propagated is None, it overwrites http_state, but UPnP still has the value
        # Conflict resolution should prefer non-empty UPnP value over empty propagated
        sync.update_from_http(
            {"title": None, "artist": None},
            timestamp=now,
            source="propagated",
        )

        merged = sync.get_merged_state()

        # When propagated is None but UPnP has a value, prefer UPnP (non-empty)
        # This tests that conflict resolution handles empty propagated values correctly
        assert merged["title"] == "Existing Track"
        assert merged["artist"] == "Existing Artist"
