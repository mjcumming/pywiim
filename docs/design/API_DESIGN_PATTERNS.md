# API Design Patterns and Defensive Programming

## Overview

This document captures API design patterns, defensive programming strategies, and implementation details learned from the WiiM integration to ensure robust device communication. **Capability probing** (probe before using optional endpoints) is formalized in **[ADR 003: Capability Probing Before Using Endpoints](adr/003-capability-probing-before-endpoints.md)**. **Connect-time** read-only probes and retries are formalized in **[ADR 016: Connect-Time Capability Probes](adr/016-connect-time-read-only-capability-probes.md)**. **Which features exist for this device** — for optional HTTP API behavior — is defined only by the merged **`WiiMClient.capabilities`** mapping (and `Player` properties that mirror it); see **[ADR 018: Client `capabilities` Dict — Single Source of Truth](adr/018-capabilities-dict-source-of-truth.md)**. Do not document or recommend gating those features on model name alone.

## API Reliability Matrix

### ✅ Universal Endpoints (Always Available)

These endpoints work on **all LinkPlay devices** and form the foundation:

| Endpoint                  | Purpose             | Critical Notes                                                                                   |
| ------------------------- | ------------------- | ------------------------------------------------------------------------------------------------ |
| **`getPlayerStatus`**     | Core playback state | **Most critical - always poll this** ⚠️ **Exception: Audio Pro MkII uses `getStatusEx` instead** |

### ⚠️ WiiM-Enhanced Endpoints (Probe Required)

These endpoints are **WiiM-specific enhancements** that may not exist on pure LinkPlay devices:

| Endpoint          | WiiM Enhancement            | LinkPlay Fallback              | Probe Strategy                            |
| ----------------- | --------------------------- | ------------------------------ | ----------------------------------------- |
| **`getStatusEx`** | Rich device/group info      | Use basic `getStatus`          | Try once, remember result                 |
| **`getMetaInfo`** | Track metadata with artwork | Extract from `getPlayerStatus` | **Critical - many devices don't support** |
| **EQ endpoints**  | Equalizer controls          | None - feature missing         | Disable EQ UI if unsupported              |

### ❌ Highly Inconsistent Endpoints (Use Carefully)

| Endpoint          | Issue                                  | Our Strategy                            |
| ----------------- | -------------------------------------- | --------------------------------------- |
| **`getStatus`**   | **DOESN'T WORK on WiiM devices!**      | Pure LinkPlay only - never rely on this |
| **EQ endpoints**  | Some devices have no EQ support at all | Probe on startup, disable if missing    |
| **`getMetaInfo`** | Missing on many older LinkPlay devices | Always have fallback metadata           |

**🚨 CRITICAL**: `getStatus` (basic LinkPlay endpoint) **does not work** on WiiM devices!

### Base API response shape

All base-layer HTTP requests return a single type: **`ApiResponse(parsed, raw)`**.

- **`parsed`**: `dict | list | None` — the JSON body when the response was valid JSON (object or array).
- **`raw`**: `str | None` — the response body as text when it was not JSON (e.g. `"OK"`, `"unknown command"`), or when the caller needs the raw string.

The base layer parses JSON in one place and **never raises** for non-JSON bodies; only transport failures (timeout, connection error) raise. Callers use `response.parsed` when they need structured data and `response.raw` when they need the body string. This avoids endpoint whitelists and keeps behavior consistent.

## Defensive Programming Patterns

### 1. Capability Probing

Always test endpoint availability on first connection:

```python
class WiiMClient:
    def __init__(self):
        # Capability flags - None means untested
        self._statusex_supported: bool | None = None
        self._metadata_supported: bool | None = None
        self._eq_supported: bool | None = None

    async def probe_capabilities(self):
        """Test endpoint support once on initial connection"""
        # Test WiiM-enhanced device info
        try:
            await self._get_status_ex()
            self._statusex_supported = True
        except WiiMError:
            self._statusex_supported = False

        # Test metadata support (critical!)
        try:
            await self._get_meta_info()
            self._metadata_supported = True
        except WiiMError:
            self._metadata_supported = False
            logger.warning("Device doesn't support getMetaInfo - no track artwork")
```

### 2. Graceful Fallbacks

Always have fallbacks for unreliable endpoints:

```python
async def get_device_info(self) -> dict:
    """Get device info with WiiM enhancement fallback"""
    if self._statusex_supported:
        try:
            return await self._request(API_ENDPOINT_STATUS)
        except WiiMError:
            self._statusex_supported = False  # Remember failure

    # Fallback to basic LinkPlay
    return await self._request(API_ENDPOINT_PLAYER_STATUS)

async def get_track_metadata(self) -> dict:
    """Get track metadata with basic info fallback"""
    if self._metadata_supported:
        try:
            result = await self._request("/httpapi.asp?command=getMetaInfo")
            if result and result.get("metaData"):
                return result["metaData"]
        except WiiMError:
            self._metadata_supported = False  # Disable forever

    # Fallback: Extract from basic player status
    status = await self.get_player_status()
    return {
        "title": status.get("title", "Unknown Track"),
        "artist": status.get("artist", "Unknown Artist"),
        "album": status.get("album", ""),
        # Note: No artwork available in basic status
    }
```

### 3. Never Fail Hard

Missing advanced features shouldn't break core functionality:

```python
async def get_eq_status(self) -> bool:
    """Return True when EQ is on, False otherwise.

    We use EQGetBand only. Its response includes EQStat ("On"/"Off") and
    Name (current preset). EQGetStat fails on some firmware (e.g. WiiM Pro
    Linkplay 4.8) with "unknown command", so we don't use it.
    """
    try:
        response = await self._request(API_ENDPOINT_EQ_GET)  # EQGetBand
        if isinstance(response, dict) and "EQStat" in response:
            return str(response["EQStat"]).lower() == "on"
        return False
    except WiiMError:
        return False
```

**EQ status: protocol vs implementation.** The [WiiM HTTP API v1.2](https://www.wiimhome.com/pdf/HTTP%20API%20for%20WiiM%20Products.pdf) specifies **EQGetStat** for on/off (`{"EQStat":"On"}` or `"Off"`). On some devices (e.g. WiiM Pro, Linkplay 4.8) **EQGetStat** returns plain text `"unknown command"` and does not work. **EQGetBand** works and its response includes **EQStat** and **Name** (current preset), e.g. `{"status":"OK","EQStat":"Off","Name":"Rock","EQBand":[...]}`. We therefore use **EQGetBand only** for `get_eq_status()` and do not call EQGetStat (wiim#165).

## Thin Integration Pattern: Source Management

To keep integrations (like Home Assistant) simple and maintenance-free, `pywiim` takes on the full responsibility for device-specific abstraction and UI-ready formatting.

### 1. Authoritative Hardware Filtering
We don't rely solely on the device's inconsistent `plm_support` bitmask or `input_list`. Instead, we use a central hardware database (`device_capabilities.py`) to filter available sources based on the actual physical hardware of each model. This prevents "phantom" inputs (like USB on a WiiM Pro) from appearing in the UI.

### 2. UI-Ready Formatting
The library is the "UI Master" for source names. `player.available_sources` and `player.source_name` return strings that are ready for display:
- **Acronyms**: Proper capitalization (`USB`, `HDMI`, `DLNA`).
- **Standardization**: Unified naming (e.g., all network variations become "Network").
- **Title Case**: Consistent formatting (e.g., `CoaxIal` → `Coaxial`).
- **Input Suffixes**: Physical inputs use the "In" suffix (e.g., "Optical In", "Line In") for clarity.

For stable programmatic comparisons, `player.source` returns a canonical source id (matching `source_catalog[*]["id"]`).

### 3. Resilient Command Normalization
The `player.set_source(source)` method accepts any logical variation of a source name (Title Case, underscore, hyphen, or no spaces) and handles the mapping to the correct API command internally.

See [SOURCE_ENUMERATION_VS_SELECTION.md](SOURCE_ENUMERATION_VS_SELECTION.md) for detailed implementation details.

## Two-Layer Source System

WiiM devices have a hierarchical source system with enumerable physical inputs and selectable services. See [SOURCE_ENUMERATION_VS_SELECTION.md](SOURCE_ENUMERATION_VS_SELECTION.md) for detailed documentation.

## Group Management API Patterns

### Essential Group Commands

#### Create Master Command
```
setMultiroom:Master
```
- **Purpose**: Makes the current device a multiroom master
- **Target**: Send to the device that should become master

#### Leave Group Command
```
multiroom:SlaveKickout:<slave_ip>
```
- **Purpose**: Removes a slave from the group
- **Target**: Send to the master device's IP
- **Parameters**: `<slave_ip>` - IP address of slave to remove

#### Ungroup Command
```
multiroom:Ungroup
```
- **Purpose**: Disbands the entire group or leaves current group
- **Target**: Send to any device in the group

#### Join Group Command
```
ConnectMasterAp:JoinGroupMaster:eth<master_ip>:wifi0.0.0.0
```
- **Purpose**: Join this device as slave to a master's multiroom group
- **Target**: Send to the **slave device's IP** (using slave's protocol!)
- **Parameters**: `<master_ip>` - IP address of the master device

**🚨 CRITICAL**: Command must be sent **TO the slave device** using **the slave's protocol** (HTTP or HTTPS). Using the master's protocol will cause SSL/connection failures with mixed-protocol devices.

### Group Status Detection

#### Device Role from getStatusEx

```json
{
  "group": "0", // Solo or Master
  "group": "1", // Slave
  "master_uuid": "...", // Present when slave
  "uuid": "...", // Device UUID
  "wmrm_version": "4.2" // WiiM MultiRoom protocol version
}
```

**wmrm_version** indicates the multiroom protocol version:
- **2.0**: Legacy LinkPlay protocol (older devices, Audio Pro Gen 1)
- **4.2**: Current router-based multiroom protocol (WiiM, Audio Pro Gen 2+/W-Gen)

**⚠️ Compatibility**: Devices can only group with matching `wmrm_version` - this is a protocol-level requirement. Devices with version 2.0 cannot join groups with version 4.2 devices.

#### Master's Slaves from getSlaveList

**Correct API Format:**
```json
{
  "slaves": 1, // Integer count (always present)
  "wmrm_version": "4.2",
  "slave_list": [
    // Array of slave objects (when slaves > 0)
    {
      "name": "Master Bedroom",
      "uuid": "FF31F09EFFF1D2BB4FDE2B3F",
      "ip": "192.168.1.116",
      "version": "4.2",
      "type": "WiiMu-A31",
      "channel": 0,
      "volume": 63,
      "mute": 0,
      "battery_percent": 0,
      "battery_charging": 0
    }
  ]
}
```

**Response when no slaves (standalone mode):**
```json
{
  "slaves": 0,
  "wmrm_version": "4.2"
}
```

**Critical Parsing Note:**
- `slaves` is always an integer count, `slave_list` contains the actual slave objects
- Prior implementations incorrectly expected `slaves` to sometimes be a list
- This caused multiroom group detection failures

### Group Role Logic

1. **Slave**: `group == "1"` and has `master_uuid`
2. **Master**: `group == "0"` and `getSlaveList` shows slaves
3. **Solo**: `group == "0"` and no slaves

## Audio Pro Device Considerations

Audio Pro devices (especially MkII generation) have significant API endpoint differences and require special handling. See [DEVICE_VARIATIONS.md](DEVICE_VARIATIONS.md) for comprehensive documentation on vendor-specific variations, endpoint abstraction, and Audio Pro generation differences.

## Best Practices

### DO

- ✅ **Probe capabilities once** - remember results permanently
- ✅ **Use getPlayerStatus as foundation** - universally supported (except Audio Pro MkII)
- ✅ **Implement graceful fallbacks** - for all enhanced features
- ✅ **Log missing capabilities** - for user troubleshooting
- ✅ **Test multiple protocols** - HTTP and HTTPS with fallback ports
- ✅ **Normalize field names** - handle Audio Pro field variations automatically
- ✅ **Send commands to target device** - multiroom join goes TO slave, using slave's protocol

### DO NOT

- ❌ **Assume getMetaInfo works** - many devices don't support it
- ❌ **Require EQ endpoints** - often missing entirely
- ❌ **Use only WiiM API docs** - covers enhanced features only
- ❌ **Fail hard on missing features** - always have fallbacks
- ❌ **Assume HTTP protocol** - Audio Pro MkII+ devices use HTTPS
- ❌ **Expect consistent field names** - Audio Pro uses different field variations
- ❌ **Use master's protocol for slave commands** - each device has its own protocol
- ❌ **Group devices with different wmrm_version** - protocol incompatibility will cause failures

## Timer and Alarm API (WiiM Only)

### Device Support

Alarm clock and sleep timer functionality is **WiiM-specific** and not part of the standard LinkPlay API. Capability detection automatically sets:

```python
capabilities["supports_alarms"] = is_wiim_device
capabilities["supports_sleep_timer"] = is_wiim_device
capabilities["max_alarm_slots"] = 3  # WiiM supports 3 independent alarms
```

### API Documentation

These features are documented in the official WiiM HTTP API specification:
- [WiiM HTTP API PDF](https://www.wiimhome.com/pdf/HTTP%20API%20for%20WiiM%20Mini.pdf) - Section 2.5 (Sleep Timer) and Section 2.6 (Alarm Clock)

### Time Handling

**Critical:** All alarm times use **UTC timezone** per the WiiM API specification. Applications must handle timezone conversion:

```python
# Application handles timezone conversion
from datetime import datetime
import pytz

local_tz = pytz.timezone('America/New_York')
local_time = local_tz.localize(datetime(2025, 1, 17, 7, 30))
utc_time = local_time.astimezone(pytz.UTC)
time_str = utc_time.strftime("%H%M%S")  # Format: HHMMSS

await client.set_alarm(alarm_id=0, trigger=2, operation=1, time=time_str)
```

### Alarm Slot Management

WiiM devices provide 3 independent alarm slots (indices 0-2). Applications can:
- Use slot 0 for single alarm scenarios
- Use all 3 slots for multiple independent alarms
- Track slot usage at application level

### Sleep Timer vs Shutdown

The API endpoint is named `setShutdown`, but it functions as a sleep timer:
- Stops playback after specified seconds
- `0` = immediate shutdown
- `-1` = cancel timer
- Positive value = seconds until playback stops

We name the methods `set_sleep_timer()` / `get_sleep_timer()` for clarity.

### Best Practices

- ✅ Check `capabilities["supports_alarms"]` before using alarm API
- ✅ Check `capabilities["supports_sleep_timer"]` before using sleep timer API
- ✅ Document UTC requirement clearly in user-facing applications
- ✅ Validate alarm_id is 0-2 before calling API
- ✅ Use constants (e.g., `ALARM_TRIGGER_DAILY`) for readability
- ✅ Handle offline devices with `sync_time()` if needed
- ❌ Don't assume these features work on non-WiiM devices
- ❌ Don't convert times to local timezone - API requires UTC
- ❌ Don't use alarm_id > 2 (only 3 slots available)

## Capability Detection and Caching Strategy

### Design Philosophy

The `pywiim` library is **stateless and framework-agnostic**. It does not persist capabilities between sessions. **Applications are responsible for managing capability storage and reuse**.

### Current Implementation

**Library Behavior:**
- Each `WiiMClient` instance has its own in-memory capability cache (per-instance)
- Capabilities are detected automatically on first use if not provided
- Cache is lost when the client instance is destroyed
- Library accepts optional `capabilities` parameter in `__init__` to avoid re-probing

**Key Point**: Creating a new `WiiMClient` instance will probe capabilities again unless you provide them.

### Recommended Design Pattern

**Option 1: Application-Managed Caching (Recommended)**

Applications should detect capabilities once and store them persistently:

```python
# Application code (e.g., Home Assistant integration)
class DeviceManager:
    def __init__(self):
        # Application's persistent storage (config entry, database, etc.)
        self._capabilities_cache: dict[str, dict[str, Any]] = {}
    
    async def get_client(self, host: str, uuid: str) -> WiiMClient:
        """Get or create client with cached capabilities."""
        device_id = f"{host}:{uuid}"
        
        # Check if we have cached capabilities
        capabilities = self._capabilities_cache.get(device_id)
        
        if capabilities:
            # Reuse cached capabilities - no probing needed
            return WiiMClient(host, capabilities=capabilities)
        else:
            # First time - create client, it will probe automatically
            client = WiiMClient(host)
            # After first use, capabilities are detected
            # Store them for next time
            device_info = await client.get_device_info_model()
            await client._detect_capabilities()
            self._capabilities_cache[device_id] = client.capabilities.copy()
            return client
```

**Option 2: Probe on Every Startup (Simple but Slower)**

If you don't need persistent caching, let the library probe each time:

```python
# Simple approach - probe every time
client = WiiMClient("192.168.1.100")
# Capabilities detected automatically on first use
# Accept the ~1-2 second delay on startup
```

**Option 3: Static Detection Only (Fastest, Less Accurate)**

Use static detection (model/firmware-based) without endpoint probing:

```python
from pywiim import WiiMClient, detect_device_capabilities

# Get device info first
client = WiiMClient("192.168.1.100")
device_info = await client.get_device_info_model()

# Static detection (no API calls, instant)
capabilities = detect_device_capabilities(device_info)

# Create new client with static capabilities
client = WiiMClient("192.168.1.100", capabilities=capabilities)
# Note: Static detection may be less accurate than runtime probing
```

### When to Re-Probe Capabilities

**Re-probe when:**
- Firmware version changes (capabilities may change with firmware updates)
- Device model changes (unlikely, but possible if device is replaced)
- User reports missing features (capability detection may have failed)
- After significant time period (firmware may have been updated)

**Don't re-probe when:**
- Same device, same session (use cached capabilities)
- Same device, different application restart (reuse stored capabilities)
- Multiple client instances for same device (share capabilities)

### Capability Storage Recommendations

**For Home Assistant:**
- Store in config entry data (persists across restarts)
- Key: `f"{host}:{uuid}"` or use device UUID
- Update when firmware version changes

**For CLI Tools:**
- Store in local JSON file or user config directory
- Key: device IP or UUID
- Optional: TTL (time-to-live) for automatic re-probing

**For Long-Running Applications:**
- In-memory cache with optional persistence
- Periodic refresh (e.g., once per day)
- Manual refresh option for users

### Library Support

The library provides:

1. **Capability Detection**: `WiiMClient._detect_capabilities()` - Full runtime probing
2. **Static Detection**: `detect_device_capabilities(device_info)` - Fast, model-based
3. **Capability Acceptance**: `WiiMClient(host, capabilities=...)` - Skip probing
4. **Capability Access**: `client.capabilities` - Read detected capabilities

**Example:**
```python
# Detect once, reuse many times
client1 = WiiMClient("192.168.1.100")
await client1._detect_capabilities()  # Probes device
cached_caps = client1.capabilities.copy()

# Reuse in new client instance
client2 = WiiMClient("192.168.1.100", capabilities=cached_caps)
# No probing - instant startup
```

### Best Practice

**Recommended Pattern:**
1. **First connection**: Probe capabilities, store in application's persistent storage
2. **Subsequent connections**: Load from storage, pass to `WiiMClient(..., capabilities=...)`
3. **Periodic refresh**: Re-probe when firmware version changes or after extended period
4. **Error recovery**: If device reports unsupported feature, re-probe capabilities

This gives you:
- ✅ Fast startup (no probing delay)
- ✅ Persistent capabilities (survive restarts)
- ✅ Flexibility (application controls when to probe)
- ✅ Framework-agnostic (library doesn't need to know storage mechanism)

## Audio Output Control API (WiiM Devices Only)

### Device Compatibility

The audio output control API is **WiiM-specific** and not universally supported across LinkPlay devices:

| Vendor | GET Status | SET Mode | Notes |
|--------|------------|----------|-------|
| **WiiM** | ✅ | ✅ | Prefer **`getNewAudioOutputHardwareMode`**; **`getAudioOutputStatus`** is legacy and often **`unknown command`** on Pro (and some Ultra) firmware. |
| **Arylic** | ⚠️ | ❌ | Read-only or not supported |
| **Audio Pro** | ❓ | ❓ | Unknown (needs testing) |

**Tested Devices:**
- ✅ **WiiM Pro** (firmware 4.8.731953): Full support (read via **`getNewAudioOutputHardwareMode`**)
- ⚠️ **Arylic H50** (firmware 4.6.529755): Read-only (GET works, SET returns "unknown command")
- ❌ **Arylic UP2STREAM_AMP_V4** (firmware 4.6.415145): Not supported (returns "unknown command")

### Official WiiM API Mode Numbers

Based on real-world device testing (Issue #160) and official WiiM API documentation:

- **Mode 1**: `AUDIO_OUTPUT_SPDIF_MODE` - Optical/TOSLINK output
- **Mode 2**: `AUDIO_OUTPUT_AUX_MODE` - Line Out/Auxiliary/RCA output (primary line out)
- **Mode 3**: `AUDIO_OUTPUT_COAX_MODE` - Coaxial output
- **Mode 4**: `AUDIO_OUTPUT_BT_MODE` - Bluetooth Out (or Headphone Out on Ultra with source=0)
- **Mode 7**: `AUDIO_OUTPUT_HDMI_MODE` - HDMI ARC output (WiiM Amp Ultra only)
- **Mode 8**: `AUDIO_OUTPUT_USB_MODE` - USB Audio Out (confirmed on WiiM Ultra, Issue #160)
- **Mode 0**: Undocumented but functional on WiiM devices (legacy mode)

**Key Findings:**
- Mode 2 is the official primary line out mode, not mode 0.
- Mode 8 is USB Out (confirmed via real-world testing on WiiM Ultra). The official WiiM API docs
  incorrectly documented this as mode 6; modes 5-7 all revert to mode 4 (headphones) on Ultra.
- Mode 6 is kept in the read map for backward compatibility, but mode 8 is used for setting.

### HTTP Endpoints

WiiM exposes **two different command names** that sometimes return the **same JSON shape** for “current output.” pywiim **always probes `getNewAudioOutputHardwareMode` first**, then falls back to `getAudioOutputStatus` (see `pywiim/capabilities.py`, [wiim#144](https://github.com/mjcumming/wiim/issues/144)).

**Do not confuse** `audiocast` (or similarly named keys) inside **`getStatusEx`** with `audiocast` in the output-status payload below—they are **different endpoints** and **different semantics**.

#### Get current output (preferred on WiiM): `getNewAudioOutputHardwareMode`

```bash
GET https://DEVICE_IP:443/httpapi.asp?command=getNewAudioOutputHardwareMode

# Example response (same field names as legacy read when supported)
{
  "hardware": "2",  # Current hardware mode (1=SPDIF, 2=AUX/line, 3=COAX; more modes on Amp/Ultra)
  "source": "0",    # Bluetooth output path (0=disabled, 1=active)
  "audiocast": "0"  # Audio cast output (0=disabled, 1=active) — see community doc
}
```

**Field meanings (output JSON):**
- `hardware`: Hardware output mode number (string)
- `source`: Bluetooth output state (0=disabled, 1=active)
- `audiocast`: Audio cast output state (0=disabled, 1=active), per device firmware

This read is what the unofficial [wiim-httpapi `openapi.md`](https://github.com/cvdlinden/wiim-httpapi/blob/main/openapi.md) documents under **Audio Output Control**.

#### Legacy read: `getAudioOutputStatus`

```bash
GET https://DEVICE_IP:443/httpapi.asp?command=getAudioOutputStatus
```

On many current WiiM devices (including **WiiM Pro** on tested firmware), this returns plain text **`unknown command`**. Treat it as a **fallback** only; use **`getNewAudioOutputHardwareMode`** for manual `curl` and for first-probe logic.

#### Set Audio Output Mode

```bash
GET https://DEVICE_IP:443/httpapi.asp?command=setAudioOutputHardwareMode:MODE

# Examples
curl -k "https://192.168.1.100:443/httpapi.asp?command=setAudioOutputHardwareMode:1"  # Optical
curl -k "https://192.168.1.100:443/httpapi.asp?command=setAudioOutputHardwareMode:2"  # Line Out
curl -k "https://192.168.1.100:443/httpapi.asp?command=setAudioOutputHardwareMode:3"  # Coax
```

**Note:** Use `-k` or `--insecure` with curl to bypass certificate verification, as WiiM devices use self-signed certificates.

### Arylic Device Behavior

Arylic devices have limited or no support for audio output control:

**Common Failure Responses:**
```bash
# Plain text "unknown command" (not JSON)
$ curl -k "https://192.168.6.50:443/httpapi.asp?command=setAudioOutputHardwareMode:2"
unknown command

# Empty response (Arylic example)
$ curl "http://192.168.6.95:80/httpapi.asp?command=getAudioOutputStatus"
[empty response]

# WiiM Pro: legacy read often fails; use getNewAudioOutputHardwareMode
$ curl -k "https://192.168.1.115:443/httpapi.asp?command=getAudioOutputStatus"
unknown command
```

**Why this matters:**
- Arylic firmware does not implement `setAudioOutputHardwareMode` command
- Some models support reading status but not changing mode
- On **WiiM**, the **supported read command name** is usually **`getNewAudioOutputHardwareMode`**, not the legacy string (see probing order in `pywiim/capabilities.py`).
- Applications should probe for support and hide audio output controls on Arylic devices

### Testing Device Compatibility

```bash
# Preferred on WiiM — same JSON used by pywiim's first probe
curl -k "https://DEVICE_IP:443/httpapi.asp?command=getNewAudioOutputHardwareMode"

# Expected responses:
# ✅ WiiM: {"hardware":"2","source":"0","audiocast":"0"} (values vary)
# ❌ Some WiiM: "unknown command" → try legacy read below (rare if new fails)
# ❌ Arylic: "unknown command" (plain text) or "" (empty)

# Legacy read (may be unknown command on WiiM Pro / some Ultra firmware)
curl -k "https://DEVICE_IP:443/httpapi.asp?command=getAudioOutputStatus"
```

### WiiM Ultra Mode 4 Behavior

The WiiM Ultra uses mode 4 for BOTH Headphone Out and Bluetooth Out, distinguished by the `source` field:

- **Mode 4 + source=0**: **Headphone Out** (physical 3.5mm jack on front panel) ✅
- **Mode 4 + source=1**: **Bluetooth Out** (wireless audio to BT devices) ✅

**Implementation:**
```python
if hardware_mode == 4:
    if device_model == "WiiM Ultra":
        if source == 0:
            return "Headphone Out"
        elif source == 1:
            return "Bluetooth Out"
```

**Setting Headphone Out on Ultra:**
```bash
# 1. Set hardware mode to 4
curl -k https://DEVICE_IP/httpapi.asp?command=setAudioOutputHardwareMode:4

# 2. Ensure Bluetooth is disconnected (source=0)
curl -k https://DEVICE_IP/httpapi.asp?command=disconnectbta2dpsynk
```

**Setting Bluetooth Out on Ultra:**
```bash
# 1. Connect to Bluetooth device (automatically sets source=1)
curl -k https://DEVICE_IP/httpapi.asp?command=connectbta2dpsynk:AA:BB:CC:DD:EE:FF
```

### WiiM Ultra USB Audio Output

- **USB Audio Output**: **Mode 8** (confirmed on WiiM Ultra, Issue #160)
  - Listed in `available_output_modes` as "USB Out"
  - Supported on WiiM Ultra for external DAC connection
  - Full support in pywiim: `AUDIO_OUTPUT_MODE_USB_OUT = 8`
  - **Note**: The official WiiM API docs documented USB as mode 6, but real-world testing
    confirmed it is mode 8. Modes 5-7 all revert to mode 4 (headphones) on Ultra.
  - Mode 6 is kept in the read map for backward compatibility.

### WiiM Amp Ultra HDMI Output

- **HDMI eARC output**: **Mode 7** (confirmed on WiiM Amp Ultra)
  - Listed in `available_output_modes` as "HDMI Out"
  - Supported on **WiiM Amp Ultra only** (not WiiM Ultra)
  - Full support in pywiim: `AUDIO_OUTPUT_MODE_HDMI_OUT = 7`
  - **Note**: WiiM Ultra has HDMI as input only, not output (confirmed via Issue #160)

### WiiM Sound / Sound Lite Speaker Out (wiim #270)

Mode **7** is also **Speaker Out** on WiiM Sound and Sound Lite (`AUDIO_OUTPUT_SPEAKER_MODE`). Confirmed on `WiiM_Sound_Lite_V2`:

| App selection | `getNewAudioOutputHardwareMode` |
| --- | --- |
| Speaker Out | `{"hardware":"7","source":"0","audiocast":"0"}` |
| Bluetooth Out | `{"hardware":"7","source":"1","audiocast":"0"}` |

Bluetooth Out is the `source` field, not a second hardware mode (same pattern as Ultra headphones vs BT on mode 4). `getSoundCardModeSupportList` returns a single `AUDIO_OUTPUT_SPEAKER_MODE` / `"Speaker Out"` row and **does not change** when Bluetooth Out is selected — do not use it as the full output dropdown.

The static map still defaults mode 7 to `"HDMI Out"`. `Player.audio_output_mode` returns `"Speaker Out"` when the hardware catalog lists it.

### Mode 0 Behavior (Defensive Fix for Legacy Devices)

Mode 0 has special handling in pywiim to prevent state bugs on legacy LinkPlay devices:

- Maps to "idle" in `MODE_MAP` but is **NOT** set as a source (Issues #122, #103)
- **Why**: "idle" is a play STATE, not a SOURCE - conceptually wrong to use as source value
- **Affected devices**:
  - **Modern WiiM devices**: Correctly report proper mode values (e.g., mode=31 for Spotify) ✓
  - **Legacy Audio Pro devices**: May report `mode=0` for DLNA/Spotify (Issue #103 confirmed)
  - **WiiM Amp Ultra**: User reported issue but not verified on actual device (Issue #122)
- **Solution**: Parser ignores `mode=0` when setting source, preserving valid source from `vendor` field
- **Impact**: Defensive fix - prevents rare edge case where source could be set to "idle"

**Testing Results**:
- **WiiM Pro (firmware 4.8.731953)**: Reports `mode=31` for Spotify - no bug present ✓
- **Audio Pro (older models)**: Suspected to report `mode=0` based on user reports (Issue #103)

**Example from Issue #103** (Audio Pro device behavior):
```json
{"mode":"2", "status":"play", "vendor":"DLNA"}  // Expected: mode=2 → source="dlna"
```

But legacy Audio Pro devices may report:
```json  
{"mode":"0", "status":"play", "vendor":"DLNA"}  // Edge case: mode=0 ignored, vendor used instead
```

Parser now uses vendor field and ignores mode=0, keeping source="dlna" correct.

### Related Spotify State Issues

**Issue #83** - State desync when controlling from phone (WiiM Amp):
- Shows "Playing" correctly, then immediately flips to "Paused"
- Logs show: `is_playing=True` → `is_playing=False` within milliseconds
- **Root cause**: Integration timing/synchronization issue (not pywiim library)
- State updates arrive out of order when external control used
- Likely related to debouncing logic in integration's state manager
- **Not fixed by mode=0 parser change** - different issue requiring integration work
- May be alternative line out configuration
- Purpose and differences from mode 2 unclear

### Best Practices

**DO:**
- ✅ Check device vendor before offering audio output control
- ✅ Probe `getAudioOutputStatus` on startup to detect support
- ✅ Use mode 2 for "Line Out" selection (official AUX mode)
- ✅ Handle "unknown command" responses gracefully
- ✅ Use HTTPS by default with proper SSL handling

**DO NOT:**
- ❌ Assume audio output API works on all LinkPlay devices
- ❌ Use mode 0 as primary line out (mode 2 is official)
- ❌ Show audio output controls on unsupported devices
- ❌ Fail hard when device returns "unknown command"

## 12V Trigger API (WiiM Ultra / Pro / Pro Plus)

### Device Support

The 12V trigger output allows controlling external amplifiers (e.g. turn on/off with playback). It is supported only on WiiM models that have the physical 12V trigger jack:

| Model        | Support |
|-------------|---------|
| **WiiM Ultra** | ✅ |
| **WiiM Pro**   | ✅ |
| **WiiM Pro Plus** | ✅ |
| **WiiM Mini** | ❌ (no hardware) |
| **Arylic / Audio Pro** | ❌ |

`capabilities["supports_trigger_out"]` is set from **known hardware models** (WiiM Ultra / Pro / Pro Plus and close variants via `is_wiim_12v_trigger_model`) — not via `getTriggeroutStatus` at connect, so we never infer support from OEM stacks that answer the API without real trigger hardware, and verify tools stay read-only for trigger.

### HTTP Endpoints

- **Get status**: `getTriggeroutStatus` → `{"status":0}` (off) or `{"status":1}` (on)
- **Set status**: `setTriggeroutStatus:0` or `setTriggeroutStatus:1` → `{"status":"OK"}`

### Library API

- **Client**: `get_trigger_out_status()` → `bool | None`; `set_trigger_out(on: bool)`; `set_trigger_out_on()`; `set_trigger_out_off()`
- **Player**: Same methods; `supports_trigger_out` property; `trigger_out_on` cached state (updated after get/set and on configuration-tier refresh in `player.refresh()`)

### Refresh cadence

- **`supports_trigger_out`**: static model class at connect ([ADR 016](adr/016-connect-time-read-only-capability-probes.md)) — no connect-time HTTP probe.
- **`statemgr`** refreshes trigger state on **full refresh** or **`PollingStrategy.should_fetch_trigger_out()`** (~60s), same tier as subwoofer ([ADR 019](adr/019-12v-trigger-cache-and-configuration-tier-refresh.md)).
- After **`set_trigger_out()`**, cache updates from the known outcome — no post-set GET ([ADR 002](adr/002-trust-api-after-success.md)).

### Best Practices

- ✅ Check `player.supports_trigger_out` before exposing trigger switch in UI
- ✅ Use `get_trigger_out_status()` to read state; returns `None` if unsupported
- ✅ Integrations read cached `player.trigger_out_on` on coordinator updates; rely on pywiim refresh for external changes
- ❌ Don't assume trigger is available on all WiiM devices (Mini has no jack)

## API Documentation Sources

**Official Documentation**:
- [Arylic LinkPlay API](https://developer.arylic.com/httpapi/) - Core LinkPlay protocol
- [WiiM API PDF](https://www.wiimhome.com/pdf/HTTP%20API%20for%20WiiM%20Products.pdf) - WiiM-specific enhancements
- [OpenAPI Specification](https://github.com/cvdlinden/wiim-httpapi/blob/main/openapi.yaml) - Complete API reference (OpenAPI 3.0 spec)

**OpenAPI Reference**: The [WiiM HTTP API OpenAPI Specification](https://github.com/cvdlinden/wiim-httpapi/blob/main/openapi.yaml) provides a comprehensive, machine-readable reference for all available endpoints, request parameters, and response structures. This is the most complete and up-to-date API documentation available.

