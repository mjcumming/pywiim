# Architecture Decision Records (ADRs)

ADRs capture **decisions we have committed to** so future changes don’t accidentally break them. They live alongside the rest of the design docs; the difference is that an ADR is a single, scoped decision with clear status and consequences.

## When to write an ADR

Write an ADR when the decision:

- Affects **user-facing behavior** or **API contracts** (e.g. naming, stability guarantees)
- Is something we want to **stick to** unless we explicitly revisit it (e.g. “we will not change X without a major version”)
- Would be easy to **reverse by mistake** if undocumented (e.g. “use capability probing, not hardcoded device checks”)

You do **not** need an ADR for:

- How-to or pattern docs (use the main design docs in `docs/design/`)
- One-off implementation details that are already clear from code and design docs

## Format

Use the same structure as [001-source-naming-stability.md](001-source-naming-stability.md):

1. **Title** – Short, decision-focused (e.g. “Source Naming Stability and Smart Normalization”).
2. **Status** – e.g. `Accepted - YYYY-MM-DD` (or Proposed / Deprecated / Superseded by ADR-XXX).
3. **Context** – What problem or situation led to this decision (constraints, pain points, options considered).
4. **Decision** – What we decided to do (concrete and actionable).
5. **Consequences** – Benefits, trade-offs, and any “we will / will not” follow-ups.

File naming: `NNN-short-slug.md` (e.g. `002-trust-api-after-success.md`). Number sequentially.

## Index

| ADR | Title | Status |
|-----|--------|--------|
| [001](001-source-naming-stability.md) | Source Naming Stability and Smart Normalization | Accepted |
| [002](002-trust-api-after-success.md) | Trust the API After Success — No Polling to Confirm | Accepted |
| [003](003-capability-probing-before-endpoints.md) | Capability Probing Before Using Endpoints | Accepted |
| [004](004-upnp-events-http-control.md) | UPnP for Events Only, HTTP API for All Control | Accepted |
| [005](005-led-indicator-and-display-apis.md) | LED Indicator and Display APIs | Accepted |
| [006](006-subwoofer-control-and-caching.md) | Subwoofer Control — WiiM-Only, Probing, Cache, Wire Semantics | Accepted |
| [007](007-media-position-raw-from-device.md) | Media Position and Duration — Raw from Device, No Client Estimation | Accepted |
| [008](008-loop-mode-vendor-specific-mapping.md) | Shuffle and Repeat (`loop_mode`) — Vendor-Specific Maps | Accepted |
| [009](009-group-role-and-slave-detection.md) | Multiroom Group Role — Authoritative `group` and `get_device_group_info` | Accepted |
| [010](010-wifi-direct-multiroom-player-resolution.md) | WiFi Direct Multiroom — UUID Resolution and Player Registry | Accepted |
| [011](011-stable-source-ids-and-catalog.md) | Stable Source Identifiers and `source_catalog` Round-Trip | Accepted |
| [012](012-play-notification-and-tts-fallback.md) | Play Notification (TTS) — Prompt Path, `play_url` Fallback, `force_interrupt` | Accepted |
| [013](013-http-apiresponse-parsed-and-raw.md) | HTTP API Layer — `ApiResponse(parsed, raw)` from `_request` | Accepted |
| [014](014-audio-output-hardware-probe-strategy.md) | Audio Output Hardware — Probe Order and Field Semantics | Accepted |
| [015](015-https-default-and-protocol-port-fallback.md) | Transport — HTTPS First and Port/Protocol Fallback | Accepted |
| [016](016-connect-time-read-only-capability-probes.md) | Connect-Time Capability Probes — Read-Only, Retries, Caching | Accepted |
| [017](017-eq-off-and-dynamic-preset-resolution.md) | EQ Presets — “Off” Semantics and Device-Native Preset Names | Accepted |
| [018](018-capabilities-dict-source-of-truth.md) | Client `capabilities` Dict — Single Source of Truth for Optional HTTP Features | Accepted |
| [019](019-12v-trigger-cache-and-configuration-tier-refresh.md) | 12V Trigger — Static Capability, Cache, Configuration-Tier Refresh | Accepted |

When adding a new ADR, add a row to this table.
