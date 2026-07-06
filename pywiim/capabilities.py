"""WiiM Device Capabilities Detection.

This module provides firmware detection and capability probing for different
WiiM and LinkPlay device types to handle compatibility issues between newer
WiiM devices and older Audio Pro units.

The capability detection system uses a multi-layer approach:
1. Vendor Detection (WiiM, Arylic, Audio Pro, Generic LinkPlay)
2. Device Type Detection (WiiM vs Legacy)
3. Firmware Version Detection
4. Generation Detection (Audio Pro: mkii, w_generation, original)
5. Endpoint Probing (runtime tests; LED/12V trigger from static model hints, no mutating HTTP at connect)
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

import asyncio
import logging
from typing import Any
from urllib.parse import quote

from .api.base import ApiResponse
from .api.constants import (
    API_ENDPOINT_EQ_GET,
    API_ENDPOINT_EQ_LIST,
    API_ENDPOINT_EQ_STATUS,
    API_ENDPOINT_GET_CHANNEL_BALANCE,
    API_ENDPOINT_PEQ_GET_LIST,
    API_ENDPOINT_SUBWOOFER_STATUS,
    PEQ_PLUGIN_URI,
)
from .api.subwoofer import is_valid_subwoofer_lpf_dict
from .exceptions import WiiMError
from .model_names import is_known_wiim_model, is_wiim_12v_trigger_model, is_wiim_ultra
from .models import DeviceInfo
from .normalize import canonical_source_key, normalize_vendor
from .profiles import detect_audio_pro_generation, detect_vendor, get_device_profile

_LOGGER = logging.getLogger(__name__)


def _channel_balance_probe_success(response: ApiResponse) -> bool:
    """True when getChannelBalance returned a numeric balance (not unknown command / empty).

    ``get_channel_balance()`` on the client coerces errors to 0.0; capability probing must
    use raw ``_request`` results and this helper so unsupported firmware is not misread as
    "centered balance".
    """
    parsed = response.parsed
    if isinstance(parsed, bool):
        return False
    if isinstance(parsed, (int, float)):
        return True
    if isinstance(parsed, str):
        stripped = parsed.strip()
        if not stripped:
            return False
        lowered = stripped.lower()
        if "unknown" in lowered:
            return False
        try:
            float(stripped)
        except ValueError:
            return False
        else:
            return True
    raw = (response.raw or "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    if "unknown" in lowered:
        return False
    try:
        float(raw)
    except ValueError:
        return False
    return True


def _subwoofer_probe_error_definitively_unsupported(err: Exception) -> bool:
    """True when the error indicates the endpoint/command is not available."""
    s = str(err).lower()
    return "unknown command" in s or "404" in s or "not found" in s


async def _probe_supports_subwoofer(client: Any, device_info: DeviceInfo, capabilities: dict[str, Any]) -> bool | None:
    """Runtime probe for getSubLPF (same backing as get_subwoofer_status_raw).

    Returns:
        True if supported, False if definitively unsupported, None for WiiM when
        the probe stays inconclusive after retries (transient errors).
    """
    if not capabilities.get("is_wiim_device"):
        return False

    host = getattr(client, "host", "?")
    model = device_info.model or "unknown"
    max_attempts = 3
    last_err: Exception | None = None

    for attempt in range(max_attempts):
        try:
            r = await client._request(API_ENDPOINT_SUBWOOFER_STATUS)
            if is_valid_subwoofer_lpf_dict(r.parsed):
                if attempt:
                    _LOGGER.debug("getSubLPF succeeded on retry for host=%s model=%s", host, model)
                return True
            raw_preview = (r.raw or "")[:200] if r.raw else None
            _LOGGER.debug(
                "Subwoofer probe host=%s model=%s: unsupported or invalid response "
                "(expected subwoofer dict); parsed_type=%s raw_preview=%r",
                host,
                model,
                type(r.parsed).__name__,
                raw_preview,
            )
            return False
        except Exception as err:
            last_err = err
            if _subwoofer_probe_error_definitively_unsupported(err):
                _LOGGER.debug(
                    "Subwoofer probe host=%s model=%s: unsupported (error=%s)",
                    host,
                    model,
                    err,
                )
                return False
            if attempt < max_attempts - 1 and is_legacy_firmware_error(err):
                await asyncio.sleep(0.15)
                continue
            break

    _LOGGER.warning(
        "Subwoofer probe inconclusive for host=%s model=%s after %d attempts: %s",
        host,
        model,
        max_attempts,
        last_err,
    )
    return None


async def _probe_wiim_input_metadata(client: Any, capabilities: dict[str, Any]) -> None:
    """Probe WiiM-only input metadata and store it as a source overlay.

    Populates (WiiM devices only, best-effort):

    - ``wiim_input_capability``: canonical ids the device reports as physical
      inputs (``getAudioInputCapbility``) — used to fill gaps in enumeration.
    - ``wiim_input_enable``: ``{canonical_id: bool}`` from ``getAudioInputEnable``
      — lets enumeration hide inputs the user disabled in the WiiM app.
    - ``source_rename``: ``{canonical_id: label}`` from ``getModeRename`` — user
      custom labels overlaid on the stable ids (never a replacement for identity).

    These are read-only WiiM endpoints absent on most LinkPlay/OEM devices, so
    the probe is skipped for non-WiiM devices and any failing endpoint is simply
    left out (no overlay → today's behavior is preserved).
    """
    if not capabilities.get("is_wiim_device"):
        return

    host = getattr(client, "host", "?")

    try:
        capability = await client.get_audio_input_capability()
        if capability is not None and capability.audio_input:
            ids = [canonical_source_key(item.mode) for item in capability.audio_input if item.mode]
            capabilities["wiim_input_capability"] = [i for i in ids if i]
    except WiiMError as err:
        _LOGGER.debug("getAudioInputCapbility probe failed for host=%s: %s", host, err)

    try:
        enable = await client.get_audio_input_enable()
        if enable is not None and enable.audio_input:
            enable_map: dict[str, bool] = {}
            for item in enable.audio_input:
                key = canonical_source_key(item.mode)
                if key:
                    enable_map[key] = item.enable
            if enable_map:
                capabilities["wiim_input_enable"] = enable_map
    except WiiMError as err:
        _LOGGER.debug("getAudioInputEnable probe failed for host=%s: %s", host, err)

    try:
        rename = await client.get_mode_rename()
        if rename:
            rename_map: dict[str, str] = {}
            for mode, label in rename.items():
                key = canonical_source_key(mode)
                label_str = str(label).strip()
                if key and label_str:
                    rename_map[key] = label_str
            if rename_map:
                capabilities["source_rename"] = rename_map
    except WiiMError as err:
        _LOGGER.debug("getModeRename probe failed for host=%s: %s", host, err)


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

    def invalidate_device(self, device_id: str) -> None:
        """Drop cached capabilities for one device (host:uuid) so the next detect re-probes."""
        self._capabilities.pop(device_id, None)

    async def detect_capabilities(self, client: Any, device_info: DeviceInfo, *, force: bool = False) -> dict[str, Any]:
        """Probe device capabilities and cache results.

        Args:
            client: WiiM API client instance (must have _request method and host attribute)
            device_info: Device information from getStatusEx
            force: When True, ignore cached capabilities and re-run all probes.

        Returns:
            Dictionary of device capabilities with vendor, device type, firmware,
            generation, endpoint support, and protocol preferences.
        """
        device_id = f"{client.host}:{device_info.uuid}"

        if not force and device_id in self._capabilities:
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
        capabilities.setdefault("supports_led_switch", False)
        capabilities.setdefault("supports_display_config", False)

        # LED Indicator (ADR 005): Arylic — set by vendor, try-and-ignore on write; no probe
        if capabilities.get("vendor") == "arylic":
            capabilities["supports_led_switch"] = True
            _LOGGER.debug("Device %s: LED Indicator supported (Arylic vendor, try-and-ignore)", client.host)

        # Display/LCD (WiiM Ultra only) - model-based, no probe to avoid changing screen state
        if is_wiim_ultra(device_info.model):
            capabilities["supports_display_config"] = True
            _LOGGER.debug("Device %s supports display/LCD config (WiiM Ultra)", client.host)

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
            r = await client._request("/httpapi.asp?command=getPlayerStatusEx")
            if isinstance(r.parsed, dict) and _is_valid_player_status(r.parsed):
                capabilities["supports_player_status_ex"] = True
                status_endpoint = "/httpapi.asp?command=getPlayerStatusEx"
                _LOGGER.debug("Device %s supports getPlayerStatusEx", client.host)
        except WiiMError:
            capabilities["supports_player_status_ex"] = False
            _LOGGER.debug("Device %s does not support getPlayerStatusEx", client.host)

        # If getPlayerStatusEx failed, try getPlayerStatus
        if not status_endpoint:
            try:
                r = await client._request("/httpapi.asp?command=getPlayerStatus")
                if isinstance(r.parsed, dict) and _is_valid_player_status(r.parsed):
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
            meta_resp = await client._request("/httpapi.asp?command=getMetaInfo")
            # Devices that don't implement getMetaInfo (e.g. some Arylic Up2Stream models)
            # return a non-JSON body like "unknown command" with HTTP 200 instead of raising.
            # Disable metadata for those so the poll loop stops calling it every cycle.
            # WiiM always keeps metadata enabled. See https://github.com/mjcumming/wiim/issues/248
            meta_raw = str(getattr(meta_resp, "raw", "") or "").lower()
            if not capabilities.get("is_wiim_device", False) and (
                "unknown command" in meta_raw or "not support" in meta_raw or "fail" == meta_raw.strip()
            ):
                capabilities["supports_metadata"] = False
                _LOGGER.debug(
                    "Device %s getMetaInfo unsupported (got %r); disabling metadata",
                    client.host,
                    meta_raw[:40],
                )
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
                result.parsed or result.raw,
            )
        except (WiiMError, Exception):
            try:
                legacy_result = await client._request("/httpapi.asp?command=getAudioOutputStatus")
                audio_output_supported = True
                _LOGGER.debug(
                    "Device %s supports audio output control via fallback endpoint "
                    "(getAudioOutputStatus), result: %s",
                    client.host,
                    legacy_result.parsed or legacy_result.raw,
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

        # Channel balance (WiiM unofficial HTTP API only — not on Arylic / generic LinkPlay)
        capabilities["supports_channel_balance"] = False
        if capabilities.get("is_wiim_device"):
            try:
                balance_result = await client._request(API_ENDPOINT_GET_CHANNEL_BALANCE)
                if _channel_balance_probe_success(balance_result):
                    capabilities["supports_channel_balance"] = True
                    _LOGGER.debug("Device %s supports channel balance (getChannelBalance)", client.host)
                else:
                    _LOGGER.debug(
                        "Device %s does not support channel balance (getChannelBalance non-numeric or error)",
                        client.host,
                    )
            except WiiMError:
                _LOGGER.debug("Device %s does not support channel balance (getChannelBalance failed)", client.host)

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

        # Subwoofer (getSubLPF) — WiiM-only read probe; same endpoint as get_subwoofer_status_raw()
        capabilities["supports_subwoofer"] = await _probe_supports_subwoofer(client, device_info, capabilities)

        # WiiM-only input metadata (capability list / enable flags / custom labels).
        # Read-only overlay on stable source ids; absent endpoints leave enumeration unchanged.
        await _probe_wiim_input_metadata(client, capabilities)

        # Get device profile for profile-specific settings (like reboot command)
        # Profile provides device-specific command variations
        # See: https://github.com/mjcumming/wiim/issues/177
        profile = get_device_profile(device_info)
        capabilities["reboot_command"] = profile.endpoints.reboot_command
        capabilities["loop_mode_scheme"] = profile.loop_mode_scheme
        # Profile is authoritative for protocol preference (HTTP-first for Arylic/generic,
        # HTTPS-first for WiiM/Audio-Pro). See https://github.com/mjcumming/wiim/issues/248
        capabilities["protocol_priority"] = list(profile.connection.protocol_priority)
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
        - supports_channel_balance: False until runtime probe (WiiM-only); see WiiMCapabilities
        - supports_metadata: Whether device supports metadata
        - status_endpoint: Preferred status endpoint path
        - supports_led_switch: True for WiiM class (no HTTP probe); absent for non-WiiM until merge defaults
        - supports_trigger_out: True only for WiiM models with known 12V hardware (Ultra/Pro/Pro Plus)
        - loop_mode_scheme: Set during runtime ``detect_capabilities`` from ``get_device_profile`` merge
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
        # Runtime detection sets this on WiiM via getChannelBalance probe (WiiMCapabilities).
        "supports_channel_balance": False,
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
        # Status LED (LED_SWITCH_SET): enable by device class only. Never probe with LED_SWITCH_SET:0
        # at connect — it turns the LED off (user-visible mutation). See ADR 005 / ADR 016.
        capabilities["supports_led_switch"] = True
        # 12V trigger: known hardware (Ultra / Pro / Pro Plus) only — no HTTP probe/toggle at connect.
        capabilities["supports_trigger_out"] = is_wiim_12v_trigger_model(device_info.model)
        # Display/LCD on/off and brightness (setLightOperationBrightConfig) - WiiM Ultra only
        if is_wiim_ultra(device_info.model):
            capabilities["supports_display_config"] = True
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

    # Protocol/port preference is profile-driven (single source of truth). The per-branch
    # assignments above tune timeouts/feature flags; the device profile is authoritative for
    # which protocol to probe first. This closes the gap where non-legacy LinkPlay devices
    # (Arylic Up2Stream/S10P) kept the HTTPS-first default and cached the slow HTTPS endpoint.
    # See: https://github.com/mjcumming/wiim/issues/248
    profile = get_device_profile(device_info)
    capabilities["protocol_priority"] = list(profile.connection.protocol_priority)

    return capabilities


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
        "s10p",  # S10+ reports model "S10P_WIFI"
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
    if any(arylic_type in model_lower for arylic_type in ["arylic", "up2stream", "s10p"]):
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
