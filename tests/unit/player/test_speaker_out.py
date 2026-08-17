"""WiiM Sound / Sound Lite speaker output (wiim #270).

Sound Lite reports hardware=7 for Speaker Out. Mode 7 is HDMI Out on Amp Ultra.
Bluetooth Out is the same hardware with source=1, not a different sound-card row.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pywiim.models import DeviceInfo
from pywiim.player import Player


def _sound_lite(mock_client) -> Player:
    player = Player(mock_client)
    player._device_info = DeviceInfo(uuid="test", model="WiiM_Sound_Lite_V2")
    mock_client._capabilities["supports_audio_output"] = True
    return player


class TestSoundLiteOutputModes:
    """Catalog and current-mode mapping for WiiM Sound Lite."""

    def test_available_output_modes_is_speaker_out(self, mock_client):
        """Sound Lite must not inherit the generic Line/Optical/Coax list."""
        player = _sound_lite(mock_client)

        assert player.available_output_modes == ["Speaker Out"]
        assert "Line Out" not in player.available_output_modes
        assert "Optical Out" not in player.available_output_modes
        assert "Coax Out" not in player.available_output_modes
        assert "HDMI Out" not in player.available_output_modes
        assert "Bluetooth Out" not in player.available_output_modes

    def test_available_output_modes_wiim_sound(self, mock_client):
        """WiiM Sound is the same speaker product class."""
        player = Player(mock_client)
        player._device_info = DeviceInfo(uuid="test", model="WiiM Sound")
        mock_client._capabilities["supports_audio_output"] = True

        assert player.available_output_modes == ["Speaker Out"]

    def test_speaker_out_hardware_7_source_0(self, mock_client):
        """hardware=7 source=0 is Speaker Out, not HDMI Out."""
        player = _sound_lite(mock_client)
        player._audio_output_status = {"hardware": "7", "source": "0"}

        assert player.audio_output_mode == "Speaker Out"

    def test_bluetooth_out_same_hardware_source_1(self, mock_client):
        """Bluetooth Out is source=1 on the same hardware=7 path."""
        player = _sound_lite(mock_client)
        player._audio_output_status = {"hardware": "7", "source": "1"}

        assert player.audio_output_mode == "Bluetooth Out"

    def test_amp_ultra_mode_7_remains_hdmi(self, mock_client):
        """Amp Ultra hardware=7 must stay HDMI Out."""
        player = Player(mock_client)
        player._device_info = DeviceInfo(uuid="test", model="WiiM Amp Ultra")
        mock_client._capabilities["supports_audio_output"] = True
        player._audio_output_status = {"hardware": "7", "source": "0"}

        assert player.audio_output_mode == "HDMI Out"
        assert "HDMI Out" in player.available_output_modes
        assert "Speaker Out" not in player.available_output_modes

    @pytest.mark.asyncio
    async def test_select_speaker_out_sets_mode_7(self, mock_client):
        """Selecting Speaker Out disconnects BT then writes hardware mode 7."""
        player = _sound_lite(mock_client)
        player._audio_output_status = {"hardware": "7", "source": "1"}
        player.disconnect_bluetooth_device = AsyncMock()
        mock_client.set_audio_output_hardware_mode = AsyncMock()
        player.refresh = AsyncMock()

        await player.audio.select_output("Speaker Out")

        player.disconnect_bluetooth_device.assert_awaited_once()
        mock_client.set_audio_output_hardware_mode.assert_awaited_once_with(7)
