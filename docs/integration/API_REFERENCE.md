# API Reference

Complete API reference for the `pywiim` library.

## Table of Contents

- [WiiMClient](#wiimclient)
  - [Read-only WiiM discovery helpers](#read-only-wiim-discovery-helpers)
- [Player](#player)
- [Models](#models)
- [Exceptions](#exceptions)
- [Group Object](#group-object)
- [Usage Examples](#usage-examples)
- [Output Selection](#output-selection-hardware--bluetooth)

## WiiMClient

Low-level HTTP client for device communication. **Most users should use the `Player` class instead**, which provides state caching, convenient properties, and a higher-level API.

The client is primarily used internally by the Player class, but may be accessed for advanced use cases via `player.client`.

### Initialization

```python
from pywiim import WiiMClient

client = WiiMClient(
    host="192.168.1.100",
    port=80,                    # Optional, default: 80
    timeout=5.0,                # Optional, default: 5.0
    ssl_context=None,           # Optional, for advanced use
    session=None,               # Optional, shared aiohttp session
    capabilities=None,          # Optional, pre-detected capabilities
)
```

### Properties

- `host: str` - Device hostname or IP address
- `base_url: str | None` - Base URL used for last successful request
- `capabilities: dict[str, Any]` - Device capabilities dictionary

### Methods

#### Connection Management

```python
async def close() -> None:
    """Close the client and clean up resources."""
```

#### Device Information

```python
async def get_device_info() -> dict[str, Any]:
    """Get device information as dictionary."""

async def get_device_info_model() -> DeviceInfo:
    """Get device information as Pydantic model."""

async def get_firmware_version() -> str:
    """Get device firmware version."""

async def get_mac_address() -> str:
    """Get device MAC address."""
```

#### Player Status

```python
async def get_player_status() -> dict[str, Any]:
    """Get player status with automatic capability detection."""

async def get_player_status_model() -> PlayerStatus:
    """Get player status as Pydantic model."""
```

### Read-only WiiM discovery helpers

These helpers expose WiiM-specific endpoints discovered from app traffic and
documented in [WiiM Discovered Read-Only APIs](../design/WIIM_DISCOVERED_APIS.md).
On WiiM, `get_mode_rename()` and `get_audio_input_enable()` overlay the source
catalog (custom labels and hidden inputs). `get_sound_card_mode_support_list()`
is diagnostic only — it does not populate `available_output_modes`.

Unsupported endpoints return `None` or an empty list.

```python
async def get_audio_input_enable() -> AudioInputEnable | None:
    """Get WiiM input enablement metadata from getAudioInputEnable."""

async def get_mode_rename() -> dict[str, str] | None:
    """Get WiiM user-renamed source labels from getModeRename."""

async def get_acoustic_capability() -> AcousticCapability | None:
    """Get WiiM acoustic capability blocks from GetAcousticCapability."""

async def get_all_routines() -> RoutineList | None:
    """Get WiiM routine metadata from getAllRoutines."""

async def get_sound_card_mode_support_list() -> list[SoundCardModeSupport]:
    """Get WiiM output sound-card support metadata."""
```

Important: `getModeRename` labels are display metadata, not stable source IDs.
`getSoundCardModeSupportList` entries should be keyed by `mode`; the endpoint's
`index` field is not known to match output read/write mode integers.

## Player

High-level player interface with state caching and convenient properties.

> **⚠️ CRITICAL for Integrations: Do NOT call `refresh()` manually in entity methods or after commands!**  
> The library handles state updates automatically via callbacks and UPnP events.  
> **Only the coordinator should call `refresh()` on schedule** (every 5-10 seconds) to catch external changes.  
> See [When to Use `refresh()`](#when-to-use-refresh) below for details.

### Initialization

```python
from pywiim import Player, WiiMClient

client = WiiMClient("192.168.1.100")
player = Player(client)

# Initial state fetch (one-time, for scripts without polling)
await player.refresh()  # Only needed for one-off scripts, not in integrations
```

#### Optional Callbacks

```python
# Full initialization with all callbacks (for integrations like Home Assistant)
player = Player(
    client,
    upnp_client=upnp_client,              # UPnP client for queue/events
    on_state_changed=callback_fn,         # Called on state changes
    player_finder=find_player_by_host,    # For automatic group linking
    all_players_finder=get_all_players,   # For WiFi Direct role inference
)
```

| Parameter | Type | Purpose |
|-----------|------|---------|
| `client` | `WiiMClient` | Required - HTTP API client |
| `upnp_client` | `UpnpClient \| None` | Optional - UPnP for queue management and events |
| `on_state_changed` | `Callable[[], None] \| None` | Optional - Callback when state changes |
| `player_finder` | `Callable[[str], Player \| None] \| None` | Optional - Find Player by host/IP for group linking |
| `all_players_finder` | `Callable[[], list[Player]] \| None` | Optional - Get all Players for WiFi Direct multiroom support |

**WiFi Direct Multiroom Support:**

Legacy LinkPlay devices (firmware < 4.2.8020) use WiFi Direct multiroom where slaves:
- Join the master's internal WiFi Direct network and get 10.10.10.x IP addresses
- Are no longer reachable from the main LAN at their original IPs
- Report `group="0"` (solo) when queried because they don't know they're in a group

pywiim handles this automatically when `all_players_finder` is provided:

1. **Master linking slaves**: When the master's `getSlaveList` returns 10.10.10.x IPs, pywiim:
   - First tries `player_finder(ip)` (fails for internal IPs)
   - Then searches `all_players_finder()` results by UUID to find the matching Player

2. **Slave role detection**: pywiim uses `all_players_finder` to check if any known master lists this device as a slave, enabling correct role detection.

```python
# Example for Home Assistant integration
# Only IP lookup is required - pywiim handles UUID matching internally
player = Player(
    client,
    player_finder=lambda host: player_registry.get(host),  # IP lookup only
    all_players_finder=lambda: list(player_registry.values()),  # Required for WiFi Direct
)
```

### Properties

#### Device Identity & Connection

```python
player.name               # str | None - Device name (e.g., "Living Room")
player.model              # str | None - Raw project model (e.g., "WiiM_Pro_with_gc4a")
player.model_name         # str | None - Friendly model name (e.g., "WiiM Pro")
player.firmware           # str | None - Firmware version
player.firmware_update_available  # bool - True if update is available and ready
player.latest_firmware_version    # str | None - Latest available firmware version
player.mac_address        # str | None - MAC address
player.uuid               # str | None - Device UUID
player.host               # str - IP/hostname
player.port               # int - Port number
player.discovered_endpoint  # str | None - Full endpoint URL (e.g., "https://192.168.1.100:443")
player.input_list         # list[str] - Raw input list from device ([] if unavailable)
```

#### Available Sources

```python
player.available_sources  # list[str] - Returns [] if unavailable
player.source_catalog     # list[dict[str, Any]] - Structured source metadata for integrations
```

`available_sources` returns a UI-ready list of source names:

1. **Always included**: Physical/hardware inputs (`Bluetooth`, `Line In`, `Optical In`, etc.) and `Network`
2. **Conditionally included**: Current active source (for example `Spotify`, `AirPlay`, or a multi-room follower name)
3. **Not included**: Inactive streaming services that are not currently active

Use `source_catalog` when an integration needs structured source metadata (for example Music Assistant).

If you need a stable identifier for the current source (to compare/store), use:

```python
current_source_id = player.source
# Examples: "network", "line_in", "optical", "spotify", "master_bedroom"
```

If you need the UI-ready display name for the current source, use:

```python
current_source_name = player.source_name
# Examples: "Network", "Line In", "Optical In", "Spotify"
```

`set_source()` accepts either UI names *or* catalog ids:

```python
await player.set_source("Line In")   # UI display name
await player.set_source("line_in")   # source_catalog id
await player.set_source("network")   # source_catalog id (maps to device "wifi" mode)
```

`source_catalog` entry schema:

```python
# One catalog entry
{
    "id": "spotify",                      # Stable source key
    "name": "Spotify",                    # Display name
    "kind": "service",                    # "hardware_input" | "service" | "virtual"
    "selectable": False,                  # Directly selectable via set_source
    "is_current": True,                   # Active source marker
    "supports_pause": True,
    "supports_seek": True,
    "supports_next_track": True,
    "supports_previous_track": True,
    "supports_shuffle": True,
    "supports_repeat": True,
}
```

`kind` semantics:
- `hardware_input`: Physical or connection-level input (`Network`, `Bluetooth`, `Line In`, `Optical In`, etc.)
- `service`: Known streaming/cast services (`Spotify`, `AirPlay`, `DLNA`, `TuneIn`, etc.)
- `virtual`: Non-standard active source names (for example a multi-room follower source label)

`selectable` semantics:
- `True` for `hardware_input` entries
- `False` for `service` and `virtual` entries

**Example usage:**
```python
await player.refresh(full=True)

# Existing UI-ready source list
source_names = player.available_sources

# New structured catalog for integrations
catalog = player.source_catalog

# Example: build selectable source options
selectable = [item for item in catalog if item["selectable"]]

# Example: discover source capabilities for UI controls
spotify = next((item for item in catalog if item["id"] == "spotify"), None)
if spotify and spotify["supports_shuffle"]:
    print("Spotify supports shuffle control")
```

#### EQ Presets

```python
player.eq_preset  # str | None
# Returns current EQ preset name, normalized to Title Case to match get_eq_presets() format.
# Example: "Flat", "Acoustic", "Rock" (not "flat", "acoustic", "rock")
```

Current EQ preset name from cached status.

#### Parametric EQ (PEQ) – WiiM only

The **Parametric EQ (PEQ)** API provides full control of the WiiM LV2 PEQ system: 10-band parametric EQ per source, stereo or independent L/R channel modes, and custom preset save/load/delete/rename. It is **only available on WiiM devices**; capability `supports_peq` is probed at connect time. (Contribution: [jeromeof](https://github.com/jeromeof) – [PR #12](https://github.com/mjcumming/pywiim/pull/12).)

**Capability check:**

```python
if player.client.capabilities.get("supports_peq", False):
    settings = await player.client.get_peq_bands()
    # ...
```

**Client methods (use when `supports_peq` is True):**

```python
# Read
settings = await player.client.get_peq_bands()                    # Current or default source
settings = await player.client.get_peq_bands(source_name="wifi")  # Specific source
# settings: PEQSettings (enabled, channel_mode, bands, bands_l, bands_r, name)

presets = await player.client.get_peq_preset_list()              # {"custom": [...], "preset": [...]}
detailed = await player.client.get_peq_preset_list_detailed()    # List[PEQPresetInfo]

# Write (see pywiim.api.peq for PEQBand, validation, and full API)
await player.client.set_peq_bands(bands, source_name="wifi")
await player.client.set_peq_enabled(True, source_name="wifi")
await player.client.save_peq("My Preset", source_name="wifi")
await player.client.load_peq("My Preset", source_name="wifi")
```

**Data models** (from `pywiim.api.peq`): `PEQBand`, `PEQSettings`, `PEQPresetInfo`. Constants: `PEQ_MODE_OFF`, `PEQ_MODE_LOW_SHELF`, `PEQ_MODE_PEAK`, `PEQ_MODE_HIGH_SHELF`, `PEQ_CHANNEL_MODE_STEREO`, `PEQ_CHANNEL_MODE_LR`.

##### LV2 graphic 10-band EQ (`Eq10HP`) — WiiM only, read-only

WiiM firmware can also load a **10-band graphic** LV2 plugin (**`http://moddevices.com/plugins/caps/Eq10HP`**) for per-source EQ. Reports indicate the **same HTTP command family** as above (`EQGetLV2SourceBandEx`, `EQSetLV2SourceBand`, `EQChangeSourceFX`, etc.), but with **`pluginURI`** set to **`http://moddevices.com/plugins/caps/Eq10HP`** and band parameters such as `band31hz`, `band63hz`, … instead of the parametric `a_mode` / `a_freq` / … shape used by **`EqNp`**.

pywiim exposes read-only helpers for this plugin. Use the WiiM app for setup/write workflows until write behavior is validated across more firmware versions.

```python
settings = await player.client.get_graphic_eq_bands()
settings = await player.client.get_graphic_eq_bands(source_name="wifi")
# settings: GraphicEQSettings (enabled, channel_mode, name, eq_level, bands)

presets = await player.client.get_graphic_eq_preset_list()
# {"custom": [...], "preset": ["Flat", "Acoustic", ...]}
```

**Data models** (from `pywiim.api.peq`): `GraphicEQBand`, `GraphicEQSettings`. Constant: `GEQ_PLUGIN_URI`.

##### Room Correction — WiiM only, read-only

WiiM firmware exposes a room-correction block through `RoomCorrGet`. The payload is PEQ-shaped (`EqNp` plugin parameters), but it represents the device's room-correction state rather than the user PEQ preset.

```python
room = await player.client.get_room_correction()
# room: RoomCorrectionSettings (enabled, channel_mode, name, eq_level, bands)
```

pywiim intentionally exposes room correction as **read-only** for now. Use the WiiM app to create or adjust room correction until `RoomCorrSet` / `RoomCorrSetLR` have broad real-device coverage.

#### Playback Presets (Radio Stations / Saved Favorites)

```python
player.presets  # list[dict[str, Any]] | None
# Returns list of preset dictionaries with number, name, url, and picurl fields.
# Returns None if presets not supported or not available.
# Automatically fetched by player.refresh() on track change or periodically (every 60s).

player.presets_full_data  # bool
# True for WiiM devices (can read preset names/URLs via getPresetInfo)
# False for LinkPlay devices (only preset count available via preset_key)

await player.client.get_max_preset_slots()  # int
# Returns maximum number of preset slots (6-20, or 0 if not supported)
# Always available if supports_presets is True
```

**Device Differences:**
- **WiiM devices**: `presets_full_data = True` - `getPresetInfo` works, returns full preset data (names, URLs, etc.)
- **LinkPlay devices**: `presets_full_data = False` - `getPresetInfo` not available, only preset count via `preset_key`

Each preset dictionary contains (when `presets_full_data = True`):
- `number`: Preset slot number (1-20)
- `name`: Preset name (e.g., "Radio Paradise", "BBC Radio 1")
- `url`: Stream URL (may be `None` if not set)
- `picurl`: Cover art URL (may be `None` if not set)

**Example - WiiM devices (full data):**
```python
await player.refresh()  # Presets automatically fetched

if player.supports_presets and player.presets_full_data and player.presets:
    # Get preset names for source list
    preset_names = [
        preset.get("name", f"Preset {preset.get('number')}")
        for preset in player.presets
        if preset.get("name")  # Only include presets with names
    ]
    # Example: ["Radio Paradise", "BBC Radio 1", ...]
    
    # Access individual preset data
    for preset in player.presets:
        print(f"Preset {preset['number']}: {preset.get('name', 'Unnamed')}")
```

**Example - LinkPlay devices (count only):**
```python
if player.supports_presets and not player.presets_full_data:
    # Only count available, not names
    max_slots = await player.client.get_max_preset_slots()
    print(f"Device supports {max_slots} preset slots")
    
    # Can still play presets by number (1 to max_slots)
    # But can't show preset names in UI
    await player.play_preset(1)  # Play preset 1 (resume from last position)
    await player.play_preset(1, index=1)  # Play preset 1 from beginning (if device supports index)
```

**Note:** Presets are automatically fetched by `player.refresh()`:
- On full refresh
- On track changes (may indicate preset switch)
- Periodically (every 60 seconds)

**For LinkPlay devices:** `player.presets` will be `None` or empty even if presets are supported. Use `get_max_preset_slots()` to get the count, and play presets by number.

#### Multiroom / Group Role

```python
player.role              # str - "solo", "master", or "slave"
player.is_solo           # bool - True if not in a group
player.is_master         # bool - True if group master
player.is_slave          # bool - True if slave in a group
player.group             # Group | None - Group object (for multi-player scenarios)
player.group_master_name # str | None - Safe accessor for group master's name
```

**Role Detection** - SINGLE source of truth:
- Role comes from device API state via `detect_role()` function
- Updated during `refresh()` from actual device multiroom status
- Cached in `player._detected_role` field
- **Independent of Group objects** - Group objects are for linking Player objects in Home Assistant, role reflects actual device state

**Example:**
```python
await player.refresh()
if player.is_master:
    print(f"Master with {len(player.group.slaves)} linked Player objects")
    # Note: In standalone monitoring, group.slaves may be empty
    # but is_master will still be True based on device API state
```

**Important:** 
- `player.role` reads device state, NOT Group object relationships
- Group objects (`player.group`) are optional and used by coordinators (like HA) to link Player objects
- A master device shows `is_master=True` even if no slave Player objects exist
- Role is always accurate regardless of whether Player objects are linked

#### Media Position and Duration

The Player provides real-time position tracking using a **hybrid approach** that combines HTTP polling, UPnP events, and position estimation for smooth updates:

```python
player.media_position  # int | None - Current position in seconds
player.media_duration  # int | None - Track duration in seconds
player.media_position_updated_at  # float | None - Unix timestamp of last update
```

**How Position Updates Work:**

1. **HTTP Polling** - `await player.refresh()` fetches current state (typically every 5-10s)
2. **UPnP Events** - Real-time notifications when tracks change or playback state changes (requires UPnP setup)
3. **Position Estimation** - Automatically ticks every second while playing for smooth progress bars

The `StateSynchronizer` intelligently merges these three sources, providing accurate position without constant network requests.

**Example - Simple Position Monitoring:**

```python
from pywiim import Player, WiiMClient

player = Player(WiiMClient("192.168.1.100"))
await player.refresh()

# Get current position and duration
position = player.media_position  # e.g., 120 (2:00)
duration = player.media_duration  # e.g., 240 (4:00)

if position and duration:
    progress = (position / duration) * 100
    print(f"{position}/{duration}s ({progress:.1f}%)")
```

**Example - Real-time Position Updates:**

```python
def on_state_changed():
    """Called every second while playing + on all state changes."""
    pos = player.media_position
    dur = player.media_duration
    if pos and dur:
        print(f"Position: {pos}/{dur}s")

player = Player(client, on_state_changed=on_state_changed)
await player.refresh()
await player.play()  # Callback fires automatically every second while playing
```

**Example - With UPnP for Real-time Events:**

UPnP is optional. To use it you must create an `UpnpClient` with a **description URL** (the device’s UPnP description document), then pass it to `Player`. For full event subscriptions you also use `UpnpEventer` with the same client. See [UPNP_INTEGRATION.md](../design/UPNP_INTEGRATION.md) and [HA_INTEGRATION.md](HA_INTEGRATION.md) for the complete setup.

```python
from pywiim import Player, WiiMClient
from pywiim.upnp import UpnpClient

# Create HTTP client and get device UUID (needed for optional UpnpEventer)
client = WiiMClient("192.168.1.100")
device_info = await client.get_device_info_model()

# UPnP description URL: WiiM devices use port 49152 (HTTP)
description_url = f"http://{client.host}:49152/description.xml"
upnp_client = await UpnpClient.create(
    client.host,
    description_url,
    session=None,  # optional: pass client's session for connection pooling
)
player = Player(client, upnp_client=upnp_client)

# Optional: subscribe to UPnP events for immediate track/volume updates.
# UpnpEventer requires (upnp_client, state_manager, device_uuid, state_updated_callback)
# and is started with eventer.start(). See UPNP_INTEGRATION.md for full example.
```

Position then updates via UPnP events (when subscribed), position estimation (smooth 1-second ticks), and HTTP polling (fallback + verification).

**Position Estimation:**
- Runs automatically in background while playing
- Updates every second for smooth UI progress
- Resets on track changes and seeks
- Clamps to duration to prevent overflow
- No manual intervention needed

#### Position & Duration Edge Cases

The library automatically handles several edge cases and device quirks related to position and duration tracking. Understanding these helps when building integrations:

##### 1. Time Unit Inconsistency (Issue [#75](https://github.com/mjcumming/wiim/issues/75))

**Problem**: The LinkPlay/WiiM API returns time values in different units depending on the source:
- Most sources (USB, Line In, etc.): **milliseconds** (1,000 ms = 1 second)
- Streaming services (Spotify, Tidal, Qobuz, etc.): **microseconds** (1,000,000 μs = 1 second)

**Solution**: The library uses source-aware auto-detection:

```python
# Known local/network/file sources = treated as milliseconds
# Other values < 36,000,000 = treated as milliseconds
# Other values ≥ 36,000,000 = treated as microseconds

# This keeps very long local files working while preserving the
# streaming-service microsecond fallback.
```

**Impact**: Position and duration values are always returned in **seconds** regardless of source. No manual conversion needed.

##### 2. Live Streams & Zero Duration

**Problem**: Web radio, internet radio, and live streams report `duration=0` because there's no defined end time.

**Solution**: The library converts zero duration to `None`:

```python
if player.media_duration is None:
    # Live stream, web radio, or duration unavailable
    # Don't show progress bar
    print("Live stream - no duration available")
else:
    # Normal track with known duration
    progress = (player.media_position / player.media_duration) * 100
    print(f"Progress: {progress:.1f}%")
```

**Sources affected**: `wifi`, `webradio`, `iheartradio`, `pandora`, `tunein`

##### 3. Position Exceeds Duration (Firmware Bugs)

**Problem**: Device firmware sometimes reports impossible states where position > duration.

**Solution**: The library has intelligent detection and correction:

```python
# Scenario A: Duration seems too short (< 2 minutes) but position is reasonable
# → Likely firmware bug in duration calculation
# → Hide duration, keep position
if position > 30 and duration < 120:
    media_duration = None  # Hide bad duration
    
# Scenario B: Position clearly exceeds reported duration
# → Prefer hiding unreliable duration over changing device position
else:
    media_duration = None
```

**Additional protection**: Position is clamped to duration at the property level:

```python
# Position can never exceed duration
if player.media_position and player.media_duration:
    assert player.media_position <= player.media_duration  # Always True
```

##### 4. AirPlay Duration Interpretation

**Problem**: Early versions incorrectly interpreted the `totlen` field as "remaining time" instead of "total duration" for AirPlay sources.

**Solution**: Fixed in v1.0.75+. The `totlen` field is now correctly interpreted as total track duration for all sources, including AirPlay.

```python
# ✅ Correct (current): totlen = total duration
# AirPlay playing 4:00 track at 2:00 position:
#   position = 120 seconds (elapsed)
#   duration = 240 seconds (total)
#   progress = 50%
```

##### 5. Negative Position Values

**Problem**: Device API sometimes returns negative position values (invalid).

**Solution**: Negative values are filtered out:

```python
if player.media_position is not None:
    # Always ≥ 0, never negative
    # Negative values from API return None instead
    pass
```

##### 6. UPnP Position Updates

**Important limitation**: UPnP events provide position/duration **only when tracks start**, not continuously during playback.

```python
# ✅ UPnP sends position/duration in these scenarios:
# - Track changes (new song starts)
# - Playback starts from idle/stopped
# - Manual seek completes

# ❌ UPnP does NOT send position during continuous playback
# Position is estimated locally using a timer
# HTTP polling every 5 seconds corrects drift
```

This is why the library uses **hybrid position tracking** (UPnP events + local estimation + HTTP polling).

##### 7. Source-Specific Behavior Summary

Different sources have different position/duration characteristics:

| Source Type | Position | Duration | Time Unit | Notes |
|-------------|----------|----------|-----------|-------|
| **USB/Local Files** | ✅ Always | ✅ Always | milliseconds | Long files can exceed 10h |
| **Spotify/Tidal/Qobuz** | ✅ Always | ✅ Always | **microseconds** | Auto-detected |
| **AirPlay** | ✅ Always | ✅ Always | milliseconds | totlen = total duration |
| **Bluetooth** | ❌ Often N/A | ❌ Often N/A | - | Commonly reports `curpos=0`/`totlen=0` even while playing (depends on phone/app/firmware) |
| **DLNA** | ✅ Usually | ✅ Usually | milliseconds | Depends on server |
| **Web Radio/WiFi** | ❌ Often N/A | ❌ `None` | - | Live streams |
| **Line In/Optical** | ❌ N/A | ❌ N/A | - | Real-time input |

**Bluetooth metadata note**: Track metadata on Bluetooth is often available via the HTTP `getMetaInfo` endpoint (AVRCP), but can be intermittent. It's normal to see `getMetaInfo` return sentinel values like `"unknow"`/`"un_known"` until the source device/app provides metadata (often after a track change). Some devices also report `"Unknown"` in `getPlayerStatus` title fields even when `getMetaInfo` has correct title/artist/album.

##### 8. Best Practices for Integrations

When building UI or integrations, follow these patterns:

```python
# ✅ GOOD: Always check if duration exists before calculating progress
if player.media_position and player.media_duration:
    progress = (player.media_position / player.media_duration) * 100
    # Show progress bar
else:
    # Don't show progress bar (live stream or no playback)
    pass

# ✅ GOOD: Handle None values gracefully
position = player.media_position or 0
duration = player.media_duration or 0

# ✅ GOOD: Use position_updated_at to detect stale data
if player.media_position_updated_at:
    age = time.time() - player.media_position_updated_at
    if age > 30:
        # Position data is stale
        pass

# ❌ BAD: Assume position/duration always exist
progress = (player.media_position / player.media_duration) * 100  # May raise TypeError/ZeroDivisionError
```

**Summary**: The library handles all position/duration edge cases automatically. Your integration code should:
1. Always check for `None` before using position/duration
2. Don't show progress bars when duration is `None` (live streams)
3. Trust the returned values - they're already validated and clamped
4. Use the automatic position callbacks for smooth UI updates

#### Other Properties

```python
player.volume_level  # float | None (0.0-1.0)
player.is_muted  # bool | None
player.play_state  # str | None ("play", "pause", "idle", "load")
player.source  # str | None (stable id, e.g., "airplay", "spotify", "line_in", "network")
player.source_id  # str | None (alias for player.source)
player.source_name  # str | None (UI name, e.g., "AirPlay", "Spotify", "Line In", "Network")
player.media_title  # str | None (falls back to URL filename if no title)
player.media_artist  # str | None
player.media_album  # str | None
player.media_content_id  # str | None (URL if playing from play_url())
# media_content_id enables scene/snapshot restoration: capture when saving, pass to play_url() when restoring
player.media_image_url  # str | None (cover art URL)
player.media_sample_rate  # int | None (Hz)
player.media_bit_depth  # int | None (bits)
player.media_bit_rate  # int | None (kbps)
player.media_codec  # str | None (e.g., "flac", "mp3", "aac")
player.upnp_health_status  # dict[str, Any] | None (health statistics)
player.upnp_is_healthy  # bool | None (True/False/None)
player.upnp_miss_rate  # float | None (0.0-1.0, miss rate)
player.shuffle  # bool | None
player.repeat  # str | None ("one", "all", "off")
player.queue_position  # int | None — HTTP plicurr, or PlayQueue overlay when empty
player.queue_count  # int | None — HTTP plicount, or PlayQueue overlay when empty
player.audio_output_mode  # str | None — current hardware mode name (model-specific)
```

#### UPnP Health Properties

UPnP health tracking monitors whether UPnP events are reliably catching state changes. Only available when UPnP client is provided to Player.

```python
# Health status dictionary (None if UPnP not enabled)
health = player.upnp_health_status
# Returns: {
#     "is_healthy": True,
#     "miss_rate": 0.05,  # 5% miss rate
#     "detected_changes": 20,
#     "missed_changes": 1,
#     "has_enough_samples": True
# }

# Simple health check
is_healthy = player.upnp_is_healthy  # True/False/None

# Miss rate (0.0 = perfect, 1.0 = all missed)
miss_rate = player.upnp_miss_rate  # 0.05 = 5% miss rate
```

**Note**: UPnP health tracking requires:
- UPnP client passed to `Player(..., upnp_client=upnp_client)`
- UPnP events being subscribed (via `UpnpEventer`)
- Player refresh being called regularly

#### Cover Art Methods

```python
# Fetch cover art image (with caching)
result = await player.fetch_cover_art(url=None)  # Returns (bytes, content_type) | None
# If url is None, uses current track's cover art URL
# If no URL available, fetches WiiM logo as fallback

# Get just the image bytes (convenience method)
image_bytes = await player.get_cover_art_bytes(url=None)  # Returns bytes | None
```

**Cover Art Features:**
- ✅ Automatic caching (in-memory, 1 hour TTL, max 10 images per player)
- ✅ Uses client's HTTP session for fetching
- ✅ Handles expired URLs gracefully
- ✅ Returns both image bytes and content type
- ✅ Cache cleanup on fetch (removes expired entries)
- ✅ Automatic WiiM logo fallback when no cover art available

### Properties

#### Connection Info

```python
player.host  # str - Device hostname or IP address
player.port  # int - Device port number
player.timeout  # float - Network timeout in seconds
```

#### Device Capabilities

Device capabilities are detected via endpoint probing during initialization and exposed as boolean properties. These allow integrations to check feature support before calling methods, enabling proper UI rendering and avoiding errors.

**Source of truth** — The merged **`player.client.capabilities`** mapping is authoritative for optional HTTP API support (`supports_*` keys and related fields). Integrations must not enable those features from device model alone. See **[ADR 018](../design/adr/018-capabilities-dict-source-of-truth.md)** and [HA_CAPABILITIES.md](HA_CAPABILITIES.md).

**HTTP API Capabilities** (detected via endpoint probing):

```python
player.supports_firmware_install  # bool - True if firmware installation via API is supported (WiiM only)
player.supports_eq                # bool - True if EQ control is supported
player.client.capabilities.get("supports_peq")  # bool - True if Parametric EQ (PEQ) is supported (WiiM only)
player.supports_presets           # bool - True if presets are supported
player.presets_full_data          # bool - True if preset names/URLs available (WiiM), False if count only (LinkPlay)
player.supports_audio_output      # bool - True if audio output mode control is supported
player.supports_metadata          # bool - True if metadata retrieval (getMetaInfo) is supported
player.supports_alarms            # bool - True if alarms are supported (WiiM only)
player.supports_sleep_timer       # bool - True if sleep timer is supported (WiiM only)
player.supports_led_control       # bool - True if primary LED control (setLED/setLEDBrightness) is supported
player.supports_led_switch        # bool - True if Status Light (LED_SWITCH_SET) is supported
player.supports_led_indicator     # bool - True if LED indicator on/off is supported (ADR 005; Arylic + WiiM)
player.supports_display_config    # bool - True if display/LCD on-off and brightness is supported (WiiM Ultra only)
```

**UPnP Capabilities** (depend on UPnP client initialization):

```python
player.supports_upnp             # bool - True if UPnP client is available (requires upnp_client parameter)
player.supports_queue_browse      # bool - True if queue retrieval is available (ContentDirectory or PlayQueue BrowseQueue)
player.supports_queue_add         # bool - True if AddURIToQueue or PlayQueue enqueue actions are advertised
player.supports_queue_count       # bool - Always True - queue count/position available via HTTP API
```

**Transport Capabilities** (depend on current playback source):

```python
player.supports_next_track        # bool - True if next track is supported for current source
player.supports_previous_track    # bool - True if previous track is supported for current source
player.supports_seek              # bool - True if seeking within track is supported for current source
```

⚠️ **IMPORTANT**: Use `supports_next_track` and `supports_previous_track` to determine feature support, NOT `queue_count`! Streaming services (Spotify, Amazon Music, etc.) always report `queue_count=0` because they manage their own queues internally, but next/previous track commands work perfectly.

For detailed capability information and usage examples, see [HA_CAPABILITIES.md](HA_CAPABILITIES.md).

### Methods

```python
# State management
await player.refresh()  # Fetch latest state from device
# ⚠️ NOTE: In integrations, only call this in coordinator's _async_update_data()
# See "When to Use refresh()" section below

# Playback control
await player.play()
await player.pause()
await player.stop()
await player.next_track()
await player.previous_track()
await player.seek(position: int)  # Seek to position in seconds
await player.set_volume(volume: float)  # 0.0-1.0
await player.set_mute(muted: bool)
await player.set_source(source: str)
await player.clear_playlist()
await player.set_shuffle(enabled: bool)  # Preserves repeat state

# Media playback
await player.play_url(url: str, enqueue: str = "replace")  # Play URL; enqueue="add"|"next"|"replace"|"play"
await player.play_playlist(playlist_url: str)  # Play M3U playlist
await player.play_preset(preset: int, index: int | None = None)  # Play preset; optional 1-based track index (e.g. index=1 = from start)
result = await player.play_notification(url: str)  # Returns NotificationPlaybackResult

# Queue (requires upnp_client; gate on supports_queue_add / supports_queue_browse)
# AVTransport AddURIToQueue, or WiiM PlayQueue on Pro / Pro Plus (see HA_CAPABILITIES.md)
await player.add_to_queue(url: str, metadata: str = "")
await player.insert_next(url: str, metadata: str = "")
await player.play_queue(position: int)
await player.remove_from_queue(position: int)
await player.clear_queue()
queue_items = await player.get_queue()  # list[dict] when supports_queue_browse

# EQ control
await player.set_eq_preset(preset: str)
await player.get_eq()  # Returns dict[str, Any]
await player.get_eq_presets()  # Returns list[str]
await player.get_eq_status()  # Returns bool

# Parametric EQ (PEQ) – WiiM only; check supports_peq first (see "Parametric EQ (PEQ)" section above)
await player.client.get_peq_bands(source_name=None)
await player.client.set_peq_bands(bands, channel_mode="Stereo", source_name=None)
await player.client.set_peq_enabled(enabled, source_name=None)
await player.client.get_peq_preset_list()
await player.client.save_peq(name, source_name=None)
await player.client.load_peq(name, source_name=None)
await player.client.delete_peq(name)
await player.client.rename_peq(name, new_name)

# Audio output control
# Mode integers are model-specific. Common: 1=Optical, 2=Line Out, 3=COAX, 4=BT/Headphone, 8=USB.
# Mode 7 is HDMI Out on Amp Ultra and Speaker Out on Sound / Sound Lite (Bluetooth Out is source=1 on the same hardware).
# Prefer names from player.available_output_modes (catalog when the model sets outputs).
await player.set_audio_output_mode(mode: str | int)  # "Line Out", "Speaker Out", "Optical Out", "USB Out", etc.

# LED control (primary: setLED / setLEDBrightness)
await player.set_led(enabled: bool)
await player.set_led_brightness(brightness: int)  # 0-100
# LED Indicator (ADR 005; Arylic + WiiM) – preferred for on/off switch
on_off = await player.get_led_indicator()  # bool; assumes on if device has no read API
await player.set_led_indicator(enabled: bool)     # uses LED_SWITCH_SET
# Display (WiiM Ultra only; setLightOperationBrightConfig JSON – not LED_SWITCH_SET / setLED)
await player.set_display_enabled(enabled: bool, default_bright: int | None = None)  # on: uses full brightness by default (1–100 scale; 1=min)
await player.set_display_config(auto_sense_enable=0, default_bright=100, disable=0)  # disable: 0=on, 1=off; see DISPLAY_* in pywiim.api.constants

# Audio settings (stereo balance; WiiM when supports_channel_balance)
bal = await player.get_channel_balance()  # float | None; updates cache, fires callback if changed
player.channel_balance  # float | None — cached; also updated on refresh() ~60s when supported
await player.set_channel_balance(balance: float)  # -1.0 to 1.0

# Status and metadata fetchers
await player.get_multiroom_status()  # Returns dict[str, Any]
await player.get_audio_output_status()  # Returns dict[str, Any] | None
await player.get_meta_info()  # Returns dict[str, Any]

# Bluetooth workflow
await player.get_bluetooth_history()  # Returns list[dict[str, Any]]
await player.connect_bluetooth_device(mac_address: str)
await player.disconnect_bluetooth_device()
await player.get_bluetooth_pair_status()  # Returns dict[str, Any]
await player.scan_for_bluetooth_devices(duration: int = 3)  # Returns list[dict[str, Any]]

# Output selection (hardware modes + paired BT devices)
outputs = player.available_outputs  # Returns list[str]
bt_devices = player.bluetooth_output_devices  # Returns list[dict[str, str]]
await player.audio.select_output("Optical Out")  # Hardware mode
await player.audio.select_output("BT: Sony Speaker")  # Specific paired Bluetooth device

# Device management
await player.reboot()
await player.sync_time(ts: int | None = None)
```

### When to Use `refresh()`

**⚠️ CRITICAL: Integrations should NOT call `refresh()` manually in general.**

**Command methods do NOT call `refresh()` internally.** State updates happen via UPnP events and coordinator polling in integrations.

**General Rule:**
- **Integrations**: Only the coordinator's `_async_update_data()` method should call `refresh()` on schedule (every 5-10 seconds)
- **Entity methods**: Never call `refresh()` or `async_request_refresh()` after commands - state updates happen automatically via callbacks
- **One-off scripts**: Can call `refresh()` to get initial state or verify changes

#### ✅ Use `refresh()` for:

```python
# 1. One-off scripts without polling
player = Player(WiiMClient("192.168.1.100"))
await player.play()
await player.refresh()  # Get fresh state
print(f"Playing: {player.media_title}")

# 2. Initial state fetch
await player.refresh()  # Populate state cache
print(f"Volume: {player.volume_level}")

# 3. Explicit verification in tests
await player.set_volume(0.5)
await player.refresh()
assert player.volume_level == 0.5
```

#### ❌ Don't use `refresh()` in integrations (except coordinator):

```python
# ❌ WRONG - Entity method calling refresh manually
async def async_media_play(self):
    await self.coordinator.data["player"].play()
    await self.coordinator.data["player"].refresh()  # ❌ NO! Unnecessary!
    # State updates automatically via callback (immediate)

# ✅ CORRECT - Entity method (no refresh needed)
async def async_media_play(self):
    await self.coordinator.data["player"].play()
    # That's it! State updates via:
    # - Callbacks (immediate, <1ms)
    # - UPnP events (immediate when available)
    # - Coordinator polling (5-10 seconds, scheduled)

# ✅ CORRECT - Coordinator's scheduled polling
async def _async_update_data(self):
    await self.player.refresh()  # ✅ Only place refresh() should be called
    return {"player": self.player}
```

**See also**: `docs/design/OPERATION_PATTERNS.md` for detailed patterns

### Seeking and Position Control

The `seek()` method allows you to jump to a specific position in the current track.

#### Basic Seek Usage

```python
# Seek to specific position (in seconds)
await player.seek(120)  # Jump to 2:00

# Seek to beginning
await player.seek(0)

# Seek to 50% through track
if player.media_duration:
    midpoint = player.media_duration // 2
    await player.seek(midpoint)
```

#### Advanced Seek Examples

```python
# Skip forward 30 seconds
if player.media_position and player.media_duration:
    new_pos = min(player.media_position + 30, player.media_duration)
    await player.seek(new_pos)

# Skip backward 10 seconds
if player.media_position:
    new_pos = max(player.media_position - 10, 0)
    await player.seek(new_pos)

# Seek to percentage of track
def seek_to_percent(player: Player, percent: float):
    """Seek to percentage (0.0-1.0) of track."""
    if player.media_duration:
        position = int(player.media_duration * percent)
        await player.seek(position)

# Seek to 75%
await seek_to_percent(player, 0.75)
```

#### How Seek Works

When you call `seek()`:
1. Command is sent to device via HTTP API
2. Cached state is updated immediately (optimistic update)
3. `on_state_changed` callback fires with new position
4. Position is confirmed by next UPnP event or HTTP poll
5. Position estimation resumes from new position

```python
def on_position_update():
    """Called immediately after seek, then every second while playing."""
    print(f"Position: {player.media_position}s")

player = Player(client, on_state_changed=on_position_update)

# Seek triggers immediate callback with optimistic update
await player.seek(60)  # Callback fires right away
# Then confirmed by UPnP event or next refresh()
```

#### Position Tracking for UI

For progress bars and time displays that update smoothly:

```python
import asyncio
from pywiim import Player, WiiMClient

async def monitor_playback():
    """Monitor playback with smooth position updates."""
    
    def on_state_changed():
        # Called every second while playing
        pos = player.media_position
        dur = player.media_duration
        
        if pos and dur:
            progress = (pos / dur) * 100
            mins, secs = divmod(pos, 60)
            dur_mins, dur_secs = divmod(dur, 60)
            print(f"{mins:02d}:{secs:02d} / {dur_mins:02d}:{dur_secs:02d} ({progress:.1f}%)")
    
    player = Player(WiiMClient("192.168.1.100"), on_state_changed=on_state_changed)
    await player.refresh()
    await player.play()
    
    # Position updates automatically every second via callback
    # No need to poll in a loop!
    await asyncio.sleep(60)  # Just keep the program running

asyncio.run(monitor_playback())
```

**Key Points:**
- No need to call `refresh()` after `seek()` - state updates automatically
- Position estimation provides smooth 1-second updates while playing
- Callbacks fire on seeks, track changes, and every second during playback
- Hybrid approach (HTTP + UPnP + estimation) ensures reliability

### Notification Playback

The `play_notification()` method is source-aware:
- Uses firmware-native `playPromptUrl` when current source is in the native set (e.g. wifi, tunein, USB). Prompt behavior (duck, play, resume) is **firmware-dependent** and may not work on all devices/sources.
- Falls back to `play_url` when source is unsupported or unknown, so audio is still heard.
- Optional `force_interrupt=True` always uses `play_url` so the notification is guaranteed audible (e.g. for TTS when the prompt path is unreliable).

```python
result = await player.play_notification("https://example.com/doorbell.mp3")
print(result.method_used)         # "prompt" or "play_url"
print(result.likely_interrupted)  # True when fallback path was used

# Force interrupt playback so TTS is always heard (e.g. linkplay_radio, Spotify)
result = await player.play_notification(tts_url, force_interrupt=True)
```

#### Return Value

`play_notification()` returns `NotificationPlaybackResult`:
- `method_used`: `"prompt"` or `"play_url"`
- `source_before`: Source observed before playback decision (lowercase) or `None`
- `likely_interrupted`: `True` when fallback playback was used
- `reason`: Optional reason (e.g. `unsupported_source`, `force_interrupt`)

#### Behavior Notes

- On native prompt sources, firmware handles duck -> prompt -> restore internally.
- On fallback sources, the device plays the URL as normal media (`play_url`), which may stop/replace the previous source session.
- Unknown sources default to fallback (`play_url`) to prioritize audible notifications.

#### Source Handling Policy

- Native prompt path (`method_used="prompt"`): `wifi`, `network`, `http`, `usb`, `udisk`, `tunein`, `iheartradio`, `radio`, `internetradio`, `webradio`, `custompushurl`, `preset`, `playlist`
- Fallback path (`method_used="play_url"`): external/pass-through sources such as `spotify`, `airplay`, `dlna`, `bluetooth`, `line_in`, `optical`, `linkplay_radio` (WiiM Home built-in radio), and unknown/unmapped sources
- Real-device validation: Spotify, AirPlay, and some radio sources (e.g. `linkplay_radio`) on modern firmware may return `OK` for `playPromptUrl` while producing no audible prompt; fallback path addresses this by forcing audible playback. Use `force_interrupt=True` for TTS when the prompt path is unreliable.

#### Limitations

- Native prompt behavior (duck, play, resume) is firmware- and source-dependent; do not overclaim in release notes.
- Fallback playback is interruptive by design on unsupported sources.
- Requires firmware 4.6.415145+ for prompt command support.
- Device API uses HTTPS on many newer devices; command URLs are still passed as encoded media URLs.

#### Use Cases

- TTS announcements (Home Assistant `tts.speak`)
- Doorbell sounds
- Alert notifications
- Timer/alarm sounds

This is the recommended approach for integrations that need audible announcements and explicit visibility into whether fallback interruption likely occurred.

### Firmware Updates

The library provides methods to check for and install firmware updates. Update installation is **only available on WiiM devices** - other devices require manual reboot after an update is downloaded.

#### Checking for Updates

All devices expose firmware update availability through `device_info`:

```python
# Check if update is available
if player.firmware_update_available:
    print(f"Update available: {player.latest_firmware_version}")
    print(f"Current version: {player.firmware}")

# Access raw fields from device_info
device_info = player.device_info
if device_info:
    print(f"Version update flag: {device_info.version_update}")
    print(f"Latest version: {device_info.latest_version}")
```

**Properties:**
- `player.firmware_update_available: bool` - True if `version_update="1"` (update downloaded and ready)
- `player.latest_firmware_version: str | None` - Latest available version from `NewVer` field
- `player.device_info.version_update: str | None` - Raw `VersionUpdate` field from `getStatusEx`
- `player.device_info.latest_version: str | None` - Raw `NewVer` field from `getStatusEx`

#### Installing Updates (WiiM Devices Only)

WiiM devices support firmware update installation via API:

```python
# Check if firmware installation is supported
if player.supports_firmware_install:
    if player.firmware_update_available:
        # Start installation (downloads and installs automatically)
        await player.install_firmware_update()
        
        # Monitor download progress
        download_status = await player.get_update_download_status()
        print(f"Download status: {download_status}")
        
        # Monitor installation progress
        install_status = await player.get_update_install_status()
        print(f"Installation progress: {install_status.get('progress')}%")
else:
    # Non-WiiM device: reboot to install (if update is ready)
    if player.firmware_update_available:
        await player.reboot()
```

**WiiM-Specific Methods:**

```python
# Check for updates (WiiM only)
update_check = await player.check_for_updates_wiim()

# Install update (WiiM only)
# WARNING: DO NOT POWER OFF THE DEVICE DURING THIS PROCESS!
await player.install_firmware_update()

# Get download status (WiiM only)
download_status = await player.get_update_download_status()
# Returns status codes: 10 (review), 25 (downloading), 27 (complete), 30 (verified)

# Get installation progress (WiiM only)
install_status = await player.get_update_install_status()
# Returns: {"status": "0", "progress": "50"} (progress 0-100%)
```

**Important Notes:**
- **WiiM devices only**: `install_firmware_update()` and related methods are only available on WiiM devices
- **Do not power off**: The device must remain powered during installation
- **Automatic reboot**: Device will reboot automatically after installation completes
- **Progress tracking**: Use `get_update_download_status()` and `get_update_install_status()` to monitor progress
- **Other devices**: For non-WiiM devices, use `reboot()` after an update is downloaded

**Capability Check:**

```python
# Check if device supports firmware installation
if player.supports_firmware_install:
    # WiiM device - can install via API
    await player.install_firmware_update()
else:
    # Other device - reboot to install
    await player.reboot()
```

## Models

### DeviceInfo

Device information model.

```python
class DeviceInfo:
    uuid: str
    name: str | None
    model: str | None
    firmware: str | None
    mac: str | None
    ip: str | None
    preset_key: str | None
    input_list: list[str] | None  # Available input sources from InputList field
    plm_support: str | int | None  # Bitmask for physical input sources (smart detection)
```

**Note on `input_list` and `plm_support`:**

- `input_list`: Direct list of available sources from device's `InputList` field in `getStatusEx`. May be `None` if device doesn't provide it.
- `plm_support`: Bitmask indicating which physical inputs are available (from `plm_support` field in `getStatusEx`). Used for smart detection when `input_list` is not available. Bit positions:
  - bit1: LineIn (Aux)
  - bit2: Bluetooth
  - bit3: USB
  - bit4: Optical
  - bit6: Coaxial
  - bit8: LineIn 2
  - bit15: USBDAC (not a selectable source)

### PlayerStatus

Player status model.

```python
class PlayerStatus:
    play_state: str | None
    volume: float | None
    mute: bool | None
    source: str | None
    position: int | None
    duration: int | None
    title: str | None
    artist: str | None
    album: str | None
    image_url: str | None
```

## Exceptions

### WiiMError

Base exception for all WiiM errors.

```python
class WiiMError(Exception):
    """Base exception for WiiM errors."""
```

### WiiMRequestError

Raised when HTTP request fails.

```python
class WiiMRequestError(WiiMError):
    """Raised when HTTP request fails."""
    endpoint: str | None
    attempts: int
    last_error: Exception | None
    device_info: dict[str, str] | None
```

### WiiMResponseError

Raised when device returns error response.

```python
class WiiMResponseError(WiiMError):
    """Raised when device returns error response."""
    endpoint: str | None
    last_error: Exception | None
    device_info: dict[str, str] | None
```

### WiiMTimeoutError

Raised when request times out.

```python
class WiiMTimeoutError(WiiMRequestError):
    """Raised when request times out."""
```

### WiiMConnectionError

Raised when connection fails.

```python
class WiiMConnectionError(WiiMRequestError):
    """Raised when connection fails."""
```

### WiiMInvalidDataError

Raised when response data is invalid.

```python
class WiiMInvalidDataError(WiiMError):
    """Raised when response data is invalid."""
```

## Group Object

The `Group` object is a utility for managing multiroom groups. It's accessed via the master player and provides group-level operations.

### Accessing the Group

```python
from pywiim import Player

# Master player automatically has a group object when it's a master
if player.is_master and player.group:
    group = player.group

# Slave players reference the same group object
if slave_player.is_slave and slave_player.group:
    # This is the same Group object as the master's
    group = slave_player.group
    master = group.master  # Access the master player
```

### Group Properties

All Group properties compute dynamically (no caching) by reading from linked Player objects:

```python
# Volume and mute (computed properties)
group.volume_level  # float | None - MAX of all devices
group.is_muted      # bool | None - True only if ALL devices muted

# Playback state and media (from master's cached state)
group.play_state      # str | None - Master's play state
group.media_title     # str | None - Master's media title
group.media_artist    # str | None - Master's media artist
group.media_album     # str | None - Master's media album
group.media_position  # float | None - Master's media position (seconds)
group.media_duration  # float | None - Master's media duration (seconds)

# Group members
group.master        # Player - The master player
group.slaves        # list[Player] - Linked slave players
group.all_players   # list[Player] - Master + all slaves
group.size          # int - Number of players (master + slaves)
```

**Important:**
- Properties read from Player objects on access (always current)
- No polling or refresh needed - reads cached Player state
- Virtual entities can use these for aggregated group state

### Group Operations

#### Playback Control

All playback commands delegate to the master player:

```python
# These all call master.play(), master.pause(), etc.
await group.play()
await group.pause()
await group.stop()
await group.next_track()
await group.previous_track()
```

**Automatic Routing:**
When a slave player's playback methods are called, they automatically route through the group:

```python
# Works the same whether called on master or slave
await slave_player.pause()
# → pywiim detects is_slave
# → routes to slave.group.pause()
# → calls master.pause()
# → master's callback fires

# Slave without group object raises WiiMError
```

#### Volume and Mute

Group-wide volume and mute operations adjust all devices:

```python
# Set volume on all devices (proportional adjustment)
await group.set_volume_all(0.5)
# If group volume is 50%, each device changes by same amount
# Master at 50% → 50%, Slave at 30% → 30%, etc.

# Mute/unmute all devices
await group.mute_all(True)   # Mute all
await group.mute_all(False)  # Unmute all
```

**Individual Volume Control:**
Players maintain independent volume control:

```python
# Adjust only the slave device
await slave_player.set_volume(0.5)
# → Command goes to slave device only
# → Slave's callback fires (slave entity updates)
# → Master's callback fires (virtual entity updates)
# → group.volume_level recomputes (MAX of all)
```

**Cross-Notification:**
When a slave's volume/mute changes via `set_volume()` / `set_mute()`, both slave and master callbacks fire:
- Slave callback → slave entity updates
- Master callback → virtual entity updates (reads group.volume_level)

External volume/mute changes on a slave (physical buttons, WiiM app) are applied on the next `refresh()` poll. Slave polls write volume/mute into the state synchronizer without overwriting master-propagated playback metadata.

#### Group Management

```python
# Create group (makes player a master)
group = await player.create_group()

# Join group (automatically handles all preconditions)
# - Works regardless of either player's current role
# - Disbands/leaves groups as needed automatically
await slave_player.join_group(master_player)

# Leave group (works for any role)
# - Solo: No-op (idempotent)
# - Master: Disbands entire group
# - Slave: Leaves group
# NO NEED to check player role before calling!
await player.leave_group()

# Disband group (explicit disband via Group object)
await group.disband()
```

### Example: Virtual Group Entity

```python
class VirtualGroupEntity:
    """Virtual entity representing a multiroom group."""
    
    def __init__(self, master_player: Player):
        self.master = master_player
    
    @property
    def group(self):
        return self.master.group
    
    @property
    def volume_level(self) -> float | None:
        """Group volume = MAX of all devices."""
        return self.group.volume_level if self.group else None
    
    @property
    def is_muted(self) -> bool | None:
        """Group mute = ALL devices muted."""
        return self.group.is_muted if self.group else None
    
    async def async_set_volume_level(self, volume: float):
        """Set volume on all group members."""
        if self.group:
            await self.group.set_volume_all(volume)
    
    async def async_media_pause(self):
        """Pause playback (routes to master)."""
        if self.group:
            await self.group.pause()
```

**Event Handling:**
- Virtual entity listens to master player's coordinator
- When any group member's volume changes, master's callback fires
- Virtual entity reads `group.volume_level` (computed property)
- No polling lag, immediate updates

## Usage Examples

### Basic Usage

```python
import asyncio
from pywiim import Player, WiiMClient

async def main():
    player = Player(WiiMClient("192.168.1.100"))
    
    # Refresh state cache
    await player.refresh()
    
    # Access cached properties
    print(f"Device: {player.device_name}")
    print(f"Playing: {player.play_state}")
    print(f"Volume: {player.volume_level}")
    
    # Control playback
    await player.set_volume(0.5)
    await player.play()
    
    await player.client.close()

asyncio.run(main())
```

### Error Handling

```python
from pywiim import Player, WiiMClient, WiiMError, WiiMRequestError

async def main():
    player = Player(WiiMClient("192.168.1.100"))
    
    try:
        await player.play()
    except WiiMRequestError as e:
        print(f"Request failed: {e}")
        print(f"Endpoint: {e.endpoint}")
        print(f"Attempts: {e.attempts}")
    except WiiMError as e:
        print(f"WiiM error: {e}")
    finally:
        await player.client.close()
```

### Capability Detection

```python
from pywiim import Player, WiiMClient

async def main():
    player = Player(WiiMClient("192.168.1.100"))
    await player.refresh()
    
    # Check capabilities via player properties
    if player.supports_sleep_timer:
        print("Device supports sleep timer")
    
    if player.shuffle_supported:
        print("Shuffle is supported for current source")

    # Access low-level capability metadata (advanced/integration use)
    caps = player.client.capabilities
    if caps.get("upnp_description_available"):
        print(f"UPnP model: {caps.get('upnp_model_name')}")
        print(f"UPnP has PlayQueue: {caps.get('upnp_has_playqueue')}")
    
    await player.client.close()
```

## Output Selection (Hardware + Bluetooth)

WiiM devices support multiple audio output modes. Hardware names come from the device catalog when the model sets `outputs` (Sound / Sound Lite: **Speaker Out**); otherwise the streamer jack list. Paired Bluetooth devices are listed as `BT: …`, not a generic `"Bluetooth Out"`.

### Available Outputs

Get all available outputs (hardware modes + paired BT devices):

```python
# List all outputs
outputs = player.available_outputs
# Streamer example (when BT devices are paired): ["Line Out", "Optical Out", "Coax Out", "BT: Sony Speaker"]
# Sound / Sound Lite example: ["Speaker Out", "BT: Kitchen Headphones"]
# Note: Generic "Bluetooth Out" is not listed; paired devices appear as "BT: …"

# Just get hardware modes
hardware_modes = player.available_output_modes
# Streamer example: ["Line Out", "Optical Out", "Coax Out"]
# Sound / Sound Lite: ["Speaker Out"]
# Amp Ultra includes "HDMI Out"; Sound Lite maps hardware 7 to "Speaker Out"

# Just get paired Bluetooth output devices
bt_devices = player.bluetooth_output_devices
# Example: [
#     {"name": "Sony Speaker", "mac": "AA:BB:CC:DD:EE:FF", "connected": True},
#     {"name": "JBL Headphones", "mac": "11:22:33:44:55:66", "connected": False}
# ]
```

### Select Output

Use `select_output()` to switch to any output (hardware mode or specific BT device):

```python
# Select hardware output mode
await player.audio.select_output("Optical Out")
await player.audio.select_output("Line Out")
await player.audio.select_output("Speaker Out")  # Sound / Sound Lite

# Select specific Bluetooth device (auto-switches to BT mode and connects)
await player.audio.select_output("BT: Sony Speaker")
await player.audio.select_output("BT: JBL Headphones")

# Check current output
current_mode = player.audio_output_mode  # e.g., "Optical Out"
is_bt_active = player.is_bluetooth_output_active  # True if BT output mode is active
```

### Complete Example

```python
from pywiim import Player, WiiMClient

async def demo_output_selection():
    player = Player(WiiMClient("192.168.1.100"))
    await player.refresh()
    
    # Show all available outputs
    print("Available outputs:")
    for output in player.available_outputs:
        print(f"  - {output}")
    
    # Select Optical output
    await player.audio.select_output("Optical Out")
    print(f"Switched to: {player.audio_output_mode}")
    
    # Show paired Bluetooth devices
    print("\nPaired Bluetooth output devices:")
    for device in player.bluetooth_output_devices:
        status = "🔗 Connected" if device["connected"] else "⊗ Paired"
        print(f"  {status} {device['name']} ({device['mac']})")
    
    # Select specific Bluetooth device
    if player.bluetooth_output_devices:
        first_device = player.bluetooth_output_devices[0]
        await player.audio.select_output(f"BT: {first_device['name']}")
        print(f"Connected to: {first_device['name']}")
```

### Home Assistant Integration

For Home Assistant `select` entity:

```python
class WiiMOutputSelectEntity(SelectEntity):
    """Select entity for output selection."""
    
    @property
    def options(self) -> list[str]:
        """Return available output options.
        
        Available as a property on player: player.available_outputs
        Returns a list of output names (hardware modes + paired BT devices).
        """
        return self.coordinator.data.available_outputs
    
    @property
    def current_option(self) -> str | None:
        """Return current output.
        
        Returns the currently selected output mode, which must match one of the
        options in the available_outputs list. Returns None if output status
        is not available or doesn't match any option.
        """
        player = self.coordinator.data
        
        # Get available options to ensure we return a valid value
        available = player.available_outputs
        if not available:
            return None
        
        # Check if BT output is active and which device is connected
        if player.is_bluetooth_output_active:
            # Find the specific connected BT device from history
            # Note: We only show specific BT devices, not generic "Bluetooth Out"
            for device in player.bluetooth_output_devices:
                if device["connected"]:
                    bt_option = f"BT: {device['name']}"
                    # Ensure this option exists in available_outputs
                    if bt_option in available:
                        return bt_option
        
        # Get current hardware output mode
        current_mode = player.audio_output_mode
        if current_mode and current_mode in available:
            return current_mode
        
        # If current_mode doesn't match, try to find a matching option
        # (handles case where device returns slightly different format)
        if current_mode:
            for option in available:
                if option.lower() == current_mode.lower():
                    return option
        
        # If still no match, return None (will show as "Unknown" in HA)
        return None
    
    async def async_select_option(self, option: str) -> None:
        """Change the selected output."""
        await self.coordinator.data.audio.select_output(option)
        # State updates automatically via callback - no manual refresh needed
```

## Subwoofer Control (WiiM Devices)

WiiM devices support external subwoofer configuration via undocumented API endpoints. Confirmed working on WiiM Pro and WiiM Ultra. Not supported on Arylic/LinkPlay devices.

### Check Subwoofer Support

```python
# Check if device supports subwoofer control
supported = await client.is_subwoofer_supported()

# Check if subwoofer is physically connected
connected = await client.is_subwoofer_connected()
```

### Get Subwoofer Status

```python
from pywiim import SubwooferStatus

# Get status as SubwooferStatus dataclass
status = await client.get_subwoofer_status()
if status:
    print(f"Enabled: {status.enabled}")
    print(f"Connected: {status.plugged}")
    print(f"Crossover: {status.crossover} Hz")
    print(f"Phase: {status.phase}°")
    print(f"Level: {status.level} dB")
    print(f"Delay: {status.sub_delay} ms")

# Get raw API response
raw = await client.get_subwoofer_status_raw()
```

### Control Subwoofer

```python
# Enable/disable subwoofer output
await client.set_subwoofer_enabled(True)
await client.set_subwoofer_enabled(False)

# Set crossover frequency (30-250 Hz)
await client.set_subwoofer_crossover(80)

# Set phase (0 or 180 degrees)
await client.set_subwoofer_phase(0)
await client.set_subwoofer_phase(180)

# Set level adjustment (-15 to +15 dB)
await client.set_subwoofer_level(0)
await client.set_subwoofer_level(-5)  # Reduce bass
await client.set_subwoofer_level(5)   # Boost bass

# Set delay adjustment (-200 to +200 ms)
# Positive: delay subwoofer (sub closer than mains)
# Negative: delay mains (sub further than mains)
await client.set_subwoofer_delay(0)
await client.set_subwoofer_delay(50)

# Control bass to main speakers
await client.set_main_speaker_bass(True)   # Bass sent to mains
await client.set_main_speaker_bass(False)  # Bass filtered from mains
# Player wrapper (preferred for HA): await player.set_main_speaker_bass(True)
# Read cached state: player.main_speaker_bass → True when mains receive bass

# Control subwoofer low-pass filter
await client.set_subwoofer_filter(True)   # Filter active (normal mode)
await client.set_subwoofer_filter(False)  # Bypass mode (full range)
```

### Constants

```python
from pywiim import (
    SUBWOOFER_CROSSOVER_MIN,  # 30
    SUBWOOFER_CROSSOVER_MAX,  # 250
    SUBWOOFER_LEVEL_MIN,      # -15
    SUBWOOFER_LEVEL_MAX,      # 15
    SUBWOOFER_DELAY_MIN,      # -200
    SUBWOOFER_DELAY_MAX,      # 200
    SUBWOOFER_PHASE_0,        # 0
    SUBWOOFER_PHASE_180,      # 180
)
```

### Device Compatibility

| Device | Support | Notes |
|--------|---------|-------|
| WiiM Ultra | ✅ Full | Original discovery (firmware 5.2+) |
| WiiM Pro | ✅ Full | Tested working (firmware 4.8+) |
| WiiM Pro Plus | ✅ Likely | Untested, same platform as Pro |
| WiiM Amp | ❓ Unknown | May work, needs testing |
| WiiM Mini | ❓ Unknown | May work, needs testing |
| Arylic | ❌ None | Returns "unknown command" |
| Other LinkPlay | ❌ None | Not supported |

**Note**: These endpoints are undocumented and were discovered through reverse engineering. The library auto-detects support on first poll. Always check `player.supports_subwoofer` before using these features.
