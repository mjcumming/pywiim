"""Unit tests for BluetoothAPI mixin.

Tests Bluetooth device discovery, scanning, connection, and pairing.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from pywiim.api.base import ApiResponse
from pywiim.exceptions import WiiMError


class TestBluetoothAPIDiscovery:
    """Test BluetoothAPI discovery methods."""

    @pytest.mark.asyncio
    async def test_start_bluetooth_discovery(self, mock_client):
        """Test starting Bluetooth discovery."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.start_bluetooth_discovery(duration=5)

        mock_client._request.assert_called_once()
        call_args = mock_client._request.call_args[0]
        assert "/httpapi.asp?command=startbtdiscovery:5" in call_args[0]

    @pytest.mark.asyncio
    async def test_start_bluetooth_discovery_invalid_duration_too_low(self, mock_client):
        """Test starting discovery with duration too low."""
        with pytest.raises(ValueError, match="Duration must be between 1 and 60 seconds"):
            await mock_client.start_bluetooth_discovery(duration=0)

    @pytest.mark.asyncio
    async def test_start_bluetooth_discovery_invalid_duration_too_high(self, mock_client):
        """Test starting discovery with duration too high."""
        with pytest.raises(ValueError, match="Duration must be between 1 and 60 seconds"):
            await mock_client.start_bluetooth_discovery(duration=61)

    @pytest.mark.asyncio
    async def test_get_bluetooth_discovery_result(self, mock_client):
        """Test getting Bluetooth discovery results."""
        mock_result = {
            "num": 2,
            "scan_status": 4,
            "list": [
                {"name": "Device 1", "ad": "AA:BB:CC:DD:EE:FF", "rssi": -50},
                {"name": "Device 2", "ad": "11:22:33:44:55:66", "rssi": -60},
            ],
        }
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=mock_result, raw=None))

        result = await mock_client.get_bluetooth_discovery_result()

        assert result["num"] == 2
        assert result["scan_status"] == 4
        assert len(result["bt_device"]) == 2
        assert result["bt_device"][0]["name"] == "Device 1"
        assert result["bt_device"][0]["mac"] == "aa:bb:cc:dd:ee:ff"  # Lowercase normalized
        assert result["bt_device"][0]["rssi"] == -50

    @pytest.mark.asyncio
    async def test_get_bluetooth_discovery_result_string_response(self, mock_client):
        """Test getting discovery results when API returns error string."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="error"))

        result = await mock_client.get_bluetooth_discovery_result()

        assert result["num"] == 0
        assert result["scan_status"] == 0
        assert result["bt_device"] == []

    @pytest.mark.asyncio
    async def test_get_bluetooth_discovery_result_no_mac(self, mock_client):
        """Test discovery results with device missing MAC address."""
        mock_result = {
            "num": 1,
            "scan_status": 4,
            "list": [
                {"name": "Device 1", "ad": ""},  # Missing MAC
            ],
        }
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=mock_result, raw=None))

        result = await mock_client.get_bluetooth_discovery_result()

        assert len(result["bt_device"]) == 0  # Device without MAC should be skipped

    @pytest.mark.asyncio
    async def test_get_bluetooth_discovery_result_backward_compatibility(self, mock_client):
        """Test discovery results with bt_device already present (backward compatibility)."""
        mock_result = {
            "num": 1,
            "scan_status": 4,
            "bt_device": [{"name": "Device 1", "mac": "AA:BB:CC:DD:EE:FF"}],
        }
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=mock_result, raw=None))

        result = await mock_client.get_bluetooth_discovery_result()

        assert result["bt_device"] == mock_result["bt_device"]


class TestBluetoothAPIScanning:
    """Test BluetoothAPI scanning helper methods."""

    @pytest.mark.asyncio
    async def test_scan_for_bluetooth_devices_success(self, mock_client):
        """Test complete Bluetooth scan with successful results."""
        # Mock the scan flow
        mock_client.clear_bluetooth_discovery_result = AsyncMock()
        mock_client.start_bluetooth_discovery = AsyncMock()
        # Need enough responses for the scan loop (max_wait_time iterations)
        # The scan waits up to max(duration + 5, 15) seconds, checking each second
        # For duration=3, max_wait_time = max(3+5, 15) = 15
        # We'll provide enough responses to complete quickly
        scan_responses = [
            {"scan_status": 2, "num": 0},  # Scanning
            {"scan_status": 2, "num": 0},  # Still scanning
            {
                "scan_status": 4,
                "num": 2,
                "bt_device": [
                    {"name": "Device 1", "mac": "AA:BB:CC:DD:EE:FF"},
                    {"name": "Device 2", "mac": "11:22:33:44:55:66"},
                ],
            },
        ]
        # Extend with enough responses to satisfy the loop
        mock_client.get_bluetooth_discovery_result = AsyncMock(
            side_effect=scan_responses + [scan_responses[-1]] * 20  # Repeat final response
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            devices = await mock_client.scan_for_bluetooth_devices(duration=3)

        assert len(devices) == 2
        assert devices[0]["name"] == "Device 1"
        mock_client.clear_bluetooth_discovery_result.assert_called_once()
        mock_client.start_bluetooth_discovery.assert_called_once_with(3)

    @pytest.mark.asyncio
    async def test_scan_for_bluetooth_devices_clear_failure(self, mock_client):
        """Test scan when clearing previous results fails."""
        mock_client.clear_bluetooth_discovery_result = AsyncMock(side_effect=WiiMError("Failed"))
        mock_client.start_bluetooth_discovery = AsyncMock()
        mock_client.get_bluetooth_discovery_result = AsyncMock(
            return_value={"scan_status": 4, "num": 1, "bt_device": [{"name": "Device", "mac": "AA:BB:CC:DD:EE:FF"}]}
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            devices = await mock_client.scan_for_bluetooth_devices(duration=3)

        # Should continue despite clear failure
        assert len(devices) == 1

    @pytest.mark.asyncio
    async def test_scan_for_bluetooth_devices_timeout(self, mock_client):
        """Test scan timeout when scan doesn't complete."""
        mock_client.clear_bluetooth_discovery_result = AsyncMock()
        mock_client.start_bluetooth_discovery = AsyncMock()
        mock_client.get_bluetooth_discovery_result = AsyncMock(return_value={"scan_status": 2, "num": 0})

        with patch("asyncio.sleep", new_callable=AsyncMock):
            devices = await mock_client.scan_for_bluetooth_devices(duration=3)

        assert devices == []  # Timeout returns empty list

    @pytest.mark.asyncio
    async def test_is_bluetooth_scan_in_progress_true(self, mock_client):
        """Test checking if scan is in progress (status 1 or 2)."""
        mock_client.get_bluetooth_discovery_result = AsyncMock(return_value={"scan_status": 2, "num": 0})

        result = await mock_client.is_bluetooth_scan_in_progress()

        assert result is True

    @pytest.mark.asyncio
    async def test_is_bluetooth_scan_in_progress_false(self, mock_client):
        """Test checking if scan is in progress when not scanning."""
        mock_client.get_bluetooth_discovery_result = AsyncMock(return_value={"scan_status": 4, "num": 0})

        result = await mock_client.is_bluetooth_scan_in_progress()

        assert result is False

    @pytest.mark.asyncio
    async def test_is_bluetooth_scan_in_progress_error(self, mock_client):
        """Test checking scan status when request fails."""
        mock_client.get_bluetooth_discovery_result = AsyncMock(side_effect=WiiMError("Failed"))

        result = await mock_client.is_bluetooth_scan_in_progress()

        assert result is False

    @pytest.mark.asyncio
    async def test_get_bluetooth_device_count(self, mock_client):
        """Test getting device count from last scan."""
        mock_client.get_bluetooth_discovery_result = AsyncMock(return_value={"num": 5, "scan_status": 4})

        count = await mock_client.get_bluetooth_device_count()

        assert count == 5

    @pytest.mark.asyncio
    async def test_get_bluetooth_device_count_error(self, mock_client):
        """Test getting device count when request fails."""
        mock_client.get_bluetooth_discovery_result = AsyncMock(side_effect=WiiMError("Failed"))

        count = await mock_client.get_bluetooth_device_count()

        assert count == 0

    @pytest.mark.asyncio
    async def test_get_last_bluetooth_scan_status(self, mock_client):
        """Test getting last scan status as string."""
        mock_client.get_bluetooth_discovery_result = AsyncMock(return_value={"scan_status": 2, "num": 0})

        status = await mock_client.get_last_bluetooth_scan_status()

        assert status == "Scanning"

    @pytest.mark.asyncio
    async def test_get_last_bluetooth_scan_status_unknown(self, mock_client):
        """Test getting scan status for unknown status code."""
        mock_client.get_bluetooth_discovery_result = AsyncMock(return_value={"scan_status": 99, "num": 0})

        status = await mock_client.get_last_bluetooth_scan_status()

        assert status == "Unknown"

    @pytest.mark.asyncio
    async def test_get_last_bluetooth_scan_status_error(self, mock_client):
        """Test getting scan status when request fails."""
        mock_client.get_bluetooth_discovery_result = AsyncMock(side_effect=WiiMError("Failed"))

        status = await mock_client.get_last_bluetooth_scan_status()

        assert status == "Unknown"


class TestBluetoothAPIConnection:
    """Test BluetoothAPI connection and pairing methods."""

    @pytest.mark.asyncio
    async def test_connect_bluetooth_device(self, mock_client):
        """Test connecting to Bluetooth device."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.connect_bluetooth_device("AA:BB:CC:DD:EE:FF")

        mock_client._request.assert_called_once()
        call_args = mock_client._request.call_args[0]
        assert "AA:BB:CC:DD:EE:FF" in call_args[0]

    @pytest.mark.asyncio
    async def test_connect_bluetooth_device_with_dash_separator(self, mock_client):
        """Test connecting with dash-separated MAC address."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.connect_bluetooth_device("AA-BB-CC-DD-EE-FF")

        call_args = mock_client._request.call_args[0]
        assert "AA:BB:CC:DD:EE:FF" in call_args[0]  # Should normalize to colons

    @pytest.mark.asyncio
    async def test_connect_bluetooth_device_invalid_mac(self, mock_client):
        """Test connecting with invalid MAC address."""
        with pytest.raises(ValueError, match="Invalid MAC address format"):
            await mock_client.connect_bluetooth_device("invalid")

    @pytest.mark.asyncio
    async def test_disconnect_bluetooth_device(self, mock_client):
        """Test disconnecting Bluetooth device."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.disconnect_bluetooth_device()

        mock_client._request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_bluetooth_pair_status(self, mock_client):
        """Test getting Bluetooth pair status."""
        mock_status = {"paired": True, "connected": True, "device": "AA:BB:CC:DD:EE:FF"}
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=mock_status, raw=None))

        result = await mock_client.get_bluetooth_pair_status()

        assert result == mock_status

    @pytest.mark.asyncio
    async def test_get_bluetooth_pair_status_error(self, mock_client):
        """Test getting pair status when request fails."""
        mock_client._request = AsyncMock(side_effect=WiiMError("Failed"))

        result = await mock_client.get_bluetooth_pair_status()

        assert result == {}

    @pytest.mark.asyncio
    async def test_get_bluetooth_pair_status_non_dict(self, mock_client):
        """Test getting pair status when response is not a dict."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="error"))

        result = await mock_client.get_bluetooth_pair_status()

        assert result == {}

    @pytest.mark.asyncio
    async def test_get_bluetooth_history_list(self, mock_client):
        """Test getting Bluetooth history as list."""
        mock_history = [
            {"name": "Device 1", "ad": "AA:BB:CC:DD:EE:FF", "ct": 1},
            {"name": "Device 2", "ad": "11:22:33:44:55:66", "ct": 0},
        ]
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=mock_history, raw=None))

        result = await mock_client.get_bluetooth_history()

        assert result == mock_history

    @pytest.mark.asyncio
    async def test_get_bluetooth_history_dict_with_list(self, mock_client):
        """Test getting Bluetooth history from dict with list field."""
        mock_history = {"list": [{"name": "Device 1", "ad": "AA:BB:CC:DD:EE:FF"}]}
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=mock_history, raw=None))

        result = await mock_client.get_bluetooth_history()

        assert result == mock_history["list"]

    @pytest.mark.asyncio
    async def test_get_bluetooth_history_dict_with_bt_device(self, mock_client):
        """Test getting Bluetooth history from dict with bt_device field."""
        mock_history = {"bt_device": [{"name": "Device 1", "mac": "AA:BB:CC:DD:EE:FF"}]}
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=mock_history, raw=None))

        result = await mock_client.get_bluetooth_history()

        assert result == mock_history["bt_device"]

    @pytest.mark.asyncio
    async def test_get_bluetooth_history_error(self, mock_client):
        """Test getting history when request fails."""
        mock_client._request = AsyncMock(side_effect=WiiMError("Failed"))

        result = await mock_client.get_bluetooth_history()

        assert result == []

    @pytest.mark.asyncio
    async def test_clear_bluetooth_discovery_result(self, mock_client):
        """Test clearing Bluetooth discovery results."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.clear_bluetooth_discovery_result()

        mock_client._request.assert_called_once()
