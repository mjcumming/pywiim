# ADR 008: Shuffle and Repeat (`loop_mode`) — Scheme and Source Context

## Status
Accepted - 2026-04-20
Updated - 2026-06-13

## Context
WiiM and Arylic devices use **different numeric schemes** for the same HTTP `loop_mode` field. A single global or bitfield interpretation produced **invalid** interpretations (e.g. treating valid WiiM `loop_mode=3` as an error) and **broke shuffle/repeat** in integrations.

Later field reports showed that device scheme alone is also not enough context. Some transports can report source-specific extension values through the same field. For example, Spotify on a WiiM-scheme device can report `loop_mode=5` for single-track repeat, while Arylic-scheme devices use `5` for shuffle plus repeat-one.

## Decision
- **Scheme-specific mapping** is required for both **parsing** device status and **sending** shuffle/repeat commands. The scheme comes from **`DeviceProfile.loop_mode_scheme`** (see **`get_device_profile`**) and is mirrored in **`client.capabilities["loop_mode_scheme"]`** — not from **`vendor`** alone, because some **WiiM** firmware uses the LinkPlay/Arylic numbering while **`vendor`** remains **`wiim`** ([pywiim#17](https://github.com/mjcumming/pywiim/issues/17)).
- Decoding raw device status must use **source context** in addition to the scheme. Use **`decode_loop_mode`** / **`decode_loop_mode_for_player`** for reads so known source-specific values can be handled without weakening the strict scheme tables.
- Encoding outgoing shuffle/repeat commands remains scheme-based. Use **`resolve_loop_mode_mapping`** / **`resolve_loop_mode_mapping_for_player`** (or **`get_loop_mode_mapping_for_scheme`**) when choosing which integer to send.
- Implementation lives in **`pywiim/api/loop_mode.py`**. **`LoopModeMapping`** represents documented scheme tables only; contextual behavior belongs in the decoder layer. **`get_loop_mode_mapping(vendor)`** remains as a vendor-only fallback when no scheme is set.
- **Do not** “unify” vendors by collapsing to one scheme without an explicit ADR and migration plan.

## Consequences
- Adding a new vendor or firmware family may require a **new row/table** in the mapping layer, not a tweak to a single shared enum.
- Adding a source-specific raw value should be modeled as a named decoder behavior, not as an exception inside a scheme table.
- Unknown-value warnings should be rate-limited by raw value, scheme, and source so repeated property reads do not multiply one device state into many log lines.
- Source-based control availability (e.g. AirPlay cannot be locally controlled) remains separate from raw value decoding, but the source still participates in interpreting reported state.
