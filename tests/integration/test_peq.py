"""Integration tests for PEQ (Parametric EQ) API against real devices.

These tests require a real WiiM device on the network. They verify that the
PEQ API works against devices in the testing database (see tests/devices.yaml).

- WiiM devices (Pro, Mini, Amp, Ultra): PEQ is supported; tests run read-only
  get_peq_bands, get_peq_preset_list, get_peq_preset_list_detailed.
- Non-WiiM devices (Arylic, Audio Pro, generic LinkPlay): supports_peq is False;
  tests are skipped so no PEQ calls are made.

Set WIIM_TEST_DEVICE to run against a specific device, or use default from devices.yaml.

Example:
    WIIM_TEST_DEVICE=192.168.1.115 pytest tests/integration/test_peq.py -v

For HTTPS:
    WIIM_TEST_DEVICE=192.168.1.115 WIIM_TEST_HTTPS=true pytest tests/integration/test_peq.py -v
"""

from __future__ import annotations

import pytest

from pywiim.api.constants import PEQ_CHANNEL_MODE_LR, PEQ_CHANNEL_MODE_STEREO
from pywiim.api.peq import PEQBand, PEQPresetInfo, PEQSettings


@pytest.mark.integration
@pytest.mark.asyncio
class TestPEQRealDevice:
    """PEQ API integration tests against real WiiM devices."""

    async def test_peq_capability_probed(self, real_device_client, integration_test_marker):
        """Ensure supports_peq is set after capability detection (WiiM=True, others=False)."""
        await real_device_client._detect_capabilities()
        caps = real_device_client._capabilities
        assert "supports_peq" in caps
        # Value is True for WiiM (probe succeeds), False for Arylic/Audio Pro/generic
        assert isinstance(caps["supports_peq"], bool)

    async def test_peq_get_bands_when_supported(self, real_device_client, integration_test_marker):
        """get_peq_bands() returns PEQSettings when device supports PEQ (read-only)."""
        await real_device_client._detect_capabilities()
        if not real_device_client._capabilities.get("supports_peq", False):
            pytest.skip("PEQ not supported on this device (use a WiiM device for PEQ tests)")

        settings = await real_device_client.get_peq_bands()
        assert isinstance(settings, PEQSettings)
        assert isinstance(settings.enabled, bool)
        assert settings.channel_mode in (PEQ_CHANNEL_MODE_STEREO, PEQ_CHANNEL_MODE_LR)
        assert isinstance(settings.bands, list)
        assert len(settings.bands) == 10
        for band in settings.bands:
            assert isinstance(band, PEQBand)
            assert band.letter in "abcdefghij"

    async def test_peq_get_bands_with_source_when_supported(self, real_device_client, integration_test_marker):
        """get_peq_bands(source_name='wifi') works when device supports PEQ (read-only)."""
        await real_device_client._detect_capabilities()
        if not real_device_client._capabilities.get("supports_peq", False):
            pytest.skip("PEQ not supported on this device (use a WiiM device for PEQ tests)")

        settings = await real_device_client.get_peq_bands(source_name="wifi")
        assert isinstance(settings, PEQSettings)
        assert len(settings.bands) == 10

    async def test_peq_get_preset_list_when_supported(self, real_device_client, integration_test_marker):
        """get_peq_preset_list() returns custom/preset lists when device supports PEQ (read-only)."""
        await real_device_client._detect_capabilities()
        if not real_device_client._capabilities.get("supports_peq", False):
            pytest.skip("PEQ not supported on this device (use a WiiM device for PEQ tests)")

        result = await real_device_client.get_peq_preset_list()
        assert isinstance(result, dict)
        assert "custom" in result
        assert "preset" in result
        assert isinstance(result["custom"], list)
        assert isinstance(result["preset"], list)

    async def test_peq_get_preset_list_detailed_when_supported(self, real_device_client, integration_test_marker):
        """get_peq_preset_list_detailed() returns PEQPresetInfo when device supports PEQ (read-only)."""
        await real_device_client._detect_capabilities()
        if not real_device_client._capabilities.get("supports_peq", False):
            pytest.skip("PEQ not supported on this device (use a WiiM device for PEQ tests)")

        result = await real_device_client.get_peq_preset_list_detailed()
        assert isinstance(result, dict)
        assert "custom" in result
        assert "preset" in result
        for entry in result["custom"] + result["preset"]:
            assert isinstance(entry, PEQPresetInfo)
            assert isinstance(entry.name, str)
