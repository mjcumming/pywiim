"""Unit tests for PresetAPI mixin.

Tests preset retrieval, validation, and playback.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pywiim.exceptions import WiiMError, WiiMRequestError
from pywiim.models import DeviceInfo


class TestPresetAPIGetPresets:
    """Test PresetAPI get_presets method."""

    @pytest.mark.asyncio
    async def test_get_presets_success(self, mock_client):
        """Test getting presets successfully."""
        mock_presets = {
            "preset_list": [
                {
                    "number": 1,
                    "name": "Radio Paradise",
                    "url": "http://example.com",
                    "picurl": "http://example.com/pic.jpg",
                },
                {"number": 2, "name": "Jazz Station", "url": "http://example.com/jazz", "picurl": None},
            ]
        }
        mock_client._request = AsyncMock(return_value=mock_presets)
        mock_client._capabilities = {"supports_presets": True}

        result = await mock_client.get_presets()

        assert len(result) == 2
        assert result[0]["number"] == 1
        assert result[0]["name"] == "Radio Paradise"

    @pytest.mark.asyncio
    async def test_get_presets_not_supported(self, mock_client):
        """Test getting presets when not supported."""
        mock_client._capabilities = {"supports_presets": False}

        result = await mock_client.get_presets()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_presets_404(self, mock_client):
        """Test getting presets when device returns 404."""
        mock_client._request = AsyncMock(side_effect=WiiMRequestError("404 Not Found", endpoint="/api"))
        mock_client._capabilities = {"supports_presets": True}

        result = await mock_client.get_presets()

        assert result == []
        assert mock_client.capabilities["supports_presets"] is False

    @pytest.mark.asyncio
    async def test_get_presets_normalize_unknow(self, mock_client):
        """Test normalizing 'unknow' typo in URL fields."""
        mock_presets = {
            "preset_list": [
                {"number": 1, "name": "Station", "url": "unknow", "picurl": "unknow"},
            ]
        }
        mock_client._request = AsyncMock(return_value=mock_presets)
        mock_client._capabilities = {"supports_presets": True}

        result = await mock_client.get_presets()

        assert result[0]["url"] is None
        assert result[0]["picurl"] is None

    @pytest.mark.asyncio
    async def test_get_presets_normalize_unknown_variants(self, mock_client):
        """Test normalizing various 'unknown' variants."""
        mock_presets = {
            "preset_list": [
                {"number": 1, "name": "Station", "url": "unknown", "picurl": "none"},
                {"number": 2, "name": "Station 2", "url": "", "picurl": "Unknown"},
            ]
        }
        mock_client._request = AsyncMock(return_value=mock_presets)
        mock_client._capabilities = {"supports_presets": True}

        result = await mock_client.get_presets()

        assert result[0]["url"] is None
        assert result[0]["picurl"] is None
        assert result[1]["url"] is None
        assert result[1]["picurl"] is None

    @pytest.mark.asyncio
    async def test_get_presets_empty_list(self, mock_client):
        """Test getting presets when list is empty."""
        mock_client._request = AsyncMock(return_value={"preset_list": []})
        mock_client._capabilities = {"supports_presets": True}

        result = await mock_client.get_presets()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_presets_linkplay_count_only(self, mock_client):
        """Test that LinkPlay devices return empty list when only count available."""
        # getPresetInfo fails (LinkPlay limitation)
        mock_client._request = AsyncMock(side_effect=WiiMRequestError("404 Not Found", endpoint="/api"))
        mock_client._capabilities = {
            "supports_presets": True,
            "presets_full_data": False,
        }

        result = await mock_client.get_presets()

        # Should return empty list (names not available)
        assert result == []
        # Note: get_presets() sets supports_presets to False on 404, but presets_full_data should remain False
        # The capability detection (in capabilities.py) handles LinkPlay differently by checking preset_key
        assert mock_client.capabilities["presets_full_data"] is False

    @pytest.mark.asyncio
    async def test_get_presets_non_dict_response(self, mock_client):
        """Test getting presets when response is not a dict."""
        mock_client._request = AsyncMock(return_value=[])
        mock_client._capabilities = {"supports_presets": True}

        result = await mock_client.get_presets()

        assert result == []


class TestPresetAPIMaxSlots:
    """Test PresetAPI get_max_preset_slots method."""

    @pytest.mark.asyncio
    async def test_get_max_preset_slots_from_preset_key(self, mock_client):
        """Test getting max slots from device preset_key."""
        mock_device_info = DeviceInfo(uuid="test", preset_key="20")
        mock_client.get_device_info_model = AsyncMock(return_value=mock_device_info)
        mock_client._capabilities = {"supports_presets": True}

        result = await mock_client.get_max_preset_slots()

        assert result == 20

    @pytest.mark.asyncio
    async def test_get_max_preset_slots_from_preset_list(self, mock_client):
        """Test getting max slots when preset_key is not available (defaults to 6)."""
        mock_device_info = DeviceInfo(uuid="test", preset_key=None)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_device_info)
        mock_client._capabilities = {"supports_presets": True}

        result = await mock_client.get_max_preset_slots()

        # When preset_key is not available from API, should default to 6
        assert result == 6

    @pytest.mark.asyncio
    async def test_get_max_preset_slots_default(self, mock_client):
        """Test getting max slots with default fallback when preset_key not available."""
        mock_device_info = DeviceInfo(uuid="test", preset_key=None)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_device_info)
        mock_client._capabilities = {"supports_presets": True}

        result = await mock_client.get_max_preset_slots()

        # When preset_key is not available from API, should default to 6
        assert result == 6

    @pytest.mark.asyncio
    async def test_get_max_preset_slots_not_supported(self, mock_client):
        """Test getting max slots when presets not supported."""
        mock_client._capabilities = {"supports_presets": False}

        result = await mock_client.get_max_preset_slots()

        assert result == 0

    @pytest.mark.asyncio
    async def test_get_max_preset_slots_404(self, mock_client):
        """Test getting max slots when device returns 404."""
        mock_client.get_device_info_model = AsyncMock(side_effect=WiiMRequestError("404 Not Found", endpoint="/api"))
        mock_client._capabilities = {"supports_presets": True}

        result = await mock_client.get_max_preset_slots()

        assert result == 0


class TestPresetAPIPlayPreset:
    """Test PresetAPI play_preset method."""

    @pytest.mark.asyncio
    async def test_play_preset_success(self, mock_client):
        """Test playing preset successfully."""
        mock_client._request = AsyncMock(return_value={"raw": "OK"})
        mock_client._capabilities = {"supports_presets": True}
        mock_client.get_max_preset_slots = AsyncMock(return_value=20)

        await mock_client.play_preset(5)

        mock_client._request.assert_called_once()
        call_args = mock_client._request.call_args[0]
        assert "/httpapi.asp?command=MCUKeyShortClick:5" in call_args[0]

    @pytest.mark.asyncio
    async def test_play_preset_not_supported(self, mock_client):
        """Test playing preset when not supported."""
        mock_client._capabilities = {"supports_presets": False}

        with pytest.raises(WiiMError, match="Presets are not supported"):
            await mock_client.play_preset(1)

    @pytest.mark.asyncio
    async def test_play_preset_zero_slots(self, mock_client):
        """Test playing preset when max slots is 0."""
        mock_client._capabilities = {"supports_presets": True}
        mock_client.get_max_preset_slots = AsyncMock(return_value=0)

        with pytest.raises(WiiMError, match="Presets are not supported"):
            await mock_client.play_preset(1)

    @pytest.mark.asyncio
    async def test_play_preset_invalid_too_low(self, mock_client):
        """Test playing preset with number too low."""
        mock_client._capabilities = {"supports_presets": True}

        with pytest.raises(ValueError, match="Preset number must be 1 or higher"):
            await mock_client.play_preset(0)

    @pytest.mark.asyncio
    async def test_play_preset_invalid_too_high(self, mock_client):
        """Test playing preset with number too high."""
        mock_client._capabilities = {"supports_presets": True}
        mock_client.get_max_preset_slots = AsyncMock(return_value=6)

        with pytest.raises(ValueError, match="Preset number 10 exceeds maximum"):
            await mock_client.play_preset(10)

    @pytest.mark.asyncio
    async def test_play_preset_max_slot(self, mock_client):
        """Test playing preset at maximum slot."""
        mock_client._request = AsyncMock(return_value={"raw": "OK"})
        mock_client._capabilities = {"supports_presets": True}
        mock_client.get_max_preset_slots = AsyncMock(return_value=6)

        await mock_client.play_preset(6)

        mock_client._request.assert_called_once()

    @pytest.mark.asyncio
    async def test_play_preset_with_index(self, mock_client):
        """Test playing preset with track index sends MCUKeyShortClick:preset:index."""
        mock_client._request = AsyncMock(return_value={"raw": "OK"})
        mock_client._capabilities = {"supports_presets": True}
        mock_client.get_max_preset_slots = AsyncMock(return_value=20)

        await mock_client.play_preset(6, index=2)

        mock_client._request.assert_called_once()
        call_args = mock_client._request.call_args[0]
        assert "/httpapi.asp?command=MCUKeyShortClick:6:2" in call_args[0]

    @pytest.mark.asyncio
    async def test_play_preset_with_index_one(self, mock_client):
        """Test playing preset with index=1 (start from beginning)."""
        mock_client._request = AsyncMock(return_value={"raw": "OK"})
        mock_client._capabilities = {"supports_presets": True}
        mock_client.get_max_preset_slots = AsyncMock(return_value=6)

        await mock_client.play_preset(1, index=1)

        mock_client._request.assert_called_once()
        call_args = mock_client._request.call_args[0]
        assert "MCUKeyShortClick:1:1" in call_args[0]

    @pytest.mark.asyncio
    async def test_play_preset_index_invalid_zero(self, mock_client):
        """Test playing preset with index 0 raises ValueError."""
        mock_client._capabilities = {"supports_presets": True}

        with pytest.raises(ValueError, match="Index must be 1 or higher"):
            await mock_client.play_preset(1, index=0)

    @pytest.mark.asyncio
    async def test_play_preset_index_invalid_negative(self, mock_client):
        """Test playing preset with negative index raises ValueError."""
        mock_client._capabilities = {"supports_presets": True}

        with pytest.raises(ValueError, match="Index must be 1 or higher"):
            await mock_client.play_preset(1, index=-1)
