# Operation Patterns

## Overview

This document defines the patterns for implementing state-changing operations in the pywiim library. The core principle is formalized in **[ADR 002: Trust the API After Success](adr/002-trust-api-after-success.md)**. It covers:
1. **Core Pattern**: The "Trust the API" approach for immediate operations
2. **Operation Categorization**: Which operations need polling vs immediate updates
3. **Implementation Guidelines**: How to implement each pattern consistently

---

## Part 1: Core Pattern - Trust the API & Handle Preconditions

### Core Principles

1. **Trust the API**: If the HTTP call returns successfully, the operation worked. Update state immediately.
2. **Handle Preconditions**: Library automatically handles all preconditions - users don't need to worry about device state.
3. **No Waiting/Polling**: Update state immediately after successful API call. No confirmation needed.
4. **Callbacks**: Notify frameworks (HA) of state changes via callbacks.

### The Pattern

All state-changing operations should follow this pattern:

```python
async def operation(self, params):
    """Perform some operation."""
    # Step 1: Handle preconditions automatically (if needed)
    if needs_preparation():
        await self.prepare_state()
    
    # Step 2: Call API (raises WiiMError on failure)
    await self.client.api_call(params)
    
    # Step 3: Update library state immediately
    self._some_state = new_value
    
    # Step 4: Call callback
    if self._on_state_changed:
        self._on_state_changed()
```

### Example: `join_group()` with Automatic Preconditions and Group-Wide Notifications

```python
async def join_group(self, master: Player) -> None:
    """Join this player to another player.
    
    Library handles all preconditions - users just call this method.
    Library also notifies ALL affected players automatically.
    """
    # Precondition 1: If THIS is a master, disband first
    if self.is_master:
        await self.leave_group()
    
    # Precondition 2: If THIS is a slave, leave current group
    if self.is_slave:
        old_group.remove_slave(self)
    
    # Precondition 3: If TARGET is a slave, have it leave first
    if master.is_slave:
        await master.leave_group()
    
    # Precondition 4: If TARGET is solo, create group
    if master.is_solo:
        await master.create_group()
    
    # Now call API and update state
    await self.client.join_slave(master.host)
    master.group.add_slave(self)
    
    # Notify ALL players in the new group (not just joiner + master)
    for player in master.group.all_players:
        if player._on_state_changed:
            player._on_state_changed()
    
    # Also notify old group members if joining from different group
    if old_group and old_group != master.group:
        for player in old_group.all_players:
            if player._on_state_changed:
                player._on_state_changed()
```

### Why This Works

1. **API Success = Operation Succeeded**: If `_request()` returns, the command was accepted and executed by the device.
2. **API Failure = Exception Raised**: If the operation fails, `WiiMError` is raised immediately.
3. **No Ambiguity**: There's no "maybe it worked" state - it either worked (returned) or failed (raised).

### What About `refresh()`?

`refresh()` is a **separate concern** - it's for:
- Syncing comprehensive device state
- Periodic polling to detect external changes
- Getting state when you don't know what changed

It is **NOT** for confirming operations worked. The API success already confirms that.

**Important**: Player command methods (play, pause, set_volume, etc.) do NOT call `refresh()` internally. State updates happen via:
1. **UPnP Events**: Real-time state updates when available (immediate)
2. **Coordinator Polling**: Framework-level periodic refresh (5-10 seconds)
3. **Explicit Refresh**: User calls `await player.refresh()` when needed (rare)

This design keeps commands fast and avoids redundant network calls.

### Correct vs Wrong Examples

#### ✅ Correct: Update State Immediately

```python
async def join_group(self, master: Player) -> None:
    """Join an existing group."""
    # Call API (raises on failure)
    await self.client.join_slave(master.host)
    
    # Update Group objects immediately
    if master.group is not None:
        master.group.add_slave(self)
    
    # Call callbacks
    if self._on_state_changed:
        self._on_state_changed()
    if master._on_state_changed:
        master._on_state_changed()
```

#### ✅ Correct: Volume Control

```python
async def set_volume(self, volume: float) -> None:
    """Set volume level."""
    # Call API (raises on failure)
    await self.client.set_volume(int(volume * 100))
    
    # Update cached state immediately
    if self._status_model:
        self._status_model.volume = int(volume * 100)
    
    # Update state synchronizer
    self._state_synchronizer.update_from_http({"volume": volume})
    
    # Call callback
    if self._on_state_changed:
        self._on_state_changed()
```

#### ❌ Wrong: Waiting and Polling

```python
async def join_group(self, master: Player) -> None:
    """Join an existing group."""
    # Call API
    await self.client.join_slave(master.host)
    
    # ❌ WRONG: Unnecessary waiting
    await asyncio.sleep(2.0)
    
    # ❌ WRONG: Unnecessary polling
    while not self.is_slave:
        await self.refresh()
        await asyncio.sleep(0.5)
    
    # This is overengineered - the API already told us it worked!
```

#### ❌ Wrong: Refresh to "Confirm"

```python
async def set_volume(self, volume: float) -> None:
    """Set volume level."""
    # Call API
    await self.client.set_volume(int(volume * 100))
    
    # ❌ WRONG: Unnecessary refresh
    await asyncio.sleep(1.0)
    await self.refresh()
    
    # If the API returned, it worked. No need to check.
```

### When to Use Explicit `refresh()`

#### Never for Success Confirmation

If you need to confirm an operation succeeded, the API return is your confirmation.

#### Use Cases for Explicit Refresh

1. **One-off Scripts**: Scripts without polling that need immediate state
2. **Testing**: Defensive verification that device state matches expectations
3. **External Changes**: When something changed outside your control

#### ✅ Correct: One-off Script with Explicit Refresh

```python
# Simple script without coordinator/polling
player = Player(WiiMClient("192.168.1.100"))

await player.play()
await player.refresh()  # Explicit - get fresh state
print(f"Now playing: {player.media_title}")
```

#### ✅ Correct: Integration with Polling (No Explicit Refresh)

```python
# Home Assistant or other framework with coordinator
await player.play()
# State will update via:
# - UPnP events (immediate)
# - Coordinator polling (5-10 seconds)
# No explicit refresh needed!
```

#### ✅ Correct: Testing (Defensive Verification)

```python
# Test code - verify it actually worked
async def test_play():
    await player.play()
    await player.refresh()  # Explicit verification step
    assert player.play_state == "play"
```

#### ❌ Wrong: Explicit Refresh in Integration

```python
# Integration with coordinator (redundant)
await player.play()
await player.refresh()  # ❌ Unnecessary - coordinator already polls!
```

### Benefits

1. **Simpler**: No complex wait/poll logic
2. **Faster**: Immediate state updates
3. **More Reliable**: Trust the API, not timing
4. **Cleaner Code**: One pattern for everything
5. **Less Confusing**: Clear what each method does

---

## Part 2: Operation Categorization - When to Poll vs Update Immediately

Not all operations need the same approach. This section categorizes operations based on their characteristics.

### Design Principle

**The library should handle all state synchronization internally.** Users should not need to manually wait, refresh, or poll after operations.

### Question: Which Operations Need Confirmation Polling?

Not all operations need confirmation polling. We categorize operations based on:
1. **Does the operation change observable state?**
2. **Is the state change immediate or delayed?**
3. **Is confirmation needed for correctness?**

### Category 1: Group Operations (✅ Implemented)

**Operations**: `create_group()`, `join_group()`, `leave_group()`, `disband()`

**Why Trust API Pattern?**
- State change is handled atomically by device
- State change affects **multiple players** (master + slaves)
- State change is **observable** (role, group membership)
- **Trust API return** - device confirms operation succeeded

**Implementation**: Use Core Pattern - no polling, immediate state update + **automatic group-wide notifications**

**Notification Strategy**: 
- ✅ Library automatically calls `on_state_changed()` callback on **ALL affected players**
- ✅ Includes all members of the new group (master + all slaves)
- ✅ Includes all members of the old group if player switched groups
- ✅ Integrations receive immediate notifications for all coordinators
- ❌ No manual `refresh()` or coordinator update calls needed

**Status**: ✅ Implemented in current codebase

### Category 2: Playback Control (✅ Use Core Pattern)

**Operations**: `play()`, `pause()`, `stop()`, `next()`, `previous()`, `seek()`

**Why Trust API Pattern?**
- State change is **immediate** (UPnP events arrive quickly)
- State change is **observable** (play_state, position)
- API return confirms command accepted

**Recommendation**: 
- **Use Core Pattern** - trust API, update immediately
- **Rely on UPnP events** for real-time state updates
- **Fallback**: Adaptive polling handles state sync if UPnP unavailable

**Exception**: `seek()` updates position immediately, UPnP/polling handles verification

### Category 3: Volume/Mute (✅ Use Core Pattern)

**Operations**: `set_volume()`, `set_mute()`

**Why Trust API Pattern?**
- State change is **immediate** (UPnP events arrive quickly)
- State change is **observable** (volume, muted)
- API return confirms command accepted

**Recommendation**:
- **Use Core Pattern** - trust API, update immediately
- **Rely on UPnP events** for real-time state updates
- **Fallback**: Adaptive polling handles state sync if UPnP unavailable

### Category 4: Source Selection (✅ Use Core Pattern)

**Operations**: `set_source()`, `play_url()`

**Why Trust API Pattern?**
- Device accepts command immediately
- State change is **observable** (source, play_state, metadata)
- API return confirms operation accepted

**Recommendation**:
- **Use Core Pattern** - trust API, update immediately
- Adaptive polling will detect source/metadata changes
- UPnP events provide real-time updates

### Category 5: EQ Operations (✅ Use Core Pattern)

**Operations**: `set_eq()`, `set_eq_preset()`

**Why Trust API Pattern?**
- Device accepts command immediately
- State change is **observable** (eq_preset, eq settings)
- API return confirms operation accepted

**Recommendation**:
- **Use Core Pattern** - trust API, update immediately
- Adaptive polling handles state verification

### Category 6: Preset Operations (✅ Use Core Pattern)

**Operations**: `save_preset()`, `load_preset()`

**Why Trust API Pattern?**
- Device accepts command immediately
- State change is **observable** (preset loaded, source changed)
- API return confirms operation accepted

**Recommendation**:
- **Use Core Pattern** - trust API, update immediately
- Adaptive polling handles state updates

### Category 7: Read Operations (❌ Don't Use Pattern)

**Operations**: `get_status()`, `get_device_info()`, `refresh()`

**Why Not Use Pattern?**
- These are **read operations** - no state change
- No state update needed
- No callback needed

**Recommendation**:
- **Don't use Core Pattern** - these are queries, not commands
- Return data directly from API

---

## Part 3: Implementation Summary

### Universal Pattern for All Operations

```python
async def operation(self, params):
    """Perform operation."""
    # 1. Handle preconditions (if needed)
    if needs_preparation():
        await self.prepare_state()
    
    # 2. Call API (raises WiiMError on failure)
    await self.client.api_call(params)
    
    # 3. Update library state immediately
    self._some_state = new_value
    
    # 4. Call callback
    if self._on_state_changed:
        self._on_state_changed()
```

### Operations Using Core Pattern

All state-changing operations should use this pattern:
- ✅ Group operations (join, leave, create, disband)
- ✅ Playback control (play, pause, stop, next, previous, seek)
- ✅ Volume/mute (set_volume, set_mute)
- ✅ Source selection (set_source, play_url)
- ✅ EQ operations (set_eq, set_eq_preset)
- ✅ Preset operations (save_preset, load_preset)
- ✅ Everything else that changes state

### State Verification Strategy

Instead of operation-specific polling, rely on:
1. **UPnP Events**: Real-time state updates when available
2. **Adaptive Polling**: Framework-level periodic refresh based on activity
3. **State Synchronizer**: Merges HTTP + UPnP state intelligently

This approach:
- ✅ Keeps operations simple and fast
- ✅ Provides real-time updates via UPnP
- ✅ Has fallback via adaptive polling
- ✅ Maintains single source of truth in StateSynchronizer

---

## Benefits

1. **Consistent API**: All operations handle synchronization internally
2. **Simple**: Users just call the method - no manual refresh/wait needed
3. **Fast**: Immediate state updates, no artificial delays
4. **Reliable**: Trust the API, not timing-based logic
5. **Robust**: UPnP + adaptive polling provides verification without per-operation complexity

---

## Deprecated Patterns

### ❌ Don't wait after operations:
```python
await player.join_group(master)
await asyncio.sleep(2.0)  # NOT NEEDED
```

### ❌ Don't refresh to confirm:
```python
await player.join_group(master)
await player.refresh()  # NOT NEEDED for confirmation
```

### ❌ Don't manually notify:
```python
await player.join_group(master)
coordinator.async_update_listeners()  # Library calls callback automatically
```

---

## Conclusion

**The library should trust the API and update state immediately.** This makes the library:
- ✅ Easier to use
- ✅ More reliable
- ✅ Faster
- ✅ Simpler to maintain

Users just call operations and trust that:
- The operation completed successfully (or raised exception)
- State is updated immediately
- Callbacks notify frameworks automatically
- UPnP + adaptive polling keep state synchronized

This is the **right design** for a production library.

