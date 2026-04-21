# Home Assistant Integration: Capability Properties

This document describes how to use pywiim's capability properties in a Home Assistant integration.

## Overview

pywiim exposes device capabilities as **boolean properties** on the `Player` class. This allows integrations to check feature support before calling methods, enabling proper UI rendering and avoiding errors.

### Single source of truth (required)

For **device-level optional HTTP API** features (EQ, PEQ, presets, subwoofer, 12V trigger, alarms, metadata, audio output mode, etc.), **`player.client.capabilities`** — the same mapping returned after `await player.client._detect_capabilities()` / `refresh_capabilities()` — is the **only** authority. Use the **`Player` properties** listed below when they exist (they mirror those keys), or read **`player.client.capabilities.get("supports_…")`** directly.

**Do not** create Home Assistant entities, buttons, or number platforms for those features based only on **model name**, **device class**, or **“WiiM X usually has Y”** heuristics. If a key is `False` (or not `True` where tri-state applies), the feature stays hidden or disabled. After firmware OTA, call **`await player.client.refresh_capabilities(force=True)`** if you need a full re-probe, then re-evaluate the same dict.

This is **[ADR 018: Client `capabilities` Dict — Single Source of Truth](../design/adr/018-capabilities-dict-source-of-truth.md)**. It complements [ADR 003](../design/adr/003-capability-probing-before-endpoints.md) (probe before use) and [ADR 016](../design/adr/016-connect-time-read-only-capability-probes.md) (how connect-time probes work).

## Available Capability Properties

### HTTP API Capabilities

These capabilities are detected via endpoint probing during device initialization:

| Property | Description | Default |
|----------|-------------|---------|
| `player.supports_eq` | EQ control (presets, bands) | Varies |
| `player.client.capabilities.get("supports_peq")` | Parametric EQ (PEQ) – 10-band per-source, WiiM only | WiiM: True, others: False |
| `player.supports_presets` | Playback presets/favorites | Varies |
| `player.presets_full_data` | Preset names/URLs available (WiiM) vs count only (LinkPlay) | WiiM: True, LinkPlay: False |
| `player.supports_audio_output` | Audio output mode control | Varies |
| `player.supports_metadata` | Metadata retrieval (getMetaInfo) | Varies |
| `player.supports_alarms` | Alarm clock feature | WiiM only |
| `player.supports_sleep_timer` | Sleep timer feature | WiiM only |
| `player.supports_led_control` | LED control (primary setLED/setLEDBrightness) | Varies |
| `player.supports_led_switch` | Status Light (LED_SWITCH_SET) – internal | Probed at init (WiiM); Arylic: vendor |
| `player.supports_led_indicator` | LED Indicator on/off (ADR 005; use get_led_indicator / set_led_indicator) | Arylic + WiiM |
| `player.supports_display_config` | Display/LCD on-off and brightness (WiiM Ultra only) | WiiM Ultra only |
| `player.supports_subwoofer` | Subwoofer configuration | WiiM only (not Arylic) |
| `player.supports_trigger_out` | 12V trigger output (amplifier control) | WiiM Ultra / Pro / Pro Plus |

### UPnP Capabilities

These capabilities depend on UPnP client initialization and service availability:

| Property | Description | Notes |
|----------|-------------|-------|
| `player.supports_upnp` | UPnP client is available | Requires `upnp_client` parameter |
| `player.supports_queue_browse` | Full queue retrieval (ContentDirectory) | WiiM Amp/Ultra + USB only |
| `player.supports_queue_add` | Add items to queue (AVTransport) | Most devices with UPnP |
| `player.supports_queue_count` | Queue count/position (HTTP API) | Always `True` |

### Transport Capabilities

These properties indicate whether next/previous track and seek commands are supported for the current source:

| Property | Description | Notes |
|----------|-------------|-------|
| `player.supports_next_track` | Next track is supported | **Use this, NOT queue_count!** |
| `player.supports_previous_track` | Previous track is supported | **Use this, NOT queue_count!** |
| `player.supports_seek` | Seeking within track is supported | Depends on current source |

⚠️ **IMPORTANT**: Do NOT use `queue_count > 0` to determine next/prev support!

Streaming services (Spotify, Amazon Music, Tidal, etc.) always report `queue_count=0` because they manage their own queues internally. However, next/previous track commands work perfectly. Use `supports_next_track` and `supports_previous_track` instead.

**Returns True for:**
- Streaming services: Spotify, Amazon Music, Tidal, Qobuz, Deezer, Pandora
- Local playback: USB, Network (WiFi), HTTP streams with playlists
- External casting: AirPlay, Bluetooth, DLNA (commands forwarded to source app)
- Multiroom slaves: Commands route through Group to master (same as play/pause)

**Returns False for:**
- Live radio: TuneIn, iHeartRadio (no "next track" concept)
- Physical inputs: Line-in, Optical, Coaxial, HDMI (passthrough audio)

**Seek support (`supports_seek`):**
- Returns True for sources where seeking within a track makes sense (USB, Network, streaming services with known duration)
- Returns False for live streams, radio, and physical inputs

### Playback State Properties

These properties provide clean boolean checks for playback state, eliminating the need to parse raw `play_state` strings:

| Property | Description | Notes |
|----------|-------------|-------|
| `player.is_playing` | Device is playing (including buffering) | True for: play, playing, buffering, loading, transitioning |
| `player.is_paused` | Device is paused | True for: pause (also normalized "stop") |
| `player.is_idle` | Device is idle (no media) | True for: idle, none, or when state is None |
| `player.is_buffering` | Device is loading/buffering | True for: buffering, loading, transitioning |
| `player.state` | Normalized state string | Returns: `"playing"`, `"paused"`, `"idle"`, or `"buffering"` |

**Two approaches for state mapping:**

```python
# Option 1: Full state mapping (expose BUFFERING state)
# Shows loading indicator during track transitions
STATE_MAP = {
    "playing": MediaPlayerState.PLAYING,
    "paused": MediaPlayerState.PAUSED,
    "idle": MediaPlayerState.IDLE,
    "buffering": MediaPlayerState.BUFFERING,
}
return STATE_MAP[player.state]

# Option 2: Simplified mapping (collapse buffering to playing)
# Avoids UI flickering during track transitions
if player.is_playing:  # includes buffering states
    return MediaPlayerState.PLAYING
elif player.is_paused:
    return MediaPlayerState.PAUSED
else:
    return MediaPlayerState.IDLE
```

**Design rationale:** pywiim exposes the full state including `"buffering"` to give integrations maximum flexibility. The integration can choose whether to show a loading indicator during buffering/transitioning states, or collapse them to "playing" for simpler UX.

**Note:** The "stop" state is normalized to "pause" for modern UX (both indicate media is loaded but not playing, position is maintained). Use `is_paused` to check for both paused and stopped states.

### Safe Accessor Properties

These properties provide safe access to nested data, eliminating None checks and chained attribute access:

| Property | Type | Description |
|----------|------|-------------|
| `player.discovered_endpoint` | `str \| None` | Full endpoint URL (e.g., "https://192.168.1.100:443") |
| `player.input_list` | `list[str]` | Raw input list from device, `[]` if unavailable |
| `player.available_sources` | `list[str]` | Available sources, `[]` if unavailable |
| `player.eq_presets` | `list[str]` | EQ presets, `[]` if unavailable |
| `player.group_master_name` | `str \| None` | Safe accessor for `player.group.master.name` |

**Eliminates unsafe chained access:**

```python
# ❌ Before - unsafe chained access
if player and player.device_info and player.device_info.name:
    return player.device_info.name

if player.is_slave and player.group and player.group.master:
    attrs["coordinator_name"] = player.group.master.name

for source in player.available_sources or []:  # needed None guard
    ...

# ✅ After - safe property access
return player.name  # already handles None device_info

if player.is_slave:
    attrs["coordinator_name"] = player.group_master_name  # safe accessor

for source in player.available_sources:  # always returns list
    ...
```

## Usage in Home Assistant

### Checking Capabilities

```python
from homeassistant.components.media_player import MediaPlayerEntityFeature

class WiiMMediaPlayer(MediaPlayerEntity):
    """WiiM media player entity."""

    def __init__(self, player: Player) -> None:
        self._player = player

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Return supported features based on device capabilities."""
        features = (
            MediaPlayerEntityFeature.PLAY
            | MediaPlayerEntityFeature.PAUSE
            | MediaPlayerEntityFeature.STOP
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_MUTE
        )

        # Next/Previous track - use supports_next_track, NOT queue_count!
        # Streaming services (Spotify, Amazon, etc.) have queue_count=0 but next/prev still work
        if self._player.supports_next_track:
            features |= MediaPlayerEntityFeature.NEXT_TRACK
        if self._player.supports_previous_track:
            features |= MediaPlayerEntityFeature.PREVIOUS_TRACK

        # Queue capabilities
        if self._player.supports_queue_add:
            features |= MediaPlayerEntityFeature.PLAY_MEDIA

        if self._player.supports_queue_browse:
            features |= MediaPlayerEntityFeature.BROWSE_MEDIA

        # EQ/Audio features
        if self._player.supports_eq:
            # Enable EQ-related services
            pass

        if self._player.supports_presets:
            features |= MediaPlayerEntityFeature.SELECT_SOURCE  # For preset selection

        return features
```

### Queue Information

```python
@property
def queue_position(self) -> int | None:
    """Return current position in queue (1-based)."""
    # Always available via HTTP API
    return self._player.queue_position

@property
def queue_size(self) -> int | None:
    """Return total items in queue."""
    # Always available via HTTP API
    return self._player.queue_count

async def async_get_queue(self) -> list[dict] | None:
    """Get full queue contents if supported."""
    if not self._player.supports_queue_browse:
        return None
    
    try:
        return await self._player.get_queue()
    except Exception:
        return None
```

### Conditional Service Registration

```python
async def async_setup_entry(hass, entry, async_add_entities):
    """Set up WiiM media player."""
    player = hass.data[DOMAIN][entry.entry_id]
    
    # Register base entity
    entity = WiiMMediaPlayer(player)
    async_add_entities([entity])
    
    # Register optional services based on capabilities
    if player.supports_eq:
        async_register_eq_services(hass, player)
    
    if player.supports_alarms:
        async_register_alarm_services(hass, player)
    
    if player.supports_sleep_timer:
        async_register_sleep_timer_service(hass, player)
```

### Entity Attributes

```python
@property
def extra_state_attributes(self) -> dict[str, Any]:
    """Return entity state attributes."""
    attrs = {
        "queue_position": self._player.queue_position,
        "queue_count": self._player.queue_count,
    }
    
    # Add capability flags for debugging/automations
    attrs["capabilities"] = {
        "eq": self._player.supports_eq,
        "presets": self._player.supports_presets,
        "audio_output": self._player.supports_audio_output,
        "queue_browse": self._player.supports_queue_browse,
        "queue_add": self._player.supports_queue_add,
        "alarms": self._player.supports_alarms,
        "upnp": self._player.supports_upnp,
    }
    
    return attrs
```

## Queue Operations

### Queue Methods

| Method | Description | Requirements |
|--------|-------------|--------------|
| `get_queue()` | Get queue contents with metadata | `supports_queue_browse` |
| `play_queue(position)` | Play from queue position | `supports_queue_add` |
| `add_to_queue(url)` | Add to end of queue | `supports_queue_add` |
| `insert_next(url)` | Insert after current track | `supports_queue_add` |
| `remove_from_queue(position)` | Remove item at position | `supports_queue_add` |
| `clear_queue()` | Remove all items | `supports_queue_add` |

### Queue Item Format (`get_queue()` return)

```python
[
    {
        "media_content_id": "http://example.com/song.mp3",  # HA standard field
        "title": "Song Title",
        "artist": "Artist Name",
        "album": "Album Name",
        "duration": 240,      # Duration in seconds
        "position": 0,        # 0-based index in queue
        "image_url": "http://example.com/art.jpg",  # Album art (optional)
    },
    # ... more items
]
```

### Adding to Queue (requires `supports_queue_add`)

```python
async def async_play_media(
    self,
    media_type: str,
    media_id: str,
    enqueue: MediaPlayerEnqueue | None = None,
    **kwargs,
) -> None:
    """Play media or add to queue."""
    if enqueue == MediaPlayerEnqueue.ADD and self._player.supports_queue_add:
        await self._player.add_to_queue(media_id)
    elif enqueue == MediaPlayerEnqueue.NEXT and self._player.supports_queue_add:
        await self._player.insert_next(media_id)
    else:
        # Play immediately
        await self._player.play_url(media_id)
```

### Playing from Queue Position

```python
# Service: wiim.play_queue
async def async_play_queue(self, queue_position: int = 0) -> None:
    """Start playing from a specific queue position."""
    if not self._player.supports_queue_add:
        raise HomeAssistantError("Queue playback not supported")
    await self._player.play_queue(queue_position)
```

### Removing from Queue

```python
# Service: wiim.remove_from_queue
async def async_remove_from_queue(self, queue_position: int = 0) -> None:
    """Remove item from queue at position."""
    if not self._player.supports_queue_add:
        raise HomeAssistantError("Queue management not supported")
    await self._player.remove_from_queue(queue_position)

# Service: wiim.clear_queue
async def async_clear_queue(self) -> None:
    """Clear all items from queue."""
    if not self._player.supports_queue_add:
        raise HomeAssistantError("Queue management not supported")
    await self._player.clear_queue()
```

### Browsing Queue (requires `supports_queue_browse`)

```python
async def async_browse_media(
    self,
    media_content_type: str | None = None,
    media_content_id: str | None = None,
) -> BrowseMedia:
    """Browse media library or queue."""
    if media_content_id == "queue" and self._player.supports_queue_browse:
        queue_items = await self._player.get_queue()
        return BrowseMedia(
            media_class=MediaClass.PLAYLIST,
            media_content_id="queue",
            media_content_type="playlist",
            title="Queue",
            can_play=False,
            can_expand=True,
            children=[
                BrowseMedia(
                    media_class=MediaClass.TRACK,
                    media_content_id=item["media_content_id"],
                    media_content_type="music",
                    title=item.get("title", "Unknown"),
                    thumbnail=item.get("image_url"),
                )
                for item in queue_items
            ],
        )
    # ... handle other browse requests
```

## Best Practices

1. **Always check capabilities before calling methods** - Prevents errors and provides better UX.

2. **Use queue_count/queue_position even without queue_browse** - These are always available via HTTP API.

3. **UPnP client is optional** - The Player works without UPnP, but some features require it.

4. **Capabilities are detected at runtime** - They may change if the device configuration changes.

5. **Cache capability checks** - Properties read from cached state, so they're fast to access.

## Migration from Dict-based Capabilities

If you were previously using the dict-based pattern:

```python
# Old pattern (still works but deprecated)
if player.client.capabilities.get("supports_eq", False):
    ...

# New pattern (preferred)
if player.supports_eq:
    ...
```

The new properties are cleaner, provide better IDE support.

