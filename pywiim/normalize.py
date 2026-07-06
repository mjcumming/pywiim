"""Device information normalization helpers.

This module provides pure functions for normalizing and enriching device
information, with no network or framework dependencies.
"""

from __future__ import annotations

from typing import Any

from .models import DeviceInfo

__all__ = [
    "HARDWARE_SOURCE_KEYS",
    "canonical_source_key",
    "normalize_device_info",
    "normalize_vendor",
    "source_rename_reverse",
]

# Canonical ids that represent selectable physical inputs (as opposed to
# streaming services / virtual sources). Shared by source enumeration, the
# catalog, and the WiiM input-metadata overlay.
HARDWARE_SOURCE_KEYS: set[str] = {
    "network",
    "wifi",
    "bluetooth",
    "line_in",
    "line_in_2",
    "aux",
    "optical",
    "coaxial",
    "usb",
    "hdmi",
    "phono",
    "rca",
}


def source_rename_reverse(rename_map: dict[str, str] | None) -> dict[str, str]:
    """Build a ``{lowercased label: canonical id}`` lookup from ``getModeRename``.

    Firmware can point several mode keys at the same label (e.g. both ``optical``
    and ``SPDIF-In`` renamed to "Optical Mike"). On such collisions we keep the
    canonical hardware id (``optical``) so the label resolves back to a real,
    selectable input rather than an unknown alias.
    """
    reverse: dict[str, str] = {}
    for cid, label in (rename_map or {}).items():
        key = str(label).strip().lower()
        if not key:
            continue
        if key not in reverse or cid in HARDWARE_SOURCE_KEYS:
            reverse[key] = cid
    return reverse


def canonical_source_key(source_name: str) -> str:
    """Normalize a source display name or device mode string to a canonical key.

    Accepts UI display names ("Line In"), device switchmode strings ("line-in",
    "HDMI"), and discovered-API mode strings (e.g. from ``getAudioInputEnable``)
    and maps them to the stable ids used by ``Player.source_catalog`` (e.g.
    ``line_in``, ``hdmi``). This is the single source of truth for source-id
    normalization; both source enumeration and the WiiM input-capability overlay
    resolve through it so their ids always agree.
    """
    source_lower = source_name.strip().lower()
    if not source_lower:
        return ""

    # Direct mappings for UI display names
    direct_map = {
        "network": "network",
        "wifi": "network",
        "wi-fi": "network",
        "ethernet": "network",
        "line in": "line_in",
        "line in 2": "line_in_2",
        "aux in": "aux",
        "optical in": "optical",
        "coaxial": "coaxial",
        "usb": "usb",
        "hdmi": "hdmi",
        "phono": "phono",
        "rca": "rca",
        "airplay": "airplay",
        "spotify": "spotify",
        "amazon music": "amazon",
        "amazon": "amazon",
        "tidal": "tidal",
        "qobuz": "qobuz",
        "deezer": "deezer",
        "pandora": "pandora",
        "tunein": "tunein",
        "iheartradio": "iheartradio",
        "dlna": "dlna",
        "bluetooth": "bluetooth",
    }
    if source_lower in direct_map:
        return direct_map[source_lower]

    # Fallback: alphanumeric simplification for resilient matching
    simple = "".join(ch for ch in source_lower if ch.isalnum())
    simple_map = {
        "linein": "line_in",
        "linein2": "line_in_2",
        "auxin": "aux",
        "opticalin": "optical",
        "coaxialin": "coaxial",
        "amazonmusic": "amazon",
        "iheartradio": "iheartradio",
        "airplay": "airplay",
    }
    if simple in simple_map:
        return simple_map[simple]

    return source_lower.replace(" ", "_").replace("-", "_")


def normalize_device_info(device_info: DeviceInfo) -> dict[str, Any]:
    """Normalize and enrich device information with derived fields.

    This function takes a DeviceInfo model and returns a dictionary with
    additional normalized and derived fields. The returned dictionary can
    be merged with the original model's dict representation.

    Args:
        device_info: DeviceInfo model instance

    Returns:
        Dictionary with normalized and derived fields including:
        - firmware: Firmware version
        - firmware_date: Release date
        - hardware: Hardware revision
        - project: Device model/project name
        - mcu_version: MCU firmware version
        - dsp_version: DSP firmware version
        - preset_slots: Number of preset slots (from preset_key)
        - wmrm_version: WiiM multiroom protocol version
        - update_available: Whether firmware update is available
        - latest_version: Latest available firmware version

    Example:
        ```python
        device_info = await client.get_device_info_model()
        normalized = normalize_device_info(device_info)

        # Merge with original dict
        full_info = {**device_info.model_dump(), **normalized}
        ```
    """
    payload: dict[str, Any] = {}

    # Core firmware / build information
    if device_info.firmware:
        payload["firmware"] = device_info.firmware

    if device_info.release_date:
        payload["firmware_date"] = device_info.release_date

    # Hardware & project identifiers
    if device_info.hardware:
        payload["hardware"] = device_info.hardware

    if device_info.model:
        payload["project"] = device_info.model

    # MCU / DSP versions
    if device_info.mcu_ver is not None:
        payload["mcu_version"] = str(device_info.mcu_ver)

    if device_info.dsp_ver is not None:
        payload["dsp_version"] = str(device_info.dsp_ver)

    # Preset slots – convert preset_key to integer count when valid
    if device_info.preset_key is not None:
        try:
            payload["preset_slots"] = int(device_info.preset_key)
        except (TypeError, ValueError):
            pass  # Leave unset if conversion fails

    # WiiM multi-room protocol version
    if device_info.wmrm_version:
        payload["wmrm_version"] = device_info.wmrm_version

    # Firmware update availability
    if device_info.version_update is not None:
        update_flag = str(device_info.version_update)
        payload["update_available"] = update_flag == "1"

        if device_info.latest_version:
            payload["latest_version"] = device_info.latest_version

    return payload


def normalize_vendor(vendor: str | None) -> str:
    """Normalize vendor name to standard format.

    Args:
        vendor: Raw vendor string (may be None, mixed case, or variant)

    Returns:
        Normalized vendor string: "wiim", "arylic", "audio_pro", or "linkplay_generic"
    """
    if not vendor:
        return "linkplay_generic"

    vendor_lower = vendor.lower().strip()

    # Normalize common variations
    vendor_map = {
        "wiim": "wiim",
        "wiimu": "wiim",
        "wii m": "wiim",
        "wii-m": "wiim",
        "arylic": "arylic",
        "up2stream": "arylic",
        "audio pro": "audio_pro",
        "audio_pro": "audio_pro",
        "addon": "audio_pro",
        "linkplay": "linkplay_generic",
        "linkplay_generic": "linkplay_generic",
        "generic": "linkplay_generic",
        "unknown": "linkplay_generic",
    }

    # Direct match
    if vendor_lower in vendor_map:
        return vendor_map[vendor_lower]

    # Partial match
    for key, normalized in vendor_map.items():
        if key in vendor_lower or vendor_lower in key:
            return normalized

    return "linkplay_generic"
