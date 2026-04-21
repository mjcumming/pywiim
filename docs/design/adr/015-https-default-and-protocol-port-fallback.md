# ADR 015: Transport — HTTPS First and Full Port/Protocol Fallback

## Status
Accepted - 2026-04-20

## Context
Devices advertise mixed hints (SSDP, user-configured host). Integrations sometimes pass **wrong port** (e.g. **443** when the device only answers on **HTTP 80**). Probing only the user-supplied port/protocol pair caused **false “unreachable”** errors and support churn.

## Decision
- **Default transport assumption**: devices are reached over **HTTPS** on standard LinkPlay/WiiM ports as implemented in the client (see **`PROTOCOL_DETECTION`** / client connection logic).
- When a **user-specified** port (or initial hint) **fails**, **fall back** through the **standard probe list** (HTTPS and HTTP on the project’s canonical port set)—do not give up until that list is exhausted (as in changelog **2.1.6** behavior).
- User-facing connectivity errors should distinguish **unreachable** vs **wrong protocol/port** where the codebase supports it (**`WiiMConnectionError`** messaging).

## Consequences
- Adding a new default port or TLS behavior is a **library-wide** connectivity decision—update tests and **`REAL-DEVICE-TESTING`** notes.
- Integrations should **omit port** when possible and persist **discovered** base URLs from pywiim discovery/connect results.
