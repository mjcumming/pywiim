# ADR 007: Media Position and Duration — Raw Device Values, No Client Estimation

## Status
Accepted - 2026-04-20

## Context
Client-side **position estimation** (timers, extrapolation, `media_position_updated_at` inside the library) fought Home Assistant’s own UI clock and caused **jitter** and inconsistent behavior across integrations. Other ecosystem players (e.g. Sonos-style integrations) expose **raw** position from the device and let the integration track **when** the value was read.

## Decision
- **`pywiim` returns raw position and duration** from the device (and parser normalizations documented elsewhere)—**no** library-side playback clock or estimation.
- **Removed** from the library’s contract: internal position timers, estimation logic, and a library-owned **`media_position_updated_at`**.
- **Integrations** (e.g. Home Assistant) own: **`media_position_updated_at`** (or equivalent), smooth UI advancement, and any extrapolation policy.

## Consequences
- **Clear separation of concerns**: device truth vs. presentation timestamp.
- **Breaking change** for integrations that relied on the library to estimate position (documented at release **2.1.0** in the changelog); those integrations **must** supply timestamps themselves.
- Parser fixes for firmware quirks (e.g. position vs duration, live streams) remain in the library; they do **not** reintroduce estimation.
