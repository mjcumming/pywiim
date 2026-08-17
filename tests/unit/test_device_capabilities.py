"""Unit tests for device capability database (physical input lists)."""

from __future__ import annotations

from pywiim.device_capabilities import get_device_inputs, get_device_output_modes


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
