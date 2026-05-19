# ADR 019: 12V Trigger — Static Capability, Cache, Configuration-Tier Refresh

## Status
Accepted - 2026-05-19

## Context

WiiM Ultra, Pro, and Pro Plus expose 12V trigger control via `getTriggeroutStatus` / `setTriggeroutStatus:0|1`. The library added client/player APIs and `supports_trigger_out` (from known hardware models), but **`player.refresh()` did not poll trigger state** on the configuration tier. Integrations (e.g. Home Assistant) read cached `player.trigger_out_on` on coordinator updates, so changes made in the WiiM Home app were invisible until something called `get_trigger_out_status()` explicitly.

Subwoofer status already follows a documented pattern: static or probed `supports_*`, optimistic cache on set ([ADR 002](002-trust-api-after-success.md)), and periodic refresh via `PollingStrategy` + `statemgr` ([ADR 006](006-subwoofer-control-and-caching.md)). Trigger differs from subwoofer in that **capability is static** ([ADR 016](016-connect-time-read-only-capability-probes.md)) — no connect-time HTTP probe.

## Decision

### 1. Capability (unchanged)
- **`supports_trigger_out`** remains set from **`is_wiim_12v_trigger_model()`** at capability detection only — not from `getTriggeroutStatus` at connect ([ADR 016](016-connect-time-read-only-capability-probes.md), [ADR 018](018-capabilities-dict-source-of-truth.md)).
- Applications gate entities on **`player.supports_trigger_out`** / **`capabilities["supports_trigger_out"]`**, not model name alone.

### 2. Player cache and set semantics
- **`_trigger_out_on`**: `bool | None` (`None` = never read).
- **`get_trigger_out_status()`** updates the cache from the device.
- After successful **`set_trigger_out()`**, update cache from the known argument and fire **`on_state_changed`** — **no** post-set GET ([ADR 002](002-trust-api-after-success.md)).

### 3. Configuration-tier refresh
- Add **`PollingStrategy.should_fetch_trigger_out()`** with the same cadence as subwoofer/EQ: first fetch when `_last_trigger_out_check == 0`, then every **`CONFIGURATION_INTERVAL`** (~60s).
- In **`statemgr`** configuration-tier refresh: when **`supports_trigger_out`** is true, call **`player.get_trigger_out_status()`** on full refresh or when `should_fetch_trigger_out()` returns true.
- Skip when **`supports_trigger_out`** is false.

### 4. CLI / integrations
- **`wiim-monitor`** uses **`should_fetch_trigger_out()`**, not `should_fetch_audio_output()` for trigger.
- Home Assistant and other integrations continue to read **`player.trigger_out_on`** on coordinator updates; they do not poll the endpoint per listener wave.

### 5. Out of scope (for now)
- **`getTriggeroutStatusEx`** and “Trigger Once” app actions are not modeled until verified on hardware; may be a follow-up if Ultra semantics differ from `getTriggeroutStatus`.

## Consequences
- External changes (WiiM app, auto trigger on playback) appear in integrations within ~60s (or on full refresh), matching subwoofer/EQ behavior.
- No extra HTTP on every fast playback poll — only configuration tier.
- If firmware returns success but does not apply `setTriggeroutStatus`, state may be wrong until the next configuration-tier read ([ADR 002](002-trust-api-after-success.md) trade-off).
- Document refresh behavior in **API_DESIGN_PATTERNS** and **HA_INTEGRATION**.
