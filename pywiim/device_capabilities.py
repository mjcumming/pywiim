"""Device-specific capability definitions for WiiM/LinkPlay devices.

This module provides a database of known physical inputs for different device models.
Used to override/correct plm_support bitmask when firmware reports incorrect data.

The plm_support bitmask is poorly documented and varies by device/firmware:
- Some devices report bits for non-existent inputs (e.g., WiiM Pro reports USB)
- Newer devices have inputs not covered by documented bits (e.g., phono, HDMI)
- Firmware updates may change bit meanings or add new bits
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass
class DeviceInputs:
    """Physical inputs available on a specific device model.

    plm_support bitmask is unreliable across all vendors (WiiM, Arylic, LinkPlay).
    While documented by Arylic, it's often incomplete or incorrect even for Arylic devices.
    This database provides authoritative input lists based on actual device hardware.
    """

    # Physical audio inputs that can be selected as sources
    inputs: list[str]

    # Bits in plm_support that should be ignored (incorrectly reported)
    ignore_plm_bits: list[int] | None = None

    # Notes about this device's capabilities
    notes: str | None = None


# Device capability database
# Maps device model identifiers to their actual physical inputs
DEVICE_CAPABILITIES: dict[str, DeviceInputs] = {
    # WiiM Devices (plm_support is marked "Reserved" in WiiM docs - unreliable)
    "wiim_mini": DeviceInputs(
        inputs=["bluetooth", "line_in", "optical"],
        ignore_plm_bits=[5],  # Ignore bit 5 (Coaxial)
        notes="WiiM Mini has Line In (RCA), Optical In (TOSLINK), Bluetooth, WiFi. "
        "Does not have Ethernet or Coaxial.",
    ),
    "wiim_pro": DeviceInputs(
        inputs=["bluetooth", "line_in", "optical"],
        ignore_plm_bits=[2, 5],  # Ignore bit 2 (USB) and bit 5 (Coaxial)
        notes="WiiM Pro has Line In (RCA), Optical In (TOSLINK/SPDIF), Bluetooth, WiFi. "
        "Has Coax OUT but not Coax IN. USB-C is power only.",
    ),
    "wiim_pro_plus": DeviceInputs(
        inputs=["bluetooth", "line_in", "optical"],
        ignore_plm_bits=[2, 5],  # Ignore bit 2 (USB) and bit 5 (Coaxial)
        notes="WiiM Pro Plus has Line In (RCA), Optical In, Bluetooth, WiFi. "
        "Note: Per user requirement, coaxial is excluded despite hardware support.",
    ),
    "wiim_amp": DeviceInputs(
        inputs=["bluetooth", "line_in", "optical", "usb", "hdmi"],
        notes="WiiM Amp has Line In (RCA), Optical In, USB, HDMI ARC, Bluetooth, WiFi.",
    ),
    "wiim_sound": DeviceInputs(
        inputs=["bluetooth", "aux"],
        notes="WiiM Sound has Aux In (Line In), Bluetooth, WiFi. " "Excludes USB, Optical, and Coaxial.",
    ),
    "wiim_ultra": DeviceInputs(
        inputs=["bluetooth", "line_in", "optical", "coaxial", "usb", "hdmi", "phono"],
        notes="WiiM Ultra has Line In (RCA), Optical In, Coaxial In, USB Audio, HDMI In, "
        "Phono In (turntable), Bluetooth, WiFi. Most feature-rich model.",
    ),
    # Generic fallback for unknown WiiM devices
    "wiim_generic": DeviceInputs(
        inputs=["bluetooth", "line_in", "optical"],
        notes="Generic fallback for unknown WiiM devices",
    ),
    # Arylic Devices (plm_support documented by Arylic but still incomplete in practice)
    "up2stream_amp": DeviceInputs(
        inputs=["bluetooth", "line_in", "optical", "usb"],
        notes="Arylic UP2STREAM AMP has Line In, Optical, USB, Bluetooth. "
        "Note: plm_support may not indicate line_in even when present.",
    ),
    "arylic_h50": DeviceInputs(
        inputs=["bluetooth", "line_in", "optical", "usb", "phono", "hdmi"],
        notes="Arylic H50 all-in-one stereo amplifier. Has Line In (RCA), Phono (MM/MC), "
        "Optical, HDMI ARC, USB-C DAC, Bluetooth 5.2. "
        "Note: plm_support (0x71c012) only shows bluetooth, missing all other inputs.",
    ),
    "arylic_generic": DeviceInputs(
        inputs=["bluetooth", "line_in", "optical"],
        notes="Arylic/LinkPlay devices: plm_support is documented but may be incomplete. "
        "Common inputs: Line In, Optical, Bluetooth, USB.",
    ),
    # Audio Pro Devices (confirmed physical inputs from device owners)
    "link_2_wireless_multiroom_hifi_player": DeviceInputs(
        inputs=["bluetooth", "optical", "coaxial", "rca"],
        notes="Audio Pro Link 2: WiFi, Bluetooth, Optical In (TOSLINK), Coaxial In (S/PDIF), RCA analog in",
    ),
    "a28_speaker": DeviceInputs(
        inputs=["bluetooth", "optical", "rca", "hdmi"],
        notes="Audio Pro A28: WiFi, Bluetooth, Optical In, RCA/Line In, HDMI In",
    ),
    "addon_c5_mkii_speaker": DeviceInputs(
        inputs=["bluetooth", "rca"],
        notes="Audio Pro ADDON C5 MkII: WiFi, Bluetooth, RCA/Line In",
    ),
    # Generic LinkPlay device (augment with common inputs)
    "linkplay_generic": DeviceInputs(
        inputs=["bluetooth", "line_in", "optical", "rca"],
        notes="Generic LinkPlay-based devices: augment plm_support with common inputs",
    ),
}


def get_device_inputs(model: str | None, vendor: str | None = None) -> DeviceInputs | None:
    """Get device inputs for a specific model.

    Args:
        model: Device model string (e.g., "WiiM_Pro_with_gc4a", "WiiM Mini", "Arylic S50 Pro")
        vendor: Device vendor string (e.g., "WiiM", "Arylic", "LinkPlay")

    Returns:
        DeviceInputs object if model is known, None otherwise
    """
    if not model:
        return None

    model_lower = model.lower().replace(" ", "_").replace("-", "_")

    # Try exact match first
    if model_lower in DEVICE_CAPABILITIES:
        return DEVICE_CAPABILITIES[model_lower]

    # Check vendor to determine if we should trust plm_support
    if vendor:
        vendor_lower = vendor.lower()
        if "arylic" in vendor_lower:
            return DEVICE_CAPABILITIES["arylic_generic"]

    # Try partial matches for WiiM devices
    if "wiim_ultra" in model_lower or "ultra" in model_lower:
        return DEVICE_CAPABILITIES["wiim_ultra"]
    elif "wiim_pro_plus" in model_lower or "pro_plus" in model_lower:
        return DEVICE_CAPABILITIES["wiim_pro_plus"]
    elif "wiim_pro" in model_lower or "pro" in model_lower:
        return DEVICE_CAPABILITIES["wiim_pro"]
    elif "wiim_amp" in model_lower or "amp" in model_lower:
        return DEVICE_CAPABILITIES["wiim_amp"]
    elif "wiim_mini" in model_lower or "mini" in model_lower:
        return DEVICE_CAPABILITIES["wiim_mini"]
    elif "wiim_sound" in model_lower or "sound" in model_lower:
        return DEVICE_CAPABILITIES["wiim_sound"]
    elif "wiim" in model_lower:
        return DEVICE_CAPABILITIES["wiim_generic"]

    # Arylic device patterns
    if "up2stream_amp" in model_lower or "up2stream amp" in model_lower.replace("_", " "):
        return DEVICE_CAPABILITIES["up2stream_amp"]
    elif "arylic_h50" in model_lower or "h50" in model_lower:
        return DEVICE_CAPABILITIES["arylic_h50"]
    elif "arylic" in model_lower or "s50" in model_lower or "up2stream" in model_lower:
        return DEVICE_CAPABILITIES["arylic_generic"]

    # LinkPlay generic fallback (trust plm_support)
    return DEVICE_CAPABILITIES["linkplay_generic"]


def filter_plm_inputs(plm_inputs: list[str], plm_value: int, model: str | None) -> list[str]:
    """Filter plm_support inputs based on device-specific ignore list.

    Some devices report plm_support bits for inputs they don't actually have.
    This function removes those spurious inputs based on device model.

    Args:
        plm_inputs: List of inputs detected from plm_support bitmask
        plm_value: The raw plm_support value (for bit checking)
        model: Device model string

    Returns:
        Filtered list of inputs with spurious entries removed
    """
    device_info = get_device_inputs(model)
    if not device_info or not device_info.ignore_plm_bits:
        return plm_inputs

    # Map bit positions to input names
    bit_to_input = {
        0: "line_in",
        1: "bluetooth",
        2: "usb",
        3: "optical",
        5: "coaxial",
        7: "line_in_2",
    }

    # Filter out inputs from ignored bits
    filtered = []
    for input_name in plm_inputs:
        # Find which bit this input came from
        bit_pos = next((bit for bit, name in bit_to_input.items() if name == input_name), None)
        # Keep input if its bit is not in the ignore list
        if bit_pos is None or bit_pos not in device_info.ignore_plm_bits:
            filtered.append(input_name)

    return filtered
