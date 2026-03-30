# Home Assistant Integration Guide

> **⚠️ CRITICAL: Do NOT call `async_request_refresh()` in entity methods!**  
> Commands (play, pause, volume, etc.) fire callbacks automatically for instant UI updates.  
> The coordinator's scheduled `refresh()` handles everything else.  
> See [State Management](#state-management---how-it-works) below for details.

## Overview

This guide explains how to integrate the `pywiim` library with Home Assistant's `DataUpdateCoordinator` polling pattern. The library provides polling strategy recommendations and helpers that integrate seamlessly with HA's async architecture.

**Recommended Approach**: Use `Player` class for HA integrations. It provides state caching, HTTP + UPnP event synchronization, convenient properties, and full API access via `player.client`.

## Critical: When to Call `refresh()` vs When NOT To

### ✅ ONLY Call `refresh()` in the Coordinator

**⚠️ CRITICAL: The ONLY place that should call `player.refresh()` is the coordinator's `_async_update_data()` method.**

This is NOT a manual refresh - this is the scheduled polling that catches external changes.

```python
async def _async_update_data(self):
    """Called by HA on schedule (every 5-10 seconds)."""
    await self.player.refresh()  # ✅ Scheduled polling (NOT a manual refresh)
    return {"player": self.player}
```

**This catches:**
- External changes (WiiM app, buttons, voice assistants)
- Track changes
- Group membership changes
- Anything UPnP events might miss

### ❌ NEVER Call `refresh()` or `async_request_refresh()` in Entity Methods

**⚠️ CRITICAL: Entity methods should NEVER manually refresh after commands.**

The integration is calling `async_request_refresh()` after every command - **this is wrong and harmful.**

```python
async def async_media_play(self) -> None:
    """Send play command."""
    player = self.coordinator.data.get("player")
    await player.play()
    # ✅ That's it! State updates via callback (immediate)
    
    # ❌ DO NOT DO THIS:
    # await player.refresh()
    # await self.coordinator.async_request_refresh()
    # These are unnecessary and cause performance issues
```

**Why it's wrong:**
- pywiim fires `on_state_changed` callback immediately after command
- Callback triggers `coordinator.async_update_listeners()`
- UI updates instantly from cached state
- Manual refresh just wastes time and network

### Why This Design?

pywiim uses a **3-tier state update system**:

1. **Optimistic Updates + Callbacks** (immediate, <1ms):
   - `await player.play()` updates cached state immediately
   - Fires `on_state_changed` callback → triggers `coordinator.async_update_listeners()`
   - UI updates instantly from cache

2. **UPnP Events** (immediate when available):
   - Real-time notifications of state changes
   - Automatically merged with cached state
   - Confirms optimistic updates

3. **Coordinator Polling** (5-10 seconds):
   - Scheduled `refresh()` catches everything else
   - External changes (WiiM app, buttons, etc.)
   - Role changes, track changes, etc.
   - **This is the ONLY refresh needed**

**Result:** Entity methods get instant UI updates (callbacks), and coordinator polling catches external changes on schedule. No manual refresh needed anywhere else.

## Critical Concepts

### Group Information: Device API vs Group Object

**⚠️ IMPORTANT: Two different purposes, don't confuse them**

#### Device API - Check Actual State

To know if a device is a master:

```python
# Check role (ONLY way - single source of truth):
player.role       # "master" (updated by refresh)
player.is_master  # True
player.is_slave   # False
player.is_solo    # False
```

#### Group Object - Perform Operations

To perform group operations (volume, mute, playback):

```python
# Group object = glue for operations
if player.group:
    await player.group.set_volume_all(0.5)  # Needs Player objects
    await player.group.mute_all(True)        # Needs Player objects
    
    # group.slaves = list of linked Player OBJECTS (may be empty)
    # This is for operations, NOT for checking if device has slaves
```

**Key difference:**
- `player.role` / `player.is_master` = check if device is master (ONLY way to check)
- `group` object = perform operations (volume, mute, playback)
- `group.slaves` = Player objects for operations (may be empty - don't check this for state)

**Don't:**
- ❌ Check `len(group.slaves)` to see if device has slaves
- ❌ Use `group.slaves` to determine group membership
- ❌ Call `get_device_group_info()` to check role

**Do:**
- ✅ Check `player.role` to see role (ONLY way)
- ✅ Use `group` object only for operations

## State Management - How It Works

### pywiim Manages All State Updates

**You NEVER need to manually refresh after commands.** The library handles all state updates automatically:

#### How Commands Work

```python
# In entity method:
await player.play()
# Internally:
# 1. Sends API call to device
# 2. Updates cached state optimistically (player._status_model)
# 3. Updates state synchronizer (merges with UPnP data)
# 4. Fires callback: player._on_state_changed()
#    → triggers coordinator.async_update_listeners()
#    → UI updates immediately from cache
```

#### What Coordinator Does

```python
# Coordinator's ONLY job for state updates:
async def _async_update_data(self):
    # Scheduled polling (every 5-10 seconds)
    await self.player.refresh()
    return {"player": self.player}
```

**That's it!** The coordinator polls on schedule to catch:
- External changes (WiiM app, physical buttons, etc.)
- Track changes
- Group membership changes
- State confirmation

### Entity Methods: Zero Manual Refresh

```python
# ✅ CORRECT - just call the command
async def async_media_play(self):
    await self.coordinator.data["player"].play()
    # State updates via callback (immediate)
    # NO refresh() needed!
    # NO async_request_refresh() needed!

# ❌ WRONG - manual refresh is unnecessary and harmful
async def async_media_play(self):
    await self.coordinator.data["player"].play()
    await self.coordinator.async_request_refresh()  # ❌ NO!
```

## Quick Reference

### Key Imports

```python
from pywiim import (
    Player,               # High-level API (RECOMMENDED for HA)
    WiiMClient,           # Low-level API (used by Player)
    UpnpClient,           # UPnP client (for events and queue)
    UpnpEventer,          # UPnP event handler
    PollingStrategy,      # Adaptive polling recommendations
    TrackChangeDetector,  # Metadata change detection
    fetch_parallel,      # Parallel execution helper
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.aiohttp_client import async_get_clientsession
```

### Integration Architecture

```
HA Coordinator
    ↓
Player (State Management + HTTP + UPnP) ──→ Uses WiiMClient
    ↓
WiiMClient (HTTP API) ──→ Device
    ↓
UpnpEventer (optional, for events) ──→ Uses UpnpClient
    ↓
UpnpClient ──→ Device (UPnP)
```

### When to Use What

| Feature               | Use                      | Notes                             |
| --------------------- | ------------------------ | --------------------------------- |
| **Basic polling**     | `Player`                 | State caching + HTTP + UPnP sync  |
| **UPnP events**       | `UpnpEventer` + `Player` | Player implements apply_diff()    |
| **Queue management**  | `Player` + `UpnpClient`  | Requires UPnP client              |
| **Polling strategy**  | `PollingStrategy`        | Adaptive interval recommendations |
| **Metadata fetching** | `TrackChangeDetector`    | Only fetch on track change        |
| **Direct API access** | `player.client.*`        | Access all WiiMClient methods     |

## Media Player Service Mapping

### Recommended Service-to-Method Mapping

Map Home Assistant media_player services to pywiim Player methods:

| HA Service | pywiim Method | Notes |
|------------|---------------|-------|
| `media_play` | `player.play()` | Raw API call |
| `media_pause` | `player.pause()` | Raw API call |
| `media_play_pause` | `player.media_play_pause()` | ✅ **Use this** - handles resume correctly |
| `media_stop` | `player.stop()` or `player.pause()` | See webradio note below |
| `media_next_track` | `player.next_track()` | Use `supports_next_track` for feature flag |
| `media_previous_track` | `player.previous_track()` | Use `supports_previous_track` for feature flag |

### Next/Previous Track Support

⚠️ **IMPORTANT**: Use `supports_next_track` and `supports_previous_track` to determine feature support, NOT `queue_count`!

Streaming services (Spotify, Amazon Music, Tidal, etc.) always report `queue_count=0` because they manage their own queues internally. However, next/previous track commands work perfectly.

```python
@property
def supported_features(self) -> MediaPlayerEntityFeature:
    """Return supported features."""
    features = MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.PAUSE
    
    # ✅ CORRECT: Use supports_next_track property
    if self._player.supports_next_track:
        features |= MediaPlayerEntityFeature.NEXT_TRACK
    if self._player.supports_previous_track:
        features |= MediaPlayerEntityFeature.PREVIOUS_TRACK
    
    # ❌ WRONG: Don't use queue_count - Spotify has queue_count=0 but next/prev work!
    # if self._player.queue_count > 0:  # This breaks Spotify!
    #     features |= MediaPlayerEntityFeature.NEXT_TRACK
    
    return features
```

### Implementation Example

```python
class WiiMMediaPlayer(MediaPlayerEntity):
    """WiiM Media Player Entity."""

    async def async_media_play(self) -> None:
        """Send play command."""
        player = self.coordinator.data.get("player")
        await player.play()

    async def async_media_pause(self) -> None:
        """Send pause command."""
        player = self.coordinator.data.get("player")
        await player.pause()

    async def async_media_play_pause(self) -> None:
        """Toggle play/pause (correctly handles resume)."""
        player = self.coordinator.data.get("player")
        await player.media_play_pause()  # ✅ Use convenience method

    async def async_media_stop(self) -> None:
        """Stop playback."""
        player = self.coordinator.data.get("player")
        
        # Option 1: Simple (document the webradio quirk)
        await player.stop()
        
        # Option 2: Handle webradio specially (better UX)
        # STREAMING_SOURCES = ['wifi', 'webradio', 'iheartradio', 'pandora', 'tunein']
        # if player.source and player.source.lower() in STREAMING_SOURCES:
        #     await player.pause()  # Pause works better for web streams
        # else:
        #     await player.stop()

    async def async_media_next_track(self) -> None:
        """Skip to next track."""
        player = self.coordinator.data.get("player")
        await player.next_track()

    async def async_media_previous_track(self) -> None:
        """Skip to previous track."""
        player = self.coordinator.data.get("player")
        await player.previous_track()
```

### Edge Cases & Device Behavior Quirks

#### Issue #102: Play/Pause Restarts Track

**Problem:** Calling `play()` on a paused streaming track (Amazon Music, Spotify, etc.) restarts the track from the beginning instead of resuming.

**Solution:** Use `player.media_play_pause()` method, which automatically calls `resume()` when paused.

**Implementation:**
```python
async def async_media_play_pause(self) -> None:
    """Toggle play/pause."""
    player = self.coordinator.data.get("player")
    await player.media_play_pause()  # ✅ Automatically uses resume() when paused
```

**Why This Works:** The `media_play_pause()` method checks the current play state and:
- When paused → calls `resume()` (continues from current position)
- When playing → calls `pause()`
- When stopped/idle → calls `play()` (starts fresh)

#### Issues #49, #45: WebRadio Stop Doesn't Work

**Problem:** Calling `stop()` on webradio or WiFi streaming sources doesn't keep the device stopped. It immediately returns to "playing" state.

**Solution Options:**

**Option A (Simple):** Just call `stop()` and document the behavior
```python
async def async_media_stop(self) -> None:
    """Stop playback.
    
    Note: Web radio streams may not stay stopped and may resume playing.
    This is a device firmware limitation.
    """
    player = self.coordinator.data.get("player")
    await player.stop()
```

**Option B (Better UX):** Detect streaming sources and use `pause()` instead
```python
# Define at class level
STREAMING_SOURCES = ['wifi', 'webradio', 'iheartradio', 'pandora', 'tunein']

async def async_media_stop(self) -> None:
    """Stop playback."""
    player = self.coordinator.data.get("player")
    
    # Use pause for web streams (stop doesn't work reliably)
    if player.source and player.source.lower() in STREAMING_SOURCES:
        await player.pause()
    else:
        await player.stop()
```

**Recommendation:** Start with Option B for better user experience, especially if you have users who listen to web radio frequently.

#### Why These Behaviors Exist

These quirks originate from the underlying LinkPlay firmware and are present across all LinkPlay-based devices (WiiM, Arylic, Audio Pro, etc.). The pywiim library provides:
- Raw API methods (`play()`, `pause()`, `resume()`, `stop()`) that expose actual device behavior
- Convenience methods (`media_play_pause()`) that handle the quirks intelligently
- Clear documentation so you can choose the right approach for your use case

## HA Polling Pattern

Home Assistant uses `DataUpdateCoordinator` to manage polling:

1. **Coordinator Manages Polling**: HA's coordinator framework schedules updates
2. **Async Methods**: All I/O operations are async and non-blocking
3. **Dynamic Intervals**: Polling intervals can be adjusted based on device state
4. **Concurrent Polling**: Many devices can poll simultaneously

## Why Player for HA?

The `Player` class is **recommended** for HA integrations because:

### ✅ StateSynchronizer (HTTP + UPnP Merging)

- Automatically merges HTTP polling data with UPnP events
- Handles conflicts intelligently (UPnP for real-time, HTTP for metadata)
- Tracks freshness and source availability
- No manual merging needed

### ✅ Convenient Properties for Entities

```python
# With Player - synchronous property access
volume = player.volume_level  # Already 0.0-1.0
title = player.media_title
play_state = player.play_state
shuffle = player.shuffle  # True/False/None (None for external sources like AirPlay)
repeat = player.repeat  # 'one'/'all'/'off'/None (None for external sources)
shuffle_supported = player.shuffle_supported  # Check before using shuffle
repeat_supported = player.repeat_supported  # Check before using repeat
eq_preset = player.eq_preset  # EQ preset name (normalized to Title Case, e.g., "Flat", "Rock")
available_sources = player.available_sources  # List of selectable input sources (smart detection)
wifi_rssi = player.wifi_rssi  # Signal strength in dBm

# With WiiMClient - manual conversion needed
status = await client.get_player_status_model()
volume = status.volume / 100.0  # Manual conversion
title = status.title
```

### ✅ Complete High-Level API

```python
# All common operations are available directly on Player
multiroom = await player.get_multiroom_status()
audio_output = await player.get_audio_output_status()
eq = await player.get_eq()
eq_presets = await player.get_eq_presets()
meta_info = await player.get_meta_info()

# Control helpers
await player.clear_playlist()

# Shuffle and repeat (check support first for external sources)
if player.shuffle_supported:
    await player.set_shuffle(True)  # Preserves current repeat state
if player.repeat_supported:
    await player.set_repeat("all")  # Preserves current shuffle state ("off", "one", "all")
# Note: Both methods abstract the low-level setLoopMode command and handle
# empty/non-JSON responses from devices gracefully.
# Raises WiiMError for external sources (AirPlay, Bluetooth, etc.)
await player.set_led(True)
await player.set_led_brightness(50)
await player.set_channel_balance(0.0)
await player.sync_time()

# Bluetooth workflow
history = await player.get_bluetooth_history()
await player.connect_bluetooth_device("AA:BB:CC:DD:EE:FF")
await player.disconnect_bluetooth_device()
status = await player.get_bluetooth_pair_status()
devices = await player.scan_for_bluetooth_devices(duration=5)

# Timer and alarm (WiiM only)
await player.set_sleep_timer(1800)  # Sleep in 30 minutes
remaining = await player.get_sleep_timer()
await player.cancel_sleep_timer()

# Alarm clock (3 slots: 0-2)
from pywiim import ALARM_TRIGGER_DAILY, ALARM_OP_PLAYBACK

await player.set_alarm(
    alarm_id=0,
    trigger=ALARM_TRIGGER_DAILY,
    operation=ALARM_OP_PLAYBACK,
    time="070000",  # 7:00 AM UTC
)
alarm = await player.get_alarm(0)
alarms = await player.get_alarms()
await player.delete_alarm(0)

# Connection info
host = player.host
port = player.port
timeout = player.timeout
```

**Note**: For advanced use cases, you can still access `player.client.*` for methods not yet promoted to Player.

#### Alarm Time Conversion (WiiM only)

Alarm times must be in UTC. For Home Assistant integrations, convert local time to UTC:

```python
from datetime import datetime
import pytz

# Convert local time to UTC for alarm
local_tz = pytz.timezone('America/New_York')
local_time = local_tz.localize(datetime(2025, 1, 17, 7, 30))
utc_time = local_time.astimezone(pytz.UTC)
time_str = utc_time.strftime("%H%M%S")  # "113000" for 7:30 AM EST

await player.set_alarm(
    alarm_id=0,
    trigger=ALARM_TRIGGER_DAILY,
    operation=ALARM_OP_PLAYBACK,
    time=time_str,
)
```

### ✅ Built-in UPnP Event Integration

- `Player` implements `apply_diff()` for `UpnpEventer`
- StateSynchronizer automatically merges UPnP events with HTTP polling
- No manual state merging required

### ✅ Group Management

- Built-in `Group` object support
- Role computed from group membership
- Group operations available

## Basic Integration Pattern

### 1. Initialize Coordinator with Player

```python
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from pywiim import Player, WiiMClient, PollingStrategy
from datetime import timedelta
import asyncio
import time

class WiiMCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, host):
        # Initialize coordinator with default interval
        super().__init__(
            hass,
            logger,
            name=f"WiiM {host}",
            update_interval=timedelta(seconds=5),  # Default, will adapt
        )

        # Create library client with HA's shared session
        session = async_get_clientsession(hass)
        client = WiiMClient(host=host, session=session)

        # Create Player (wraps client with state management)
        # Provide player_finder callback for automatic group linking
        # pywiim will automatically link Player objects when groups are detected
        # Provide all_players_finder for WiFi Direct multiroom role inference
        self.player = Player(
            client,
            player_finder=self._find_player_by_host,  # Enables automatic linking
            all_players_finder=self._get_all_players,  # Enables WiFi Direct role inference
        )

        # Detect capabilities and create polling strategy
        # Note: This is async, so do it in async_setup_entry or first update
        self._capabilities = {}
        self._polling_strategy = None
        self._strategy_initialized = False
    
    def _find_player_by_host(self, host: str):
        """Find Player object by host/IP (for automatic group linking).
        
        This callback is used by pywiim to automatically link Player objects
        when groups are detected during refresh(). Returns None if player
        not found (e.g., device not configured in HA).
        
        Note: For WiFi Direct multiroom (legacy LinkPlay devices with 10.10.10.x
        internal IPs), pywiim automatically handles UUID-based matching using
        all_players_finder - you only need to implement IP lookup here.
        
        Args:
            host: IP address of the player to find.
            
        Returns:
            Player object if found, None otherwise.
        """
        # Example: Get player from coordinator registry
        # In HA, you'd typically get this from a central registry
        # that maps host -> coordinator -> player
        # return player_registry.get(host)
        return None  # Implement based on your coordinator registry
    
    def _get_all_players(self):
        """Return all Player objects (REQUIRED for WiFi Direct multiroom).
        
        This callback is CRITICAL for legacy LinkPlay devices that use WiFi Direct
        multiroom (firmware < 4.2.8020). These devices:
        - Slaves join master's internal WiFi Direct network and get 10.10.10.x IPs
        - Are no longer reachable from LAN at their original IPs
        - Slaves report "solo" when queried (they don't know they're in a group)
        
        pywiim uses this callback to:
        1. Link slaves by UUID when IP matching fails (master's getSlaveList returns
           10.10.10.x IPs that HA doesn't know, but includes UUIDs for matching)
        2. Check if any known master lists this device as a slave (correct role detection)
        
        Returns:
            List of all Player objects known to the integration.
        """
        # Example: Return all players from coordinator registry
        # return [coord.player for coord in coordinator_registry.values()]
        return []  # Implement based on your coordinator registry
```

### 2. Initialize Polling Strategy (Async)

```python
async def async_setup_coordinator(self):
    """Initialize coordinator with capabilities and polling strategy."""
    # Detect device capabilities via client
    self._capabilities = await self.player.client._detect_capabilities()

    # Create polling strategy
    self._polling_strategy = PollingStrategy(self._capabilities)
    self._strategy_initialized = True

    # Track last fetch times for conditional polling
    # Initialize to 0 so first check triggers immediate fetch (startup)
    self._last_device_info_check = 0
    self._last_multiroom_check = 0
    self._last_eq_info_check = 0
    # Note: Audio output status is automatically fetched by player.refresh() on startup
    # EQ presets and preset stations are automatically fetched by player.refresh() on track change
```

### 3. Implement Adaptive Polling with Player

```python
async def _async_update_data(self):
    """HA calls this method at the update_interval."""
    # Initialize strategy on first update if needed
    if not self._strategy_initialized:
        await self.async_setup_coordinator()

    # Refresh player state (updates cache and StateSynchronizer)
    try:
        await self.player.refresh()
    except Exception as e:
        logger.warning("Failed to refresh player state: %s", e)
        # Return cached data if available
        if self.data:
            return self.data
        # Or raise UpdateFailed to trigger HA's retry logic
        raise UpdateFailed(f"Error communicating with device: {e}")

    # Get current state for adaptive polling (from cached properties)
    # IMPORTANT: Use THIS player's state, not the group's state
    # Each player should be polled independently based on its own state
    role = self.player.role if self.player.group else "solo"
    is_playing = self.player.play_state in ("play", "playing")  # THIS player's state

    # Get recommended polling interval from library
    # This returns the optimal interval for THIS player based on its own state
    interval = self._polling_strategy.get_optimal_interval(role, is_playing)

    # Update HA's polling interval dynamically
    if self.update_interval.total_seconds() != interval:
        self.update_interval = timedelta(seconds=interval)
        logger.debug("Updated polling interval to %s seconds", interval)

    # Build fetch tasks for additional data (conditional fetching)
    now = time.time()
    fetch_tasks = []
    fetch_flags = {}  # Track which fetches were added to process results correctly

    # Device info (every 60s) - use cached if recent
    if self._polling_strategy.should_fetch_device_info(self._last_device_info_check, now):
        fetch_tasks.append(self.player.get_device_info())
        fetch_flags["device_info"] = True
        self._last_device_info_check = now
    else:
        fetch_flags["device_info"] = False

    # Multiroom info (every 15s)
    if self._polling_strategy.should_fetch_multiroom(self._last_multiroom_check, now):
        fetch_tasks.append(self.player.get_multiroom_status())
        fetch_flags["multiroom"] = True
        self._last_multiroom_check = now
    else:
        fetch_flags["multiroom"] = False

    # EQ info (every 60s, if supported) - only fetch EQ band values
    # Note: EQ presets are automatically fetched by player.refresh() on track change
    eq_supported = self._capabilities.get("supports_eq", None)
    if self._polling_strategy.should_fetch_eq_info(
        self._last_eq_info_check, eq_supported, now
    ):
        fetch_tasks.append(self.player.get_eq())  # EQ band values only
        # EQ presets are automatically refreshed by player.refresh() on track change
        fetch_flags["eq"] = True
        self._last_eq_info_check = now
    else:
        fetch_flags["eq"] = False

    # Note: Preset stations are automatically fetched by player.refresh() on track change
    # No need to manually fetch them here - the library handles it

    # Audio output status is automatically fetched by player.refresh() on startup
    # No need to manually fetch it here - the library handles it

    # Execute additional fetches in parallel (if any)
    additional_data = {}
    if fetch_tasks:
        results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

        # Process results in order they were added to fetch_tasks
        result_idx = 0

        # Device info (if fetched)
        if fetch_flags.get("device_info", False):
            device_info = results[result_idx] if not isinstance(results[result_idx], Exception) else None
            if device_info:
                additional_data["device_info"] = device_info
            result_idx += 1

        # Multiroom (if fetched)
        if fetch_flags.get("multiroom", False):
            multiroom = results[result_idx] if not isinstance(results[result_idx], Exception) else None
            if multiroom:
                additional_data["multiroom"] = multiroom
            result_idx += 1

        # EQ info (if fetched) - only EQ band values (EQ presets handled by refresh() on track change)
        if fetch_flags.get("eq", False):
            eq_status = results[result_idx] if not isinstance(results[result_idx], Exception) else None
            # EQ presets are automatically refreshed by player.refresh() on track change
            result_idx += 1


    # Get preset names for source list (WiiM devices only)
    preset_names = []
    max_preset_slots = 0
    if self.player.supports_presets:
        if self.player.presets_full_data and self.player.presets:
            # WiiM devices: Get preset names
            preset_names = [
                preset.get("name", f"Preset {preset.get('number')}")
                for preset in self.player.presets
                if preset.get("name")  # Only include presets with names
            ]
        elif not self.player.presets_full_data:
            # LinkPlay devices: Only count available, not names
            max_preset_slots = await self.player.client.get_max_preset_slots()
    
    # Return data dict for entities (use Player properties)
    return {
        # Player state (from cached properties - already refreshed)
        "player": self.player,  # Pass Player object for entity access
        "volume_level": self.player.volume_level,
        "is_muted": self.player.is_muted,
        "play_state": self.player.play_state,
        "media_title": self.player.media_title,  # Falls back to URL filename
        "media_artist": self.player.media_artist,
        "media_album": self.player.media_album,
        "media_content_id": self.player.media_content_id,  # URL if playing from play_url()
        "media_image_url": self.player.media_image_url,
        "media_position": self.player.media_position,
        "media_duration": self.player.media_duration,
        "media_sample_rate": self.player.media_sample_rate,
        "media_bit_depth": self.player.media_bit_depth,
        "media_bit_rate": self.player.media_bit_rate,
        "media_codec": self.player.media_codec,
        "upnp_health_status": self.player.upnp_health_status,
        "upnp_is_healthy": self.player.upnp_is_healthy,
        "upnp_miss_rate": self.player.upnp_miss_rate,
        "source": self.player.source,
        "available_sources": self.player.available_sources,  # List of selectable input sources (smart detection)
        "presets": self.player.presets,  # Full preset data (WiiM) or None (LinkPlay)
        "preset_names": preset_names,  # Preset names for source list (WiiM only)
        "max_preset_slots": max_preset_slots,  # Preset count (LinkPlay devices)
        "shuffle": self.player.shuffle,
        "repeat": self.player.repeat,
        "eq_preset": self.player.eq_preset,
        "wifi_rssi": self.player.wifi_rssi,
        "role": role,
        # Additional data from conditional fetching
        **additional_data,
    }
```

**Note on `source`, `available_sources`, `presets`, and `eq_presets`:**

- **`source`**: Current source id (stable identifier, e.g., `"airplay"`, `"spotify"`, `"line_in"`, `"network"`). For comparisons, compare ids (e.g., `player.source == "airplay"`).
- **`source_name`**: Current source display name (UI-ready, e.g., "AirPlay", "Spotify", "Line In", "Network").

- **`available_sources`**: Returns user-selectable physical inputs plus the current source (when active):

  - **Always included**: Physical/hardware sources (Bluetooth, USB, Line In, Optical, Coax, AUX, HDMI) - user-selectable
  - **Conditionally included**: Current source (when active) - includes streaming services and multi-room follower sources. NOT user-selectable but included for correct UI state display
  - **NOT included**: Inactive streaming services - can't be manually selected and aren't currently playing
  - **Always excluded**: WiFi (it's the network connection, not a selectable source)
  
  This filtering shows only physical inputs that users can manually select, plus the current source if it's not a physical input (e.g., AirPlay, Spotify, or a multi-room follower name like "Master Bedroom"). This ensures Home Assistant's dropdown shows selectable options while correctly displaying the current state. You can directly use `player.available_sources` without additional filtering.

- **`presets`**: List of playback presets (radio stations, saved favorites) from cached state. Each preset is a dictionary with `number`, `name`, `url`, and `picurl` fields. Automatically fetched by `player.refresh()` on track change or periodically (every 60s). Returns `None` if presets not supported or not available. See [Using Playback Presets](#using-playback-presets) section below for details.

- **`eq_presets`**: List of available EQ preset names with "Off" as the first option (e.g., `["Off", "Flat", "Rock", "Jazz", ...]`). The "Off" option indicates EQ is disabled (audio bypass). Fetched every 60 seconds when EQ is supported.
  
- **`eq_preset`**: Current EQ preset name, or "Off" if EQ is disabled. Normalized to Title Case to match the format from `eq_presets`. When EQ is off (disabled/bypassed), this returns "Off" instead of the last-used preset, ensuring accurate UI representation. This ensures consistency - if `eq_presets` returns `["Off", "Flat", "Acoustic", ...]`, then `eq_preset` will return `"Off"` or `"Flat"` etc., making comparisons straightforward.

- **Parametric EQ (PEQ)** – On WiiM devices, the full LV2 PEQ API is available via `player.client` when `player.client.capabilities.get("supports_peq")` is True. This provides 10-band parametric EQ per source, stereo/L-R modes, and custom preset save/load. See [API_REFERENCE.md – Parametric EQ (PEQ)](API_REFERENCE.md#parametric-eq-peq--wiim-only). (Contribution: [jeromeof](https://github.com/jeromeof), [PR #12](https://github.com/mjcumming/pywiim/pull/12).)

## Advanced Patterns

### Track Change Detection for Metadata

```python
from pywiim import TrackChangeDetector

class WiiMCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, host):
        # ... initialization ...
        self._track_detector = TrackChangeDetector()

    async def _async_update_data(self):
        # Refresh player state
        await self.player.refresh()

        # Check if track changed (for metadata fetching)
        # Note: track_changed() parameter is named 'artwork' but accepts cover_url field
        # Note: Artwork URLs are automatically retrieved from getMetaInfo when missing
        #       from getPlayerStatusEx - no manual fetching needed for artwork
        track_changed = self._track_detector.track_changed(
            self.player.media_title,
            self.player.media_artist,
            self.player.source,
            self.player.media_image_url,  # Passed as 'artwork' parameter
        )

        # Fetch metadata only on track change (for additional metadata like audio quality)
        # Artwork URL is already included in player.media_image_url automatically
        metadata_supported = self._capabilities.get("supports_metadata", None)
        if self._polling_strategy.should_fetch_metadata(track_changed, metadata_supported):
            try:
                metadata = await self.player.get_meta_info()
            except Exception:
                metadata = None
        else:
            metadata = self.data.get("metadata") if self.data else None

        return {
            # ... player state ...
            "metadata": metadata,
        }
```

### Parallel Execution Helper

```python
from pywiim import fetch_parallel

async def _async_update_data(self):
    # Refresh player state first
    await self.player.refresh()

    # Build additional fetch tasks
    tasks = [
        self.player.get_device_info(),
        self.player.get_multiroom_status(),
    ]

    # Execute in parallel with error handling
    results = await fetch_parallel(*tasks, return_exceptions=True)

    # Process results
    device_info = results[0] if not isinstance(results[0], Exception) else None
    multiroom = results[1] if not isinstance(results[1], Exception) else {}
```

## Polling Interval Recommendations

The library's `PollingStrategy` provides these recommendations:

| Device State | WiiM Devices | Legacy Devices |
| ------------ | ------------ | -------------- |
| **Playing**  | 5 seconds    | 3 seconds      |
| **Idle**     | 5 seconds    | 15 seconds     |
| **Slave**    | 5 seconds    | 10 seconds     |

**Note:** Modern WiiM devices use a hybrid position estimation approach where position is estimated locally and corrected via periodic polls. This allows for less frequent polling (5 seconds) while maintaining smooth position updates. The previous 1-second interval is no longer needed.

These intervals are automatically recommended based on:

- Device capabilities (WiiM vs Legacy)
- Device role (master/slave/solo)
- Playback state (playing vs idle)

### Multi-Player Polling (IMPORTANT)

**Each player must be polled independently based on its own state.**

When managing multiple players (in groups or standalone):

✅ **Correct:** Each player has its own coordinator and uses its own state:
```python
# Each coordinator polls its own player independently
for coordinator in coordinators:
    player = coordinator.data["player"]
    is_playing = player.play_state in ("play", "playing")  # THIS player's state
    interval = strategy.get_optimal_interval(player.role, is_playing)
    # Poll this player at its own interval
```

❌ **Wrong:** Using master's state for all players:
```python
# DON'T do this - causes all players to poll fast when master is playing
master_playing = master.play_state in ("play", "playing")
for coordinator in coordinators:
    player = coordinator.data["player"]
    interval = strategy.get_optimal_interval(player.role, master_playing)  # ❌ Wrong!
```

**Why This Matters:**
- Idle players don't need fast polling (wastes resources)
- Each player's state changes independently
- Group members can have different states (master playing, slaves idle)
- Prevents unnecessary network traffic and device load

## Conditional Fetching Intervals

| Data Type         | Interval        | Trigger                                   |
| ----------------- | --------------- | ----------------------------------------- |
| **Player Status** | Always          | Every poll cycle (via `player.refresh()`) |
| **Device Info**   | 60 seconds      | Health check                              |
| **Multiroom**     | 15 seconds      | + Activity triggers                       |
| **EQ Info**       | 60 seconds      | If supported                              |
| **Audio Output**  | 15 seconds      | If supported                              |
| **Subwoofer**     | 60 seconds      | If supported (WiiM only)                  |
| **Metadata**      | On track change | Only if supported                         |

## Error Handling

```python
async def _async_update_data(self):
    try:
        # Refresh player state
        await self.player.refresh()
    except Exception as e:
        logger.warning("Failed to update: %s", e)

        # Return cached data if available (Player caches state)
        if self.data:
            return self.data

        # Or raise UpdateFailed to trigger HA's retry logic
        raise UpdateFailed(f"Error communicating with device: {e}")

    # Return data using Player properties
    return {
        "player": self.player,
        "volume_level": self.player.volume_level,
        # ... other properties ...
    }
```

## Protocol and Port Detection

### Automatic Detection (Recommended)

**⚠️ IMPORTANT: pywiim automatically detects protocol (HTTP/HTTPS) and port. The integration should NOT pass a port unless it has a previously discovered endpoint.**

**Simplest Pattern (Recommended):**

```python
from homeassistant.helpers.aiohttp_client import async_get_clientsession

session = async_get_clientsession(hass)
# Just pass host - pywiim figures out protocol and port automatically
client = WiiMClient(host="192.168.1.100", session=session)
```

**What pywiim does:**
- Automatically probes standard combinations (HTTPS 443, HTTPS 4443, HTTPS 8443, HTTP 80, HTTP 8080)
- Caches the working endpoint permanently
- Handles all device types (WiiM, Arylic, Audio Pro, LinkPlay)

**Why this works:**
- Devices use consistent protocol/port combinations
- pywiim probes once and caches forever
- Works for all device types without configuration

### Optimized Pattern (Optional, for Faster Startup)

If you want to avoid probing on every startup, you can persist the discovered endpoint:

```python
from urllib.parse import urlparse
from homeassistant.helpers.aiohttp_client import async_get_clientsession

session = async_get_clientsession(hass)

# Check if we have a cached endpoint from previous discovery
cached_endpoint = entry.data.get("endpoint")
if cached_endpoint:
    # Parse cached endpoint and pass port/protocol
    parsed = urlparse(cached_endpoint)
    client = WiiMClient(
        host=entry.data["host"],
        port=parsed.port,
        protocol=parsed.scheme,
        session=session
    )
else:
    # First time - let pywiim probe automatically
    client = WiiMClient(host=entry.data["host"], session=session)

# After first successful connection, persist the discovered endpoint
# (Do this in async_setup_entry after first refresh)
if not cached_endpoint:
    await client.get_player_status()  # Triggers probe
    discovered = client.discovered_endpoint  # e.g., "http://192.168.0.210:80"
    if discovered:
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, "endpoint": discovered}
        )
```

**Important Notes:**
- ✅ **DO**: Pass only `host` if you don't have a cached endpoint
- ✅ **DO**: Persist `client.discovered_endpoint` after first connection
- ✅ **DO**: Pass `port` and `protocol` if you have a cached endpoint
- ❌ **DON'T**: Default to `port=443` - many devices use HTTP on port 80
- ❌ **DON'T**: Pass a port without a protocol unless you're sure

**What pywiim does when port is specified:**
- If `port=443` is specified: Tries HTTPS on 443 first, then falls back to standard probe list (including HTTP on 80)
- If `port=80` is specified: Tries HTTP on 80 first, then falls back to standard probe list (including HTTPS on 443)
- This ensures devices are found even if the wrong port is specified

## HTTP Client Session Management

### HA Provides HTTP Session Helper

Home Assistant provides `async_get_clientsession(hass)` from `homeassistant.helpers.aiohttp_client` which returns a shared aiohttp `ClientSession` for connection pooling and resource management.

**Usage in Integration:**

```python
from homeassistant.helpers.aiohttp_client import async_get_clientsession

session = async_get_clientsession(hass)
client = WiiMClient(host="192.168.1.100", session=session)
player = Player(client)  # Player uses the client with shared session
```

**Library Support:**

- ✅ Library supports this via optional `session` parameter in `WiiMClient.__init__()`
- ✅ If no session provided, library creates its own `aiohttp.ClientSession`
- ✅ This allows HA integration to use HA's shared session for connection pooling
- ✅ Library remains framework-agnostic (works without HA session)

## UPnP Client Setup for Events and Queue Management

The UPnP client is used for two purposes:

1. **Event Subscriptions** (via `UpnpEventer`) - Real-time state updates
2. **Queue Management** (via `Player`) - Adding/inserting items to playback queue

**Setup Pattern:**

```python
from pywiim import Player, WiiMClient
from pywiim.upnp import UpnpClient, UpnpEventer

class WiiMCoordinator(DataUpdateCoordinator):
    async def async_setup(self):
        # Create HTTP client
        session = async_get_clientsession(self.hass)
        client = WiiMClient(host=self.host, session=session)

        # Get device info for UUID
        device_info = await client.get_device_info_model()

        # Create UPnP client (required for events and queue management)
        description_url = f"http://{self.host}:49152/description.xml"
        self.upnp_client = await UpnpClient.create(
            self.host,
            description_url,
        )

        # Create Player with UPnP client (for queue management + events)
        self.player = Player(
            client,
            upnp_client=self.upnp_client,
        )

        # Create UpnpEventer with same UPnP client (for real-time events)
        self.eventer = UpnpEventer(
            self.upnp_client,  # Share same UPnP client
            self.player,  # Player implements apply_diff() for state updates
            device_info.uuid,
            state_updated_callback=self._on_upnp_event,
        )

        # Start UPnP event subscriptions
        await self.eventer.start()

    def _on_upnp_event(self):
        """Called when UPnP event received."""
        # Player's StateSynchronizer automatically merges UPnP event
        # Trigger coordinator update to refresh entity state
        self.async_update_listeners()
```

**Key Points:**

- ✅ **One UPnP client shared** between `UpnpEventer` (events) and `Player` (queue)
- ✅ **Player implements apply_diff()** - StateSynchronizer merges UPnP events with HTTP polling
- ✅ **Integration creates UPnP client** - Not HA core, not pywiim
- ✅ **Lifecycle managed by integration** - Integration owns the UPnP client
- ✅ **Matches existing HA patterns** - Same as Samsung TV, DLNA DMR integrations

## StateSynchronizer Benefits

The `Player` class uses `StateSynchronizer` to intelligently merge HTTP polling and UPnP events:

### Automatic Conflict Resolution

- **Real-time fields** (play_state, volume): UPnP preferred (more timely)
- **Position/Duration**: UPnP provides initial values when track starts, then local timer estimates position during playback with periodic HTTP polling to correct drift
- **Metadata fields** (title, artist, album): UPnP preferred **when it has a sane value** (fast on track changes; required for Spotify). HTTP supplements/fills gaps when UPnP metadata is empty/placeholder (e.g., Bluetooth AVRCP via `getMetaInfo`).
- **Artwork URL**: Automatically retrieved from `getMetaInfo` endpoint when missing from `getPlayerStatusEx` - no manual fetching needed
- **Cover Art Images**: pywiim can fetch and cache cover art images directly - use `player.fetch_cover_art()` or `player.get_cover_art_bytes()` for reliable image serving
- **Source field**: HTTP preferred (more accurate)

### Freshness Tracking

- Tracks when each field was last updated from each source
- Considers data "fresh" based on field-specific windows
- Falls back to available source if one becomes stale

### Source Availability

- Tracks HTTP and UPnP source health
- Handles cases where one source is unavailable
- Automatically recovers when source becomes available again

**Result**: You get the best of both worlds - real-time UPnP updates for play_state/volume, UPnP initial position/duration on track start with local timer estimation during playback (periodic HTTP polling corrects drift), reliable HTTP data for metadata (except Spotify), all automatically merged.

## Queue Management

### Overview

Queue management allows adding media to the playback queue instead of replacing the current track. This requires UPnP AVTransport actions, which are only available via the UPnP client.

**Supported Operations:**

- `add_to_queue(url, metadata="")` - Add URL to end of queue
- `insert_next(url, metadata="")` - Insert URL after current track
- `play_url(url, enqueue="add|next|replace|play")` - Play URL with optional enqueue support

### Setup

Queue management requires:

1. **UPnP client** - Created by integration (see UPnP Client section above)
2. **Player with UPnP client** - Pass `upnp_client` to `Player.__init__()`

```python
# In coordinator setup
self.upnp_client = await UpnpClient.create(host, description_url)
self.player = Player(client, upnp_client=self.upnp_client)
```

### Implementation in Media Player Entity

```python
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEnqueue,
    ATTR_MEDIA_ENQUEUE,
    ATTR_MEDIA_ANNOUNCE,
)

class WiiMMediaPlayer(MediaPlayerEntity):
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self._attr_supported_features = (
            MediaPlayerEntityFeature.PLAY_MEDIA
            | MediaPlayerEntityFeature.MEDIA_ENQUEUE  # Enable queue support
            # Note: Shuffle/repeat features can be dynamic based on source
            # See "Source-Aware Shuffle and Repeat Control" section
            | MediaPlayerEntityFeature.SHUFFLE_SET  # May not work for AirPlay, Bluetooth, etc.
            | MediaPlayerEntityFeature.REPEAT_SET  # May not work for AirPlay, Bluetooth, etc.
            | ...  # other features
        )

    async def async_play_media(
        self,
        media_type: str,
        media_id: str,
        **kwargs: Any,
    ) -> None:
        """Play media with optional enqueue and announcement support."""
        # Handle announcements (TTS, doorbell sounds, etc.)
        announce = kwargs.get(ATTR_MEDIA_ANNOUNCE, False)
        if announce:
            # Integration must resolve media_id (e.g. media_source://tts?...)
            # to a URL the device can fetch before calling the library.
            url = ...  # e.g. media_source.async_resolve_media() then async_process_play_media_url()
            await self.coordinator.player.play_notification(url)
            return

        # Handle queue management
        enqueue: MediaPlayerEnqueue | None = kwargs.get(ATTR_MEDIA_ENQUEUE)

        if enqueue and enqueue != MediaPlayerEnqueue.REPLACE:
            # Use queue management (requires UPnP client)
            if not self.coordinator.player._upnp_client:
                raise HomeAssistantError(
                    "Queue management requires UPnP client. "
                    "Ensure UPnP is properly configured."
                )

            if enqueue == MediaPlayerEnqueue.ADD:
                await self.coordinator.player.add_to_queue(media_id)
            elif enqueue == MediaPlayerEnqueue.NEXT:
                await self.coordinator.player.insert_next(media_id)
            elif enqueue == MediaPlayerEnqueue.PLAY:
                # Play immediately (uses HTTP API)
                await self.coordinator.player.play_url(media_id)
        else:
            # Default: replace current (HTTP API)
            await self.coordinator.player.play_url(media_id)
```

### Notification/Announcement Support

The `play_notification(url)` method uses the device's built-in `playPromptUrl` command. The library accepts only a **URL string that the device can HTTP GET** (e.g. `https://host/path/to/audio.mp3`). The integration is responsible for resolving any platform-specific IDs (e.g. Home Assistant `media_source://` or TTS proxy URLs) to such a URL before calling `play_notification(url)`.

#### How It Works (device firmware)

When the **prompt path** is used (`playPromptUrl`), the device firmware is expected to:
1. Lower current playback volume (if something is playing)
2. Play the notification audio
3. Restore original volume and resume after completion

**Behavior is firmware- and source-dependent.** On some devices or sources, the prompt path may not play the notification or may not resume; the library falls back to `play_url` when appropriate, or the integration can call `play_notification(url, force_interrupt=True)` for TTS to guarantee audible playback.

#### Home Assistant Service Calls

```yaml
# TTS announcement
service: tts.speak
data:
  entity_id: media_player.wiim_pro
  message: "Your package has been delivered"
  options:
    announce: true

# Media player announcement
service: media_player.play_media
target:
  entity_id: media_player.wiim_pro
data:
  media_content_id: "https://example.com/doorbell.mp3"
  media_content_type: "music"
  announce: true
```

#### Limitations

- **Prompt path behavior is firmware-dependent** — duck, play, and resume may not work on all devices or sources; the library falls back to `play_url` when needed, or use `force_interrupt=True` for TTS.
- **Only works in NETWORK or USB playback mode** (for prompt path) — Line In, Optical, Bluetooth may not support prompt; fallback still plays the URL.
- **Requires firmware 4.6.415145+** for prompt command support.
- **Spotify Connect and some radio sources** — firmware may not play or resume with `playPromptUrl`; use `play_notification(url, force_interrupt=True)` for reliable TTS.

#### For integration authors: TTS / announcement URL must be fetchable by the device

If the integration resolves a TTS or media_source ID to a URL and calls `play_notification(url)` but no audio is heard, the device may be **unable to fetch that URL** (e.g. 401 from an authenticated TTS proxy). That is an **integration and HA configuration** concern, not library behaviour: the library only sends the URL to the device. The integration should ensure the URL is reachable by the device without auth (e.g. HA trusted_networks / TTS proxy configuration). See [Home Assistant HTTP documentation](https://www.home-assistant.io/docs/configuration/http/) for auth and network options.

#### TTS announcements not working? (troubleshooting)

If TTS or announcements play in the browser but not on the device, check the following:

1. **Resolve media_source to a real URL**  
   Do not pass `media_source://tts?message=...` to the device. The device cannot fetch that. Resolve it (e.g. `media_source.async_resolve_media()` and `async_process_play_media_url()`) to a URL the device can HTTP GET, then call `player.play_notification(url)`.

2. **Use the player method, not the client**  
   Call `player.play_notification(url)` so the library’s source-aware logic runs. If the integration calls `client.play_notification(url)` (raw `playPromptUrl`) directly, the library’s fallback is skipped: on sources like `linkplay_radio` or Spotify, `playPromptUrl` may return OK but produce no audible prompt; the player method falls back to `play_url` so the notification is heard.

3. **Force interrupt for guaranteed TTS**  
   If the device ducks but no speech is heard (or nothing happens with Spotify Connect), use `player.play_notification(url, force_interrupt=True)`. That always uses `play_url`, interrupting current playback so the TTS is guaranteed audible. Use for TTS when the native prompt path is unreliable.

4. **URL must be reachable by the device**  
   The WiiM fetches the URL itself. If the TTS proxy or HA requires auth, the device gets 401 and no audio. Configure HA so the URL is fetchable from the device’s IP (e.g. trusted_networks, or TTS proxy without auth for the LAN).

#### Library contract

- **`play_notification(url)`** accepts only a URL string that the **device** can HTTP GET. The integration must not pass `media_content_id`, `media_source://` IDs, or any other platform-specific identifier; it must resolve those to a fetchable URL before calling the library.

#### What the WiiM (HA) integration must do

The integration, not the library, is responsible for:

1. **Resolving `media_content_id` before calling the library**  
   When `media_player.play_media` is called with `announce: true`, `media_content_id` may be a Home Assistant media source (e.g. `media-source://tts?message=...`). The device cannot fetch that. The integration must resolve it (e.g. via `media_source.async_resolve_media()` and `async_process_play_media_url()`) to a URL the device can GET, then call `player.play_notification(url)` with that URL.

2. **Using HA media_player constants and patterns**  
   Use `ATTR_MEDIA_ANNOUNCE`, `ATTR_MEDIA_EXTRA`, and the same resolution flow for both announce and normal play (e.g. resolve media_source once at the start of `async_play_media`, then branch on announce vs play). Follow HA/Sonos-style patterns for the service schema and kwargs.

3. **Ensuring the URL is reachable by the device**  
   If the resolved URL is an HA TTS proxy or similar and requires auth, the device will get 401. The integration cannot fix that in code; the user must configure HA (e.g. trusted_networks, TTS proxy access) so the URL is fetchable by the device without cookies.

#### Integration work list (TTS / announcements)

- [ ] **Resolve `media_content_id` before calling the library** — In `async_play_media`, when `announce: true`, resolve `media_content_id` (e.g. `media_source://tts?...`) via `media_source.async_resolve_media()` and `async_process_play_media_url()` to a URL the device can GET. Never pass the raw media_source ID to `play_notification()`.
- [ ] **Use `player.play_notification(url)` for announce** — Call `coordinator.player.play_notification(resolved_url)`, not `client.play_notification()`, so the library’s source-aware fallback runs (and linkplay_radio / Spotify get audible TTS via `play_url` when the prompt path fails).
- [ ] **Optional: `force_interrupt=True` for TTS** — For TTS (or when `announce: true` with TTS content), consider calling `player.play_notification(resolved_url, force_interrupt=True)` so TTS is always heard even when the prompt path does not play or resume. Optionally expose a user option (e.g. “Prefer reliable TTS (interrupt playback)”).
- [ ] **Release notes** — Do not claim “auto-resumes” or “no interruption” for announcements; state that prompt behavior is firmware-dependent and that fallback / `force_interrupt` ensure audible TTS when the prompt path is unreliable.
- [ ] **Working TTS YAML example** — Provide a minimal, copy-paste example (e.g. `media_player.play_media` with `announce: true` and TTS, or `tts.speak` with the WiiM as target) and a note that playback may be interrupted and not resume.
- [ ] **Document TTS proxy / device access** — In integration docs, note that the TTS proxy URL must be reachable by the device (e.g. trusted_networks, or no auth for LAN) so the device does not get 401 when fetching the URL.

#### Benefits (when the integration passes a fetchable URL)

- **Simple**: Call `play_notification(url)` (or `play_notification(url, force_interrupt=True)` for TTS when prompt path is unreliable); no state management needed.
- **Audible**: Fallback and `force_interrupt` ensure the notification is heard when the prompt path does not work.
- **Transparent**: Result reports `method_used` and `likely_interrupted` so the integration can log or adapt.

### Error Handling

Queue management methods will raise `WiiMError` if:

- UPnP client is not available
- UPnP AVTransport service is not available
- Device doesn't support queue operations

Announcement playback will attempt state restoration even if playback fails. Expected warnings (e.g., streaming service source restore) are logged but don't raise exceptions.

#### Fire-and-Forget URL Playback

**Important:** The `play_url()` method uses a fire-and-forget API. The LinkPlay device accepts URLs without validation, meaning:

- **Invalid URLs don't raise exceptions** - non-existent domains, 404 errors, wrong protocols (ftp://), empty strings, or non-audio files are all accepted by the API
- **Device attempts playback asynchronously** - the API returns immediately before verifying if the URL is actually playable
- **Failed playback results in 'pause' or 'idle' state** - the device will try to play and silently fail if the URL doesn't work

##### What Works Without Errors

| URL Type | API Response | Device State |
|----------|-------------|--------------|
| Non-existent domain | ✅ Accepted | `pause` |
| 404 Not Found | ✅ Accepted | `pause` |
| Invalid protocol (ftp://) | ✅ Accepted | `pause` |
| Empty string | ✅ Accepted | `pause` |
| Non-audio file (.txt, .html) | ✅ Accepted | `idle` |

##### Detecting Playback Failures

If your integration needs to verify playback actually started, check the state after a delay:

```python
async def async_play_media(
    self,
    media_type: str,
    media_id: str,
    **kwargs: Any,
) -> None:
    """Play media with optional failure detection."""
    await self.coordinator.player.play_url(media_id)
    
    # Optional: Verify playback started
    await asyncio.sleep(3)  # Give device time to attempt playback
    await self.coordinator.async_refresh()
    
    if self.coordinator.player.play_state not in ("play", "playing"):
        _LOGGER.warning(
            "Playback may have failed for URL: %s (state: %s)",
            media_id,
            self.coordinator.player.play_state,
        )
        # Optionally raise an error for the UI
        # raise HomeAssistantError(f"Failed to play: {media_id}")
```

**Note:** Adding verification introduces a 3+ second delay. Most integrations skip this and rely on the user to notice if playback doesn't start. The pywiim library intentionally does not include built-in verification to keep the API fast and simple.

**Best Practice:** Check for UPnP client availability before enabling queue features:

```python
# In entity setup
if coordinator.player._upnp_client:
    self._attr_supported_features |= MediaPlayerEntityFeature.MEDIA_ENQUEUE
```

## Source-Aware Shuffle and Repeat Control

### Overview

Shuffle and repeat modes can only be controlled when the WiiM device itself controls playback. For external sources like AirPlay, Bluetooth, and streaming services, these modes are controlled by the source device/app, not the WiiM device.

### New Properties (v1.0.71+)

```python
# Check if shuffle/repeat can be controlled
if player.shuffle_supported:
    # Device controls shuffle - show controls
    shuffle_state = player.shuffle_state  # bool | None
else:
    # External source controls shuffle - hide or disable controls
    shuffle_state = None  # Always None for unsupported sources

if player.repeat_supported:
    # Device controls repeat - show controls
    repeat_mode = player.repeat_mode  # "one" | "all" | "off" | None
else:
    # External source controls repeat - hide or disable controls
    repeat_mode = None  # Always None for unsupported sources
```

### Source Classification

**Device-Controlled Sources** (shuffle/repeat work):
- `usb` - Local USB storage
- `line_in`, `optical`, `coaxial` - Physical inputs  
- `playlist` - Device playlists
- `preset` - Saved presets
- `http` - HTTP streaming

**External-Controlled Sources** (shuffle/repeat DON'T work):
- `airplay` - iOS/macOS controls
- `bluetooth` - Source device controls
- `dlna` - Source app controls
- `spotify`, `tidal`, `amazon`, `qobuz`, `deezer` - Streaming app controls
- `iheartradio`, `pandora`, `tunein` - Radio app controls
- `multiroom` - Slave device, can't control

### Implementation in Media Player Entity

```python
class WiiMMediaPlayer(MediaPlayerEntity):
    def __init__(self, coordinator):
        self.coordinator = coordinator
        # Only add shuffle/repeat features if device supports them
        self._attr_supported_features = self._get_supported_features()

    def _get_supported_features(self) -> int:
        """Get supported features based on current state."""
        features = (
            MediaPlayerEntityFeature.PLAY_MEDIA
            | MediaPlayerEntityFeature.PAUSE
            | MediaPlayerEntityFeature.VOLUME_SET
            # ... other always-supported features
        )
        
        player = self.coordinator.data.get("player")
        if not player:
            return features
        
        # Dynamically add shuffle/repeat based on source
        if player.shuffle_supported:
            features |= MediaPlayerEntityFeature.SHUFFLE_SET
        if player.repeat_supported:
            features |= MediaPlayerEntityFeature.REPEAT_SET
        
        return features

    @property
    def supported_features(self) -> int:
        """Return supported features (dynamic based on source)."""
        return self._get_supported_features()

    @property
    def shuffle(self) -> bool | None:
        """Shuffle state, or None if not controlled by device."""
        player = self.coordinator.data.get("player")
        if not player:
            return None
        return player.shuffle_state  # None for external sources

    @property
    def repeat(self) -> str | None:
        """Repeat mode ('one', 'all', 'off'), or None if not controlled by device."""
        player = self.coordinator.data.get("player")
        if not player:
            return None
        return player.repeat_mode  # None for external sources

    async def async_set_shuffle(self, shuffle: bool) -> None:
        """Set shuffle mode.
        
        Raises WiiMError if shuffle cannot be controlled on current source.
        """
        player = self.coordinator.data.get("player")
        if not player:
            return
        
        try:
            await player.set_shuffle(shuffle)
            # State updates automatically via callback
        except WiiMError as e:
            # Handle error - source doesn't support shuffle
            _LOGGER.warning("Cannot set shuffle: %s", e)
            raise HomeAssistantError(str(e))

    async def async_set_repeat(self, repeat: str) -> None:
        """Set repeat mode.
        
        Raises WiiMError if repeat cannot be controlled on current source.
        """
        player = self.coordinator.data.get("player")
        if not player:
            return
        
        try:
            await player.set_repeat(repeat)
            # State updates automatically via callback
        except WiiMError as e:
            # Handle error - source doesn't support repeat
            _LOGGER.warning("Cannot set repeat: %s", e)
            raise HomeAssistantError(str(e))
```

### Alternative: Static Features with Error Handling

If you prefer to always show shuffle/repeat controls:

```python
class WiiMMediaPlayer(MediaPlayerEntity):
    def __init__(self, coordinator):
        # Always include shuffle/repeat features
        self._attr_supported_features = (
            MediaPlayerEntityFeature.SHUFFLE_SET
            | MediaPlayerEntityFeature.REPEAT_SET
            | ...
        )

    @property
    def shuffle(self) -> bool | None:
        """Shuffle state, or None if not available."""
        player = self.coordinator.data.get("player")
        if not player:
            return None
        # Returns None for AirPlay, Bluetooth, etc.
        return player.shuffle_state

    async def async_set_shuffle(self, shuffle: bool) -> None:
        """Set shuffle mode."""
        player = self.coordinator.data.get("player")
        if not player:
            return
        
        try:
            await player.set_shuffle(shuffle)
        except WiiMError:
            # Silently ignore - controls will appear disabled when None
            pass
```

### Behavior Summary

| Source Type | `shuffle_supported` | `shuffle_state` | `set_shuffle()` |
|-------------|---------------------|-----------------|-----------------|
| USB, Line In, etc. | `True` | `True` / `False` | ✅ Works |
| AirPlay, Bluetooth | `False` | `None` | ❌ Raises `WiiMError` |
| Spotify, Tidal | `False` | `None` | ❌ Raises `WiiMError` |

**Why This Design:**
- External sources (AirPlay, Bluetooth, streaming services) control shuffle/repeat from the source app
- WiiM device can't control these modes - commands would fail silently or have no effect
- Returning `None` and raising errors makes this limitation explicit
- UI can adapt (hide controls, show "N/A", or disable buttons)

**Migration from v1.0.70:**
- Old: `shuffle_state` returned stale values for AirPlay, Bluetooth, etc.
- New: `shuffle_state` returns `None` for external sources
- Check `shuffle_supported` before showing controls or reading state
- Catch `WiiMError` from `set_shuffle()` / `set_repeat()` for external sources

## Accessing Player Properties in Entities

The `Player` class provides convenient properties for entity state:

```python
class WiiMMediaPlayer(MediaPlayerEntity):
    @property
    def volume_level(self) -> float | None:
        """Volume level of the media player (0..1)."""
        return self.coordinator.data.get("volume_level")

    @property
    def is_volume_muted(self) -> bool:
        """Boolean if volume is currently muted."""
        return self.coordinator.data.get("is_muted", False)

    @property
    def state(self) -> str:
        """Return the state of the device."""
        play_state = self.coordinator.data.get("play_state")
        # Map to HA media player states
        if play_state in ("play", "playing"):
            return MediaPlayerState.PLAYING
        elif play_state == "pause":
            return MediaPlayerState.PAUSED
        elif play_state == "stop":
            return MediaPlayerState.IDLE
        else:
            return MediaPlayerState.IDLE

    @property
    def media_title(self) -> str | None:
        """Title of current playing media."""
        return self.coordinator.data.get("media_title")

    @property
    def media_artist(self) -> str | None:
        """Artist of current playing media."""
        return self.coordinator.data.get("media_artist")

    @property
    def media_album_name(self) -> str | None:
        """Album name of current playing media."""
        return self.coordinator.data.get("media_album")

    @property
    def media_image_url(self) -> str | None:
        """Image url of current playing media."""
        return self.coordinator.data.get("media_image_url")

    async def async_get_media_image(self) -> tuple[bytes | None, str | None]:
        """Return image bytes and content type of current playing media.
        
        This method fetches cover art directly from pywiim's cache or fetches it
        if not cached. This provides more reliable cover art than using URLs directly,
        as pywiim handles caching and can serve images even if original URLs expire.
        
        Returns:
            Tuple of (image_bytes, content_type) or (None, None) if no image available.
        """
        player = self.coordinator.data.get("player")
        if not player:
            return (None, None)
        
        result = await player.fetch_cover_art()
        if result:
            return result
        return (None, None)

    @property
    def media_position(self) -> int | None:
        """Position of current playing media in seconds."""
        return self.coordinator.data.get("media_position")

    @property
    def media_duration(self) -> int | None:
        """Duration of current playing media in seconds."""
        return self.coordinator.data.get("media_duration")

    @property
    def media_sample_rate(self) -> int | None:
        """Sample rate of current playing media in Hz."""
        return self.coordinator.data.get("media_sample_rate")

    @property
    def media_bit_depth(self) -> int | None:
        """Bit depth of current playing media in bits."""
        return self.coordinator.data.get("media_bit_depth")

    @property
    def media_bit_rate(self) -> int | None:
        """Bit rate of current playing media in kbps."""
        return self.coordinator.data.get("media_bit_rate")

    @property
    def media_codec(self) -> str | None:
        """Codec of current playing media (e.g., 'flac', 'mp3', 'aac')."""
        return self.coordinator.data.get("media_codec")

    @property
    def shuffle(self) -> bool | None:
        """Shuffle state, or None if not controlled by device.
        
        Returns None for external sources (AirPlay, Bluetooth, streaming services).
        """
        return self.coordinator.data.get("shuffle")

    @property
    def repeat(self) -> str | None:
        """Repeat mode ('one', 'all', 'off'), or None if not controlled by device.
        
        Returns None for external sources (AirPlay, Bluetooth, streaming services).
        """
        return self.coordinator.data.get("repeat")

    @property
    def sound_mode(self) -> str | None:
        """Current sound mode (EQ preset) of the media player.
        
        Returns "Off" when EQ is disabled (audio bypass), otherwise returns
        the current EQ preset name in Title Case (e.g., "Flat", "Rock").
        """
        return self.coordinator.data.get("eq_preset")

    @property
    def sound_mode_list(self) -> list[str] | None:
        """List of available sound modes (EQ presets).
        
        Returns a list with "Off" as the first option, followed by available
        EQ presets (e.g., ["Off", "Flat", "Rock", "Jazz", ...]).
        Selecting "Off" disables EQ entirely (audio bypass).
        """
        return self.coordinator.data.get("eq_presets")

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        """Select sound mode (EQ preset).
        
        Args:
            sound_mode: Sound mode to select. Can be "Off" to disable EQ,
                       or any preset name (e.g., "Flat", "Rock", "Jazz").
        
        Note: The pywiim library handles "Off" automatically:
              - Selecting "Off" disables EQ (audio bypass)
              - Selecting any preset enables EQ if disabled, then applies preset
        """
        player = self.coordinator.data.get("player")
        if player:
            await player.set_eq_preset(sound_mode)
            # State is automatically updated via on_state_changed callback

    @property
    def source_list(self) -> list[str] | None:
        """List of available input sources."""
        return self.coordinator.data.get("available_sources")

    async def async_select_source(self, source: str) -> None:
        """Select input source or play preset.
        
        Args:
            source: Source name or preset name to select.
        """
        player = self.coordinator.data.get("player")
        if not player:
            return
        
        # Check if this is a preset name
        if player.supports_presets and player.presets:
            # Try to find preset by name
            for preset in player.presets:
                preset_name = preset.get("name", f"Preset {preset.get('number')}")
                if preset_name == source:
                    # Play preset by number
                    await player.play_preset(preset["number"])
                    return
        
        # Otherwise, treat as regular source
        await player.set_source(source)
        # State updates automatically via callback

    async def async_set_shuffle(self, shuffle: bool) -> None:
        """Set shuffle mode on the media player.
        
        Args:
            shuffle: True to enable shuffle, False to disable.
                    Preserves current repeat state automatically.
        
        Note: Raises WiiMError for external sources (AirPlay, Bluetooth, etc.)
              where shuffle is controlled by the source app.
        """
        player = self.coordinator.data.get("player")
        if player:
            try:
                await player.set_shuffle(shuffle)
                # State is automatically updated via on_state_changed callback
            except WiiMError as e:
                # Handle error for external sources
                _LOGGER.warning("Cannot set shuffle: %s", e)
                raise HomeAssistantError(str(e))

    async def async_set_repeat(self, repeat: str) -> None:
        """Set repeat mode on the media player.
        
        Args:
            repeat: Repeat mode - "off", "one", or "all".
                   Preserves current shuffle state automatically.
        
        Note: Raises WiiMError for external sources (AirPlay, Bluetooth, etc.)
              where repeat is controlled by the source app.
        """
        player = self.coordinator.data.get("player")
        if player:
            try:
                await player.set_repeat(repeat)
                # State is automatically updated via on_state_changed callback
            except WiiMError as e:
                # Handle error for external sources
                _LOGGER.warning("Cannot set repeat: %s", e)
                raise HomeAssistantError(str(e))
```

## Using Playback Presets

Playback presets are saved radio stations or favorites that users can quickly access. They're different from EQ presets (sound modes).

### Getting Preset Names

Presets are automatically fetched by `player.refresh()` and available via the `player.presets` property:

**Device Differences:**
- **WiiM devices**: `player.presets_full_data = True` - Can read preset names, URLs, etc. via `getPresetInfo`
- **LinkPlay devices**: `player.presets_full_data = False` - Only preset count available via `preset_key`, not names

```python
async def _async_update_data(self):
    """HA calls this method at the update_interval."""
    await self.player.refresh()  # Presets automatically fetched
    
    # Get preset names for source list (WiiM devices only)
    preset_names = []
    max_preset_slots = 0
    
    if self.player.supports_presets:
        if self.player.presets_full_data and self.player.presets:
            # WiiM devices: Get preset names
            preset_names = [
                preset.get("name", f"Preset {preset.get('number')}")
                for preset in self.player.presets
                if preset.get("name")  # Only include presets with names
            ]
        elif not self.player.presets_full_data:
            # LinkPlay devices: Only count available, not names
            max_preset_slots = await self.player.client.get_max_preset_slots()
            # Can't show preset names, but can still play by number (1 to max_preset_slots)
    
    return {
        "player": self.player,
        "available_sources": self.player.available_sources,
        "presets": self.player.presets,  # Full preset data (WiiM) or None (LinkPlay)
        "preset_names": preset_names,  # Preset names for source list (WiiM only)
        "max_preset_slots": max_preset_slots,  # Preset count (LinkPlay devices)
        # ... other data
    }
```

### Including Presets in Source List

To show presets in Home Assistant's source dropdown:

**WiiM devices (with preset names):**
```python
@property
def source_list(self) -> list[str] | None:
    """List of available input sources and presets."""
    sources = self.coordinator.data.get("available_sources", []) or []
    preset_names = self.coordinator.data.get("preset_names", []) or []
    return sources + preset_names  # Combine sources and presets
```

**LinkPlay devices (count only, no names):**
```python
@property
def source_list(self) -> list[str] | None:
    """List of available input sources."""
    # LinkPlay devices: Can't show preset names, only count available
    # Users can still play presets by number via play_preset() service
    return self.coordinator.data.get("available_sources", []) or []
```

### Playing a Preset

Use `play_preset()` to play a preset by number. An optional **index** (1-based track index) lets you start from a specific track in the preset's playlist; when omitted, the device resumes from the last playback position.

```python
async def async_select_source(self, source: str) -> None:
    """Select input source or play preset."""
    player = self.coordinator.data.get("player")
    if not player:
        return
    
    # Check if this is a preset name
    if player.supports_presets and player.presets:
        for preset in player.presets:
            preset_name = preset.get("name", f"Preset {preset.get('number')}")
            if preset_name == source:
                # Play preset by number (resume from last position)
                await player.play_preset(preset["number"])
                # State updates automatically via callback
                return
    
    # Otherwise, treat as regular source
    await player.set_source(source)
    # State updates automatically via callback
```

**Start preset from beginning:** On devices that support it, pass `index=1` to always start from the first track instead of resuming:

```python
# Start preset 6 from the beginning of its playlist (e.g. for automations)
await player.play_preset(6, index=1)
```

Not all devices support the index parameter; if unsupported, the device may ignore it or return an error. Omit `index` for normal resume behavior.

### Preset Data Structure

**WiiM devices (`presets_full_data = True`):**
Each preset dictionary contains:
- `number`: Preset slot number (1-20)
- `name`: Preset name (e.g., "Radio Paradise", "BBC Radio 1")
- `url`: Stream URL (may be `None` if not set)
- `picurl`: Cover art URL (may be `None` if not set)

**Example:**
```python
presets = player.presets
# [
#     {"number": 1, "name": "Radio Paradise", "url": "http://...", "picurl": "http://..."},
#     {"number": 2, "name": "BBC Radio 1", "url": "http://...", "picurl": None},
#     ...
# ]
```

**LinkPlay devices (`presets_full_data = False`):**
- `player.presets` returns `None` or empty list (names not available)
- Use `await player.client.get_max_preset_slots()` to get count (e.g., 6, 20)
- Can still play presets by number: `await player.play_preset(1)` through `await player.play_preset(max_slots)`. Optional `index` (1-based track) to start at a specific track: `await player.play_preset(3, index=1)` (start from beginning).

### Automatic Fetching

Presets are automatically fetched by `player.refresh()`:
- On full refresh
- On track changes (may indicate preset switch)
- Periodically (every 60 seconds)

**No manual fetching needed** - just use `player.presets` after the coordinator's scheduled refresh.

## Audio Output Selection

### Available Outputs Property

The `available_outputs` property provides a unified list of all available outputs (hardware modes + paired Bluetooth devices):

```python
# Access as a property on player (not a method)
outputs = player.available_outputs  # Returns list[str]

# Example output (when BT devices are paired):
# ["Line Out", "Optical Out", "Coax Out", "BT: Sony Speaker", "BT: JBL Headphones"]
# Note: Generic "Bluetooth Out" is removed when specific BT devices are available
```

**Important Notes:**
- ✅ `available_outputs` is a **property** on `player` (accessed as `player.available_outputs`)
- ✅ It's **not** a method - no parentheses needed
- ❌ There is **no** `player.audio.available_outputs` - `player.audio` is for methods like `select_output()`
- ✅ Returns a list of strings combining hardware output modes and paired Bluetooth devices
- ✅ Bluetooth devices are prefixed with "BT: " in the list

### Related Properties

```python
# Get just hardware output modes
hardware_modes = player.available_output_modes  # ["Line Out", "Optical Out", ...]

# Get just paired Bluetooth output devices
bt_devices = player.bluetooth_output_devices  # [{"name": "...", "mac": "...", "connected": bool}, ...]

# Get current output mode
current_mode = player.audio_output_mode  # e.g., "Optical Out"

# Check if Bluetooth output is active
is_bt_active = player.is_bluetooth_output_active  # True/False
```

### Selecting Outputs

Use `player.audio.select_output()` to change the output:

```python
# Select hardware output mode
await player.audio.select_output("Optical Out")
await player.audio.select_output("Line Out")

# Select specific Bluetooth device (auto-switches to BT mode and connects)
await player.audio.select_output("BT: Sony Speaker")
```

### Home Assistant Select Entity Example

```python
from homeassistant.components.select import SelectEntity

class WiiMOutputSelectEntity(SelectEntity):
    """Select entity for output selection."""
    
    @property
    def options(self) -> list[str]:
        """Return available output options.
        
        Available as a property on player: player.available_outputs
        Returns a list of output names (hardware modes + paired BT devices).
        """
        player = self.coordinator.data.get("player")
        if not player:
            return []
        return player.available_outputs
    
    @property
    def current_option(self) -> str | None:
        """Return current output.
        
        Returns the currently selected output mode, which must match one of the
        options in the available_outputs list. Returns None if output status
        is not available or doesn't match any option.
        """
        player = self.coordinator.data.get("player")
        if not player:
            return None
        
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
        player = self.coordinator.data.get("player")
        if not player:
            return
        await player.audio.select_output(option)
        # State updates automatically via callback - no manual refresh needed
```

### Including in Coordinator Data

If you need `available_outputs` in your coordinator data:

```python
async def _async_update_data(self):
    """HA calls this method at the update_interval."""
    await self.player.refresh()
    
    # IMPORTANT: Ensure audio output status is fetched for current_option to work
    # This is done automatically if you follow the polling strategy pattern
    # (see "Implement Adaptive Polling with Player" section above)
    
    return {
        "player": self.player,
        # ... other properties ...
        "available_outputs": self.player.available_outputs,  # Include if needed
        # ... other properties ...
    }
```

### Troubleshooting: Current Option Not Showing

If the select entity shows "Audio Output Mode" instead of the actual selected value:

1. **Ensure audio output status is being fetched:**
   - Check that `get_audio_output_status()` is called in your coordinator's `_async_update_data()` method
   - Verify that `supports_audio_output` capability is detected
   - See "Implement Adaptive Polling with Player" section for the correct pattern

2. **Check that `current_option` returns a valid value:**
   - The returned value must exactly match one of the options in `available_outputs`
   - If `audio_output_mode` returns `None`, `current_option` will also return `None`
   - Add logging to debug: `_LOGGER.debug("Current mode: %s, Available: %s", player.audio_output_mode, player.available_outputs)`

3. **Verify audio output status is being fetched:**
   - Ensure `player.get_audio_output_status()` is called in coordinator's `_async_update_data()`
   - The method automatically updates the player's internal cache, so `audio_output_mode` will work
   - See coordinator example above for the correct pattern

4. **Verify refresh is working:**
   - Ensure `player.refresh()` is called in coordinator
   - Check that `player._audio_output_status` is not `None` after coordinator update
   - Audio output status is fetched every 15 seconds when supported (see polling strategy)

## Subwoofer Control (WiiM Devices)

WiiM devices (Pro, Ultra, etc.) support external subwoofer configuration. Not supported on Arylic/LinkPlay devices. The library auto-detects support and fetches status every 60 seconds.

### Available Properties

```python
# Check if subwoofer control is supported
player.supports_subwoofer  # bool

# Cached subwoofer status (updated every 60s)
player.subwoofer_status    # dict | None - Full status dict
player.subwoofer_enabled   # bool | None - Subwoofer on/off
player.subwoofer_level     # int | None - Level adjustment (-15 to +15 dB)
player.subwoofer_crossover # int | None - Crossover frequency (30-250 Hz)
```

### Control Methods

```python
# Enable/disable subwoofer (most useful for automations)
await player.set_subwoofer_enabled(True)
await player.set_subwoofer_enabled(False)

# Adjust level (-15 to +15 dB)
await player.set_subwoofer_level(0)

# Other settings (typically set once during setup)
await player.set_subwoofer_crossover(80)  # 30-250 Hz
await player.set_subwoofer_phase(0)        # 0 or 180 degrees
await player.set_subwoofer_delay(0)        # -200 to +200 ms
```

### Recommended Entity: Switch for Enable/Disable

The most useful automation is "late-night mode" (disable subwoofer after hours). Create a simple switch:

```python
class WiiMSubwooferSwitch(SwitchEntity):
    """Switch to enable/disable subwoofer."""
    
    @property
    def is_on(self) -> bool | None:
        """Return true if subwoofer is enabled."""
        return self.coordinator.data.get("player").subwoofer_enabled
    
    @property
    def available(self) -> bool:
        """Return true if subwoofer is supported."""
        return self.coordinator.data.get("player").supports_subwoofer
    
    async def async_turn_on(self, **kwargs) -> None:
        """Enable subwoofer."""
        await self.coordinator.data.get("player").set_subwoofer_enabled(True)
    
    async def async_turn_off(self, **kwargs) -> None:
        """Disable subwoofer."""
        await self.coordinator.data.get("player").set_subwoofer_enabled(False)
```

### Optional: Number Entity for Level

If users want scene-based bass levels:

```python
class WiiMSubwooferLevel(NumberEntity):
    """Number entity for subwoofer level adjustment."""
    
    _attr_native_min_value = -15
    _attr_native_max_value = 15
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "dB"
    
    @property
    def native_value(self) -> int | None:
        """Return current level."""
        return self.coordinator.data.get("player").subwoofer_level
    
    async def async_set_native_value(self, value: float) -> None:
        """Set subwoofer level."""
        await self.coordinator.data.get("player").set_subwoofer_level(int(value))
```

### Notes

- **Polling**: Subwoofer status is automatically fetched every 60 seconds by `player.refresh()`
- **First fetch**: On first poll, the library probes for support and caches the result
- **No manual fetching needed**: Just access the properties - state is always current
- **Optimistic updates**: Methods update cached state immediately after API success

## LED Indicator and Display Control (ADR 005)

pywiim exposes two distinct capabilities: **LED Indicator** (on/off) and **Display** (WiiM Ultra screen). Use the player API below; no persistent state is stored between sessions.

| Concept | Capability | Player API | Use |
|--------|------------|------------|-----|
| **LED Indicator** | `supports_led_indicator` | `get_led_indicator()`, `set_led_indicator(enabled)` | Small status light; Arylic + WiiM (probe). Read assumes **on** if device has no read API. |
| **Display** | `supports_display_config` | `set_display_enabled(enabled)`, `set_display_config(...)` | WiiM Ultra LCD on/off and brightness; **not** the status LED. |

- **LED Indicator**: We try to read from the device; if read fails or no API exists, we return **on** and log a warning. No persistent state between restarts.
- **Display** (WiiM Ultra only): Check `player.supports_display_config`; then use the player methods. No read API; integration may track state if needed.

### LED Indicator (Light Entity)

Integrations that expose the **LED indicator** as a Home Assistant **Light** entity must satisfy HA's Light platform contract.

### pywiim API

```python
# LED Indicator (ADR 005) – preferred for on/off switch
player.supports_led_indicator  # bool (Arylic + WiiM)

on_off = await player.get_led_indicator()  # bool; assumes on if device has no read API
await player.set_led_indicator(True)   # or False

# Legacy: primary LED (setLED) and Status Light (client only)
player.supports_led_control
await player.set_led(True)
await player.set_led_brightness(50)
await player.client.set_led_switch(True)  # same as set_led_indicator
```

### Display (WiiM Ultra)

WiiM Ultra has an LCD controlled by **`setLightOperationBrightConfig`** (brightness + on/off in one JSON payload). That is **not** the same command family as the **LED indicator** (`LED_SWITCH_SET` / `set_led_indicator`).

```python
if player.supports_display_config:
    await player.set_display_enabled(True)   # screen on at default brightness (100 on a 1–100 scale)
    await player.set_display_enabled(True, default_bright=50)  # optional level when turning on
    await player.set_display_enabled(False)  # screen off
    await player.set_display_config(auto_sense_enable=0, default_bright=100, disable=0)  # full control; disable: 0=on, 1=off
```

Constants: `DISPLAY_BRIGHTNESS_MIN`, `DISPLAY_BRIGHTNESS_MAX`, `DISPLAY_DEFAULT_BRIGHTNESS` in `pywiim.api.constants`. No getter: display state is not in device status; track it in the integration if needed.

### Home Assistant: "does not report a color mode"

If the coordinator update fails with:

```text
HomeAssistantError: light.<entity> (<class '...WiiMLEDLight'>) does not report a color mode
```

the cause is in the **integration**, not in pywiim. HA's Light platform requires every light entity to report `color_mode` and `supported_color_modes`. The fix is in the integration's Light entity class:

- Set **`supported_color_modes`** (e.g. `{ColorMode.BRIGHTNESS}` for on/off + brightness, or `{ColorMode.ONOFF}` for on/off only).
- Set **`color_mode`** in the entity state (e.g. `ColorMode.BRIGHTNESS` when brightness is supported, `ColorMode.ONOFF` otherwise).

Example for a dimmable LED (on/off + brightness):

```python
from homeassistant.components.light import ColorMode

# In your WiiMLEDLight entity:
_supported_color_modes = {ColorMode.BRIGHTNESS}

@property
def color_mode(self) -> ColorMode:
    return ColorMode.BRIGHTNESS
```

For LED Indicator use `get_led_indicator()`; it returns the device state when available, or **assumes on** and logs a warning when the device has no read API. No persistent state is stored between sessions.

## 12V Trigger (WiiM Ultra / Pro / Pro Plus)

WiiM Ultra, Pro, and Pro Plus have a 12V trigger output that can control external amplifiers (e.g. turn on when playing). The library exposes read/set and a capability flag.

### Available Properties and Methods

```python
# Check if 12V trigger is supported
player.supports_trigger_out  # bool

# Cached state (updated when get_trigger_out_status or set_trigger_out is called)
player.trigger_out_on  # bool | None - True=on, False=off, None=unknown

# Read current state from device (updates trigger_out_on)
status = await player.get_trigger_out_status()  # bool | None

# Set trigger on/off
await player.set_trigger_out(True)
await player.set_trigger_out_on()
await player.set_trigger_out_off()
```

### Home Assistant Switch Example

```python
class WiiMTriggerSwitch(SwitchEntity):
    """Switch for 12V trigger output (amplifier control)."""
    
    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("player").trigger_out_on)
    
    @property
    def available(self) -> bool:
        return self.coordinator.data.get("player").supports_trigger_out
    
    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.data.get("player").set_trigger_out_on()
    
    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.data.get("player").set_trigger_out_off()
```

### Notes

- **Capability**: Support is probed at device init via `getTriggeroutStatus`; only models with the physical jack report support.
- **State**: Call `get_trigger_out_status()` when needed (e.g. on entity update) to refresh `trigger_out_on`; the library does not poll trigger state automatically.

## Group Join/Unjoin Operations

### Library Handles Everything Automatically

The `pywiim` library now handles all group operation complexity internally. You just need to:

1. **Set up callback in coordinator** (for entity updates)
2. **Call the operation** (`join_group()` or `leave_group()`)

The library automatically:
- ✅ Handles all preconditions (disband groups, create groups, etc.)
- ✅ Updates state immediately after API success
- ✅ Calls `on_state_changed` callback to notify coordinator

### Setup: Add Callback to Player

```python
class WiiMCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, host):
        # ... initialization ...
        
        # Create Player with callback for automatic coordinator updates
        self.player = Player(
            client,
            on_state_changed=self.async_update_listeners,  # HA will update entities
        )
```

### Join Group Implementation

```python
async def async_join_group(
    hass: HomeAssistant,
    slave_entity_id: str,
    master_entity_id: str,
) -> None:
    """Join a player to a group (HA service)."""
    # Get players
    slave_player = get_player_for_entity(slave_entity_id)
    master_player = get_player_for_entity(master_entity_id)
    
    # That's it! Library handles everything automatically:
    # - Disbands joiner's group if it's a master
    # - Removes joiner from group if it's a slave
    # - Removes target from group if it's a slave
    # - Creates group on target if it's solo
    # - Calls API
    # - Updates Group objects immediately
    # - Calls callbacks (which trigger coordinator.async_update_listeners())
    # 
    # NO NEED to check roles or handle preconditions - just call it!
    await slave_player.join_group(master_player)
```

### Leave Group Implementation

```python
async def async_leave_group(
    hass: HomeAssistant,
    entity_id: str,
) -> None:
    """Leave a group (HA service)."""
    player = get_player_for_entity(entity_id)
    
    # That's it! Library handles everything based on player role:
    # - Solo: No-op (idempotent, returns immediately)
    # - Master: Disbands entire group (all players become solo)
    # - Slave: Leaves group (master and other slaves remain)
    # - Updates Group objects immediately
    # - Calls callbacks (which trigger coordinator.async_update_listeners())
    # 
    # NO NEED to check player.is_master or player.is_slave - just call it!
    await player.leave_group()
```

## Diagnostic Sensors

The library exposes diagnostic information that can be used to create Home Assistant sensors for monitoring device health and UPnP event reliability.

### Available Diagnostic Properties

These properties are available on the `Player` object and can be accessed via the coordinator's data:

- **`upnp_health_status`** (dict | None): Complete health statistics dictionary
- **`upnp_is_healthy`** (bool | None): Simple health check (True/False/None)
- **`upnp_miss_rate`** (float | None): Miss rate as fraction (0.0-1.0, where 0.0 = perfect, 1.0 = all missed)

**Note**: These properties are only available when UPnP client is provided to the Player. They return `None` if UPnP is not enabled.

### UPnP Health Sensor

You can create a sensor to monitor UPnP event health:

```python
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE

class WiiMUpnpHealthSensor(SensorEntity):
    """Sensor for UPnP event health monitoring."""

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry_id}_upnp_health"
        self._attr_name = f"{coordinator.player.name or coordinator.player.host} UPnP Health"
        self._attr_icon = "mdi:network"
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> str | None:
        """Return the health status as a string."""
        health_status = self.coordinator.data.get("upnp_health_status")
        if health_status is None:
            return "unavailable"  # UPnP not enabled
        return "healthy" if health_status.get("is_healthy") else "degraded"

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit of measurement."""
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        health_status = self.coordinator.data.get("upnp_health_status")
        if health_status is None:
            return {
                "status": "UPnP not enabled",
            }

        miss_rate = health_status.get("miss_rate", 0.0)
        return {
            "is_healthy": health_status.get("is_healthy", False),
            "miss_rate_percent": round(miss_rate * 100, 1),
            "detected_changes": health_status.get("detected_changes", 0),
            "missed_changes": health_status.get("missed_changes", 0),
            "has_enough_samples": health_status.get("has_enough_samples", False),
        }

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_coordinator_update))

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
```

Or create separate sensors for specific metrics:

```python
class WiiMUpnpMissRateSensor(SensorEntity):
    """Sensor for UPnP miss rate percentage."""

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry_id}_upnp_miss_rate"
        self._attr_name = f"{coordinator.player.name or coordinator.player.host} UPnP Miss Rate"
        self._attr_icon = "mdi:network-off"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE

    @property
    def native_value(self) -> float | None:
        """Return the miss rate as a percentage."""
        miss_rate = self.coordinator.data.get("upnp_miss_rate")
        if miss_rate is None:
            return None
        return round(miss_rate * 100, 1)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.native_value is not None
```

### Quick Reference: Accessing Diagnostic Sensors

All diagnostic properties are available in your coordinator's data dictionary after calling `async_update()`:

```python
# In your sensor entity or coordinator
data = self.coordinator.data

# UPnP health status (full dictionary)
health_status = data.get("upnp_health_status")
# Returns: {
#     "is_healthy": True,
#     "miss_rate": 0.05,  # 5% miss rate
#     "detected_changes": 20,
#     "missed_changes": 1,
#     "has_enough_samples": True
# }

# Simple health check
is_healthy = data.get("upnp_is_healthy")  # True/False/None

# Miss rate as percentage
miss_rate = data.get("upnp_miss_rate")  # 0.05 = 5% miss rate
if miss_rate is not None:
    miss_rate_percent = round(miss_rate * 100, 1)  # Convert to percentage
```

**Important**: These properties are included in the coordinator data automatically when you include them in your `_async_update_data()` method (see example in "Coordinator Implementation" section above).

### Firmware Update Entity

Home Assistant's `UpdateEntity` can be used to expose firmware update availability and installation:

```python
from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.const import ATTR_INSTALLED_VERSION, ATTR_LATEST_VERSION

class WiiMFirmwareUpdate(UpdateEntity):
    """Firmware update entity for WiiM devices."""

    def __init__(self, coordinator):
        self.coordinator = coordinator
        player = coordinator.data.get("player")
        self._attr_unique_id = f"{coordinator.entry_id}_firmware_update"
        self._attr_name = f"{player.name or player.host} Firmware Update"
        self._attr_supported_features = UpdateEntityFeature.INSTALL
        if player.supports_firmware_install:
            self._attr_supported_features |= UpdateEntityFeature.PROGRESS

    @property
    def installed_version(self) -> str | None:
        """Return the installed firmware version."""
        player = self.coordinator.data.get("player")
        return player.firmware

    @property
    def latest_version(self) -> str | None:
        """Return the latest available firmware version."""
        player = self.coordinator.data.get("player")
        return player.latest_firmware_version

    @property
    def release_summary(self) -> str | None:
        """Return release summary."""
        if not self.available:
            return None
        if self.latest_version and self.installed_version:
            return f"Update from {self.installed_version} to {self.latest_version}"
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        player = self.coordinator.data.get("player")
        return (
            self.coordinator.last_update_success
            and player is not None
            and player.firmware is not None
        )

    async def async_install(self, version: str | None, backup: bool) -> None:
        """Install the firmware update.
        
        Args:
            version: Version to install (ignored, uses latest available)
            backup: Whether to backup before install (ignored, device handles this)
        """
        player = self.coordinator.data.get("player")
        if not player:
            raise RuntimeError("Player not available")
        
        if player.supports_firmware_install:
            # WiiM device: install via API
            await player.install_firmware_update()
        else:
            # Other device: reboot to install (if update is ready)
            if player.firmware_update_available:
                await player.reboot()
            else:
                raise RuntimeError("No update available or not ready to install")

    @property
    def in_progress(self) -> bool | None:
        """Return if update is in progress (WiiM devices only)."""
        player = self.coordinator.data.get("player")
        if not player or not player.supports_firmware_install:
            return None
        
        # Check installation status (would need to be cached in coordinator)
        # For now, return None (unknown)
        return None

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {("wiim", self.coordinator.entry_id)},
            "name": self.coordinator.data.get("player").name,
            "manufacturer": "WiiM",
            "model": self.coordinator.data.get("player").model,
        }
```

**Key Points:**
- Use `player.firmware_update_available` to determine if update is available
- Use `player.latest_firmware_version` for the latest version
- Use `player.supports_firmware_install` to check if API installation is supported
- For WiiM devices: `async_install()` calls `player.install_firmware_update()`
- For other devices: `async_install()` calls `player.reboot()` (if update is ready)
- The entity automatically updates when `coordinator.data` is refreshed

**Coordinator Data:**

Include firmware update info in coordinator data:

```python
async def _async_update_data(self):
    """HA calls this method at the update_interval."""
    await self.player.refresh()
    
    return {
        "player": self.player,
        "firmware_update_available": self.player.firmware_update_available,
        "latest_firmware_version": self.player.latest_firmware_version,
        "installed_firmware_version": self.player.firmware,
        "supports_firmware_install": self.player.supports_firmware_install,
    }
```

### Accessing Group Information in Entities

```python
@property
def group_role(self) -> str | None:
    """Return the current group role."""
    player = self.coordinator.data.get("player")
    if not player:
        return None
    # Role comes from device API state (SINGLE source of truth)
    # This is accurate even if Player objects aren't linked
    return player.role  # "solo", "master", or "slave"

@property
def group_members(self) -> list[str] | None:
    """Return list of group member hostnames.
    
    Note: This returns Player objects that are linked together via Group.
    For a master device, this will only include slaves that have been
    automatically linked by pywiim (i.e., slave Player objects exist and
    player_finder was provided when creating Player objects).
    """
    player = self.coordinator.data.get("player")
    if not player or not player.group:
        return None
    return [p.host for p in player.group.all_players]
```

**Important: Role vs Group Objects**

- **`player.role`**: Device's actual role from API state ("solo", "master", or "slave")
  - Source: Device API via `detect_role()` function
  - Always accurate, updated during `refresh()`
  - **This is the SINGLE source of truth for role**

- **`player.group`**: Group object for linking Player objects together
  - Source: pywiim automatically links Player objects during `refresh()` when `player_finder` is provided
  - Used for multi-player operations (volume sync, etc.)
  - If `player_finder` is not provided, `group.slaves` may be empty even if device is a master
  
**Example:**
```python
# Device IS a master according to API
player.is_master  # True

# Group object automatically links Player objects when player_finder is provided
# During refresh(), pywiim automatically:
# - Finds slave Player objects via player_finder callback
# - Links them to the master's group
# - Links slave players to their master's group
player.group.slaves  # [slave1, slave2, ...] (automatically linked by pywiim)

# To enable automatic linking, provide player_finder when creating Player:
player = Player(
    client,
    player_finder=lambda host: player_registry.get(host),  # Returns Player | None
    all_players_finder=lambda: list(player_registry.values()),  # Returns list[Player]
)

# all_players_finder is CRITICAL for WiFi Direct multiroom (legacy LinkPlay devices):
# - WiFi Direct slaves join master's internal network and get 10.10.10.x IPs
# - Slaves report "solo" when queried directly (they don't know they're in a group)
# - Only the master knows the slave list (via getSlaveList API)
# - pywiim uses all_players_finder to:
#   1. Link slaves by UUID when IP matching fails (10.10.10.x IPs not known to HA)
#   2. Check if any master lists this device as a slave (correct role detection)
# - No UUID lookup implementation needed in player_finder - pywiim handles it internally
```

## Virtual Group Entity Implementation

When a multiroom group exists, Home Assistant can create a virtual group media player entity that represents the entire group. This section explains how to implement this entity using pywiim's Group object.

### Accessing the Group Object

The Group object is accessed via the master player:

```python
# Get the master player's coordinator
master_coordinator = get_coordinator_for_entity(master_entity_id)
master_player = master_coordinator.data.get("player")

# Access the group object (only exists when player is master or slave)
if master_player.is_master and master_player.group:
    group = master_player.group
    # Use group for virtual entity operations
```

### Virtual Entity Setup

The virtual group entity listens to the **master player's coordinator** and uses the Group object for operations:

```python
class VirtualGroupMediaPlayer(CoordinatorEntity):
    """Virtual media player representing a multiroom group."""
    
    def __init__(self, master_coordinator):
        """Initialize virtual group entity."""
        super().__init__(master_coordinator)
        self._master_coordinator = master_coordinator
    
    @property
    def master_player(self):
        """Get master player from coordinator."""
        return self._master_coordinator.data.get("player")
    
    @property
    def group(self):
        """Get group object."""
        return self.master_player.group if self.master_player else None
```

### Group Operations

Use Group object methods for group-wide operations:

```python
async def async_set_volume_level(self, volume: float) -> None:
    """Set volume for all group members."""
    if self.group:
        await self.group.set_volume_all(volume)

async def async_mute_volume(self, mute: bool) -> None:
    """Mute/unmute all group members."""
    if self.group:
        await self.group.mute_all(mute)

async def async_media_play(self) -> None:
    """Play on group (routes to master)."""
    if self.group:
        await self.group.play()

async def async_media_pause(self) -> None:
    """Pause on group (routes to master)."""
    if self.group:
        await self.group.pause()
```

### Reading Group State

Group properties compute aggregated state dynamically:

```python
@property
def volume_level(self) -> float | None:
    """Virtual group volume = MAX of all members."""
    return self.group.volume_level if self.group else None

@property
def is_volume_muted(self) -> bool | None:
    """Virtual group mute = ALL members muted."""
    return self.group.is_muted if self.group else None

@property
def state(self) -> str | None:
    """Playback state from master."""
    return self.group.play_state if self.group else None

@property
def media_title(self) -> str | None:
    """Media title from master."""
    return self.group.media_title if self.group else None

@property
def media_artist(self) -> str | None:
    """Media artist from master."""
    return self.group.media_artist if self.group else None

@property
def media_position(self) -> float | None:
    """Media position from master."""
    return self.group.media_position if self.group else None

@property
def media_duration(self) -> float | None:
    """Media duration from master."""
    return self.group.media_duration if self.group else None
```

**Key Points:**
- Volume/mute are unique group properties (MAX volume, ALL muted)
- Playback state and media metadata come from the master (via Group properties)
- Properties are computed on access (no caching)

## Event Propagation Model

pywiim uses a smart event propagation model to ensure immediate UI updates across all entities without polling lag.

### Playback Commands - Automatic Routing

When a playback command is sent to a slave player, pywiim automatically routes it to the master:

```python
# User presses pause on slave entity in HA
await slave_player.pause()
# → pywiim detects slave role
# → routes to slave.group.pause()
# → calls master.pause()
# → master's callback fires
# → virtual group entity updates (listens to master)
# → slaves get updated state via _propagate_metadata_to_slaves()
```

**What happens:**
1. Command routes through Group object to master
2. Master executes command and updates its state
3. Master's `on_state_changed` fires → master coordinator updates
4. Virtual entity (listening to master coordinator) updates immediately
5. Master's next refresh propagates playback state to all slaves
6. Slave entities update on their next refresh

**HA implementation:**
```python
async def async_media_pause(self) -> None:
    """Pause playback (works for master, slave, or group entity)."""
    player = self.coordinator.data.get("player")
    await player.pause()  # pywiim handles routing automatically
```

### Volume/Mute Commands - Cross-Notification

When a slave's volume or mute changes, pywiim fires callbacks on **both** the slave and master:

```python
# User adjusts volume on slave entity
await slave_player.set_volume(0.5)
# → Command goes to slave device
# → Slave's state updated optimistically
# → Slave's callback fires → slave entity updates
# → Master's callback fires → master coordinator updates
# → Virtual entity (listening to master) updates immediately
# → Reads group.volume_level (MAX of all) - includes new slave volume
```

**What happens:**
1. Command goes to the individual slave device
2. Slave's own callback fires (slave entity updates)
3. Master's callback also fires (virtual entity updates immediately)
4. Virtual entity reads `group.volume_level` which computes MAX on access

**HA implementation:**
```python
async def async_set_volume_level(self, volume: float) -> None:
    """Set individual player volume."""
    player = self.coordinator.data.get("player")
    await player.set_volume(volume)
    # Both callbacks fire automatically - no manual refresh needed
```

### Master Volume/Mute - Propagation

When the master's volume or mute changes:

```python
# User adjusts volume on master entity
await master_player.set_volume(0.8)
# → Volume propagates to all slaves (if called via Group.set_volume_all)
# → OR only master changes (if called via Player.set_volume)
# → Master's callback fires
# → Master entity updates
# → Virtual entity updates (listens to master)
```

**For group-wide changes, use Group object:**
```python
# Virtual entity adjusting group volume
await master.group.set_volume_all(0.8)
# → Adjusts all devices proportionally
# → Master's callback fires
# → Virtual entity updates
```

### Event Flow Summary

| Action | Callback Fires On | Virtual Entity Update | Slave Entity Update |
|--------|-------------------|----------------------|---------------------|
| Slave playback command | Master only | Immediate (via master) | Next refresh (propagation) |
| Slave volume/mute | Slave + Master | Immediate (via master) | Immediate (own callback) |
| Master playback command | Master only | Immediate | Next refresh (propagation) |
| Master volume/mute | Master only | Immediate | Next refresh (if group-wide) |
| Group volume/mute | Master only | Immediate | Next refresh |

**Key benefits:**
- ✅ No polling lag for virtual entity
- ✅ Immediate updates from any member
- ✅ No manual refresh needed
- ✅ Works seamlessly with HA coordinator pattern

### Key Benefits

✅ **No manual precondition handling**: Library handles master/slave/solo transitions automatically
✅ **No manual refresh needed**: State updates immediately after successful API calls
✅ **No manual coordinator updates**: Callback handles it automatically  
✅ **Works regardless of current state**: Join any player to any player - library handles transitions
✅ **Automatic command routing**: Slave playback commands route to master automatically
✅ **Cross-notification**: Volume/mute changes fire callbacks on relevant players for immediate updates

### How It Works Internally

The library automatically handles all preconditions:

1. **If joiner is MASTER**: Disbands the group first, then joins
2. **If joiner is SLAVE**: Device leaves current group automatically during join
3. **If target is SLAVE**: Has target leave its group first
4. **If target is SOLO**: Creates group on target (device promotes to master automatically)

After successful API call, library immediately:
- Updates Group objects (add/remove slaves)
- Calls `on_state_changed` callback on **ALL group members** (not just the two involved players)
- Ensures all coordinators receive immediate notifications
- Ensures library state matches device state across all affected players

**No waiting, no polling, no manual refresh needed for ANY player in the group.**

**See also**: 
- `docs/design/OPERATION_PATTERNS.md` for the general operation pattern

## Player Command Methods - No Manual Refresh Required

All Player command methods (playback control, volume, multiroom, etc.) are designed to work seamlessly with Home Assistant's coordinator pattern. **You should NOT call `async_request_refresh()` after Player commands.**

### How State Updates Work

After calling any Player command method, state updates happen automatically via:

1. **Optimistic State Updates + Callbacks** (immediate, < 1ms)
   - Player updates cached state optimistically after API call succeeds
   - Player fires `on_state_changed` callback immediately
   - Callback triggers `coordinator.async_update_listeners()`
   - UI updates instantly from cached state (no network delay)
   - Works for ALL player commands: play/pause, volume, shuffle, repeat, source, EQ, etc.

2. **UPnP Events** (immediate, when available)
   - Volume changes, play state changes, track changes
   - Real-time updates with < 1 second latency
   - Automatically merged with HTTP polling data
   - Provides confirmation of device state

3. **Coordinator Polling** (5-10 seconds)
   - Adaptive intervals based on play state
   - Catches all changes including those without UPnP events
   - Already debounced by DataUpdateCoordinator
   - Final fallback for state synchronization

### ✅ Correct: Trust the Coordinator

```python
async def async_media_play(self) -> None:
    """Send play command."""
    player = self.coordinator.data.get("player")
    await player.play()
    # That's it! State updates via:
    # 1. Callback fires immediately (<1ms) - UI updates instantly
    # 2. UPnP event confirms (immediate)
    # 3. Next coordinator poll (5-10s)

async def async_set_volume_level(self, volume: float) -> None:
    """Set volume level."""
    player = self.coordinator.data.get("player")
    await player.set_volume(volume)
    # That's it! State updates via:
    # 1. Callback fires immediately (<1ms) - UI updates instantly
    # 2. UPnP event confirms (immediate)
    # 3. Next coordinator poll (5-10s)
```

### ❌ Wrong: Manual Refresh After Commands

```python
async def async_media_play(self) -> None:
    """Send play command."""
    player = self.coordinator.data.get("player")
    await player.play()
    await self.coordinator.async_request_refresh()  # ❌ Unnecessary!
    # This causes:
    # - Extra network call (slow)
    # - Potential race with UPnP events
    # - Coordinator already polling
```

### Multiroom Operations - No Manual Refresh Needed

**Important**: Group operations automatically notify ALL group members via their `on_state_changed` callbacks. You do NOT need to call `async_force_multiroom_refresh()` or `async_request_refresh()` after group operations.

```python
async def async_join_group(slave_entity_id: str, master_entity_id: str):
    """Join a player to a group (HA service)."""
    slave_player = get_player_for_entity(slave_entity_id)
    master_player = get_player_for_entity(master_entity_id)
    
    # That's it! pywiim automatically notifies ALL group members
    await slave_player.join_group(master_player)
    # ❌ No async_force_multiroom_refresh() needed!
    # All coordinators for all group members are notified immediately
```

**What pywiim does automatically:**
- Notifies all players in the new group (joiner, master, and all slaves)
- Notifies all players in the old group if joiner left a different group
- Ensures all coordinators receive immediate state updates
- Updates all UIs immediately across all group members

### Performance Benefits

By NOT calling `async_request_refresh()` after commands:
- ⚡ Commands execute faster (single HTTP call instead of two)
- 📉 Reduced network traffic
- 🎯 No race conditions between manual refresh and UPnP events
- ✅ Coordinator's debouncing works properly

## Alternative: Using WiiMClient Directly

If you prefer direct API access without state caching, you can use `WiiMClient` directly:

```python
from pywiim import WiiMClient, PollingStrategy

class WiiMCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, host):
        # ... initialization ...
        session = async_get_clientsession(self.hass)
        self.client = WiiMClient(host=host, session=session)

    async def _async_update_data(self):
        # Fetch data directly
        status = await self.client.get_player_status_model()
        device_info = await self.client.get_device_info_model()
        multiroom = await self.client.get_multiroom_status()

        # Manual state management
        return {
            "status_model": status,
            "device_info": device_info,
            "multiroom": multiroom,
            # Manual property access
            "volume_level": status.volume / 100.0 if status.volume else None,
            "is_muted": status.mute,
            "play_state": status.play_state,
            # ... etc
        }
```

**Note**: This approach requires manual state management, manual HTTP + UPnP merging, and manual property conversion. Using `Player` is recommended for HA integrations.

## Division of Responsibilities: Polling, Updates, and Roles

This section clarifies **who decides what** and **who does what** in the polling architecture, following best practices and design patterns.

### Design Pattern: Strategy Pattern with Framework Control

The architecture follows a **Strategy Pattern** where:
- **Home Assistant** (framework) controls **when** to poll (scheduling)
- **pywiim** (library) recommends **what** to poll and **how often** (strategy)
- **Integration** (coordinator) orchestrates between framework and library

### Responsibility Matrix

| Responsibility | Owner | What They Do |
|----------------|-------|--------------|
| **Polling Schedule** | Home Assistant | `DataUpdateCoordinator` schedules when `_async_update_data()` is called |
| **Polling Interval** | pywiim (recommends) + HA (applies) | `PollingStrategy.get_optimal_interval()` recommends, coordinator applies via `update_interval` |
| **What to Poll** | pywiim (recommends) + Integration (decides) | `PollingStrategy.should_fetch_*()` methods recommend, coordinator decides to fetch |
| **State Management** | pywiim | `Player.refresh()` fetches and caches state, `StateSynchronizer` merges HTTP + UPnP |
| **State Access** | pywiim | `Player` properties provide convenient, normalized state access |
| **UPnP Events** | pywiim | `UpnpEventer` subscribes to events, `Player.apply_diff()` merges with HTTP state |
| **Error Handling** | Integration | Coordinator handles exceptions, returns cached data or raises `UpdateFailed` |

### Detailed Breakdown

#### 1. **Polling Schedule (WHEN to Poll)**

**Owner: Home Assistant**

Home Assistant's `DataUpdateCoordinator` is responsible for:
- Scheduling when `_async_update_data()` is called
- Managing the polling loop lifecycle
- Handling retries on failures
- Coordinating multiple devices (concurrent polling)

```python
# HA controls the schedule
class WiiMCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, host):
        super().__init__(
            hass,
            logger,
            name=f"WiiM {host}",
            update_interval=timedelta(seconds=5),  # HA schedules based on this
        )
```

**Why HA Controls This:**
- HA needs to coordinate polling across many integrations
- HA manages system resources (CPU, network, battery)
- HA provides retry logic and error recovery
- HA can pause/resume polling based on system state

#### 2. **Polling Interval (HOW OFTEN to Poll)**

**Owner: pywiim (recommends) + HA (applies)**

The library recommends optimal intervals, but HA applies them:

```python
# pywiim recommends
interval = self._polling_strategy.get_optimal_interval(role, is_playing)
# Returns: 5.0 (WiiM playing), 5.0 (WiiM idle), 3.0 (Legacy playing), etc.

# HA applies the recommendation
if self.update_interval.total_seconds() != interval:
    self.update_interval = timedelta(seconds=interval)
    # HA will now schedule polls at this interval
```

**Why This Separation:**
- **pywiim** knows device capabilities and optimal intervals
- **HA** controls the actual scheduling mechanism
- **Integration** bridges the two (gets recommendation, applies to HA)

**Best Practice:** Always query the strategy and apply the recommendation. Don't hardcode intervals in the integration.

#### 3. **What to Poll (WHICH Endpoints to Fetch)**

**Owner: pywiim (recommends) + Integration (decides)**

The library provides conditional fetching helpers, but the integration decides what to fetch:

```python
# pywiim recommends
if self._polling_strategy.should_fetch_device_info(self._last_device_info_check, now):
    # Integration decides to fetch
    fetch_tasks.append(self.player.get_device_info())
```

**Why This Separation:**
- **pywiim** knows:
  - Which endpoints are supported (capability detection)
  - Optimal fetch intervals (60s for device info, 15s for multiroom, etc.)
  - When metadata should be fetched (track change detection)
- **Integration** knows:
  - What data entities need
  - How to structure the data dict
  - When to parallelize fetches

**Best Practice:** Always use `PollingStrategy.should_fetch_*()` methods. Don't hardcode intervals or skip capability checks.

#### 4. **State Management (HOW to Fetch and Cache)**

**Owner: pywiim**

The library handles all state management:

```python
# Player manages state fetching and caching
await self.player.refresh()  # Fetches HTTP state, updates cache

# StateSynchronizer merges HTTP + UPnP
# (happens automatically inside Player)
```

**What pywiim Does:**
- Fetches HTTP state via `WiiMClient`
- Caches state in `Player` object
- Merges HTTP + UPnP via `StateSynchronizer`
- Provides convenient properties (`player.volume_level`, `player.media_title`, etc.)
- Handles position estimation (hybrid approach)

**What Integration Does:**
- Calls `player.refresh()` when HA schedules a poll
- Accesses state via `Player` properties
- Returns data dict for entities

**Best Practice:** Always use `Player.refresh()` for state updates. Don't call `client.get_player_status()` directly.

#### 5. **UPnP Events (Real-time Updates)**

**Owner: pywiim**

The library handles UPnP event subscriptions and merging:

```python
# Integration creates eventer
self.eventer = UpnpEventer(
    self.upnp_client,
    self.player,  # Player implements apply_diff()
    device_info.uuid,
    state_updated_callback=self._on_upnp_event,
)

# pywiim handles everything else:
# - Subscribes to UPnP events
# - Parses LastChange XML
# - Calls player.apply_diff() to merge with HTTP state
# - StateSynchronizer resolves conflicts automatically
```

**What pywiim Does:**
- Manages UPnP subscriptions
- Parses UPnP events
- Merges UPnP events with HTTP state (via `StateSynchronizer`)
- Handles subscription failures and reconnection

**What Integration Does:**
- Creates `UpnpClient` and `UpnpEventer`
- Provides callback to trigger coordinator updates
- Calls `eventer.start()` to begin subscriptions

**Best Practice:** Let pywiim handle all UPnP event processing. Integration just needs to trigger coordinator updates on events.

### Design Patterns Used

#### 1. **Strategy Pattern**
- `PollingStrategy` encapsulates polling recommendations
- Integration uses strategy without knowing implementation details
- Strategy adapts based on device capabilities and state

#### 2. **Template Method Pattern**
- HA defines the polling template (`_async_update_data()`)
- Integration fills in the details (what to fetch, how to structure data)
- Library provides helpers (`PollingStrategy`, `Player.refresh()`)

#### 3. **Observer Pattern**
- `UpnpEventer` observes UPnP events
- `Player` observes state changes (via `on_state_changed` callback)
- Coordinator observes both and updates entities

#### 4. **State Synchronization Pattern**
- `StateSynchronizer` merges multiple state sources
- Conflict resolution based on freshness and priority
- Graceful degradation when sources unavailable

### Best Practices Summary

#### ✅ DO:

1. **Let HA Control Scheduling**
   - Use `DataUpdateCoordinator` for polling schedule
   - Don't create custom polling loops

2. **Use Library Recommendations**
   - Always query `PollingStrategy.get_optimal_interval()`
   - Always use `PollingStrategy.should_fetch_*()` methods
   - Apply recommendations to HA's `update_interval`

3. **Use Player for State**
   - Always call `player.refresh()` in `_async_update_data()`
   - Access state via `Player` properties
   - Don't call `client.get_player_status()` directly

4. **Let Library Handle Merging**
   - Don't manually merge HTTP + UPnP state
   - `StateSynchronizer` handles it automatically
   - Just trigger coordinator updates on UPnP events

5. **Respect Capabilities**
   - Always check `capabilities` before fetching optional endpoints
   - Use `PollingStrategy.should_fetch_*()` which respects capabilities

#### ❌ DON'T:

1. **Don't Hardcode Intervals**
   - Don't hardcode `update_interval = timedelta(seconds=5)`
   - Always query strategy and apply recommendation

2. **Don't Bypass Player**
   - Don't call `client.get_player_status()` directly
   - Don't manually manage state caching
   - Use `Player.refresh()` and properties

3. **Don't Manually Merge State**
   - Don't try to merge HTTP + UPnP manually
   - `StateSynchronizer` handles it automatically

4. **Don't Ignore Capabilities**
   - Don't fetch endpoints without checking support
   - Use `PollingStrategy.should_fetch_*()` which checks capabilities

5. **Don't Create Custom Polling Loops**
   - Don't use `asyncio.create_task()` for polling
   - Use HA's `DataUpdateCoordinator` framework

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ Home Assistant (Framework)                                   │
│  - Schedules polling via DataUpdateCoordinator              │
│  - Manages update_interval                                   │
│  - Handles retries and error recovery                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Calls _async_update_data() at interval
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ Integration (Coordinator)                                    │
│  - Orchestrates between HA and pywiim                        │
│  - Queries PollingStrategy for recommendations              │
│  - Applies recommendations to HA's update_interval            │
│  - Decides what to fetch based on strategy recommendations   │
│  - Structures data dict for entities                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ Uses Player.refresh() and strategy helpers
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ pywiim (Library)                                             │
│  - PollingStrategy: Recommends intervals and what to fetch  │
│  - Player: Fetches and caches state                         │
│  - StateSynchronizer: Merges HTTP + UPnP                     │
│  - UpnpEventer: Subscribes to UPnP events                   │
│  - WiiMClient: HTTP API calls                                │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ HTTP requests and UPnP subscriptions
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ WiiM Device                                                  │
│  - HTTP API endpoints                                        │
│  - UPnP event notifications                                  │
└─────────────────────────────────────────────────────────────┘
```

### Key Takeaways

1. **HA Controls WHEN**: Home Assistant schedules polling via `DataUpdateCoordinator`
2. **pywiim Recommends HOW OFTEN**: `PollingStrategy` recommends optimal intervals
3. **pywiim Recommends WHAT**: `PollingStrategy.should_fetch_*()` recommends what to fetch
4. **Integration Orchestrates**: Coordinator bridges HA and pywiim, applies recommendations
5. **pywiim Manages State**: `Player` handles fetching, caching, and merging
6. **Separation of Concerns**: Each layer has clear responsibilities
7. **Framework Agnostic**: pywiim provides recommendations, doesn't control scheduling

This architecture ensures:
- ✅ Framework independence (pywiim works with any async framework)
- ✅ Optimal performance (adaptive intervals, conditional fetching)
- ✅ Maintainability (clear responsibilities, no duplication)
- ✅ Testability (each layer can be tested independently)

## Summary

1. **Use Player Class**: Recommended for HA integrations - state caching, HTTP + UPnP sync, convenient properties
2. **StateSynchronizer**: Automatically merges HTTP polling + UPnP events with conflict resolution
3. **Library Provides Strategy**: `PollingStrategy` recommends optimal intervals
4. **HA Manages Polling**: `DataUpdateCoordinator` schedules updates
5. **Dynamic Adaptation**: Intervals adjust based on device state
6. **Conditional Fetching**: Library helpers optimize API calls
7. **Seamless Integration**: Works naturally with HA's async architecture
8. **Session Management**: Use HA's shared session for HTTP, library handles UPnP
9. **UPnP Client**: Integration creates UPnP client for events and queue management
10. **Full API Access**: Access all methods via `player.client.*` when needed

## Complete Integration Checklist

### Required Setup

- [ ] Create `WiiMClient` with HA's shared session
- [ ] Create `Player` with client
- [ ] Initialize `PollingStrategy` with device capabilities
- [ ] Implement `_async_update_data()` with `player.refresh()`
- [ ] Return data using Player properties
- [ ] Handle errors gracefully (return cached data on transient failures)

### Optional: UPnP Events

- [ ] Create `UpnpClient` using `UpnpClient.create()`
- [ ] Create `Player` with `upnp_client` parameter
- [ ] Create `UpnpEventer` with UPnP client and Player
- [ ] Call `eventer.start()` to begin subscriptions
- [ ] Handle UPnP event callbacks to trigger coordinator updates
- [ ] StateSynchronizer automatically merges UPnP events with HTTP polling

### Optional: Queue Management

- [ ] Create `UpnpClient` (can share with `UpnpEventer`)
- [ ] Create `Player` with `upnp_client` parameter
- [ ] Implement `async_play_media()` with `ATTR_MEDIA_ENQUEUE` support
- [ ] Add `MediaPlayerEntityFeature.MEDIA_ENQUEUE` to supported features
- [ ] Handle `WiiMError` when UPnP client not available

### Optional: Group Join/Unjoin Operations

- [ ] Set `on_state_changed` callback when creating `Player` (for automatic coordinator updates)
- [ ] Implement `async_join_group()` service (just call `player.join_group()`)
- [ ] Implement `async_leave_group()` service (just call `player.leave_group()`)
- [ ] Access group role via `player.role` property (computed from group membership)
- [ ] Access group members via `player.group.all_players` when in group

**Note**: Library now handles all preconditions, state updates, and callbacks automatically.

## Cover Art Handling

### Direct Image Fetching

pywiim can fetch cover art images directly and cache them, providing more reliable cover art than using URLs directly:

```python
# In media player entity
async def async_get_media_image(self) -> tuple[bytes | None, str | None]:
    """Return image bytes and content type of current playing media."""
    player = self.coordinator.data.get("player")
    if not player:
        return (None, None)
    
    result = await player.fetch_cover_art()
    if result:
        return result  # (image_bytes, content_type)
    return (None, None)
```

**Benefits:**
- ✅ Handles expired URLs gracefully
- ✅ Automatic caching (1 hour TTL, max 10 images per player)
- ✅ Uses client's HTTP session for fetching
- ✅ More reliable than passing URLs directly to HA
- ✅ Automatically falls back to WiiM logo when no valid cover art is available

**When to Use:**
- When cover art URLs from devices expire or become inaccessible
- When you want to cache images to reduce network requests
- When you need to serve images via your own HTTP endpoint

**Alternative:** You can still use `player.media_image_url` to get the URL and let HA fetch it directly (simpler, but less reliable if URLs expire).

**Note:** When no valid cover art is available (e.g., web radio stations without artwork), pywiim automatically provides the WiiM logo as a fallback, ensuring a consistent user experience.

## Future Optimizations

1. **UPnP Session Reuse**: Could optimize UPnP client to reuse HTTP session when SSL not needed
2. **Session Lifecycle**: Could add context manager support for automatic cleanup
3. **Connection Pooling**: Document best practices for session sharing across devices
