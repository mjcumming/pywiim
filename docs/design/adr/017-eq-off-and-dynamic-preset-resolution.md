# ADR 017: EQ Presets — “Off” Semantics and Device-Native Preset Names

## Status
Accepted - 2026-04-20

## Context
Users expect **EQ fully bypassed** as a first-class sound mode. Firmware can expose **custom preset names** and new labels (e.g. “Vocal Booster”) that are not in a static library map. Hardcoding only legacy names caused **`set_eq_preset`** to fail on newer firmware while the device list showed valid options.

## Decision

### 1. “Off” as explicit preset
- **`eq_presets`** includes **`"Off"`** as the **disabled / bypass** option when the device supports turning EQ off.
- **`eq_preset`** returns **`"Off"`** when EQ is bypassed, not the last active preset name.
- **`set_eq_preset("Off")`** disables EQ (bypass). Selecting a **non-Off** preset when EQ is off **enables** EQ then applies the preset (order as implemented in player/client).

### 2. Dynamic name resolution
- **`set_eq_preset(name)`** resolves the requested name against the device’s **current `eq_presets` list** (case/fuzzy rules as implemented) **before** falling back to built-in alias maps, so **user-defined** and **new firmware** labels work.

### 3. Refresh
- EQ **enabled** state and preset list are refreshed on the same **periodic** cadence as other “configuration tier” features (e.g. ~60s with full refresh), so “Off” and custom names stay accurate.

## Consequences
- Integrations exposing **`sound_mode`** / EQ must treat **`"Off"`** as distinct from named curves.
- Removing or renaming **`"Off"`** in the public API is a **breaking** change for HA and scripts.
- Built-in preset maps remain **fallback only**, not the sole source of truth for **`set_eq_preset`**.
