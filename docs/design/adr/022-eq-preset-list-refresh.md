# ADR 022: Refresh EQ preset lists separately from active state

## Status

Accepted - 2026-11-03

## Context

Saved EQ names change infrequently, but changes made in WiiM Home must eventually appear in integrations. We have no verified device notification or revision for these lists. The previous graphic list policy fetched on track changes and roughly every minute, while parametric names were read only once per player session. A failed first PEQ list read could therefore leave names unavailable until the integration was reloaded.

## Decision

- While the application polls a supported player, read the saved graphic and parametric lists at startup and approximately every 15 minutes. A full player refresh also reads both lists. Track changes alone do not cause list reads.
- Graphic EQ is input-specific. Invalidate its list on input changes and fetch the new input's list; reject an in-flight result for an old input. The cached parametric list remains separate from active per-input state.
- Keep the last valid same-input list if a later read fails. An initial failed list read is retried after about 60 seconds; a valid empty list is still a successful read.
- Active EQ state retains its existing shorter refresh and command readback behavior. Integrations may reload a player session for earlier list discovery without adding a refresh button.

This amends the preset-list cadence in [ADR 017](017-eq-off-and-dynamic-preset-resolution.md); its state and command guarantees remain in force.

## Consequences

- External changes to unselected saved names can take up to roughly 15 minutes to appear while normal polling succeeds. Offline devices, failed reads, and slow polling can delay this longer.
- Routine list traffic is lower than the former graphic polling cadence. The first retry, a full refresh, and input changes can add requests.
- The library owns scheduling and cache updates; consumers display the refreshed options through their existing player-state notifications.
