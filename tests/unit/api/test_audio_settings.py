"""Unit tests for AudioSettingsAPI mixin.

Tests SPDIF settings, channel balance, and audio configuration.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pywiim.api.base import ApiResponse
from pywiim.exceptions import WiiMError, WiiMResponseError


class TestAudioSettingsAPISoundCardSupport:
    """Test AudioSettingsAPI sound-card support discovery."""

    @pytest.mark.asyncio
    async def test_get_sound_card_mode_support_list(self, mock_client):
        """Test getSoundCardModeSupportList parses output entries by mode."""
        mock_client._request = AsyncMock(
            return_value=ApiResponse(
                parsed=[
                    {
                        "index": 5,
                        "mode": "AUDIO_OUTPUT_UAC_CARD_MODE",
                        "soundCard": {
                            "cardName": "SABRE-D70 Pro SABRE",
                            "devName": "Topping D70 Pro SABRE at usb-xhci-hcd.0.auto-1.2",
                            "cardId": "hw:1,0",
                            "supportDigitalFilter": 1,
                            "sampleRateSupportList": [44100, 48000, 192000],
                        },
                    }
                ],
                raw=None,
            )
        )

        result = await mock_client.get_sound_card_mode_support_list()

        assert len(result) == 1
        assert result[0].index == 5
        assert result[0].mode == "AUDIO_OUTPUT_UAC_CARD_MODE"
        assert result[0].sound_card is not None
        assert result[0].sound_card.dev_name == "Topping D70 Pro SABRE at usb-xhci-hcd.0.auto-1.2"
        assert result[0].sound_card.support_digital_filter is True
        assert result[0].sound_card.sample_rate_support_list == [44100, 48000, 192000]

    @pytest.mark.asyncio
    async def test_get_sound_card_mode_support_list_filters_invalid_items(self, mock_client):
        """Invalid entries without a mode are ignored."""
        mock_client._request = AsyncMock(
            return_value=ApiResponse(
                parsed=[
                    {"index": 1, "soundCard": {"devName": "Missing Mode"}},
                    {"index": 2, "mode": "AUDIO_OUTPUT_SPDIF_MODE", "soundCard": {"devName": "Optical Out"}},
                    "not-a-dict",
                ],
                raw=None,
            )
        )

        result = await mock_client.get_sound_card_mode_support_list()

        assert [item.mode for item in result] == ["AUDIO_OUTPUT_SPDIF_MODE"]

    @pytest.mark.asyncio
    async def test_get_sound_card_mode_support_list_unsupported(self, mock_client):
        """Unsupported endpoint returns an empty list."""
        mock_client._request = AsyncMock(side_effect=WiiMError("unknown command"))

        assert await mock_client.get_sound_card_mode_support_list() == []


class TestAudioSettingsAPISPDIF:
    """Test AudioSettingsAPI SPDIF methods."""

    @pytest.mark.asyncio
    async def test_get_spdif_sample_rate(self, mock_client):
        """Test getting SPDIF sample rate."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed="48000", raw=None))

        result = await mock_client.get_spdif_sample_rate()

        assert result == "48000"

    @pytest.mark.asyncio
    async def test_get_spdif_sample_rate_error(self, mock_client):
        """Test getting SPDIF sample rate when request fails."""
        mock_client._request = AsyncMock(side_effect=WiiMError("Failed"))

        result = await mock_client.get_spdif_sample_rate()

        assert result == ""

    @pytest.mark.asyncio
    async def test_get_spdif_sample_rate_empty(self, mock_client):
        """Test getting SPDIF sample rate when response is empty."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw=None))

        result = await mock_client.get_spdif_sample_rate()

        assert result == ""

    @pytest.mark.asyncio
    async def test_set_spdif_switch_delay(self, mock_client):
        """Test setting SPDIF switch delay."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_spdif_switch_delay(100)

        mock_client._request.assert_called_once()
        call_args = mock_client._request.call_args[0]
        assert "100" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_spdif_switch_delay_invalid_too_low(self, mock_client):
        """Test setting SPDIF delay with value too low."""
        with pytest.raises(ValueError, match="SPDIF switch delay must be between 0 and 3000"):
            await mock_client.set_spdif_switch_delay(-1)

    @pytest.mark.asyncio
    async def test_set_spdif_switch_delay_invalid_too_high(self, mock_client):
        """Test setting SPDIF delay with value too high."""
        with pytest.raises(ValueError, match="SPDIF switch delay must be between 0 and 3000"):
            await mock_client.set_spdif_switch_delay(3001)

    @pytest.mark.asyncio
    async def test_set_spdif_switch_delay_boundary(self, mock_client):
        """Test setting SPDIF delay at boundaries."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_spdif_switch_delay(0)
        await mock_client.set_spdif_switch_delay(3000)

        assert mock_client._request.call_count == 2

    @pytest.mark.asyncio
    async def test_get_spdif_sample_rate_int(self, mock_client):
        """Test getting SPDIF sample rate as integer."""
        mock_client.get_spdif_sample_rate = AsyncMock(return_value="96000")

        result = await mock_client.get_spdif_sample_rate_int()

        assert result == 96000

    @pytest.mark.asyncio
    async def test_get_spdif_sample_rate_int_invalid(self, mock_client):
        """Test getting SPDIF sample rate as integer when invalid."""
        mock_client.get_spdif_sample_rate = AsyncMock(return_value="invalid")

        result = await mock_client.get_spdif_sample_rate_int()

        assert result == 0

    @pytest.mark.asyncio
    async def test_get_spdif_sample_rate_int_empty(self, mock_client):
        """Test getting SPDIF sample rate as integer when empty."""
        mock_client.get_spdif_sample_rate = AsyncMock(return_value="")

        result = await mock_client.get_spdif_sample_rate_int()

        assert result == 0

    @pytest.mark.asyncio
    async def test_is_spdif_output_active_true(self, mock_client):
        """Test checking if SPDIF output is active."""
        mock_client.get_spdif_sample_rate_int = AsyncMock(return_value=48000)

        result = await mock_client.is_spdif_output_active()

        assert result is True

    @pytest.mark.asyncio
    async def test_is_spdif_output_active_false(self, mock_client):
        """Test checking if SPDIF output is inactive."""
        mock_client.get_spdif_sample_rate_int = AsyncMock(return_value=0)

        result = await mock_client.is_spdif_output_active()

        assert result is False


class TestAudioSettingsAPIChannelBalance:
    """Test AudioSettingsAPI channel balance methods."""

    @pytest.mark.asyncio
    async def test_get_channel_balance(self, mock_client):
        """Test getting channel balance."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=0.5, raw=None))

        result = await mock_client.get_channel_balance()

        assert result == 0.5

    @pytest.mark.asyncio
    async def test_get_channel_balance_string(self, mock_client):
        """Test getting channel balance as string."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed="0.75", raw=None))

        result = await mock_client.get_channel_balance()

        assert result == 0.75

    @pytest.mark.asyncio
    async def test_get_channel_balance_error(self, mock_client):
        """Test getting channel balance when request fails."""
        mock_client._request = AsyncMock(side_effect=WiiMError("Failed"))

        result = await mock_client.get_channel_balance()

        assert result == 0.0

    @pytest.mark.asyncio
    async def test_get_channel_balance_invalid_type(self, mock_client):
        """Test getting channel balance with invalid response type."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed={"error": "invalid"}, raw=None))

        result = await mock_client.get_channel_balance()

        assert result == 0.0

    @pytest.mark.asyncio
    async def test_set_channel_balance(self, mock_client):
        """Test setting channel balance."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_channel_balance(0.5)

        mock_client._request.assert_called_once()
        call_args = mock_client._request.call_args[0]
        assert "0.5" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_channel_balance_negative(self, mock_client):
        """Test setting negative channel balance (left)."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_channel_balance(-0.5)

        call_args = mock_client._request.call_args[0]
        assert "-0.5" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_channel_balance_invalid_too_low(self, mock_client):
        """Test setting channel balance with value too low."""
        with pytest.raises(ValueError, match="Channel balance must be between -1.0 and 1.0"):
            await mock_client.set_channel_balance(-1.1)

    @pytest.mark.asyncio
    async def test_set_channel_balance_invalid_too_high(self, mock_client):
        """Test setting channel balance with value too high."""
        with pytest.raises(ValueError, match="Channel balance must be between -1.0 and 1.0"):
            await mock_client.set_channel_balance(1.1)

    @pytest.mark.asyncio
    async def test_set_channel_balance_boundary(self, mock_client):
        """Test setting channel balance at boundaries."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_channel_balance(-1.0)
        await mock_client.set_channel_balance(0.0)
        await mock_client.set_channel_balance(1.0)

        assert mock_client._request.call_count == 3

    @pytest.mark.asyncio
    async def test_set_channel_balance_formatting(self, mock_client):
        """Test channel balance formatting removes unnecessary decimals."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_channel_balance(1.0)

        call_args = mock_client._request.call_args[0]
        # Should format as "1" not "1.0"
        assert "1" in call_args[0]

    @pytest.mark.asyncio
    async def test_center_channel_balance(self, mock_client):
        """Test centering channel balance."""
        mock_client.set_channel_balance = AsyncMock()

        await mock_client.center_channel_balance()

        mock_client.set_channel_balance.assert_called_once_with(0.0)


class TestAudioSettingsAPIOutputChannel:
    """Test AudioSettingsAPI output channel (stereo / left / right)."""

    @pytest.mark.parametrize(
        "response",
        [
            ApiResponse(parsed=None, raw="unknown command"),
            ApiResponse(parsed=None, raw=""),
            ApiResponse(parsed={"error": "unsupported_command"}, raw=None),
        ],
    )
    @pytest.mark.asyncio
    async def test_output_channel_rejected_response(self, mock_client, response):
        """An HTTP 200 response must acknowledge the setting before it succeeds."""
        mock_client._request = AsyncMock(return_value=response)

        with pytest.raises(WiiMResponseError, match="output channel"):
            await mock_client.set_output_channel("left")

    @pytest.mark.parametrize(
        ("channel", "expected"),
        [("stereo", "0"), ("left", "1"), ("right", "2"), ("LEFT", "1"), (" Right ", "2")],
    )
    @pytest.mark.asyncio
    async def test_set_output_channel_sends_slave_channel(self, mock_client, channel, expected):
        """set_output_channel sends setPlayerCmd:slave_channel:N with N 0/1/2."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_output_channel(channel)

        mock_client._request.assert_called_once_with(f"/httpapi.asp?command=setPlayerCmd:slave_channel:{expected}")

    @pytest.mark.parametrize("channel", ["mono", "", "1", "center"])
    @pytest.mark.asyncio
    async def test_set_output_channel_rejects_unknown_name(self, mock_client, channel):
        """Unknown names raise ValueError and send nothing."""
        mock_client._request = AsyncMock()

        with pytest.raises(ValueError, match="Output channel must be one of"):
            await mock_client.set_output_channel(channel)

        mock_client._request.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_output_channel_from_player_status(self, mock_client):
        """get_output_channel reads ch from a real AudioCast AMP getPlayerStatus payload."""
        payload = {
            "type": "0",
            "ch": "1",
            "mode": "31",
            "loop": "3",
            "eq": "0",
            "status": "pause",
            "curpos": "34608",
            "offset_pts": "0",
            "totlen": "192112",
            "Title": "44726167204D6520446F776E",
            "alarmflag": "0",
            "plicount": "0",
            "plicurr": "0",
            "vol": "24",
            "mute": "0",
        }
        mock_client._capabilities["status_endpoint"] = "/httpapi.asp?command=getPlayerStatus"
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=payload, raw=None))

        assert await mock_client.get_output_channel() == "left"
        assert mock_client._request.call_args_list[0][0][0] == "/httpapi.asp?command=getPlayerStatus"

    @pytest.mark.parametrize(
        ("ch", "expected"), [("0", "stereo"), ("2", "right"), (2, "right"), ("9", None), ("", None)]
    )
    @pytest.mark.asyncio
    async def test_get_output_channel_values(self, mock_client, ch, expected):
        """ch 0/1/2 map to names; out-of-range or empty values return None."""
        mock_client.get_player_status = AsyncMock(return_value={"ch": ch})

        assert await mock_client.get_output_channel() == expected

    @pytest.mark.asyncio
    async def test_get_output_channel_missing_field(self, mock_client):
        """A status without ch returns None."""
        mock_client.get_player_status = AsyncMock(return_value={"vol": "24"})

        assert await mock_client.get_output_channel() is None


class TestAudioSettingsAPIStatus:
    """Test AudioSettingsAPI status methods."""

    @pytest.mark.asyncio
    async def test_get_audio_settings_status(self, mock_client):
        """Test getting comprehensive audio settings status."""
        mock_client.get_spdif_sample_rate = AsyncMock(return_value="48000")
        mock_client.get_channel_balance = AsyncMock(return_value=0.5)
        mock_client.is_spdif_output_active = AsyncMock(return_value=True)

        result = await mock_client.get_audio_settings_status()

        assert result["spdif_sample_rate"] == "48000"
        assert result["channel_balance"] == 0.5
        assert result["spdif_active"] is True

    @pytest.mark.asyncio
    async def test_get_audio_settings_status_error(self, mock_client):
        """Test getting audio settings status when request fails."""
        mock_client.get_spdif_sample_rate = AsyncMock(side_effect=WiiMError("Failed"))

        result = await mock_client.get_audio_settings_status()

        assert result["spdif_sample_rate"] == ""
        assert result["channel_balance"] == 0.0
        assert result["spdif_active"] is False
