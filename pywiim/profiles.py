"""Device profiles for WiiM and LinkPlay devices.

This module provides a centralized definition of device-specific behaviors,
eliminating scattered conditionals throughout the codebase. Each device type
has a profile that defines:

1. State source preferences (HTTP vs UPnP for each field)
2. Loop mode interpretation (WiiM vs Arylic schemes)
3. Connection requirements (ports, protocols, certificates)
4. Endpoint availability (which API endpoints work)
5. Grouping behavior (WiFi Direct vs router-based)

Usage:
    from pywiim.profiles import get_device_profile

    profile = get_device_profile(device_info)

    # Check state source for a field
    if profile.state_sources.play_state == "upnp":
        # Use UPnP for play_state
        ...

    # Check connection requirements
    if profile.connection.requires_client_cert:
        # Set up mTLS
        ...
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Literal

from .api.firmware import compare_firmware_versions
from .model_names import is_known_wiim_model, is_wiim_ultra
from .normalize import normalize_vendor

# Firmware version patterns for Audio Pro generation detection.
# Use word-boundary–style lookarounds to avoid matching substrings like "420200" or "v1.205".
_MKII_FIRMWARE_RE = r"(?<!\d)1\.5[6-9](?!\d)|(?<!\d)1\.60(?!\d)"
_W_GEN_FIRMWARE_RE = r"(?<!\d)2\.[0-3](?!\d)"

if TYPE_CHECKING:
    from .models import DeviceInfo

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "DeviceProfile",
    "StateSourceConfig",
    "ConnectionConfig",
    "EndpointConfig",
    "GroupingConfig",
    "get_device_profile",
    "PROFILES",
    "detect_vendor",
    "detect_audio_pro_generation",
]


# Type for state source preference
StateSource = Literal["http", "upnp", "latest"]

# Type for loop mode scheme
LoopModeScheme = Literal["wiim", "arylic", "legacy"]


@dataclass(frozen=True)
class StateSourceConfig:
    """Which source is authoritative for each state field.

    Values:
        - "http": HTTP polling is authoritative, UPnP is fallback
        - "upnp": UPnP events are authoritative, HTTP is fallback
        - "latest": Use whichever source has the most recent data

    Most devices work well with HTTP as primary. Audio Pro MkII requires
    UPnP for play_state and volume because HTTP doesn't provide them.
    """

    play_state: StateSource = "http"
    volume: StateSource = "http"
    mute: StateSource = "http"
    position: StateSource = "http"
    duration: StateSource = "http"
    source: StateSource = "http"
    # Metadata is always HTTP-preferred (more complete, less likely to be cleared)
    title: StateSource = "http"
    artist: StateSource = "http"
    album: StateSource = "http"
    image_url: StateSource = "http"


@dataclass(frozen=True)
class ConnectionConfig:
    """Connection and protocol settings for a device type."""

    # Whether device requires mTLS client certificate (Audio Pro MkII)
    requires_client_cert: bool = False

    # Preferred ports in order of preference
    preferred_ports: tuple[int, ...] = (80, 443)

    # Preferred protocols in order of preference
    protocol_priority: tuple[str, ...] = ("http", "https")

    # Network timeout in seconds (some devices need longer)
    response_timeout: float = 5.0

    # Number of retries for failed requests
    retry_count: int = 2


@dataclass(frozen=True)
class EndpointConfig:
    """Which API endpoints are available on this device type."""

    # Status endpoints
    supports_getPlayerStatusEx: bool = True
    supports_getStatusEx: bool = True

    # Metadata and features
    supports_getMetaInfo: bool = True
    supports_getPresetInfo: bool = True
    supports_eq: bool = True
    supports_eq_set: bool = True  # Some devices can read EQ but not set it
    supports_audio_output: bool = True
    supports_led_control: bool = True
    supports_alarms: bool = False  # WiiM only
    supports_sleep_timer: bool = False  # WiiM only

    # Status endpoint path (some devices need getStatusEx instead of getPlayerStatusEx)
    status_endpoint: str = "/httpapi.asp?command=getPlayerStatusEx"

    # Reboot command (Audio Pro devices use StartRebootTime:0 instead of reboot)
    # See: https://github.com/mjcumming/wiim/issues/177
    reboot_command: str = "reboot"


@dataclass(frozen=True)
class GroupingConfig:
    """Multiroom grouping settings for a device type."""

    # Gen1 devices use WiFi Direct, Gen2+ use router-based
    uses_wifi_direct: bool = False


@dataclass(frozen=True)
class DeviceProfile:
    """Complete profile for a device type.

    A profile defines all device-specific behaviors in one place,
    eliminating the need for scattered conditionals throughout the code.
    """

    # Device identification
    vendor: str  # "wiim", "arylic", "audio_pro", "linkplay_generic"
    generation: str | None = None  # "mkii", "w_generation", "original", "gen1", etc.
    display_name: str = ""  # Human-readable name for logging

    # Loop mode interpretation
    loop_mode_scheme: LoopModeScheme = "wiim"

    # Configuration sections
    state_sources: StateSourceConfig = field(default_factory=StateSourceConfig)
    connection: ConnectionConfig = field(default_factory=ConnectionConfig)
    endpoints: EndpointConfig = field(default_factory=EndpointConfig)
    grouping: GroupingConfig = field(default_factory=GroupingConfig)

    def __post_init__(self) -> None:
        """Set display_name if not provided."""
        if not self.display_name:
            name = self.vendor
            if self.generation:
                name = f"{self.vendor}_{self.generation}"
            # Use object.__setattr__ since dataclass is frozen
            object.__setattr__(self, "display_name", name)


# =============================================================================
# Pre-defined Device Profiles
# =============================================================================

# Default WiiM profile - most common case.
# WiiM hardware (Pro/Plus/Ultra/Mini, etc.) exposes the HTTP API on HTTPS:443 and
# does NOT listen on plain HTTP:80 (the port is closed), so HTTPS must be tried first.
# See: https://github.com/mjcumming/wiim/issues/248
PROFILE_WIIM = DeviceProfile(
    vendor="wiim",
    display_name="WiiM",
    loop_mode_scheme="wiim",
    state_sources=StateSourceConfig(
        # Real-time fields should prefer UPnP events for immediate UI updates.
        play_state="upnp",
        volume="upnp",
        mute="upnp",
    ),
    connection=ConnectionConfig(
        preferred_ports=(443, 80),
        protocol_priority=("https", "http"),
        response_timeout=5.0,
    ),
    endpoints=EndpointConfig(
        supports_alarms=True,
        supports_sleep_timer=True,
    ),
    grouping=GroupingConfig(
        uses_wifi_direct=False,
    ),
)

# Arylic devices - different loop mode scheme
PROFILE_ARYLIC = DeviceProfile(
    vendor="arylic",
    display_name="Arylic",
    loop_mode_scheme="arylic",
    state_sources=StateSourceConfig(),  # All HTTP
    connection=ConnectionConfig(
        preferred_ports=(80, 443),
        protocol_priority=("http", "https"),
        response_timeout=5.0,
    ),
    endpoints=EndpointConfig(
        supports_eq=True,
        supports_eq_set=False,  # Many Arylic devices can read but not set EQ
    ),
    grouping=GroupingConfig(
        uses_wifi_direct=False,
    ),
)

# Audio Pro MkII - requires UPnP for state, mTLS for connection
PROFILE_AUDIO_PRO_MKII = DeviceProfile(
    vendor="audio_pro",
    generation="mkii",
    display_name="Audio Pro MkII",
    loop_mode_scheme="arylic",
    state_sources=StateSourceConfig(
        # HTTP doesn't provide these on MkII - must use UPnP
        play_state="upnp",
        volume="upnp",
        mute="upnp",
        # Position/duration can come from either, prefer UPnP for real-time
        position="upnp",
        duration="upnp",
        # Source: prefer UPnP (PlaybackStorageMedium events are reliable on MkII)
        # HTTP mode returns 0 (idle) when nothing is playing, masking the actual input
        source="upnp",
        title="http",
        artist="http",
        album="http",
        image_url="http",
    ),
    connection=ConnectionConfig(
        requires_client_cert=True,
        preferred_ports=(4443, 8443, 443),
        protocol_priority=("https",),  # HTTPS only
        response_timeout=6.0,  # MkII needs longer timeout
        retry_count=3,
    ),
    endpoints=EndpointConfig(
        supports_getPlayerStatusEx=False,  # Use getStatusEx instead
        supports_getMetaInfo=False,
        supports_getPresetInfo=False,
        supports_eq=False,
        supports_eq_set=False,
        status_endpoint="/httpapi.asp?command=getStatusEx",
        reboot_command="StartRebootTime:0",  # Audio Pro uses different reboot command
    ),
    grouping=GroupingConfig(
        uses_wifi_direct=False,
    ),
)

# Audio Pro W-Generation - HTTPS preferred, otherwise similar to WiiM
PROFILE_AUDIO_PRO_W_GENERATION = DeviceProfile(
    vendor="audio_pro",
    generation="w_generation",
    display_name="Audio Pro W-Generation",
    loop_mode_scheme="arylic",
    state_sources=StateSourceConfig(),  # All HTTP
    connection=ConnectionConfig(
        preferred_ports=(443, 8443, 80),
        protocol_priority=("https", "http"),
        response_timeout=4.0,
    ),
    endpoints=EndpointConfig(
        supports_getPlayerStatusEx=True,
        supports_getPresetInfo=True,
        supports_eq=True,
        reboot_command="StartRebootTime:0",  # Audio Pro uses different reboot command
    ),
    grouping=GroupingConfig(
        uses_wifi_direct=False,
    ),
)

# Audio Pro Original (Gen1) - uses WiFi Direct for grouping
PROFILE_AUDIO_PRO_ORIGINAL = DeviceProfile(
    vendor="audio_pro",
    generation="original",
    display_name="Audio Pro Original",
    loop_mode_scheme="arylic",
    state_sources=StateSourceConfig(),  # All HTTP
    connection=ConnectionConfig(
        preferred_ports=(80, 443),
        protocol_priority=("http", "https"),
        response_timeout=5.0,
    ),
    endpoints=EndpointConfig(
        supports_getPlayerStatusEx=True,
        reboot_command="StartRebootTime:0",  # Audio Pro uses different reboot command
    ),
    grouping=GroupingConfig(
        uses_wifi_direct=True,  # Gen1 requires WiFi Direct
    ),
)

# Generic LinkPlay - conservative defaults
PROFILE_LINKPLAY_GENERIC = DeviceProfile(
    vendor="linkplay_generic",
    display_name="LinkPlay Generic",
    loop_mode_scheme="arylic",  # Arylic scheme is more common for generic
    state_sources=StateSourceConfig(),  # All HTTP
    connection=ConnectionConfig(
        preferred_ports=(80, 443, 8080),
        protocol_priority=("http", "https"),
        response_timeout=5.0,
    ),
    endpoints=EndpointConfig(
        # Conservative - probe to determine
        supports_getPlayerStatusEx=True,
        supports_eq=True,
        supports_eq_set=True,
    ),
    grouping=GroupingConfig(
        uses_wifi_direct=False,
    ),
)


# Profile registry - maps profile keys to profile instances
PROFILES: dict[str, DeviceProfile] = {
    "wiim": PROFILE_WIIM,
    "arylic": PROFILE_ARYLIC,
    "audio_pro_mkii": PROFILE_AUDIO_PRO_MKII,
    "audio_pro_w_generation": PROFILE_AUDIO_PRO_W_GENERATION,
    "audio_pro_original": PROFILE_AUDIO_PRO_ORIGINAL,
    "linkplay_generic": PROFILE_LINKPLAY_GENERIC,
}


# =============================================================================
# Profile Detection
# =============================================================================


def detect_vendor(device_info: DeviceInfo) -> str:
    """Detect device vendor from device information.

    Args:
        device_info: Device information

    Returns:
        Normalized vendor string: "wiim", "arylic", "audio_pro", or "linkplay_generic"
    """
    if not device_info.model:
        if device_info.name:
            return normalize_vendor(device_info.name)
        return "linkplay_generic"

    model_lower = device_info.model.lower()
    name_lower = (device_info.name or "").lower()

    # WiiM devices - include known raw model aliases (e.g., "Muzo_Mini")
    if is_known_wiim_model(device_info.model) or "wiim" in model_lower:
        return "wiim"
    if "wiim" in name_lower:
        return "wiim"

    # Arylic devices. Note: the S10+ reports its model as "S10P_WIFI" (a "p", no "+"),
    # so match "s10p" as well. See https://github.com/mjcumming/wiim/issues/248
    if any(arylic in model_lower for arylic in ["arylic", "up2stream", "s10+", "s10p"]):
        return "arylic"
    if "arylic" in name_lower or "up2stream" in name_lower:
        return "arylic"

    # Audio Pro devices
    if any(pro in model_lower for pro in ["audio pro", "addon", "a10", "a15", "a28", "c10"]):
        return "audio_pro"
    if "audio pro" in name_lower or "addon" in name_lower:
        return "audio_pro"

    # Firmware-based fallback for Audio Pro devices with non-standard model strings
    # (e.g. Link 2 model is "LINK 2 Wireless multiroom HiFi player" but firmware starts with "audiopro_")
    if device_info.firmware and "audiopro" in device_info.firmware.lower():
        return "audio_pro"

    return "linkplay_generic"


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

    if any(gen in model_lower for gen in ["mkii", "mk2", "mk ii", "mark ii"]):
        return "mkii"
    if any(gen in model_lower for gen in ["w-", "w series", "w generation", "w gen"]):
        return "w_generation"

    # For known Audio Pro model strings, try firmware to distinguish MkII from W-gen
    if any(model in model_lower for model in ["a10", "a15", "a28", "c10", "audio pro"]):
        if device_info.firmware:
            firmware_lower = device_info.firmware.lower()
            if re.search(_MKII_FIRMWARE_RE, firmware_lower):
                return "mkii"
            if re.search(_W_GEN_FIRMWARE_RE, firmware_lower):
                return "w_generation"
        return "mkii"  # Default to MkII for modern Audio Pro models

    # Firmware-based fallback for Audio Pro devices with non-standard model strings
    # (e.g. Link 2: firmware "audiopro_link2-user 1.56..." → MkII)
    if device_info.firmware:
        firmware_lower = device_info.firmware.lower()
        if re.search(_MKII_FIRMWARE_RE, firmware_lower):
            return "mkii"
        if re.search(_W_GEN_FIRMWARE_RE, firmware_lower):
            return "w_generation"

    return "original"


def _is_gen1_device(device_info: DeviceInfo) -> bool:
    """Check if device is a Gen1 device requiring WiFi Direct.

    Gen1 devices are identified by:
    - wmrm_version == "2.0"
    - firmware < "4.2.8020"

    Args:
        device_info: Device information

    Returns:
        True if device is Gen1 (requires WiFi Direct)
    """
    # Check wmrm_version first (most reliable)
    if device_info.wmrm_version == "2.0":
        return True

    if device_info.wmrm_version == "4.2":
        return False

    # Fall back to firmware version
    if device_info.firmware:
        try:
            # Simple version comparison (works for X.Y.Z format)
            fw = device_info.firmware
            if fw < "4.2.8020":
                return True
        except (ValueError, TypeError):
            pass

    return False


def _wiim_ultra_uses_arylic_loop_mode_scheme(device_info: DeviceInfo) -> bool:
    """WiiM Ultra on firmware 5.2+ reports LinkPlay/Arylic ``loop_mode`` values (pywiim#17)."""
    if not is_wiim_ultra(device_info.model):
        return False
    fw = device_info.firmware
    if not fw or not str(fw).strip():
        return False
    return compare_firmware_versions(str(fw).strip(), "5.2.0") >= 0


def get_device_profile(device_info: DeviceInfo) -> DeviceProfile:
    """Get the appropriate profile for a device.

    This function analyzes device information and returns the matching
    profile. The profile defines all device-specific behaviors.

    Args:
        device_info: Device information from getStatusEx

    Returns:
        DeviceProfile for this device type
    """
    vendor = detect_vendor(device_info)

    # Audio Pro has multiple generations with different profiles
    if vendor == "audio_pro":
        generation = detect_audio_pro_generation(device_info)
        profile_key = f"audio_pro_{generation}"

        if profile_key in PROFILES:
            profile = PROFILES[profile_key]
        else:
            # Unknown generation, use original as fallback
            profile = PROFILES["audio_pro_original"]

        # Check if this is a Gen1 device needing WiFi Direct
        # (might override the generation-based profile)
        if _is_gen1_device(device_info) and not profile.grouping.uses_wifi_direct:
            _LOGGER.debug(
                "Device %s detected as Gen1 (wmrm=%s, fw=%s) - enabling WiFi Direct",
                device_info.name or device_info.model,
                device_info.wmrm_version,
                device_info.firmware,
            )
            # Return a modified profile with WiFi Direct enabled
            return DeviceProfile(
                vendor=profile.vendor,
                generation=profile.generation,
                display_name=profile.display_name,
                loop_mode_scheme=profile.loop_mode_scheme,
                state_sources=profile.state_sources,
                connection=profile.connection,
                endpoints=profile.endpoints,
                grouping=GroupingConfig(
                    uses_wifi_direct=True,
                ),
            )

        return profile

    # Other vendors - direct lookup
    profile = PROFILES.get(vendor, PROFILES["linkplay_generic"])

    if vendor == "wiim" and _wiim_ultra_uses_arylic_loop_mode_scheme(device_info):
        profile = replace(profile, loop_mode_scheme="arylic")
        _LOGGER.debug(
            "Device %s: WiiM Ultra firmware uses Arylic loop_mode scheme (pywiim#17)",
            device_info.name or device_info.model or "?",
        )

    # Check for Gen1 on any device type
    if _is_gen1_device(device_info) and not profile.grouping.uses_wifi_direct:
        _LOGGER.debug(
            "Device %s detected as Gen1 (wmrm=%s, fw=%s) - enabling WiFi Direct",
            device_info.name or device_info.model,
            device_info.wmrm_version,
            device_info.firmware,
        )
        return DeviceProfile(
            vendor=profile.vendor,
            generation="gen1",
            display_name=f"{profile.display_name} (Gen1)",
            loop_mode_scheme=profile.loop_mode_scheme,
            state_sources=profile.state_sources,
            connection=profile.connection,
            endpoints=profile.endpoints,
            grouping=GroupingConfig(
                uses_wifi_direct=True,
            ),
        )

    return profile


def get_profile_for_vendor(
    vendor: str,
    generation: str | None = None,
) -> DeviceProfile:
    """Get profile by vendor and optional generation.

    This is useful when you only have vendor/generation strings,
    not full DeviceInfo.

    Args:
        vendor: Vendor string ("wiim", "arylic", "audio_pro", "linkplay_generic")
        generation: Optional generation string for Audio Pro

    Returns:
        DeviceProfile for this vendor/generation
    """
    if vendor == "audio_pro" and generation:
        profile_key = f"audio_pro_{generation}"
        if profile_key in PROFILES:
            return PROFILES[profile_key]

    return PROFILES.get(vendor, PROFILES["linkplay_generic"])
