"""Typed Pydantic models for WiiM API payloads.

- Only fields currently used by the library are included.
- Additional keys can be added incrementally as needed.
- Field aliases match the WiiM API payload keys for seamless parsing.
- Models are designed for forward compatibility and robust validation.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

from .state import normalize_play_state

__all__ = [
    "DeviceInfo",
    "PlayerStatus",
    "SlaveInfo",
    "MultiroomInfo",
    "TrackMetadata",
    "EQInfo",
    "PollingMetrics",
    "GroupDeviceState",
    "GroupState",
    "DeviceGroupInfo",
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
]


class _WiimBase(BaseModel):
    """Base class with permissive extra handling for future-proofing.

    Allows unknown fields (extra="allow") and supports population by field name or alias.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class DeviceInfo(_WiimBase):
    """Subset of *getStatusEx* payload required by the library.

    Field aliases correspond to WiiM API keys (e.g., 'DeviceName', 'MAC').
    Only a subset of fields is included; extend as needed.
    """

    uuid: str | None = None
    name: str | None = Field(None, alias="DeviceName")
    model: str | None = Field(None, alias="project")
    firmware: str | None = None
    mac: str | None = Field(None, alias="MAC")
    ip: str | None = None

    # Extended attributes referenced elsewhere
    release_date: str | None = Field(None, alias="Release")  # Firmware release date
    hardware: str | None = None  # Hardware revision/model
    wmrm_version: str | None = None  # Wiim multiroom version
    mcu_ver: str | None = None  # MCU firmware version
    dsp_ver: str | None = None  # DSP firmware version
    preset_key: int | None = None  # Preset key index
    group: str | None = None  # Group name or ID
    master_uuid: str | None = None  # UUID of group master
    master_ip: str | None = None  # IP of group master
    version_update: str | None = Field(None, alias="VersionUpdate")  # Available update version
    latest_version: str | None = Field(None, alias="NewVer")  # Latest firmware version
    input_list: list[str] | None = Field(
        None, alias="InputList"
    )  # Available input sources from device (matches HA integration)
    plm_support: str | int | None = Field(
        None, alias="plm_support"
    )  # Bitmask for physical input sources (plm_support from getStatusEx)
    ssid: str | None = Field(None, alias="ssid")  # WiFi SSID (needed for WiFi Direct multiroom mode)
    wifi_channel: int | None = Field(None, alias="WifiChannel")  # WiFi channel (needed for WiFi Direct multiroom mode)

    # ---------------- Computed Properties (Multiroom) ----------------

    @property
    def needs_wifi_direct_multiroom(self) -> bool:
        """True if this device requires WiFi Direct mode for multiroom grouping.

        Devices with firmware < 4.2.8020 use WiFi Direct mode (older LinkPlay protocol).
        Modern devices (firmware >= 4.2.8020) use router-based mode.

        This matches the detection logic from the original LinkPlay integration.
        """
        if not self.firmware:
            return False  # Unknown firmware, assume modern

        from .api.firmware import compare_firmware_versions

        return compare_firmware_versions(self.firmware, "4.2.8020") < 0

    # ---------------- Validators ----------------

    @field_validator("input_list", mode="before")
    @classmethod
    def _normalize_input_list(cls, v: list[str] | str | None) -> list[str] | None:  # noqa: D401
        """Normalize input_list to always be a list of strings.

        Handles cases where API returns:
        - List of strings: ["wifi", "bluetooth"]
        - Comma-separated string: "wifi,bluetooth,line_in"
        - None or empty: None

        Note: This matches how the Home Assistant integration handles input_list.
        The HA integration successfully parses InputList from getStatusEx responses.
        """
        if v is None:
            return None
        if isinstance(v, str):
            # Handle comma-separated string
            if not v.strip():
                return None
            return [item.strip() for item in v.split(",") if item.strip()]
        if isinstance(v, list):
            # Ensure all items are strings
            return [str(item).strip() for item in v if item]
        return None

    @classmethod
    def model_validate(cls, obj: dict[str, Any], **kwargs) -> DeviceInfo:
        """Override to handle multiple field name variations for input_list.

        The API may return InputList, inputList, input_list, or inputlist.
        This matches how the Home Assistant integration handles the field.
        """
        # Check for various input_list field name variations (matches HA integration)
        if isinstance(obj, dict):
            input_list_value = None
            for key in ["InputList", "inputList", "input_list", "inputlist"]:
                if key in obj:
                    input_list_value = obj[key]
                    break

            # If we found it with a different key, normalize it
            if input_list_value is not None:
                # Remove all variations and add back as InputList (our alias)
                for key in ["InputList", "inputList", "input_list", "inputlist"]:
                    obj.pop(key, None)
                obj["InputList"] = input_list_value

        return super().model_validate(obj, **kwargs)


class PlayerStatus(_WiimBase):
    """Subset of *getPlayerStatusEx* payload required by the library.

    Includes playback state, volume, source, position, metadata, and device details.
    Field aliases correspond to WiiM API keys.
    """

    play_state: Literal["play", "pause", "stop", "idle", "buffering"] | None = Field(None, alias="play_status")
    volume: int | None = Field(None, ge=0, le=100, alias="vol")
    mute: bool | None = Field(None, alias="mute")

    # Source / mode
    source: str | None = None  # e.g. "spotify"
    mode: str | None = Field(None, alias="mode")

    # Position / duration
    position: int | None = Field(None, alias="position")  # seconds
    seek: int | None = None  # Some firmwares use "seek"
    duration: int | None = Field(None, alias="duration")  # seconds

    # Metadata & artwork
    title: str | None = Field(None, alias="Title")
    artist: str | None = Field(None, alias="Artist")
    album: str | None = Field(None, alias="Album")

    # Album / track artwork (populated by coordinator)
    entity_picture: str | None = None  # Standard HA key used by media-player
    cover_url: str | None = None  # Alternative field used elsewhere

    # Misc device / stream details
    eq_preset: str | None = Field(None, alias="eq")
    wifi_rssi: int | None = Field(None, alias="RSSI")
    wifi_channel: int | None = Field(None, alias="WifiChannel")
    loop_mode: int | None = Field(None, alias="loop_mode")
    play_mode: str | None = Field(None, alias="play_mode")
    codec: str | None = None  # Audio codec (e.g., "flac", "mp3", "aac")

    # Shuffle and repeat can come from different API fields depending on firmware
    repeat: str | None = Field(None, alias="repeat")
    shuffle: str | None = Field(None, alias="shuffle")

    # Queue/playlist information
    queue_count: int | None = Field(None, alias="plicount")  # Total tracks in queue
    queue_position: int | None = Field(None, alias="plicurr")  # Current track position in queue

    # Group/multiroom fields (sometimes in status payload)
    group: str | None = None
    master_uuid: str | None = None
    master_ip: str | None = None
    uuid: str | None = None

    # Internal flags – allow underscore alias via extra="allow"
    _multiroom_mode: bool | None = PrivateAttr(default=None)

    # ---------------- Validators ----------------

    # Keep source casing as-is for proper UI display
    # (Comparisons should use case-insensitive logic where needed)
    @field_validator("source", mode="before")
    @classmethod
    def _normalize_source(cls, v: str | None) -> str | None:  # noqa: D401
        return v if isinstance(v, str) else v

    # Normalize play_state using standard normalization (handles "playing"→"play", "paused"→"pause", etc.)
    @field_validator("play_state", mode="before")
    @classmethod
    def _normalize_play_state(cls, v: str | None) -> str | None:  # noqa: D401
        return normalize_play_state(v)

    # Handle duration field - convert 0 to None for streaming services
    @field_validator("duration", mode="before")
    @classmethod
    def _normalize_duration(cls, v: int | None) -> int | None:  # noqa: D401
        if v == 0:
            return None  # Streaming services report 0 duration - treat as unknown
        return v

    # Handle eq field - convert dictionary to string or None
    @field_validator("eq_preset", mode="before")
    @classmethod
    def _normalize_eq_preset(cls, v: str | dict | None) -> str | None:  # noqa: D401
        if isinstance(v, dict):
            # If it's a dictionary like {'eq_enabled': False}, return None
            return None
        return v


class SlaveInfo(BaseModel):
    """Represents a slave device in a multiroom group."""

    uuid: str | None = None
    ip: str  # IP address of the slave device
    name: str  # Display name of the slave device


class MultiroomInfo(BaseModel):
    """Represents multiroom group information and role."""

    role: Literal["master", "slave", "solo"]
    slave_list: list[SlaveInfo] = []


class TrackMetadata(_WiimBase):
    """Normalized track metadata returned by metadata helper.

    Includes title, artist, album, artwork, and audio quality information.
    """

    title: str | None = None
    artist: str | None = None
    album: str | None = None
    entity_picture: str | None = None
    cover_url: str | None = None

    # Audio quality fields from getMetaInfo response
    sample_rate: int | None = None
    bit_depth: int | None = None
    bit_rate: int | None = None


class EQInfo(_WiimBase):
    """Represents equalizer state & current preset."""

    eq_enabled: bool | None = None
    eq_preset: str | None = None


class AudioInputEnableItem(_WiimBase):
    """One entry from WiiM ``getAudioInputEnable``."""

    mode: str
    enable: bool

    @field_validator("enable", mode="before")
    @classmethod
    def _normalize_enable(cls, v: bool | int | str) -> bool:
        """Normalize WiiM 0/1-ish enable flags to bool."""
        if isinstance(v, bool):
            return v
        if isinstance(v, int):
            return v == 1
        if isinstance(v, str):
            return v.strip().lower() in {"1", "true", "on", "yes", "enabled"}
        return False


class AudioInputEnable(_WiimBase):
    """Payload from WiiM ``getAudioInputEnable``."""

    version: str | None = Field(None, alias="ver")
    audio_input: list[AudioInputEnableItem] = Field(default_factory=list, alias="audioInput")


class AudioInputCapabilityItem(_WiimBase):
    """One entry from WiiM ``getAudioInputCapbility``.

    The command name is misspelled in firmware ("Capbility"). It returns source
    modes that the device can expose, without the per-input enable flag returned
    by ``getAudioInputEnable``.
    """

    mode: str


class AudioInputCapability(_WiimBase):
    """Payload from WiiM ``getAudioInputCapbility``."""

    version: str | None = Field(None, alias="ver")
    audio_input: list[AudioInputCapabilityItem] = Field(default_factory=list, alias="audioInput")


class AcousticCapability(_WiimBase):
    """Read-only acoustic capability payload from WiiM ``GetAcousticCapability``.

    The endpoint is broad and firmware-shaped. pywiim keeps feature blocks as
    dictionaries for now so callers can inspect GEQ/PEQ/RC/OutputDelay data
    without locking a premature high-level API.
    """

    version: str | None = Field(None, alias="Version")
    geq: dict[str, Any] | None = Field(None, alias="GEQ")
    peq: dict[str, Any] | None = Field(None, alias="PEQ")
    room_correction: dict[str, Any] | None = Field(None, alias="RC")
    headphone_eq: dict[str, Any] | None = Field(None, alias="HeadphoneEQ")
    sub_lpf: dict[str, Any] | None = Field(None, alias="SubLPF")
    evaluation: dict[str, Any] | None = Field(None, alias="Evaluation")
    eq_block: dict[str, Any] | None = Field(None, alias="EQBlock")
    output_delay: dict[str, Any] | None = Field(None, alias="OutputDelay")


class RoutineStep(_WiimBase):
    """One step inside a WiiM routine."""

    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class Routine(_WiimBase):
    """A WiiM routine from ``getAllRoutines``."""

    id: str
    name: str | None = None
    index: int | None = None
    create_date: str | None = Field(None, alias="createDate")
    update_date: str | None = Field(None, alias="updateDate")
    steps: list[RoutineStep] = Field(default_factory=list)


class RoutineList(_WiimBase):
    """Payload from WiiM ``getAllRoutines``."""

    routines: list[Routine] = Field(default_factory=list)


class SoundCardInfo(_WiimBase):
    """Nested sound-card details from ``getSoundCardModeSupportList``."""

    card_name: str | None = Field(None, alias="cardName")
    dev_name: str | None = Field(None, alias="devName")
    card_id: str | None = Field(None, alias="cardId")
    hifi_src_version: str | None = Field(None, alias="HiFiSRCVersion")
    support_digital_filter: bool | None = Field(None, alias="supportDigitalFilter")
    support_vrms_change: bool | None = Field(None, alias="supportVrmsChange")
    support_sample_rate_switch_latency: bool | None = Field(None, alias="supportSampleRateSwitchLatency")
    coexist_mode: list[str] | None = Field(None, alias="coexistMode")
    channel_support_list: list[int] | None = Field(None, alias="channelSupportList")
    bit_depth_support_list: list[int] | None = Field(None, alias="bitDepthSupportList")
    format_support_list: list[str] | None = Field(None, alias="formatSupportList")
    sample_rate_support_list: list[int] | None = Field(None, alias="sampleRateSupportList")

    @field_validator(
        "support_digital_filter", "support_vrms_change", "support_sample_rate_switch_latency", mode="before"
    )
    @classmethod
    def _normalize_optional_bool(cls, v: bool | int | str | None) -> bool | None:
        """Normalize optional 0/1-ish support flags."""
        if v is None:
            return None
        if isinstance(v, bool):
            return v
        if isinstance(v, int):
            return v == 1
        if isinstance(v, str):
            return v.strip().lower() in {"1", "true", "on", "yes", "supported"}
        return None


class SoundCardModeSupport(_WiimBase):
    """One output mode entry from ``getSoundCardModeSupportList``.

    The endpoint has an ``index`` field, but field reports show it should not be
    treated as the stable output identity. Use ``mode`` as identity.
    """

    index: int | None = None
    mode: str
    sound_card: SoundCardInfo | None = Field(None, alias="soundCard")


class PollingMetrics(BaseModel):
    """Diagnostics about the most recent polling cycle."""

    interval: float  # seconds
    is_playing: bool
    api_capabilities: dict[str, bool | None]


class GroupDeviceState(BaseModel):
    """Individual device state within a group.

    Represents the state of a single device (master or slave) in a group,
    including volume, mute, playback state, and timestamps for freshness tracking.
    """

    host: str  # Device hostname or IP
    role: Literal["master", "slave"]
    volume: float | None = None  # 0.0-1.0
    mute: bool | None = None
    play_state: str | None = None
    position: int | None = None  # seconds
    duration: int | None = None  # seconds
    source: str | None = None
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    last_updated: float | None = None  # Unix timestamp


class GroupState(BaseModel):
    """Complete group state (master + all slaves).

    Represents the synchronized state of a multiroom group, including
    individual device states and aggregated group-level state.
    """

    master_host: str
    slave_hosts: list[str] = []

    # Individual device states
    master_state: GroupDeviceState
    slave_states: list[GroupDeviceState] = []

    # Aggregated group state (from master)
    play_state: str | None = None  # Master's play state (synced to all)
    position: int | None = None  # Master's position (synced to all)
    duration: int | None = None  # Master's duration
    source: str | None = None  # Master's source
    title: str | None = None  # Master's metadata
    artist: str | None = None
    album: str | None = None

    # Group volume/mute (aggregated)
    volume_level: float | None = None  # MAX volume of any device
    is_muted: bool | None = None  # ALL devices muted

    # Metadata
    created_at: float | None = None  # Unix timestamp
    last_updated: float | None = None  # Unix timestamp


class DeviceGroupInfo(BaseModel):
    """Device's view of its group membership.

    Represents what a device knows about its group membership, including
    role, master info, and slave list (if master).

    Note on API limitations:
        - For **master** devices: All fields are populated.
        - For **slave** devices: The WiiM API only provides `master_uuid`,
          NOT `master_ip`. Therefore `master_host` will typically be None
          for slaves. Use the Player.group object to access the master's
          IP when working with grouped players.
        - For **solo** devices: master_* fields are None, slave_* are empty.

    Note on WiFi Direct multiroom (older LinkPlay devices):
        - Slaves join master's internal network (10.10.10.x) and become
          unreachable from the main LAN.
        - Use `slave_uuids` for matching slaves by UUID when IP-based
          matching fails (slave_hosts contains internal 10.10.10.x IPs).
    """

    role: Literal["solo", "master", "slave"]
    master_host: str | None = None  # Master IP (always set for master, often None for slave - API limitation)
    master_uuid: str | None = None  # Master UUID (if slave or master)
    slave_hosts: list[str] = []  # Slave IPs (if master) - may be internal 10.10.10.x for WiFi Direct
    slave_uuids: list[str] = []  # Slave UUIDs (if master) - for UUID-based matching
    slave_count: int = 0  # Number of slaves (if master)
