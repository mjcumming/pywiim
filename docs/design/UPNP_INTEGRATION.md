# UPnP Integration Patterns

## Overview

The `pywiim` library uses a **hybrid approach** for device communication (formalized in **[ADR 004: UPnP for Events Only, HTTP for Control](adr/004-upnp-events-http-control.md)**):
- **UPnP**: For real-time event notifications (play/pause, volume, track changes)
- **HTTP API**: For all device control and configuration

This differs from some other implementations (like [WiiM Play](https://github.com/shumatech/wiimplay)) which use UPnP for both events and transport control.

## UPnP Usage: Events Only

### What We Use UPnP For

✅ **Event Notifications** (via DLNA DMR pattern):
- Play/pause/stop state changes
- Volume changes
- Mute state changes
- Track metadata updates (title/artist/album/artwork)
- Position updates

❌ **What We DON'T Use UPnP For**:
- Playback control (play, pause, stop, next, previous)
- Volume control
- Source selection
- EQ settings
- Audio output mode
- Group management
- Any device configuration

**All control operations use the HTTP API** (`/httpapi.asp?command=...`)

## Architecture

### UPnP Event Flow

```
Device State Change (play/pause/volume)
    ↓
UPnP Service (AVTransport/RenderingControl)
    ↓
UPnP Event Notification (via callback URL)
    ↓
UpnpEventer receives event
    ↓
Merges event state into StateSynchronizer
    ↓
Player.update_from_upnp() updates cached state
    ↓
Application receives state change callback
```

### HTTP API Control Flow

```
User Action (play/pause/volume)
    ↓
Player.set_volume() / Player.play() (library method)
    ↓
WiiMClient sends HTTP API command
    ↓
Device executes command
    ↓
UPnP event notification (if UPnP working)
    OR
HTTP polling detects change (if UPnP not working)
    ↓
StateSynchronizer merges state
    ↓
Player updates cached state
    ↓
Application receives state change callback
```

## Why This Hybrid Approach?

### Advantages

1. **Reliability**: HTTP API is always available, even if UPnP fails
2. **Consistency**: All control uses same API, regardless of UPnP status
3. **Simplicity**: Single control path (HTTP API) is easier to maintain
4. **Feature Completeness**: HTTP API supports all WiiM-specific features (EQ, audio output, groups, etc.)
5. **Graceful Degradation**: If UPnP fails, HTTP polling works perfectly

### Comparison with Other Implementations

**WiiM Play Approach:**
- UPnP for transport control (play/pause/seek/volume)
- HTTP API for device-specific features (EQ, audio output, balance, fade)

**Our Approach:**
- UPnP for events only (notifications)
- HTTP API for everything (control + device features)

**Why We Chose This:**
- Framework-agnostic pattern: Most integrations use HTTP API for control
- Simpler codebase: One control path instead of two
- Better error handling: HTTP API errors are easier to handle than UPnP SOAP errors
- Feature parity: HTTP API supports everything, UPnP doesn't (no EQ, no groups, etc.)

## Implementation Details

### UPnP Client Setup

Following the **DLNA DMR pattern** (same as Samsung TV and DLNA DMR integrations):

```python
# From pywiim/upnp/client.py
class UpnpClient:
    """UPnP client wrapper using async-upnp-client DmrDevice pattern."""

    async def _initialize(self):
        # Create UPnP device from description.xml
        factory = UpnpFactory(requester, non_strict=True)
        device = await factory.async_create_device(self.description_url)

        # Create DmrDevice wrapper for subscriptions
        self._dmr_device = DmrDevice(device, event_handler)

        # Get services
        self._av_transport_service = device.service("urn:schemas-upnp-org:service:AVTransport:1")
        self._rendering_control_service = device.service("urn:schemas-upnp-org:service:RenderingControl:1")
```

### Event Subscription

```python
# From pywiim/upnp/eventer.py
class UpnpEventer:
    """Handles UPnP events and merges into state."""

    async def subscribe(self):
        """Subscribe to UPnP services."""
        try:
            await self._dmr_device.async_subscribe_services(auto_resubscribe=True)
        except UpnpResponseError as err:
            # Device rejected subscription - fall back to HTTP polling
            _LOGGER.debug("Device rejected subscription: %r", err)
```

### Event Handling

```python
# From pywiim/upnp/eventer.py
class UpnpEventer:
    """Handles UPnP events and merges into state."""

    def _on_event(self, service, state_variables):
        # Parse UPnP event state variables
        # Call state_manager.apply_diff() with changes
        # State manager merges into Player's cached state
```

### State Merging

Events are merged into the Player's state via `StateSynchronizer`:

```python
# From pywiim/player.py
class Player:
    def update_from_upnp(self, data: dict[str, Any]):
        """Update state from UPnP events."""
        # Update StateSynchronizer with UPnP data
        self._state_synchronizer.update_from_upnp(data)
        
        # Get merged state from synchronizer
        merged_state = self._state_synchronizer.get_merged_state()
        
        # Update cached models with merged state
        if self._status_model:
            # Update fields from merged state
            ...
        
        # Notify application of state change
        if self._on_state_changed:
            self._on_state_changed()
```

## UPnP Services Used

### AVTransport Service

**Purpose**: Transport state events (play/pause/stop, track changes)

**Events We Listen To:**
- `TransportState` - Current playback state
- `CurrentTrackMetaData` - Track metadata
- `CurrentTrack` - Current track number
- `CurrentTrackDuration` - Track duration (provided when track starts)
- `RelativeTimePosition` - Current position (provided when track starts)

**Note on Position/Duration:**
- `CurrentTrackDuration` and `RelativeTimePosition` **ARE provided in UPnP events when a new track starts**
- These values are included in the `LastChange` event notification when playback begins or track changes
- UPnP events do **NOT** send continuous position updates during playback - only on track changes
- During playback: Position is estimated locally using a timer (based on elapsed time)
- Periodic HTTP polling (every 5 seconds) corrects any drift in the local estimation
- The library uses: UPnP for initial position/duration on track start → local timer estimation during playback → periodic HTTP polling to correct drift

**We DON'T Use:**
- `Play()` - We use HTTP API `setPlayerCmd:play`
- `Pause()` - We use HTTP API `setPlayerCmd:pause`
- `Stop()` - We use HTTP API `setPlayerCmd:stop`
- `Seek()` - We use HTTP API `setPlayerCmd:seek`

### RenderingControl Service

**Purpose**: Volume and mute events

**Events We Listen To:**
- `Volume` - Current volume level
- `Mute` - Mute state

**We DON'T Use:**
- `SetVolume()` - We use HTTP API `setPlayerCmd:vol:<level>`
- `SetMute()` - We use HTTP API `setPlayerCmd:mute:<state>`

## Configuration

### UPnP Discovery

UPnP devices are discovered via SSDP (Simple Service Discovery Protocol):

```python
# From pywiim/discovery.py
# SSDP discovery provides:
ssdp_info = {
    "location": "http://192.168.1.68:49152/description.xml",
    "st": "urn:schemas-upnp-org:device:MediaRenderer:1",
    "usn": "uuid:FF31F09E-1A50-2011-3B0A-3918FF31F09E",
}
```

### Description URL

WiiM devices serve UPnP description on **port 49152** (HTTP, not HTTPS):

```
http://<device_ip>:49152/description.xml
```

### Callback URL

UPnP events are delivered to a callback URL on the application:

```
http://<app_ip>:<random_port>/notify/<subscription_id>
```

**Important**: The callback URL must be reachable from the device's network. This can be problematic in Docker/WSL environments.

## Fallback Strategy

### Graceful Degradation

If UPnP fails at any stage, the library falls back to HTTP polling:

1. **Description fetch fails** → HTTP polling
2. **Service not found** → HTTP polling
3. **Subscription rejected** → HTTP polling
4. **Events not arriving** → HTTP polling (but no way to detect this reliably)

### HTTP Polling Fallback

When UPnP is unavailable:
- **Playing state**: Poll every 1 second
- **Idle state**: Poll every 5 seconds
- **All functionality works perfectly**

This is the same polling strategy used when UPnP is working (UPnP events supplement polling, don't replace it).

## UPnP Health Tracking

### The Challenge

UPnP has **no heartbeat** - events only occur on state changes. This makes it impossible to reliably detect if UPnP is working when the device is idle using time-based methods alone.

### Why Time-Based Detection Fails

**Naive Approach (❌ WRONG):**
```python
if time_since_last_upnp_event > 5.0:
    upnp_working = False  # Assume broken
```

**Why It Fails:**
- **False Negative**: When device is idle (not playing), there are no state changes, so no UPnP events are sent
- An idle device with working UPnP will be incorrectly flagged as "broken"
- Can't distinguish between "UPnP is broken" vs "UPnP is working but device is idle"

### The Solution: Change-Based Detection

**Smart Approach (✅ CORRECT):**
```python
# ✅ CORRECT: Change-based detection
if polling_detected_change and not upnp_reported_change:
    missed_changes += 1  # Evidence that UPnP missed something
```

**Why It Works:**
- Only checks UPnP health when there's actual proof (a missed change)
- Idle device = no changes = no false negatives
- Active device with broken UPnP = missed changes = correctly detected
- Self-healing: Can detect when UPnP recovers

### How Health Tracking Works

#### 1. State Monitoring

The health tracker monitors specific fields that UPnP should **always** notify about:

```python
UPNP_MONITORED_FIELDS = {
    "play_state",  # play/pause/stop always fires UPnP event
    "volume",      # Volume changes always fire UPnP event
    "muted",       # Mute changes always fire UPnP event
    "title",       # Track changes include metadata updates
    "artist",      # Track changes include metadata updates
    "album",       # Track changes include metadata updates
}
```

**Note:** We deliberately **don't** monitor `position`/`duration` because:
- UPnP only sends these on track start, not continuously during playback
- Position during playback is estimated locally, not via UPnP events

#### 2. Change Detection Flow

```
┌─────────────────┐
│  HTTP Poll #1   │  play_state: "pause", volume: 50
└────────┬────────┘
         │ (store state)
         ▼
┌─────────────────┐
│  HTTP Poll #2   │  play_state: "play", volume: 60  ← CHANGE DETECTED!
└────────┬────────┘
         │
         ├─► Check: Did UPnP report play_state="play"?
         │          ├─ Yes (within 2s) → ✅ UPnP caught it
         │          └─ No → ❌ UPnP missed it (missed_changes++)
         │
         └─► Check: Did UPnP report volume=60?
                    ├─ Yes (within 2s) → ✅ UPnP caught it
                    └─ No → ❌ UPnP missed it (missed_changes++)
```

#### 3. Health Assessment

The tracker uses **hysteresis** to avoid flapping between healthy/unhealthy:

```python
if miss_rate > 50%:  # More than half of changes missed
    status = UNHEALTHY  # Mark as degraded
elif miss_rate < 20%:  # Catching most changes
    status = HEALTHY    # Mark as healthy
# Between 20-50%: Keep current status (hysteresis)
```

#### 4. Adaptive Polling Response

When UPnP is detected as unhealthy:

```python
# Normal polling (UPnP working)
interval = 5.0  # Poll every 5 seconds (when playing)

# Fast polling (UPnP degraded)
if is_playing and not upnp_healthy:
    interval = 1.0  # Poll every 1 second to compensate
```

### Implementation: UpnpHealthTracker

Located in `pywiim/upnp/health.py`:

```python
from pywiim.upnp.health import UpnpHealthTracker

# Initialize tracker
tracker = UpnpHealthTracker(
    grace_period=2.0,  # Wait 2 seconds for UPnP event to arrive
    min_samples=3,     # Need 3 changes before making decisions
)

# After each HTTP poll
tracker.on_poll_update({
    "play_state": player.play_state,
    "volume": player.volume,
    "muted": player.muted,
    "title": player.media_title,
    "artist": player.media_artist,
    "album": player.media_album,
})

# When UPnP event arrives
tracker.on_upnp_event({
    "play_state": player.play_state,
    "volume": player.volume,
    # ... same fields
})

# Check health status
if tracker.is_healthy:
    print("✅ UPnP working!")
else:
    print("❌ UPnP degraded, switching to fast polling")

# Get detailed statistics
stats = tracker.statistics
print(f"Miss rate: {stats['miss_rate']*100:.1f}%")
```

### Key Features

1. **Grace Period for Race Conditions**: 2-second window to handle network latency and asynchronous timing
2. **Minimum Sample Requirement**: Requires at least 3 detected changes before making health decisions
3. **Self-Healing / Recovery Detection**: Detects when UPnP recovers and resets statistics
4. **Hysteresis**: 20-50% gap prevents flapping between healthy/unhealthy states

### Design Decisions

- **Why 2-Second Grace Period?** Network latency typically < 500ms, event processing < 500ms, 2 seconds provides comfortable margin
- **Why 50% Threshold for Unhealthy?** Conservative threshold - occasional missed event (< 20%) = acceptable, consistent missing (> 50%) = clearly broken
- **Why Hysteresis?** Prevents "flapping" between states when miss rate hovers around threshold

### Resubscription Failure Detection

Detect empty `state_variables` as resubscription failure indicator:

```python
def _on_event(self, service, state_variables):
    """Handle UPnP event."""
    if not state_variables:
        # Empty state_variables indicates resubscription failure
        _LOGGER.warning("UPnP event with empty state_variables - subscription may have failed")
        # HTTP polling will become authoritative
        return
    
    # Process event normally
    ...
```

## Benefits of Our Approach

### 1. Reliability

- ✅ HTTP API always works (even if UPnP fails)
- ✅ Graceful fallback to polling
- ✅ No single point of failure

### 2. Simplicity

- ✅ Single control path (HTTP API)
- ✅ Consistent error handling
- ✅ Easier to debug

### 3. Feature Completeness

- ✅ All WiiM features available via HTTP API
- ✅ UPnP doesn't support EQ, groups, audio output, etc.
- ✅ No need to mix UPnP and HTTP for different features

### 4. Performance

- ✅ UPnP events provide instant updates (when working)
- ✅ HTTP polling provides reliable updates (always working)
- ✅ Best of both worlds

## Key Takeaways

1. **UPnP is for events, not control** - We use HTTP API for all control operations
2. **Hybrid approach** - UPnP provides real-time events, HTTP API provides control
3. **Graceful fallback** - If UPnP fails, HTTP polling works perfectly
4. **DLNA DMR pattern** - We follow the same pattern as Samsung TV and DLNA DMR integrations
5. **Optional optimization** - UPnP is nice-to-have, not required for functionality
6. **No health checking** - UPnP has no heartbeat, events only on changes
7. **Cooperative sources** - HTTP and UPnP work together, not one authoritative

## Audio-Quality Metadata (Bitrate / Sample Rate / Bit Depth)

UPnP DIDL-Lite metadata does **not** reliably include audio-quality fields. In `pywiim`,
these fields are retrieved from the HTTP endpoint `getMetaInfo` and cached as
`player.metadata` (used by `player.media_bit_rate`, `player.media_sample_rate`,
`player.media_bit_depth`).

Because `getMetaInfo` is not part of the core UPnP event flow, `pywiim` refreshes it:
- On startup / full refresh
- On track change
- Periodically while playing

## Related Documentation

- **[ARCHITECTURE_DATA_FLOW.md](ARCHITECTURE_DATA_FLOW.md)** - How HTTP and UPnP state is merged
- **[API_DESIGN_PATTERNS.md](API_DESIGN_PATTERNS.md)** - HTTP API reference (used for all control)
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Overall library architecture

