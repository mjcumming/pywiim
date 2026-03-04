"""Miscellaneous device control helpers for WiiM HTTP client.

This mixin handles various device controls including button controls and
other miscellaneous operations. These endpoints are unofficial and may not
be available on all firmware versions.

Note: LED controls are already implemented in the DeviceAPI mixin with
device-specific command detection.

It assumes the base client provides the `_request` coroutine. No state is stored –
all results come from the device each call.
"""

from __future__ import annotations

from typing import Any

from ..exceptions import WiiMError
from .constants import (
    API_ENDPOINT_SET_BUTTONS,
    API_ENDPOINT_SET_LED,
    API_ENDPOINT_TRIGGER_OUT_SET,
    API_ENDPOINT_TRIGGER_OUT_STATUS,
)


class MiscAPI:
    """Miscellaneous device control helpers (buttons, etc.).

    This mixin provides methods for controlling miscellaneous device features
    such as touch buttons and alternative LED control methods.
    """

    # ------------------------------------------------------------------
    # Touch button controls
    # ------------------------------------------------------------------

    async def set_buttons_enabled(self, enabled: bool) -> None:
        """Enable or disable touch button controls on the device.

        Args:
            enabled: True to enable touch buttons, False to disable

        Raises:
            WiiMRequestError: If the request fails

        Note:
            This controls the physical touch buttons on the device itself,
            not Home Assistant button entities.
        """
        value = "1" if enabled else "0"
        await self._request(f"{API_ENDPOINT_SET_BUTTONS}{value}")  # type: ignore[attr-defined]

    async def enable_touch_buttons(self) -> None:
        """Enable touch button controls on the device.

        Raises:
            WiiMRequestError: If the request fails
        """
        await self.set_buttons_enabled(True)

    async def disable_touch_buttons(self) -> None:
        """Disable touch button controls on the device.

        Raises:
            WiiMRequestError: If the request fails
        """
        await self.set_buttons_enabled(False)

    # ------------------------------------------------------------------
    # 12V trigger control (WiiM Ultra / Pro / Pro Plus)
    # ------------------------------------------------------------------

    async def get_trigger_out_status(self) -> bool | None:
        """Get 12V trigger output status.

        Returns:
            True if trigger is on, False if off, or None if not supported.
            Devices without 12V trigger hardware return None or raise.
        """
        try:
            result = await self._request(API_ENDPOINT_TRIGGER_OUT_STATUS)  # type: ignore[attr-defined]
            if isinstance(result.parsed, dict) and "status" in result.parsed:
                return int(result.parsed["status"]) == 1
            return None
        except WiiMError:
            return None

    async def set_trigger_out(self, on: bool) -> None:
        """Set 12V trigger output on or off.

        Args:
            on: True to turn trigger on, False to turn off.

        Raises:
            WiiMError: If the request fails (e.g. device does not support 12V trigger).
        """
        value = 1 if on else 0
        await self._request(f"{API_ENDPOINT_TRIGGER_OUT_SET}{value}")  # type: ignore[attr-defined]

    async def set_trigger_out_on(self) -> None:
        """Turn 12V trigger output on.

        Raises:
            WiiMError: If the request fails.
        """
        await self.set_trigger_out(True)

    async def set_trigger_out_off(self) -> None:
        """Turn 12V trigger output off.

        Raises:
            WiiMError: If the request fails.
        """
        await self.set_trigger_out(False)

    # ------------------------------------------------------------------
    # Alternative LED control (if needed)
    # ------------------------------------------------------------------

    async def set_led_switch(self, enabled: bool) -> None:
        """Alternative LED control method using LED_SWITCH_SET command.

        This is an alternative to the device-specific LED commands already
        implemented in the DeviceAPI mixin. Use only if the standard LED
        commands don't work on your device.

        Args:
            enabled: True to enable LED, False to disable

        Raises:
            WiiMRequestError: If the request fails
        """
        value = "1" if enabled else "0"
        await self._request(f"{API_ENDPOINT_SET_LED}{value}")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Status and information helpers
    # ------------------------------------------------------------------

    async def get_device_capabilities(self) -> dict[str, Any]:
        """Get comprehensive device capabilities including unofficial endpoints.

        Returns:
            Dict containing capability flags for various features

        Note:
            This method tests each capability by attempting to use it,
            which may produce log warnings for unsupported features.
        """
        capabilities = {
            "touch_buttons": False,
            "alternative_led": False,
            "network_config": False,
            "bluetooth_scanning": False,
            "audio_settings": False,
            "lms_integration": False,
        }

        # Test each capability by attempting to use it
        # Note: This is a best-effort check and may produce log warnings

        # Check touch buttons (this one should work if endpoint exists)
        try:
            await self.set_buttons_enabled(True)
            capabilities["touch_buttons"] = True
        except WiiMError:
            pass

        # Check alternative LED control
        try:
            await self.set_led_switch(True)
            capabilities["alternative_led"] = True
        except WiiMError:
            pass

        return capabilities

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    async def are_touch_buttons_enabled(self) -> bool:
        """Check if touch buttons are currently enabled.

        Returns:
            True if buttons are enabled, False otherwise.
            Note: This is a guess since the API doesn't provide readback.
            Always returns True unless the endpoint fails completely.
        """
        try:
            # Try to enable buttons - if it succeeds, assume they're supported
            await self.enable_touch_buttons()
            return True
        except WiiMError:
            return False

    async def test_misc_functionality(self) -> dict[str, bool]:
        """Test all miscellaneous functionality and report what's available.

        Returns:
            Dict with availability status for each feature
        """
        results = {}

        # Test touch button control
        try:
            await self.set_buttons_enabled(True)
            results["touch_buttons"] = True
        except WiiMError:
            results["touch_buttons"] = False

        # Test alternative LED control
        try:
            await self.set_led_switch(True)
            results["alternative_led"] = True
        except WiiMError:
            results["alternative_led"] = False

        return results
