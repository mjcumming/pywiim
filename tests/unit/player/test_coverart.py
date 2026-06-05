"""Unit tests for CoverArtManager.

Tests cover art fetching, caching, and URL hashing.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from pywiim.api.constants import DEFAULT_WIIM_LOGO_URL


class TestCoverArtManager:
    """Test CoverArtManager class."""

    @pytest.fixture
    def mock_player(self, mock_client):
        """Create a mock Player instance."""
        from pywiim.player import Player

        player = Player(mock_client)
        # Initialize cover art cache attributes
        player._cover_art_cache = {}
        player._cover_art_cache_ttl = 3600
        player._cover_art_cache_max_size = 10
        return player

    @pytest.fixture
    def cover_art_manager(self, mock_player):
        """Create a CoverArtManager instance."""
        from pywiim.player.coverart import CoverArtManager

        return CoverArtManager(mock_player)

    def test_get_url_hash(self, cover_art_manager):
        """Test URL hash generation."""
        hash1 = cover_art_manager._get_url_hash("https://example.com/image.jpg")
        hash2 = cover_art_manager._get_url_hash("https://example.com/image.jpg")
        hash3 = cover_art_manager._get_url_hash("https://example.com/other.jpg")

        # Same URL should produce same hash
        assert hash1 == hash2
        # Different URLs should produce different hashes
        assert hash1 != hash3
        # Hash should be a hex string
        assert len(hash1) == 32  # MD5 hex digest length

    def test_cleanup_cover_art_cache_expired(self, cover_art_manager, mock_player):
        """Test cache cleanup removes expired entries."""
        import time

        # Add expired entry
        url_hash = cover_art_manager._get_url_hash("https://example.com/old.jpg")
        mock_player._cover_art_cache[url_hash] = (b"image_data", "image/jpeg", time.time() - 4000)

        # Add non-expired entry
        url_hash2 = cover_art_manager._get_url_hash("https://example.com/new.jpg")
        mock_player._cover_art_cache[url_hash2] = (b"image_data", "image/jpeg", time.time())

        cover_art_manager._cleanup_cover_art_cache()

        # Expired entry should be removed
        assert url_hash not in mock_player._cover_art_cache
        # Non-expired entry should remain
        assert url_hash2 in mock_player._cover_art_cache

    def test_cleanup_cover_art_cache_size_limit(self, cover_art_manager, mock_player):
        """Test cache cleanup enforces size limit."""
        import time

        # Fill cache beyond max size
        for i in range(15):
            url_hash = cover_art_manager._get_url_hash(f"https://example.com/image{i}.jpg")
            mock_player._cover_art_cache[url_hash] = (b"image_data", "image/jpeg", time.time() + i)

        cover_art_manager._cleanup_cover_art_cache()

        # Cache should be at max size
        assert len(mock_player._cover_art_cache) <= mock_player._cover_art_cache_max_size

    @pytest.mark.asyncio
    async def test_fetch_cover_art_embedded_logo(self, cover_art_manager):
        """Test fetch_cover_art returns embedded logo for sentinel URL."""
        result = await cover_art_manager.fetch_cover_art(DEFAULT_WIIM_LOGO_URL)

        assert result is not None
        image_bytes, content_type = result
        assert isinstance(image_bytes, bytes)
        assert content_type == "image/png"
        assert len(image_bytes) > 0

    @pytest.mark.asyncio
    async def test_fetch_cover_art_none_url(self, cover_art_manager, mock_player):
        """Test fetch_cover_art with None URL uses media_image_url."""
        from pywiim.player.properties import PlayerProperties

        # Mock PlayerProperties to return sentinel URL
        with patch.object(PlayerProperties, "media_image_url", new=DEFAULT_WIIM_LOGO_URL):
            result = await cover_art_manager.fetch_cover_art(None)

            assert result is not None
            image_bytes, content_type = result
            assert content_type == "image/png"

    @pytest.mark.asyncio
    async def test_fetch_cover_art_empty_url(self, cover_art_manager):
        """Test fetch_cover_art with empty URL returns embedded logo."""
        result = await cover_art_manager.fetch_cover_art("")

        assert result is not None
        image_bytes, content_type = result
        assert content_type == "image/png"

    @pytest.mark.asyncio
    async def test_fetch_cover_art_cache_hit(self, cover_art_manager, mock_player):
        """Test fetch_cover_art returns cached entry."""
        import time

        url = "https://example.com/image.jpg"
        url_hash = cover_art_manager._get_url_hash(url)
        cached_data = (b"cached_image", "image/jpeg", time.time())
        mock_player._cover_art_cache[url_hash] = cached_data

        # Mock session to ensure we don't make HTTP call
        mock_player.client._session = None

        result = await cover_art_manager.fetch_cover_art(url)

        assert result == (b"cached_image", "image/jpeg")

    @pytest.mark.asyncio
    async def test_fetch_cover_art_https_success(self, cover_art_manager, mock_player):
        """Test fetch_cover_art fetches HTTPS URL successfully."""
        url = "https://example.com/image.jpg"
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "image/jpeg"}
        mock_response.read = AsyncMock(return_value=b"image_data")

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_player.client._session = MagicMock()
        mock_player.client._session.get = MagicMock(return_value=mock_session)
        mock_player.client._get_ssl_context = AsyncMock(return_value=None)

        result = await cover_art_manager.fetch_cover_art(url)

        assert result is not None
        image_bytes, content_type = result
        assert image_bytes == b"image_data"
        assert content_type == "image/jpeg"

    @pytest.mark.asyncio
    async def test_fetch_cover_art_http_success(self, cover_art_manager, mock_player):
        """Test fetch_cover_art fetches HTTP URL successfully."""
        url = "http://example.com/image.jpg"
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "image/png"}
        mock_response.read = AsyncMock(return_value=b"image_data")

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_player.client._session = MagicMock()
        mock_player.client._session.get = MagicMock(return_value=mock_session)

        result = await cover_art_manager.fetch_cover_art(url)

        assert result is not None
        image_bytes, content_type = result
        assert image_bytes == b"image_data"
        assert content_type == "image/png"

    @pytest.mark.asyncio
    async def test_fetch_cover_art_http_error(self, cover_art_manager, mock_player):
        """Test fetch_cover_art handles HTTP error."""
        url = "https://example.com/image.jpg"
        mock_response = MagicMock()
        mock_response.status = 404

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_player.client._session = MagicMock()
        mock_player.client._session.get = MagicMock(return_value=mock_session)
        mock_player.client._get_ssl_context = AsyncMock(return_value=None)

        result = await cover_art_manager.fetch_cover_art(url)

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_cover_art_network_error(self, cover_art_manager, mock_player):
        """Test fetch_cover_art handles network errors."""
        url = "https://example.com/image.jpg"

        mock_player.client._session = MagicMock()
        mock_player.client._session.get = MagicMock(side_effect=aiohttp.ClientError("Network error"))
        mock_player.client._get_ssl_context = AsyncMock(return_value=None)

        result = await cover_art_manager.fetch_cover_art(url)

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_cover_art_creates_session(self, cover_art_manager, mock_player):
        """Test fetch_cover_art creates session if none exists."""
        url = "https://example.com/image.jpg"
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "image/jpeg"}
        mock_response.read = AsyncMock(return_value=b"image_data")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.close = AsyncMock()

        mock_player.client._session = None
        mock_player.client._get_ssl_context = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await cover_art_manager.fetch_cover_art(url)

            assert result is not None
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_cover_art_content_type_fallback(self, cover_art_manager, mock_player):
        """Test fetch_cover_art uses image/jpeg fallback for non-image content type."""
        url = "https://example.com/image.jpg"
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "application/octet-stream"}
        mock_response.read = AsyncMock(return_value=b"image_data")

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_player.client._session = MagicMock()
        mock_player.client._session.get = MagicMock(return_value=mock_session)
        mock_player.client._get_ssl_context = AsyncMock(return_value=None)

        result = await cover_art_manager.fetch_cover_art(url)

        assert result is not None
        _, content_type = result
        assert content_type == "image/jpeg"

    @pytest.mark.asyncio
    async def test_get_cover_art_bytes(self, cover_art_manager):
        """Test get_cover_art_bytes convenience method."""
        with patch.object(cover_art_manager, "fetch_cover_art", return_value=(b"image_data", "image/jpeg")):
            result = await cover_art_manager.get_cover_art_bytes("https://example.com/image.jpg")

            assert result == b"image_data"

    @pytest.mark.asyncio
    async def test_get_cover_art_bytes_none(self, cover_art_manager):
        """Test get_cover_art_bytes returns None when fetch fails."""
        with patch.object(cover_art_manager, "fetch_cover_art", return_value=None):
            result = await cover_art_manager.get_cover_art_bytes("https://example.com/image.jpg")

            assert result is None

    # === Track change detection and metadata enrichment tests ===

    def test_check_track_changed(self, cover_art_manager):
        """Test checking if track changed."""
        merged = {"title": "New Track", "artist": "New Artist", "album": "New Album"}
        cover_art_manager._last_track_signature = None

        result = cover_art_manager.check_track_changed(merged)

        # First track, should not be changed
        assert result is False
        assert cover_art_manager._last_track_signature == "New Track|New Artist|New Album"

    def test_check_track_changed_track_changed(self, cover_art_manager):
        """Test checking when track actually changed."""
        merged = {"title": "New Track", "artist": "New Artist", "album": "New Album"}
        cover_art_manager._last_track_signature = "Old Track|Old Artist|Old Album"

        result = cover_art_manager.check_track_changed(merged)

        assert result is True
        assert cover_art_manager._last_track_signature == "New Track|New Artist|New Album"

    def test_check_track_changed_same_track(self, cover_art_manager):
        """Test checking when track is the same."""
        merged = {"title": "Same Track", "artist": "Same Artist", "album": "Same Album"}
        cover_art_manager._last_track_signature = "Same Track|Same Artist|Same Album"

        result = cover_art_manager.check_track_changed(merged)

        assert result is False
        assert cover_art_manager._last_track_signature == "Same Track|Same Artist|Same Album"

    @pytest.mark.asyncio
    async def test_enrich_metadata_on_track_change_track_changed(self, cover_art_manager, mock_player):
        """Test enriching metadata when track changed."""
        merged = {"title": "New Track", "artist": "New Artist", "image_url": None}
        cover_art_manager._last_track_signature = "Old Track|Old Artist|Old Album"
        mock_player.client._capabilities = {"supports_metadata": True}
        mock_player.client.get_meta_info = MagicMock()
        cover_art_manager._fetch_artwork_from_metainfo = AsyncMock()

        await cover_art_manager.enrich_metadata_on_track_change(merged)

        cover_art_manager._fetch_artwork_from_metainfo.assert_awaited_once_with(merged)

    @pytest.mark.asyncio
    async def test_enrich_metadata_on_track_change_unknown_metadata(self, cover_art_manager, mock_player):
        """Test enriching metadata when metadata is Unknown."""
        merged = {"title": "Unknown", "artist": "Unknown", "image_url": "http://example.com/art.jpg"}
        cover_art_manager._last_track_signature = None
        mock_player.client._capabilities = {"supports_metadata": True}
        mock_player.client.get_meta_info = MagicMock()
        cover_art_manager._fetch_artwork_from_metainfo = AsyncMock()

        await cover_art_manager.enrich_metadata_on_track_change(merged)

        cover_art_manager._fetch_artwork_from_metainfo.assert_awaited_once_with(merged)

    @pytest.mark.asyncio
    async def test_enrich_metadata_on_track_change_best_effort_when_capability_false(
        self, cover_art_manager, mock_player
    ):
        """Test enriching metadata still runs best-effort when capability is false."""
        merged = {"title": "New Track", "artist": "New Artist", "image_url": None}
        cover_art_manager._last_track_signature = "Old Track|Old Artist|Old Album"
        mock_player.client._capabilities = {"supports_metadata": False}
        mock_player.client.get_meta_info = MagicMock()
        cover_art_manager._fetch_artwork_from_metainfo = AsyncMock()

        await cover_art_manager.enrich_metadata_on_track_change(merged)

        cover_art_manager._fetch_artwork_from_metainfo.assert_awaited_once_with(merged)

    @pytest.mark.asyncio
    async def test_enrich_metadata_on_track_change_valid_artwork(self, cover_art_manager, mock_player):
        """Test enriching metadata when artwork is valid."""
        merged = {"title": "New Track", "artist": "New Artist", "image_url": "http://example.com/art.jpg"}
        cover_art_manager._last_track_signature = "Old Track|Old Artist|Old Album"
        mock_player.client._capabilities = {"supports_metadata": True}

        await cover_art_manager.enrich_metadata_on_track_change(merged)

        # Should not schedule fetch if artwork is valid
        assert cover_art_manager._artwork_fetch_task is None

    @pytest.mark.asyncio
    async def test_fetch_artwork_from_metainfo_success(self, cover_art_manager, mock_player):
        """Test fetching artwork from meta info successfully."""
        from pywiim.models import PlayerStatus

        merged = {"title": "Unknown", "artist": "Unknown"}
        mock_player.client.get_meta_info = AsyncMock(
            return_value={
                "metaData": {"title": "Real Title", "artist": "Real Artist", "cover": "http://example.com/art.jpg"}
            }
        )
        mock_player._state_synchronizer.update_from_http = MagicMock()
        mock_player._state_synchronizer.get_merged_state = MagicMock(
            return_value={"title": "Real Title", "artist": "Real Artist", "image_url": "http://example.com/art.jpg"}
        )
        mock_player._status_model = PlayerStatus(title="Unknown", artist="Unknown")
        mock_player._on_state_changed = MagicMock()

        await cover_art_manager._fetch_artwork_from_metainfo(merged)

        mock_player.client.get_meta_info.assert_called_once()
        mock_player._state_synchronizer.update_from_http.assert_called_once()
        assert mock_player._status_model.title == "Real Title"
        assert mock_player._status_model.artist == "Real Artist"

    @pytest.mark.asyncio
    async def test_fetch_artwork_from_metainfo_cancelled(self, cover_art_manager, mock_player):
        """Test fetching artwork when cancelled."""
        import asyncio

        merged = {"title": "Unknown", "artist": "Unknown"}
        if not hasattr(mock_player.client, "get_meta_info"):
            pytest.skip("get_meta_info not available")
        mock_player.client.get_meta_info = AsyncMock(side_effect=asyncio.CancelledError())

        # Should not raise
        try:
            await cover_art_manager._fetch_artwork_from_metainfo(merged)
        except asyncio.CancelledError:
            pytest.fail("CancelledError should be caught")

    @pytest.mark.asyncio
    async def test_fetch_artwork_from_metainfo_error(self, cover_art_manager, mock_player):
        """Test fetching artwork when error occurs."""
        merged = {"title": "Unknown", "artist": "Unknown"}
        mock_player.client.get_meta_info = AsyncMock(side_effect=Exception("Network error"))

        # Should not raise
        await cover_art_manager._fetch_artwork_from_metainfo(merged)

    @pytest.mark.asyncio
    async def test_fetch_artwork_from_metainfo_no_meta_info(self, cover_art_manager, mock_player):
        """Test fetching artwork when get_meta_info not available."""
        merged = {"title": "Unknown", "artist": "Unknown"}
        if not hasattr(mock_player.client, "get_meta_info"):
            # Skip if method doesn't exist
            return

        mock_player.client.get_meta_info = AsyncMock(return_value={})

        await cover_art_manager._fetch_artwork_from_metainfo(merged)

        # Should not crash

    @pytest.mark.asyncio
    async def test_fetch_artwork_falls_back_to_getinfoex(self, cover_art_manager, mock_player):
        """Test GetInfoEx fallback when getMetaInfo has no artwork."""
        from pywiim.models import PlayerStatus

        merged = {"title": "Song", "artist": "Artist", "album": "Album"}
        mock_player.client.get_meta_info = AsyncMock(return_value={"metaData": {"title": "Song", "artist": "Artist"}})
        mock_player._state_synchronizer.update_from_http = MagicMock()
        mock_player._state_synchronizer.get_merged_state = MagicMock(return_value=merged)
        mock_player._status_model = PlayerStatus(title="Song", artist="Artist")
        mock_player._on_state_changed = MagicMock()
        mock_player._ensure_upnp_client = AsyncMock(return_value=True)

        mock_upnp = MagicMock()
        mock_upnp.av_transport = MagicMock()
        mock_upnp.get_info_ex = AsyncMock(
            return_value={
                "title": "Song",
                "artist": "Artist",
                "image_url": "https://example.com/getinfoex.jpg",
            }
        )
        mock_player._upnp_client = mock_upnp

        await cover_art_manager._fetch_artwork_from_metainfo(merged)

        mock_upnp.get_info_ex.assert_called_once()
        mock_player._state_synchronizer.update_from_http.assert_called()
        assert mock_player._getinfoex_supported is True

    @pytest.mark.asyncio
    async def test_enrich_metadata_when_artwork_missing(self, cover_art_manager, mock_player):
        """Schedule enrichment when artwork is missing but metadata exists."""
        merged = {"title": "Song", "artist": "Artist", "album": "Album", "image_url": None}
        cover_art_manager._last_track_signature = "Song|Artist|Album"
        cover_art_manager._fetch_artwork_from_metainfo = AsyncMock()

        await cover_art_manager.enrich_metadata_on_track_change(merged)

        cover_art_manager._fetch_artwork_from_metainfo.assert_awaited_once_with(merged)
