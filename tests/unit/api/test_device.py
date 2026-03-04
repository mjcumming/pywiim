"""Unit tests for DeviceAPI mixin.

Tests device information retrieval and LED control.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pywiim.api.base import ApiResponse
from pywiim.api.device import _get_led_command_format
from pywiim.exceptions import WiiMError
from pywiim.models import DeviceInfo


class TestDeviceAPI:
    """Test DeviceAPI mixin methods."""

    @pytest.mark.asyncio
    async def test_get_device_info(self, mock_client):
        """Test getting device info."""
        expected_data = {
            "DeviceName": "Test Device",
            "project": "WiiM Pro",
            "firmware": "5.0.1",
        }
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=expected_data, raw=None))

        result = await mock_client.get_device_info()

        assert result == expected_data
        mock_client._request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_device_info_model(self, mock_client):
        """Test getting device info as model."""
        raw_data = {
            "DeviceName": "Test Device",
            "project": "WiiM Pro",
            "firmware": "5.0.1",
            "MAC": "AA:BB:CC:DD:EE:FF",
        }
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=raw_data, raw=None))

        result = await mock_client.get_device_info_model()

        assert isinstance(result, DeviceInfo)
        assert result.name == "Test Device"
        assert result.model == "WiiM Pro"
        assert result.firmware == "5.0.1"
        assert result.mac == "AA:BB:CC:DD:EE:FF"

    @pytest.mark.asyncio
    async def test_get_firmware_version(self, mock_client):
        """Test getting firmware version."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed={"firmware": "5.0.1"}, raw=None))

        result = await mock_client.get_firmware_version()

        assert result == "5.0.1"

    @pytest.mark.asyncio
    async def test_get_firmware_version_empty(self, mock_client):
        """Test getting firmware version when not available."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed={}, raw=None))

        result = await mock_client.get_firmware_version()

        assert result == ""

    @pytest.mark.asyncio
    async def test_get_firmware_version_non_dict(self, mock_client):
        """Test getting firmware version with non-dict response."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="invalid"))

        result = await mock_client.get_firmware_version()

        assert result == ""

    @pytest.mark.asyncio
    async def test_get_mac_address(self, mock_client):
        """Test getting MAC address."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed={"mac": "AA:BB:CC:DD:EE:FF"}, raw=None))

        result = await mock_client.get_mac_address()

        assert result == "AA:BB:CC:DD:EE:FF"

    @pytest.mark.asyncio
    async def test_get_mac_address_empty(self, mock_client):
        """Test getting MAC address when not available."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed={}, raw=None))

        result = await mock_client.get_mac_address()

        assert result == ""

    @pytest.mark.asyncio
    async def test_get_mac_address_non_dict(self, mock_client):
        """Test getting MAC address with non-dict response."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="invalid"))

        result = await mock_client.get_mac_address()

        assert result == ""


class TestDeviceAPILED:
    """Test DeviceAPI LED control methods."""

    @pytest.mark.asyncio
    async def test_set_led_enable_standard(self, mock_client):
        """Test enabling LED on standard device."""
        device_info = DeviceInfo(model="WiiM Pro", name="Test")
        mock_client.get_device_info_model = AsyncMock(return_value=device_info)
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_led(True)

        call_args = mock_client._request.call_args[0]
        assert "setLED:1" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_led_disable_standard(self, mock_client):
        """Test disabling LED on standard device."""
        device_info = DeviceInfo(model="WiiM Pro", name="Test")
        mock_client.get_device_info_model = AsyncMock(return_value=device_info)
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_led(False)

        call_args = mock_client._request.call_args[0]
        assert "setLED:0" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_led_enable_arylic(self, mock_client):
        """Test enabling LED on Arylic device."""
        device_info = DeviceInfo(model="Arylic Up2Stream", name="Test")
        mock_client.get_device_info_model = AsyncMock(return_value=device_info)
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_led(True)

        call_args = mock_client._request.call_args[0]
        assert "MCU+PAS+RAKOIT:LED:1" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_led_arylic_fallback(self, mock_client):
        """Test Arylic LED command fallback to standard."""
        device_info = DeviceInfo(model="Arylic Up2Stream", name="Test")
        mock_client.get_device_info_model = AsyncMock(return_value=device_info)
        # First call fails, second succeeds
        mock_client._request = AsyncMock(side_effect=[WiiMError("Not supported"), ApiResponse(parsed=None, raw="OK")])

        await mock_client.set_led(True)

        # Should have tried Arylic command first, then standard
        assert mock_client._request.call_count == 2

    @pytest.mark.asyncio
    async def test_set_led_error_handling(self, mock_client):
        """Test LED error handling (should not raise)."""
        device_info = DeviceInfo(model="WiiM Pro", name="Test")
        mock_client.get_device_info_model = AsyncMock(return_value=device_info)
        mock_client._request = AsyncMock(side_effect=WiiMError("Not supported"))

        # Should not raise exception
        await mock_client.set_led(True)

    @pytest.mark.asyncio
    async def test_set_led_brightness_valid(self, mock_client):
        """Test setting LED brightness with valid value."""
        device_info = DeviceInfo(model="WiiM Pro", name="Test")
        mock_client.get_device_info_model = AsyncMock(return_value=device_info)
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_led_brightness(50)

        call_args = mock_client._request.call_args[0]
        assert "setLEDBrightness:50" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_led_brightness_min(self, mock_client):
        """Test setting LED brightness to minimum (0)."""
        device_info = DeviceInfo(model="WiiM Pro", name="Test")
        mock_client.get_device_info_model = AsyncMock(return_value=device_info)
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_led_brightness(0)

        call_args = mock_client._request.call_args[0]
        assert "setLEDBrightness:0" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_led_brightness_max(self, mock_client):
        """Test setting LED brightness to maximum (100)."""
        device_info = DeviceInfo(model="WiiM Pro", name="Test")
        mock_client.get_device_info_model = AsyncMock(return_value=device_info)
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_led_brightness(100)

        call_args = mock_client._request.call_args[0]
        assert "setLEDBrightness:100" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_led_brightness_invalid_low(self, mock_client):
        """Test setting LED brightness below valid range."""
        with pytest.raises(ValueError, match="Brightness must be between 0 and 100"):
            await mock_client.set_led_brightness(-1)

    @pytest.mark.asyncio
    async def test_set_led_brightness_invalid_high(self, mock_client):
        """Test setting LED brightness above valid range."""
        with pytest.raises(ValueError, match="Brightness must be between 0 and 100"):
            await mock_client.set_led_brightness(101)

    @pytest.mark.asyncio
    async def test_set_led_brightness_arylic(self, mock_client):
        """Test setting LED brightness on Arylic device."""
        device_info = DeviceInfo(model="Arylic Up2Stream", name="Test")
        mock_client.get_device_info_model = AsyncMock(return_value=device_info)
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_led_brightness(75)

        call_args = mock_client._request.call_args[0]
        assert "MCU+PAS+RAKOIT:LEDBRIGHTNESS:75" in call_args[0]

    @pytest.mark.asyncio
    async def test_set_led_brightness_error_handling(self, mock_client):
        """Test LED brightness error handling (should not raise)."""
        device_info = DeviceInfo(model="WiiM Pro", name="Test")
        mock_client.get_device_info_model = AsyncMock(return_value=device_info)
        mock_client._request = AsyncMock(side_effect=WiiMError("Not supported"))

        # Should not raise exception
        await mock_client.set_led_brightness(50)


class TestLEDCommandFormat:
    """Test LED command format detection."""

    def test_get_led_command_format_standard(self):
        """Test LED command format for standard device."""
        device_info = DeviceInfo(model="WiiM Pro")
        result = _get_led_command_format(device_info)
        assert result == "standard"

    def test_get_led_command_format_arylic(self):
        """Test LED command format for Arylic device."""
        device_info = DeviceInfo(model="Arylic Up2Stream")
        result = _get_led_command_format(device_info)
        assert result == "arylic"

    def test_get_led_command_format_up2stream(self):
        """Test LED command format for Up2Stream device."""
        device_info = DeviceInfo(model="Up2Stream Pro")
        result = _get_led_command_format(device_info)
        assert result == "arylic"

    def test_get_led_command_format_no_model(self):
        """Test LED command format when model is None."""
        device_info = DeviceInfo()
        result = _get_led_command_format(device_info)
        assert result == "standard"

    def test_get_led_command_format_unknown(self):
        """Test LED command format for unknown device."""
        device_info = DeviceInfo(model="Unknown Device")
        result = _get_led_command_format(device_info)
        assert result == "standard"
