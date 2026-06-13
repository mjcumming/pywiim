# Design Documentation

This directory contains design documentation, architecture decisions, and implementation patterns for the pywiim library.

## Architecture Decision Records (ADRs)

Decisions we have explicitly committed to (e.g. user-facing stability, API contracts) are recorded as ADRs:

- **[adr/](adr/)** - ADR index and when to write one
- **[001: Source Naming Stability](adr/001-source-naming-stability.md)** - Locked display names and smart normalization for sources
- **[002: Trust the API After Success](adr/002-trust-api-after-success.md)** - No polling to confirm operations; update state immediately
- **[003: Capability Probing Before Endpoints](adr/003-capability-probing-before-endpoints.md)** - Probe optional endpoints at runtime, don't hardcode by device
- **[004: UPnP for Events, HTTP for Control](adr/004-upnp-events-http-control.md)** - Single control path (HTTP); UPnP for notifications only
- **[005: LED Indicator and Display APIs](adr/005-led-indicator-and-display-apis.md)** - Separate capabilities and player APIs for status LED vs screen/display
- **[006: Subwoofer control](adr/006-subwoofer-control-and-caching.md)** - WiiM-only, probing, cache, inverted wire fields
- **[007: Media position](adr/007-media-position-raw-from-device.md)** - Raw device position/duration; no library-side estimation
- **[008: Loop mode](adr/008-loop-mode-vendor-specific-mapping.md)** - Scheme-specific maps plus source-aware decoding
- **[009: Group role](adr/009-group-role-and-slave-detection.md)** - Authoritative `group` field; `get_device_group_info` policy
- **[010: WiFi Direct multiroom](adr/010-wifi-direct-multiroom-player-resolution.md)** - UUID resolution, `all_players_finder`, internal registry
- **[011: Stable source ids](adr/011-stable-source-ids-and-catalog.md)** - `player.source` ids vs `source_name`; catalog round-trip (complements 001)
- **[012: Play notification / TTS](adr/012-play-notification-and-tts-fallback.md)** - Prompt vs `play_url`, `force_interrupt`, structured result
- **[013: ApiResponse](adr/013-http-apiresponse-parsed-and-raw.md)** - `parsed` / `raw` from HTTP `_request`
- **[014: Audio output probes](adr/014-audio-output-hardware-probe-strategy.md)** - Probe order; `getStatusEx` vs output JSON semantics
- **[015: HTTPS and fallback](adr/015-https-default-and-protocol-port-fallback.md)** - HTTPS first; full port/protocol probe list on failure
- **[016: Connect-time probes](adr/016-connect-time-read-only-capability-probes.md)** - Read-only probes, retries; complements 003
- **[017: EQ Off and presets](adr/017-eq-off-and-dynamic-preset-resolution.md)** - “Off” semantics; resolve preset names from device list
- **[018: Capabilities dict](adr/018-capabilities-dict-source-of-truth.md)** - `client.capabilities` is the source of truth for optional HTTP features; integrations gate on it, not model alone

When changing behavior that might be covered by an ADR, check the ADR first. When making a significant decision, add a new ADR (see `adr/README.md` for format). **Full table:** [adr/README.md](adr/README.md).

## Core Architecture

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - High-level system architecture, components, and design patterns
- **[ARCHITECTURE_DATA_FLOW.md](ARCHITECTURE_DATA_FLOW.md)** - State synchronization, data flow, play state identification, and position handling

## Design Principles

- **[DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md)** - Core design principles, goals, trade-offs, and patterns
- **[LESSONS_LEARNED.md](LESSONS_LEARNED.md)** - Critical design requirements and patterns learned from integration

## Device Compatibility

- **[DEVICE_PROFILES.md](DEVICE_PROFILES.md)** - Device profiles system, vendor detection, endpoint abstraction, device catalog, and compatibility matrix
- **[PROTOCOL_DETECTION.md](PROTOCOL_DETECTION.md)** - Protocol/port detection strategy and endpoint caching

## API & Integration

- **[API_DESIGN_PATTERNS.md](API_DESIGN_PATTERNS.md)** - API reliability matrix, defensive programming, and endpoint patterns
- **[UPNP_INTEGRATION.md](UPNP_INTEGRATION.md)** - UPnP integration patterns, architecture, and health tracking
- **[LINKPLAY_ARCHITECTURE.md](LINKPLAY_ARCHITECTURE.md)** - LinkPlay "split brain" system, transport protocols, shuffle/repeat support, and control authority

## Implementation Patterns

- **[OPERATION_PATTERNS.md](OPERATION_PATTERNS.md)** - State-changing operation patterns (trust API, handle preconditions)
- **[SOURCE_ENUMERATION_VS_SELECTION.md](SOURCE_ENUMERATION_VS_SELECTION.md)** - Two-layer source system (enumerable vs selectable)

## Documentation Status

All design documentation has been consolidated and updated as of 2025-01-XX:
- ✅ Merged overlapping documents
- ✅ Removed outdated information
- ✅ Updated cross-references
- ✅ Consolidated from 15 files to 12 files

See [CONSOLIDATION_PLAN.md](CONSOLIDATION_PLAN.md) for details on the consolidation process.
