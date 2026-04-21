# ADR 013: HTTP API Layer — `ApiResponse(parsed, raw)` from `_request`

## Status
Accepted - 2026-04-20

## Context
Device endpoints return a mix of **JSON objects**, **non-JSON bodies** (plain text errors, empty bodies), and success-like non-JSON responses. Callers inconsistently accessed `.json()` or assumed dicts, complicating **error classification** and **best-effort** commands (e.g. `EQOff` on devices that return plain text `"unknown command"`).

## Decision
- The base HTTP layer returns a single type (**`ApiResponse`**, names may vary slightly in code) with at least:
  - **`parsed`**: decoded JSON when the body is JSON; otherwise **`None`** or an agreed sentinel as implemented.
  - **`raw`**: original body / text / bytes as appropriate for logging and non-JSON success paths.
- **All API mixins** and tests that talk to **`_request`** / **`_request_with_protocol_fallback`** use **`.parsed` / `.raw`** explicitly—no direct `.json()` on the transport response from scattered call sites.

## Consequences
- New endpoints must decide how to interpret **`parsed` vs `raw`** and document edge cases in **`API_DESIGN_PATTERNS`**.
- Centralizing here makes **“unknown command” as plain text** and similar quirks one policy change away instead of per-endpoint surprises.
