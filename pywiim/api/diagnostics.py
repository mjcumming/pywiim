"""Diagnostics / maintenance helpers (reboot, time sync, raw commands, getDebugInfo)."""

from __future__ import annotations

import logging
import time
from typing import Any, cast
from urllib.parse import quote

from .constants import API_ENDPOINT_DEBUG_INFO

_LOGGER = logging.getLogger(__name__)


class DiagnosticsAPI:
    """Low-level device maintenance helpers.

    This mixin provides diagnostic and maintenance functions for device management.
    Use with caution - some operations (like reboot) may disconnect the device.
    """

    async def reboot(self) -> None:
        """Reboot the device.

        Note: This command may not return a response as the device will restart.
        The method handles this gracefully and considers the command successful
        even if the device stops responding.

        The reboot command varies by device:
        - WiiM devices: "reboot"
        - Audio Pro devices: "StartRebootTime:0"

        The correct command is determined from device capabilities/profile.
        See: https://github.com/mjcumming/wiim/issues/177

        Raises:
            WiiMError: If the request fails before the device reboots.
        """
        try:
            # Get reboot command from capabilities (set from device profile)
            # Default to "reboot" for WiiM and most LinkPlay devices
            reboot_command = self._capabilities.get("reboot_command", "reboot")  # type: ignore[attr-defined]
            endpoint = f"/httpapi.asp?command={reboot_command}"

            _LOGGER.debug("Sending reboot command: %s", reboot_command)

            # Send reboot command - device may not respond after this
            # Use a custom request method that handles empty responses gracefully
            await self._request_reboot(endpoint)
        except Exception as err:
            # Reboot commands often don't return proper responses
            # Log the attempt but don't fail the service call
            _LOGGER.info("Reboot command sent to device (device may not respond): %s", err)
            # Don't re-raise - reboot command was sent successfully

    async def _request_reboot(self, endpoint: str) -> None:
        """Special request method for reboot that handles empty responses gracefully.

        Args:
            endpoint: The reboot endpoint to call.

        Raises:
            WiiMError: If the request fails for reasons other than expected reboot behavior.
        """
        try:
            # Try to send the reboot command
            await self._request(endpoint)  # type: ignore[attr-defined]
        except Exception as err:
            # If the request fails due to parsing issues (common with reboot),
            # we still consider it successful since the command was sent
            error_str = str(err).lower()
            if any(x in error_str for x in ["expecting value", "json decode", "empty response"]):
                _LOGGER.info("Reboot command sent successfully (device stopped responding as expected)")
                return
            else:
                # Re-raise other types of errors
                raise

    async def sync_time(self, ts: int | None = None) -> None:
        """Synchronize device time with system time or provided timestamp.

        Args:
            ts: Unix timestamp (seconds since epoch). If None, uses current system time.

        Raises:
            WiiMError: If the request fails.
        """
        if ts is None:
            ts = int(time.time())
        await self._request(f"/httpapi.asp?command=timeSync:{ts}")  # type: ignore[attr-defined]

    async def get_debug_info(self) -> dict[str, Any]:
        """Return raw device debug information (getDebugInfo).

        Retrieves low-level debug state (slave status, play flags, crash
        indicators, UPnP action counts, etc.). Documented in the WiiM HTTP API;
        output may be incomplete or vary by device/firmware. Primarily for
        diagnostics and troubleshooting.

        Returns:
            Raw response dict (e.g. system_ready, slave_status, slave_latency,
            play_status, crash flags, upnp_action_*, wifi_abort_date, etc.).

        Raises:
            WiiMError: If the request fails.
        """
        result = await self._request(API_ENDPOINT_DEBUG_INFO)  # type: ignore[attr-defined]
        return cast(dict[str, Any], result.parsed or {})

    async def send_command(self, command: str) -> dict[str, Any]:
        """Send arbitrary LinkPlay HTTP command (expert use only).

        This method allows sending raw LinkPlay commands for advanced use cases.
        Use with caution - incorrect commands may cause device errors.

        Args:
            command: Raw LinkPlay command string (e.g., "getStatusEx").

        Returns:
            Response dictionary from the device.

        Raises:
            WiiMError: If the request fails.

        Example:
            >>> response = await client.send_command("getStatusEx")
        """
        endpoint = f"/httpapi.asp?command={quote(command)}"
        result = await self._request(endpoint)  # type: ignore[attr-defined]
        return cast(dict[str, Any], result.parsed or {})
