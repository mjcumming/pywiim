# ADR 024: getStatusEx Stays Off the Regular Poll

## Status

Accepted - 2026-11-24

## Context

`getStatusEx` is the device document: name, model, firmware, network, inputs, group membership, and a large set of other keys. `getPlayerStatusEx` is the playback document: play state, volume, track, and position.

The regular refresh loop polls playback. Device info is loaded on the first refresh, when `refresh(full=True)` runs, and when a caller asks for it. That split has been the player behavior since the tiered polling work in 2.1.10, and the state manager states it directly: device info is not needed every poll. The polling helper `should_fetch_device_info()` still describes a 60-second device-info fetch. `Player.refresh()` does not use that helper.

The size is why it left the loop. On three WiiM speakers, `getStatusEx` returned about 2.8 KB and 112 keys in about 120 ms. `getPlayerStatusEx` returned about 270 bytes and 18 keys in about 70 ms. The device document is about ten times larger and slower by about 50 ms. It is not a multi-second stall. It is the wrong call to put back on a timer to sample one or two fields that rarely change.

Some devices use `getStatusEx` as their playback status because they have no `getPlayerStatusEx`. That existing fallback is a playback poll, not a second device-info poll.

## Decision

`Player.refresh()` does not call `getStatusEx` on the regular loop. The playback poll is `getPlayerStatusEx`, or the capability-selected status endpoint when a device has no `getPlayerStatusEx`.

`getStatusEx` runs at startup, on an explicit full refresh, and when a caller needs a field that exists only in that document. A new feature does not add it to a timer to read a handful of keys. If a smaller command already returns those keys, the feature uses the smaller command.

`should_fetch_device_info()` is not permission to poll `getStatusEx` every 60 seconds. Wiring it into `refresh()` would reverse this decision.

## Consequences

- Playback polling stays on the small status command. Device identity stays cached until startup or a full refresh.
- A feature that needs one field from `getStatusEx` has to show that no smaller command provides it before that command goes on a timer.
- Devices whose only playback endpoint is `getStatusEx` keep using it for playback. They do not gain a second copy of the same call for device info.
- The 60-second device-info helper remains unused by `refresh()`. Removing or renaming it is a cleanup, not a change in behavior.
