# ADR 023: Prefer Daily Use over Set-and-Forget Settings

## Status

Accepted - 2026-11-24

## Context

The WiiM HTTP API can configure most of what the WiiM Home app can configure. That includes playback and groups, and also accounts, network, one-time hardware setup, and preferences a person sets once. Contributors reasonably ask the library to grow toward the app.

The discovered-API notes already say one-off setup commands are a poor Home Assistant surface, and that user-facing behavior should stay on daily listening and automation. That note is easy to miss. This ADR records it as guidance for new work.

The Home Assistant integration uses the same guidance for entities and services ([wiim ADR 0010](https://github.com/mjcumming/wiim/blob/main/docs/adr/0010-daily-use-surface.md)).

## Decision

This is guidance for reviewing a new feature, not a ban, and not a promise to cover the HTTP API.

Prefer daily use. That means playback, volume, source, grouping, the EQ choice a listener actually selects, and a device reading that changes on its own and is worth acting on.

Set-and-forget settings are not the focus. A preference someone chooses once, or a control whose purpose is to repeat a screen in the WiiM Home app, usually stays in the app. Account, network, and one-time hardware setup are in that group. A request there needs a reason beyond avoiding the app.

A feature can still be accepted when that reason is real. The review should say what the daily or automated use is, and what the feature costs a speaker that never uses it. An uncommon setting is not refused by this guidance alone, and it is not something the library sets out to add.

A library field does not have to become an integration entity. Features already shipped stay. This guidance applies to what we add.

## Consequences

- Reviews have a shared question: who uses this in normal listening, and how often?
- A pull request that only mirrors an app screen can be declined without that decline becoming a rule against every uncommon setting.
- Two reviewers can weigh the same request differently. The reason recorded on the request is what keeps the guidance honest.
