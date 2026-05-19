"""Unit tests for polling strategy helpers.

Tests PollingStrategy and TrackChangeDetector.
"""

from __future__ import annotations

import time

import pytest

from pywiim.polling import PollingStrategy, TrackChangeDetector, fetch_parallel


class TestPollingStrategy:
    """Test PollingStrategy class."""

    def test_init(self):
        """Test PollingStrategy initialization."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        assert strategy.capabilities == capabilities

    def test_get_optimal_interval_wiim_playing(self):
        """Test optimal interval for WiiM device playing."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        interval = strategy.get_optimal_interval("master", is_playing=True)

        assert interval == 1.0  # Fast poll during playback

    def test_get_optimal_interval_wiim_idle_startup(self):
        """Test optimal interval for WiiM device on startup (should use normal polling)."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)
        # On startup, _last_playing_time is 0, so should use normal polling
        assert strategy._last_playing_time == 0.0

        interval = strategy.get_optimal_interval("master", is_playing=False)

        assert interval == 5.0  # Normal poll on startup (not fast)

    def test_get_optimal_interval_wiim_idle_active(self):
        """Test optimal interval for WiiM device in active idle window."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)
        # Set last playing time to be < 30 seconds ago (within active idle window)
        strategy._last_playing_time = time.time() - 10

        interval = strategy.get_optimal_interval("master", is_playing=False)

        assert interval == 1.0  # Fast poll during active idle window

    def test_get_optimal_interval_wiim_idle(self):
        """Test optimal interval for WiiM device idle."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)
        # Set last playing time to be > 30 seconds ago to get normal interval
        strategy._last_playing_time = time.time() - 60

        interval = strategy.get_optimal_interval("master", is_playing=False)

        assert interval == 5.0  # Normal poll when deep idle

    def test_get_optimal_interval_wiim_slave(self):
        """Test optimal interval for WiiM slave."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        interval = strategy.get_optimal_interval("slave", is_playing=False)

        assert interval == 5.0

    def test_get_optimal_interval_legacy_playing(self):
        """Test optimal interval for legacy device playing."""
        capabilities = {"is_legacy_device": True}
        strategy = PollingStrategy(capabilities)

        interval = strategy.get_optimal_interval("master", is_playing=True)

        assert interval == 3.0

    def test_get_optimal_interval_legacy_idle(self):
        """Test optimal interval for legacy device idle."""
        capabilities = {"is_legacy_device": True}
        strategy = PollingStrategy(capabilities)

        interval = strategy.get_optimal_interval("master", is_playing=False)

        assert interval == 15.0

    def test_get_optimal_interval_legacy_slave(self):
        """Test optimal interval for legacy slave."""
        capabilities = {"is_legacy_device": True}
        strategy = PollingStrategy(capabilities)

        interval = strategy.get_optimal_interval("slave", is_playing=False)

        assert interval == 10.0

    def test_should_fetch_configuration_first_time(self):
        """Test configuration fetch on first check."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        assert strategy.should_fetch_configuration(0) is True

    def test_should_fetch_configuration_interval(self):
        """Test configuration fetch after interval."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        now = time.time()
        last_fetch = now - 61.0  # 61 seconds ago

        assert strategy.should_fetch_configuration(last_fetch, now=now) is True

    def test_should_fetch_configuration_too_soon(self):
        """Test configuration fetch before interval."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        now = time.time()
        last_fetch = now - 30.0  # 30 seconds ago

        assert strategy.should_fetch_configuration(last_fetch, now=now) is False

    def test_should_fetch_metadata_track_changed(self):
        """Test metadata fetch when track changed."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        assert strategy.should_fetch_metadata(track_changed=True, metadata_supported=True) is True

    def test_should_fetch_metadata_not_supported(self):
        """Test metadata fetch when not supported."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        assert strategy.should_fetch_metadata(track_changed=True, metadata_supported=False) is False

    def test_should_fetch_metadata_no_change(self):
        """Test metadata fetch when track not changed."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        assert strategy.should_fetch_metadata(track_changed=False, metadata_supported=True) is False

    def test_should_fetch_configuration_eq(self):
        """Test configuration fetch for EQ info."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        now = time.time()
        last_fetch = now - 61.0  # 61 seconds ago

        assert strategy.should_fetch_configuration(last_fetch, now=now) is True

    def test_should_fetch_audio_output(self):
        """Test audio output fetch."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        now = time.time()
        last_fetch = now - 61.0  # 61 seconds ago

        assert (
            strategy.should_fetch_audio_output(last_fetch, source_changed=False, audio_output_supported=True, now=now)
            is True
        )

    def test_should_fetch_audio_output_source_changed(self):
        """Test audio output fetch when source changed."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        now = time.time()
        last_fetch = now - 10.0  # 10 seconds ago (would normally not fetch)

        assert (
            strategy.should_fetch_audio_output(last_fetch, source_changed=True, audio_output_supported=True, now=now)
            is True
        )

    def test_should_fetch_audio_output_not_supported(self):
        """Test audio output fetch when not supported."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        assert strategy.should_fetch_audio_output(0, source_changed=False, audio_output_supported=False) is False

    def test_should_fetch_eq_info_first_time(self):
        """Test EQ info fetch on first check."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        assert strategy.should_fetch_eq_info(0, eq_supported=True) is True

    def test_should_fetch_eq_info_interval(self):
        """Test EQ info fetch after interval."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        now = time.time()
        last_fetch = now - 61.0  # 61 seconds ago

        assert strategy.should_fetch_eq_info(last_fetch, eq_supported=True, now=now) is True

    def test_should_fetch_eq_info_not_supported(self):
        """Test EQ info fetch when not supported."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        assert strategy.should_fetch_eq_info(0, eq_supported=False) is False

    def test_should_fetch_eq_info_too_soon(self):
        """Test EQ info fetch before interval."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        now = time.time()
        last_fetch = now - 30.0  # 30 seconds ago

        assert strategy.should_fetch_eq_info(last_fetch, eq_supported=True, now=now) is False

    def test_should_fetch_device_info_first_time(self):
        """Test device info fetch on first check."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        assert strategy.should_fetch_device_info(0) is True

    def test_should_fetch_device_info_interval(self):
        """Test device info fetch after interval."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        now = time.time()
        last_fetch = now - 61.0  # 61 seconds ago

        assert strategy.should_fetch_device_info(last_fetch, now=now) is True

    def test_should_fetch_device_info_too_soon(self):
        """Test device info fetch before interval."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        now = time.time()
        last_fetch = now - 30.0  # 30 seconds ago

        assert strategy.should_fetch_device_info(last_fetch, now=now) is False

    def test_should_fetch_multiroom_first_time(self):
        """Test multiroom fetch on first check."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        assert strategy.should_fetch_multiroom(0) is True

    def test_should_fetch_multiroom_interval(self):
        """Test multiroom fetch after interval."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        now = time.time()
        last_fetch = now - 16.0  # 16 seconds ago (more than 15s interval)

        assert strategy.should_fetch_multiroom(last_fetch, now=now) is True

    def test_should_fetch_multiroom_too_soon(self):
        """Test multiroom fetch before interval."""
        capabilities = {"is_legacy_device": False}
        strategy = PollingStrategy(capabilities)

        now = time.time()
        last_fetch = now - 10.0  # 10 seconds ago (less than 15s interval)

        assert strategy.should_fetch_multiroom(last_fetch, now=now) is False

    def test_should_fetch_trigger_out_first_time(self):
        """Test trigger fetch on first check when supported."""
        strategy = PollingStrategy({})
        assert strategy.should_fetch_trigger_out(0, trigger_out_supported=True) is True

    def test_should_fetch_trigger_out_not_supported(self):
        """Test trigger fetch skipped when capability false."""
        strategy = PollingStrategy({})
        assert strategy.should_fetch_trigger_out(0, trigger_out_supported=False) is False

    def test_should_fetch_trigger_out_interval(self):
        """Test trigger fetch after configuration interval."""
        strategy = PollingStrategy({})
        now = time.time()
        last_fetch = now - 61.0
        assert strategy.should_fetch_trigger_out(last_fetch, trigger_out_supported=True, now=now) is True

    def test_should_fetch_trigger_out_too_soon(self):
        """Test trigger fetch before configuration interval."""
        strategy = PollingStrategy({})
        now = time.time()
        last_fetch = now - 30.0
        assert strategy.should_fetch_trigger_out(last_fetch, trigger_out_supported=True, now=now) is False

    def test_should_fetch_led_indicator_first_time(self):
        """Test LED indicator fetch on first check when supported."""
        strategy = PollingStrategy({})
        assert strategy.should_fetch_led_indicator(0, led_supported=True) is True

    def test_should_fetch_led_indicator_not_supported(self):
        """Test LED indicator fetch skipped when unsupported."""
        strategy = PollingStrategy({})
        assert strategy.should_fetch_led_indicator(0, led_supported=False) is False


class TestTrackChangeDetector:
    """Test TrackChangeDetector class."""

    def test_init(self):
        """Test TrackChangeDetector initialization."""
        detector = TrackChangeDetector()

        assert detector._last_track_info is None

    def test_track_changed_first_time(self):
        """Test track change detection on first check."""
        detector = TrackChangeDetector()

        changed = detector.track_changed("Song", "Artist", "wifi", "http://artwork.jpg")

        assert changed is True
        assert detector._last_track_info == ("Song", "Artist", "wifi", "http://artwork.jpg")

    def test_track_changed_different_title(self):
        """Test track change when title changes."""
        detector = TrackChangeDetector()
        detector.track_changed("Song 1", "Artist", "wifi", "http://artwork.jpg")

        changed = detector.track_changed("Song 2", "Artist", "wifi", "http://artwork.jpg")

        assert changed is True

    def test_track_changed_different_artist(self):
        """Test track change when artist changes."""
        detector = TrackChangeDetector()
        detector.track_changed("Song", "Artist 1", "wifi", "http://artwork.jpg")

        changed = detector.track_changed("Song", "Artist 2", "wifi", "http://artwork.jpg")

        assert changed is True

    def test_track_changed_different_source(self):
        """Test track change when source changes."""
        detector = TrackChangeDetector()
        detector.track_changed("Song", "Artist", "wifi", "http://artwork.jpg")

        changed = detector.track_changed("Song", "Artist", "bluetooth", "http://artwork.jpg")

        assert changed is True

    def test_track_not_changed(self):
        """Test track not changed when same."""
        detector = TrackChangeDetector()
        detector.track_changed("Song", "Artist", "wifi", "http://artwork.jpg")

        changed = detector.track_changed("Song", "Artist", "wifi", "http://artwork.jpg")

        assert changed is False

    def test_track_changed_none_values(self):
        """Test track change with None values."""
        detector = TrackChangeDetector()
        detector.track_changed("Song", "Artist", "wifi", "http://artwork.jpg")

        changed = detector.track_changed(None, None, None, None)

        assert changed is True  # None != "Song"

    def test_reset(self):
        """Test resetting track change detector."""
        detector = TrackChangeDetector()
        detector.track_changed("Song", "Artist", "wifi", "http://artwork.jpg")

        detector.reset()

        assert detector._last_track_info is None


class TestFetchParallel:
    """Test fetch_parallel helper."""

    @pytest.mark.asyncio
    async def test_fetch_parallel_success(self):
        """Test parallel fetch with success."""

        async def task1():
            return "result1"

        async def task2():
            return "result2"

        results = await fetch_parallel(task1(), task2())

        assert results == ["result1", "result2"]

    @pytest.mark.asyncio
    async def test_fetch_parallel_with_exceptions(self):
        """Test parallel fetch with exceptions."""

        async def task1():
            return "result1"

        async def task2():
            raise ValueError("Error")

        results = await fetch_parallel(task1(), task2(), return_exceptions=True)

        assert results[0] == "result1"
        assert isinstance(results[1], ValueError)

    @pytest.mark.asyncio
    async def test_fetch_parallel_empty(self):
        """Test parallel fetch with no tasks."""
        results = await fetch_parallel()

        assert results == []
