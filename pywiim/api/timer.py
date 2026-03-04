"""Timer and alarm helpers for WiiM HTTP client.

Timer and alarm features are supported by WiiM devices via HTTP API.
This module provides methods for managing device sleep timers and alarm clocks.

Note: These features are WiiM-specific and may not be available on generic LinkPlay devices.
API documentation: https://www.wiimhome.com/pdf/HTTP%20API%20for%20WiiM%20Mini.pdf
"""

from __future__ import annotations

import logging
from typing import Any

from .constants import (
    ALARM_OP_PLAYBACK,
    ALARM_TRIGGER_CANCEL,
    ALARM_TRIGGER_DAILY,
    API_ENDPOINT_ALARM_STOP,
    API_ENDPOINT_GET_ALARM,
    API_ENDPOINT_GET_SHUTDOWN,
    API_ENDPOINT_SET_ALARM,
    API_ENDPOINT_SET_SHUTDOWN,
)

_LOGGER = logging.getLogger(__name__)


class TimerAPI:
    """Timer and alarm helpers.

    This mixin provides methods for managing device sleep timers and alarm clocks.

    Supported by: WiiM devices via HTTP API.

    Note: These features are WiiM-specific. Generic LinkPlay devices may not support them.
    All alarm times are in UTC timezone per the WiiM API specification.
    """

    # Sleep Timer Methods

    async def set_sleep_timer(self, seconds: int) -> None:
        """Set sleep timer to stop playback after specified seconds.

        Args:
            seconds: Duration in seconds before device stops playback
                - Positive value: Set timer for that many seconds
                - 0: Stop playback immediately
                - -1: Cancel any active sleep timer

        Raises:
            WiiMError: If the request fails.

        Note:
            This feature is WiiM-specific and may not work on generic LinkPlay devices.

        Example:
            ```python
            # Sleep after 30 minutes
            await client.set_sleep_timer(1800)

            # Cancel sleep timer
            await client.set_sleep_timer(-1)
            ```
        """
        endpoint = f"{API_ENDPOINT_SET_SHUTDOWN}{seconds}"
        await self._request(endpoint)  # type: ignore[attr-defined]
        if seconds == -1:
            _LOGGER.debug("Sleep timer cancelled")
        elif seconds == 0:
            _LOGGER.debug("Device shutdown immediately")
        else:
            _LOGGER.debug("Sleep timer set for %d seconds", seconds)

    async def get_sleep_timer(self) -> int:
        """Get remaining sleep timer seconds.

        Returns:
            Remaining seconds until device stops playback, or 0 if no timer is active.

        Raises:
            WiiMError: If the request fails.

        Note:
            This feature is WiiM-specific and may not work on generic LinkPlay devices.

        Example:
            ```python
            remaining = await client.get_sleep_timer()
            print(f"Device will sleep in {remaining} seconds")
            ```
        """
        result = await self._request(API_ENDPOINT_GET_SHUTDOWN)  # type: ignore[attr-defined]
        # API returns the number as a string or in a dict
        if isinstance(result.parsed, dict):
            seconds = result.parsed.get("shutdown", result.parsed.get("timer", result.parsed.get("seconds", 0)))
        else:
            seconds = result.raw or result.parsed

        try:
            return int(seconds)  # type: ignore[arg-type]
        except (ValueError, TypeError):
            _LOGGER.warning("Unexpected response format from getShutdown: %s", result.parsed or result.raw)
            return 0

    async def cancel_sleep_timer(self) -> None:
        """Cancel active sleep timer.

        This is a convenience method equivalent to set_sleep_timer(-1).

        Raises:
            WiiMError: If the request fails.

        Example:
            ```python
            await client.cancel_sleep_timer()
            ```
        """
        await self.set_sleep_timer(-1)

    # Alarm Clock Methods

    async def set_alarm(
        self,
        alarm_id: int,
        trigger: int,
        operation: int,
        time: str,
        day: str | None = None,
        url: str | None = None,
    ) -> None:
        """Set or configure an alarm.

        WiiM devices support 3 independent alarm slots (indices 0-2).

        Args:
            alarm_id: Alarm slot index (0-2)
            trigger: Alarm trigger type (use ALARM_TRIGGER_* constants)
                - ALARM_TRIGGER_CANCEL (0): Cancel alarm
                - ALARM_TRIGGER_ONCE (1): One-time alarm (requires day=YYYYMMDD)
                - ALARM_TRIGGER_DAILY (2): Every day
                - ALARM_TRIGGER_WEEKLY (3): Every week (day="00"-"06" for Sun-Sat)
                - ALARM_TRIGGER_WEEKLY_BITMASK (4): Week bitmask (day="7F"=all, "01"=Sun)
                - ALARM_TRIGGER_MONTHLY (5): Every month (day="01"-"31")
            operation: Alarm operation (use ALARM_OP_* constants)
                - ALARM_OP_SHELL (0): Execute shell command
                - ALARM_OP_PLAYBACK (1): Play audio/ring
                - ALARM_OP_STOP (2): Stop playback
            time: Alarm time in HHMMSS format (UTC timezone)
            day: Day parameter (format depends on trigger type, optional for daily/cancel)
            url: Media URL to play or shell command to execute (optional, max 256 bytes)

        Raises:
            ValueError: If alarm_id is not 0-2
            WiiMError: If the request fails.

        Note:
            All times are in UTC. Applications must handle timezone conversion.
            This feature is WiiM-specific and may not work on generic LinkPlay devices.

        Example:
            ```python
            from pywiim.api.constants import ALARM_TRIGGER_DAILY, ALARM_OP_PLAYBACK

            # Set daily alarm at 7:00 AM UTC
            await client.set_alarm(
                alarm_id=0,
                trigger=ALARM_TRIGGER_DAILY,
                operation=ALARM_OP_PLAYBACK,
                time="070000",
            )

            # Set weekday alarm (Monday-Friday)
            await client.set_alarm(
                alarm_id=1,
                trigger=ALARM_TRIGGER_WEEKLY_BITMASK,
                operation=ALARM_OP_PLAYBACK,
                time="073000",
                day="3E",  # Binary 0111110 = Mon-Fri
            )
            ```
        """
        # Validate alarm_id
        if not 0 <= alarm_id <= 2:
            raise ValueError(f"alarm_id must be 0-2, got {alarm_id}")

        # Build command
        cmd_parts = [str(alarm_id), str(trigger), str(operation), time]

        # Add optional day parameter
        if day is not None:
            cmd_parts.append(day)

        # Add optional URL parameter
        if url is not None:
            # Day is required if URL is provided (API format requirement)
            if day is None and trigger not in (ALARM_TRIGGER_CANCEL, ALARM_TRIGGER_DAILY):
                raise ValueError("day parameter required when url is provided for this trigger type")
            cmd_parts.append(url)

        # Build endpoint
        command = ":".join(cmd_parts)
        endpoint = f"{API_ENDPOINT_SET_ALARM}{command}"

        await self._request(endpoint)  # type: ignore[attr-defined]

        if trigger == ALARM_TRIGGER_CANCEL:
            _LOGGER.debug("Alarm %d cancelled", alarm_id)
        else:
            _LOGGER.debug("Alarm %d set: trigger=%d, op=%d, time=%s", alarm_id, trigger, operation, time)

    async def get_alarm(self, alarm_id: int) -> dict[str, Any]:
        """Get specific alarm configuration.

        Args:
            alarm_id: Alarm slot index (0-2)

        Returns:
            Dictionary with alarm configuration. Structure includes:
            - enable: "1" if enabled, "0" if disabled
            - trigger: Trigger type (int as string)
            - operation: Operation type (int as string)
            - time: Alarm time in HH:MM:SS format (UTC)
            - date/week_day/day: Depends on trigger type
            - path: Media URL or shell command (if set)

        Raises:
            ValueError: If alarm_id is not 0-2
            WiiMError: If the request fails.

        Note:
            This feature is WiiM-specific and may not work on generic LinkPlay devices.

        Example:
            ```python
            alarm = await client.get_alarm(0)
            if alarm.get("enable") == "1":
                print(f"Alarm at {alarm.get('time')}")
            ```
        """
        # Validate alarm_id
        if not 0 <= alarm_id <= 2:
            raise ValueError(f"alarm_id must be 0-2, got {alarm_id}")

        endpoint = f"{API_ENDPOINT_GET_ALARM}{alarm_id}"
        result = await self._request(endpoint)  # type: ignore[attr-defined]

        # API returns dict with alarm configuration
        if isinstance(result.parsed, dict):
            return result.parsed
        _LOGGER.warning("Unexpected response format from getAlarmClock: %s", result.parsed or result.raw)
        return {}

    async def get_alarms(self) -> list[dict[str, Any]]:
        """Get all alarm configurations (3 slots).

        Returns:
            List of 3 alarm configuration dictionaries (indices 0-2).
            Each dictionary has the same structure as get_alarm().

        Raises:
            WiiMError: If any request fails.

        Note:
            This method makes 3 API calls to retrieve all alarm slots.
            This feature is WiiM-specific and may not work on generic LinkPlay devices.

        Example:
            ```python
            alarms = await client.get_alarms()
            for i, alarm in enumerate(alarms):
                if alarm.get("enable") == "1":
                    print(f"Alarm {i}: {alarm.get('time')}")
            ```
        """
        alarms = []
        for alarm_id in range(3):
            try:
                alarm = await self.get_alarm(alarm_id)
                alarms.append(alarm)
            except Exception as e:
                _LOGGER.warning("Failed to get alarm %d: %s", alarm_id, e)
                # Add empty dict to maintain index consistency
                alarms.append({})

        return alarms

    async def delete_alarm(self, alarm_id: int) -> None:
        """Delete (cancel) an alarm.

        This is a convenience method that sets the alarm trigger to ALARM_TRIGGER_CANCEL.

        Args:
            alarm_id: Alarm slot index (0-2)

        Raises:
            ValueError: If alarm_id is not 0-2
            WiiMError: If the request fails.

        Example:
            ```python
            await client.delete_alarm(0)
            ```
        """
        # Cancel alarm by setting trigger to 0
        await self.set_alarm(
            alarm_id=alarm_id,
            trigger=ALARM_TRIGGER_CANCEL,
            operation=ALARM_OP_PLAYBACK,  # Operation doesn't matter for cancel
            time="000000",  # Time doesn't matter for cancel
        )

    async def stop_current_alarm(self) -> None:
        """Stop currently ringing alarm.

        Stops the alarm that is currently playing/ringing.

        Raises:
            WiiMError: If the request fails.

        Note:
            This feature is WiiM-specific and may not work on generic LinkPlay devices.

        Example:
            ```python
            await client.stop_current_alarm()
            ```
        """
        await self._request(API_ENDPOINT_ALARM_STOP)  # type: ignore[attr-defined]
        _LOGGER.debug("Current alarm stopped")
