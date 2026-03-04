# ADR 004: UPnP for Events Only, HTTP API for All Control

## Status
Accepted - 2025-12 (architecture established in design; formalized here)

## Context
WiiM and LinkPlay devices expose both:

- **HTTP API** (`/httpapi.asp?command=...`): Commands for playback, volume, source, EQ, groups, etc.
- **UPnP/DLNA**: Services (e.g. AVTransport, RenderingControl) that can be used for both control and for event subscriptions.

Some implementations (e.g. WiiM Play) use UPnP for transport control (play/pause/seek/volume) and HTTP for device-specific features. That gives two control paths and requires handling UPnP SOAP errors and timeouts for control.

## Decision
We use a **single control path** and a **single event path**:

- **All control** (play, pause, stop, volume, mute, source, EQ, groups, presets, etc.) goes through the **HTTP API** only.
- **UPnP is used only for events**: subscriptions to AVTransport and RenderingControl to receive state-change notifications (play state, volume, mute, track, position). We do not use UPnP for sending control commands.

### Rules
1. **No UPnP for control**: Playback control, volume, source selection, EQ, group operations, and any device configuration are implemented exclusively via HTTP API calls.
2. **UPnP for notifications only**: Subscribe to UPnP services to get real-time state updates; merge those into library state (e.g. via StateSynchronizer).
3. **HTTP remains authoritative for control**: If UPnP subscription fails or is unavailable, the application still has full control via HTTP and can rely on HTTP polling for state sync.

### Out of scope
- How we merge UPnP events with HTTP state (freshness, priority) is documented in ARCHITECTURE_DATA_FLOW and STATE_MANAGEMENT; this ADR only fixes the split between control (HTTP) and events (UPnP).

## Consequences
- **One control path**: Simpler mental model and fewer failure modes than dual HTTP + UPnP control.
- **Better error handling**: HTTP API errors are easier to handle and report than UPnP SOAP errors.
- **Feature parity**: HTTP API supports all features we need (EQ, groups, audio output, etc.); UPnP does not.
- **Framework-agnostic**: Integrations that already use HTTP for control (e.g. Home Assistant) align naturally; UPnP is an optional enhancement for real-time updates.

Details: [UPNP_INTEGRATION.md](../UPNP_INTEGRATION.md).
