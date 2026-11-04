# ADR 017: EQ Presets — “Off” Semantics and Device-Native Preset Names

## Status
Accepted - 2026-04-20. The 2026-11-03 amendments are tracked in [PR #37](https://github.com/mjcumming/pywiim/pull/37).

## Context
Users expect **EQ fully bypassed** as a first-class sound mode. Firmware can expose **custom preset names** and new labels (e.g. “Vocal Booster”) that are not in a static library map. Hardcoding only legacy names caused **`set_eq_preset`** to fail on newer firmware while the device list showed valid options.

The Audio Pro A10 MkII reports an EQ preset for each input and returns `EQGetList` as a JSON array. Legacy response validation discarded that valid array, so the integration showed only Off even though the device reported 24 presets ([wiim #187](https://github.com/mjcumming/wiim/issues/187)). A WiiM Pro Plus can report unsaved graphic bands with EQ on and an empty name ([wiim #302](https://github.com/mjcumming/wiim/issues/302)); a saved PEQ preset can also be active while graphic EQ is inactive ([wiim #301](https://github.com/mjcumming/wiim/issues/301)).

## Decision

### 1. “Off” as explicit preset
- **`eq_presets`** includes **`"Off"`** as the **disabled / bypass** option when the device supports turning EQ off.
- **`eq_preset`** returns **`"Off"`** when graphic EQ is inactive, including when PEQ is active. Use `peq_enabled` to distinguish PEQ from full bypass; unknown remains `None`.
- **`set_eq_preset("Off")`** disables EQ (bypass). Selecting a **non-Off** preset when EQ is off **enables** EQ then applies the preset (order as implemented in player/client).

### 2. Dynamic name resolution
- **`set_eq_preset(name)`** accepts both built-in aliases and names in the device's current `eq_presets` list, so user-defined and new firmware labels can be loaded. Built-in aliases are checked first; an otherwise unmatched device name is sent using its device-reported label.
- Preserve a valid JSON array through endpoint discovery and legacy response validation. Obtain the available names from the device; do not replace a lost response with a hard-coded list.

### 3. Refresh
- The current preset **name** is `EQGetBand` `Name`. `getPlayerStatus` `eq` stays stale on current firmware (often `flat` / `0` after `EQLoad`) and must not replace a name already read from `EQGetBand`.
- EQ **enabled** state and that name refresh on the configuration-tier cadence (~60s), and again when `getPlayerStatus` `eq` changes to a new value. Saved preset lists use the separate 15-minute policy in [ADR 022](022-eq-preset-list-refresh.md).
- Invalidate the current EQ state and graphic preset list when the active input changes, then fetch the new input's data. Reject in-flight results for an old input. An empty `Name` with graphic EQ on means unsaved `Custom` bands, not a saved preset. Failed or malformed reads do not replace valid same-input state with Off.
- After a graphic preset or enable/disable command, or a PEQ preset or disable command, read back graphic and supported PEQ state. An acknowledgment alone does not establish the resulting state. Numeric playback-status EQ mappings are opt-in for verified legacy profiles.

### 4. Custom bands and PEQ profiles
- The LV2 band writer requires a valid response identifying the requested plugin and input, pins a current-input operation to the observed source, then checks every written parameter against device readback. Missing gains are not converted to zero. Graphic writes use `Eq10HP` stereo gains in dB; they do not depend on `supports_peq`, and unverified graphic L/R writes are rejected.
- The old comma-separated `set_eq_custom` command is replaced by the verified graphic writer. Its ten values are dB gains from -12 to +12, and a successful Player write refreshes both EQ states. A device without a confirmed Eq10HP response fails explicitly rather than falling back to an unproven legacy upload.
- PEQ custom profiles are created, edited and managed in pywiim. Replacing an existing custom name requires explicit `overwrite=True`; an existing factory name cannot be replaced. Save checks the list and active bands, reloads the stored profile, and compares its bands. If verification after reload fails, it attempts to restore the prior bands and reports a failed restoration. This sequence cannot be atomic. Rename and delete check the resulting list.

## Verification and limits

- Regression coverage includes the supplied A10 and Pro Plus responses, source changes, temporary failures, and repeated configuration polls. Device confirmation is specific to the model and firmware actually tested; the reported A10 and Pro Plus have not yet been tested with this change.
- On one WiiM Pro (`Linkplay.4.8.833748`), comma-separated `EQSetBand` returned `OK` without changing the readback. Source-scoped and current-input LV2 graphic writes, ten-band custom writes, and PEQ create/overwrite/load/rename/delete were checked against device responses; the original curves and preset list were restored. No A10, Pro Plus, Yamaha, other firmware, or other input was available for those write tests.
- Yamaha sound programs need their own verified sound-state protocol and capability evidence. Linkplay identification alone does not establish support for WiiM presets.

## Consequences
- Integrations exposing **`sound_mode`** / EQ must treat **`"Off"`** as distinct from named curves.
- Removing or renaming **`"Off"`** in the public API is a **breaking** change for HA and scripts.
- Built-in preset maps remain **fallback only**, not the sole source of truth for **`set_eq_preset`**.
