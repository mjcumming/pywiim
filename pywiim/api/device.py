"""Device-related helpers for WiiM HTTP client.

Contains only low-level calls for static device information and LED control.
All networking is provided by the base client.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from ..models import DeviceInfo
from .constants import (
    API_ENDPOINT_ARYLIC_LED,
    API_ENDPOINT_ARYLIC_LED_BRIGHTNESS,
    API_ENDPOINT_FIRMWARE,
    API_ENDPOINT_LED,
    API_ENDPOINT_LED_BRIGHTNESS,
    API_ENDPOINT_MAC,
    API_ENDPOINT_STATUS,
)

_LOGGER = logging.getLogger(__name__)


def _get_led_command_format(device_info: DeviceInfo) -> str:
    """Get the LED command format for a specific device type.

    Args:
        device_info: Device information

    Returns:
        LED command format: "standard" or "arylic"
    """
    if not device_info.model:
        return "standard"  # Default to standard for unknown devices

    model_lower = device_info.model.lower()

    # Arylic devices use different LED commands
    if any(arylic_type in model_lower for arylic_type in ["arylic", "up2stream"]):
        return "arylic"

    return "standard"


class DeviceAPI:
    """Device-information and LED helpers expected by the integration.

    This mixin provides methods for retrieving device information and controlling
    device LEDs with vendor-specific command handling.
    """

    # ------------------------------------------------------------------
    # Information helpers
    # ------------------------------------------------------------------

    async def get_device_info(self) -> dict[str, Any]:
        """Return the raw `getStatusEx` JSON payload.

        Returns:
            Dictionary containing device status information.

        Raises:
            WiiMError: If the request fails.
        """
        result = await self._request(API_ENDPOINT_STATUS)  # type: ignore[attr-defined]
        if isinstance(result.parsed, dict):
            return cast(dict[str, Any], result.parsed)
        return {"raw": result.raw} if result.raw is not None else {}

    async def get_device_info_model(self) -> DeviceInfo:
        """Return a pydantic-validated :class:`DeviceInfo`.

        Returns:
            DeviceInfo model instance.

        Raises:
            WiiMError: If the request fails.
            WiiMInvalidDataError: If the response cannot be validated.
        """
        return DeviceInfo.model_validate(await self.get_device_info())

    async def get_firmware_version(self) -> str:
        """Return firmware version string (empty on error).

        Returns:
            Firmware version string, or empty string if unavailable.

        Raises:
            WiiMError: If the request fails.
        """
        resp = await self._request(API_ENDPOINT_FIRMWARE)  # type: ignore[attr-defined]
        return resp.parsed.get("firmware", "") if isinstance(resp.parsed, dict) else ""

    async def get_mac_address(self) -> str:
        """Return MAC address string (empty on error).

        Returns:
            MAC address string, or empty string if unavailable.

        Raises:
            WiiMError: If the request fails.
        """
        resp = await self._request(API_ENDPOINT_MAC)  # type: ignore[attr-defined]
        return resp.parsed.get("mac", "") if isinstance(resp.parsed, dict) else ""

    # ------------------------------------------------------------------
    # LED helpers
    # ------------------------------------------------------------------

    async def set_led(self, enabled: bool) -> None:
        """Enable or disable the front LED with device-specific commands.

        Args:
            enabled: True to enable LED, False to disable.

        Note:
            This method handles vendor-specific LED commands (Arylic vs standard)
            and falls back gracefully if LED control is not supported.
        """
        try:
            # Get device info to determine LED command format
            device_info = await self.get_device_info_model()
            led_format = _get_led_command_format(device_info)

            if led_format == "arylic":
                # Arylic devices use MCU+PAS+RAKOIT:LED commands
                # LED:1 = on, LED:0 = off
                # Note: These commands are experimental based on user research
                try:
                    await self._request(f"{API_ENDPOINT_ARYLIC_LED}{1 if enabled else 0}")  # type: ignore[attr-defined]
                except Exception as arylic_err:
                    # Fallback: try standard commands in case Arylic supports them
                    _LOGGER.debug("Arylic LED command failed, trying standard: %s", arylic_err)
                    try:
                        await self._request(f"{API_ENDPOINT_LED}{1 if enabled else 0}")  # type: ignore[attr-defined]
                    except Exception as std_err:
                        _LOGGER.debug("Standard LED command also failed: %s", std_err)
                        raise arylic_err from std_err  # Re-raise original error
            else:
                # Standard LinkPlay LED command
                await self._request(f"{API_ENDPOINT_LED}{1 if enabled else 0}")  # type: ignore[attr-defined]

        except Exception as err:
            # Log but don't fail - LED control is optional
            _LOGGER.debug("LED control not supported or failed for device: %s", err)

    async def set_led_brightness(self, brightness: int) -> None:
        """Set LED brightness (0–100) with device-specific commands.

        Args:
            brightness: Brightness level from 0 to 100.

        Raises:
            ValueError: If brightness is outside valid range.

        Note:
            This method handles vendor-specific LED commands (Arylic vs standard)
            and falls back gracefully if LED control is not supported.
        """
        if not 0 <= brightness <= 100:
            raise ValueError("Brightness must be between 0 and 100")

        try:
            # Get device info to determine LED command format
            device_info = await self.get_device_info_model()
            led_format = _get_led_command_format(device_info)

            if led_format == "arylic":
                # Arylic devices use MCU+PAS+RAKOIT:LEDBRIGHTNESS commands
                # Brightness: 0-100 percentage
                # Note: These commands are experimental based on user research
                try:
                    await self._request(f"{API_ENDPOINT_ARYLIC_LED_BRIGHTNESS}{brightness}")  # type: ignore[attr-defined]
                except Exception as arylic_err:
                    # Fallback: try standard commands in case Arylic supports them
                    _LOGGER.debug("Arylic LED brightness command failed, trying standard: %s", arylic_err)
                    try:
                        await self._request(f"{API_ENDPOINT_LED_BRIGHTNESS}{brightness}")  # type: ignore[attr-defined]
                    except Exception as std_err:
                        _LOGGER.debug("Standard LED brightness command also failed: %s", std_err)
                        raise arylic_err from std_err  # Re-raise original error
            else:
                # Standard LinkPlay brightness command
                await self._request(f"{API_ENDPOINT_LED_BRIGHTNESS}{brightness}")  # type: ignore[attr-defined]

        except Exception as err:
            # Log but don't fail - LED control is optional
            _LOGGER.debug("LED brightness control not supported or failed for device: %s", err)
