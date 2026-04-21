# ADR 006: Subwoofer Control — WiiM-Only, Probing, Cache, and Wire Semantics

## Status
Accepted - 2026-04-20

## Context
Subwoofer configuration uses **undocumented** HTTP commands (`getSubLPF`, `setSubLPF:*`) discovered via reverse engineering. Devices differ; Arylic/LinkPlay generics do not implement these commands. Integrations need a stable rule for **when** the feature exists, **how** status is refreshed without spamming the device, and **how** raw device keys map to typed APIs.

## Decision

Subwoofer support is a **`supports_*` entry in `client.capabilities`**; applications gate on that dict (or `player.supports_subwoofer`), not on model name — see **[ADR 018](018-capabilities-dict-source-of-truth.md)**.

### 1. Vendor gate
- **`supports_subwoofer`** is determined only for **WiiM-class devices** (`is_wiim_device` in capabilities). Non-WiiM → **`False`** without calling the subwoofer endpoint.

### 2. Connect-time probe
- **`_probe_supports_subwoofer`** (in `capabilities.py`) may run up to **3** attempts with short backoff on legacy-style transient errors.
- **`True`**: response matches “real” subwoofer status (shape heuristic: known keys or status + level/phase).
- **`False`**: definitive unsupported errors (e.g. `unknown command`, 404) **or** response shape clearly not subwoofer status.
- **`None`**: still inconclusive after retries → log warning; refresh may later promote to **`True`** if a valid dict appears.

### 3. Player cache and API surface
- Internal cache is a **raw dict** keyed as the device returns (`_subwoofer_status`). Properties (`subwoofer_enabled`, `subwoofer_crossover`, etc.) read from that cache.
- **`Player.get_subwoofer_status()`** returns **`SubwooferStatus`** (typed view built from the raw dict).
- After successful **`set_subwoofer_*`**, the player **updates the raw cache** from known arguments—no extra poll to confirm (consistent with [ADR 002](002-trust-api-after-success.md)).

### 4. Refresh cadence
- While **`supports_subwoofer` is not `False`**, `statemgr` may fetch raw status on **full refresh** or on the **configuration-tier interval** (~60s) via `PollingStrategy.should_fetch_subwoofer`.
- If capability was **`None`** and refresh obtains a **valid** status dict, set **`supports_subwoofer`** to **`True`**.

### 5. Inverted filter fields on the wire
- Device fields **`main_filter`** / **`sub_filter`** use **inverted** semantics relative to “bass to mains” / “sub LPF enabled”. **`SubwooferStatus.from_dict`** and setters document and abstract this; callers use the dataclass / player setters, not raw wire meaning.

## Consequences
- Integrations must check **`player.supports_subwoofer`** (strict **`True`**) before exposing controls.
- Documentation should prefer **`get_subwoofer_status()`** / **`SubwooferStatus`** for typed access; the **`subwoofer_status`** property remains the raw cache for backward compatibility.
- Changes to probe heuristics or cadence affect HA and other consumers—treat as a **minor version** discussion if behavior visible to users changes.
