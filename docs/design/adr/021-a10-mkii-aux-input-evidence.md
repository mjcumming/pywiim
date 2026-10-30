# ADR 021: A10 MkII AUX selection requires advertised command evidence

## Status
Proposed - 2026-10-30

## Context
[wiim#187](https://github.com/mjcumming/wiim/issues/187#issuecomment-6270088302) reports four AudioPro_A10MKII_WiiM speakers on Linkplay.5.2.825329: `switchmode:auxIn` selects AUX (mode 60), while `switchmode:line-in` returns OK without switching. Their `getAudioInputCapbility` lists wifi, auxIn, and bluetooth. Earlier A10 firmware tests led to a conservative analog-input block.

## Decision
- Probe the read-only capability endpoint on explicit Audio Pro A10 MkII models, including those classified as non-WiiM. Other OEM devices retain their existing probe policy.
- Only an exact advertised `auxIn` enables this correction. Missing, empty, unsupported, or failed queries retain existing behavior; a model or firmware version alone never enables it.
- Store the wire command in `source_command_overrides`, preserving case. Keep the existing `line_in` identity and Line In display name for mode 60; Aux In aliases select the same input.
- Use the verified `selectable_source_ids` list instead of heuristic input enumeration. Unlisted active sources remain readable and present in the catalog with `selectable: false`, but stay out of `available_sources` and are rejected by `set_source`.
- Keep post-command state verification: an OK reply alone does not establish successful switching.

## Consequences
The Home Assistant integration consumes the library's corrected list and command through its existing Player API. It requires a released pywiim dependency before integration merge/release. No EQ changes are included. Reporter validation after release is still required; automated tests reproduce the supplied device evidence without claiming new hardware testing.
