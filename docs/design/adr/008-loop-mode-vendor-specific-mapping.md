# ADR 008: Shuffle and Repeat (`loop_mode`) — Vendor-Specific Numeric Maps

## Status
Accepted - 2026-04-20

## Context
WiiM and Arylic devices use **different numeric schemes** for the same HTTP `loop_mode` field. A single global or bitfield interpretation produced **invalid** interpretations (e.g. treating valid WiiM `loop_mode=3` as an error) and **broke shuffle/repeat** in integrations.

## Decision
- **Vendor-specific mapping** is required for both **parsing** device status and **sending** shuffle/repeat commands.
- Implementation lives in dedicated mapping logic (e.g. `pywiim/api/loop_mode.py` and call sites): use **`get_loop_mode_mapping(vendor)`** (or equivalent) so WiiM vs Arylic (and future vendors) do not share one numeric table.
- **Do not** “unify” vendors by collapsing to one scheme without an explicit ADR and migration plan.

## Consequences
- Adding a new vendor or firmware family may require a **new row/table** in the mapping layer, not a tweak to a single shared enum.
- Blacklists / source-based restrictions (e.g. AirPlay) remain **orthogonal** to numeric mapping—first interpret values correctly, then apply product rules.
