# ADR 016: Connect-Time Capability Probes — Read-Only, Retries, and Caching

## Status
Accepted - 2026-04-20

## Context
Features such as **subwoofer**, **PEQ**, **12V trigger**, **channel balance**, and **LED indicator** (where probed) cannot be inferred reliably from static device info alone. Once populated, the merged **`client.capabilities`** dict is the **single source of truth** for what to expose in apps; see **[ADR 018](018-capabilities-dict-source-of-truth.md)**. Probes must **not brick** startup, must avoid **mutating** device state, and must behave predictably under **transient** network or firmware errors. [ADR 003](003-capability-probing-before-endpoints.md) covers **using** probed capabilities when **calling** endpoints during operation; this ADR covers **how** we populate capabilities at **connect** (and **`refresh_capabilities`**).

## Decision

### 1. Read-only at probe time
- Connect-time probes use **GET**-style or **status-only** commands that do **not** intentionally change user-visible playback, output routing, or stored settings. (If a vendor’s only test is inherently mutating, document the exception explicitly in code and design docs.)

### 2. Retries and inconclusive results
- Transient errors may use **limited retries** with small backoff where implemented (e.g. subwoofer probe).
- **`True` / `False` / `None`** semantics where used: **`False`** = definitively unsupported; **`None`** = inconclusive until a later refresh or **`refresh_capabilities`** proves otherwise.

### 3. Invalidation
- **`refresh_capabilities(force=True)`** must allow **re-running** probes after firmware OTA or major state change, per client API.

### 4. Relationship to ADR 003
- ADR 003: **do not hardcode** device models for optional code paths—use **`capabilities`** populated here and elsewhere.
- ADR 016: **how** those booleans/objects get set **at connect** without destabilizing the rest of the stack.

## Consequences
- New optional features should add a **clear probe function** and wire into **`detect_device_capabilities`** (or successor) with tests in **`tests/unit/test_capabilities.py`** (or equivalent).
- Changing probe side effects or retry counts can affect **boot-time** traffic and flakiness—benchmark and document when tightening.
