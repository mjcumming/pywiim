"""Preset helpers – manage and play stored preset slots.

Device-specific variations:
- WiiM devices: Typically support 6-20 presets (varies by model/firmware)
- Audio Pro MkII: Does NOT support presets (getPresetInfo returns 404)
- Legacy devices: May support 6 presets (default) or more
- Preset count is determined by device_info.preset_key field
"""

from __future__ import annotations

import logging
from typing import Any

from ..exceptions import WiiMError, WiiMRequestError
from .constants import API_ENDPOINT_PRESET, API_ENDPOINT_PRESET_INFO

_LOGGER = logging.getLogger(__name__)

# Default preset slots for devices that don't expose preset_key
DEFAULT_PRESET_SLOTS = 6

# Maximum preset slots (some devices support up to 20)
MAX_PRESET_SLOTS = 20


class PresetAPI:
    """List and play device presets.

    This mixin provides methods for managing device presets (radio stations, playlists, etc.).
    Presets are stored on the device and can be played by number.

    Device-specific behavior:
    - Preset count varies by device (6-20 slots, determined by preset_key in device info)
    - Some devices (Audio Pro MkII) don't support presets at all
    - Older firmware may not expose preset_key, defaulting to 6 slots
    """

    async def get_presets(self) -> list[dict[str, Any]]:
        """Return list of preset entries from getPresetInfo.

        Each entry looks like::
            {"number": 1, "name": "Radio Paradise", "url": "...", "picurl": "..."}

        Returns:
            List of preset dictionaries with number, name, url, and picurl fields.
            Returns empty list if presets are not supported.

        Raises:
            WiiMError: If the request fails (may indicate presets not supported).
        """
        # Check if device supports presets (capability detection)
        capabilities = getattr(self, "capabilities", {})
        if capabilities.get("supports_presets") is False:
            _LOGGER.debug("Presets not supported on this device (capability detection)")
            return []

        try:
            payload = await self._request(API_ENDPOINT_PRESET_INFO)  # type: ignore[attr-defined]
            parsed = payload.parsed
            if isinstance(parsed, dict):
                preset_list = parsed.get("preset_list", []) or []
                # Normalize preset data - convert "unknow" to None for URL fields
                normalized_presets = []
                for preset in preset_list:
                    normalized_preset = dict(preset)  # Copy to avoid mutating original
                    # Normalize URL fields - "unknow" is a common device typo for "unknown"
                    for url_field in ["url", "picurl", "pic_url"]:
                        if url_field in normalized_preset:
                            url_value = normalized_preset[url_field]
                            if isinstance(url_value, str):
                                url_lower = url_value.lower().strip()
                                # Normalize common invalid values
                                if url_lower in ("unknow", "unknown", "none", ""):
                                    normalized_preset[url_field] = None
                    normalized_presets.append(normalized_preset)
                _LOGGER.debug("Retrieved %d presets from device", len(normalized_presets))
                return normalized_presets
            return []
        except WiiMRequestError as err:
            # Check if this is a 404 (presets not supported)
            error_str = str(err).lower()
            if "404" in error_str or "not found" in error_str:
                _LOGGER.debug("Presets not supported on this device (404 response)")
                # Mark as unsupported in capabilities for future calls
                if hasattr(self, "_capabilities"):
                    self._capabilities["supports_presets"] = False
                return []
            # Re-raise other errors
            raise
        except Exception:  # noqa: BLE001
            # Let higher layer treat as capability unsupported
            raise

    async def get_max_preset_slots(self) -> int:
        """Get the maximum number of preset slots supported by this device.

        Returns:
            Maximum preset slot number (typically 6-20, determined from API's preset_key field).
            Returns 6 if preset_key is not available from the API (assumes 6 for older firmware).
            Returns 0 if presets are not supported.
        """
        # Check if device supports presets
        capabilities = getattr(self, "_capabilities", {})
        if capabilities.get("supports_presets") is False:
            return 0

        try:
            # Get device info to check preset_key (this comes from the API)
            device_info = await self.get_device_info_model()  # type: ignore[attr-defined]
            if device_info.preset_key is not None:
                try:
                    max_slots = int(device_info.preset_key)
                    _LOGGER.debug("Device reports %d preset slots from API (preset_key)", max_slots)
                    return max_slots
                except (TypeError, ValueError):
                    _LOGGER.debug("Invalid preset_key value: %s", device_info.preset_key)
                    pass

            # If preset_key is not available from the API, assume 6 (default for older firmware)
            _LOGGER.debug("preset_key not available from API, assuming default %d slots", DEFAULT_PRESET_SLOTS)
            return DEFAULT_PRESET_SLOTS

        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Could not determine preset slots: %s", err)
            # If presets are not supported, return 0
            if isinstance(err, WiiMRequestError):
                error_str = str(err).lower()
                if "404" in error_str or "not found" in error_str:
                    return 0
            # Otherwise, assume default (cannot determine from API)
            _LOGGER.debug("Cannot determine preset slots from API, assuming default %d", DEFAULT_PRESET_SLOTS)
            return DEFAULT_PRESET_SLOTS

    async def play_preset(self, preset: int, index: int | None = None) -> None:
        """Initiate playback of preset slot *preset* (1-based).

        Optionally start at a specific track index within the preset's playlist.
        When index is omitted, the device resumes from the last playback position.

        Args:
            preset: Preset number (1-based, must be within device's supported range).
            index: Optional 1-based track index to start from (e.g. 1 = from beginning).
                When None, sends MCUKeyShortClick:preset (resume). When set, sends
                MCUKeyShortClick:preset:index. Not all devices support the index parameter.

        Raises:
            ValueError: If preset number or index is outside valid range.
            WiiMError: If the request fails or presets are not supported.
        """
        if preset < 1:
            raise ValueError("Preset number must be 1 or higher")
        if index is not None and index < 1:
            raise ValueError("Index must be 1 or higher when provided")

        # Check if device supports presets
        capabilities = getattr(self, "_capabilities", {})
        if capabilities.get("supports_presets") is False:
            raise WiiMError("Presets are not supported on this device")

        # Validate against maximum preset slots
        max_slots = await self.get_max_preset_slots()
        if max_slots == 0:
            raise WiiMError("Presets are not supported on this device")
        if preset > max_slots:
            raise ValueError(f"Preset number {preset} exceeds maximum supported slots ({max_slots}) for this device")

        if index is not None:
            cmd = f"{API_ENDPOINT_PRESET}{preset}:{index}"
            _LOGGER.debug("Playing preset %d at index %d (max slots: %d)", preset, index, max_slots)
        else:
            cmd = f"{API_ENDPOINT_PRESET}{preset}"
            _LOGGER.debug("Playing preset %d (max slots: %d)", preset, max_slots)
        await self._request(cmd)  # type: ignore[attr-defined]
