"""WiiM Device Capabilities Detection.

This module provides firmware detection and capability probing for different
WiiM and LinkPlay device types to handle compatibility issues between newer
WiiM devices and older Audio Pro units.

The capability detection system uses a multi-layer approach:
1. Vendor Detection (WiiM, Arylic, Audio Pro, Generic LinkPlay)
2. Device Type Detection (WiiM vs Legacy)
3. Firmware Version Detection
4. Generation Detection (Audio Pro: mkii, w_generation, original)
5. Endpoint Probing (runtime capability testing)
6. Protocol Detection (HTTP/HTTPS, ports, client certs)

# pragma: allow-long-file capabilities-cohesive
# This file exceeds the 400 LOC soft limit (500 lines) but is kept as a single
# cohesive unit because:
# 1. Single responsibility: Device capability detection and caching
# 2. Well-organized: Clear sections for detection, caching, and helper functions
# 3. Tight coupling: All functions work together for capability detection
# 4. Maintainable: Clear structure, follows capability detection pattern
# 5. Natural unit: Represents one concept (device capabilities)
# Splitting would add complexity without clear benefit.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from .api.constants import (
    API_ENDPOINT_EQ_GET,
    API_ENDPOINT_EQ_LIST,
    API_ENDPOINT_EQ_STATUS,
    API_ENDPOINT_PEQ_GET_LIST,
    API_ENDPOINT_TRIGGER_OUT_STATUS,
    PEQ_PLUGIN_URI,
)
from .exceptions import WiiMError
from .model_names import is_known_wiim_model
from .models import DeviceInfo
from .normalize import normalize_vendor
from .profiles import get_device_profile

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "WiiMCapabilities",
    "detect_device_capabilities",
    "is_wiim_device",
    "is_legacy_device",
    "detect_audio_pro_generation",
    "detect_vendor",
    "supports_standard_led_control",
    "get_led_command_format",
    "get_optimal_polling_interval",
    "is_legacy_firmware_error",
]


class WiiMCapabilities:
    """Detect and cache firmware capabilities for different device types.

    This class provides capability detection with caching to avoid repeated
    probing of the same device. Capabilities are detected through a combination
    of static analysis (model name, firmware version) and runtime probing.
    """

    def __init__(self) -> None:
        """Initialize the capabilities detector."""
        self._capabilities: dict[str, dict[str, Any]] = {}
        self._firmware_versions: dict[str, str] = {}
        self._device_types: dict[str, str] = {}

    async def detect_capabilities(self, client: Any, device_info: DeviceInfo) -> dict[str, Any]:
        """Probe device capabilities and cache results.

        Args:
            client: WiiM API client instance (must have _request method and host attribute)
            device_info: Device information from getStatusEx

        Returns:
            Dictionary of device capabilities with vendor, device type, firmware,
            generation, endpoint support, and protocol preferences.
        """
        device_id = f"{client.host}:{device_info.uuid}"

        if device_id in self._capabilities:
            # Return cached capabilities, but ensure vendor is normalized
            cached = self._capabilities[device_id].copy()
            if "vendor" not in cached or not cached.get("vendor"):
                # Vendor missing from cache, detect and normalize it
                vendor = detect_vendor(device_info)
                cached["vendor"] = normalize_vendor(vendor)
            else:
                # Normalize existing vendor (in case it's from cache with old format)
                cached["vendor"] = normalize_vendor(cached["vendor"])
            return cached

        # Start with base capabilities from static detection
        capabilities = detect_device_capabilities(device_info)

        # Detect and normalize vendor (always ensure vendor is set and normalized)
        if "vendor" not in capabilities or not capabilities.get("vendor"):
            vendor = detect_vendor(device_info)
            vendor = normalize_vendor(vendor)
            capabilities["vendor"] = vendor
        else:
            # Normalize existing vendor (in case it's from cache with old format)
            capabilities["vendor"] = normalize_vendor(capabilities["vendor"])
            vendor = capabilities["vendor"]  # Ensure vendor variable is set for logging

        # Detect LED support
        capabilities["supports_led_control"] = supports_standard_led_control(device_info)
        capabilities["led_command_format"] = get_led_command_format(device_info)

        # Add defaults for probing
        capabilities.setdefault("supports_getstatuse", True)
        capabilities.setdefault("supports_getslavelist", True)
        capabilities.setdefault("supports_metadata", True)
        capabilities.setdefault("supports_audio_output", True)
        capabilities.setdefault("supports_presets", True)
        capabilities.setdefault("supports_eq", True)
        capabilities.setdefault("supports_peq", False)
        capabilities.setdefault("supports_trigger_out", False)

        # Probe for getStatusEx support
        try:
            await client.get_status()
        except WiiMError:
            capabilities["supports_getstatuse"] = False
            _LOGGER.debug("Device %s does not support getStatusEx", client.host)

        # Probe for best status endpoint - try in order of preference:
        # 1. getPlayerStatusEx (enhanced player status - most WiiM devices)
        # 2. getPlayerStatus (basic player status - some LinkPlay devices like HCN_BWD03)
        # 3. getStatusEx (device info + player status - fallback)
        # See: https://github.com/mjcumming/wiim/issues/145
        status_endpoint = None

        # Try getPlayerStatusEx first
        try:
            raw = await client._request("/httpapi.asp?command=getPlayerStatusEx")
            if isinstance(raw, dict) and _is_valid_player_status(raw):
                capabilities["supports_player_status_ex"] = True
                status_endpoint = "/httpapi.asp?command=getPlayerStatusEx"
                _LOGGER.debug("Device %s supports getPlayerStatusEx", client.host)
        except WiiMError:
            capabilities["supports_player_status_ex"] = False
            _LOGGER.debug("Device %s does not support getPlayerStatusEx", client.host)

        # If getPlayerStatusEx failed, try getPlayerStatus
        if not status_endpoint:
            try:
                raw = await client._request("/httpapi.asp?command=getPlayerStatus")
                if isinstance(raw, dict) and _is_valid_player_status(raw):
                    status_endpoint = "/httpapi.asp?command=getPlayerStatus"
                    _LOGGER.debug("Device %s supports getPlayerStatus (using as fallback)", client.host)
            except WiiMError:
                _LOGGER.debug("Device %s does not support getPlayerStatus", client.host)

        # Store the best status endpoint (if found, otherwise base.py will use getStatusEx)
        if status_endpoint:
            capabilities["status_endpoint"] = status_endpoint

        # Probe for getSlaveList support
        try:
            await client._request("/httpapi.asp?command=multiroom:getSlaveList")
        except WiiMError:
            capabilities["supports_getslavelist"] = False
            _LOGGER.debug("Device %s does not support getSlaveList", client.host)

        # Probe for metadata support (getMetaInfo)
        try:
            await client._request("/httpapi.asp?command=getMetaInfo")
        except WiiMError:
            # Keep metadata enabled for all WiiM devices. A single probe failure can be
            # transient and should not permanently disable metadata/artwork handling.
            if capabilities.get("is_wiim_device", False):
                capabilities["supports_metadata"] = True
                _LOGGER.debug(
                    "Device %s is WiiM; keeping supports_metadata=True despite getMetaInfo probe failure",
                    client.host,
                )
            else:
                capabilities["supports_metadata"] = False
                _LOGGER.debug("Device %s does not support getMetaInfo", client.host)

        # Probe for audio output support (read-only probe)
        # If we can read audio output status, assume we can set it too.
        # Try getNewAudioOutputHardwareMode first (works on all tested devices including
        # WiiM Ultra which returns "unknown command" for getAudioOutputStatus - Issue #160).
        # Fall back to getAudioOutputStatus for devices that may only support that endpoint.
        # We don't probe setting to avoid changing device state during initialization.
        # See: https://github.com/mjcumming/wiim/issues/144
        audio_output_supported = False
        try:
            result = await client._request("/httpapi.asp?command=getNewAudioOutputHardwareMode")
            audio_output_supported = True
            _LOGGER.debug(
                "Device %s supports audio output control (getNewAudioOutputHardwareMode), result: %s",
                client.host,
                result,
            )
        except (WiiMError, Exception):
            try:
                legacy_result = await client._request("/httpapi.asp?command=getAudioOutputStatus")
                audio_output_supported = True
                _LOGGER.debug(
                    "Device %s supports audio output control via fallback endpoint "
                    "(getAudioOutputStatus), result: %s",
                    client.host,
                    legacy_result,
                )
            except (WiiMError, Exception) as e:
                # Keep WiiM default support on probe failure to avoid transient false negatives
                # hiding output controls in integrations.
                if capabilities.get("is_wiim_device", False):
                    audio_output_supported = True
                    _LOGGER.debug(
                        "Device %s is WiiM; keeping supports_audio_output=True despite probe failure (%s)",
                        client.host,
                        type(e).__name__,
                    )
                else:
                    _LOGGER.debug(
                        "Device %s does not support audio output control (%s)",
                        client.host,
                        type(e).__name__,
                    )

        capabilities["supports_audio_output"] = audio_output_supported

        # Probe for preset support (getPresetInfo)
        # If getPresetInfo fails, fall back to checking preset_key from device info
        try:
            await client._request("/httpapi.asp?command=getPresetInfo")
            capabilities["supports_presets"] = True
            capabilities["presets_full_data"] = True  # WiiM devices: can read preset names/URLs
            _LOGGER.debug("Device %s supports presets with full data (getPresetInfo available)", client.host)
        except WiiMError:
            # Fallback: check if preset_key indicates preset support
            # preset_key > 0 means device supports presets (even if we can't read names)
            if device_info.preset_key is not None:
                try:
                    preset_key_int = int(device_info.preset_key)
                    if preset_key_int > 0:
                        capabilities["supports_presets"] = True
                        capabilities["presets_full_data"] = False  # LinkPlay devices: only count available
                        _LOGGER.debug(
                            "Device %s supports presets (fallback: preset_key=%d, "
                            "getPresetInfo not available - count only)",
                            client.host,
                            preset_key_int,
                        )
                    else:
                        capabilities["supports_presets"] = False
                        capabilities["presets_full_data"] = False
                        _LOGGER.debug("Device %s does not support presets (preset_key=%d)", client.host, preset_key_int)
                except (TypeError, ValueError):
                    # Invalid preset_key value, assume no support
                    capabilities["supports_presets"] = False
                    capabilities["presets_full_data"] = False
                    _LOGGER.debug("Device %s does not support getPresetInfo (invalid preset_key)", client.host)
            else:
                # No preset_key available, assume no support
                capabilities["supports_presets"] = False
                capabilities["presets_full_data"] = False
                _LOGGER.debug("Device %s does not support getPresetInfo (no preset_key)", client.host)

        # Probe for EQ support (read-only probe)
        # If we can read any EQ endpoint, assume we support EQ
        # We don't probe setting to avoid changing device state during initialization
        # See: https://github.com/mjcumming/wiim/issues/144
        eq_supported = False
        for endpoint in [
            API_ENDPOINT_EQ_GET,  # EQGetBand
            API_ENDPOINT_EQ_LIST,  # EQGetList
            API_ENDPOINT_EQ_STATUS,  # EQGetStat
        ]:
            try:
                await client._request(endpoint)
                eq_supported = True
                _LOGGER.debug("Device %s supports EQ (detected via %s)", client.host, endpoint)
                break
            except WiiMError:
                continue  # Try next endpoint

        capabilities["supports_eq"] = eq_supported
        if not eq_supported:
            _LOGGER.debug(
                "Device %s does not support EQ (tried EQGetBand, EQGetList, EQGetStat)",
                client.host,
            )

        # Probe for WiiM LV2 PEQ support (read-only probe)
        # PEQ is a WiiM-specific feature not available on Audio Pro, Arylic, or generic
        # LinkPlay devices.  We use the preset-list endpoint as a lightweight read probe.
        peq_supported = False
        try:
            await client._request(API_ENDPOINT_PEQ_GET_LIST + quote(PEQ_PLUGIN_URI, safe=""))
            peq_supported = True
            _LOGGER.debug("Device %s supports WiiM LV2 PEQ (EQv2GetList probe succeeded)", client.host)
        except WiiMError:
            _LOGGER.debug("Device %s does not support WiiM LV2 PEQ (EQv2GetList probe failed)", client.host)

        capabilities["supports_peq"] = peq_supported

        # Probe for 12V trigger support (WiiM Ultra / Pro / Pro Plus)
        # getTriggeroutStatus returns {"status":0|1}; only some WiiM models have the hardware
        try:
            result = await client._request(API_ENDPOINT_TRIGGER_OUT_STATUS)
            if isinstance(result, dict) and "status" in result:
                capabilities["supports_trigger_out"] = True
                _LOGGER.debug(
                    "Device %s supports 12V trigger (getTriggeroutStatus), result: %s",
                    client.host,
                    result,
                )
        except WiiMError:
            _LOGGER.debug("Device %s does not support 12V trigger (getTriggeroutStatus)", client.host)

        # Get device profile for profile-specific settings (like reboot command)
        # Profile provides device-specific command variations
        # See: https://github.com/mjcumming/wiim/issues/177
        profile = get_device_profile(device_info)
        capabilities["reboot_command"] = profile.endpoints.reboot_command
        _LOGGER.debug(
            "Device %s reboot command: %s (from profile %s)",
            client.host,
            capabilities["reboot_command"],
            profile.display_name,
        )

        self._capabilities[device_id] = capabilities
        # Log capabilities at DEBUG level to reduce verbosity
        # Only log key info - detailed features available via debug logging
        _LOGGER.debug(
            "Detected capabilities for %s (%s): vendor=%s, generation=%s",
            device_info.name or "Unknown",
            device_info.model or "Unknown",
            vendor,
            capabilities.get("audio_pro_generation", "unknown"),
        )
        # Log detailed features at DEBUG level to reduce verbosity
        _LOGGER.debug(
            "Capability features for %s: %s",
            device_info.name or "Unknown",
            {k: v for k, v in capabilities.items() if k.startswith("supports_") and v},
        )

        return capabilities

    def get_cached_capabilities(self, device_id: str) -> dict[str, Any] | None:
        """Get cached capabilities for a device.

        Args:
            device_id: Device identifier (host:uuid)

        Returns:
            Cached capabilities or None if not found
        """
        return self._capabilities.get(device_id)

    def clear_cache(self) -> None:
        """Clear all cached capabilities."""
        self._capabilities.clear()
        self._firmware_versions.clear()
        self._device_types.clear()


def detect_device_capabilities(device_info: DeviceInfo) -> dict[str, Any]:
    """Detect device capabilities from device info without API calls.

    This function performs static capability detection based on device model,
    firmware version, and known device patterns. It does not probe endpoints.

    Args:
        device_info: Device information from getStatusEx

    Returns:
        Dictionary of detected capabilities including:
        - firmware_version: Firmware version string
        - device_type: Device model name
        - is_wiim_device: Whether device is a WiiM device
        - is_legacy_device: Whether device is a legacy device
        - audio_pro_generation: Audio Pro generation (mkii, w_generation, original, unknown)
        - supports_audio_output: Whether device supports audio output control
        - supports_alarms: Whether device supports alarm clocks (WiiM only)
        - supports_sleep_timer: Whether device supports sleep timer (WiiM only)
        - supports_firmware_install: Whether device supports firmware update installation via API (WiiM only)
        - max_alarm_slots: Number of alarm slots supported (3 for WiiM, 0 otherwise)
        - response_timeout: Recommended timeout in seconds
        - retry_count: Recommended retry count
        - protocol_priority: Preferred protocol order (["https", "http"] or ["http", "https"])
        - requires_client_cert: Whether device requires client certificate
        - preferred_ports: List of preferred ports in order
        - supports_player_status_ex: Whether device supports getPlayerStatusEx
        - supports_presets: Whether device supports presets
        - supports_eq: Whether device supports EQ
        - supports_metadata: Whether device supports metadata
        - status_endpoint: Preferred status endpoint path
    """
    # Detect and normalize vendor first
    vendor = detect_vendor(device_info)
    vendor = normalize_vendor(vendor)

    capabilities: dict[str, Any] = {
        "firmware_version": device_info.firmware,
        "device_type": device_info.model,
        "vendor": vendor,  # Always include normalized vendor
        "is_wiim_device": is_wiim_device(device_info),
        "is_legacy_device": is_legacy_device(device_info),
        "audio_pro_generation": detect_audio_pro_generation(device_info),
        "supports_audio_output": False,  # Default to False, enable for WiiM devices
        "supports_alarms": False,  # Default to False, enable for WiiM devices
        "supports_sleep_timer": False,  # Default to False, enable for WiiM devices
        "max_alarm_slots": 0,  # Default to 0, set to 3 for WiiM devices
        "response_timeout": 5.0,
        "retry_count": 3,
        "protocol_priority": ["https", "http"],  # Default: try HTTPS first
        # Canonical source IDs from Player.source_catalog that should not be treated
        # as directly selectable for this device (device/firmware-specific quirks).
        "non_selectable_source_ids": [],
    }

    if capabilities["is_wiim_device"]:
        capabilities["supports_audio_output"] = True  # All WiiM devices support audio output control
        capabilities["response_timeout"] = 2.0
        capabilities["retry_count"] = 2
        capabilities["protocol_priority"] = ["https", "http"]
        capabilities["supports_player_status_ex"] = True
        capabilities["supports_presets"] = True
        capabilities["supports_eq"] = True
        capabilities["supports_metadata"] = True
        capabilities["supports_alarms"] = True  # WiiM devices support alarm clocks
        capabilities["supports_sleep_timer"] = True  # WiiM devices support sleep timer
        capabilities["max_alarm_slots"] = 3  # WiiM supports 3 independent alarms
        capabilities["supports_firmware_install"] = True  # WiiM devices support firmware update installation via API
    elif capabilities["is_legacy_device"]:
        # Apply Audio Pro generation specific optimizations ONLY for Audio Pro devices
        # Other legacy devices (e.g., Arylic) should use defaults or be probed
        vendor = capabilities.get("vendor", "")
        if vendor == "audio_pro":
            generation = capabilities["audio_pro_generation"]
            model_lower = (device_info.model or "").lower()
            if generation == "mkii":
                capabilities["response_timeout"] = 6.0
                capabilities["retry_count"] = 3
                capabilities["protocol_priority"] = ["https", "http"]  # HTTPS first for MkII
                # Audio Pro MkII specific: requires client certificate for mTLS on port 4443
                capabilities["requires_client_cert"] = True
                capabilities["preferred_ports"] = [4443, 8443, 443]  # Port 4443 primary
                capabilities["supports_player_status_ex"] = False  # Use getStatusEx instead
                capabilities["supports_presets"] = False  # getPresetInfo not supported
                capabilities["supports_eq"] = False  # EQ commands not supported
                # Audio Pro MkII: getMetaInfo support varies by firmware/model - probe at runtime.
                # Default to True here because getMetaInfo is read-only and the library handles
                # "unknown command"/404 gracefully.
                capabilities["supports_metadata"] = True
                capabilities["status_endpoint"] = "/httpapi.asp?command=getStatusEx"

                # Audio Pro A10 MkII WiiM Edition firmware quirk:
                # AUX/Line In can be active (mode 60) but switchmode source
                # selection is not implemented and returns silent no-op.
                # Keep source visible, but don't expose as directly selectable.
                if "a10" in model_lower:
                    capabilities["non_selectable_source_ids"] = ["line_in", "aux", "rca"]
            elif generation == "w_generation":
                capabilities["response_timeout"] = 4.0
                capabilities["retry_count"] = 2
                capabilities["protocol_priority"] = ["https", "http"]
                capabilities["supports_player_status_ex"] = True
                capabilities["supports_presets"] = True  # May support presets
                capabilities["supports_eq"] = True  # May support EQ
                capabilities["supports_metadata"] = True  # May support metadata
            else:
                # Original Audio Pro devices
                capabilities["response_timeout"] = 8.0
                capabilities["retry_count"] = 4
                capabilities["protocol_priority"] = ["http", "https"]  # HTTP first for legacy
                capabilities["supports_player_status_ex"] = False  # Use getStatusEx
                capabilities["supports_presets"] = True  # May support presets
                capabilities["supports_eq"] = False  # EQ typically not supported
                capabilities["supports_metadata"] = False  # Metadata typically not supported
        # For other legacy devices (e.g., Arylic), use defaults - capabilities will be probed

    return capabilities


def detect_vendor(device_info: DeviceInfo) -> str:
    """Detect device vendor from device information.

    Args:
        device_info: Device information

    Returns:
        Normalized vendor string: "wiim", "arylic", "audio_pro", or "linkplay_generic"
    """
    if not device_info.model:
        # Try device name as fallback
        if device_info.name:
            return normalize_vendor(device_info.name)
        return "linkplay_generic"

    model_lower = device_info.model.lower()
    name_lower = (device_info.name or "").lower()

    # WiiM devices - include known raw model aliases (e.g., "Muzo_Mini")
    # and project variants like "WiiM_Pro_with_gc4a".
    if is_known_wiim_model(device_info.model) or "wiim" in model_lower:
        return "wiim"
    if "wiim" in name_lower:
        return "wiim"

    # Arylic devices
    if any(arylic in model_lower for arylic in ["arylic", "up2stream", "s10+"]):
        return "arylic"
    if "arylic" in name_lower or "up2stream" in name_lower:
        return "arylic"

    # Audio Pro devices
    if any(pro in model_lower for pro in ["audio pro", "addon", "a10", "a15", "a28", "c10"]):
        return "audio_pro"
    if "audio pro" in name_lower or "addon" in name_lower:
        return "audio_pro"

    return "linkplay_generic"


def is_wiim_device(device_info: DeviceInfo) -> bool:
    """Check if device is a WiiM device.

    Args:
        device_info: Device information

    Returns:
        True if device is a WiiM device
    """
    if not device_info.model:
        return False

    model_lower = device_info.model.lower()
    return is_known_wiim_model(device_info.model) or "wiim" in model_lower


def detect_audio_pro_generation(device_info: DeviceInfo) -> str:
    """Detect Audio Pro device generation for optimized handling.

    Args:
        device_info: Device information

    Returns:
        Generation string: "original", "mkii", "w_generation", or "unknown"
    """
    if not device_info.model:
        return "unknown"

    model_lower = device_info.model.lower()

    # Audio Pro generation patterns
    if any(gen in model_lower for gen in ["mkii", "mk2", "mk ii", "mark ii"]):
        return "mkii"
    elif any(gen in model_lower for gen in ["w-", "w series", "w generation", "w gen"]):
        return "w_generation"
    elif any(model in model_lower for model in ["a10", "a15", "a28", "c10", "audio pro"]):
        # Modern Audio Pro devices (assume MkII if not specified)
        if device_info.firmware:
            # Try to determine from firmware version if available
            firmware_lower = device_info.firmware.lower()
            if any(version in firmware_lower for version in ["1.56", "1.57", "1.58", "1.59", "1.60"]):
                return "mkii"  # MkII firmware range
            elif any(version in firmware_lower for version in ["2.0", "2.1", "2.2", "2.3"]):
                return "w_generation"  # W-generation firmware range

        return "mkii"  # Default to MkII for modern Audio Pro models
    else:
        return "original"


def is_legacy_device(device_info: DeviceInfo) -> bool:
    """Check if device is a legacy Audio Pro or older LinkPlay device.

    Args:
        device_info: Device information

    Returns:
        True if device is a legacy device
    """
    if not device_info.model:
        return False

    model_lower = device_info.model.lower()
    legacy_models = [
        "audio pro",
        "a10",  # Audio Pro A10 (including MkII)
        "a15",  # Audio Pro A15 (including MkII)
        "a28",  # Audio Pro A28
        "c10",  # Audio Pro C10 (including MkII)
        "arylic",
        "doss",
        "dayton audio",
        "ieast",
        "linkplay",
        "smart zone",
    ]

    return any(legacy_model in model_lower for legacy_model in legacy_models)


def supports_standard_led_control(device_info: DeviceInfo) -> bool:
    """Check if device supports standard LinkPlay LED commands.

    Args:
        device_info: Device information

    Returns:
        True if device supports standard LED commands
    """
    if not device_info.model:
        return True  # Assume yes for unknown devices

    model_lower = device_info.model.lower()

    # Devices known to NOT support standard LED commands
    non_standard_led_devices = [
        "arylic",
        "up2stream",
        "s10+",
        "amp 2.0",
        "amp 2.1",
    ]

    return not any(device_type in model_lower for device_type in non_standard_led_devices)


def get_led_command_format(device_info: DeviceInfo) -> str:
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


def _is_valid_player_status(response: dict[str, Any]) -> bool:
    """Check if API response contains valid player status data.

    Some devices (e.g., HCN_BWD03) return system info from getStatusEx instead of
    player status. This function validates that a response contains actual player
    status fields.

    Args:
        response: API response dictionary

    Returns:
        True if response contains player status fields, False if it's just system info
    """
    # Player status should contain at least some of these playback-related fields
    player_status_fields = {
        "status",  # Play state (play/pause/stop)
        "curpos",  # Current position
        "totlen",  # Total length/duration
        "Title",  # Track title
        "Artist",  # Track artist
        "vol",  # Volume
        "mute",  # Mute state
        "mode",  # Playback mode
        "loop",  # Loop mode
    }

    # System-only responses typically have these without player fields
    system_only_fields = {"ssid", "firmware", "build", "project", "language"}

    response_keys = set(response.keys())

    # Check if we have player status fields
    has_player_fields = bool(response_keys & player_status_fields)

    # If we only have system fields and no player fields, it's not valid player status
    if not has_player_fields and (response_keys & system_only_fields):
        return False

    return has_player_fields


def get_optimal_polling_interval(
    capabilities: dict[str, Any], role: str, is_playing: bool, upnp_working: bool = False
) -> int:
    """Get optimal polling interval based on device capabilities and state.

    Args:
        capabilities: Device capabilities dictionary
        role: Device role (master/slave/solo)
        is_playing: Whether device is currently playing
        upnp_working: DEPRECATED - Always use fast polling when playing.
            UPnP events supplement HTTP polling but don't replace it (following DLNA DMR pattern).
            We can't reliably detect if UPnP is working because UPnP has no heartbeat/keepalive.

    Returns:
        Polling interval in seconds
    """
    if capabilities.get("is_legacy_device", False):
        # Legacy devices need longer intervals
        if role == "slave":
            return 10  # 10 seconds for legacy slaves
        elif is_playing:
            return 3  # 3 seconds for legacy devices during playback
        else:
            return 15  # 15 seconds for legacy devices when idle
    else:
        # Modern WiiM devices
        # Always use fast HTTP polling when playing, regardless of UPnP status.
        # UPnP events provide instant updates on top of HTTP polling (following DLNA DMR pattern).
        # We removed the upnp_working check because UPnP has no heartbeat, so we can't
        # reliably detect if it's working (idle devices = no events = false negative).
        if role == "slave":
            return 5  # 5 seconds for slaves
        elif is_playing:
            return 1  # 1 second for real-time updates (always, regardless of UPnP)
        else:
            return 5  # 5 seconds when idle


def is_legacy_firmware_error(error: Exception) -> bool:
    """Detect errors specific to legacy firmware.

    Args:
        error: Exception to check

    Returns:
        True if error is typical of legacy firmware
    """
    error_str = str(error).lower()
    legacy_error_indicators = [
        "empty response",
        "invalid json",
        "expecting value",
        "timeout",
        "connection refused",
        "unknown command",
    ]
    return any(indicator in error_str for indicator in legacy_error_indicators)
