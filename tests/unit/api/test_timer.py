"""Unit tests for TimerAPI mixin.

Tests timer and alarm functionality for WiiM devices.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pywiim.api.base import ApiResponse
from pywiim.api.constants import (
    ALARM_OP_PLAYBACK,
    ALARM_OP_SHELL,
    ALARM_TRIGGER_DAILY,
    ALARM_TRIGGER_MONTHLY,
    ALARM_TRIGGER_ONCE,
    ALARM_TRIGGER_WEEKLY,
    ALARM_TRIGGER_WEEKLY_BITMASK,
)


class TestTimerAPISleepTimer:
    """Test TimerAPI sleep timer methods."""

    @pytest.mark.asyncio
    async def test_set_sleep_timer_success(self, mock_client):
        """Test setting sleep timer successfully."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_sleep_timer(1800)

        mock_client._request.assert_called_once_with("/httpapi.asp?command=setShutdown:1800")

    @pytest.mark.asyncio
    async def test_set_sleep_timer_immediate(self, mock_client):
        """Test immediate shutdown."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_sleep_timer(0)

        mock_client._request.assert_called_once_with("/httpapi.asp?command=setShutdown:0")

    @pytest.mark.asyncio
    async def test_set_sleep_timer_cancel(self, mock_client):
        """Test cancelling sleep timer."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_sleep_timer(-1)

        mock_client._request.assert_called_once_with("/httpapi.asp?command=setShutdown:-1")

    @pytest.mark.asyncio
    async def test_get_sleep_timer_with_value(self, mock_client):
        """Test getting remaining sleep timer seconds."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="600"))

        remaining = await mock_client.get_sleep_timer()

        assert remaining == 600
        mock_client._request.assert_called_once_with("/httpapi.asp?command=getShutdown")

    @pytest.mark.asyncio
    async def test_get_sleep_timer_dict_response(self, mock_client):
        """Test getting sleep timer with dict response."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed={"shutdown": "300"}, raw=None))

        remaining = await mock_client.get_sleep_timer()

        assert remaining == 300

    @pytest.mark.asyncio
    async def test_get_sleep_timer_no_timer(self, mock_client):
        """Test getting sleep timer when none is active."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="0"))

        remaining = await mock_client.get_sleep_timer()

        assert remaining == 0

    @pytest.mark.asyncio
    async def test_get_sleep_timer_invalid_response(self, mock_client):
        """Test getting sleep timer with invalid response."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed={"invalid": "data"}, raw=None))

        remaining = await mock_client.get_sleep_timer()

        assert remaining == 0  # Fallback to 0 on parse error

    @pytest.mark.asyncio
    async def test_cancel_sleep_timer(self, mock_client):
        """Test cancel sleep timer convenience method."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.cancel_sleep_timer()

        mock_client._request.assert_called_once_with("/httpapi.asp?command=setShutdown:-1")


class TestTimerAPIAlarms:
    """Test TimerAPI alarm methods."""

    @pytest.mark.asyncio
    async def test_set_alarm_daily(self, mock_client):
        """Test setting a daily alarm."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_alarm(
            alarm_id=0,
            trigger=ALARM_TRIGGER_DAILY,
            operation=ALARM_OP_PLAYBACK,
            time="070000",
        )

        mock_client._request.assert_called_once_with("/httpapi.asp?command=setAlarmClock:0:2:1:070000")

    @pytest.mark.asyncio
    async def test_set_alarm_once(self, mock_client):
        """Test setting a one-time alarm."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_alarm(
            alarm_id=1,
            trigger=ALARM_TRIGGER_ONCE,
            operation=ALARM_OP_PLAYBACK,
            time="080000",
            day="20250120",
        )

        mock_client._request.assert_called_once_with("/httpapi.asp?command=setAlarmClock:1:1:1:080000:20250120")

    @pytest.mark.asyncio
    async def test_set_alarm_weekly(self, mock_client):
        """Test setting a weekly alarm."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_alarm(
            alarm_id=2,
            trigger=ALARM_TRIGGER_WEEKLY,
            operation=ALARM_OP_PLAYBACK,
            time="090000",
            day="01",  # Monday
        )

        mock_client._request.assert_called_once_with("/httpapi.asp?command=setAlarmClock:2:3:1:090000:01")

    @pytest.mark.asyncio
    async def test_set_alarm_weekly_bitmask(self, mock_client):
        """Test setting a weekly alarm with bitmask."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_alarm(
            alarm_id=0,
            trigger=ALARM_TRIGGER_WEEKLY_BITMASK,
            operation=ALARM_OP_PLAYBACK,
            time="070000",
            day="3E",  # Mon-Fri (binary 0111110)
        )

        mock_client._request.assert_called_once_with("/httpapi.asp?command=setAlarmClock:0:4:1:070000:3E")

    @pytest.mark.asyncio
    async def test_set_alarm_monthly(self, mock_client):
        """Test setting a monthly alarm."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_alarm(
            alarm_id=1,
            trigger=ALARM_TRIGGER_MONTHLY,
            operation=ALARM_OP_PLAYBACK,
            time="100000",
            day="15",  # 15th of each month
        )

        mock_client._request.assert_called_once_with("/httpapi.asp?command=setAlarmClock:1:5:1:100000:15")

    @pytest.mark.asyncio
    async def test_set_alarm_with_url(self, mock_client):
        """Test setting an alarm with a media URL."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_alarm(
            alarm_id=0,
            trigger=ALARM_TRIGGER_ONCE,
            operation=ALARM_OP_PLAYBACK,
            time="060000",
            day="20250125",
            url="http://example.com/alarm.mp3",
        )

        mock_client._request.assert_called_once_with(
            "/httpapi.asp?command=setAlarmClock:0:1:1:060000:20250125:http://example.com/alarm.mp3"
        )

    @pytest.mark.asyncio
    async def test_set_alarm_shell_operation(self, mock_client):
        """Test setting an alarm with shell operation."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_alarm(
            alarm_id=2,
            trigger=ALARM_TRIGGER_DAILY,
            operation=ALARM_OP_SHELL,
            time="120000",
        )

        mock_client._request.assert_called_once_with("/httpapi.asp?command=setAlarmClock:2:2:0:120000")

    @pytest.mark.asyncio
    async def test_set_alarm_invalid_id_low(self, mock_client):
        """Test setting alarm with invalid ID (too low)."""
        with pytest.raises(ValueError, match="alarm_id must be 0-2"):
            await mock_client.set_alarm(
                alarm_id=-1,
                trigger=ALARM_TRIGGER_DAILY,
                operation=ALARM_OP_PLAYBACK,
                time="070000",
            )

    @pytest.mark.asyncio
    async def test_set_alarm_invalid_id_high(self, mock_client):
        """Test setting alarm with invalid ID (too high)."""
        with pytest.raises(ValueError, match="alarm_id must be 0-2"):
            await mock_client.set_alarm(
                alarm_id=3,
                trigger=ALARM_TRIGGER_DAILY,
                operation=ALARM_OP_PLAYBACK,
                time="070000",
            )

    @pytest.mark.asyncio
    async def test_set_alarm_url_requires_day(self, mock_client):
        """Test that URL requires day parameter for certain trigger types."""
        with pytest.raises(ValueError, match="day parameter required"):
            await mock_client.set_alarm(
                alarm_id=0,
                trigger=ALARM_TRIGGER_ONCE,
                operation=ALARM_OP_PLAYBACK,
                time="070000",
                url="http://example.com/alarm.mp3",
            )

    @pytest.mark.asyncio
    async def test_get_alarm(self, mock_client):
        """Test getting a specific alarm configuration."""
        mock_response = {
            "enable": "1",
            "trigger": "2",
            "operation": "1",
            "time": "07:00:00",
        }
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=mock_response, raw=None))

        alarm = await mock_client.get_alarm(0)

        assert alarm == mock_response
        mock_client._request.assert_called_once_with("/httpapi.asp?command=getAlarmClock:0")

    @pytest.mark.asyncio
    async def test_get_alarm_disabled(self, mock_client):
        """Test getting a disabled alarm."""
        mock_response = {
            "enable": "0",
            "trigger": "0",
            "operation": "0",
            "time": "00:00:00",
        }
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=mock_response, raw=None))

        alarm = await mock_client.get_alarm(1)

        assert alarm["enable"] == "0"

    @pytest.mark.asyncio
    async def test_get_alarm_invalid_id(self, mock_client):
        """Test getting alarm with invalid ID."""
        with pytest.raises(ValueError, match="alarm_id must be 0-2"):
            await mock_client.get_alarm(5)

    @pytest.mark.asyncio
    async def test_get_alarms(self, mock_client):
        """Test getting all alarm configurations."""
        mock_responses = [
            {"enable": "1", "trigger": "2", "time": "07:00:00"},
            {"enable": "0", "trigger": "0", "time": "00:00:00"},
            {"enable": "1", "trigger": "4", "time": "08:00:00"},
        ]
        mock_client._request = AsyncMock(side_effect=[ApiResponse(parsed=r, raw=None) for r in mock_responses])

        alarms = await mock_client.get_alarms()

        assert len(alarms) == 3
        assert alarms[0]["enable"] == "1"
        assert alarms[1]["enable"] == "0"
        assert alarms[2]["enable"] == "1"
        assert mock_client._request.call_count == 3

    @pytest.mark.asyncio
    async def test_get_alarms_with_failure(self, mock_client):
        """Test getting alarms when one request fails."""
        mock_client._request = AsyncMock(
            side_effect=[
                ApiResponse(
                    parsed={"enable": "1", "trigger": "2", "time": "07:00:00"},
                    raw=None,
                ),
                Exception("Network error"),
                ApiResponse(
                    parsed={"enable": "1", "trigger": "4", "time": "08:00:00"},
                    raw=None,
                ),
            ]
        )

        alarms = await mock_client.get_alarms()

        # Should still return 3 items, with empty dict for failed alarm
        assert len(alarms) == 3
        assert alarms[0]["enable"] == "1"
        assert alarms[1] == {}  # Failed request
        assert alarms[2]["enable"] == "1"

    @pytest.mark.asyncio
    async def test_delete_alarm(self, mock_client):
        """Test deleting an alarm."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.delete_alarm(0)

        # Should call set_alarm with trigger=0 (cancel)
        mock_client._request.assert_called_once_with("/httpapi.asp?command=setAlarmClock:0:0:1:000000")

    @pytest.mark.asyncio
    async def test_delete_alarm_invalid_id(self, mock_client):
        """Test deleting alarm with invalid ID."""
        with pytest.raises(ValueError, match="alarm_id must be 0-2"):
            await mock_client.delete_alarm(10)

    @pytest.mark.asyncio
    async def test_stop_current_alarm(self, mock_client):
        """Test stopping currently ringing alarm."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.stop_current_alarm()

        mock_client._request.assert_called_once_with("/httpapi.asp?command=alarmStop")

    @pytest.mark.asyncio
    async def test_sync_time(self, mock_client):
        """Test syncing device time."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.sync_time("20250117123045")

        mock_client._request.assert_called_once_with("/httpapi.asp?command=timeSync:20250117123045")
