# 020: Solo and Group Output Channel Selection

**Status:** Proposed — 2026-10-28

## Context

Some WiiM devices expose two independent settings: the `ch` status field controlled by `setPlayerCmd:slave_channel`, and a standalone mode controlled by `getChannelMode` and `setChannelMode`. A solo WiiM Pro Plus owner reported that changing `ch` did not isolate the requested channel. On two WiiM Pros, tests at zero volume confirmed independent command and status readback for both settings in solo and group roles; they could not establish which audio was audible. The Pro Plus and audible behavior still need confirmation.

Other LinkPlay devices report that the channel-mode command is unknown and may use `ch` for standalone playback. A missing or failed probe cannot establish that the API is unsupported.

## Decision

- Probe the standalone channel-mode API without writing. Distinguish supported, explicitly unsupported, and inconclusive results.
- For a solo player that supports this API, read and set its standalone mode. For a group leader or member, use that player's group `ch`; maintain independent cached values as roles change.
- If the device explicitly rejects the mode API as unknown, retain legacy `ch` behavior. If the probe is inconclusive, leave the solo mode unknown and do not write the group setting as a substitute; retry on refresh.
- Preserve the existing public stereo, left and right setter and low-level group-channel APIs. A reported standalone `mono` mode remains visible to library consumers, but is not a supported setter or Home Assistant select option.
- Honor the normal command acknowledgement and cache contract in [ADR 002](002-trust-api-after-success.md); a successful status readback alone does not prove audible channel isolation.

## Consequences

The same player-facing control follows its current group role and does not overwrite the other setting. Solo devices with a supported mode API make an additional read during refresh. Failed probes can temporarily leave solo control unavailable, avoiding a misleading or unintended group-channel write. Audible validation, including on the issue reporter's Pro Plus, remains necessary before treating the reported problem as confirmed fixed.
