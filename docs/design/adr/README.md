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

| ADR   | Title                                               | Status   |
|-------|-----------------------------------------------------|----------|
| [001](001-source-naming-stability.md) | Source Naming Stability and Smart Normalization     | Accepted |
| [002](002-trust-api-after-success.md) | Trust the API After Success — No Polling to Confirm | Accepted |
| [003](003-capability-probing-before-endpoints.md) | Capability Probing Before Using Endpoints           | Accepted |
| [004](004-upnp-events-http-control.md) | UPnP for Events Only, HTTP API for All Control     | Accepted |

When adding a new ADR, add a row to this table.
