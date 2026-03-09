"""Unit tests for device capability database (physical input lists)."""

from __future__ import annotations

import pytest

from pywiim.device_capabilities import get_device_inputs


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
