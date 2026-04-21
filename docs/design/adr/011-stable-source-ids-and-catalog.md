# ADR 011: Stable Source Identifiers and `source_catalog` Round-Trip

## Status
Accepted - 2026-04-20

## Context
Integrations (e.g. Music Assistant, Home Assistant) need to **persist** a source value and later pass it to **`set_source`** without drift. Returning UI-only strings from **`player.source`** caused mismatches with catalog entries and brittle automations. This is **complementary** to [ADR 001](001-source-naming-stability.md), which locks **display** names and **normalization for API** calls; ADR 001 does not by itself define the **`player.source`** property’s return type for **id** vs **label**.

## Decision
- **`player.source`** (and **`player.source_id`**) return a **canonical source id** aligned with **`player.source_catalog[*]["id"]`** (e.g. `network`, `line_in`, `spotify`) so stored values **round-trip** through **`set_source`**.
- **Human-facing labels** for UI use **`player.source_name`** (or catalog `name` fields), not the raw id string where a label is required.
- **`source_catalog`** remains the structured list of sources with **`id`**, **`name`**, **`kind`**, **`selectable`**, per-source capability flags, and **`is_current`**.

## Consequences
- **Breaking change** relative to older releases that returned display-oriented strings from **`source`** alone (see changelog **2.1.82**); integrations must use **`source_name`** for display and **`source`** for logic/persistence.
- New sources or ids must be added consistently to **MODE_MAP / catalog generation** and documented in API reference.
- ADR 001 remains the authority for **locked display names** and **`set_source`** normalization; ADR 011 is the authority for **property-level ids** vs **names**.
