# ADR 009: Multiroom Group Role — Authoritative `group` Field and `get_device_group_info`

## Status
Accepted - 2026-04-20

## Context
Firmware can leave **`mode`** (e.g. follower `99`) **stuck** after leaving a group while **`group`** is cleared correctly. Using **`mode` alone** for slave detection caused devices to appear **stuck as slave**, rejecting playback. Conversely, skipping **`get_device_group_info()`** to save API calls caused **masters with slaves** to be misclassified as solo.

## Decision

### 1. Slave vs solo/master (fast path)
- **Authoritative for “in a group as slave”**: HTTP **`group`** (and related master pointers), per **`docs/design/API_DESIGN_PATTERNS.md`** — Group Role Logic.
- **Do not** rely on **`mode == 99`** alone as proof of slave; it may be stale.

### 2. Master and slave list
- Use **`get_device_group_info()`** (getStatus → slave hints → getSlaveList / device info as documented) when the design guide says it is required—especially when **slave indicators may be present**, a **group object** exists, or **device info** is available from a full refresh so expensive calls are justified.

### 3. Stale `multiroom` source
- When role detection says the device is **not** a slave but **source** still reads as multiroom, **clear** the inconsistent source so UI and automations do not show a false multiroom state.

## Consequences
- Optimizations that skip **`get_device_group_info()`** must preserve **correct master detection**; regressions here break grouped playback UIs.
- Future firmware quirks should be handled by **extending** the documented flow, not reintroducing **`mode`**-only shortcuts without analysis.
