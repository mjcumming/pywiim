# Device Profiles

## Overview

Device profiles provide a centralized way to define device-specific behaviors, eliminating scattered conditionals throughout the codebase. Each device type (WiiM, Arylic, Audio Pro MkII, etc.) has a profile that defines:

- **State source preferences** - Which source (HTTP or UPnP) is authoritative for each state field
- **Connection requirements** - Ports, protocols, timeouts, client certificates
- **Endpoint availability** - Which API endpoints are supported
- **Grouping behavior** - WiFi Direct vs router-based multiroom
- **Loop mode scheme** - How shuffle/repeat values are interpreted

### Why Profiles Were Created

The library experienced a pattern of "fix one thing, break another" during releases. Analysis revealed:

1. **State management complexity** - The `StateSynchronizer` was guessing which source (HTTP vs UPnP) to trust using freshness windows and priority rules. This was error-prone.

2. **Scattered device conditionals** - Code like `if vendor == "audio_pro_mkii"` was spread across multiple files, making it hard to understand what a device needed.

3. **Implicit knowledge** - Device quirks (e.g., "Audio Pro MkII doesn't provide play_state via HTTP") were encoded in logic, not documented in one place.

Profiles solve this by making device behavior **explicit and centralized**.

---

## Architecture

### Profile Components

```python
# pywiim/profiles.py

@dataclass(frozen=True)
class StateSourceConfig:
    """Which source is authoritative for each state field."""
    play_state: str = "http"  # "http" | "upnp" | "latest"
    volume: str = "http"
    mute: str = "http"
    # ... other fields

@dataclass(frozen=True)
class ConnectionConfig:
    """Connection and protocol settings."""
    requires_client_cert: bool = False
    preferred_ports: tuple[int, ...] = (80, 443)
    protocol_priority: tuple[str, ...] = ("http", "https")
    response_timeout: float = 5.0

@dataclass(frozen=True)
class EndpointConfig:
    """Which API endpoints are available."""
    supports_getPlayerStatusEx: bool = True
    supports_getMetaInfo: bool = True
    supports_eq: bool = True
    # ... other endpoints

@dataclass(frozen=True)
class GroupingConfig:
    """Multiroom grouping settings."""
    uses_wifi_direct: bool = False

@dataclass(frozen=True)
class DeviceProfile:
    """Complete profile for a device type."""
    vendor: str
    generation: str | None = None
    loop_mode_scheme: str = "wiim"  # "wiim" | "arylic" | "legacy"
    state_sources: StateSourceConfig
    connection: ConnectionConfig
    endpoints: EndpointConfig
    grouping: GroupingConfig
```

### Pre-defined Profiles

| Profile | Key Characteristics |
|---------|---------------------|
| `PROFILE_WIIM` | HTTP for all state, standard ports, alarms/sleep timer supported |
| `PROFILE_ARYLIC` | HTTP for all state, Arylic loop mode scheme, EQ read-only |
| `PROFILE_AUDIO_PRO_MKII` | **UPnP for play_state/volume/mute/source** (HTTP returns mode=0 when idle), mTLS required, port 4443 |
| `PROFILE_AUDIO_PRO_W_GENERATION` | HTTP for all state, HTTPS preferred |
| `PROFILE_AUDIO_PRO_ORIGINAL` | HTTP for all state, WiFi Direct for grouping |
| `PROFILE_LINKPLAY_GENERIC` | Conservative defaults |

### Profile Detection

Profiles are detected automatically from `DeviceInfo`:

```python
from pywiim.profiles import get_device_profile

profile = get_device_profile(device_info)
# Returns the appropriate profile based on model, vendor, firmware, wmrm_version
```

Detection uses:
1. Model name patterns (WiiM, Arylic, Audio Pro, etc.)
2. Generation detection for Audio Pro (MkII, W-Generation, Original)
3. Gen1 detection via `wmrm_version == "2.0"` or old firmware

---

## Current Integration Status

The profile system is partially integrated. Core functionality is complete; other areas use legacy conditionals.

### Completed

| Area | File | Description |
|------|------|-------------|
| State source selection | `pywiim/state.py` | `StateSynchronizer` uses profile to determine HTTP vs UPnP per field |
| Player profile detection | `pywiim/player/base.py` | Profile auto-detected on first refresh when `device_info` available |
| Profile setting on sync | `pywiim/player/statemgr.py` | Calls `_update_profile_from_device_info()` after device_info fetch |

**How it works:**
1. Player refreshes and fetches `device_info`
2. `_update_profile_from_device_info()` calls `get_device_profile(device_info)`
3. Profile is set on `StateSynchronizer` via `set_profile()`
4. All subsequent state merging uses the profile's source preferences

### Pending (Wait and See)

These areas still use scattered conditionals. They work correctly but are harder to maintain.

| Area | File | Current Approach | Notes |
|------|------|------------------|-------|
| Connection config | `pywiim/capabilities.py` | `detect_device_capabilities()` returns dict | Could use `profile.connection` |
| Loop mode interpretation | `pywiim/api/loop_mode.py` + `get_device_profile` | **`profile.loop_mode_scheme`** merged to `capabilities["loop_mode_scheme"]`; **`resolve_loop_mode_mapping_for_player`** for writes, **`decode_loop_mode_for_player`** for reads with source context | Done (pywiim#17: Ultra 5.2+ → `arylic`; wiim#246: Spotify/WiiM `loop_mode=5`) |
| WiFi Direct detection | `pywiim/api/group.py` | `_needs_wifi_direct_mode()` function | Could use `profile.grouping.uses_wifi_direct` |
| Endpoint probing | `pywiim/capabilities.py` | Runtime probing | Could use `profile.endpoints` as hints |

**Migration approach:** Wait and see. Migrate an area when:
- A bug report reveals the scattered conditionals are causing problems
- Adding a new device type becomes painful without profiles
- Maintenance burden becomes too high

The profile infrastructure is in place; future migrations are incremental.

---

## Usage

### Getting a Profile

```python
from pywiim.profiles import get_device_profile, get_profile_for_vendor

# From device_info (preferred - auto-detects everything)
profile = get_device_profile(device_info)

# From vendor/generation strings (when device_info not available)
profile = get_profile_for_vendor("audio_pro", "mkii")
```

### Checking Profile Settings

```python
# State sources
if profile.state_sources.play_state == "upnp":
    # Use UPnP for play_state on this device
    ...

# Connection requirements
if profile.connection.requires_client_cert:
    # Set up mTLS
    ...

# Grouping behavior
if profile.grouping.uses_wifi_direct:
    # Use WiFi Direct mode for multiroom
    ...

# Loop mode command mapping
from pywiim.api.loop_mode import get_loop_mode_mapping_for_scheme

mapping = get_loop_mode_mapping_for_scheme(profile.loop_mode_scheme)
```

### In StateSynchronizer

The synchronizer automatically uses the profile when set:

```python
# Profile-driven resolution (when profile is set)
sync = StateSynchronizer(profile=profile)
# OR
sync.set_profile(profile)

# For Audio Pro MkII: UPnP is used for play_state
# For WiiM: HTTP is used for play_state
# No manual conflict resolution needed
```

---

## Adding a New Device Type

### Step 1: Understand the Device

Determine:
- What vendor/model/generation?
- Does HTTP provide all state fields, or does UPnP required for some?
- What ports/protocols does it use?
- What endpoints are supported?
- Does it need WiFi Direct for multiroom?

### Step 2: Create the Profile

Add to `pywiim/profiles.py`:

```python
PROFILE_NEW_DEVICE = DeviceProfile(
    vendor="new_vendor",
    generation="gen2",  # if applicable
    display_name="New Device Gen2",
    loop_mode_scheme="wiim",  # or "arylic"
    state_sources=StateSourceConfig(
        play_state="http",  # or "upnp" if HTTP doesn't provide it
        volume="http",
        # ...
    ),
    connection=ConnectionConfig(
        preferred_ports=(80, 443),
        protocol_priority=("http", "https"),
    ),
    endpoints=EndpointConfig(
        supports_eq=True,
        # ...
    ),
    grouping=GroupingConfig(
        uses_wifi_direct=False,
    ),
)

# Add to registry
PROFILES["new_vendor_gen2"] = PROFILE_NEW_DEVICE
```

### Step 3: Update Detection

Update `get_device_profile()` to detect your new device:

```python
def _detect_vendor(device_info: DeviceInfo) -> str:
    # Add detection for new vendor
    if "new_vendor" in model_lower:
        return "new_vendor"
    # ...
```

### Step 4: Add Tests

Add tests to `tests/unit/test_profiles.py`:

```python
def test_new_device_detection(self):
    device_info = DeviceInfo(uuid="test", name="Test", model="New Vendor Speaker")
    profile = get_device_profile(device_info)
    assert profile.vendor == "new_vendor"

def test_new_device_profile_settings(self):
    profile = PROFILES["new_vendor_gen2"]
    assert profile.state_sources.play_state == "http"
    # ...
```

---

## Migration Guide

When migrating an area from scattered conditionals to profiles:

### Example: Migrating Loop Mode

**Before (in `api/loop_mode.py`):**
```python
def get_loop_mode_mapping(vendor: str | None) -> LoopModeMapping:
    if vendor == "wiim":
        return WIIM_LOOP_MODE
    elif vendor in ("arylic", "audio_pro"):
        return ARYLIC_LOOP_MODE
    return WIIM_LOOP_MODE
```

**After (using profile / capabilities):**
```python
from pywiim.api.loop_mode import (
    decode_loop_mode_for_player,
    get_loop_mode_mapping_for_scheme,
    resolve_loop_mode_mapping_for_player,
)

mapping = get_loop_mode_mapping_for_scheme(profile.loop_mode_scheme)
# For writes from a Player (profile overrides capabilities when set):
mapping = resolve_loop_mode_mapping_for_player(player)
# For reads, include source context for transport-specific values:
loop_state = decode_loop_mode_for_player(loop_mode, player)
```

**Caller change:**
```python
# Before
mapping = get_loop_mode_mapping(vendor)

# After, for command writes
mapping = resolve_loop_mode_mapping_for_player(player)
# Or: resolve_loop_mode_mapping(loop_mode_scheme=client.capabilities.get("loop_mode_scheme"), vendor=...)

# After, for status reads
loop_state = decode_loop_mode_for_player(loop_mode, player)
```

---

---

## Endpoint Abstraction

### Problem Statement

Different LinkPlay implementations use different endpoint paths and formats:
- **Vendor Variations**: Arylic, WiiM, Audio Pro may use different endpoint formats
- **Generation Variations**: Audio Pro MkII vs W-Generation vs Original have different endpoint support
- **Firmware Variations**: Different firmware versions may add/remove/modify endpoints
- **Fallback Requirements**: Need to try multiple endpoint variants when primary fails

### Design Pattern: Endpoint Registry with Fallback Chains

We use an **Endpoint Registry** pattern with **Fallback Chains** to handle endpoint variations:

1. **Endpoint Registry**: Maps logical operations to endpoint variants by vendor/generation
2. **Fallback Chains**: Ordered list of endpoints to try when primary fails
3. **Capability-Aware Selection**: Select endpoints based on detected capabilities
4. **Runtime Probing**: Probe endpoints to determine actual availability

### Logical Endpoint Names

Endpoints are identified by logical names, not literal paths:

```python
# Logical endpoint names
ENDPOINT_PLAYER_STATUS = "player_status"  # Get playback status
ENDPOINT_DEVICE_STATUS = "device_status"  # Get device info
ENDPOINT_METADATA = "metadata"  # Get track metadata
```

### Endpoint Registry Structure

Each logical endpoint can have multiple variants:

```python
ENDPOINT_REGISTRY: dict[str, dict[str, list[str]]] = {
    "player_status": {
        "default": [
            "/httpapi.asp?command=getPlayerStatusEx",  # Primary (WiiM, most devices)
            "/httpapi.asp?command=getStatusEx",  # Fallback (Audio Pro MkII)
            "/httpapi.asp?command=getPlayerStatus",  # Legacy fallback
        ],
        "audio_pro_mkii": [
            "/httpapi.asp?command=getStatusEx",  # Primary (MkII doesn't support getPlayerStatusEx)
            "/httpapi.asp?command=getStatus",  # Fallback
        ],
        "audio_pro_w_generation": [
            "/httpapi.asp?command=getPlayerStatusEx",  # Primary
            "/httpapi.asp?command=getStatusEx",  # Fallback
        ],
    },
    "metadata": {
        "default": [
            "/httpapi.asp?command=getMetaInfo",  # Primary
        ],
        "audio_pro_mkii": [],  # Not supported - empty list means unsupported
    },
}
```

The endpoint resolver automatically selects the appropriate chain based on the device profile.

---

## Device Catalog

This section catalogs known device models, their quirks, compatibility issues, and workarounds.

### WiiM Devices

WiiM devices are newer LinkPlay-based devices with enhanced features and better API support.

#### WiiM Pro / Mini / Amp / Ultra
- **Model**: `WiiM Pro`, `WiiM Mini`, `WiiM Amp`, `WiiM Ultra`
- **Firmware**: 4.0+ recommended
- **Features**: Full feature support
- **HTTPS**: Supported (self-signed cert)
- **Client Cert**: Not required
- **Profile**: `PROFILE_WIIM`
- **Known Issues**: None

### Arylic Devices

Arylic devices are LinkPlay-based devices with vendor-specific API variations.

#### Arylic Up2Stream / S10+
- **Model**: `Arylic Up2Stream Amp 2.0/2.1`, `Arylic S10+`
- **Vendor**: `arylic`
- **Profile**: `PROFILE_ARYLIC`
- **Known Issues**:
  - Uses different LED command format (`MCU+PAS+RAKOIT:LED:` instead of `setLED:`)
  - Prefers hyphen format for source names (e.g., "line-in" vs "line_in")
- **Workarounds**:
  - Try Arylic-specific LED commands first, fallback to standard if they fail
  - Normalize source names to hyphen format for Arylic devices

### Audio Pro Devices

Audio Pro devices have **three generations** with distinct capabilities. See [Audio Pro Generations](#audio-pro-generations) for details.

#### Audio Pro Addon C5/C10 (Original)
- **Model**: `Addon C5` or `Addon C10`
- **Generation**: `original`
- **Profile**: `PROFILE_AUDIO_PRO_ORIGINAL`
- **Features**: Basic LinkPlay features, limited endpoint support
- **Known Issues**: May not support getMetaInfo, limited EQ support

#### Audio Pro Addon C5A/C10A (W-Generation)
- **Model**: `Addon C5A` or `Addon C10A`
- **Generation**: `w_generation`
- **Profile**: `PROFILE_AUDIO_PRO_W_GENERATION`
- **Features**: Enhanced support compared to original
- **HTTPS**: Supported (self-signed cert)

#### Audio Pro Addon C5 MkII
- **Model**: `Addon C5 MkII`, `A10`, `A15`, `A28`, `C10` (with MkII firmware)
- **Generation**: `mkii`
- **Profile**: `PROFILE_AUDIO_PRO_MKII`
- **Features**: Very limited support - **significantly different endpoints**
- **HTTPS**: Required (port 4443)
- **Client Cert**: **REQUIRED** (mTLS)
- **Critical**: HTTP does NOT provide play_state or volume - must use UPnP (profile handles this)

---

## API Endpoint Compatibility

### getStatusEx
- **WiiM Devices**: ✅ Supported
- **Arylic Devices**: ✅ Supported
- **Audio Pro MkII**: ✅ Supported (preferred over getPlayerStatusEx)
- **Audio Pro W-Generation**: ✅ Supported
- **Notes**: Core endpoint, always available

### getPlayerStatusEx
- **WiiM Devices**: ✅ Supported
- **Arylic Devices**: ✅ Supported
- **Audio Pro MkII**: ❌ Not supported (use getStatusEx)
- **Audio Pro W-Generation**: ✅ Supported
- **Notes**: Enhanced status endpoint, not available on all devices

### getMetaInfo
- **WiiM Devices**: ✅ Supported
- **Arylic Devices**: ⚠️ May not be supported
- **Audio Pro MkII**: ⚠️ Varies by firmware/model (probe at runtime)
- **Audio Pro W-Generation**: ⚠️ May not be supported
- **Notes**: Metadata endpoint, gracefully handle 404/"unknown command"

### EQ Endpoints
- **WiiM Devices**: ✅ Supported
- **Arylic Devices**: ⚠️ Read-only (GET works, SET returns "unknown command")
- **Audio Pro MkII**: ❌ Not supported
- **Audio Pro W-Generation**: ⚠️ Limited support

### Preset Endpoints
- **WiiM Devices**: ✅ Supported (6-20 slots, varies by model/firmware)
- **Arylic Devices**: ⚠️ May not be supported
- **Audio Pro MkII**: ❌ Not supported (getPresetInfo returns 404)
- **Audio Pro W-Generation**: ⚠️ May not be supported

---

## Protocol Support

### HTTP
- **WiiM Devices**: ✅ Supported (port 80)
- **Arylic Devices**: ✅ Supported (port 80)
- **Audio Pro MkII**: ✅ Supported (fallback, prefer HTTPS)
- **Audio Pro W-Generation**: ✅ Supported (port 80)

### HTTPS
- **WiiM Devices**: ✅ Supported (self-signed cert, port 443)
- **Arylic Devices**: ✅ Supported (self-signed cert, port 443)
- **Audio Pro MkII**: ✅ Required (port 4443, requires client cert)
- **Audio Pro W-Generation**: ✅ Supported (self-signed cert, port 443)

### UPnP/DLNA
- **All Devices**: ✅ Supported
- **Notes**: Real-time event subscriptions, preferred for volume/play state on Audio Pro MkII

---

## Related Documentation

- **[ARCHITECTURE_DATA_FLOW.md](ARCHITECTURE_DATA_FLOW.md)** - State synchronization design (profiles used for source selection)
- **[LESSONS_LEARNED.md](LESSONS_LEARNED.md)** - Key design requirements
- **[API_DESIGN_PATTERNS.md](API_DESIGN_PATTERNS.md)** - API reliability and defensive programming
