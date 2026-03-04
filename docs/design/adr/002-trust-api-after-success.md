# ADR 002: Trust the API After Success — No Polling to Confirm Operations

## Status
Accepted - 2025-12 (pattern established in design; formalized here)

## Context
State-changing operations (play, pause, join_group, set_volume, set_source, etc.) are sent to the device via the HTTP API. Historically, some code tried to "confirm" that an operation worked by waiting and polling (e.g. `await asyncio.sleep(2)` then `await player.refresh()` until state matched). This led to:

- Slower, more complex code
- Fragile timing-dependent behavior
- Redundant network traffic
- Confusion about when to use `refresh()` (for confirmation vs. for syncing external changes)

The device API is request/response: if the HTTP call succeeds, the device has accepted and executed the command. If it fails, the client raises an exception.

## Decision
We **trust the API**: if a state-changing HTTP call returns successfully, the operation succeeded. We do **not** wait or poll to "confirm" it.

### Rules
1. **On success**: Update library state immediately from the known outcome of the operation (e.g. after `join_slave` succeeds, update group membership locally).
2. **On failure**: The client raises; no state update.
3. **No post-operation confirmation polling**: Do not call `refresh()` or poll solely to verify that an operation worked. The API return is the verification.
4. **Callbacks**: Notify frameworks (e.g. Home Assistant) of state changes via callbacks so they can update their UI without an extra round-trip.
5. **`refresh()` is for other purposes**: Syncing comprehensive state, detecting external changes, or one-off scripts — not for confirming that a just-sent command worked.

### Scope
Applies to all state-changing operations: playback control, volume/mute, source selection, group operations, EQ, presets, etc. Read operations (`get_player_status`, `refresh()`) are unchanged.

## Consequences
- **Simpler, faster code**: No wait/poll logic after operations.
- **Clear contract**: Success = return; failure = exception.
- **State sync**: Frameworks rely on UPnP events and/or coordinator polling for ongoing sync; the library does not add per-command refresh.
- **Risk**: If the device sometimes reports success but does not apply the change (e.g. firmware bug), we would not detect it until the next normal refresh or UPnP event. We accept this trade-off for simplicity and speed; such cases are expected to be rare.

Full pattern and examples: [OPERATION_PATTERNS.md](../OPERATION_PATTERNS.md).
