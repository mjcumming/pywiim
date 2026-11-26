"""Unit tests for device capability database (physical input lists)."""

from __future__ import annotations

import pytest

from pywiim.capabilities import detect_device_capabilities
from pywiim.device_capabilities import get_device_inputs, get_device_output_modes
from pywiim.models import DeviceInfo


class TestAudioProDeviceInputs:
    """Test device input lookups for Audio Pro models."""

    def test_link2_inputs(self):
        """Link 2 has optical, coaxial, RCA, and bluetooth inputs."""
        result = get_device_inputs("LINK 2 Wireless multiroom HiFi player")
        assert result is not None
        assert "rca" in result.inputs
        assert "optical" in result.inputs
        assert "coaxial" in result.inputs
        assert "bluetooth" in result.inputs

    def test_a28_inputs(self):
        """A28 has optical, RCA, HDMI, and bluetooth inputs."""
        result = get_device_inputs("A28 Speaker")
        assert result is not None
        assert "optical" in result.inputs
        assert "rca" in result.inputs
        assert "hdmi" in result.inputs
        assert "bluetooth" in result.inputs

    def test_c5_mkii_inputs(self):
        """ADDON C5 MkII has RCA and bluetooth inputs only."""
        result = get_device_inputs("ADDON C5 MkII Speaker")
        assert result is not None
        assert "rca" in result.inputs
        assert "bluetooth" in result.inputs
        assert "optical" not in result.inputs


class TestArtSoundSmartStream:
    """ArtSound Smart Stream 2, project Huan_HI8 (pywiim#48)."""

    def test_catalog_includes_hdmi_and_omits_usb(self):
        result = get_device_inputs("Huan_HI8")
        assert result is not None
        assert result.inputs == ["bluetooth", "line_in", "optical", "rca", "hdmi"]

    def test_hdmi_command_keeps_device_case(self):
        capabilities = detect_device_capabilities(DeviceInfo(uuid="smart-stream", model="Huan_HI8"))
        assert capabilities["source_command_overrides"] == {"hdmi": "HDMI"}

    def test_other_models_keep_the_default_command(self):
        capabilities = detect_device_capabilities(DeviceInfo(uuid="pro", model="WiiM Pro"))
        assert capabilities["source_command_overrides"] == {}

    @pytest.mark.asyncio
    async def test_available_sources_include_hdmi_from_incomplete_plm(self, mock_client):
        """plm_support 0x416 is Bluetooth, USB, and two unknown bits. HDMI is still listed."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._device_info = DeviceInfo(uuid="smart-stream", model="Huan_HI8", plm_support="0x416")

        result = player.available_sources
        assert "HDMI" in result
        assert "Optical In" in result
        assert "RCA" in result
        assert "Line In" in result
        assert "Bluetooth" in result
        assert "USB" not in result


class TestWiiMSoundOutputs:
    """Sound / Sound Lite hardware output catalog (wiim #270)."""

    def test_sound_lite_outputs_speaker_out(self):
        result = get_device_inputs("WiiM_Sound_Lite_V2")
        assert result is not None
        assert result.outputs == ["Speaker Out"]
        assert get_device_output_modes("WiiM_Sound_Lite_V2") == ["Speaker Out"]

    def test_wiim_sound_outputs_speaker_out(self):
        result = get_device_inputs("WiiM Sound")
        assert result is not None
        assert result.outputs == ["Speaker Out"]

    def test_pro_outputs_not_catalogued(self):
        """Streamer models keep the properties.py ladder until migrated."""
        result = get_device_inputs("WiiM Pro")
        assert result is not None
        assert result.outputs is None
        assert get_device_output_modes("WiiM Pro") is None
