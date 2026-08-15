"""Diagnostics / maintenance helpers (reboot, time sync, raw commands, getDebugInfo)."""

from __future__ import annotations

import logging
import time
from typing import Any, cast
from urllib.parse import quote

from .constants import API_ENDPOINT_DEBUG_INFO

_LOGGER = logging.getLogger(__name__)

# Tried after the profile/capability command if the device returns "unknown command".
# WiiM Amp (and some current WiiM firmware) rejects `reboot` and accepts StartRebootTime:1.
# Audio Pro devices use StartRebootTime:0.
_REBOOT_FALLBACKS = ("StartRebootTime:1", "StartRebootTime:0", "reboot")


def _is_unknown_reboot_command(resp: Any) -> bool:
    """Return True when the device rejected the reboot command as unknown."""
    if resp is None:
        return False
    raw = getattr(resp, "raw", None)
    parsed = getattr(resp, "parsed", None)
    text = str(raw if raw not in (None, "") else parsed or "").lower()
    return "unknown command" in text


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
        - WiiM devices (legacy): "reboot"
        - WiiM Amp / current WiiM firmware: "StartRebootTime:1"
        - Audio Pro devices: "StartRebootTime:0"

        The first command comes from device capabilities/profile. If the device
        returns "unknown command", remaining fallbacks are tried and the working
        command is cached on the client. See: https://github.com/mjcumming/wiim/issues/260

        Raises:
            WiiMError: If the request fails before the device reboots.
        """
        primary = self._capabilities.get("reboot_command", "reboot")  # type: ignore[attr-defined]
        commands: list[str] = [primary]
        for fallback in _REBOOT_FALLBACKS:
            if fallback not in commands:
                commands.append(fallback)

        last_err: Exception | None = None
        for command in commands:
            endpoint = f"/httpapi.asp?command={command}"
            _LOGGER.debug("Sending reboot command: %s", command)
            try:
                resp = await self._request_reboot(endpoint)
            except Exception as err:
                last_err = err
                error_str = str(err).lower()
                if "unknown command" in error_str:
                    _LOGGER.debug("Reboot command %s not supported, trying fallback", command)
                    continue
                # Connection drop / empty body: command was likely accepted
                _LOGGER.info("Reboot command sent to device (device may not respond): %s", err)
                return

            if _is_unknown_reboot_command(resp):
                _LOGGER.debug("Reboot command %s returned unknown command, trying fallback", command)
                continue

            if command != primary:
                self._capabilities["reboot_command"] = command  # type: ignore[attr-defined]
                _LOGGER.info("Reboot command %s succeeded; cached for this device", command)
            return

        if last_err:
            _LOGGER.info("Reboot command sent to device (device may not respond): %s", last_err)

    async def _request_reboot(self, endpoint: str) -> Any:
        """Special request method for reboot that handles empty responses gracefully.

        Args:
            endpoint: The reboot endpoint to call.

        Returns:
            ApiResponse from the device, or None when the device dropped the
            connection after accepting the command.

        Raises:
            WiiMError: If the request fails for reasons other than expected reboot behavior.
        """
        try:
            # Try to send the reboot command
            return await self._request(endpoint)  # type: ignore[attr-defined]
        except Exception as err:
            # If the request fails due to parsing issues (common with reboot),
            # we still consider it successful since the command was sent
            error_str = str(err).lower()
            if any(x in error_str for x in ["expecting value", "json decode", "empty response"]):
                _LOGGER.info("Reboot command sent successfully (device stopped responding as expected)")
                return None
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
