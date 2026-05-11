# ADR 008: Shuffle and Repeat (`loop_mode`) — Vendor-Specific Numeric Maps

## Status
Accepted - 2026-04-20

## Context
WiiM and Arylic devices use **different numeric schemes** for the same HTTP `loop_mode` field. A single global or bitfield interpretation produced **invalid** interpretations (e.g. treating valid WiiM `loop_mode=3` as an error) and **broke shuffle/repeat** in integrations.

## Decision
- **Scheme-specific mapping** is required for both **parsing** device status and **sending** shuffle/repeat commands. The scheme comes from **`DeviceProfile.loop_mode_scheme`** (see **`get_device_profile`**) and is mirrored in **`client.capabilities["loop_mode_scheme"]`** — not from **`vendor`** alone, because some **WiiM** firmware uses the LinkPlay/Arylic numbering while **`vendor`** remains **`wiim`** ([pywiim#17](https://github.com/mjcumming/pywiim/issues/17)).
- Implementation lives in **`pywiim/api/loop_mode.py`**: use **`resolve_loop_mode_mapping`** / **`resolve_loop_mode_mapping_for_player`** (or **`get_loop_mode_mapping_for_scheme`**) at call sites; **`get_loop_mode_mapping(vendor)`** remains as a vendor-only fallback when no scheme is set.
- **Do not** “unify” vendors by collapsing to one scheme without an explicit ADR and migration plan.

## Consequences
- Adding a new vendor or firmware family may require a **new row/table** in the mapping layer, not a tweak to a single shared enum.
- Blacklists / source-based restrictions (e.g. AirPlay) remain **orthogonal** to numeric mapping—first interpret values correctly, then apply product rules.
