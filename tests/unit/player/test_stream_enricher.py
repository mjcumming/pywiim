"""Unit tests for StreamEnricher.

Tests stream metadata enrichment for raw URL playback.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from pywiim.models import PlayerStatus


class TestStreamEnricher:
    """Test StreamEnricher class."""

    @pytest.fixture
    def mock_player(self, mock_client):
        """Create a mock Player instance."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._state_synchronizer = MagicMock()
        player._state_synchronizer.update_from_http = MagicMock()
        player._state_synchronizer.get_merged_state = MagicMock(return_value={})
        player._status_model = MagicMock()
        player._on_state_changed = None
        return player

    @pytest.fixture
    def stream_enricher(self, mock_player):
        """Create a StreamEnricher instance."""
        from pywiim.player.stream_enricher import StreamEnricher

        return StreamEnricher(mock_player)

    def test_init(self, stream_enricher, mock_player):
        """Test StreamEnricher initialization."""
        assert stream_enricher.player == mock_player
        assert stream_enricher.enabled is True
        assert stream_enricher._last_stream_url is None
        assert stream_enricher._last_stream_metadata is None
        assert stream_enricher._enrichment_task is None

    @pytest.mark.asyncio
    async def test_enrich_if_needed_disabled(self, stream_enricher):
        """Test enrichment when disabled."""
        stream_enricher.enabled = False
        status = PlayerStatus(source="wifi", title="http://example.com/stream.mp3", play_state="play")

        await stream_enricher.enrich_if_needed(status)

        # Should return early
        assert stream_enricher._enrichment_task is None

    @pytest.mark.asyncio
    async def test_enrich_if_needed_none_status(self, stream_enricher):
        """Test enrichment with None status."""
        await stream_enricher.enrich_if_needed(None)

        # Should return early
        assert stream_enricher._enrichment_task is None

    @pytest.mark.asyncio
    async def test_enrich_if_needed_not_playing(self, stream_enricher):
        """Test enrichment when not playing."""
        # Clean up any existing task first (including finished ones)
        if stream_enricher._enrichment_task:
            if not stream_enricher._enrichment_task.done():
                stream_enricher._enrichment_task.cancel()
                try:
                    await stream_enricher._enrichment_task
                except asyncio.CancelledError:
                    pass
            stream_enricher._enrichment_task = None
        stream_enricher._last_stream_url = None  # Reset state
        stream_enricher._last_stream_metadata = None  # Reset state

        # Test with play_state="pause" - should return early before checking URL
        # Note: "stop" gets normalized to "idle" by PlayerStatus, so use "pause" or "idle"
        status = PlayerStatus(source="wifi", title="http://example.com/stream.mp3", play_state="pause")

        await stream_enricher.enrich_if_needed(status)

        # Should return early - no task should be created
        # The early return check at line 52 should prevent task creation when play_state is "stop"
        # Wait a tiny bit to ensure any async operations complete
        await asyncio.sleep(0.001)
        assert stream_enricher._enrichment_task is None

    @pytest.mark.asyncio
    async def test_enrich_if_needed_wrong_source(self, stream_enricher):
        """Test enrichment with wrong source."""
        status = PlayerStatus(source="bluetooth", title="http://example.com/stream.mp3", play_state="play")

        await stream_enricher.enrich_if_needed(status)

        # Should return early
        assert stream_enricher._enrichment_task is None

    @pytest.mark.asyncio
    async def test_enrich_if_needed_no_url(self, stream_enricher):
        """Test enrichment when title is not a URL."""
        status = PlayerStatus(source="wifi", title="Regular Title", play_state="play")

        await stream_enricher.enrich_if_needed(status)

        # Should return early
        assert stream_enricher._enrichment_task is None

    @pytest.mark.asyncio
    async def test_enrich_if_needed_cached(self, stream_enricher, mock_player):
        """Test enrichment uses cached metadata."""
        from pywiim.player.stream import StreamMetadata

        status = PlayerStatus(source="wifi", title="http://example.com/stream.mp3", play_state="play")
        cached_metadata = StreamMetadata(title="Cached Title", artist="Cached Artist")
        stream_enricher._last_stream_url = "http://example.com/stream.mp3"
        stream_enricher._last_stream_metadata = cached_metadata
        mock_player._state_synchronizer.update_from_http = MagicMock()

        await stream_enricher.enrich_if_needed(status)

        # Should use cached metadata
        mock_player._state_synchronizer.update_from_http.assert_called()

    @pytest.mark.asyncio
    async def test_enrich_if_needed_starts_task(self, stream_enricher, mock_player):
        """Test enrichment starts new task for new URL."""
        status = PlayerStatus(source="wifi", title="http://example.com/stream.mp3", play_state="play")

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_task = MagicMock()
            mock_loop.return_value.create_task = MagicMock(return_value=mock_task)

            await stream_enricher.enrich_if_needed(status)

            assert stream_enricher._enrichment_task == mock_task
            assert stream_enricher._last_stream_url == "http://example.com/stream.mp3"

    @pytest.mark.asyncio
    async def test_enrich_if_needed_cancels_existing(self, stream_enricher):
        """Test enrichment cancels existing task for new URL."""
        existing_task = MagicMock()
        existing_task.done.return_value = False
        stream_enricher._enrichment_task = existing_task
        stream_enricher._last_stream_url = "http://example.com/old.mp3"

        status = PlayerStatus(source="wifi", title="http://example.com/new.mp3", play_state="play")

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_task = MagicMock()
            mock_loop.return_value.create_task = MagicMock(return_value=mock_task)

            await stream_enricher.enrich_if_needed(status)

            existing_task.cancel.assert_called_once()
            assert stream_enricher._enrichment_task == mock_task

    @pytest.mark.asyncio
    async def test_enrich_if_needed_no_event_loop(self, stream_enricher):
        """Test enrichment when no event loop."""
        status = PlayerStatus(source="wifi", title="http://example.com/stream.mp3", play_state="play")

        with patch("asyncio.get_running_loop", side_effect=RuntimeError("No event loop")):
            # Should not raise
            await stream_enricher.enrich_if_needed(status)

    @pytest.mark.asyncio
    async def test_fetch_and_apply_stream_metadata_success(self, stream_enricher, mock_player):
        """Test fetching and applying stream metadata successfully."""
        with patch("pywiim.player.stream_enricher.get_stream_metadata") as mock_get_metadata:
            from pywiim.player.stream import StreamMetadata

            mock_metadata = StreamMetadata(title="Stream Title", artist="Stream Artist")
            mock_get_metadata.return_value = mock_metadata
            mock_player._state_synchronizer.update_from_http = MagicMock()
            mock_player._state_synchronizer.get_merged_state = MagicMock(return_value={"title": "Stream Title"})
            mock_player._on_state_changed = MagicMock()

            await stream_enricher._fetch_and_apply_stream_metadata("http://example.com/stream.mp3")

            mock_get_metadata.assert_called_once()
            assert stream_enricher._last_stream_metadata == mock_metadata
            mock_player._state_synchronizer.update_from_http.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_and_apply_stream_metadata_cancelled(self, stream_enricher):
        """Test fetching stream metadata when cancelled."""
        with patch("pywiim.player.stream_enricher.get_stream_metadata", side_effect=asyncio.CancelledError()):
            # Should not raise
            await stream_enricher._fetch_and_apply_stream_metadata("http://example.com/stream.mp3")

    @pytest.mark.asyncio
    async def test_fetch_and_apply_stream_metadata_error(self, stream_enricher):
        """Test fetching stream metadata when error occurs."""
        with patch("pywiim.player.stream_enricher.get_stream_metadata", side_effect=Exception("Network error")):
            # Should not raise
            await stream_enricher._fetch_and_apply_stream_metadata("http://example.com/stream.mp3")

    @pytest.mark.asyncio
    async def test_fetch_and_apply_stream_metadata_no_metadata(self, stream_enricher, mock_player):
        """Test fetching stream metadata when no metadata returned."""
        with patch("pywiim.player.stream_enricher.get_stream_metadata", return_value=None):
            await stream_enricher._fetch_and_apply_stream_metadata("http://example.com/stream.mp3")

            # Should not update state
            mock_player._state_synchronizer.update_from_http.assert_not_called()

    def test_apply_stream_metadata(self, stream_enricher, mock_player):
        """Test applying stream metadata."""
        from pywiim.player.stream import StreamMetadata

        metadata = StreamMetadata(title="Stream Title", artist="Stream Artist")
        mock_player._state_synchronizer.update_from_http = MagicMock()
        mock_player._state_synchronizer.get_merged_state = MagicMock(
            return_value={"title": "Stream Title", "artist": "Stream Artist"}
        )

        stream_enricher._apply_stream_metadata(metadata)

        mock_player._state_synchronizer.update_from_http.assert_called_once()
        assert mock_player._status_model.title == "Stream Title"
        assert mock_player._status_model.artist == "Stream Artist"

    def test_apply_stream_metadata_station_name_fallback(self, stream_enricher, mock_player):
        """Test applying stream metadata uses station name as artist fallback."""
        from pywiim.player.stream import StreamMetadata

        metadata = StreamMetadata(title="Stream Title", station_name="Radio Station")
        mock_player._state_synchronizer.update_from_http = MagicMock()
        mock_player._state_synchronizer.get_merged_state = MagicMock(
            return_value={"title": "Stream Title", "artist": "Radio Station"}
        )

        stream_enricher._apply_stream_metadata(metadata)

        call_args = mock_player._state_synchronizer.update_from_http.call_args
        update_dict = call_args[0][0]
        assert update_dict["artist"] == "Radio Station"
