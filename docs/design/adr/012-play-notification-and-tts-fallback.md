# ADR 012: Play Notification (TTS) — Prompt Path, `play_url` Fallback, and `force_interrupt`

## Status
Accepted - 2026-04-20

## Context
**`playPromptUrl`** firmware behavior is **source- and firmware-dependent** (duck/resume, silence, or success without audible output). Documentation previously **overclaimed** universal resume behavior. Integrations need predictable ways to get **audible** TTS and to understand **what changed** (method used, whether playback was likely interrupted).

## Decision

### 1. Library responsibilities
- **`play_notification(url, …)`** chooses **`playPromptUrl`** only for **known-good** native prompt sources; for others it **falls back** to **`play_url`** so the device performs a normal HTTP GET of the audio URL (audible TTS in more cases).
- **`force_interrupt=True`** (optional): always use the **`play_url`** path so the notification is **guaranteed** to use the interrupting playback path when the prompt path is unreliable.
- Return a **structured result** (e.g. **`NotificationPlaybackResult`**) with fields such as **`method_used`**, **`source_before`**, **`likely_interrupted`**, and optional **`reason`** so integrations can log and branch without parsing exceptions.

### 2. Integration responsibilities
- Callers pass a **URL the device can HTTP GET**; resolving **`media_content_id`** / HA TTS proxy URLs is the **integration’s** job before calling the library (see **`docs/integration/HA_INTEGRATION.md`**).

### 3. Documentation honesty
- Do **not** promise automatic resume after TTS unless verified for that source/device; document **firmware-dependent** prompt behavior and point to **`force_interrupt`** where “always hear it” matters.

## Consequences
- New sources may need explicit classification for **prompt vs url** fallback as they are validated on hardware.
- Changing fallback policy is a **user-visible** contract change—update ADR, changelog, and integration guides together.
