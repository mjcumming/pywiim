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

import json
import logging
from typing import Any
from urllib.parse import quote

from pydantic import ValidationError

from ..exceptions import WiiMError
from ..models import AcousticCapability, AudioInputCapability, AudioInputEnable, RoutineList
from .constants import (
    API_ENDPOINT_DISPLAY_CONFIG,
    API_ENDPOINT_GET_ACOUSTIC_CAPABILITY,
    API_ENDPOINT_GET_ALL_ROUTINES,
    API_ENDPOINT_GET_AUDIO_INPUT_CAPABILITY,
    API_ENDPOINT_GET_AUDIO_INPUT_ENABLE,
    API_ENDPOINT_GET_LED_MCU,
    API_ENDPOINT_GET_LED_SWITCH,
    API_ENDPOINT_GET_MODE_RENAME,
    API_ENDPOINT_SET_BUTTONS,
    API_ENDPOINT_SET_LED,
    API_ENDPOINT_TRIGGER_OUT_SET,
    API_ENDPOINT_TRIGGER_OUT_STATUS,
    DISPLAY_DEFAULT_BRIGHTNESS,
)

_LOGGER = logging.getLogger(__name__)


def _is_unsupported_discovered_payload(payload: dict[str, Any]) -> bool:
    """Return True for firmware error payloads from optional discovered APIs."""
    raw = str(payload.get("raw", "")).strip().lower()
    error = str(payload.get("error", "")).strip().lower()
    state = payload.get("state")

    if "unknown command" in raw:
        return True
    if error in {"unsupported_command", "unknown command", "fail", "failed"}:
        return True
    return state == -1 and bool(error)


class MiscAPI:
    """Miscellaneous device control helpers (buttons, etc.).

    This mixin provides methods for controlling miscellaneous device features
    such as touch buttons and alternative LED control methods.
    """

    # ------------------------------------------------------------------
    # WiiM read-only discovery helpers
    # ------------------------------------------------------------------

    async def get_audio_input_enable(self) -> AudioInputEnable | None:
        """Return WiiM input enablement metadata, if available.

        This is a read-only WiiM endpoint discovered from app traffic. It is
        expected to be absent on many LinkPlay/OEM devices; unsupported responses
        return ``None``.
        """
        try:
            result = await self._request(API_ENDPOINT_GET_AUDIO_INPUT_ENABLE)  # type: ignore[attr-defined]
            if isinstance(result.parsed, dict) and not _is_unsupported_discovered_payload(result.parsed):
                return AudioInputEnable.model_validate(result.parsed)
        except (ValidationError, WiiMError):
            return None
        return None

    async def get_audio_input_capability(self) -> AudioInputCapability | None:
        """Return WiiM input capability metadata, if available.

        The firmware command is named ``getAudioInputCapbility`` (misspelled).
        It returns available input modes without enable/disable state. This is
        read-only and expected to be absent on many non-WiiM LinkPlay devices.
        """
        try:
            result = await self._request(API_ENDPOINT_GET_AUDIO_INPUT_CAPABILITY)  # type: ignore[attr-defined]
            if isinstance(result.parsed, dict) and not _is_unsupported_discovered_payload(result.parsed):
                return AudioInputCapability.model_validate(result.parsed)
        except (ValidationError, WiiMError):
            return None
        return None

    async def get_mode_rename(self) -> dict[str, str] | None:
        """Return user-renamed source labels from WiiM, if configured.

        WiiM returns a dynamic object such as ``{"optical": "TV"}``. When no
        source has been renamed, firmware may return plain ``Failed``; that maps
        to ``None``.
        """
        try:
            result = await self._request(API_ENDPOINT_GET_MODE_RENAME)  # type: ignore[attr-defined]
            if isinstance(result.parsed, dict) and not _is_unsupported_discovered_payload(result.parsed):
                return {str(key): str(value) for key, value in result.parsed.items() if value is not None}
        except (ValidationError, WiiMError):
            return None
        return None

    async def get_acoustic_capability(self) -> AcousticCapability | None:
        """Return WiiM acoustic capability metadata, if available."""
        try:
            result = await self._request(API_ENDPOINT_GET_ACOUSTIC_CAPABILITY)  # type: ignore[attr-defined]
            if isinstance(result.parsed, dict) and not _is_unsupported_discovered_payload(result.parsed):
                return AcousticCapability.model_validate(result.parsed)
        except (ValidationError, WiiMError):
            return None
        return None

    async def get_all_routines(self) -> RoutineList | None:
        """Return WiiM routines, if available.

        Routines are device-side action sequences, not playback presets. This
        method is read-only and does not imply pywiim can execute routines.
        """
        try:
            result = await self._request(API_ENDPOINT_GET_ALL_ROUTINES)  # type: ignore[attr-defined]
            if isinstance(result.parsed, dict) and not _is_unsupported_discovered_payload(result.parsed):
                return RoutineList.model_validate(result.parsed)
        except (ValidationError, WiiMError):
            return None
        return None

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
    # LED Indicator (ADR 005: on/off; read assumes on if unavailable)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_led_switch_get_response(raw: str | None, parsed: Any) -> bool | None:
        """Parse LED_SWITCH_GET (plain 0/1) or similar short text responses."""
        text = (raw or "").strip()
        if not text and parsed is not None and not isinstance(parsed, dict):
            text = str(parsed).strip()
        if text in ("0", "1"):
            return text == "1"
        return None

    async def get_led_indicator(self) -> bool:
        """Read LED indicator state from the device.

        Tries LED_SWITCH_GET (read-only on WiiM), getStatusEx led fields, and
        for Arylic getMCUASCIICmd:LED. If read fails or no API exists, returns True
        (assume on) and logs a warning. No persistent state between sessions.

        Returns:
            True if LED is on or assumed on, False if read as off.
        """
        caps = getattr(self, "_capabilities", {}) or {}
        vendor = caps.get("vendor", "")

        # 1. LED_SWITCH_GET — read-only; does not mutate hardware (WiiM Pro/Ultra class)
        if caps.get("supports_led_switch") or caps.get("is_wiim_device"):
            try:
                result = await self._request(API_ENDPOINT_GET_LED_SWITCH)  # type: ignore[attr-defined]
                state = self._parse_led_switch_get_response(
                    getattr(result, "raw", None),
                    getattr(result, "parsed", None),
                )
                if state is not None:
                    return state
            except WiiMError:
                pass

        # 2. Try getStatusEx / get_device_info for led/LED/led_switch
        try:
            info = await self.get_device_info()  # type: ignore[attr-defined]
            if isinstance(info, dict):
                for key in ("led", "LED", "led_switch", "Led"):
                    if key in info:
                        val = info[key]
                        if val in (0, "0", False):
                            return False
                        if val in (1, "1", True):
                            return True
                        if isinstance(val, str) and val.lower() in ("on", "1", "true"):
                            return True
                        if isinstance(val, str) and val.lower() in ("off", "0", "false"):
                            return False
        except WiiMError:
            pass

        # 3. Arylic: try getMCUASCIICmd:LED (e.g. response "LED:1" or "LED:0")
        if vendor == "arylic":
            try:
                result = await self._request(API_ENDPOINT_GET_LED_MCU)  # type: ignore[attr-defined]
                raw = getattr(result, "raw", None) or getattr(result, "parsed", None)
                if isinstance(raw, str):
                    parts = raw.strip().split(":")
                    last = parts[-1].strip() if parts else ""
                    if last == "0":
                        return False
                    if last == "1":
                        return True
            except WiiMError:
                pass

        _LOGGER.warning("LED indicator read not available for device (no API or read failed); assuming on")
        return True

    async def set_led_switch(self, enabled: bool) -> None:
        """Set LED indicator on/off using LED_SWITCH_SET (ADR 005).

        For Arylic devices, failures are ignored (try-and-ignore). For others,
        raises on request failure.

        Args:
            enabled: True to enable LED, False to disable.

        Raises:
            WiiMRequestError: If the request fails (non-Arylic only).
        """
        value = "1" if enabled else "0"
        caps = getattr(self, "_capabilities", {}) or {}
        if caps.get("vendor") == "arylic":
            try:
                await self._request(f"{API_ENDPOINT_SET_LED}{value}")  # type: ignore[attr-defined]
            except WiiMError as err:
                _LOGGER.debug("Arylic LED_SWITCH_SET failed (try-and-ignore): %s", err)
            return
        await self._request(f"{API_ENDPOINT_SET_LED}{value}")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Display / LCD (WiiM Ultra)
    # ------------------------------------------------------------------

    async def set_display_config(
        self,
        *,
        auto_sense_enable: int = 0,
        default_bright: int = DISPLAY_DEFAULT_BRIGHTNESS,
        disable: int = 0,
    ) -> None:
        """Set display/LCD config (WiiM Ultra only).

        Controls the LCD via ``setLightOperationBrightConfig`` (one JSON payload).
        This is **not** the status LED: use ``set_led_switch`` / ``set_led`` for that.

        Args:
            auto_sense_enable: 1 to enable auto brightness, 0 to disable.
            default_bright: Brightness level (WiiM Ultra uses a 1–100 style scale;
                1 is minimum — see ``DISPLAY_BRIGHTNESS_*`` in ``constants``).
            disable: 0 = screen on, 1 = screen off.

        Raises:
            WiiMRequestError: If the request fails (e.g. not supported on this device).
        """
        payload = {
            "auto_sense_enable": auto_sense_enable,
            "default_bright": default_bright,
            "disable": disable,
        }
        encoded = quote(json.dumps(payload, separators=(",", ":")), safe="")
        await self._request(f"{API_ENDPOINT_DISPLAY_CONFIG}{encoded}")  # type: ignore[attr-defined]

    async def set_display_enabled(
        self,
        enabled: bool,
        *,
        default_bright: int | None = None,
        auto_sense_enable: int | None = None,
    ) -> None:
        """Turn the display/LCD on or off (WiiM Ultra only).

        The device API always sends ``default_bright`` and ``auto_sense_enable``
        in the same command as ``disable``; this wrapper uses
        :data:`DISPLAY_DEFAULT_BRIGHTNESS` when turning **on** so the screen is
        not left at level 1 (minimum).

        Adaptive brightness (``auto_sense_enable``): when turning the screen on
        this defaults to **1** (adaptive brightness enabled). Historically it was
        forced to ``0``, which on at least some WiiM Ultra / Amp Ultra firmware
        left the panel dark even though the device reported the display as "on"
        (``disable=0``) — users had to toggle adaptive brightness in the WiiM app
        to relight it (mjcumming/wiim#250). Pass ``auto_sense_enable=0`` to keep
        adaptive brightness off (fixed brightness).

        Args:
            enabled: True to turn screen on, False to turn off.
            default_bright: When turning on, optional brightness (1–100). If omitted,
                uses ``DISPLAY_DEFAULT_BRIGHTNESS``. Ignored when ``enabled`` is False.
            auto_sense_enable: 1 to enable adaptive brightness, 0 to disable. If
                omitted, defaults to 1 when turning on and 0 when turning off.
        """
        if enabled:
            bright = default_bright if default_bright is not None else DISPLAY_DEFAULT_BRIGHTNESS
            sense = auto_sense_enable if auto_sense_enable is not None else 1
            await self.set_display_config(disable=0, default_bright=bright, auto_sense_enable=sense)
        else:
            sense = auto_sense_enable if auto_sense_enable is not None else 0
            await self.set_display_config(disable=1, auto_sense_enable=sense)

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
