# ADR 018: Client Capabilities Dict — Single Source of Truth for Optional Features

## Status

Accepted - 2026-04-20

## Context

pywiim learns what a device can do in two related ways:

1. **Runtime capability detection** — `WiiMClient._detect_capabilities()` / `WiiMClient.refresh_capabilities()` merges static hints with **probed** results into the **`WiiMClient.capabilities`** mapping (`supports_eq`, `supports_subwoofer`, `supports_peq`, `supports_presets`, `supports_trigger_out`, etc.). [ADR 003](003-capability-probing-before-endpoints.md) requires probing before relying on optional endpoints; [ADR 016](016-connect-time-read-only-capability-probes.md) defines connect-time probe behavior.

2. **Other registries** — e.g. `device_capabilities.py` and `source_catalog` constrain **which physical inputs / source ids exist** for a model. That is layout and selection policy, not a replacement for per-device, per-firmware **HTTP endpoint** support.

Without a clear rule, integrations and docs drift: entities are created from **model name** or **“WiiM Pro usually has X”** assumptions, duplicate probing happens in app code, or UI exposes features that the merged **`capabilities`** map has already marked unsupported. That produces errors, support load, and contradictions with library behavior.

## Decision

1. **Authoritative object** — For “can this **player / client** use this **optional HTTP API** feature right now?”, the **only** source of truth is **`player.client.capabilities`** (same mapping as `WiiMClient.capabilities`): keys such as `supports_*`, tri-state values where documented (`True` / `False` / `None`), plus related keys (`presets_full_data`, `status_endpoint`, etc.) produced by detection and intentional corrective updates (e.g. runtime downgrade when an endpoint proves unsupported).

2. **Player facade** — When `Player` exposes a boolean (or documented) capability for integrations (**`player.supports_eq`**, **`player.supports_subwoofer`**, etc.), that property **must** reflect the merged **`client.capabilities`** (or a narrow exception documented in the same ADR family, e.g. UPnP availability tied to `upnp_client` construction). Integrations **should prefer** these `Player` properties when they exist; otherwise **`player.client.capabilities.get("supports_…")`** with the same semantics.

3. **Integrations (including Home Assistant)** — **Do not** create entities, platforms, or services for optional HTTP features based solely on **device model**, **friendly name**, or **static lists** unless the feature is **also** gated on the **`capabilities`** map (or the matching `Player` property). If the map says unsupported, the feature is off; if the map is updated after a corrective call, UI must follow the updated dict (call `refresh_capabilities()` after firmware OTA when you need a full re-probe).

4. **Library code** — New optional HTTP features **add or reuse a `supports_*` (or documented) key** populated in **`WiiMCapabilities.detect_capabilities()`** (or the agreed detection path), with unit tests. Avoid setting those flags from deep mixin code except for **documented corrective cache updates** that still write into the **same** `client._capabilities` dict (same object the app reads).

5. **Documentation** — Architecture, API, and Home Assistant integration docs **must not** tell readers to enable optional HTTP features using rules that bypass **`capabilities`** (e.g. “if model contains Ultra then show subwoofer”). Examples may show model for **illustration** only when paired with a **`capabilities`** check in the same snippet.

### Relationship to other layers

- **`device_capabilities.py` / source catalog** — Use for **which sources exist and which are selectable**; do not use as the sole gate for unrelated HTTP endpoints (PEQ, subwoofer, trigger, etc.).
- **Current-source playback affordances** (`supports_next_track`, shuffle, etc.) — Follow existing docs; they are **playback-state** driven. This ADR applies to **device-level optional HTTP** features represented in **`client.capabilities`**.

## Consequences

- **Predictable integrations** — HA and other apps align with the library; fewer “works on my model” forks.
- **One place to refresh** — After OTA or rare mis-detection, `refresh_capabilities()` and the same dict drive UI.
- **Discipline** — New features pay the cost of a clear `supports_*` key and tests up front.
- **Docs maintenance** — Examples and checklists must stay in sync with **`capabilities`** keys (see `docs/integration/HA_CAPABILITIES.md`).
