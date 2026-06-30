"""Python library for WiiM/LinkPlay device communication.

This library provides a clean, async interface for communicating with WiiM
and LinkPlay-based audio devices via HTTP API and UPnP.

Example:
    ```python
    import asyncio
    from pywiim import WiiMClient

    async def main():
        client = WiiMClient("192.168.1.100")
        device_info = await client.get_device_info_model()
        print(f"Device: {device_info.name}")
        await client.close()

    asyncio.run(main())
    ```
"""

from __future__ import annotations

from .api.constants import (
    ALARM_OP_PLAYBACK,
    ALARM_OP_SHELL,
    ALARM_OP_STOP,
    ALARM_TRIGGER_CANCEL,
    ALARM_TRIGGER_DAILY,
    ALARM_TRIGGER_MONTHLY,
    ALARM_TRIGGER_ONCE,
    ALARM_TRIGGER_WEEKLY,
    ALARM_TRIGGER_WEEKLY_BITMASK,
    GEQ_PLUGIN_URI,
    PEQ_CHANNEL_MODE_LR,
    PEQ_CHANNEL_MODE_STEREO,
    PEQ_DEFAULT_FREQUENCIES,
    PEQ_FREQ_MAX,
    PEQ_FREQ_MIN,
    PEQ_GAIN_MAX,
    PEQ_GAIN_MIN,
    PEQ_MODE_HIGH_SHELF,
    PEQ_MODE_LOW_SHELF,
    PEQ_MODE_OFF,
    PEQ_MODE_PEAK,
    PEQ_PLUGIN_URI,
    PEQ_Q_MAX,
    PEQ_Q_MIN,
    SUBWOOFER_CROSSOVER_MAX,
    SUBWOOFER_CROSSOVER_MIN,
    SUBWOOFER_DELAY_MAX,
    SUBWOOFER_DELAY_MIN,
    SUBWOOFER_LEVEL_MAX,
    SUBWOOFER_LEVEL_MIN,
    SUBWOOFER_PHASE_0,
    SUBWOOFER_PHASE_180,
)
from .api.peq import GraphicEQBand, GraphicEQSettings, PEQBand, PEQPresetInfo, PEQSettings, RoomCorrectionSettings
from .api.subwoofer import SubwooferStatus
from .backoff import BackoffController
from .client import WiiMClient
from .discovery import (
    DiscoveredDevice,
    discover_devices,
    discover_via_ssdp,
    validate_device,
    validate_device_strict,
)
from .exceptions import (
    WiiMConnectionError,
    WiiMError,
    WiiMGroupCompatibilityError,
    WiiMInvalidDataError,
    WiiMRequestError,
    WiiMResponseError,
    WiiMTimeoutError,
)
from .group import Group
from .group_helpers import build_group_state_from_players
from .models import (
    AcousticCapability,
    AudioInputCapability,
    AudioInputCapabilityItem,
    AudioInputEnable,
    AudioInputEnableItem,
    DeviceInfo,
    PlayerStatus,
    Routine,
    RoutineList,
    RoutineStep,
    SoundCardInfo,
    SoundCardModeSupport,
)
from .normalize import normalize_device_info
from .player import NotificationPlaybackResult, Player
from .polling import PollingStrategy, TrackChangeDetector, fetch_parallel
from .profiles import (
    PROFILES,
    DeviceProfile,
    get_device_profile,
    get_profile_for_vendor,
)
from .role import RoleDetectionResult, detect_role
from .state import GroupStateSynchronizer, StateSynchronizer

__version__ = "2.2.19"
__all__ = [
    # Main client
    "WiiMClient",
    # Player and Group
    "Player",
    "NotificationPlaybackResult",
    "Group",
    # Exceptions
    "WiiMError",
    "WiiMRequestError",
    "WiiMResponseError",
    "WiiMTimeoutError",
    "WiiMConnectionError",
    "WiiMInvalidDataError",
    "WiiMGroupCompatibilityError",
    # Models
    "DeviceInfo",
    "PlayerStatus",
    "AudioInputEnableItem",
    "AudioInputEnable",
    "AudioInputCapabilityItem",
    "AudioInputCapability",
    "AcousticCapability",
    "RoutineStep",
    "Routine",
    "RoutineList",
    "SoundCardInfo",
    "SoundCardModeSupport",
    # Discovery
    "DiscoveredDevice",
    "discover_devices",
    "discover_via_ssdp",
    "validate_device",
    "validate_device_strict",
    # Backoff
    "BackoffController",
    # Normalization
    "normalize_device_info",
    # Polling
    "PollingStrategy",
    "TrackChangeDetector",
    "fetch_parallel",
    # Role Detection
    "detect_role",
    "RoleDetectionResult",
    # Group Helpers
    "build_group_state_from_players",
    # State Synchronization
    "StateSynchronizer",
    "GroupStateSynchronizer",
    # Device Profiles
    "DeviceProfile",
    "get_device_profile",
    "get_profile_for_vendor",
    "PROFILES",
    # Alarm Constants (WiiM only)
    "ALARM_TRIGGER_CANCEL",
    "ALARM_TRIGGER_ONCE",
    "ALARM_TRIGGER_DAILY",
    "ALARM_TRIGGER_WEEKLY",
    "ALARM_TRIGGER_WEEKLY_BITMASK",
    "ALARM_TRIGGER_MONTHLY",
    "ALARM_OP_SHELL",
    "ALARM_OP_PLAYBACK",
    "ALARM_OP_STOP",
    # Subwoofer (WiiM Ultra)
    "SubwooferStatus",
    "SUBWOOFER_CROSSOVER_MIN",
    "SUBWOOFER_CROSSOVER_MAX",
    "SUBWOOFER_LEVEL_MIN",
    "SUBWOOFER_LEVEL_MAX",
    "SUBWOOFER_DELAY_MIN",
    "SUBWOOFER_DELAY_MAX",
    "SUBWOOFER_PHASE_0",
    "SUBWOOFER_PHASE_180",
    # PEQ (Parametric EQ) models and constants
    "PEQBand",
    "PEQSettings",
    "PEQPresetInfo",
    "GraphicEQBand",
    "GraphicEQSettings",
    "RoomCorrectionSettings",
    "PEQ_PLUGIN_URI",
    "GEQ_PLUGIN_URI",
    "PEQ_MODE_OFF",
    "PEQ_MODE_LOW_SHELF",
    "PEQ_MODE_PEAK",
    "PEQ_MODE_HIGH_SHELF",
    "PEQ_CHANNEL_MODE_STEREO",
    "PEQ_CHANNEL_MODE_LR",
    "PEQ_FREQ_MIN",
    "PEQ_FREQ_MAX",
    "PEQ_Q_MIN",
    "PEQ_Q_MAX",
    "PEQ_GAIN_MIN",
    "PEQ_GAIN_MAX",
    "PEQ_DEFAULT_FREQUENCIES",
    # Version
    "__version__",
]
