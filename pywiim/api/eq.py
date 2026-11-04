"""Equaliser (EQ) helpers for WiiM HTTP client.

This mixin handles preset selection, custom 10-band EQ upload, enable/disable,
and querying current EQ status and the list of presets.

It assumes the base client provides the `_request` coroutine. No state is stored –
all results come from the device each call.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from ..exceptions import WiiMResponseError
from .constants import (
    API_ENDPOINT_EQ_GET,
    API_ENDPOINT_EQ_LIST,
    API_ENDPOINT_EQ_OFF,
    API_ENDPOINT_EQ_ON,
    API_ENDPOINT_EQ_PRESET,
    EQ_PRESET_MAP,
)
from .peq import GEQ_BAND_NAMES, GraphicEQBand


class EQAPI:
    """Equaliser helpers (presets, on/off, custom bands).

    This mixin provides methods for managing the device's equalizer settings,
    including presets, custom 10-band EQ, and enable/disable functionality.
    """

    # ------------------------------------------------------------------
    # Preset handling
    # ------------------------------------------------------------------

    def _normalize_eq_preset_name(self, preset: str, available_presets: list[str] | None = None) -> str:
        """Normalize EQ preset name to match EQ_PRESET_MAP keys.

        Handles variations like:
        - "base reducer" -> "bassreducer"
        - "bass reducer" -> "bassreducer"
        - "Bass Reducer" -> "bassreducer"
        - "bass_reducer" -> "bassreducer"
        - "bass-reducer" -> "bassreducer"

        Args:
            preset: Preset name (may contain spaces, hyphens, underscores, or typos).

        Returns:
            Normalized preset name matching a key in EQ_PRESET_MAP, or an exact
            device-reported preset label when matched via ``available_presets``.

        Raises:
            ValueError: If preset name cannot be normalized to a valid preset.
        """
        preset = preset.strip()

        # Try direct lookup first (fast path for already-normalized names)
        if preset in EQ_PRESET_MAP:
            return preset

        # Create reverse lookup: display name -> key
        # Also create normalized variations map
        display_to_key: dict[str, str] = {}
        normalized_variations: dict[str, str] = {}

        for key, display_name in EQ_PRESET_MAP.items():
            # Map display name to key
            display_to_key[display_name.lower()] = key

            # Create normalized variations (lowercase, no spaces/hyphens/underscores)
            normalized = key.lower().replace(" ", "").replace("-", "").replace("_", "")
            normalized_variations[normalized] = key

            # Also normalize display name
            display_normalized = display_name.lower().replace(" ", "").replace("-", "").replace("_", "")
            normalized_variations[display_normalized] = key

        # Try display name lookup (case-insensitive)
        preset_lower = preset.lower().strip()
        if preset_lower in display_to_key:
            return display_to_key[preset_lower]

        # Normalize input: lowercase, remove spaces/hyphens/underscores
        normalized_input = preset_lower.replace(" ", "").replace("-", "").replace("_", "")

        # Handle common typos
        if normalized_input.startswith("base") and "reducer" in normalized_input:
            normalized_input = normalized_input.replace("base", "bass", 1)

        # Try normalized lookup
        if normalized_input in normalized_variations:
            return normalized_variations[normalized_input]

        # Try direct normalized match against keys
        for key in EQ_PRESET_MAP.keys():
            if normalized_input == key.lower().replace(" ", "").replace("-", "").replace("_", ""):
                return key

        # Try matching against device-reported presets if available. This supports
        # newer firmware exposing labels outside the fixed built-in map and
        # user-defined custom EQ presets.
        if available_presets:
            for available_preset in available_presets:
                if not available_preset or available_preset.lower() == "off":
                    continue
                available_normalized = available_preset.lower().replace(" ", "").replace("-", "").replace("_", "")
                if normalized_input == available_normalized:
                    return available_preset

        # If we get here, we couldn't normalize it
        raise ValueError(f"Invalid EQ preset: {preset}. Valid presets: {', '.join(sorted(EQ_PRESET_MAP.keys()))}")

    async def set_eq_preset(self, preset: str, available_presets: list[str] | None = None) -> None:
        """Apply a named EQ preset (e.g. "rock", "flat", "bass reducer").

        Args:
            preset: Preset name. Can be a key from EQ_PRESET_MAP (e.g., "bassreducer"),
                   a display name (e.g., "Bass Reducer"), a variation with spaces/hyphens
                   (e.g., "bass reducer", "bass-reducer", "base reducer"), or a
                   device-reported preset label when ``available_presets`` is supplied.
            available_presets: Optional device-reported preset labels to support
                   dynamic/custom presets not present in the fixed built-in map.

        Raises:
            ValueError: If preset name is invalid.
            WiiMError: If the request fails.
        """
        # Normalize preset name to match EQ_PRESET_MAP key or a device-reported label.
        normalized_preset = self._normalize_eq_preset_name(preset, available_presets=available_presets)
        api_value = EQ_PRESET_MAP.get(normalized_preset, normalized_preset)
        await self._request(f"{API_ENDPOINT_EQ_PRESET}{api_value}")  # type: ignore[attr-defined]

    async def get_eq_presets(self) -> list[str]:
        """Get list of available EQ presets from the device.

        Returns:
            List of preset names available on the device.

        Raises:
            WiiMError: If the request fails.
        """
        resp = await self._request(API_ENDPOINT_EQ_LIST)  # type: ignore[attr-defined]
        parsed = resp.parsed

        # Handle direct list response (most common)
        if isinstance(parsed, list):
            return [str(item) for item in parsed if item]

        # Handle dict response (some devices wrap the list)
        if isinstance(parsed, dict):
            if parsed.get("error") or str(parsed.get("status", "ok")).lower() in ("error", "failed"):
                raise WiiMResponseError("Invalid EQ preset list response", endpoint=API_ENDPOINT_EQ_LIST)
            for key in ["EQList", "eq_list", "list", "presets", "preset_list"]:
                if key in parsed and isinstance(parsed[key], list):
                    return [str(item) for item in parsed[key] if item]
        raise WiiMResponseError("Invalid EQ preset list response", endpoint=API_ENDPOINT_EQ_LIST)

    # ------------------------------------------------------------------
    # Custom 10-band upload
    # ------------------------------------------------------------------

    async def set_eq_custom(self, eq_values: Sequence[float]) -> None:
        """Apply and verify a 10-band graphic EQ curve in dB.

        Args:
            eq_values: Ten gains from 31 Hz to 16 kHz, each -12 to +12 dB.

        Raises:
            ValueError: If eq_values doesn't have exactly 10 bands.
            WiiMError: If the device cannot confirm Eq10HP support or the write.
        """
        if len(eq_values) != 10:
            raise ValueError("EQ must have exactly 10 bands")
        bands = [GraphicEQBand(name, value) for name, value in zip(GEQ_BAND_NAMES, eq_values, strict=True)]
        await self.set_graphic_eq_bands(bands)  # type: ignore[attr-defined]

    async def get_eq(self) -> dict[str, Any]:
        """Get current EQ band values.

        Returns:
            Dictionary containing current EQ band values.

        Raises:
            WiiMError: If the request fails.
        """
        result = await self._request(API_ENDPOINT_EQ_GET)  # type: ignore[attr-defined]
        return cast(dict[str, Any], result.parsed or {})

    # ------------------------------------------------------------------
    # Enable / disable
    # ------------------------------------------------------------------

    async def set_eq_enabled(self, enabled: bool) -> None:
        """Enable or disable the EQ.

        Args:
            enabled: True to enable EQ, False to disable.

        Raises:
            WiiMError: If the request fails.
        """
        await self._request(API_ENDPOINT_EQ_ON if enabled else API_ENDPOINT_EQ_OFF)  # type: ignore[attr-defined]

    async def get_eq_status(self) -> bool | None:
        """Return the reported EQ enabled state, or None when unavailable.

        Uses EQGetBand where supported. EQGetStat fails on some firmware
        (e.g. WiiM Pro Linkplay 4.8), so we do not use it as a fallback.
        """
        try:
            response = await self._request(API_ENDPOINT_EQ_GET)  # type: ignore[attr-defined]
            if isinstance(response.parsed, dict):
                if response.parsed.get("error") or str(response.parsed.get("status", "ok")).lower() in (
                    "error",
                    "failed",
                ):
                    return None
                status = str(response.parsed.get("EQStat", "")).strip().lower()
                if status in ("on", "off"):
                    return status == "on"
            return None
        except Exception:  # noqa: BLE001
            return None
