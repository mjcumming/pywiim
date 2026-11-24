# ADR 025: WiiM Voice Remote — Capability, State Sources, Volume Step, and Safety

## Status
Accepted - 2026-11-23

## Context

A WiiM speaker can be paired with a WiiM Voice Remote over Bluetooth LE. Home Assistant users want the remote's battery, connection, signal strength, and its "Volume Adjustment Step" setting (see [mjcumming/wiim#320](https://github.com/mjcumming/wiim/issues/320)). The data was captured from a WiiM Pro Plus (firmware `Linkplay.4.8.833841`); other models and firmware are **not tested**.

What the device reports:

- `getStatusEx` has `BleRemoteControl`, `BleRemoteConnected`, and, **only while the remote is connected**, `BleRemoteBatterylevel`, `BleRemoteRSSI`, `BleRemoteVersion` and more. `BleRemoteControl` is `"1"` in every state, so it means "the speaker supports a remote", not "a remote is paired".
- `getblehidstatus` returns `status` (`connected` / `notconnect` / `scanning`), `name`, `mac`, `ver`, `rssi`, `battery`. When no remote is paired, `name` is `""` and `mac` is `00:00:00:00:00:00`. Its `battery` lags after a battery change (0 right after, 100 on a later read) while `getStatusEx` updates immediately.
- `get_remote_volume_step` / `set_remote_volume_step:N` read and write the setting; N = 1–5 were tested. Other values are untested.

The same command family also contains commands that pair, remove, or update the remote.

## Decision

### 1. Capability: `supports_ble_remote` (read-only probe)
- Detected in `WiiMCapabilities.detect_capabilities()` ([ADR 016](016-connect-time-read-only-capability-probes.md), [ADR 018](018-capabilities-dict-source-of-truth.md)).
- Gate: `getStatusEx` `BleRemoteControl == "1"` (already read). Without it the value is `False` and **no remote request is sent**, so other devices never see `getblehidstatus`.
- With the gate open, one read of `getblehidstatus` must return a valid status object: `True`. `unknown command` or an unexpected body: `False`. A transient error: `None` (inconclusive); the next successful refresh sets `True`.
- `player.supports_ble_remote` means "supports a remote", not "a remote is paired". Pairing is `player.ble_remote.paired`.

### 2. State source and cadence
- `BleRemoteState(paired, connected, name, mac, firmware, battery, rssi)` is built from `getblehidstatus` only. `getStatusEx` is not polled for the remote ([ADR 024](024-getstatusex-off-regular-poll.md)).
- `getblehidstatus` is read about every 60 seconds while a remote is paired, and about every 5 minutes when the last read said none is paired. A full refresh reads it immediately.
- Connected means `status` is `connected`. Battery and RSSI are `None` otherwise. Battery can lag after a battery change; that lag is accepted.
- A failed or unreadable read keeps the previous state.
- The remote volume step is cached and re-read with that same read, only while a remote is paired. An unpaired read clears the cached step.

### 3. Volume step setter verifies by reading back
`set_remote_volume_step(step)` accepts only integers 1–5 (`ValueError` otherwise, nothing sent), writes, then reads the value back and raises `WiiMError` when the read-back is missing or differs. This is a deliberate exception to [ADR 002](002-trust-api-after-success.md): the device answers `{"status":"OK"}` to a write that it may not apply, behaviour outside 1–5 is untested, and the extra GET only happens on a user-initiated write, not during polling. The Player cache changes only after the read-back confirms.

`REMOTE_VOLUME_STEPS` (`{1: "Fine Adjustment", …, 5: "Quick Adjustment"}`, the app's labels, default 1) is exported so integrations can label the values.

### 4. Safety: pairing, removal and update commands are never sent
- Not modelled, not sent: `blehidremoveall`, `startblescan`, `blehidpair`, `getMvRemoteUpdateStart`, `getMvRemoteUpdateStartCheck`. They change pairing or firmware and are not needed for read-only state or the volume step.
- A unit test fails if the pairing/removal command names appear anywhere in `pywiim/`, and if the two update command names appear outside the older speaker-firmware API (`api/firmware.py`, which predates this ADR and is unchanged).
- Device test scripts must block these commands in code, not only in a comment.

### 5. Privacy
- The BLE MAC is excluded from `repr()` of `BleRemoteIdentity` and `BleRemoteState`, is never logged, and `diagnostics_dict()` / `Player` diagnostics report it masked (`XX:XX:XX:XX:XX:XX`). Raw `getblehidstatus` bodies are not logged or added to the diagnostics CLI dump.

## Consequences
- Integrations gate remote entities on `player.supports_ble_remote` and `player.ble_remote.paired`, and use `connected`/`battery`/`rssi` for availability.
- A speaker with a paired remote costs one `getblehidstatus` per minute. A speaker that can have a remote, and does not, costs that call every 5 minutes. `getStatusEx` is not added to the timer.
- Behaviour on other models, after the remote is forgotten and re-paired, and for volume step values outside 1–5 is **not tested**.
- Pairing and firmware update of the remote stay in the WiiM Home app.
