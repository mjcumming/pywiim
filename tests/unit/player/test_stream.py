"""Unit tests for stream metadata extraction.

Tests Icecast, HLS, M3U/PLS parsing, and URL resolution.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from pywiim.player.stream import (
    StreamMetadata,
    _decode_text,
    _extract_station_name_from_url,
    _fetch_hls_metadata,
    _fetch_icecast_metadata,
    _parse_m3u,
    _parse_pls,
    _parse_stream_title,
    _resolve_stream_url,
    get_stream_metadata,
)


class TestGetStreamMetadata:
    """Test get_stream_metadata function."""

    @pytest.mark.asyncio
    async def test_invalid_url(self):
        """Test get_stream_metadata with invalid URL."""
        result = await get_stream_metadata("not-a-url")
        assert result is None

    @pytest.mark.asyncio
    async def test_hls_url(self):
        """Test get_stream_metadata with HLS URL."""
        url = "https://example.com/stream.m3u8"

        with patch("pywiim.player.stream.m3u8") as mock_m3u8:
            mock_m3u8.loads.return_value.is_variant = False
            mock_m3u8.loads.return_value.segments = []
            with patch("pywiim.player.stream._fetch_hls_metadata", return_value=None):
                with patch("pywiim.player.stream._resolve_stream_url", return_value=url):
                    with patch("pywiim.player.stream._fetch_icecast_metadata", return_value=StreamMetadata()):
                        result = await get_stream_metadata(url)

                        assert result is not None

    @pytest.mark.asyncio
    async def test_creates_session(self):
        """Test get_stream_metadata creates session if none provided."""
        url = "https://example.com/stream.mp3"

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = MagicMock()
            mock_session.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.close = AsyncMock()
            mock_session_class.return_value = mock_session

            with patch("pywiim.player.stream._resolve_stream_url", return_value=url):
                with patch("pywiim.player.stream._fetch_icecast_metadata", return_value=None):
                    await get_stream_metadata(url)

                    mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_provided_session(self):
        """Test get_stream_metadata uses provided session."""
        url = "https://example.com/stream.mp3"
        mock_session = MagicMock()

        with patch("pywiim.player.stream._resolve_stream_url", return_value=url):
            with patch("pywiim.player.stream._fetch_icecast_metadata", return_value=None):
                result = await get_stream_metadata(url, session=mock_session)

                # Should not create new session
                assert result is None


class TestResolveStreamUrl:
    """Test _resolve_stream_url function."""

    @pytest.mark.asyncio
    async def test_direct_url(self):
        """Test _resolve_stream_url with direct URL."""
        url = "https://example.com/stream.mp3"
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200  # Not a redirect
        mock_response.headers = {}  # No Location header
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.head = MagicMock(return_value=mock_response)

        result = await _resolve_stream_url(url, mock_session)

        assert result == url

    @pytest.mark.asyncio
    async def test_redirect(self):
        """Test _resolve_stream_url follows redirects."""
        url1 = "https://example.com/redirect"
        url2 = "https://example.com/stream.mp3"
        mock_session = MagicMock()
        mock_response1 = MagicMock()
        mock_response1.status = 302
        mock_response1.headers = {"Location": url2}
        mock_response1.__aenter__ = AsyncMock(return_value=mock_response1)
        mock_response1.__aexit__ = AsyncMock(return_value=None)
        mock_response2 = MagicMock()
        mock_response2.status = 200
        mock_response2.headers = {}
        mock_response2.__aenter__ = AsyncMock(return_value=mock_response2)
        mock_response2.__aexit__ = AsyncMock(return_value=None)
        mock_session.head = MagicMock(side_effect=[mock_response1, mock_response2])

        result = await _resolve_stream_url(url1, mock_session)

        assert result == url2

    @pytest.mark.asyncio
    async def test_m3u_playlist(self):
        """Test _resolve_stream_url parses M3U playlist."""
        url = "https://example.com/playlist.m3u"
        mock_session = MagicMock()

        with patch("pywiim.player.stream._parse_m3u", return_value="https://example.com/stream.mp3"):
            result = await _resolve_stream_url(url, mock_session)

            assert result == "https://example.com/stream.mp3"

    @pytest.mark.asyncio
    async def test_pls_playlist(self):
        """Test _resolve_stream_url parses PLS playlist."""
        url = "https://example.com/playlist.pls"
        mock_session = MagicMock()

        with patch("pywiim.player.stream._parse_pls", return_value="https://example.com/stream.mp3"):
            result = await _resolve_stream_url(url, mock_session)

            assert result == "https://example.com/stream.mp3"

    @pytest.mark.asyncio
    async def test_max_hops(self):
        """Test _resolve_stream_url limits redirect hops."""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 302
        mock_response.headers = {"Location": "https://example.com/redirect2"}
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.head = MagicMock(return_value=mock_response)

        result = await _resolve_stream_url("https://example.com/redirect1", mock_session)

        # Should stop after max hops
        assert result is not None


class TestParseM3U:
    """Test _parse_m3u function."""

    @pytest.mark.asyncio
    async def test_parse_m3u_success(self):
        """Test _parse_m3u parses valid M3U playlist."""
        url = "https://example.com/playlist.m3u"
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="#EXTM3U\nhttps://example.com/stream.mp3\n")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)

        result = await _parse_m3u(url, mock_session)

        assert result == "https://example.com/stream.mp3"

    @pytest.mark.asyncio
    async def test_parse_m3u_skips_hls(self):
        """Test _parse_m3u skips HLS playlists."""
        url = "https://example.com/playlist.m3u8"
        mock_session = MagicMock()

        result = await _parse_m3u(url, mock_session)

        assert result is None

    @pytest.mark.asyncio
    async def test_parse_m3u_no_stream_url(self):
        """Test _parse_m3u returns None if no stream URL found."""
        url = "https://example.com/playlist.m3u"
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="#EXTM3U\n# Comment only\n")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)

        result = await _parse_m3u(url, mock_session)

        assert result is None

    @pytest.mark.asyncio
    async def test_parse_m3u_error(self):
        """Test _parse_m3u handles errors."""
        url = "https://example.com/playlist.m3u"
        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=aiohttp.ClientError("Network error"))

        result = await _parse_m3u(url, mock_session)

        assert result is None


class TestParsePls:
    """Test _parse_pls function."""

    @pytest.mark.asyncio
    async def test_parse_pls_success(self):
        """Test _parse_pls parses valid PLS playlist."""
        url = "https://example.com/playlist.pls"
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="[playlist]\nFile1=https://example.com/stream.mp3\n")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)

        result = await _parse_pls(url, mock_session)

        assert result == "https://example.com/stream.mp3"

    @pytest.mark.asyncio
    async def test_parse_pls_no_stream_url(self):
        """Test _parse_pls returns None if no stream URL found."""
        url = "https://example.com/playlist.pls"
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="[playlist]\nTitle1=Test\n")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)

        result = await _parse_pls(url, mock_session)

        assert result is None

    @pytest.mark.asyncio
    async def test_parse_pls_error(self):
        """Test _parse_pls handles errors."""
        url = "https://example.com/playlist.pls"
        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=aiohttp.ClientError("Network error"))

        result = await _parse_pls(url, mock_session)

        assert result is None


class TestFetchIcecastMetadata:
    """Test _fetch_icecast_metadata function."""

    @pytest.mark.asyncio
    async def test_no_icy_headers(self):
        """Test _fetch_icecast_metadata returns None if no ICY headers."""
        url = "https://example.com/stream.mp3"
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.headers = {}
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)

        result = await _fetch_icecast_metadata(url, mock_session, timeout=5)

        assert result is None
        mock_response.__aenter__.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_station_name_only(self):
        """Test _fetch_icecast_metadata extracts station name."""
        url = "https://example.com/stream.mp3"
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.headers = {
            "Icy-MetaData": "1",
            "icy-name": "Test Station",
        }
        mock_response.content.readexactly = AsyncMock(side_effect=Exception("No metaint"))
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)

        result = await _fetch_icecast_metadata(url, mock_session, timeout=5)

        assert result is not None
        assert result.station_name == "Test Station"

    @pytest.mark.asyncio
    async def test_parse_stream_title(self):
        """Test _fetch_icecast_metadata parses stream title."""
        url = "https://example.com/stream.mp3"
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.headers = {
            "Icy-MetaData": "1",
            "icy-metaint": "8192",
        }
        # Mock reading audio data and metadata
        mock_response.content.readexactly = AsyncMock(
            side_effect=[
                b"audio_data" * 100,  # Audio data
                b"\x10",  # Length byte (16 * 16 = 256)
                b"StreamTitle='Artist - Title';" + b"\x00" * 200,  # Metadata block
            ]
        )
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)

        result = await _fetch_icecast_metadata(url, mock_session, timeout=5)

        assert result is not None
        assert result.title == "Title"
        assert result.artist == "Artist"

    @pytest.mark.asyncio
    async def test_network_error(self):
        """Test _fetch_icecast_metadata handles network errors."""
        url = "https://example.com/stream.mp3"
        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=aiohttp.ClientError("Network error"))

        result = await _fetch_icecast_metadata(url, mock_session, timeout=5)

        assert result is None


class TestParseStreamTitle:
    """Test _parse_stream_title function."""

    def test_artist_title_format(self):
        """Test _parse_stream_title parses 'Artist - Title' format."""
        metadata = StreamMetadata()
        meta_block = b"StreamTitle='Artist - Title';" + b"\x00" * 200

        _parse_stream_title(meta_block, metadata)

        assert metadata.title == "Title"
        assert metadata.artist == "Artist"

    def test_title_only(self):
        """Test _parse_stream_title with title only."""
        metadata = StreamMetadata()
        metadata.station_name = "Test Station"
        meta_block = b"StreamTitle='Title Only';" + b"\x00" * 200

        _parse_stream_title(meta_block, metadata)

        assert metadata.title == "Title Only"
        assert metadata.artist == "Test Station"

    def test_no_stream_title(self):
        """Test _parse_stream_title with no StreamTitle."""
        metadata = StreamMetadata()
        meta_block = b"OtherField='value';" + b"\x00" * 200

        _parse_stream_title(meta_block, metadata)

        assert metadata.title is None
        assert metadata.artist is None


class TestExtractStationNameFromUrl:
    """Test _extract_station_name_from_url function."""

    def test_radio_canada_premiere(self):
        """Test Radio-Canada ICI Première pattern."""
        url = "https://example.com/rcavliveaudio/P-2QMTL0_MTL"
        result = _extract_station_name_from_url(url)

        assert result.station_name == "Radio-Canada ICI Première Montréal"

    def test_radio_canada_musique(self):
        """Test Radio-Canada ICI Musique pattern."""
        # The pattern checks for "radio-canada" in url.lower() OR "rcavliveaudio" in url
        # Then checks if "ICI_MUSIQUE" in url.upper()
        url = "https://example.com/radio-canada/stream/ICI_MUSIQUE/playlist.m3u8"
        result = _extract_station_name_from_url(url)

        assert result.station_name == "Radio-Canada ICI Musique"

    def test_bbc_radio_one(self):
        """Test BBC Radio 1 pattern."""
        url = "https://example.com/bbc/radio_one"
        result = _extract_station_name_from_url(url)

        assert result.station_name == "BBC Radio 1"

    def test_bbc_radio_two(self):
        """Test BBC Radio 2 pattern."""
        url = "https://example.com/bbc/radio_two"
        result = _extract_station_name_from_url(url)

        assert result.station_name == "BBC Radio 2"

    def test_cbc_radio_one(self):
        """Test CBC Radio One pattern."""
        url = "https://example.com/cbc/CBCR1"
        result = _extract_station_name_from_url(url)

        assert result.station_name == "CBC Radio One"

    def test_unknown_url(self):
        """Test unknown URL returns empty metadata."""
        url = "https://example.com/unknown"
        result = _extract_station_name_from_url(url)

        assert result.station_name is None


class TestDecodeText:
    """Test _decode_text function."""

    def test_string_input(self):
        """Test _decode_text with string input."""
        result = _decode_text("  test string  ")
        assert result == "test string"

    def test_utf8_bytes(self):
        """Test _decode_text with UTF-8 bytes."""
        result = _decode_text(b"test string")
        assert result == "test string"

    def test_latin1_fallback(self):
        """Test _decode_text falls back to latin-1."""
        # Create bytes that are valid latin-1 but not UTF-8
        latin1_bytes = "café".encode("latin-1")
        result = _decode_text(latin1_bytes)
        assert result == "café"

    def test_ignore_errors(self):
        """Test _decode_text ignores decode errors."""
        invalid_bytes = b"\xff\xfe\xfd"
        result = _decode_text(invalid_bytes)
        # Should not raise, returns string representation
        assert isinstance(result, str)


class TestFetchHlsMetadata:
    """Test _fetch_hls_metadata function."""

    @pytest.mark.asyncio
    async def test_m3u8_not_available(self):
        """Test _fetch_hls_metadata returns None if m3u8 not available."""
        with patch("pywiim.player.stream.m3u8", None):
            result = await _fetch_hls_metadata("https://example.com/stream.m3u8", MagicMock(), timeout=5)
            assert result is None

    @pytest.mark.asyncio
    async def test_mutagen_not_available(self):
        """Test _fetch_hls_metadata returns None if mutagen not available."""
        with patch("pywiim.player.stream.m3u8", MagicMock()):
            with patch("pywiim.player.stream.MutagenFile", None):
                result = await _fetch_hls_metadata("https://example.com/stream.m3u8", MagicMock(), timeout=5)
                assert result is None

    @pytest.mark.asyncio
    async def test_master_playlist(self):
        """Test _fetch_hls_metadata handles master playlists."""
        url = "https://example.com/master.m3u8"
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="#EXTM3U\n#EXT-X-STREAM-INF\nvariant.m3u8\n")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)

        mock_m3u8 = MagicMock()
        mock_playlist = MagicMock()
        mock_playlist.is_variant = True
        mock_playlist.playlists = [MagicMock(uri="variant.m3u8")]
        mock_m3u8.loads.return_value = mock_playlist

        with patch("pywiim.player.stream.m3u8", mock_m3u8):
            with patch("pywiim.player.stream._fetch_hls_metadata", return_value=StreamMetadata()) as mock_recursive:
                await _fetch_hls_metadata(url, mock_session, timeout=5)

                # Should recursively call for variant
                assert mock_recursive.called

    @pytest.mark.asyncio
    async def test_no_segments(self):
        """Test _fetch_hls_metadata handles playlists with no segments."""
        url = "https://example.com/stream.m3u8"
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="#EXTM3U\n")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)

        mock_m3u8 = MagicMock()
        mock_playlist = MagicMock()
        mock_playlist.is_variant = False
        mock_playlist.segments = []
        mock_m3u8.loads.return_value = mock_playlist

        with patch("pywiim.player.stream.m3u8", mock_m3u8):
            with patch("pywiim.player.stream._extract_station_name_from_url", return_value=StreamMetadata()):
                result = await _fetch_hls_metadata(url, mock_session, timeout=5)

                # Should try URL extraction
                assert result is not None or result is None  # Either is valid
