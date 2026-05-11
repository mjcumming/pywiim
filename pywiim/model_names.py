"""Helpers for LinkPlay/WiiM raw model identifiers."""

from __future__ import annotations

import re

__all__ = ["is_known_wiim_model", "is_wiim_ultra", "is_wiim_12v_trigger_model", "to_friendly_model_name"]

# Raw `project` aliases seen on WiiM firmware variants.
# Keep this list conservative and add entries when confirmed by real devices.
_WIIM_MODEL_ALIASES: frozenset[str] = frozenset(
    {
        "wiim_mini",
        "wiim_pro",
        "wiim_pro_plus",
        "wiim_amp",
        "wiim_amp_pro",
        "wiim_ultra",
        "wiim_pro_with_gc4a",
        "wiim_amp_4layer",
        "muzo_mini",
    }
)

_FRIENDLY_MODEL_MAP: dict[str, str] = {
    "muzo_mini": "WiiM Mini",
    "wiim_mini": "WiiM Mini",
    "wiim_pro": "WiiM Pro",
    "wiim_pro_plus": "WiiM Pro Plus",
    "wiim_pro_with_gc4a": "WiiM Pro",
    "wiim_amp": "WiiM Amp",
    "wiim_amp_4layer": "WiiM Amp",
    "wiim_amp_pro": "WiiM Amp Pro",
    "wiim_ultra": "WiiM Ultra",
    "up2stream": "Arylic Up2Stream",
    "s10+": "Arylic S10+",
    "s10_plus": "Arylic S10+",
    "addon_c10": "Audio Pro Addon C10",
    "a10": "Audio Pro A10",
    "a15": "Audio Pro A15",
    "a28": "Audio Pro A28",
    "c10": "Audio Pro C10",
}


def _normalize_model_key(model: str | None) -> str:
    """Normalize raw model string for matching."""
    if not model:
        return ""
    key = model.strip().lower()
    key = re.sub(r"[\s\-]+", "_", key)
    key = re.sub(r"_+", "_", key)
    return key


def is_known_wiim_model(model: str | None) -> bool:
    """Return True if model string matches known WiiM raw identifiers."""
    key = _normalize_model_key(model)
    if not key:
        return False
    return key in _WIIM_MODEL_ALIASES or key.startswith("wiim_") or key == "wiimu"


def is_wiim_ultra(model: str | None) -> bool:
    """Return True if model is WiiM Ultra (has LCD/display config API)."""
    key = _normalize_model_key(model)
    if not key:
        return False
    return key == "wiim_ultra" or (key.startswith("wiim_") and "ultra" in key)


# Models known to ship a 12V trigger output (hardware). Do not infer from HTTP at connect:
# some stacks answer getTriggeroutStatus or accept setTriggeroutStatus without real hardware.
_WIIM_12V_TRIGGER_EXACT: frozenset[str] = frozenset(
    {
        "wiim_ultra",
        "wiim_pro",
        "wiim_pro_plus",
        "wiim_pro_with_gc4a",
    }
)


def is_wiim_12v_trigger_model(model: str | None) -> bool:
    """Return True if this WiiM model is expected to have 12V trigger hardware.

    Ultra, Pro, and Pro Plus lines ship the jack. We avoid runtime probing so we
    never toggle trigger output during capability detection or verification.
    """
    key = _normalize_model_key(model)
    if not key:
        return False
    if key in _WIIM_12V_TRIGGER_EXACT:
        return True
    if key.startswith("wiim_") and "ultra" in key:
        return True
    if key.startswith("wiim_") and "pro_plus" in key:
        return True
    return False


def to_friendly_model_name(model: str | None) -> str | None:
    """Convert raw project model to branding-friendly name when known."""
    key = _normalize_model_key(model)
    if not key:
        return None

    friendly = _FRIENDLY_MODEL_MAP.get(key)
    if friendly:
        return friendly

    # Heuristic fallback for unseen WiiM raw project variants.
    if key.startswith("wiim_"):
        if "pro_plus" in key:
            return "WiiM Pro Plus"
        if "amp_pro" in key:
            return "WiiM Amp Pro"
        if "ultra" in key:
            return "WiiM Ultra"
        if "amp" in key:
            return "WiiM Amp"
        if "mini" in key:
            return "WiiM Mini"
        if "pro" in key:
            return "WiiM Pro"

    # Known Arylic model families used in vendor detection.
    if "up2stream" in key:
        return "Arylic Up2Stream"
    if "s10+" in key or "s10_plus" in key or "s10plus" in key:
        return "Arylic S10+"
    if "arylic" in key:
        return "Arylic"

    # Known Audio Pro model families used in vendor detection.
    if "addon" in key and "c10" in key:
        return "Audio Pro Addon C10"
    if key in {"a10", "a15", "a28", "c10"}:
        return f"Audio Pro {key.upper()}"
    if "audio_pro" in key or "audio pro" in key:
        return "Audio Pro"

    return model
