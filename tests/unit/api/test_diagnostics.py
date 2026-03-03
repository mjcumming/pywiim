"""Unit tests for DiagnosticsAPI mixin.

Tests reboot, time sync, and raw command functionality.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from pywiim.exceptions import WiiMError


class TestDiagnosticsAPI:
    """Test DiagnosticsAPI mixin methods."""

    @pytest.mark.asyncio
    async def test_reboot_success(self, mock_client):
        """Test reboot command success with default command."""
        mock_client._request_reboot = AsyncMock(return_value=None)

        await mock_client.reboot()

        mock_client._request_reboot.assert_called_once()
        assert "/httpapi.asp?command=reboot" in mock_client._request_reboot.call_args[0][0]

    @pytest.mark.asyncio
    async def test_reboot_uses_capability_command(self, mock_client):
        """Test reboot uses command from capabilities (Audio Pro devices).

        Audio Pro devices use StartRebootTime:0 instead of reboot.
        See: https://github.com/mjcumming/wiim/issues/177
        """
        mock_client._capabilities["reboot_command"] = "StartRebootTime:0"
        mock_client._request_reboot = AsyncMock(return_value=None)

        await mock_client.reboot()

        mock_client._request_reboot.assert_called_once()
        assert "/httpapi.asp?command=StartRebootTime:0" in mock_client._request_reboot.call_args[0][0]

    @pytest.mark.asyncio
    async def test_reboot_default_command_when_capability_missing(self, mock_client):
        """Test reboot uses default 'reboot' when capability not set."""
        # Ensure reboot_command is not in capabilities
        mock_client._capabilities.pop("reboot_command", None)
        mock_client._request_reboot = AsyncMock(return_value=None)

        await mock_client.reboot()

        mock_client._request_reboot.assert_called_once()
        assert "/httpapi.asp?command=reboot" in mock_client._request_reboot.call_args[0][0]

    @pytest.mark.asyncio
    async def test_reboot_handles_exception_gracefully(self, mock_client):
        """Test reboot handles exceptions gracefully (device may not respond)."""
        mock_client._request_reboot = AsyncMock(side_effect=Exception("Device stopped responding"))

        # Should not raise - reboot command was sent
        await mock_client.reboot()

        mock_client._request_reboot.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_reboot_success(self, mock_client):
        """Test _request_reboot with successful response."""
        mock_client._request = AsyncMock(return_value={"raw": "OK"})

        await mock_client._request_reboot("/httpapi.asp?command=reboot")

        mock_client._request.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_reboot_json_decode_error(self, mock_client):
        """Test _request_reboot handles JSON decode errors gracefully."""
        mock_client._request = AsyncMock(side_effect=ValueError("Expecting value: line 1 column 1 (char 0)"))

        # Should not raise - device stopped responding as expected
        await mock_client._request_reboot("/httpapi.asp?command=reboot")

        mock_client._request.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_reboot_empty_response(self, mock_client):
        """Test _request_reboot handles empty response errors gracefully."""
        mock_client._request = AsyncMock(side_effect=Exception("Empty response"))

        # Should not raise - device stopped responding as expected
        await mock_client._request_reboot("/httpapi.asp?command=reboot")

        mock_client._request.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_reboot_other_error_raises(self, mock_client):
        """Test _request_reboot re-raises non-parse errors."""
        mock_client._request = AsyncMock(side_effect=WiiMError("Network error"))

        with pytest.raises(WiiMError, match="Network error"):
            await mock_client._request_reboot("/httpapi.asp?command=reboot")

    @pytest.mark.asyncio
    async def test_sync_time_with_timestamp(self, mock_client):
        """Test sync_time with provided timestamp."""
        mock_client._request = AsyncMock(return_value={"raw": "OK"})

        await mock_client.sync_time(1234567890)

        mock_client._request.assert_called_once()
        assert "/httpapi.asp?command=timeSync:1234567890" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_sync_time_without_timestamp(self, mock_client):
        """Test sync_time uses current system time when timestamp not provided."""
        mock_client._request = AsyncMock(return_value={"raw": "OK"})

        with patch("pywiim.api.diagnostics.time.time", return_value=1234567890.5):
            await mock_client.sync_time()

        mock_client._request.assert_called_once()
        assert "/httpapi.asp?command=timeSync:1234567890" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_send_command_success(self, mock_client):
        """Test send_command with valid command."""
        mock_client._request = AsyncMock(return_value={"status": "ok", "volume": 50})

        result = await mock_client.send_command("getStatusEx")

        assert result == {"status": "ok", "volume": 50}
        mock_client._request.assert_called_once()
        assert "/httpapi.asp?command=getStatusEx" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_send_command_with_special_chars(self, mock_client):
        """Test send_command URL-encodes special characters."""
        mock_client._request = AsyncMock(return_value={"raw": "OK"})

        await mock_client.send_command("getStatus:param=value")

        mock_client._request.assert_called_once()
        # Command should be URL-encoded
        assert "getStatus%3Aparam%3Dvalue" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_send_command_error(self, mock_client):
        """Test send_command raises on error."""
        mock_client._request = AsyncMock(side_effect=WiiMError("Request failed"))

        with pytest.raises(WiiMError, match="Request failed"):
            await mock_client.send_command("invalidCommand")

    @pytest.mark.asyncio
    async def test_get_debug_info_success(self, mock_client):
        """Test get_debug_info returns raw debug info dict."""
        mock_client._request = AsyncMock(
            return_value={
                "system_ready": "1",
                "slave_status": "0",
                "play_status": "0",
                "slave_num": "0",
            }
        )

        result = await mock_client.get_debug_info()

        assert result == {
            "system_ready": "1",
            "slave_status": "0",
            "play_status": "0",
            "slave_num": "0",
        }
        mock_client._request.assert_called_once()
        assert "/httpapi.asp?command=getDebugInfo" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_get_debug_info_error(self, mock_client):
        """Test get_debug_info raises on request failure."""
        mock_client._request = AsyncMock(side_effect=WiiMError("Not supported"))

        with pytest.raises(WiiMError, match="Not supported"):
            await mock_client.get_debug_info()
