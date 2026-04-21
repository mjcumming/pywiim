# ADR 010: WiFi Direct Multiroom — UUID Resolution and Player Registry

## Status
Accepted - 2026-04-20

## Context
Some LinkPlay / legacy devices use **WiFi Direct** multiroom: slaves appear on **internal IPs** (e.g. `10.10.10.x`) that Home Assistant does not know as entities. **`getSlaveList`** may return those IPs but include **UUIDs**. Matching slaves only by **IP** fails; **`group`** on the slave can also look **solo** when queried directly.

## Decision

### 1. UUID as stable identity
- **Populate and use `slave_uuids`** (alongside `slave_hosts`) from **`get_device_group_info()`** so group membership can be correlated across address spaces.

### 2. Resolving the other `Player` instance
- Prefer matching slaves to **`Player`** instances by **UUID** when IP-based **`player_finder`** cannot resolve the address seen on the master.
- **`all_players_finder`**: optional callback returning known **`Player`** objects so pywiim can search by UUID when the integration holds multiple players (e.g. HA coordinator registry).
- **Internal player registry** (`PlayerBase._all_instances` and helpers): allows **WiFi Direct** linking **without** always requiring integration wiring when instances are created in-process; when hosts need cross-process discovery, **`all_players_finder`** remains the integration hook.

### 3. Cross-coordinator inference
- When a device reports **solo** but **another** known master’s slave list includes this device’s **UUID**, infer **slave** role for group membership display (documented integration pattern).

## Consequences
- Integrations that support WiFi Direct groups **should** provide **`all_players_finder`** (and UUID-aware **`player_finder`**) where slaves are not reachable at the IP the user configured.
- Changes to registry lifetime or UUID normalization are **high regression** areas for `group_members` and master/slave UIs.
