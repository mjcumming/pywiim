# ADR 003: Capability Probing Before Using Device-Specific Endpoints

## Status
Accepted - 2025-12 (pattern established in design; formalized here)

## Context
WiiM and LinkPlay devices vary widely: different firmware, vendors (WiiM, Arylic, Audio Pro, etc.), and models support different HTTP API endpoints. For example:

- `getStatusEx` is available on WiiM-enhanced devices; basic LinkPlay may only have `getStatus`.
- `getMetaInfo` (track metadata/artwork) is missing on many older or non-WiiM devices.
- EQ endpoints may be absent on some units.
- `getStatus` (basic LinkPlay) **does not work** on WiiM devices; we must use `getPlayerStatus` / status-ex flows.

Hardcoding endpoint usage by device model or vendor is fragile: new models and firmware versions constantly appear, and the same endpoint can work on one firmware and fail on another.

## Decision
We **probe for capability at runtime** instead of relying on device type or model alone. Before using an optional or device-varying endpoint, we check that it is supported.

### Rules
1. **Probe on first use**: When a client is created (or first needs an optional feature), probe the relevant endpoint(s) and cache the result (e.g. `_statusex_supported`, `_metadata_supported`, `_eq_supported`).
2. **Use probe result, not model**: Code paths branch on capability flags (e.g. "does this client support getMetaInfo?") rather than on device model or vendor strings for endpoint availability.
3. **Graceful fallback**: If an endpoint is unsupported, disable that capability and use documented fallbacks (e.g. metadata from `getPlayerStatus` when `getMetaInfo` is unavailable).
4. **No hardcoded "device X has endpoint Y"**: Avoid adding special cases that say "if WiiM then use A, if Audio Pro then use B" for endpoint availability. Prefer "if probed capability then use A, else B."
5. **Application may cache capabilities**: The library is stateless; applications (e.g. Home Assistant) may persist and reuse capability results across restarts to avoid repeated probing. The library accepts optional `capabilities` in `WiiMClient(host, capabilities=...)`.

### Out of scope
- Protocol/port detection (HTTPS vs HTTP, ports 443/8443/4443) and endpoint *resolution* (which base URL to use) are separate concerns, documented in DEVICE_PROFILES and PROTOCOL_DETECTION.
- This ADR is about **which** API commands/endpoints we call once we have a working base URL.

## Consequences
- **Robust across devices and firmware**: New devices and firmware updates are handled by probing, not by maintaining a large model table.
- **Clear fallbacks**: When an endpoint is missing, we degrade gracefully (e.g. no artwork) instead of failing or guessing.
- **Consistent pattern**: All optional or variable endpoints follow the same probe-then-use pattern.
- **Cost**: One-time probe delay on first connection; can be mitigated by application-level capability caching.

Details and examples: [API_DESIGN_PATTERNS.md](../API_DESIGN_PATTERNS.md) (Capability Probing, Capability Detection and Caching Strategy).
