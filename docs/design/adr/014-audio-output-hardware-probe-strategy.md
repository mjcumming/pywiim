# ADR 014: Audio Output Hardware — Probe Order and Field Semantics

## Status
Accepted - 2026-04-20

## Context
WiiM firmware and documentation evolved: **`getAudioOutputStatus`** may return **`unknown command`** on some models while **`getNewAudioOutputHardwareMode`** works. **`audiocast`** (and related fields) in **`getStatusEx`** are **not** the same semantics as fields in the **audio output status** JSON—conflating them caused wrong UI and wrong mode sends (e.g. USB Out mode numbers on Ultra).

## Decision

### 1. Probe order and fallbacks
- **Prefer** the modern / broadly working hardware-mode read (**`getNewAudioOutputHardwareMode`**) **first** when probing or refreshing output mode, with **fallback** to legacy **`getAudioOutputStatus`** (and profile-specific behavior) as implemented in **`API_DESIGN_PATTERNS`** and code.
- **False negatives** (marking `supports_audio_output` false because one probe failed) are unacceptable when another probe would succeed—capability and refresh logic should **retry / alternate** per documented patterns.

### 2. Model-specific output lists
- **`available_output_modes`** (and related) must reflect **hardware reality** (e.g. **no HDMI Out** on Ultra if HDMI is input-only; **USB Out** mode numbers from **device testing**, not stale public docs alone).
- When `device_capabilities.py` sets **`outputs`** for a model, that list is authoritative (WiiM Sound / Sound Lite: **Speaker Out** only). Models with `outputs is None` keep the streamer ladder until migrated.
- **Mode integers are overloaded.** Do not treat the static `AUDIO_OUTPUT_MODE_MAP` as model-agnostic: **mode 4** is Bluetooth vs Headphone on Ultra; **mode 7** is HDMI Out on Amp Ultra vs Speaker Out on Sound Lite (Bluetooth Out is `source=1` on the same hardware). `Player.audio_output_mode` applies the catalog.

### 3. Field semantics
- Treat **`getStatusEx`** output-related fields and **dedicated audio output** endpoint JSON as **different schemas**—do not assume key names imply identical meaning across endpoints.

## Consequences
- New devices or firmware may require **probe order** or **capability** tweaks; changes belong with **regression tests** and **curl** documentation updates (**`docs/testing/CURL_HTTPAPI.md`**).
- Integrations should use **player-level** output APIs that respect the probe strategy, not hard-coded legacy endpoints.
