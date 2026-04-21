# Player State Architecture - Data Flow & Source of Truth

## Overview

The Player tracks state from **TWO sources** simultaneously:
1. **HTTP Polling** - periodic queries (e.g., every 5 seconds)
2. **UPnP Events** - real-time push notifications when state changes

These two sources are merged together to provide the most current state.

## The Three-Layer Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         APPLICATION LAYER                            │
│  (monitor, properties, commands - what users/code interact with)    │
└────────────────────────┬────────────────────────────────────────────┘
                         │ reads from
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        MERGE LAYER (NEW)                             │
│                     StateSynchronizer                                │
│  ┌────────────────┐      ┌─────────────┐      ┌─────────────────┐  │
│  │  HTTP State    │      │   MERGED    │      │   UPnP State    │  │
│  │  (polling)     │─────▶│   STATE     │◀─────│   (events)      │  │
│  │  5s intervals  │      │ (live truth)│      │   real-time     │  │
│  └────────────────┘      └─────────────┘      └─────────────────┘  │
│         │                       │                      │             │
│         │ Conflict Resolution:  │                      │             │
│         │  • Device profile-driven (explicit per device) │          │
│         │  • Fallback to freshness-based (legacy)        │             │
│         │  • play_state: profile-defined (often UPnP)    │             │
│         │  • metadata: profile-defined (often HTTP)       │             │
│         │  • position: raw device value (no estimation)   │             │
│         └───────────────────────┴──────────────────────┘             │
└─────────────────────────────────────────────────────────────────────┘
                         │ updates (for backwards compat)
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      CACHE LAYER (LEGACY)                            │
│                    Player._status_model                              │
│  ┌───────────────────────────────────────────────────────────┐      │
│  │  Cached PlayerStatus (updated from merged state)          │      │
│  │  • Originally: only updated during HTTP polling           │      │
│  │  • Now: synced from merged state for backwards compat     │      │
│  └───────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
                         │
                         ▼
                 (Used to be read by properties
                  - now deprecated, but kept
                  for backwards compatibility)
```

## Data Flow: Step by Step

### 1. HTTP Polling (Every 5 seconds)

```python
# In monitor_loop or periodic refresh:
await player.refresh()  # StateManager.refresh()
    │
    ├─▶ status = client.get_player_status_model()  # HTTP call to device
    │
    ├─▶ _state_synchronizer.update_from_http(status_dict)
    │   │   Stores data in: _http_state = {
    │   │       "play_state": TimestampedField(value="play", source="http", timestamp=123456),
    │   │       "volume": TimestampedField(...),
    │   │       "title": TimestampedField(...),
    │   │       ...
    │   │   }
    │   └─▶ _merge_state()  # Merge HTTP + UPnP → _merged_state
    │
    └─▶ _status_model = status  # Update cache (legacy)
        └─▶ Sync _status_model from merged state (for backwards compat)
```

### 2. UPnP Events (Real-time, when changes occur)

```python
# When device sends UPnP event:
upnp_callback(changes)  # changes = {"play_state": "stop", "volume": 50}
    │
    └─▶ player.apply_diff(changes)  # StateManager.apply_diff()
        │
        ├─▶ _state_synchronizer.update_from_upnp(changes)
        │   │   Stores data in: _upnp_state = {
        │   │       "play_state": TimestampedField(value="stop", source="upnp", timestamp=123457),
        │   │       "volume": TimestampedField(...),
        │   │       ...
        │   │   }
        │   └─▶ _merge_state()  # Merge HTTP + UPnP → _merged_state
        │
        └─▶ Update _status_model from merged state (for backwards compat)
```

### 3. Reading State (Properties)

**BEFORE (Broken):**
```python
@property
def play_state(self) -> str | None:
    # ❌ WRONG: Only reads cached HTTP data (5s stale)
    return self._status_model.play_state
```

**AFTER (Fixed):**
```python
@property
def play_state(self) -> str | None:
    # ✅ CORRECT: Reads merged state (HTTP + UPnP)
    merged = self._state_synchronizer.get_merged_state()
    return merged.get("play_state")
```

## Source of Truth: StateSynchronizer._merged_state

The **single source of truth** is:

```python
StateSynchronizer._merged_state  # SynchronizedState object
```

This contains **merged data** from both HTTP and UPnP, resolved using smart conflict resolution:

### Conflict Resolution Rules

The StateSynchronizer uses **device profile-driven resolution** when available, with fallback to freshness-based logic for legacy compatibility.

**Profile-Driven Resolution (Recommended):**
When a `DeviceProfile` is set (detected automatically from device info), the synchronizer uses explicit source preferences defined in the profile's `state_sources` configuration. This eliminates guessing and makes behavior predictable per device type.

Example: Audio Pro MkII devices require UPnP for `play_state` because HTTP API is unreliable. The profile explicitly sets `state_sources.play_state = "upnp"`.

**Legacy Resolution (Fallback):**
When no profile is available, the synchronizer uses global priority rules with freshness windows:

| Field | Default Priority | Reason |
|-------|------------------|--------|
| `play_state` | **UPnP** > HTTP | Real-time state changes are immediate via UPnP |
| `volume` | **UPnP** > HTTP | Volume changes are immediate via UPnP |
| `muted` | **UPnP** > HTTP | Mute changes are immediate via UPnP |
| `position` | **UPnP** > HTTP | UPnP fires on track start, HTTP polls periodically |
| `duration` | **UPnP** > HTTP | UPnP fires on track start |
| `title` | **HTTP** > UPnP | HTTP metadata is more complete |
| `artist` | **HTTP** > UPnP | HTTP metadata is more complete |
| `album` | **HTTP** > UPnP | HTTP metadata is more complete |
| `image_url` | **HTTP** > UPnP | HTTP artwork URLs are more reliable |
| `source` | **HTTP** > UPnP | HTTP source reporting is more accurate |

**Exception:** For Spotify, metadata ONLY comes from UPnP events. HTTP API does not provide Spotify metadata.

**Note:** Position is returned as **raw device value** (no estimation). Integrations must track `media_position_updated_at` timestamp and handle position advancement in the UI layer.

### Freshness Windows

Data is considered "fresh" for different durations:

```python
FRESHNESS_WINDOWS = {
    "play_state": 5.0,   # Changes frequently
    "position": 2.0,      # Changes very frequently  
    "volume": 10.0,       # Changes less frequently
    "title": 30.0,        # Changes less frequently
    "source": 60.0,       # Changes rarely
}
```

If data exceeds its freshness window, it's considered stale and the other source is preferred.

## What We Cache and Why

### 1. `StateSynchronizer._merged_state` (Primary State)
**What:** Merged HTTP + UPnP data with timestamps and source tracking
**Why:** Single source of truth, real-time accurate
**Updated:** Immediately on HTTP poll OR UPnP event

### 2. `Player._status_model` (Legacy Cache)
**What:** Raw HTTP API response, synced with merged state
**Why:** Backwards compatibility - older code may still read this
**Updated:** 
- Every HTTP poll (refresh)
- After UPnP events (synced from merged state)

### 3. `Player._device_info` (Device Info Cache)
**What:** Parsed **getStatusEx** / device info (model, firmware, UUID, name, etc.). This is **not** the same structure as runtime **`supports_*`** flags for optional HTTP endpoints.
**Why:** Rarely changes, expensive to query
**Updated:** Every HTTP poll (refresh)

**Where optional HTTP features are decided:** **`player.client.capabilities`** (merged after `_detect_capabilities()` / `refresh_capabilities()`). Integrations gate entities on that dict, not on `_device_info.model` alone — see **[ADR 018: Client `capabilities` Dict — Single Source of Truth](adr/018-capabilities-dict-source-of-truth.md)**.

### 4. Other Caches
- `_audio_output_status` - Audio output config (rare changes)
- `_eq_presets` - Available EQ presets (rare changes)
- `_metadata` - Audio quality info (changes per track)
- `_bluetooth_history` - Paired BT devices (checked every 60s)
- `_cover_art_cache` - Downloaded album art images (1hr TTL)

## Position Handling: Raw Device Values

**As of v2.1.0, position estimation was removed.** PyWiim now returns **raw position values** directly from the device (via HTTP polling or UPnP events).

### Why Position Estimation Was Removed

Position estimation caused jitter by fighting with integration frontend advancement logic. The correct separation of concerns is:
- **PyWiim**: Returns "what device said" (raw position value)
- **Integration**: Tracks "when we read it" (`media_position_updated_at` timestamp)
- **Frontend**: Handles smooth display advancement

This matches the pattern used by all other Home Assistant media player integrations (Sonos, LinkPlay, etc.).

### How Position Works Now

**Player.media_position Property:**
```python
@property
def media_position(self) -> int | None:
    # Reads raw position from merged state (no estimation)
    merged = self.player._state_synchronizer.get_merged_state()
    position = merged.get("position")
    return int(float(position)) if position is not None else None
```

**Integration Responsibility:**
Integrations must:
1. Track `media_position_updated_at` timestamp when reading position
2. Calculate elapsed time: `elapsed = now - media_position_updated_at`
3. Display: `display_position = media_position + elapsed` (if playing)
4. Update timestamp on each poll/event

This gives integrations full control over position advancement and eliminates jitter.

## Play State Identification

Determining the correct player state (play, pause, stop, idle) is challenging because different sources use different field names and value formats, and some devices don't provide state via HTTP.

### HTTP API State Identification

#### Field Names

The HTTP API uses multiple field names for play state:
- `"status"`, `"state"`, `"player_state"` all map to play state
- Parser checks all possible field names

#### Value Formats and Normalization

HTTP API returns various value formats that need normalization:

**Raw Values:**
- `"play"`, `"playing"` → normalized to `"play"`
- `"pause"`, `"paused"` → normalized to `"pause"`
- `"stop"`, `"stopped"` → normalized to `"pause"` (modern UX: stop == pause)
- `"none"` → normalized to `"idle"` (no media loaded)
- `"load"`, `"loading"`, `"transitioning"`, `"buffering"` → normalized to `"buffering"`

**Rationale for stop→pause mapping:**
Modern streaming devices maintain playback position whether "paused" or "stopped". Users think in terms of "playing" vs "not playing", not three separate states. This aligns with Home Assistant conventions (no STATE_STOPPED) and Sonos behavior.

#### Device-Specific Behavior

- **WiiM Devices**: HTTP provides play_state via `getPlayerStatusEx` or `getStatusEx`
- **Audio Pro Original/W-Generation**: HTTP provides play_state via `getStatusEx`
- **Audio Pro MkII**: ❌ HTTP does NOT provide play_state - must use UPnP (profile-driven)

### UPnP State Identification

#### Field Names

UPnP uses `TransportState` variable in AVTransport service.

#### Value Formats

UPnP uses DLNA standard state values with underscores:
- `"PLAYING"` → `"play"`
- `"PAUSED_PLAYBACK"` → `"pause"`
- `"STOPPED"` → `"pause"` (modern UX)
- `"NO_MEDIA_PRESENT"` → `"idle"`
- `"TRANSITIONING"`, `"LOADING"` → `"buffering"`

Normalization: lowercase, replace underscores with spaces, then map to standard values.

### State Identification Rules

1. **Source Availability**: If only one source has state → use that source
2. **Freshness Check**: If one is stale and one is fresh → use fresh one
3. **Source Priority**: For play_state, UPnP preferred (more timely) unless profile says otherwise
4. **State Normalization**: Normalize all values to standard set ("play", "pause", "idle", "buffering")
5. **Device-Specific**: Audio Pro MkII always uses UPnP (profile-driven)

### Key Takeaways

- HTTP field names vary: check `"state"`, `"status"`, `"player_state"`
- HTTP value normalization: `"none"` → `"idle"`, lowercase all values
- UPnP value normalization: replace underscores, lowercase, map to standard values
- Device variations: Audio Pro MkII doesn't provide HTTP play_state (use profile)
- Source priority: Profile-driven (explicit) > UPnP (default for play_state) > HTTP
- Conflict resolution: Freshness > Priority > Recency

## Why Did We Have This Mess?

### Historical Evolution:

**Phase 1:** Simple HTTP polling only
```python
Player._status_model = await client.get_status()
```

**Phase 2:** Added UPnP events (needed real-time updates)
```python
# Problem: HTTP cache is stale, UPnP events need to update it
```

**Phase 3:** Added StateSynchronizer to merge both sources
```python
StateSynchronizer merges HTTP + UPnP intelligently
```

**Phase 4:** Properties never updated to use StateSynchronizer
```python
# ❌ Properties still reading old cache
# ❌ UPnP events updating merged state, but nobody reading it
# ❌ Monitor shows stale data from cache
```

**Phase 5 (NOW):** Fixed properties to read merged state
```python
# ✅ Properties now read from StateSynchronizer
# ✅ Real-time UPnP updates now visible
# ✅ Cache kept for backwards compatibility only
```

## Summary: What's the Source of Truth?

| Component | Source of Truth | Why |
|-----------|----------------|-----|
| **Real-time state** | `StateSynchronizer._merged_state` | Merges HTTP + UPnP with conflict resolution |
| **Player properties** | Read from `_merged_state` | Always current, real-time accurate |
| **Legacy cache** | `Player._status_model` | Synced from merged state, backwards compat |
| **Device info** | `Player._device_info` | Cached, updated every poll |

## What We Cleaned Up ✅

1. ✅ **Removed duplicate position estimation** - Only StateSynchronizer version remains
2. ✅ **All properties now read from merged state** - Real-time UPnP updates work
3. ✅ **Position timer simplified** - Now reads from StateSynchronizer
4. ✅ **Removed 9 duplicate tracking fields from Player** - Much cleaner architecture

## Future Improvements (Optional)

1. **Deprecate direct `_status_model` access** - Force all reads through properties
2. **Consider removing `_status_model` entirely** - It's now just a synced copy for backwards compat
3. **Add deprecation warnings** - Warn if code tries to access `_status_model` directly

## Recommendation: Read State the Right Way

**DO:**
```python
play_state = player.play_state  # Reads from merged state ✅
volume = player.volume_level     # Reads from merged state ✅
title = player.media_title       # Reads from merged state ✅
```

**DON'T:**
```python
play_state = player._status_model.play_state  # Bypasses merge logic ❌
```

The properties are now the **correct API** - they hide the complexity of the merge layer.

