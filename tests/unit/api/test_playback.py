"""Unit tests for PlaybackAPI mixin.

Tests playback controls, volume, mute, source selection, and URL playback.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pywiim.api.base import ApiResponse
from pywiim.exceptions import WiiMError


class TestPlaybackAPI:
    """Test PlaybackAPI mixin methods."""

    @pytest.mark.asyncio
    async def test_play(self, mock_client):
        """Test play command."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.play()

        mock_client._request.assert_called_once()
        call_args = mock_client._request.call_args[0]
        assert "/httpapi.asp?command=setPlayerCmd:play" in call_args[0]

    @pytest.mark.asyncio
    async def test_pause(self, mock_client):
        """Test pause command."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.pause()

        mock_client._request.assert_called_once()
        call_args = mock_client._request.call_args[0]
        assert "/httpapi.asp?command=setPlayerCmd:pause" in call_args[0]

    @pytest.mark.asyncio
    async def test_resume(self, mock_client):
        """Test resume command."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.resume()

        mock_client._request.assert_called_once()
        call_args = mock_client._request.call_args[0]
        assert "/httpapi.asp?command=setPlayerCmd:resume" in call_args[0]

    @pytest.mark.asyncio
    async def test_stop(self, mock_client):
        """Test stop command."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.stop()

        mock_client._request.assert_called_once()
        call_args = mock_client._request.call_args[0]
        assert "/httpapi.asp?command=setPlayerCmd:stop" in call_args[0]

    @pytest.mark.asyncio
    async def test_next_track(self, mock_client):
        """Test next track command."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.next_track()

        mock_client._request.assert_called_once()
        call_args = mock_client._request.call_args[0]
        assert "/httpapi.asp?command=setPlayerCmd:next" in call_args[0]

    @pytest.mark.asyncio
    async def test_previous_track(self, mock_client):
        """Test previous track command."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.previous_track()

        mock_client._request.assert_called_once()
        call_args = mock_client._request.call_args[0]
        assert "/httpapi.asp?command=setPlayerCmd:prev" in call_args[0]

    @pytest.mark.asyncio
    async def test_seek(self, mock_client):
        """Test seek command."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.seek(120)

        mock_client._request.assert_called_once()
        call_args = mock_client._request.call_args[0]
        assert "/httpapi.asp?command=setPlayerCmd:seek:120" in call_args[0]

    @pytest.mark.asyncio
    async def test_seek_zero(self, mock_client):
        """Test seek to position 0."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.seek(0)

        call_args = mock_client._request.call_args[0]
        assert "setPlayerCmd:seek:0" in call_args[0]


class TestPlaybackAPIVolume:
    """Test PlaybackAPI volume methods."""

    @pytest.mark.asyncio
    async def test_set_volume_min(self, mock_client):
        """Test setting volume to minimum (0.0)."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))
        mock_client._host = "192.168.1.100"

        await mock_client.set_volume(0.0)

        mock_client._request.assert_called_once()
        call_args = mock_client._request.call_args[0]
        # Must use setPlayerCmd:vol: prefix
        assert "setPlayerCmd:vol:0" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_volume_max(self, mock_client):
        """Test setting volume to maximum (1.0)."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))
        mock_client._host = "192.168.1.100"

        await mock_client.set_volume(1.0)

        call_args = mock_client._request.call_args[0]
        # Must use setPlayerCmd:vol: prefix
        assert "setPlayerCmd:vol:100" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_volume_mid(self, mock_client):
        """Test setting volume to middle (0.5)."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))
        mock_client._host = "192.168.1.100"

        await mock_client.set_volume(0.5)

        call_args = mock_client._request.call_args[0]
        # Must use setPlayerCmd:vol: prefix
        assert "setPlayerCmd:vol:50" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_volume_clamps_above_max(self, mock_client):
        """Test volume clamps values above 1.0."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))
        mock_client._host = "192.168.1.100"

        await mock_client.set_volume(1.5)

        call_args = mock_client._request.call_args[0]
        # Must use setPlayerCmd:vol: prefix
        assert "setPlayerCmd:vol:100" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_volume_clamps_below_min(self, mock_client):
        """Test volume clamps values below 0.0."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))
        mock_client._host = "192.168.1.100"

        await mock_client.set_volume(-0.5)

        call_args = mock_client._request.call_args[0]
        # Must use setPlayerCmd:vol: prefix
        assert "setPlayerCmd:vol:0" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_volume_error_handling(self, mock_client):
        """Test volume error handling."""
        mock_client._request = AsyncMock(side_effect=WiiMError("Connection failed"))
        mock_client._host = "192.168.1.100"

        with pytest.raises(WiiMError):
            await mock_client.set_volume(0.5)


class TestPlaybackAPIMute:
    """Test PlaybackAPI mute methods."""

    @pytest.mark.asyncio
    async def test_set_mute_true(self, mock_client):
        """Test setting mute to True."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_mute(True)

        mock_client._request.assert_called_once()
        call_args = mock_client._request.call_args[0]
        # Must use setPlayerCmd:mute: prefix
        assert "setPlayerCmd:mute:1" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_mute_false(self, mock_client):
        """Test setting mute to False."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_mute(False)

        call_args = mock_client._request.call_args[0]
        # Must use setPlayerCmd:mute: prefix
        assert "setPlayerCmd:mute:0" in call_args[0]


class TestPlaybackAPILoopMode:
    """Test PlaybackAPI loop mode methods."""

    @pytest.mark.asyncio
    async def test_set_loop_mode_normal(self, mock_client):
        """Test setting loop mode to normal (0)."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_loop_mode(0)

        call_args = mock_client._request.call_args[0]
        assert "setPlayerCmd:loopmode:0" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_loop_mode_repeat_one(self, mock_client):
        """Test setting loop mode to repeat_one (1)."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_loop_mode(1)

        call_args = mock_client._request.call_args[0]
        assert "setPlayerCmd:loopmode:1" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_loop_mode_repeat_all(self, mock_client):
        """Test setting loop mode to repeat_all (2)."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_loop_mode(2)

        call_args = mock_client._request.call_args[0]
        assert "setPlayerCmd:loopmode:2" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_loop_mode_shuffle(self, mock_client):
        """Test setting loop mode to shuffle (4)."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_loop_mode(4)

        call_args = mock_client._request.call_args[0]
        assert "setPlayerCmd:loopmode:4" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_loop_mode_invalid(self, mock_client):
        """Test setting invalid loop mode raises ValueError."""
        # Only reject unreasonably large or negative values
        with pytest.raises(ValueError, match="Invalid loop mode"):
            await mock_client.set_loop_mode(11)

        with pytest.raises(ValueError, match="Invalid loop mode"):
            await mock_client.set_loop_mode(-1)


class TestPlaybackAPISource:
    """Test PlaybackAPI source selection methods."""

    @pytest.mark.asyncio
    async def test_set_source_wifi(self, mock_client):
        """Test setting source to wifi."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_source("wifi")

        call_args = mock_client._request.call_args[0]
        # Must use setPlayerCmd:switchmode: prefix (not just switchmode:)
        # Without the prefix, device returns "unknown command"
        assert "setPlayerCmd:switchmode:wifi" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_source_bluetooth(self, mock_client):
        """Test setting source to bluetooth."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_source("bluetooth")

        call_args = mock_client._request.call_args[0]
        # Must use setPlayerCmd:switchmode: prefix (not just switchmode:)
        assert "setPlayerCmd:switchmode:bluetooth" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_source_line_in(self, mock_client):
        """Test setting source to line_in."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_source("line_in")

        call_args = mock_client._request.call_args[0]
        # Must use setPlayerCmd:switchmode: prefix (not just switchmode:)
        assert "setPlayerCmd:switchmode:line_in" in call_args[0]


class TestPlaybackAPIAudioOutput:
    """Test PlaybackAPI audio output methods."""

    @pytest.mark.asyncio
    async def test_get_audio_output_status_success(self, mock_client):
        """Test getting audio output status successfully."""
        mock_client._request = AsyncMock(
            return_value=ApiResponse(parsed={"hardware": 0, "source": 0, "audiocast": 0}, raw=None)
        )

        result = await mock_client.get_audio_output_status()

        assert result == {"hardware": 0, "source": 0, "audiocast": 0}
        mock_client._request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_audio_output_status_not_supported(self, mock_client):
        """Test getting audio output status when not supported."""
        mock_client._request = AsyncMock(side_effect=WiiMError("Not supported"))

        result = await mock_client.get_audio_output_status()

        assert result is None

    @pytest.mark.asyncio
    async def test_set_audio_output_hardware_mode(self, mock_client):
        """Test setting audio output hardware mode."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_audio_output_hardware_mode(1)

        call_args = mock_client._request.call_args[0]
        assert "setAudioOutputHardwareMode:1" in call_args[0]

    @pytest.mark.asyncio
    async def test_audio_output_mode_to_name(self, mock_client):
        """Test converting audio output mode to name."""
        assert mock_client.audio_output_mode_to_name(0) == "Line Out"
        assert mock_client.audio_output_mode_to_name(1) == "Optical Out"
        assert mock_client.audio_output_mode_to_name(4) == "Bluetooth Out"  # Default for mode 4
        assert mock_client.audio_output_mode_to_name(6) == "USB Out"  # Mode 6 - legacy compat
        assert mock_client.audio_output_mode_to_name(7) == "HDMI Out"  # Mode 7 - WiiM Amp Ultra
        assert mock_client.audio_output_mode_to_name(8) == "USB Out"  # Mode 8 - confirmed USB (Issue #160)
        assert mock_client.audio_output_mode_to_name(None) is None

    @pytest.mark.asyncio
    async def test_audio_output_name_to_mode(self, mock_client):
        """Test converting audio output name to mode."""
        assert mock_client.audio_output_name_to_mode("Line Out") == 2  # Maps to AUX per official API
        assert mock_client.audio_output_name_to_mode("Optical Out") == 1  # Maps to SPDIF
        assert mock_client.audio_output_name_to_mode("Headphone Out") == 4  # Mode 4
        assert mock_client.audio_output_name_to_mode("Bluetooth Out") == 4  # Mode 4
        assert mock_client.audio_output_name_to_mode("USB Out") == 8  # Mode 8 - confirmed (Issue #160)
        assert mock_client.audio_output_name_to_mode("usb") == 8  # Case insensitive
        assert mock_client.audio_output_name_to_mode("HDMI Out") == 7  # Mode 7 - WiiM Amp Ultra
        assert mock_client.audio_output_name_to_mode("hdmi") == 7  # Case insensitive
        assert mock_client.audio_output_name_to_mode("hdmi arc") == 7  # Alias
        assert mock_client.audio_output_name_to_mode("Speaker Out") == 7  # Sound / Sound Lite
        assert mock_client.audio_output_name_to_mode("speaker") == 7
        assert mock_client.audio_output_name_to_mode("Unknown") is None
        assert mock_client.audio_output_name_to_mode("") is None

    @pytest.mark.asyncio
    async def test_set_audio_output_mode_by_name(self, mock_client):
        """Test setting audio output mode by friendly name."""
        mock_client.set_audio_output_hardware_mode = AsyncMock()

        await mock_client.set_audio_output_mode("Line Out")

        mock_client.set_audio_output_hardware_mode.assert_called_once_with(2)  # AUX mode per official API

    @pytest.mark.asyncio
    async def test_set_audio_output_mode_usb_out(self, mock_client):
        """Test setting USB Out sends mode 8 (Issue #160)."""
        mock_client.set_audio_output_hardware_mode = AsyncMock()

        await mock_client.set_audio_output_mode("USB Out")

        mock_client.set_audio_output_hardware_mode.assert_called_once_with(8)  # Mode 8 confirmed

    @pytest.mark.asyncio
    async def test_set_audio_output_mode_by_int(self, mock_client):
        """Test setting audio output mode by integer."""
        mock_client.set_audio_output_hardware_mode = AsyncMock()

        await mock_client.set_audio_output_mode(1)

        mock_client.set_audio_output_hardware_mode.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_set_audio_output_mode_invalid_name(self, mock_client):
        """Test setting audio output mode with invalid name."""
        with pytest.raises(ValueError, match="Unknown audio output mode"):
            await mock_client.set_audio_output_mode("Invalid Mode")

    @pytest.mark.asyncio
    async def test_set_audio_output_mode_invalid_int(self, mock_client):
        """Test setting audio output mode with invalid integer."""
        with pytest.raises(ValueError, match="Invalid audio output mode"):
            await mock_client.set_audio_output_mode(99)  # 99 is now invalid (was temporary sentinel)

    @pytest.mark.asyncio
    async def test_set_audio_output_mode_invalid_type(self, mock_client):
        """Test setting audio output mode with invalid type."""
        with pytest.raises(TypeError, match="Mode must be str or int"):
            await mock_client.set_audio_output_mode(1.5)


class TestPlaybackAPIPlaylist:
    """Test PlaybackAPI playlist methods."""

    @pytest.mark.asyncio
    async def test_clear_playlist(self, mock_client):
        """Test clearing playlist."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.clear_playlist()

        call_args = mock_client._request.call_args[0]
        assert "setPlayerCmd:clear_playlist" in call_args[0]


class TestPlaybackAPIURLPlayback:
    """Test PlaybackAPI URL playback methods."""

    @pytest.mark.asyncio
    async def test_play_url(self, mock_client):
        """Test playing a URL."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))
        url = "http://example.com/audio.mp3"

        await mock_client.play_url(url)

        call_args = mock_client._request.call_args[0]
        assert "setPlayerCmd:play:" in call_args[0]
        assert "example.com" in call_args[0]

    @pytest.mark.asyncio
    async def test_play_url_with_special_chars(self, mock_client):
        """Test playing URL with special characters."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))
        url = "http://example.com/audio file.mp3?param=value&other=123"

        await mock_client.play_url(url)

        call_args = mock_client._request.call_args[0]
        assert "setPlayerCmd:play:" in call_args[0]

    @pytest.mark.asyncio
    async def test_play_playlist(self, mock_client):
        """Test playing a playlist URL."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))
        playlist_url = "http://example.com/playlist.m3u"

        await mock_client.play_playlist(playlist_url)

        call_args = mock_client._request.call_args[0]
        assert "setPlayerCmd:playlist:" in call_args[0]

    @pytest.mark.asyncio
    async def test_play_notification(self, mock_client):
        """Test playing notification sound."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))
        url = "http://example.com/notification.mp3"

        await mock_client.play_notification(url)

        call_args = mock_client._request.call_args[0]
        assert "playPromptUrl:" in call_args[0]


class TestPlaybackAPIMetadata:
    """Test PlaybackAPI metadata methods."""

    @pytest.mark.asyncio
    async def test_get_meta_info_success(self, mock_client):
        """Test getting metadata successfully."""
        mock_client._request = AsyncMock(
            return_value=ApiResponse(
                parsed={"metaData": {"title": "Test Song", "artist": "Test Artist"}},
                raw=None,
            )
        )

        result = await mock_client.get_meta_info()

        assert result == {"metaData": {"title": "Test Song", "artist": "Test Artist"}}

    @pytest.mark.asyncio
    async def test_get_meta_info_not_supported(self, mock_client):
        """Test getting metadata when not supported."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="unknown command"))

        result = await mock_client.get_meta_info()

        assert result == {}

    @pytest.mark.asyncio
    async def test_get_meta_info_error(self, mock_client):
        """Test getting metadata when endpoint fails."""
        mock_client._request = AsyncMock(side_effect=WiiMError("Not supported"))

        result = await mock_client.get_meta_info()

        assert result == {}
