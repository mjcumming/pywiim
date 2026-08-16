# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **PlayQueue auto-advance** — after `PlayQueueWithIndex`, call `SetQueueLoopMode` (default 4 = play through once; respects shuffle/repeat) so queued URLs continue instead of going idle (wiim #268).
- **PlayQueue `queue_count` / `queue_position`** — overlay from `BrowseQueue` / `GetQueueIndex` when HTTP `plicount`/`plicurr` stay empty (ADR 004) (wiim #268).

## [2.3.2] - 2026-08-15

### Fixed
- **Connect failures after retries** — exhausted `ClientConnectorError` / disconnect retries now raise `WiiMConnectionError` instead of a generic `WiiMRequestError`, so integrations can mark powered-off devices unavailable (wiim #259).
- **Stale metadata leaking through `_status_field`** — when the synchronizer has resolved title/artist/album/art to no value, do not fall back to leftover firmware fields still sitting on the raw status model. Source-change clears now leave an explicit None so that fallback cannot reopen (wiim #263).
- **Gen1 profile override** — use `dataclasses.replace()` so extra DeviceProfile fields are not dropped back to defaults.

## [2.3.1] - 2026-08-15

### Fixed
- **UPnP `async_call_action("AVTransport")`** — SOAP service names like `AVTransport` now resolve to `_av_transport_service`. Missing actions raise `Action … not found` instead of a misleading service error (wiim #264).
- **`supports_queue_add` requires a real enqueue action** — AVTransport without `AddURIToQueue` is not enough. WiiM Pro / Pro Plus use vendor PlayQueue (`CreateQueue`, `AppendTracksInQueueEx`, `PlayQueueWithIndex`) instead; Arylic remains false until that path is proven there (wiim #264).
- **PlayQueue URL enqueue** — `add_to_queue` / `insert_next` / `play_queue` / `clear_queue` / `remove_from_queue` use PlayQueue SOAP with DIDL `TrackN` metadata when `AddURIToQueue` is missing. HTTP `setPlayerCmd:add` is a no-op on this firmware (wiim #264).
- **Stop / none map to idle** — HTTP/UPnP `stop` and `stopped` normalize to `idle` instead of `pause`, so integrations can tell a stopped device from a paused one (wiim #259).
- **Stale metadata after source change** — title/artist/album/art/duration are cleared when the source changes, leftover firmware values are ignored on later polls, and `play_url()` filename fallback is not used for physical inputs or idle (wiim #263).
- **Reboot command fallback** — if `reboot` returns `unknown command`, try `StartRebootTime:1` then `StartRebootTime:0` and cache the working command (WiiM Amp / current firmware; wiim #260).
- **Audio Pro C5 / compact `AudioPro` names** — vendor detection now matches `c5` and `AudioPro` without a space so C5 MkII gets the MkII profile (wiim #266).

### Added
- **`Player.set_main_speaker_bass()` / `Player.main_speaker_bass`** — expose the existing client main-speaker bass filter on the Player API (wiim #265).

### Documentation
- **PlayQueue enqueue** — ADR 004 exception, HA_CAPABILITIES, HA_INTEGRATION, and API_REFERENCE now describe the WiiM PlayQueue path vs AVTransport `AddURIToQueue`.

## [2.3.0] - 2026-07-06

### Added
- **Custom input labels and accurate input lists (WiiM)** — source enumeration now
  consumes the read-only WiiM app APIs discovered in 2.2.18. On WiiM devices,
  `Player.available_sources` / `source_catalog` overlay:
  - **`getModeRename`** — user custom labels (e.g. Optical renamed "Optical Mike")
    are shown as the source display name while the stable id stays canonical
    (`optical`). `set_source()` resolves the custom label, the canonical name, and
    the previous normalized name ("Optical In"), so existing automations keep working.
  - **`getAudioInputEnable`** — inputs the user disabled in the WiiM app are hidden
    from the source list (the currently active source is always kept for state display).
  - **`getAudioInputCapbility`** — the device's authoritative input list fills gaps
    left by `plm_support`/`InputList` guessing.

  These are read-only, WiiM-only overlays probed once at connect. Non-WiiM
  LinkPlay/OEM devices return no data and keep the existing enumeration behavior
  unchanged. Firmware that points several mode keys at one label (e.g. `optical`
  and `SPDIF-In`) resolves to the canonical hardware id. Addresses
  [mjcumming/wiim#257](https://github.com/mjcumming/wiim/issues/257).
- **`normalize.canonical_source_key()` / `source_rename_reverse()`** — shared, pure
  source-id normalization helpers so enumeration, the catalog, and the input overlay
  agree on ids.

## [2.2.19] - 2026-06-30

### Added
- **More read-only WiiM daily-use APIs** — `WiiMClient` now exposes
  `get_audio_input_capability()` for the firmware-spelled `getAudioInputCapbility`,
  read-only LV2 graphic EQ helpers (`get_graphic_eq_bands()`,
  `get_graphic_eq_preset_list()` for `Eq10HP`), and read-only room-correction
  state (`get_room_correction()`). These APIs are documented as daily-use or
  capability/diagnostic surfaces; one-off setup, account, network, and token
  endpoints remain intentionally out of scope. Diagnostics and verify CLIs now
  include these read-only probes/summaries.

## [2.2.18] - 2026-06-27

### Added
- **Read-only WiiM app-discovered APIs** — `WiiMClient` now exposes optional helpers for
  `getAudioInputEnable`, `getModeRename`, `GetAcousticCapability`, `getAllRoutines`, and
  `getSoundCardModeSupportList`. These helpers are intentionally read-only and return `None`
  or an empty list when unsupported so they can be used for diagnostics and future capability
  enrichment without changing source/output behavior yet ([#20](https://github.com/mjcumming/pywiim/issues/20)).
- **`wiim-diagnostics --discovered-apis-only`** — Focused real-device probe for the new
  read-only WiiM endpoints, with JSON report support.

### Fixed
- **Unsupported LinkPlay/Arylic error payloads for discovered APIs** — Firmware responses such
  as `{"error": "unsupported_command", "raw": "unknown command"}` and
  `{"state": -1, "error": "Fail"}` are now classified as unsupported instead of being accepted
  as permissive empty Pydantic models.

### Documentation
- **Discovered WiiM API protocol note** — Added real-device observations for WiiM Pro,
  Arylic H50, and Up2Stream Amp V4 to document that these endpoints appear WiiM-specific
  in current testing.

## [2.2.17] - 2026-06-27

### Fixed
- **Long local/network media durations** — `curpos` / `totlen` parsing is now source-aware, so
  local URL playback (`mode=10`) and USB/UDisk tracks keep millisecond time units even when the
  raw duration exceeds the old 10-hour heuristic threshold. Very long tracks no longer collapse to
  tiny durations such as `41s` or trigger false position > duration warnings
  ([mjcumming/wiim#251](https://github.com/mjcumming/wiim/issues/251),
  [#21](https://github.com/mjcumming/pywiim/issues/21)).
- **WiiM Ultra USB source detection** — `getPlayerStatusEx` responses with `vendor=UDisk*`
  now normalize to canonical source `usb` even when firmware reports `mode=10`
  ([#21](https://github.com/mjcumming/pywiim/issues/21)).

## [2.2.16] - 2026-06-20

### Fixed
- **WiiM Ultra / Amp Ultra display reported "on" but panel stayed dark when turned back on**
  — `setLightOperationBrightConfig` requires `auto_sense_enable`, `default_bright`, and `disable`
  in one payload, and `set_display_enabled(True)` hard-coded `auto_sense_enable=0`. On affected
  firmware this registered the display as on (`disable=0`) while leaving the LCD dark and silently
  disabling the user's adaptive-brightness setting — users had to toggle adaptive brightness in
  the WiiM app to relight it. Turning the display **on** now enables adaptive brightness
  (`auto_sense_enable=1`) by default so the panel actually lights. Both `set_display_enabled` (client
  and player) gain an optional `auto_sense_enable` keyword (pass `0` for fixed brightness); defaults
  are `1` when turning on and `0` when turning off ([mjcumming/wiim#250](https://github.com/mjcumming/wiim/issues/250)).

## [2.2.15] - 2026-06-18

### Fixed
- **Arylic HTTP endpoint still not persisted (follow-up to 2.2.14)** — The 2.2.14
  `_apply_protocol_preference()` correction only ran inside `_detect_capabilities()`, but the
  poll/coordinator client is constructed with *cached* capabilities and skips detection, so it
  still probed HTTPS-first and persisted the slow HTTPS endpoint. The standard probe list now
  orders by the device profile's `protocol_priority` whenever capabilities are known, so a
  client that already knows it is talking to an Arylic device probes — and caches/persists —
  HTTP first. HTTPS-only Arylic devices still fall through to their working HTTPS endpoint, and
  WiiM/Audio Pro remain HTTPS-first. Additionally, `client.port` is now kept in sync with the
  cached endpoint so discovery/integration code that reads `port` no longer mis-persists HTTPS
  for an HTTP endpoint ([mjcumming/wiim#248](https://github.com/mjcumming/wiim/issues/248)).
- **Spurious "Failed to detect capabilities" WARNING for non-LinkPlay devices during discovery** —
  Home Assistant's broad SSDP matcher (`MediaRenderer:1`, intentionally wide so all LinkPlay OEMs
  are discovered) hands every DLNA renderer on the LAN (AV receivers, TVs) to the config flow,
  which probes each via `validate_device`/`is_linkplay_device`. The fallback probe calls
  `get_player_status()` → `_detect_capabilities()`, whose *recoverable* failure path logged at
  `warning` — so each non-WiiM device produced a misleading "Failed to detect capabilities…"
  WARNING even though it was simply not a LinkPlay device. Discovery probes now set
  `client._quiet_capabilities`, downgrading that message to `debug`; configured-device setup is
  unchanged and still warns on a genuine failure
  ([mjcumming/wiim#249](https://github.com/mjcumming/wiim/issues/249)).

## [2.2.14] - 2026-06-17

### Fixed
- **Slow HTTPS endpoint cached on Arylic devices despite HTTP being ~10x faster** —
  The endpoint probe is HTTPS-first (WiiM hardware only listens on HTTPS:443), so Arylic
  devices that also answer on HTTPS:443 with a slow embedded-TLS handshake (~250–470 ms vs
  ~25–85 ms over plain HTTP) had HTTPS cached permanently, making every poll cycle sluggish.
  The device profile is now the single source of truth for protocol preference, and once the
  vendor is known the client re-points a cached HTTPS endpoint to HTTP **only** when the
  profile prefers HTTP *and* plain HTTP actually returns a valid response — so HTTP-only
  Arylic devices become snappy while HTTPS-only Arylic and all WiiM devices keep working
  unchanged ([mjcumming/wiim#248](https://github.com/mjcumming/wiim/issues/248)).
- **Arylic S10+ mis-detected as `linkplay_generic`** — The S10+ reports its model as
  `S10P_WIFI` (a "p", no "+"), which the vendor and LED-format detection did not match. It is
  now correctly identified as an Arylic device ([mjcumming/wiim#248](https://github.com/mjcumming/wiim/issues/248)).
- **`getMetaInfo` called on every poll for devices that do not support it** — Devices such as
  some Arylic Up2Stream models reply to `getMetaInfo` with a non-JSON `unknown command` body
  and HTTP 200 (rather than an error), so metadata stayed enabled and the command was retried
  every poll cycle. Capability detection now recognises this response and disables metadata for
  non-WiiM devices, and the poll/cover-art paths skip `getMetaInfo` when it is unsupported
  ([mjcumming/wiim#248](https://github.com/mjcumming/wiim/issues/248)).

## [2.2.13] - 2026-06-13

### Fixed
- **Context-aware `loop_mode` decoding** — `loop_mode` interpretation now uses
  source context in addition to the device `loop_mode_scheme`. Spotify on WiiM-scheme
  devices can report `loop_mode=5` for single-track repeat, which is now decoded as
  repeat-one without noisy "unknown loop_mode" warnings, while Arylic-scheme devices
  still decode `5` as shuffle plus repeat-one ([mjcumming/wiim#246](https://github.com/mjcumming/wiim/issues/246)).

## [2.2.12] - 2026-06-13

### Fixed
- **Cover art stuck one track behind on the HTTP polling path** — The track-change signal
  (`_last_track_signature`) was a single-shot latch consumed by the EQ/source trigger logic
  early in `refresh()`, so the artwork enrichment in `_finalize_refresh` re-derived
  `track_changed=False` and silently skipped refreshing a *valid but stale* previous-track
  artwork URL. The enrichment override (added in 2.2.10) therefore never ran on the polling
  path that most setups use when UPnP eventing is degraded. The track-change edge is now
  computed once per refresh and threaded to every consumer (triggers, periodic data, finalize,
  and the UPnP-event path), so `getMetaInfo`/`GetInfoEx` enrichment reliably runs on each track
  change ([mjcumming/wiim#245](https://github.com/mjcumming/wiim/issues/245)).

## [2.2.11] - 2026-06-11

### Fixed
- **Arylic grouped playback artwork refresh** — Track changes now refresh UPnP/GetInfoEx
  enrichment even when `getMetaInfo` returns a syntactically valid but stale artwork URL from the
  previous track. `GetInfoEx` is now probed on track changes and its UPnP metadata can override the
  stale HTTP artwork, so Arylic/grouped playback no longer gets stuck on the first loaded cover art
  while titles continue changing ([mjcumming/wiim#244](https://github.com/mjcumming/wiim/issues/244)).

## [2.2.9] - 2026-06-08

### Fixed
- **Arylic/GetInfoEx artwork source merge** — LinkPlay `GetInfoEx` artwork is now applied through
  the UPnP state lane instead of the HTTP lane, and explicit enrichment updates may apply metadata
  while paused. This prevents metadata-free UPnP pause updates from falling back to the embedded
  WiiM logo while the paused track still exposes album art
  ([mjcumming/wiim#244](https://github.com/mjcumming/wiim/issues/244)).

## [2.2.8] - 2026-06-05

### Added
- **Strict discovery validation helper** — `validate_device_strict()` wraps the existing soft
  `validate_device()` contract and raises `WiiMConnectionError` when a host does not validate as
  LinkPlay/WiiM. This gives integrations and manual setup flows an exception-style API without
  breaking bulk discovery scans that rely on `validated=False`.

## [2.2.7] - 2026-06-05

### Added
- **LinkPlay GetInfoEx artwork fallback** — Arylic and other generic LinkPlay devices can expose
  `upnp:albumArtURI` via the vendor `GetInfoEx` UPnP action when HTTP `getMetaInfo` lacks artwork
  ([mjcumming/wiim#244](https://github.com/mjcumming/wiim/issues/244)).
  - `UpnpClient.get_info_ex()` with raw SOAP fallback when SCPD does not advertise the action
  - Cover art enrichment now tries GetInfoEx after `getMetaInfo`
  - UPnP description probing now also tries port `59152`

### Fixed
- **GetInfoEx artwork propagation** — The 2.2.6 fallback could parse Arylic/generic LinkPlay artwork
  but fail to expose it through `Player.media_image_url` because enrichment updated `entity_picture`
  without the canonical `image_url` state field. `GetInfoEx` now also tries raw SOAP when the
  advertised UPnP action returns no usable artwork, and DIDL parsing tolerates bare `&` characters
  in titles or artwork URLs.
- **CI codecov patch** — Unit tests for monitor hardware helpers, LED `LED_SWITCH_GET` parsing, and configuration-tier refresh paths (patch coverage ≥ 55%).

## [2.2.6] - 2026-06-05

### Added
- **LinkPlay GetInfoEx artwork fallback** for Arylic/generic LinkPlay devices ([mjcumming/wiim#244](https://github.com/mjcumming/wiim/issues/244)).

### Fixed
- **Chromecast source on WiiM Amp** — `vendor="CAST"` with `mode=5` now maps to network (`wifi`) instead of incorrectly reporting `bluetooth` ([#19](https://github.com/mjcumming/pywiim/issues/19)).

## [2.2.5] - 2026-05-19

### Added
- **ADR 019** — 12V trigger cache and configuration-tier refresh (`PollingStrategy.should_fetch_trigger_out`, `statemgr` slow poll). Fixes external trigger changes (e.g. WiiM Home app) not reaching integrations that read `player.trigger_out_on` ([mjcumming/wiim#240](https://github.com/mjcumming/wiim/issues/240)).
- **`PollingStrategy.should_fetch_led_indicator()`** and **`statemgr`** configuration-tier refresh for status LED; **`player.led_indicator_on`** cache.
- **`scripts/manual/watch_trigger_out.py`** — Manual watch script for 12V trigger testing.

### Fixed
- **Status LED read always “on” on WiiM** — `get_led_indicator()` now uses read-only **`LED_SWITCH_GET`** (plain `0`/`1`) before falling back to getStatusEx / assume-on.

### Changed
- **`wiim-monitor`** — Uses `should_fetch_trigger_out()` instead of misusing `should_fetch_audio_output()` for 12V trigger polling.
- **`wiim-monitor`** — Polls 12V trigger, subwoofer, and **status LED** on a **monitor-local** interval (default **10s**, `--hardware-poll N`); library/HA refresh stays ~60s.

## [2.2.4] - 2026-05-11

### Added
- **`get_loop_mode_mapping_for_scheme`**, **`resolve_loop_mode_mapping`**, **`resolve_loop_mode_mapping_for_player`** (`pywiim.api.loop_mode`) — scheme-first shuffle/repeat ↔ `loop_mode` mapping.
- **`is_wiim_12v_trigger_model()`** (`pywiim.model_names`) — known 12V trigger hardware models.
- **`client.capabilities["loop_mode_scheme"]`** — merged after capability detection from **`get_device_profile`**. Integration test asserts presence (**`test_capability_detection`**).

### Fixed
- **Status LED stuck off after connect or `wiim-verify`** ([#18](https://github.com/mjcumming/pywiim/issues/18)) — Connect-time **`LED_SWITCH_SET:0`** “probe” turned the LED off on stacks that accept the command. **Removed** that probe; **`supports_led_switch`** for **WiiM** comes from device class; **Arylic** unchanged (vendor + try-and-ignore on write).
- **WiiM Ultra `loop_mode` vs documented WiiM table** ([#17](https://github.com/mjcumming/pywiim/issues/17)) — Ultra firmware **≥ 5.2.0** uses LinkPlay/**Arylic**-style values; mapping now follows **`DeviceProfile.loop_mode_scheme`** (`arylic` for that case) through **`parse_player_status`**, **`WiiMClient`**, and **`Player`** shuffle/repeat.

### Changed
- **`supports_trigger_out`** — From **`getTriggeroutStatus`** probe to **`is_wiim_12v_trigger_model()`** only (no connect-time HTTP); avoids false positives on OEM hardware. **`wiim-verify`** trigger check is **read-only** (no toggle).
- **Design / integration docs** — ADR 005, 008, 016, 018; **API_REFERENCE**, **API_DESIGN_PATTERNS**, **DEVICE_PROFILES**, **HA_INTEGRATION**, **HA_CAPABILITIES** (LED, trigger, `loop_mode_scheme`, PEQ vs Eq10HP note for [#16](https://github.com/mjcumming/pywiim/issues/16)).

## [2.2.3] - 2026-04-24

### Fixed
- **Qobuz Connect / Home Assistant idle state** — `getPlayerStatusEx` may report `status: "none"` while `curpos`, `totlen`, and metadata still describe an active Qobuz session ([mjcumming/wiim#222](https://github.com/mjcumming/wiim/issues/222)). `_handle_qobuz_connect_state_quirks` previously treated `none` as a final transport state and skipped correction; it now only skips when status is already play/pause/buffering-style. Position-at-track-start (`curpos` / `position` **0**) now counts toward playback indicators.

## [2.2.2] - 2026-04-20

### Added
- **`WiiMClient.refresh_capabilities(force=True)`** — Re-runs `WiiMCapabilities.detect_capabilities` (with optional detector cache invalidation) so firmware OTA can refresh `supports_*` flags including subwoofer.
- **ADR 018** — Client **`capabilities`** dict is the single source of truth for optional HTTP features; Home Assistant and architecture docs updated accordingly. **ADR 006–018** files are now under version control (several were referenced in the ADR index but absent from the tree in this branch).
- **Integration tests** — `test_subwoofer_capability_detection` and stricter **`test_capability_detection`** / **`test_player_subwoofer_read`** for real devices (unsupported path and `refresh_capabilities`).

### Changed
- **`supports_subwoofer`** — Set only during **`WiiMCapabilities.detect_capabilities()`** via **getSubLPF** probe (retries; `True` / `False` / `None` for inconclusive WiiM). **`StateManager`** no longer writes the flag on poll failure; it only refreshes cached status when support is not `False`, and may set **`True`** if capability was **`None`** and a valid status dict appears.
- **`Player.supports_subwoofer`** — **`True`** only when **`client.capabilities["supports_subwoofer"] is True`** (not truthy coercion for **`None`**).
- **`WiiMClient._detect_capabilities(force=...)`** / **`detect_capabilities(..., force=...)`** — Support forced re-detection.

### Fixed
- **`get_subwoofer_status` / `get_subwoofer_status_raw`** — Reject JSON **error** bodies (e.g. `{"error": "unsupported_command"}` on Arylic) so they do not become fake **`SubwooferStatus`** instances.

### Documentation
- **HA_INTEGRATION.md**, **HA_CAPABILITIES.md**, **API_REFERENCE.md**, **ARCHITECTURE.md**, **ARCHITECTURE_DATA_FLOW.md**, **API_DESIGN_PATTERNS.md**, **DESIGN_PRINCIPLES.md**, **design/README.md** — Capabilities-first integration guidance and ADR 018 links.

## [2.2.1] - 2026-04-20

### Fixed
- **mypy CI (`warn_unused_ignores`)** — `MediaControl.play_url`: removed dead `# type: ignore[arg-type]` (newer mypy narrows `enqueue` correctly) and replaced the `in ("add", "next")` branch with explicit **`add` / `next`** calls so older mypy still type-checks. Removed unused **`[[tool.mypy.overrides]]`** for `tests.*` (only `pywiim` is checked; that block triggered `warn_unused_configs`).

## [2.2.0] - 2026-04-20

### Added
- **`supports_channel_balance` capability** — Set at connect time for **WiiM devices only** via a read-only `getChannelBalance` probe (Arylic and other non-WiiM players stay `False` with no extra request). `Player.supports_channel_balance` mirrors `client.capabilities["supports_channel_balance"]` for integrations.
- **`Player.get_channel_balance()` / `Player.channel_balance`** — Read and cache stereo balance (HTTP only; no UPnP). **`refresh()`** refetches on the same **~60s** cadence as EQ info when supported. **`set_channel_balance`** updates the cache and notifies callbacks.
- **CLI** — `wiim-diagnostics` / `DeviceDiagnostics`: **Channel Balance** feature test, JSON report field `channel_balance`, and capability banner when supported. `wiim-verify` runs **`test_channel_balance`** (read-only `get_channel_balance`). `wiim-monitor` refreshes balance over HTTP on the same adaptive interval as EQ, shows balance in TUI and single-line status, and documents HTTP-only refresh in the startup banner.

### Documentation
- **`docs/testing/CURL_HTTPAPI.md`** — How to `curl` local WiiM/LinkPlay devices (HTTPS `-k`, read-only starter commands, pointers to [wiim#225](https://github.com/mjcumming/wiim/issues/225) / [wiim-httpapi](https://github.com/cvdlinden/wiim-httpapi/commits/main/openapi.md)). Linked from `docs/testing/REAL-DEVICE-TESTING.md`, `docs/README.md`, and `docs/development/DEVELOPMENT.md`.
- **Audio output HTTP reads** — `CURL_HTTPAPI.md` and [API_DESIGN_PATTERNS.md](docs/design/API_DESIGN_PATTERNS.md) now lead with **`getNewAudioOutputHardwareMode`** (WiiM), document **`getAudioOutputStatus`** as legacy (often `unknown command` on WiiM Pro), link [wiim#144](https://github.com/mjcumming/wiim/issues/144), and state that **`audiocast` in `getStatusEx` is not the same field/semantics as `audiocast` in the output-status JSON**.

## [2.1.98] - 2026-03-30

### Fixed
- **WiiM Ultra display brightness when turning screen on** ([mjcumming/wiim#213](https://github.com/mjcumming/wiim/issues/213)) - `setLightOperationBrightConfig` always includes `default_bright`; `set_display_enabled(True)` previously sent `default_bright: 1` (minimum). Default is now `DISPLAY_DEFAULT_BRIGHTNESS` (100 on a 1–100 scale). Added `DISPLAY_BRIGHTNESS_MIN`, `DISPLAY_BRIGHTNESS_MAX`, and `DISPLAY_DEFAULT_BRIGHTNESS` in `pywiim.api.constants`. Optional keyword `default_bright` on `set_display_enabled(..., *, default_bright=...)`.

### Changed
- **`set_display_config` default brightness** - Default `default_bright` is `DISPLAY_DEFAULT_BRIGHTNESS` instead of `1`.

### Documentation
- **API_REFERENCE / HA_INTEGRATION** - Clarify LCD (`setLightOperationBrightConfig`) vs LED indicator APIs; document optional display brightness when turning on.

## [2.1.97] - 2026-03-17

### Fixed
- **Dynamic EQ preset selection** - `set_eq_preset()` now resolves preset names against the device's current `eq_presets` list before falling back to the built-in preset map. This allows newer firmware labels such as "Vocal Booster" and user-defined custom preset names to be selected successfully from integrations while preserving existing built-in alias handling.

## [2.1.96] - 2026-03-12

### Added
- **Audio Pro RCA input and Link 2 source detection** (PR [#15](https://github.com/mjcumming/pywiim/pull/15)) - Audio Pro devices with non-standard model strings (e.g. Link 2: "LINK 2 Wireless multiroom HiFi player") were misidentified as `linkplay_generic` and showed `source=unknown` because HTTP `getStatusEx` returns `mode=0` when idle. Fixes: (1) **RCA input**: mode 44 → `"rca"` in MODE_MAP, SOURCE_CAPABILITIES, and UPnP PlaybackStorageMedium fallback for physical inputs (RCA, BLUETOOTH, LINE-IN, OPTICAL, COAXIAL, HDMI). (2) **Vendor/generation fallback**: firmware prefix `audiopro_` → `audio_pro` vendor; regex-based firmware version matching (1.56–1.60 → MkII, 2.0–2.3 → W-generation) avoids false positives. (3) **MkII source via UPnP**: `PROFILE_AUDIO_PRO_MKII` now uses `state_sources.source = "upnp"`; new `UpnpClient.get_control_device_info()` (RenderingControl:GetControlDeviceInfo) provides PlayMode when idle; statemgr polls it when profile prefers UPnP for source (gated when HTTP already has valid source). (4) **Device capability database**: confirmed physical inputs for Link 2, A28, ADDON C5 MkII. Vendor/generation detection consolidated in `profiles.py`; `capabilities` re-exports for existing API. Thanks to [dantheman2865](https://github.com/dantheman2865) for the contribution.

### Documentation
- **Merge verification checklist** - `docs/MERGE_VERIFICATION.md` documents steps to fetch a PR branch, run CI locally, and optionally run integration tests before merging.
- **DEVICE_PROFILES.md** - Audio Pro MkII profile now documents UPnP for `source` (in addition to play_state/volume/mute) when HTTP returns mode=0 idle.

## [2.1.95] - 2026-03-10

### Added
- **LED Indicator and Display APIs (ADR 005)** - Two distinct capabilities: **LED Indicator** (on/off) for Arylic + WiiM via `LED_SWITCH_SET`; **Display** (WiiM Ultra only) for LCD on/off and brightness. Player API: `get_led_indicator()` (reads state; assumes on if device has no read API), `set_led_indicator(enabled)`, `supports_led_indicator`; `set_display_enabled(enabled)`, `set_display_config(...)`. Client: `get_led_indicator()` tries getStatusEx and Arylic `getMCUASCIICmd:LED`; on read failure returns True and logs warning. Arylic: `supports_led_switch` set by vendor, `set_led_switch` try-and-ignore. Diagnostics CLI: LED Indicator and Display in feature tests and report. Docs: API_REFERENCE, HA_INTEGRATION, HA_CAPABILITIES. See ADR 005.

## [2.1.94] - 2026-03-10

### Changed
- **UPnP documentation** - Docs now match the code: `UpnpClient` is created with `await UpnpClient.create(host, description_url, session=None)` (description URL e.g. `http://<device_ip>:49152/description.xml`). Clarified that "state_manager" is only a parameter of `UpnpEventer`, not `UpnpClient`. Added user-facing "Creating and Using the UPnP Client" section in UPNP_INTEGRATION.md; fixed API_REFERENCE and HA_INTEGRATION examples and imports (`from pywiim.upnp import UpnpClient, UpnpEventer`).

## [2.1.93] - 2026-03-04

### Added
- **ApiResponse(parsed, raw)** - Base API now returns a consistent `ApiResponse(parsed, raw)` from `_request` / `_request_with_protocol_fallback`. JSON responses use `parsed`; non-JSON or empty body use `raw`. All API callers and unit tests updated to use `.parsed` / `.raw`. Documented in API_DESIGN_PATTERNS.

### Changed
- **Player.get_subwoofer_status()** - Now returns `SubwooferStatus` (attribute access: `.enabled`, `.crossover`, etc.) instead of raw dict; internal cache still uses raw keys for existing properties.

## [2.1.92] - 2026-03-03

### Added
- **`play_notification(url, force_interrupt=True)`** - Optional `force_interrupt` parameter always uses `play_url` so the notification is guaranteed audible (e.g. for TTS when the prompt path returns OK but produces no sound). Integration can use this to match LinkPlay-style behavior (interrupt playback, TTS heard, no resume).
- **`linkplay_radio` in source capabilities** - WiiM Home built-in radio (e.g. BBC) is now a known source with fallback path for notifications; `play_notification()` uses `play_url` for this source so TTS is heard when the prompt path is unreliable.
- **TTS troubleshooting and integration work list** - `HA_INTEGRATION.md`: "TTS announcements not working?" steps (resolve URL, use player not client, force_interrupt, device-reachable URL) and a checklist of integration tasks (resolve media_content_id, use player.play_notification, optional force_interrupt, release notes, YAML example, TTS proxy docs).

### Changed
- **Notification docs: firmware-dependent behavior** - README, HA_INTEGRATION, and API_REFERENCE no longer overclaim duck/resume for `playPromptUrl`. Document that prompt behavior is firmware- and source-dependent; fallback and `force_interrupt` ensure audible TTS when the prompt path is unreliable. Integration work list instructs not to claim "auto-resumes" in release notes.

## [2.1.91] - 2026-03-02

### Added
- **getDebugInfo API** - New `get_debug_info()` on the client (DiagnosticsAPI) calling the documented `getDebugInfo` endpoint. Returns raw device debug info (e.g. system_ready, slave_status, slave_latency, play_status, crash flags, upnp_action_*, wifi_abort_date) for diagnostics and troubleshooting. Diagnostics CLI: report includes `debug_info` and tests the endpoint; verify CLI: device info tests include `get_debug_info`. Optional endpoint; unsupported devices are reported as warnings in diagnostics.

## [2.1.90] - 2026-03-02

### Added
- **Optional track index for `play_preset()`** (GitHub [mjcumming/wiim#191](https://github.com/mjcumming/wiim/issues/191)) - `play_preset(preset, index=None)` now accepts an optional 1-based `index` to start playback at a specific track in the preset's playlist (e.g. `index=1` to start from the beginning). When omitted, behavior is unchanged (device resumes from last position). Sends `MCUKeyShortClick:preset:index` when index is provided. Documented in API_REFERENCE, HA_INTEGRATION, SOURCE_ENUMERATION.

## [2.1.89] - 2026-03-02

### Added
- **12V trigger support** (Issue [#13](https://github.com/mjcumming/pywiim/issues/13)) - API and player support for 12V trigger output on WiiM Ultra / Pro / Pro Plus: `get_trigger_out_status()`, `set_trigger_out(on)`, `set_trigger_out_on()`, `set_trigger_out_off()`, `player.supports_trigger_out`, `player.trigger_out_on`. Capability probed via `getTriggeroutStatus`. Documented in API_DESIGN_PATTERNS, HA_INTEGRATION, HA_CAPABILITIES.
- **CLI: 12V trigger and diagnostics** - Verify CLI: `test_trigger_out()` in feature test suite. Diagnostics: 12V Trigger and PEQ (Advanced EQ) feature tests and report sections; `getTriggeroutStatus` in endpoint list; subwoofer, PEQ, and trigger_out in `collect_diagnostic_data` output.
- **Monitor CLI: 12V trigger and subwoofer** - Live status shows "12V Trigger: ON/OFF" and "Subwoofer: On/Off, XXHz" when supported; trigger status fetched on same interval as audio output.

## [2.1.88] - 2026-02-28

### Added
- **Full PEQ (Parametric EQ) API** (PR [#12](https://github.com/mjcumming/pywiim/pull/12)) - New `PEQAPI` mixin and client support for the official WiiM LV2 PEQ system: 10-band per-source parametric EQ, stereo and L/R channel modes, preset save/load/delete/rename. Data models: `PEQBand`, `PEQSettings`, `PEQPresetInfo`. Capability `supports_peq` is probed at connect time; PEQ is only available on WiiM devices. Integration tests in `tests/integration/test_peq.py`; docs and integration guide updated. Thanks to [jeromeof](https://github.com/jeromeof) for the contribution.

## [2.1.87] - 2026-02-26

### Fixed
- **Chromecast input source reported as Bluetooth** (Issue [#6](https://github.com/mjcumming/pywiim/issues/6)) - When casting via Chromecast (e.g. BBC Sounds), the device can report mode=5 (Bluetooth). Parser now treats vendor "BBC Sounds", "BBC iPlayer", "BBC" as network and overrides source to wifi; if vendor is missing, artwork URL domains (bbci.co.uk, bbc.co.uk) are used to detect Chromecast/network and correct source to wifi.

## [2.1.86] - 2026-02-22

### Fixed
- **Lyrion position>duration log spam** (Issue [mjcumming/wiim#188](https://github.com/mjcumming/wiim/issues/188)) - "Impossible media position" for Lyrion (mode 34) is now logged at DEBUG instead of WARNING. Lyrion has a known firmware quirk with curpos/totlen; the parser already handles it by hiding duration. No user action needed.

## [2.1.85] - 2026-02-22

### Added
- **Friendly model naming** (Issue [mjcumming/wiim#11](https://github.com/mjcumming/wiim/issues/11)) - New `player.model_name` property provides branding-friendly names (e.g. "WiiM Pro", "Arylic S10+") while `player.model` retains raw project identifiers (e.g. `Muzo_Mini`, `WiiM_Amp_4layer`). New helper module `pywiim.model_names` with `is_known_wiim_model()` and `to_friendly_model_name()`.

### Fixed
- **WiiM vendor detection for legacy/raw model aliases** (Issue [mjcumming/wiim#10](https://github.com/mjcumming/wiim/issues/10)) - `Muzo_Mini` and other WiiM raw variants now correctly classify as `wiim` instead of `linkplay_generic`. Updated detection in `capabilities.py` and `profiles.py`.
- **Reduced wrong-device probe noise during discovery** (Issue [mjcumming/wiim#9](https://github.com/mjcumming/wiim/issues/9)) - `discover_devices()` now uses `is_likely_non_linkplay()` pre-filter before HTTP validation when `validate=True`, skipping obvious non-LinkPlay devices (Sonos, Chromecast, etc.) and keeping HTTP validation for ambiguous devices.

### Documentation
- `API_REFERENCE.md`: documents `player.model` (raw) and `player.model_name` (friendly).
- `README.md`: quick-start example prefers `player.model_name or player.model`.

## [2.1.84] - 2026-02-15

### Fixed
- **Position > duration log spam on Lyrion/LMS (mode 34)** (Issue [mjcumming/wiim#188](https://github.com/mjcumming/wiim/issues/188)) - WiiM Pro used as Lyrion endpoint reported odd curpos/totlen payloads causing "impossible media position" warnings on every poll and resetting position to 0. Parser now: (1) never resets position to 0, preferring to hide unreliable duration instead; (2) adds 2-second tolerance for small clock drift; (3) rate-limits warnings to once per track/source per 60 seconds; (4) maps mode 34 to "lyrion" in MODE_MAP.

## [2.1.83] - 2026-02-14

### Fixed
- **USB Out mode number corrected from 6 to 8** (Issue [mjcumming/wiim#160](https://github.com/mjcumming/wiim/issues/160)) - Real-world testing on a WiiM Ultra confirmed that USB Out is hardware mode 8, not mode 6 as documented in the WiiM API spec. Modes 5-7 all silently revert to mode 4 (headphones) on Ultra. Setting "USB Out" from Home Assistant now sends the correct mode and the device properly switches output.
- **HDMI Out removed from WiiM Ultra output list** - HDMI on WiiM Ultra is input-only, not output. Removed "HDMI Out" from `available_output_modes` for WiiM Ultra (HDMI Out remains available for WiiM Amp Ultra where it is a valid output).
- **Audio output capability probe order optimized** - Swapped probe order to try `getNewAudioOutputHardwareMode` first (works on all tested devices including WiiM Ultra), falling back to `getAudioOutputStatus` which returns "unknown command" on some devices.

## [2.1.82] - 2026-02-13

### Changed
- **Breaking: `player.source` now returns stable ids** - `player.source` now returns a canonical source id that matches `player.source_catalog[*]["id"]` (e.g., `"network"`, `"line_in"`, `"spotify"`), enabling clean round-tripping when storing catalog ids. The UI-ready display name is now available via `player.source_name` (e.g., `"Network"`, `"Line In"`, `"Spotify"`). `player.source_id` remains as an alias for `player.source`.
- **Source-aware `play_notification()` fallback with structured result** - `player.play_notification(url)` now chooses firmware-native `playPromptUrl` only on known native prompt sources and falls back to `play_url` on unsupported/unknown sources (including Spotify and AirPlay behavior validated on real devices), returning `NotificationPlaybackResult` with `method_used`, `source_before`, `likely_interrupted`, and optional `reason`.
- **UPnP description capability enrichment surfaced in diagnostics** - first-time capability detection now augments capabilities with best-effort UPnP `description.xml` metadata (`upnp_*` keys), and CLI diagnostics/verification output now includes these fields when available.

### Fixed
- **EQOff "unknown command" handling for scene restoration** (Issue [mjcumming/wiim#116](https://github.com/mjcumming/wiim/issues/116)) - Some devices (e.g. Arylic UP2STREAM) do not support the `EQOff` command and return plain text "unknown command" instead of JSON. Added `EQOff` to the non-JSON success-handling path so scene restoration with sound mode "Off" no longer fails with `Invalid JSON response`. The command is treated as best-effort (device does not support disabling EQ).

### Documentation
- Updated `API_REFERENCE.md` notification section with source-handling policy, fallback semantics, and `NotificationPlaybackResult` contract details.
- Added a README section documenting notification limitations, fallback behavior, and interruption expectations for unsupported sources.
- Updated diagnostics docs/API reference to document the new UPnP `description.xml` capability fields and where they appear.

## [2.1.80] - 2026-02-12

### Fixed
- **`timeSync` non-JSON/empty response handling** - Added `timeSync` to the non-JSON/empty-response success handling path so devices returning plain text or empty bodies no longer raise `WiiMResponseError` during `sync_time()`.
- **Version string drift in package runtime** - Updated `pywiim.__version__` to match the current release line and added release-time version synchronization between `pyproject.toml` and `pywiim/__init__.py` to prevent future mismatches.

## [2.1.79] - 2026-02-12

### Added
- **Structured source catalog API for integrations** - Added `player.source_catalog` to expose normalized source metadata for Music Assistant and similar integrations.
  - Each source now includes stable `id`, display `name`, `kind` (`hardware_input`, `service`, `virtual`), `selectable`, `is_current`, and per-source capability flags (`supports_pause`, `supports_seek`, `supports_next_track`, `supports_previous_track`, `supports_shuffle`, `supports_repeat`).
  - Added unit tests and real-device integration coverage for catalog shape and capability mapping.
- **Dedicated multiroom join/unjoin hardware test suite** - Added focused integration tests for real-device group transitions, including:
  - Per-slave join/leave validation against a configured master.
  - Pairwise join/unjoin matrix coverage across configured devices.
  - Full 3-player stress scenarios with all master/slave permutations and repeated join/leave churn, including real-time role snapshots.

### Changed
- **WiiM play-state source preference now UPnP-first** - Updated the WiiM profile to prefer UPnP for `play_state` (in addition to `volume` and `mute`) for faster UI responsiveness during playback transitions.
- **Profile-driven UPnP conflict resolution hardened** - Removed coarse `upnp_available` gating for UPnP-preferred fields in profile mode so fresh UPnP data is not incorrectly overridden by older HTTP polls between event bursts.
- **Group operations optimistic state updates expanded** - Improved local role/group responsiveness:
  - `join_group()` now applies optimistic local slave linking immediately after command success and rolls back if verification fails.
  - `leave_group()` callback signaling now fires on post-mutation state, ensuring integrations observe immediate solo/group role updates.

### Fixed
- **Audio output capability probing for USB Out devices** - Fixed a `pywiim` false-negative path where capability detection could disable `supports_audio_output` on WiiM devices and hide output options like **USB Out** (Issue [mjcumming/wiim#160](https://github.com/mjcumming/wiim/issues/160)).
  - Probe now prefers `getAudioOutputStatus`, falls back to legacy `getNewAudioOutputHardwareMode`, and keeps WiiM audio-output support enabled on probe failures.
  - Added regression tests for WiiM probe-failure behavior and legacy probe fallback.

## [2.1.77] - 2026-02-11

### Fixed
- **User-friendly WiiMConnectionError when device unreachable** - When protocol probe fails because the device is unreachable (connection refused, timeout, WSL2/firewall), pywiim now raises a clear "Device unreachable" message instead of "No working protocol/port found". Helps users distinguish connectivity issues from protocol configuration problems.

## [2.1.76] - 2026-02-11

### Fixed
- **Discovery protocol reporting now reflects validated transport** - Discovery results now show `https` when validation confirms API connectivity on HTTPS ports (443/4443/8443), avoiding stale protocol hints from SSDP metadata.
- **Discovery CLI filtering for validated devices** - Added `--validated-only` to `wiim-discover` to suppress unvalidated SSDP candidates and focus output on devices that pass API validation.
- **Chromecast source classification** - Corrected source mapping so Chromecast/Google Cast sessions no longer present as Bluetooth when devices report `mode=5`; these now map to network (`wifi`) source.
- **HTTP/UPnP volume conflict resolution for WiiM** - WiiM profile now prefers UPnP for `volume` and `mute`, so real-time UPnP events are not overridden by older-but-fresh HTTP poll values.
- **UPnP volume unit consistency** - RenderingControl volume events now use the same internal 0-100 scale as HTTP parsing, fixing incorrect values like `0.0016` from double normalization paths.

## [2.1.73] - 2026-02-10

### Added
- **MCP Server** - Expose WiiM/LinkPlay control as an [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server for Cursor, Claude Desktop, and other MCP hosts
  - Install with `pip install pywiim[mcp]`, run with `wiim-mcp` or `python -m pywiim.mcp`
  - Tools: wiim_discover, wiim_status, wiim_play, wiim_pause, wiim_media_play_pause, wiim_stop, wiim_next_track, wiim_previous_track, wiim_volume, wiim_mute, wiim_unmute, wiim_sources, wiim_set_source, wiim_play_url, wiim_group_join, wiim_group_leave
  - Config file support (`~/.config/wiim/config.json`) with `WIIM_CONFIG_FILE` override
  - `WIIM_DISCOVERY_DISABLED` for pre-configured devices (e.g. WSL where SSDP doesn't work)
  - `WIIM_TIMEOUT` for HTTP client timeout
  - Device targeting by name (fuzzy match) or IP
  - wiim_status now includes position, duration, and time left for current track

## [2.1.72] - 2026-02-03

### Fixed
- **URL encoding for `playPromptUrl` command** - Fixed `play_notification()`, `play_url()`, and `play_playlist()` to fully encode URLs (changed `safe=":/?&=#%"` to `safe=""`). WiiM's `playPromptUrl` and related commands require fully encoded URLs where characters like `:`, `/`, `?`, `&`, `=`, `#`, `%` must all be percent-encoded.

## [2.1.71] - 2026-01-31

### Documentation
- **HA integration: library/integration separation for `play_notification`** - Clarified in `HA_INTEGRATION.md` that `play_notification(url)` accepts only a URL the device can HTTP GET; the integration must resolve `media_content_id` (e.g. `media_source://tts?...`) to such a URL before calling the library
- Added library contract and "What the WiiM (HA) integration must do" (resolve before calling library, HA constants/patterns, ensure URL is fetchable by device)
- Reframed TTS 401/no-audio as integration and HA configuration concern, not library behaviour

## [2.1.70] - 2026-01-30

### Added
- **Automatic WiFi Direct multiroom linking** - pywiim now handles WiFi Direct multiroom **automatically without any integration changes**:
  - Added internal player registry (`PlayerBase._all_instances`) that tracks all Player objects
  - `_find_slave_player()` and `_check_if_slave_of_any_master()` now automatically search this registry by UUID
  - **No `all_players_finder` callback needed** - pywiim handles everything internally
  - This fixes Issue [mjcumming/wiim#178](https://github.com/mjcumming/wiim/issues/178) without requiring HA integration changes

- **Multiroom diagnostics method** - Added `player.get_multiroom_diagnostics()` to help debug WiFi Direct multiroom linking issues:
  - Returns comprehensive information about device identity, callbacks, linked players, and raw API state
  - Automatically analyzes potential linking issues (missing UUIDs, WiFi Direct detection)
  - Provides actionable recommendations for fixing linking problems

### Changed
- **Enhanced multiroom linking logging** - Added detailed debug logging to `_find_slave_player()` and `_check_if_slave_of_any_master()`:
  - Logs all lookup attempts (IP, UUID via player_finder, UUID via internal registry)
  - Shows UUID comparison details when matches fail (normalized values for both)
  - Identifies when players don't have UUIDs populated (need full refresh)
  - Makes it clear when WiFi Direct multiroom linking fails and why

## [2.1.69] - 2026-01-29

### Fixed
- **WiFi Direct multiroom slave linking** (Issue [mjcumming/wiim#178](https://github.com/mjcumming/wiim/issues/178)) - Fixed slave linking for legacy LinkPlay devices (e.g., Xoro XVS 100) that use WiFi Direct multiroom:
  - Slaves join master's internal WiFi Direct network and get 10.10.10.x IPs
  - Master's `getSlaveList` returns these internal IPs (unknown to HA) but includes UUIDs
  - Added third fallback in `_find_slave_player()`: searches `all_players_finder()` results by UUID
  - **No integration changes required** - pywiim now handles UUID matching internally when `all_players_finder` is provided
  - This fixes `group_members` showing incomplete data for WiFi Direct groups

### Documentation
- Updated `HA_INTEGRATION.md` with complete `_get_all_players()` implementation example
- Clarified that `all_players_finder` is **required** for WiFi Direct multiroom support
- Updated `API_REFERENCE.md` to explain the UUID search fallback mechanism

## [2.1.68] - 2026-01-28

### Fixed
- **USB Out support for WiiM Amp devices** - Fixed model detection order so WiiM Amp, Amp Pro, and Amp Ultra now properly show USB Out in available output modes
  - Previously, "WiiM Amp Ultra" and "WiiM Amp Pro" were incorrectly matched as "WiiM Amp" (only Line Out)
  - Now all Amp variants correctly support USB Out for external USB DAC output
  - WiiM Amp Ultra also gets HDMI Out
  - Fixed diagnostics CLI to match Player logic

## [2.1.67] - 2026-01-28

### Changed
- **CI coverage enforcement** - CI now fails if coverage drops below 55%
- **Local release checks** - `make check` and `make release` now verify coverage threshold before allowing releases

## [2.1.66] - 2026-01-28

### Added
- **Additional test coverage** - Added integration tests for cross-coordinator role inference

## [2.1.65] - 2026-01-28

### Fixed
- **Code formatting** - Applied Black formatting to ensure CI passes

## [2.1.64] - 2026-01-28

### Added
- **Cross-coordinator role inference for WiFi Direct multiroom** (Issue [mjcumming/wiim#164](https://github.com/mjcumming/wiim/issues/164)): Added `all_players_finder` callback to fix WiFi Direct slave role detection:
  - WiFi Direct slaves report `group="0"` (solo) when queried directly because they don't know they're in a group
  - Only the master knows the group membership via `getSlaveList`
  - New `all_players_finder` callback enables pywiim to check if any known master lists this device as a slave
  - When a device reports "solo" but is found in a master's slave list (by UUID), pywiim correctly infers "slave" role
  - **HA Integration required change**: Add `all_players_finder=lambda: list(player_registry.values())` when creating Player objects
  - This completes the WiFi Direct multiroom fix started in v2.1.60 (UUID-based slave matching)

## [2.1.63] - 2026-01-28

### Added
- **Subwoofer Control API** ([Issue #2](https://github.com/mjcumming/pywiim/issues/2)): Added undocumented API endpoints for subwoofer configuration (WiiM devices only - tested on Pro and Ultra, not supported on Arylic).
  - `get_subwoofer_status()` - Get current subwoofer configuration as `SubwooferStatus` dataclass
  - `set_subwoofer_enabled(enabled)` - Enable/disable subwoofer output
  - `set_subwoofer_crossover(frequency)` - Set crossover frequency (30-250 Hz)
  - `set_subwoofer_phase(phase)` - Set phase (0 or 180 degrees)
  - `set_subwoofer_level(level)` - Set level adjustment (-15 to +15 dB)
  - `set_main_speaker_bass(enabled)` - Enable/disable bass to main speakers
  - `set_subwoofer_filter(enabled)` - Enable/disable subwoofer low-pass filter (bypass mode)
  - `set_subwoofer_delay(delay_ms)` - Set delay adjustment (-200 to +200 ms)
  - `is_subwoofer_supported()` - Check if device supports subwoofer control
  - `is_subwoofer_connected()` - Check if subwoofer is physically connected
  - New constants: `SUBWOOFER_CROSSOVER_MIN/MAX`, `SUBWOOFER_LEVEL_MIN/MAX`, `SUBWOOFER_DELAY_MIN/MAX`, `SUBWOOFER_PHASE_0/180`
- **CLI Subwoofer Testing**: Added subwoofer tests to `wiim-verify` and `wiim-diagnostics` CLI tools
- **Integration Tests**: Added subwoofer integration tests in `tests/integration/test_real_device.py`

## [2.1.62] - 2026-01-28

### Fixed
- **Audio Pro Reboot Command (Issue [mjcumming/wiim#177](https://github.com/mjcumming/wiim/issues/177))**: Fixed reboot not working on Audio Pro speakers.
  - Audio Pro devices require `StartRebootTime:0` instead of standard `Reboot` command.
  - Added `reboot_command` to device profiles with device-specific commands.
  - Reboot command is now read from capabilities, following the established Strategy Pattern.

### Removed
- **Removed unused `supports_enhanced_grouping` capability**: This flag was never used in any logic - multiroom grouping relies on `wmrm_version` instead. Cleaned up from profiles, capabilities, and player properties.

## [2.1.61] - 2026-01-02

### Fixed
- **Audio Pro C10 MkII Source Selection (Issue [mjcumming/wiim#167](https://github.com/mjcumming/wiim/issues/167))**: Fixed RCA input not being selectable or working.
  - Added `rca` to known physical inputs to prevent it being filtered out of the source list.
  - Implemented specific `RCA` (uppercase) normalization for API commands as required by Audio Pro firmware.
  - Strengthened smart fallback to respect device-reported input names when standard mappings fail.

## [2.1.60] - 2025-12-28

### Added
- **EQ "Off" sound mode option** (Issue [mjcumming/wiim#165](https://github.com/mjcumming/wiim/issues/165)) - Added ability to disable EQ entirely via sound mode selection:
  - `eq_preset` property now returns `"Off"` when EQ is disabled (bypassed), instead of showing the last-used preset
  - `eq_presets` list now includes `"Off"` as the first option (e.g., `["Off", "Flat", "Rock", ...]`)
  - `set_eq_preset("Off")` disables EQ entirely (audio bypass mode)
  - Selecting any other preset when EQ is off automatically enables EQ first
  - EQ enabled/disabled status is now cached and refreshed periodically (every 60s)
  - Home Assistant integration now correctly reflects EQ off state in `sound_mode` attribute
- **UUID-based slave matching for WiFi Direct multiroom** (Issue [mjcumming/wiim#164](https://github.com/mjcumming/wiim/issues/164)) - Added support for older LinkPlay devices (e.g., Xoro HCN_BWD03) that use WiFi Direct multiroom:
  - Added `slave_uuids` field to `DeviceGroupInfo` model for UUID-based slave identification
  - `get_device_group_info()` now populates both `slave_hosts` (IPs) and `slave_uuids` (UUIDs)
  - Group operations now use UUID fallback when IP-based player matching fails
  - Enables linking slaves that use internal 10.10.10.x IPs (WiFi Direct) by matching their UUID
  - **HA Integration required change**: `player_finder` callback should also accept UUID lookups (see docs)

### Documentation
- Updated HA_INTEGRATION.md with `async_select_sound_mode()` example and "Off" option documentation

## [2.1.59] - 2025-12-26

### Fixed
- **Source Selection Resilience (Issue #161)**: Fixed physical source selection failure caused by "In" suffix mismatch in recent standardization.
  - Implemented **Smart Normalization**: `set_source()` now uses alphanumeric matching against the device's own reported `InputList` to find the correct command format.
  - Added explicit mappings for common variations: "Optical In" → `optical`, "Coaxial In" → `coaxial`, etc.
  - Reverted "In" suffix for **Coaxial**, **HDMI**, **Phono**, and **USB** display names to stop UI churn and preserve Home Assistant automation stability (ADR 001).
- **Source Selection Logic**: Improved source normalization to handle mixed case, underscores, and hyphens more robustly.

### Added
- **ADR 001: Source Naming Stability**: Formalized decision to lock hardware source display names and use smart normalization for API compatibility.
- **Regression Tests**: Added unit and integration tests covering standardized source naming and device-specific command mapping.

## [2.1.58] - 2025-12-23

### Added
- **USB Output support for WiiM Ultra** - Added hardware output mode 6 for external DAC support (Issue #160):
  - Added `AUDIO_OUTPUT_MODE_USB_OUT = 6` constant and mapping.
  - Included "USB Out" in `available_output_modes` for WiiM Ultra models.
  - Updated selection logic to support switching to USB output by name.
- **"Thin Integration" Source Overhaul** - Centralized device-specific source abstraction and UI-ready formatting in the library:
  - **Model-Specific Filtering**: Authoritative hardware filtering using `device_capabilities.py` (e.g., hiding USB on WiiM Pro, hiding Coaxial on Pro Plus).
  - **Unified "Network" Source**: Standardized all WiFi/Ethernet variations into a single "Network" source for UI stability and consistency.
  - **"UI Master" Formatting**: Source names are now returned ready for display:
    - Proper acronym capitalization (`USB`, `HDMI`, `DLNA`, `SPDIF`, `RCA`).
    - Title Case enforcement with "In" suffixes for physical inputs (e.g., "Optical In", "Line In").
    - Typo fixes at the library level (e.g., "CoaxIal" → "Coaxial").
  - **Highly Resilient `set_source`**: Accepts Title Case, underscores, hyphens, or no-space variants and maps them to the correct API command.
  - **Essential Source Injection**: "Network" is now always present in `available_sources`, providing a consistent way to return to streaming mode from physical inputs.
  - **Match Guarantee**: `player.source` is guaranteed to match an entry in `player.available_sources` for reliable UI selection highlighting.
  - **WiiM Sound Support**: Added hardware profile for the new WiiM Sound model with correct input filtering.
- **WiFi Direct multiroom unjoin support** - Fixed unjoin not working for old Linkplay devices (firmware < 4.2.8020):
  - Old Linkplay devices (Xoro, Medion, etc.) use WiFi Direct mode where slaves move to internal 10.10.10.x network
  - Slaves become unreachable from LAN, so direct `Ungroup` command fails
  - `leave_group()` now detects WiFi Direct mode and routes unjoin through the master using `SlaveKickout`
  - Matches slave by UUID in master's slave list to find the 10.10.10.x IP
  - Falls back to direct `Ungroup` if master kick fails
  - Added `get_slaves_info()` API method to get full slave data including UUIDs

### Fixed
- **UPnP health tracking robustness** (Issue #157) - Improved handling of transient metadata changes and mode transitions:
  - Relaxed `UpnpHealthTracker` to ignore metadata changes to "Unknown" or empty values, common during source switches.
  - Increased `min_samples` from 3 to 10 to require more sustained failure before marking UPnP as degraded.
  - Optimized `StateManager` to skip UPnP control calls (`GetVolume`, `GetMute`) when eventing is unhealthy, preventing device overload and disconnects during mode transitions.
- **Artwork fallback logic** - Fixed pre-existing unit test failures where artwork fallbacks were being handled inconsistently between the parser and the player property.

## [2.1.57] - 2025-12-17

### Fixed
- **Source selection not working for Line In** - Fixed GitHub issue #153 where selecting "Line In" via Home Assistant silently did nothing:
  - API normalization now correctly uses hyphens (`line-in`) instead of underscores (`line_in`) for the WiiM `switchmode` command
  - Fixed all physical input sources: "Line In" → `line-in`, "Line In 2" → `line-in-2`, "Wi-Fi" → `wifi`, etc.
  - Fixed "CoaxIal" capitalization - now displays as "Coaxial" in source list
  - All source name variants (spaces, underscores, hyphens) now correctly normalize to the API-expected format

### Added
- **Integration tests for source selection** - Added `tests/integration/test_source_selection.py` with real-device tests:
  - Verifies correct API format is sent to device (catches `line_in` vs `line-in` bugs)
  - Tests source name display formatting (catches "CoaxIal" capitalization issues)
  - Tests actual source selection roundtrip on real hardware
- **Testing requirements in .cursorrules** - Added explicit rule requiring tests for new code to prevent similar issues

## [2.1.56] - 2025-12-15

### Fixed
- **Source list capitalization and selection issues** - Fixed multiple source-related issues reported in GitHub issue #153:
  - `available_sources` now returns Title Case format (e.g., "Line In", "Bluetooth") to match `source` property, fixing Home Assistant validation failures
  - Added source name normalization in `set_source()` to handle variations ("Line In", "Line-in", "line_in", "linein" → "line_in")
  - Fixed USB filtering for WiiM Pro Plus - added `ignore_plm_bits=[2]` to prevent incorrect USB input from appearing
  - Included WiFi/Ethernet as selectable source (user can switch to network mode)
  - Fixed capitalization for streaming services: "TuneIn" and "iHeartRadio" now display correctly
  - All source names now consistently normalized for both display (Title Case) and API calls (lowercase with underscores)
- **Playlist clearing reliability** - Fixed `clear_playlist()` not working on some devices (Audio Pro C5MkII, etc.) by adding UPnP PlayQueue service support:
  - `clear_playlist()` now uses UPnP PlayQueue `DeleteQueue` action when available (more reliable than HTTP API on some devices)
  - Falls back to HTTP API `setPlayerCmd:clear_playlist` if UPnP PlayQueue service is not available or fails
  - PlayQueue service is automatically discovered during UPnP initialization (optional, LinkPlay-specific service)
  - Addresses GitHub issue #154 where HTTP API `clear_playlist` command doesn't work on some devices
- **HCN_BWD03 slave device status timeout** - Fixed slave devices timing out when fetching status in multiroom mode:
  - Added timeout fallback for HCN_BWD03 slave devices that timeout on `getPlayerStatus` in multiroom mode
  - Automatically falls back to `getStatusEx` for HCN_BWD03 devices when `getPlayerStatus` times out
  - Other devices continue to use `getPlayerStatus` and will raise timeout errors normally
  - Ensures slave devices can refresh status even when master device is controlling playback

## [2.1.55] - 2025-12-14

### Fixed
- **Python 3.13 SSL blocking operations** - Fixed blocking SSL context creation in event loop by wrapping all SSL context creation in `asyncio.to_thread()`:
  - `discovery.py`: `ssl.create_default_context()` now runs in executor thread
  - `upnp/client.py`: `ssl.SSLContext()` creation now runs in executor thread (2 locations)
  - `api/ssl.py`: SSL context creation already properly wrapped via helper function
  - Prevents Home Assistant warnings about blocking calls to `load_default_certs()` and `set_default_verify_paths()` in Python 3.13
  - No functional changes - SSL behavior is identical, just non-blocking

## [2.1.54] - 2025-12-14

### Fixed
- **Documentation completeness** - Fixed missing capability properties in API and HA integration guides:
  - API_REFERENCE.md: Added all 17 capability properties (was missing 11 capabilities)
  - HA_CAPABILITIES.md: Added missing `supports_seek` capability
  - Organized capabilities into clear categories (HTTP API, UPnP, Transport)
  - Added cross-references between documentation files
- **Documentation maintenance rule** - Added mandatory rule to `.cursorrules` requiring documentation updates when API changes are made

### Added
- **Preset data availability capability** - Added `presets_full_data` capability to distinguish between WiiM devices (full preset data) and LinkPlay devices (count only):
  - `player.presets_full_data` - Boolean property indicating whether preset names/URLs are available
  - WiiM devices: `presets_full_data = True` - Can read preset names, URLs, and cover art via `getPresetInfo`
  - LinkPlay devices: `presets_full_data = False` - Only preset count available via `preset_key`, names not accessible
  - Enables integrations to handle both device types correctly (show preset names for WiiM, play by number for LinkPlay)
- **Preset documentation updates** - Enhanced documentation to cover preset usage:
  - API Reference: Added "Playback Presets" section with device-specific examples
  - HA Integration Guide: Added "Using Playback Presets" section with coordinator data examples
  - HA Capabilities Guide: Added `presets_full_data` to capabilities table
- **Preset capability tests** - Added comprehensive test coverage:
  - Unit tests for capability detection (WiiM vs LinkPlay vs no presets)
  - Unit tests for Player property access
  - Integration tests for real device preset reading and playback
  - CLI tools (diagnostics, verify) now display preset capability information
- **UPnP verbose event logging in monitor CLI** - Added `--upnp-verbose` flag to `wiim-monitor` to display full UPnP event JSON/XML data for debugging and analysis. When enabled, shows complete event payload including all state variables and their values in formatted JSON format.
- **Firmware update metadata and installation** - Exposed firmware update information from `getStatusEx` as part of `device_info`:
  - `player.device_info.version_update` - Raw `VersionUpdate` field (string, "1" = update available)
  - `player.device_info.latest_version` - Raw `NewVer` field (latest firmware version string)
  - `player.firmware_update_available` - Boolean convenience property (True if update is ready)
  - `player.latest_firmware_version` - String convenience property (latest version or None)
  - `player.supports_firmware_install` - Boolean capability property (True for WiiM devices only)
- **WiiM-specific firmware update installation** - Added API methods for installing firmware updates on WiiM devices:
  - `player.check_for_updates_wiim()` - Check for available updates using `getMvRemoteUpdateStartCheck`
  - `player.install_firmware_update()` - Download and install firmware update automatically (WARNING: Do not power off during process)
  - `player.get_update_download_status()` - Get download progress and status
  - `player.get_update_install_status()` - Get installation progress (0-100%)
- **Firmware update capability detection** - Added `supports_firmware_install` capability flag (True for WiiM devices, False for others)
- **Firmware update documentation** - Added comprehensive documentation:
  - API Reference: Firmware update section with usage examples
  - HA Integration Guide: Complete `UpdateEntity` implementation example
- **Firmware update tests** - Added comprehensive test coverage:
  - Unit tests for all firmware update methods and capability checks
  - Integration tests for real-world firmware update scenarios
  - Standalone test script (`scripts/test_firmware_update.py`) for manual testing

### Notes
- Firmware update installation is **only available on WiiM devices** - other devices require manual reboot after update is downloaded
- For non-WiiM devices, use `player.reboot()` after an update is available and downloaded
- Installation process can take several minutes - device will reboot automatically when complete
- **Preset data availability**: WiiM devices support reading preset names/URLs via `getPresetInfo`, while LinkPlay devices only expose preset count via `preset_key`. Use `player.presets_full_data` to determine which approach to use in integrations.

## [2.1.52] - 2025-12-13

### Fixed
- **Slave device status endpoint** - Changed slave devices to use capability-configured status endpoint (`get_player_status()`) instead of hardcoded `get_status()` (which calls `getStatusEx`). This ensures slaves use the same capability-driven endpoint selection as masters, improving consistency and device compatibility. Fixes issue [#145](https://github.com/mjcumming/wiim/issues/145) where HCN_BWD03 devices failed to get status in multiroom mode because `getStatusEx` returns system info instead of player status - slaves now correctly use `getPlayerStatus` via capability detection.

## [2.1.51] - 2025-12-08

### Fixed
- **Non-blocking UPnP initialization** - UPnP client creation no longer blocks initial player refresh for 5+ seconds on slow-responding devices. Creation now happens in background with automatic retry every 60 seconds until successful.
- **Source name case-sensitivity in tests** - Fixed integration test assertions to use case-insensitive comparison for source names (device returns lowercase, UI displays title case)

### Added
- **UPnP debug script** - Added `scripts/debug/test_upnp_support.py` to test UPnP connectivity across all configured devices
- **Group edge case tests** - Added integration tests for group edge cases: slave leave/rejoin, group dissolution, solo+solo→group, and slave migration to different group
- **Friendly source name for URL playback** - `custompushurl` (raw API value when playing via `play_url()`) now displays as "URL Stream"

## [2.1.50] - 2025-12-07

### Fixed
- **Gen 1 device multiroom grouping attempt** - Simplified WiFi Direct mode detection to use firmware version (< 4.2.8020) instead of unreliable wmrm_version field. Removed broken compatibility checks that were preventing Gen 1 devices from joining groups.
- **Improved slave device role detection** - Fixed master IP detection by also checking the `multiroom` section of status response, which some devices use exclusively
- **Better status endpoint selection for legacy devices** - Added `getPlayerStatus` as fallback for devices (e.g., HCN_BWD03) where `getPlayerStatusEx` isn't supported and `getStatusEx` returns system info instead of player status

### Changed
- **Faster integration tests** - Removed unnecessary 5-second observation waits from multiroom group tests (saves ~60 seconds per test run)
- **Cleaner multiroom mode detection** - Moved `needs_wifi_direct_multiroom` property to `DeviceInfo` model for better encapsulation

## [2.1.49] - 2025-12-07

### Fixed
- **Device discovery now uses HTTP probe as definitive filter** (Issue [mjcumming/wiim#141](https://github.com/mjcumming/wiim/issues/141))
  - Removed unreliable SSDP header filtering that was missing Samsung TVs and Sonos devices
  - All discovered devices are now probed via HTTP to check LinkPlay API compatibility
  - Non-LinkPlay devices (Samsung TV, Sonos, etc.) are filtered out during validation
  - Matches velleman linkplay library approach: probe every device, don't rely on SSDP headers
  - This prevents non-WIIM devices from being discovered and causing integration errors

## [2.1.48] - 2025-12-07

### Fixed
- **Remove unused import** - Fixed ruff lint error (unused `WiiMResponseError` import in capabilities.py)
- **Updated test expectations for read-only probing** - Tests now correctly expect `supports_eq = True` when EQ can be read (matches new capability detection behavior)
- **Suppressed unclosed session warnings** - Added pytest filterwarnings to suppress harmless ResourceWarnings from mock aiohttp sessions

### Changed
- **Added `make release` workflow** - New Makefile target that:
  - Runs all CI checks (isort, ruff, mypy, pytest) before pushing
  - Automatically commits uncommitted changes
  - Creates and pushes release tag
  - Prevents lint/test failures from reaching CI
- **Added pytest-xdist for parallel test execution** - Tests now run in parallel locally (2+ min → ~30 seconds)
- **Improved mock session fixture** - Better cleanup to prevent resource warnings

## [2.1.47] - 2025-12-07

### Fixed
- **Capability detection no longer changes device settings** (Issue [mjcumming/wiim#144](https://github.com/mjcumming/wiim/issues/144))
  - Audio output mode was being changed to Line Out during initialization
  - EQ preset was being changed to Flat during initialization
  - Now uses read-only probing: if we can read a setting, we assume we can set it
  - This prevents unintended changes to user's audio output and EQ settings on HA restart or integration reload

## [2.1.46] - 2025-12-06

### Changed
- **Consolidated test infrastructure** - Simplified and unified real-device testing:
  - All tests now use pytest with tier markers (`smoke`, `playback`, `controls`, `features`, `groups`)
  - Single configuration file: `tests/devices.yaml` (replaces multiple configs)
  - Automatic test report tracking: `tests/test_reports.json` shows last run status per tier
  - Removed deprecated `scripts/run_tests.py` (1,547 lines) and `scripts/groups/` directory
  - Environment variables can still override config for CI flexibility

### Added
- **Test tier markers for selective testing**:
  - `pytest -m smoke` - Basic connectivity (any device state)
  - `pytest -m playback` - Play/pause/next/prev (requires media)
  - `pytest -m controls` - Shuffle/repeat (requires album/playlist)
  - `pytest -m features` - EQ, presets, outputs
  - `pytest -m groups` - Multi-room tests (requires 2+ devices)
- **Test result tracking** - Integration tests auto-save results to JSON for pre-release checks

### Documentation
- Updated `tests/README.md` with new testing workflow and tier system
- Updated `scripts/README.md` to point to pytest-based testing

## [2.1.45] - 2025-12-06

### Added
- **Group media properties** - Added convenience properties to `Group` class for accessing master's media state:
  - `group.media_title` - Master's media title
  - `group.media_artist` - Master's media artist
  - `group.media_album` - Master's media album
  - `group.media_position` - Master's media position (seconds)
  - `group.media_duration` - Master's media duration (seconds)
  - These delegate to master's cached state, consistent with existing `group.play_state`

### Fixed
- **Immediate role detection on group changes** - `player._detected_role` now updates immediately when:
  - `add_slave()` is called (master becomes "master", slave becomes "slave")
  - `remove_slave()` is called (slave becomes "solo", master becomes "solo" if no slaves remain)
  - `disband()` is called (master becomes "solo")
  - This ensures `is_solo`, `is_master`, `is_slave` properties work immediately after group operations

### Documentation
- Updated `API_REFERENCE.md` with new Group media properties
- Updated `HA_INTEGRATION.md` virtual entity examples to use `group.media_*` properties

## [2.1.44] - 2025-12-04

### Fixed
- **`join_group()` now handles "already in group" gracefully** - Made group operations idempotent to handle race conditions:
  - If player is already in target group → returns success (no-op)
  - If player is in a different group → automatically leaves first, then joins
  - `add_slave()` similarly handles moving slaves between groups without errors
  - Eliminates sporadic "Player X is already in a group" errors during group operations

## [2.1.43] - 2025-12-04

### Fixed
- **EQ preset and shuffle/repeat state preservation during refresh** - Fixed issue where `refresh()` would overwrite optimistic EQ preset and loop_mode (shuffle/repeat) updates with stale data from the device status endpoint. The device's `getPlayerStatus` returns stale EQ data for several minutes after a change. Now:
  - `set_eq_preset()` verifies the change with `get_eq()` (authoritative endpoint) after a 300ms delay
  - Optimistic EQ preset updates are preserved for 60 seconds during `refresh()` calls
  - Optimistic loop_mode updates from `set_shuffle()`/`set_repeat()` are similarly preserved for 60 seconds
  - This prevents the UI from flickering back to old values after changing EQ or shuffle/repeat

### Added
- **Unified test runner** - New `scripts/run_tests.py` for comprehensive real-device testing with tiered test suites:
  - **Tier 1 (Smoke)**: 8 tests - connectivity, volume, mute, state properties
  - **Tier 2 (Playback)**: 5 tests - play/pause/resume, next/previous track
  - **Tier 3 (Controls)**: 5 tests - shuffle toggle, repeat modes, state preservation
  - **Tier 4 (Features)**: 5 tests - EQ presets, audio outputs, favorites
  - **Tier 5 (Groups)**: 9 tests - group creation, metadata propagation, volume/mute sync, command routing
  - Colorful real-time output with test progress and results
  - Device configuration via `scripts/test_devices.yaml`
  - Pre-release validation: `python scripts/run_tests.py --prerelease --device IP --yes`

### Changed
- **Reorganized test scripts** - Cleaned up `scripts/` directory:
  - Removed 13 redundant test scripts now covered by unified runner
  - Moved interactive tests to `scripts/manual/`
  - Moved group tests to `scripts/groups/`
  - Added comprehensive README documentation

### Documentation
- **Shuffle/repeat testing requirements** - Updated `docs/design/SHUFFLE_REPEAT_SUPPORT.md` with critical documentation about content-type requirements for testing:
  - Spotify albums/playlists support shuffle/repeat, but radio stations/Daily Mix do not
  - Added guidance for interpreting test results and distinguishing real bugs from expected content-type limitations

## [2.1.42] - 2025-12-04

### Fixed
- **EQ preset normalization** - `player.eq_preset` now returns Title Case (e.g., "Flat", "Acoustic") to match the format from `get_eq_presets()`, ensuring consistency between the current preset and available presets list.

### Changed
- **Source name normalization** - `player.source` now returns Title Case for consistent UI display (e.g., "AirPlay", "Spotify", "Line In", "Bluetooth", "WiFi"). This ensures professional casing in Home Assistant's UI while maintaining case-insensitive comparisons for capability checks.

## [2.1.41] - 2025-12-04

### Fixed
- Re-release of v2.1.39 with correct package (PyPI had incorrect package from initial release attempt)

## [2.1.39] - 2025-12-04


### Added
- **Play state debouncing** - New `PlayStateDebouncer` class to smooth track changes:
  - Delays applying pause/stop states during track transitions
  - Prevents false "stopped" states when devices briefly report STOPPED between tracks
  - Automatically cancels delayed states if playback resumes quickly (indicating track change, not pause)
  
- **Stream metadata enrichment** - New `StreamEnricher` class for raw URL playback:
  - Automatically fetches and applies metadata from Icecast, M3U, and PLS streams
  - Replaces raw URLs in title field with parsed artist/title metadata
  - Caches metadata to avoid repeated fetches for the same stream
  - Works with WiFi/URL source playback

- **Enhanced cover art management**:
  - Track change detection based on title/artist/album signature
  - Automatic metadata enrichment on track changes when artwork is missing
  - Handles "Unknown" metadata cases (e.g., Bluetooth AVRCP) by fetching from getMetaInfo endpoint

- **Group operations improvements**:
  - `get_master_name()` method to retrieve master device name from group or master IP
  - `propagate_metadata_to_slaves()` method to synchronize playback metadata from master to all slaves
  - Ensures slaves always have latest metadata even when master's metadata changes via UPnP

### Changed
- **State manager refactoring**:
  - Significant code cleanup and simplification (reduced complexity)
  - Better separation of concerns with dedicated debounce and enrichment modules
  - Improved track change detection and handling

### Fixed
- Track changes no longer cause false "stopped" or "paused" states
- Raw stream URLs now show proper metadata instead of URLs in title field
- Group slaves now properly receive metadata updates from master

## [2.1.38] - 2025-12-03

### Added
- **Device Profiles System** - Centralized device-specific behaviors in `pywiim/profiles.py`:
  - `DeviceProfile` dataclass defines all device-specific settings in one place
  - Pre-defined profiles for WiiM, Arylic, Audio Pro (MkII, W-Generation, Original), and generic LinkPlay
  - `get_device_profile(device_info)` auto-detects the appropriate profile
  - `StateSourceConfig` defines which source (HTTP vs UPnP) is authoritative per field
  - `ConnectionConfig`, `EndpointConfig`, `GroupingConfig` for other device-specific settings

- **Profile-Driven State Management**:
  - `StateSynchronizer` now accepts an optional `DeviceProfile`
  - When profile is set, uses explicit source selection instead of guessing
  - Audio Pro MkII automatically uses UPnP for play_state/volume (HTTP doesn't provide them)
  - WiiM/Arylic use HTTP for all state (as before)
  - Eliminates "which source do I trust?" bugs

- **Player Profile Integration**:
  - `player.profile` property exposes the detected device profile
  - Profile auto-detected on first refresh when `device_info` becomes available
  - Profile automatically set on `StateSynchronizer`

### Documentation
- Added `docs/design/DEVICE_PROFILES.md`:
  - Explains why profiles were created (fix one thing, break another pattern)
  - Documents profile architecture and components
  - Lists current integration status (what's done vs pending)
  - Provides migration guide for future work
  - Instructions for adding new device types

## [2.1.37] - 2025-12-03

### Added
- **Playback state properties** for cleaner integration code:
  - `is_playing` - True when device is playing (includes buffering/loading states)
  - `is_paused` - True when device is paused (includes normalized "stop" state)
  - `is_idle` - True when device is idle (no media loaded)
  - `is_buffering` - True when device is loading/buffering media
  - `state` - Normalized state string: `"playing"`, `"paused"`, `"idle"`, or `"buffering"`
  
- These properties eliminate the need to parse raw `play_state` strings:
  ```python
  # Before (parsing strings)
  if player.play_state in ("play", "playing", "buffering", ...):
      return MediaPlayerState.PLAYING
  
  # After (clean property access)
  STATE_MAP = {
      "playing": MediaPlayerState.PLAYING,
      "paused": MediaPlayerState.PAUSED,
      "idle": MediaPlayerState.IDLE,
      "buffering": MediaPlayerState.BUFFERING,
  }
  return STATE_MAP[player.state]
  ```

- **Safe property accessors** for simpler HA integration code:
  - `player.discovered_endpoint` - Exposes `client.discovered_endpoint` at player level
  - `player.input_list` - Returns `[]` instead of `None` when device info unavailable
  - `player.group_master_name` - Safe accessor for `player.group.master.name` chain

### Changed
- **`available_sources` now returns `list[str]` instead of `list[str] | None`**
  - Returns empty list `[]` when device info is unavailable (eliminates None checks)
- **`eq_presets` now returns `list[str]` instead of `list[str] | None`**
  - Returns empty list `[]` when presets not available (eliminates None checks)

### Documentation
- Updated `HA_CAPABILITIES.md` with new playback state properties section
- Added usage examples showing both full state mapping (with BUFFERING) and simplified mapping
- **Design note:** pywiim exposes `"buffering"` state to give integrations full visibility; integrations can choose to collapse it to "playing" if preferred for simpler UX

### Developer Experience
- Added `scripts/prerelease-test.sh` - comprehensive pre-release testing workflow
- Added `scripts/test_devices.conf` - configurable test device list
- Added `scripts/test_state_properties.py` - validates new state properties against real devices
- Pre-release workflow runs: unit tests → device connectivity → state validation → integration tests

## [2.1.36] - 2025-12-03

### Documentation
- Removed client-level API Mixins section from API reference - users should use Player class, not client methods directly
- Updated usage examples to demonstrate Player pattern instead of raw WiiMClient
- Clarified WiiMClient is low-level and primarily for internal use

## [2.1.35] - 2025-12-03

### Added
- **Centralized Source Capability System** (`source_capabilities.py`)
  - New `SourceCapability` enum with flags: `SHUFFLE`, `REPEAT`, `NEXT_TRACK`, `PREVIOUS_TRACK`, `SEEK`
  - Centralized `SOURCE_CAPABILITIES` mapping defines what each source type supports
  - Single source of truth for source-based capabilities (replaces scattered blacklists)
  - Easy to maintain and extend with new sources

- **Source-based capability properties**:
  - `supports_next_track` / `next_track_supported` - Whether next track is supported
  - `supports_previous_track` / `previous_track_supported` - Whether previous track is supported
  - `supports_seek` / `seek_supported` - Whether seeking is supported
  - `shuffle_supported` - Whether device can control shuffle (refactored to use new system)
  - `repeat_supported` - Whether device can control repeat (refactored to use new system)

- **Capability categories**:
  - `FULL_CONTROL`: Streaming services (Spotify, Amazon, Tidal, etc.) and local playback (USB, WiFi)
  - `TRACK_CONTROL`: External casting (AirPlay, Bluetooth, DLNA, multiroom) - track navigation works, shuffle/repeat controlled by source app
  - `NONE`: Live radio (TuneIn, iHeartRadio) and physical inputs (Line-in, Optical)

- **IMPORTANT for Home Assistant integrations**: 
  - Use `next_track_supported` to determine NEXT_TRACK feature, NOT `queue_count`
  - Streaming services report `queue_count=0` but next/previous commands work perfectly

### Fixed
- **Source switching now works correctly** (live debugging session)
  - Fixed `API_ENDPOINT_SOURCE` to use `setPlayerCmd:switchmode:` instead of `switchmode:`
  - The incorrect endpoint returned "unknown command" on WiiM devices
  - Source selection (Bluetooth, Line In, Optical, WiFi, etc.) from Home Assistant UI now works

### Changed
- **Bluetooth source now hides shuffle/repeat controls**
  - When playing from Bluetooth, the WiiM device is a passive audio sink receiving audio from an external device (phone, tablet)
  - Shuffle and repeat are controlled by the source device's app, not the WiiM device
  - `shuffle_supported` and `repeat_supported` now return `False` for Bluetooth source
  - `shuffle_state` and `repeat_mode` return `None` for Bluetooth source
  - This prevents confusing UI controls that have no effect

## [2.1.34] - 2025-12-02

### Fixed
- **Increased protocol probe timeouts for Audio Pro Link2 mTLS compatibility** (PR #1 by @notchris1)
  - Increased connect timeout from 0.5s to 1.0s
  - Increased total probe timeout from 2.0s to 5.0s
  - Increased async timeout from 2.0s to 5.0s
  - Audio Pro Link2 devices on port 4443 require mutual TLS (mTLS) authentication which can take several seconds to complete
  - Changed `min()` to `max()` in timeout logic to ensure mTLS handshakes always have sufficient time regardless of caller-specified timeout
  - Extracted timeout values into named constants (`PROBE_TIMEOUT_CONNECT`, `PROBE_TIMEOUT_TOTAL`, `PROBE_ASYNC_TIMEOUT`) for maintainability

## [2.1.33] - 2025-12-02

### Fixed
- **Bluetooth metadata now displays correctly (enhanced fix for Issue #138)**
  - When `getPlayerStatusEx` returns "Unknown" for title/artist/album (common with Bluetooth AVRCP), the library now fetches metadata from `getMetaInfo` endpoint
  - This ensures Bluetooth track information (title, artist, album) is displayed correctly
  - The WiiM device receives AVRCP metadata from the Bluetooth source, but only exposes it via `getMetaInfo`, not `getPlayerStatusEx`
  - Fix applies to both HTTP polling and UPnP event handling

## [2.1.32] - 2025-12-02

### Added
- **Enhanced device discovery validation** (GitHub Issue #141)
  - Added three-tier validation to prevent non-LinkPlay devices (Samsung TV, Sonos) from being incorrectly discovered
  - **Tier 1**: SSDP pattern filtering - immediately rejects known non-LinkPlay devices (Sonos, Samsung, Chromecast, Denon-Heos, SmartThings, Roku)
  - **Tier 2**: Known LinkPlay fast path - devices with "WiiM" or "Linkplay" in SERVER header skip API probe
  - **Tier 3**: API probe - tries `getStatusEx`/`getStatus` endpoints to definitively confirm LinkPlay compatibility
  
- **New discovery functions**:
  - `is_linkplay_device(host, port, timeout)` - Quick probe to check if device responds to LinkPlay API
  - `is_known_linkplay(ssdp_response)` - Check if SSDP response identifies a known LinkPlay device

- **Samsung device filtering** - Added Samsung patterns to SSDP filters:
  - SERVER patterns: `Samsung`, `SEC_HHP`, `SmartThings`
  - ST patterns: `urn:samsung.com:device`, `urn:samsung.com:service`

### Documentation
- **Comprehensive LinkPlay ecosystem documentation** in `docs/user/DISCOVERY.md`:
  - Documented the "white label" challenge (Arylic/Audio Pro use generic Linux headers)
  - Explained the "Wiimu" namespace (`urn:schemas-wiimu-com:service:PlayQueue:1`) as the definitive identifier
  - Documented manufacturer field mappings (WiiM → Linkplay, Arylic → Rakoit, etc.)
  - Clarified that mDNS/TCP discovery is legacy and not used
  - Hardware generation differences (MIPS vs ARM architectures)

## [2.1.31] - 2025-12-02

### Fixed
- **Gen1 WiFi Direct multiroom grouping now works correctly**
  - Added `get_wifi_direct_info()` method to fetch SSID and WiFi channel from device API
  - Follows the pattern from the old Linkplay integration (tries both `getStatusEx` and `getStatus` endpoints)
  - `join_group()` now automatically fetches SSID/channel from master device when Gen1 detected
  - Fixes issue where Gen1 devices (Audio Pro Gen1, legacy LinkPlay with `wmrm_version=2.0`) could not join groups
  - The previous implementation relied on DeviceInfo having `ssid` field populated, which may not be the case for all devices
  - Now explicitly fetches the WiFi Direct info when needed, ensuring WiFi Direct mode works for Gen1 devices

## [2.1.30] - 2025-12-02

### Fixed
- **Codecov configuration** - Exclude `scripts/` and `tests/` directories from patch coverage requirements
  - Scripts are manual test tools, not library code requiring unit test coverage
  - Fixes codecov/patch check failures when adding new scripts

## [2.1.29] - 2025-12-02

### Added
- **`media_content_id` property** - Returns the URL when playing media via `play_url()`
  - Useful for Home Assistant integration to expose `media_content_id` entity attribute
  - Returns `None` for non-URL sources (Spotify, Bluetooth, etc.)

- **`media_title` URL fallback** - Extracts filename from URL when device doesn't report a title
  - Common with direct URL playback where device doesn't parse metadata
  - Examples: `SoundHelix-Song-1.mp3` from `https://example.com/SoundHelix-Song-1.mp3`
  - URL-decodes special characters (e.g., `%20` → space)
  - Falls back only when device title is empty/unknown

## [2.1.28] - 2025-12-02

### Added
- **Queue Management Methods** 
  - `play_queue(queue_position)` - Start playing from a specific queue position
  - `remove_from_queue(queue_position)` - Remove item at position from queue
  - `clear_queue()` - Remove all items from queue
  - All methods use UPnP AVTransport actions (requires `supports_queue_add`)

- **Device Capability Properties** 
  - Added boolean properties for checking feature support before calling methods
  - HTTP API capabilities: `supports_eq`, `supports_presets`, `supports_audio_output`, `supports_metadata`, `supports_alarms`, `supports_sleep_timer`, `supports_led_control`, `supports_enhanced_grouping`
  - UPnP capabilities: `supports_upnp`, `supports_queue_browse`, `supports_queue_add`, `supports_queue_count`
  - Cleaner than dict access: `player.supports_eq` instead of `player.client.capabilities.get("supports_eq")`

- **Convenience Property**
  - `player.device_name` - Direct access to device name (shortcut for `player.device_info.name`)

### Changed
- **`get_queue()` return format** now matches Home Assistant standards:
  - `media_content_id` instead of `uri` (HA standard field name)
  - Added `position` field (0-based index in queue)
  - Added `duration` field (track length in seconds, parsed from DIDL-Lite)
  - Existing fields: `title`, `artist`, `album`, `image_url`

### Documentation
- Added `docs/integration/HA_CAPABILITIES.md` - Comprehensive guide for Home Assistant integration
  - Capability property reference
  - Queue operation examples
  - Service registration patterns

## [2.1.27] - 2025-12-01

### Fixed
- **Bluetooth source no longer reverts to "Idle" when no device connected (Issue #138)**
  - Fixed issue where selecting Bluetooth source would switch correctly but then revert to "Idle" after a few seconds
  - Root cause: When device reports `mode=0` (idle) without a source field, refresh() was replacing the optimistic source with None
  - Solution: Preserve existing optimistic source when new status doesn't have one (e.g., when mode=0 is correctly ignored)
  - The source now remains "bluetooth" even when device is idle and no BT device is connected
  - Prevents source from being cleared when device reports idle state without a source field

### Changed
- **Script cleanup and consolidation**
  - Removed duplicate `test-shuffle-repeat-once.py` (functionality covered by `test-playback-controls.py`)
  - Merged `debug_capabilities.py` into `test_my_devices.py` with `--debug-capabilities` flag
  - Updated scripts documentation to reflect changes

## [2.1.26] - 2025-11-30

### Fixed
- **wmrm_version compatibility check now compares major versions only**

## [2.1.25] - 2025-11-30

### Added
- **WiFi Direct mode support for Gen1 devices (Audio Pro Gen1, legacy LinkPlay)**
  - Added automatic detection of WiFi Direct vs router-based multiroom join mode
  - WiFi Direct mode is used for devices with `wmrm_version` 2.0 or firmware < 4.2.8020
  - Router-based mode (default) is used for modern devices with `wmrm_version` 4.2 or firmware >= 4.2.8020
  - `join_slave()` now accepts optional `master_device_info` parameter to determine join mode
  - WiFi Direct mode uses command format: `ConnectMasterAp:ssid={hex}:ch={channel}:auth=OPEN:encry=NONE:pwd=:chext=0`
  - Router-based mode uses command format: `ConnectMasterAp:JoinGroupMaster:eth{ip}:wifi0.0.0.0`
  - Automatically falls back to router-based mode if SSID is missing (with warning)
  - **Impact**: Gen1 devices can now join groups correctly using the legacy WiFi Direct protocol
  - **Related**: Fixes GitHub issue #129 - Audio Pro Gen1 speakers can now join groups

### Fixed
- **Enhanced wmrm_version validation with extensive debug logging for Gen1 devices**
  - Added comprehensive debug logging for Gen1 device join operations
  - Logs SSID, WiFi channel, firmware version, and wmrm_version for troubleshooting
  - Detailed error messages when join fails for Gen1 devices
  - Helps diagnose WiFi Direct mode configuration issues when testing with Gen1 devices

### Changed
- **Added SSID and WiFi channel fields to DeviceInfo model**
  - `DeviceInfo` now includes `ssid` and `wifi_channel` fields needed for WiFi Direct mode
  - Fields are populated from `getStatusEx` response (same endpoint path for all devices)
  - Enables automatic WiFi Direct mode detection and join command generation

## [2.1.24] - 2025-11-30

### Added
- **Comprehensive pre-release testing infrastructure**
  - Added extensive integration test suite (`test_prerelease.py`) with real device validation
  - Tests cover all major Player functionality: playback controls, shuffle/repeat, volume/mute, EQ presets, source switching, audio output modes
  - Automatic state restoration after tests to prevent device disruption
  - Pre-release check script (`scripts/prerelease-check.sh`) for automated validation before releases
  - Enhanced unit test coverage with 730+ new test cases for API client functionality
- **Codecov integration for test coverage reporting**
  - Added Codecov configuration and coverage uploads to CI workflow
  - Coverage badge and reporting now available in repository

### Changed
- **Enhanced capability detection with read/write distinction**
  - EQ capability detection now distinguishes between read-only and read/write support
  - Some devices (e.g., Arylic) can read EQ status but not set EQ presets - now correctly detected
  - Audio output capability detection improved with separate read/set probing
  - Preset capability detection enhanced with fallback to `preset_key` field when `getPresetInfo` unavailable
  - Capability probing now uses multiple endpoint attempts for more reliable detection
- **Improved CI/CD workflow reliability**
  - Enhanced GitHub release creation error handling
  - Removed duplicate ruff check from release script
  - Streamlined CI workflow configuration

## [2.1.23] - 2025-11-28

### Changed
- **Release script now uses check.sh for validation**
  - Ensures all CI checks (format, lint, typecheck, tests) run before release
  - Prevents releases with mypy errors or other CI failures
  - Consistent validation between local and CI

## [2.1.22] - 2025-11-28

### Changed
- **Improved CI workflow reliability**
  - Changed black/isort to check-only mode (fail if formatting needed)
  - Added clear error messages for failed checks
  - Ensures CI catches formatting/linting issues before merge

## [2.1.21] - 2025-11-28

### Fixed
- **Fixed volume attribute missing for grouped speakers (Issue #126)**
  - State synchronization now preserves volume/mute when HTTP API returns `None` (e.g., grouped Audio Pro devices)
  - Capability detection now probes `getPlayerStatusEx` support instead of assuming based on device generation
  - Audio Pro generation-specific settings now only apply to Audio Pro devices, not all legacy devices (e.g., Arylic)
- **Improved volume detection reliability**
  - Added lazy UPnP client creation for automatic UPnP support
  - UPnP `GetVolume` is now preferred over HTTP for volume retrieval (with HTTP fallback)
  - Ensures volume is available even when HTTP API doesn't return it (e.g., grouped devices)
- **Fixed excessive polling on Home Assistant startup when devices are idle**

## [2.1.20] - 2025-11-27

### Added
- **UPnP SOAP action methods for diagnostics and edge cases**
  - `get_media_info()` - Fetch current media URI and metadata via UPnP
  - `get_transport_info()` - Fetch play state (PLAYING/PAUSED/STOPPED) via UPnP
  - `get_position_info()` - Fetch position and duration via UPnP
  - `get_volume()` / `get_mute()` - Fetch volume/mute state via UPnP
  - `get_device_capabilities()` - Fetch supported media types via UPnP
  - `get_current_transport_actions()` - Fetch available transport controls via UPnP
  - `get_full_state_snapshot()` - Convenience method to fetch all state in one call
  - **Use case**: Diagnostics, debugging, and Audio Pro MkII devices (which require UPnP for volume/play state)
  - **Note**: These are low-level utilities on `UpnpClient`, not integrated into Player state flow

### Fixed
- **Added URL validation for UPnP image URLs**
  - Invalid image URLs from DIDL-Lite metadata are now filtered out
  - Uses Python's built-in `urllib.parse` (no new dependencies)
  - Prevents invalid/placeholder URLs from being used as album art
- **Added proper resource cleanup to UPnP client**
  - Added `close()` method to `UpnpClient` for proper session cleanup
  - Eliminates "unclosed connector" warnings

## [2.1.19] - 2025-11-27

### Fixed
- **Fixed `play_notification()` endpoint to use correct API command**
  - Fixed URL encoding to use consistent `safe=":/?&=#%"` matching `play_url()`
  - **Tested successfully**: Spotify and AirPlay both resume seamlessly after notification
  - The device firmware handles volume attenuation and restoration automatically
  - No state management needed - device's built-in `playPromptUrl` handles everything

## [2.1.18] - 2025-11-26

### Fixed
- **Defensive fix: Prevent mode=0 from being mapped to source="idle" (Issues #122, #103)**
  - **Root cause**: `mode=0` maps to "idle" in MODE_MAP, but "idle" is a play STATE, not a SOURCE
  - Parser now ignores mode=0 when setting source field to prevent incorrect `source="idle"`
  - **Why this matters**: Primarily affects legacy LinkPlay devices (e.g., Audio Pro)
    - Modern WiiM devices (tested: WiiM Pro) correctly report mode=31 for Spotify ✓
    - Legacy Audio Pro devices may report mode=0 for DLNA/Spotify (Issue #103 - v0.28 worked, later versions broke)
    - WiiM Amp Ultra user reported similar issue (Issue #122) but unverified
  - **Impact**: Defensive - prevents source from being set to "idle" if device reports mode=0
  - This is a conceptually correct fix regardless: "idle" should never be a source value
  - **Note**: Other Spotify state issues exist but are integration-specific:
    - Issue #103: UPnP subscription failures on Audio Pro devices (integration bug)
    - Issue #83: State desync when controlling from phone (integration timing bug)

### Added
- **Added HDMI audio output mode support for WiiM Amp Ultra (Issue #122)**
  - Added `AUDIO_OUTPUT_MODE_HDMI_OUT = 7` constant
  - Updated `AUDIO_OUTPUT_MODE_MAP` to recognize mode 7 as "HDMI Out"
  - Added name mappings: "hdmi out", "hdmi", "hdmi arc" → mode 7
  - **Impact**: Eliminates "Unknown audio output mode 7" warning on WiiM Amp Ultra devices
  - HDMI ARC output now properly recognized and controllable

## [2.1.17] - 2025-11-25

### Fixed
- **CRITICAL: Fixed three shuffle/repeat bugs that have plagued the library since inception**
  - **Bug 1 - Wrong API endpoint**: Changed from `setLoopMode:` (non-existent) to `setPlayerCmd:loopmode:` (correct)
    - Root cause: Library was calling an API endpoint that doesn't exist - device returned "unknown command" silently
    - **Impact**: Shuffle and repeat commands were completely non-functional across ALL sources
    - Discovered via systematic curl testing comparing working WiiM app commands vs library commands
  - **Bug 2 - Wrong parsing logic**: Fixed shuffle/repeat state reading to use vendor-specific loop_mode mappings instead of legacy bitfield logic
    - Root cause: Reading state used bitfield logic (`loop_mode & 4` for shuffle) while writing used vendor mappings
    - **Impact**: Shuffle showed as repeat, repeat showed as shuffle (values were swapped)
    - WiiM loop_mode=3 interpreted as: shuffle=False, repeat=True (WRONG) instead of shuffle=True, repeat=False (CORRECT)
  - **Bug 3 - Invalid validation**: Removed hardcoded loop_mode validation that rejected valid values
    - Root cause: Validation hardcoded `(0,1,2,4,5,6)` from legacy bitfield mapping, rejecting loop_mode=3
    - **Impact**: Library rejected loop_mode=3 (shuffle, no repeat) as "invalid" even though it's valid for WiiM devices
    - Changed to accept all reasonable loop_mode values (0-10) since mappings are vendor-specific
  - **Testing**: Shuffle and repeat now work correctly on Spotify albums, playlists, and all other controllable sources
- **EQ preset normalization for integration calls**
  - Fixed EQ preset setting failing when integrations pass preset names with spaces, hyphens, or underscores
  - Now normalizes "bass reducer", "base reducer", "bass_reducer", "bass-reducer", "Bass Reducer" to "bassreducer" (the internal key)
  - Handles common typos like "base" -> "bass" automatically
  - Supports both internal keys (e.g., "bassreducer") and display names (e.g., "Bass Reducer") as input
  - Integrations can now use any format and it will be normalized correctly before sending to device

### Added
- **Spotify content-type detection for shuffle/repeat support**
  - Detects content type using Spotify URI in `vendor` field from device status
  - `spotify:album:*` and `spotify:playlist:*` → shuffle_supported = True (music content)
  - `spotify:show:*` and `spotify:episode:*` → shuffle_supported = False (episodic content like podcasts/audiobooks)
  - Matches WiiM app behavior: hides shuffle/repeat controls for podcasts and audiobooks
  - **Why**: Shuffling podcast episodes or audiobook chapters doesn't make sense
  - **Impact**: Home Assistant will correctly show/hide shuffle controls based on Spotify content type
- Added `loop_mode=5` handling to prevent "unknown loop_mode" warnings
  - Some sources (like Spotify Connect) may use loop_mode=5 for external control state
  - Now treated as valid and interpreted as normal/off state
- **AirPlay blacklisted after testing confirmed iOS device controls playback**
  - Tested: Device accepts loop_mode commands but they don't affect iOS-controlled queue
  - Both WiiM app and Apple Music app hide shuffle/repeat controls for AirPlay
  - Device is passive audio sink; iOS/macOS device owns the playback queue
  - No vendor field metadata to distinguish content types (always empty)
  - Matches behavior documented in CHANGELOG v1.0.71 technical background

## [2.1.16] - 2025-11-24

### Fixed
- **SSDP discovery now filters out Sonos and other non-LinkPlay devices (GitHub discussion #120)**
  - Added Sonos to SERVER pattern filter to prevent Sonos devices from being auto-discovered by WiiM integration
  - Enhanced filtering to check both ST (service type) and SERVER headers for more reliable device identification
  - Added ST patterns for Sonos (ZonePlayer, ZoneGroupTopology), Roku, and DIAL protocol devices
  - Filtering remains conservative - only excludes devices with specific vendor identifiers
  - Improves discovery performance by skipping validation of known non-LinkPlay devices
  - Logs filtered devices with both ST and SERVER values for debugging

## [2.1.15] - 2025-11-23

### Fixed
- **State change callback now triggered after Bluetooth connection failure**
  - When Bluetooth connection fails, the state change callback is now triggered after refreshing audio output status
  - Ensures integrations are notified to update when output mode changes after failed BT connection attempts
  - Integrations will now receive state change events even when BT connection fails

## [2.1.14] - 2025-11-23

### Fixed
- **Audio output status refresh after Bluetooth connection failure**
  - When Bluetooth connection fails, audio output status is now refreshed to show current hardware output mode
  - Prevents showing stale Bluetooth output state when device is unavailable
  - Ensures UI reflects correct current output after failed BT connection attempts
- **Player code now consistently uses player-level methods**
  - Fixed `statemgr.py` and `diagnostics.py` to use `player.get_audio_output_status()` instead of calling client methods directly
  - Player-level methods automatically update internal cache, ensuring properties work correctly
  - Added rule to `.cursorrules` documenting this pattern

## [2.1.13] - 2025-11-23

### Changed
- **Completely removed generic "Bluetooth Out" from available_output_modes**
  - Generic "Bluetooth Out" is no longer included in `available_output_modes` property
  - Only specific paired Bluetooth output devices from history are shown in `available_outputs`
  - Simplified logic: no need to conditionally remove "Bluetooth Out" since it never exists
  - Updated diagnostics tool to match Player logic

## [2.1.12] - 2025-11-23

### Changed
- **Improved audio output selection behavior**
  - `available_outputs` now removes generic "Bluetooth Out" option when specific BT devices are available from history
  - Only shows specific paired Bluetooth output devices (Audio Sinks) instead of generic option
  - Provides cleaner UI for output selection in Home Assistant and other integrations
  - Output selection methods now use full refresh to ensure cache is updated immediately
  - Bluetooth connection failures now refresh BT history to update available devices list
  - Improved error messages for unavailable Bluetooth devices (powered off, out of range, etc.)

## [2.1.11] - 2025-11-23

### Fixed
- **Headphone output now appears in available_output_modes for WiiM Ultra (GitHub issues #86, #117)**
  - Fixed lenient model check: now checks for "ultra" in model name (not just "wiim ultra")
  - Restores behavior from integration v0.2.14 where headphone output was working
  - "Headphone Out" now correctly appears in dropdown selector for Ultra devices
- **Preset names now populate automatically (GitHub issue #118)**
  - Presets are now fetched periodically every 60 seconds, not just on full refresh or track change
  - Fixes Home Assistant showing generic "Preset 1" to "Preset 20" instead of actual preset names
  - Presets refresh on: full refresh, track change, and every 60s (periodic background refresh)
- **EQ preset change detection**
  - Automatically fetches full EQ info (band values, enabled status) when EQ preset changes in status
- **Monitor CLI debug info now shows for all roles**
  - Debug info now displays for master/slave roles, not just solo
  - Removed redundant `slave_count` field from debug output

### Added
- **Monitor CLI now displays preset stations**
  - Shows preset list with names (up to 10 presets)
  - Displays "None configured" if device supports presets but none are set

### Changed
- **Simplified role detection logic**
  - Removed mode=99 (follower mode) check from role detection
  - Now uses `group` field exclusively for slave detection (per design guide)
  - The `group` field is always reliable, while `mode=99` can get stuck after leaving a group (firmware bug)
  - Role detection now follows design guide pattern: Slave = `group != "0"` and has `master_uuid`/`master_ip` pointing to another device
  - This simplifies the code and makes it more reliable
- **Improved audio output selection behavior**
  - `available_outputs` now removes generic "Bluetooth Out" option when specific BT devices are available from history
  - Only shows specific paired Bluetooth output devices (Audio Sinks) instead of generic option
  - Provides cleaner UI for output selection in Home Assistant and other integrations
  - Output selection methods now use full refresh to ensure cache is updated immediately
  - Bluetooth connection failures now refresh BT history to update available devices list
  - Improved error messages for unavailable Bluetooth devices (powered off, out of range, etc.)

### Fixed
- **Clear multiroom source when device is not a slave**
  - When role detection determines device is not a slave (solo or master) but source is still "multiroom", the source is now automatically cleared
  - Prevents UI confusion where devices show "multiroom" as source when they're actually solo or master
  - Handles stale state from firmware bugs (mode=99 getting stuck) or parser setting multiroom source incorrectly
  - Source is cleared from both status model and state synchronizer to prevent refresh from restoring it

## [2.1.10] - 2025-11-22

### Changed
- **`refresh()` now automatically performs full refresh on startup**
  - First call to `refresh()` automatically sets `full=True` to ensure all state is populated
  - Ensures player is "ready for use" with all properties available (device info, EQ presets, preset stations, audio output, Bluetooth history)
  - Subsequent refreshes use lightweight polling (Tier 1 only)

### Fixed
- **Fixed devices stuck as "slave" after leaving multiroom group (GitHub issue #119)**
  - **Problem**: Devices that left a multiroom group would be stuck in slave mode, rejecting all playback commands
  - **Root cause**: Firmware bug - when device leaves group, it clears `group` field but forgets to clear `mode` field from "99" (follower mode)
  - **Previous behavior**: Library used `mode=="99"` to detect slaves, which would incorrectly treat solo devices as slaves if mode stuck
  - **Fix**: Now uses `group` field exclusively for slave detection (`group=="1"` = slave, `group=="0"` = solo/master)
  - **Impact**: Devices work correctly after leaving groups - playback commands are accepted, media player entity is selectable in Home Assistant
  - The `group` field is always correct (firmware clears it properly), while `mode` field can get stuck
  - Removed override logic that trusted `mode` over authoritative `group` field
- **EQ presets and preset stations now refresh on track change**
  - Previously only fetched on full refresh, now also fetched when track changes
  - Track changes may indicate user switched presets/stations, so refreshing keeps data current
  - No periodic polling needed - library handles it automatically
- **Bluetooth paired devices now refresh on track change**
  - Bluetooth history (paired devices) now fetched on track change or full refresh
  - Keeps BT device list current when users connect/disconnect devices
- **Audio output status automatically fetched on startup**
  - `refresh()` now fetches audio output status on first refresh (when `_audio_output_status` is None)
  - Ensures `audio_output_mode` property works immediately after startup
  - Integrations no longer need to manually fetch audio output status

### Documentation
- **Updated HA integration guide to reflect automatic refresh behavior**
  - Removed manual fetching instructions for EQ presets, preset stations, and audio output
  - Clarified that library handles these automatically (on startup and track change)
  - Updated examples to show only EQ band values need periodic fetching

## [2.1.9] - 2025-11-22

### Added
- **Monitor CLI now displays current and available audio outputs**
  - Shows current output mode with "(current)" indicator
  - Lists all available outputs (hardware modes + paired BT devices)
  - Automatically fetches audio output status every 60 seconds when supported
  - Display format: `Output: Line Out (current), Optical Out, Coax Out, Bluetooth Out`

### Fixed
- **Fixed HA integration guide `should_fetch_audio_output()` calls**
  - Added missing `source_changed` parameter to method calls
  - Updated interval documentation from 15s to 60s to match actual strategy

## [2.1.8] - 2025-11-22

### Fixed
- **Fixed `audio_output_mode` property returning None in Home Assistant integrations**
  - Root cause: `player.get_audio_output_status()` was fetching data but not updating player's internal cache
  - **Solution**: `get_audio_output_status()` now automatically updates player's `_audio_output_status` cache
  - **Impact**: `player.audio_output_mode` property now works correctly when audio output status is fetched via coordinator
  - Home Assistant select entities now correctly display the current output mode instead of showing "Audio Output Mode"
  - Improved `current_option` implementation in documentation with better validation and fallback logic

## [2.1.7] - 2025-11-22

### Documentation
- **Fixed incorrect documentation for `available_outputs` property**
  - Corrected docstring to clarify that `available_outputs` is a property on `player` (not `player.audio`)
  - Added comprehensive "Audio Output Selection" section to HA_INTEGRATION.md
  - Clarified that `available_outputs` is a property (not a method) and should be accessed as `player.available_outputs`
  - Removed incorrect reference to `player.audio.available_outputs` (does not exist)
  - Updated example code to remove unnecessary `async_request_refresh()` call

## [2.1.6] - 2025-11-22

### Fixed
- **Fixed protocol/port detection when integration passes incorrect port (GitHub Issue #114)**
  - Root cause: When integration passes `port=443` but device uses HTTP on port 80, pywiim would try both HTTPS and HTTP on port 443, which always fails
  - **Solution**: When a user-specified port fails, pywiim now falls back to the full standard probe list (HTTPS 443, HTTPS 4443, HTTPS 8443, HTTP 80, HTTP 8080)
  - This ensures devices are found even if the integration incorrectly specifies a port
  - **Impact**: Devices that use HTTP on port 80 (like LinkPlay "smart_audio" devices) now connect correctly even when integration defaults to port 443
  - **Note**: Integration should ideally not pass a port at all, or persist and use the discovered endpoint (see HA_INTEGRATION.md)

### Changed
- **Enhanced port/protocol detection robustness**
  - When `port=443` is specified: Tries HTTPS on 443 first, then falls back to standard probe list
  - When `port=80` is specified: Tries HTTP on 80 first, then falls back to standard probe list
  - When non-standard port is specified: Tries both protocols on that port, then falls back to standard probe list
  - This makes pywiim resilient to incorrect port specifications from integrations

## [2.1.5] - 2025-11-22

### Fixed
- **Fixed missing polling strategy methods that broke EQ in Home Assistant**
  - Added missing `should_fetch_eq_info()`, `should_fetch_device_info()`, and `should_fetch_multiroom()` methods to `PollingStrategy` class
  - These methods were referenced in Home Assistant integration documentation but didn't exist in the code
  - Root cause: Methods were removed/consolidated during polling refactoring but documentation wasn't updated
  - **Impact**: EQ presets now properly appear in Home Assistant integrations

### Added
- **Enhanced HLS stream metadata extraction with URL-based fallback**
  - Added station name extraction from URL patterns when metadata isn't embedded in segments
  - Checks multiple segments (last 3) instead of just the latest one
  - Provides station name as fallback when track/artist metadata isn't available
  - **Impact**: Users now see station names even when streams don't embed metadata

## [2.1.4] - 2025-11-22

### Added
- **HLS stream metadata extraction support**
  - Added support for extracting metadata (title, artist) from HLS (HTTP Live Streaming) radio streams
  - Handles master playlists and automatically resolves to variant playlists
  - Extracts ID3 tags from HLS audio segments using `m3u8` and `mutagen` libraries
  - Works alongside existing Icecast/SHOUTcast metadata extraction
  - Gracefully handles streams that don't embed metadata in segments
  - New dependencies: `m3u8>=3.5.0`, `mutagen>=1.47.0`

## [2.1.3] - 2025-11-22

### Fixed
- **Fixed master device role detection after polling optimization**
  - Root cause: Code assumed `mode != "99"` meant device was solo, but master devices can have slaves with `mode != "99"` (mode reflects source, not group status)
  - Previous optimization skipped `get_device_group_info()` when `mode != "99"`, causing masters to be incorrectly detected as solo
  - **Solution**: Always call `get_device_group_info()` when potential slave indicators are present OR when device_info is cached (full refresh)
  - Fast path optimization: Only skip expensive `getDeviceInfo` calls when no slave indicators AND no group object AND no cached device_info
  - **Impact**: Master devices are now correctly detected even when they have `mode != "99"`

- **Enhanced slave detection with dual indicators**
  - Added support for two slave indicators (either/or, not both required):
    - `mode == "99"` (follower mode)
    - `source == "multiroom"` (multiroom source)
  - These indicators may not both be present, so we check for either
  - When fast indicators suggest slave but `get_device_group_info()` returns solo (due to missing master info), we trust the fast indicators
  - Slaves often don't have master info in their status, so this override ensures correct detection
  - **Impact**: Slave devices are now correctly detected even when they lack master info in device status

### Changed
- **Optimized role detection to reduce expensive API calls**
  - Only call `get_device_group_info()` (which uses expensive `getDeviceInfo`) when:
    - Potential slave detected via fast indicators (`mode=99` OR `source=multiroom`)
    - Group object exists (might be master, need to verify)
    - Device info is cached (full refresh happened, safe to check)
  - Fast path: Skip expensive calls when no indicators and device is solo with no group
  - **Impact**: Reduces unnecessary `getDeviceInfo` calls during normal polling, improving performance

## [2.1.2] - 2025-11-22

### Changed
- **Smooth player state transitions with debounce logic**
  - Added 500ms debounce buffer for "pause", "stop", and "buffering" events during playback
  - Eliminates UI flickering (Play -> Pause -> Play) that occurred during track changes
  - Legitimate pauses/stops are still applied after the short debounce period
  - Metadata updates are always applied immediately to ensure track info updates instantly
- **Standardized buffering state handling**
  - Normalized device-specific states ("load", "loading", "transitioning") to standard "buffering" state
  - Updated `play_state` model to include "buffering" as a valid state
  - Updated UPnP event handler to treat "buffering" as an active state (preserving metadata)
  - Prevents "Load" or "Loading" from appearing as a distinct state in integrations

### Added
- **Stream metadata enrichment for radio streams**
  - Automatically extracts title/artist metadata from Icecast/SHOUTcast streams and M3U/PLS playlists
  - Enriches player state when device reports raw URLs instead of parsed metadata
  - Enabled by default, can be disabled via `StateManager.stream_enrichment_enabled`

### Fixed
- **CRITICAL: Fixed loop_mode interpretation for WiiM and Arylic devices (GitHub Issue #111)**
  - Root cause: WiiM and Arylic devices use different loop_mode value schemes, pywiim was using incorrect bitfield interpretation
  - WiiM devices use: 0=loop_all, 1=repeat_one, 2=shuffle_loop, **3=shuffle_no_loop**, 4=normal
  - Arylic devices use: 0=repeat_all, 1=repeat_one, 2=shuffle_repeat_all, **3=shuffle**, 4=normal, 5=shuffle_repeat_one
  - Previous code interpreted loop_mode as bitfields and flagged **loop_mode=3 as INVALID** (both repeat bits set)
  - **This broke shuffle buttons in Home Assistant** - device returned valid loop_mode=3, but pywiim rejected it
  - **Solution**: Added vendor-specific loop mode mappings (`pywiim/api/loop_mode.py`)
  - Parser now uses `get_loop_mode_mapping(vendor)` to correctly interpret loop_mode values per device type
  - Playback control now uses vendor-specific mappings when setting shuffle/repeat modes
  - No more "Invalid loop_mode 3" warnings
  - Shuffle and repeat buttons now work correctly for all device types

### Changed
- **Re-enabled shuffle/repeat support for AirPlay (testing)**
  - AirPlay was previously blacklisted, but the problem may have been loop_mode misinterpretation
  - With vendor-specific loop_mode parsing, AirPlay controls may now work correctly
  - Requires testing with real devices to confirm functionality
  - If unsuccessful, can easily be re-blacklisted
  - Updated tests to use `tunein` (radio streams) for blacklist testing instead of AirPlay

## [2.1.1] - 2025-11-21

### Changed
- **Shuffle and repeat control availability - now permissive by default**
  - Changed from whitelist (restrictive) to blacklist (permissive) approach for shuffle/repeat control
  - Most sources now support shuffle/repeat controls (Spotify, Tidal, Amazon Music, Qobuz, Deezer, Pandora, Bluetooth, USB, physical inputs, etc.)
  - Blacklist only blocks sources where we know controls don't work: AirPlay, TuneIn, iHeartRadio, multiroom slaves, and generic radio streams
  - Resolves GitHub issue #111 - users can now shuffle collections in streaming services
  - Easy to extend: add sources to blacklist as needed when discovering incompatibilities

## [2.1.0] - 2025-11-21

### Changed
- **BREAKING: Removed position estimation - return raw device position**
  - PyWiim now returns RAW position values from device (no estimation or timer)
  - Removed `media_position_updated_at` property - integrations must manage timestamps
  - Removed internal position timer and all estimation logic (~300 lines deleted)
  - **Rationale**: Position estimation caused jitter by fighting with HA frontend advancement
  - **Home Assistant Integration Impact**: HA integration must now manage `media_position_updated_at` timestamp
  - **Benefit**: Simpler architecture, matches all other HA integrations (Sonos, LinkPlay, etc.)
  - **Architecture**: PyWiim returns "what device said", HA integration tracks "when we read it", HA frontend does smooth display
  - This is the correct separation of concerns and eliminates position jitter at the root cause

## [2.0.19] - 2025-11-21

### Fixed
- **Position jitter fix attempt (SUPERSEDED by 2.1.0)**
  - This release attempted to fix jitter with estimation improvements
  - The correct fix was to remove estimation entirely (done in 2.1.0)

## [2.0.18] - 2025-11-21

### Fixed
- **Fixed GitHub Actions CI to skip integration tests**
  - Integration tests require a real device and are now properly skipped in CI
  - Tests still pass locally when device is available
  - Prevents CI failures when device is not accessible on GitHub runners
  - Updated pytest configuration to skip integration tests by default

## [2.0.17] - 2025-11-21

### Added
- **Added `pywiim_version` to diagnostics**
  - The library version is now included in diagnostic information
  - Displayed in Home Assistant device diagnostics section
  - Helps with troubleshooting and support

## [2.0.16] - 2025-11-21

### Documentation
- **Added comprehensive Position & Duration Edge Cases section to API_REFERENCE.md**
  - Documents time unit inconsistency (milliseconds vs microseconds) for different sources (Issue #75)
  - Explains live stream and zero duration handling for web radio
  - Details position > duration firmware bug detection and correction
  - Clarifies AirPlay duration interpretation (totlen field)
  - Documents negative position value filtering
  - Explains UPnP position update behavior (only on track start, not continuously)
  - Provides source-specific behavior reference table
  - Includes best practices with code examples for integrations
  - **Impact**: Integrators can now understand all position/duration edge cases without digging through closed issues

## [2.0.15] - 2025-11-21

### Fixed
- Fixed audio output mode mapping to match official WiiM API documentation (1=SPDIF/Optical, 2=AUX/Line Out, 3=COAX)
- "Line Out" now correctly maps to mode 2 (AUX) instead of mode 0, per official API specs
- Added `player.audio` property to expose AudioConfiguration (documented API was previously broken)

## [2.0.14] - 2025-11-20

### Fixed
- **Replaced rectangular logo with square logo for better HA display**
  - Now using 256x257 square icon from original WiiM HA integration
  - Smaller file size: 4.85 KB (was 7.79 KB)
  - Better visual appearance when displayed in Home Assistant UI
  - **Impact**: Logo displays properly in square aspect ratio on HA media player cards

## [2.0.13] - 2025-11-20

### Fixed
- **Fixed entity_picture sentinel value for embedded logo fallback**
  - Set `entity_picture = "pywiim:embedded-logo"` when no artwork (was `None`)
  - HA now correctly detects there's cover art to display
  - `fetch_cover_art()` recognizes sentinel and serves embedded logo bytes
  - **Impact**: Logo now actually displays in HA when nothing is playing

## [2.0.12] - 2025-11-20

### Fixed
- **Cover art fallback now uses embedded logo instead of external URL**
  - Embedded actual WiiM logo (PNG, 7.8 KB) as base64 in library
  - `fetch_cover_art()` now returns embedded logo bytes directly when no artwork available
  - No HTTP call needed for fallback - instant display with zero network dependency
  - Fixes issue where external logo URL (`wiimhome.com`) returns HTTP 403
  - **Impact**: Fallback logo will always display correctly in Home Assistant and other integrations

## [2.0.11] - 2025-11-20

### Changed
- **Made `leave_group()` idempotent and intelligent**
  - Solo players: Returns immediately (no error) - idempotent behavior
  - Master players: Disbands entire group (all players become solo)
  - Slave players: Leaves group normally (master and other slaves remain)
  - **Impact**: Integrations no longer need to check player role before calling `leave_group()`
  - **Impact**: HA integration can remove defensive check that blocked master unjoin

### Documentation
- Enhanced `join_group()` and `leave_group()` docstrings to explicitly document automatic role handling
- Updated HA_INTEGRATION.md to emphasize that role checking is unnecessary
- Updated API_REFERENCE.md with clear examples showing role-agnostic usage
- Added prominent comments: "NO NEED to check player.is_master or player.is_slave - just call it!"

## [2.0.10] - 2025-11-20

### Documentation
- Added "Critical Concepts" section to HA_INTEGRATION.md clarifying Device API vs Group object usage
- Clarified that `player.role` is the ONLY way to check if device is master/slave/solo
- Explained that `group.slaves` is for operations only, not for checking if device has slaves
- Removed confusing references to calling `get_device_group_info()` directly to check role

## [2.0.9] - 2025-11-20

### Documentation
- Enhanced HA_INTEGRATION.md with prominent warnings about NOT calling `async_request_refresh()` in entity methods
- Added "State Management - How It Works" section at top of integration guide
- Clarified that coordinator's `refresh()` is scheduled polling, not manual refresh
- Added critical warnings to prevent integration from calling unnecessary manual refresh after commands

## [2.0.8] - 2025-11-20

### Added
- **Automatic playback command routing for slave players**
  - Slave playback commands (play, pause, stop, next, previous) now automatically route through Group object to master
  - No integration changes needed - just call `slave_player.pause()` and pywiim handles routing
  - Raises clear `WiiMError` if slave not linked to group (edge case)
  - **Impact**: HA slave entities can use playback controls directly, commands route to master automatically

### Changed
- **Cross-notification for volume and mute changes**
  - When slave volume/mute changes, both slave's and master's callbacks now fire
  - Enables immediate virtual group entity updates without polling lag
  - Master's callback doesn't fire duplicate when master changes its own volume
  - **Impact**: Virtual group entities update immediately when any member's volume changes
- **Enhanced automatic Player linking in `_synchronize_group_state()`**
  - Now uses `player_finder` callback to automatically link slave Player objects when groups detected
  - Automatically links new slaves that appear in group
  - Automatically links slaves to master when slave refreshes
  - **Impact**: Player objects link automatically during `refresh()`, no manual coordinator linking needed

### Documentation
- Added "Virtual Group Entity Implementation" section to HA_INTEGRATION.md
- Added "Event Propagation Model" section explaining routing and cross-notification
- Added comprehensive "Group Object" documentation to API_REFERENCE.md
- Updated README.md with smart routing and cross-notification features
- Added `docs/testing/GROUP_ROUTING_TESTS.md` for testing guidance

## [2.0.7] - 2025-11-19

### Fixed
- **No functional changes** - patch release

## [2.0.6] - 2025-11-19

### Fixed
- **Fixed master detection - role property now uses device API state**
  - Fixed `player.role` property to return `_detected_role` from device API instead of checking `_group` object
  - Added `_detected_role` initialization and update during `refresh()` via `get_device_group_info()`
  - Fixes issue where master devices showed as "solo" when `_group` was None, even if device had slaves
  - **Root cause**: CHANGELOG documented fix in v1.0.76 but code was never actually updated
  - **Impact**: Master detection now works correctly based on actual device API state, independent of Group object linking

## [2.0.5] - 2025-11-19

### Fixed
- **Fixed role detection in monitor_cli for devices without player_finder**
  - monitor_cli now uses `get_device_group_info()` role directly instead of relying on Group object's linked Player instances
  - Fixes issue where master devices with slaves showed "SOLO" instead of "MASTER" when Player objects aren't linked
  - **Impact**: monitor_cli now correctly displays device role based on actual device API state

### Changed
- **Improved monitor_cli role display accuracy**
  - Role is now determined from device API state (`last_group_info.role`) rather than Group object membership
  - This ensures accurate role display even when `player_finder` is not provided (standalone monitoring scenarios)

## [2.0.4] - 2025-11-19

### Added
- **Audio quality properties for Player**
  - Added `media_sample_rate` property: Audio sample rate in Hz from metadata (getMetaInfo)
  - Added `media_bit_depth` property: Audio bit depth in bits from metadata (getMetaInfo)
  - Added `media_bit_rate` property: Audio bit rate in kbps from metadata (getMetaInfo)
  - Added `media_codec` property: Audio codec from status (getStatusEx), e.g., "flac", "mp3", "aac"
  - All properties support both camelCase and snake_case field names from API responses
  - Properties return `None` if metadata/status is unavailable or field is missing
  - **Impact**: Easy access to audio quality information without navigating nested dict structures

## [2.0.3] - 2025-11-19

### Fixed
- **Fixed cover art not retrieved from getMetaInfo when getPlayerStatusEx has no artwork**
  - Base.py now correctly detects when entity_picture is set to default WiiM logo and treats it as "no valid artwork"
  - This triggers the getMetaInfo fallback to retrieve artwork from albumArtURI field
  - Fixes issue where players (e.g., AirPlay sources) that only provide artwork via getMetaInfo were showing default logo instead of actual cover art
  - **Impact**: Players now correctly display cover art from getMetaInfo when getPlayerStatusEx doesn't include artwork fields

## [2.0.2] - 2025-11-19

### Fixed
- **Fixed delayed UI updates for play/pause operations in Home Assistant**
  - Play/pause/resume/stop methods now update state synchronizer optimistically (matching volume/mute behavior)
  - Fixes issue where UI would take 5+ seconds to update when pausing/playing radio streams
  - State synchronizer is now updated immediately after API calls, ensuring `play_state` property returns correct value instantly
  - **Impact**: Home Assistant and other integrations now receive instant UI updates (<1ms) for play/pause operations, matching the behavior of volume and mute controls

## [2.0.1] - 2025-11-19

### Fixed
- **Fixed default cover art not showing for radio streams**
  - Improved `entity_picture` validation in parser to check for invalid values (None, empty, "unknown") not just missing key
  - Default WiiM logo now properly displays when device returns empty or invalid cover art values
  - Fixes issue where radio streams showed no cover art even though default logo should be used
  - **Impact**: Radio streams and other media without cover art now consistently show WiiM logo

- **Fixed metadata flickering when playing/pausing radio streams**
  - Improved state merge logic to preserve existing metadata when both HTTP and UPnP return empty values
  - Prevents empty HTTP polling data from overwriting valid UPnP metadata
  - Fixes UI flickering issue where metadata would disappear when pausing/playing radio streams
  - **Impact**: Stable metadata display for radio streams in Home Assistant and other integrations

### Added
- **Extract stream URI from UPnP events**
  - Added extraction of `AVTransportURI` and `CurrentURI` from UPnP events
  - Stream URI stored internally for potential future ICY metadata extraction
  - Currently logged for debugging purposes
  - **Impact**: Foundation for potential future radio metadata enhancement

## [1.0.89] - 2025-11-19

### Added
- **WiiM logo as default cover art fallback**
  - When no valid cover art is available (e.g., web radio without artwork), the WiiM logo is automatically used as a fallback
  - `entity_picture` field now defaults to WiiM logo URL instead of None when cover art is missing or invalid
  - `fetch_cover_art()` automatically fetches WiiM logo when no URL is provided
  - Ensures consistent user experience with visible artwork in all playback scenarios
  - **Impact**: Home Assistant and other integrations will always have cover art to display

## [1.0.88] - 2025-11-19

### Changed
- **Refactored role tracking to use single source of truth**
  - Role (`solo`, `master`, `slave`) is now computed from Group object membership instead of maintaining separate `_detected_role` field
  - Eliminates dual representation that could get out of sync
  - Master with no slaves correctly reports as "solo"
  - Group structure is synced from device API during `refresh()` and updated optimistically during operations
  - **Impact**: More reliable role detection with simpler, more maintainable code

### Fixed
- **Fixed optimistic state updates for group operations**
  - Group membership changes now trigger immediate state change notifications to all group members (master + slaves)
  - Both Group object structure and role property update optimistically without polling
  - Fixes issue where role property was not updating after group operations
  - **Impact**: Home Assistant entities and other integrations receive immediate updates when group membership changes

### Added
- **Added test script for verifying optimistic group notifications**
  - New `scripts/test-optimistic-group-notification.py` demonstrates and verifies optimistic notification behavior
  - Shows exact timestamps of state change callbacks with millisecond precision
  - Validates that both master and slave receive immediate notifications during join operations
  - Useful for testing and debugging group state synchronization

## [1.0.87] - 2025-11-19

### Fixed
- **Fixed infinite recursion in Group volume and mute control**
  - Removed incorrect auto-delegation logic from `Player.set_volume()` and `Player.set_mute()` that caused infinite loop when called from `Group.set_volume_all()` / `Group.mute_all()`
  - Physical player methods now only control the device itself, not automatically trigger group-wide propagation
  - Group-level operations must be explicitly called via `Group` object methods
  - **Impact**: Group volume and mute operations now work correctly without hanging

### Changed
- **Simplified Player volume/mute API behavior**
  - `Player.set_volume()` now only sets volume on that specific device (no group propagation)
  - `Player.set_mute()` now only sets mute on that specific device (no group propagation)
  - Group-wide operations require explicit calls to `Group.set_volume_all()` or `Group.mute_all()`
  - Makes API behavior more explicit and predictable

### Added
- **Enhanced integration tests for multi-room group control**
  - Comprehensive test coverage for volume propagation with different device combinations (master is MAX, slave1 is MAX, slave2 is MAX, all equal)
  - Complete mute state permutation testing (all unmuted, all muted, mixed states)
  - Boundary testing (0.0, 0.40 max volume)
  - Tests include 5-second observation pauses for manual verification via WiiM app
  - All tests query device states directly (not cached) to confirm actual hardware changes

## [1.0.86] - 2025-11-18

### Fixed
- **Fixed solo/master/slave role detection in `get_device_group_info()`**
  - Now correctly checks if master info (both IP and UUID) points to the device itself before classifying as slave
  - Matches the logic used in `detect_role()` and the working Home Assistant integration
  - Fixes issue where master devices with master_uuid/master_ip pointing to themselves were incorrectly detected as slaves
  - **Impact**: Devices in groups now correctly identify as solo/master/slave, matching the behavior of the HA integration

## [1.0.85] - 2025-11-18

### Fixed
- **Fixed role detection logic to correctly identify master devices**
  - `get_device_group_info()` now checks if master info points to the device itself before treating it as a slave
  - `detect_role()` now correctly identifies master devices even when they have master_uuid/master_ip set to themselves
  - Fixed type error in `groupops.py` where `_detected_role` (str) was assigned to a Literal type variable
  - **Impact**: Master devices in groups are now correctly identified, fixing group operations and state synchronization

## [1.0.84] - 2025-11-18

### Fixed
- **Fixed timing issue where `on_state_changed` callback fires before Player properties are updated**
  - `update_from_upnp()` now ensures `_status_model` is fully synchronized with merged state before callbacks fire
  - All fields (including metadata like `media_title`, `media_artist`) are now updated from merged state, ensuring properties reflect latest data when callbacks fire
  - Fixes issue where callbacks would read `None` for metadata even though state had changed
  - **Impact**: Callbacks now have access to current Player properties (media_title, media_artist, etc.) when they fire, eliminating the need for workaround refresh calls

## [1.0.83] - 2025-11-18

## [1.0.82] - 2025-11-18

### Fixed
- **Monitor CLI now shows slaves for master devices even when Player objects aren't linked**
  - Monitor CLI now fetches and caches device group info to display slave information directly from device API
  - When a master device has slaves but Player objects aren't linked (e.g., when player_finder isn't available), monitor now shows slave count and IP addresses
  - Fixed display showing "Master (no slaves)" when slaves actually exist according to device API
  - **Impact**: Monitor CLI correctly displays multi-room group information even in single-device monitoring scenarios

## [1.0.81] - 2025-11-18

### Added
- **Automatic Player object linking when groups are detected on startup/refresh**
  - Added optional `player_finder` callback parameter to `Player` constructor
  - When `player_finder` is provided, library automatically links Player objects together when groups are detected during `refresh()`
  - Master players automatically find and link slave Player objects
  - Slave players automatically find and link to master Player object
  - New slaves are automatically linked when they appear
  - **Impact**: Volume propagation and group operations now work immediately on startup, not just after join/unjoin operations
  - **Usage**: Coordinators can provide `player_finder=lambda host: player_registry.get(host)` to enable auto-linking

### Fixed
- **Release script bug: CHANGELOG version numbering**
  - Fixed release script using `CURRENT_VERSION` instead of `NEW_VERSION` when updating CHANGELOG
  - CHANGELOG now correctly shows the new version number for releases

## [1.0.80] - 2025-11-18

### Fixed
- **Master volume and mute changes now propagate to all slaves in group**
  - When `set_volume()` is called on a master player with slaves, volume changes now propagate proportionally to ALL devices (master + slaves)
  - When `set_mute()` is called on a master player with slaves, mute changes now apply to ALL devices
  - Virtual master volume behavior: if master goes from 50% to 60% (+10 points), all slaves adjust by +10 points
  - Slave players maintain independent volume control (calling set_volume on slave only affects that device)
  - **Impact**: Home Assistant group entities now correctly adjust all devices when master/group volume is changed
  - **Breaking**: None - this fixes expected behavior that was documented but not implemented

## [1.0.79] - 2025-11-18

### Fixed
- Duplicate release (no changes - version numbering correction)

## [1.0.78] - 2025-11-18

### Fixed
- **Code quality: Fixed linting errors that bypassed pre-release checks**
  - Removed unused `group_changed` variable in `groupops.py` (F841 error)
  - Fixed line length violation in `statemgr.py` log message (E501 error - 128 > 120 chars)
  - Fixed syntax error in `test_models.py` (stray "1" character)
  - **Impact**: All code now passes Ruff linting checks in CI/CD pipeline
- **Tests: Fixed 12 failing tests related to v1.0.76 role detection architecture**
  - Updated tests to set `_detected_role` instead of relying on Group structure
  - Fixed group_helpers tests (5 tests) - build_group_state_from_players now checks _detected_role
  - Fixed player role tests (2 tests) - is_master/is_slave properties now check _detected_role
  - Fixed group operation tests (4 tests) - leave_group now checks _detected_role for is_solo
  - Fixed API test for get_multiroom_status to expect getSlaveList fallback response
  - **Impact**: Test suite now properly validates the v1.0.76 role detection architecture

### Documentation
- **Consolidated release documentation into single source of truth**
  - Merged `RELEASE_WORKFLOW.md` into `RELEASE_PROCESS.md`
  - Added guidelines for when to create RELEASE_NOTES files
  - Removed duplicate/conflicting documentation

## [1.0.78] - 2025-11-18

### Fixed
- **Available sources now include current non-physical sources**
  - Fixed `available_sources` not including active streaming services (AirPlay, Spotify, Amazon, etc.)
  - Fixed `available_sources` not including multi-room follower sources (e.g., "Master Bedroom")
  - Current source is now always included when active, even if not a physical input
  - Ensures Home Assistant can correctly display what's actually playing instead of showing "Unknown"
  - **Impact**: Source dropdown now shows physical inputs + current active source for proper UI state

### Changed
- **Source names now preserve original casing for proper UI display**
  - Removed lowercase normalization from `PlayerStatus.source` field
  - Source names now display as received: "AirPlay" not "airplay", "Spotify" not "spotify"
  - Multi-room sources preserve casing: "Master Bedroom" not "master bedroom"
  - **Impact**: Home Assistant UI now shows professionally-cased source names

## [1.0.77] - 2025-11-18

### Fixed
- **Slave players now receive ALL metadata from master**
  - When slave Player is linked to master via Group, copy all playback metadata during refresh
  - Copies: title, artist, album, cover art, play_state, position, duration
  - Source already set to master's name
  - All metadata cleared when device leaves group
  - **Impact**: Home Assistant slave entities now show correct track info, progress, and artwork

## [1.0.76] - 2025-11-18

### Changed
- **ARCHITECTURAL: Role detection consolidated to SINGLE source of truth**
  - **Problem**: Role was determined in 5 different places (role.py, group.py, groupops.py, base.py), all potentially out of sync
  - **Root cause**: `player.role` property checked Group.slaves (Python objects) instead of device API state
  - **Solution**: 
    - Added `player._detected_role` field updated during `refresh()` from device API state
    - `player.role` now returns `_detected_role` directly - ONE source of truth
    - Role comes from device API via `detect_role()` function, cached in Player
    - Group objects are for linking Player objects (HA), role is independent of Group
  - **Impact**: Role is always accurate whether monitoring one device or multiple devices
  - **Breaking**: None - external API unchanged, internal architecture cleaned up

### Documentation
- Added clear "Multiroom / Group Role" section to API_REFERENCE.md
- Updated HA_INTEGRATION.md with "Role vs Group Objects" explanation
- Documented that role comes from device state, Group objects are for linking

## [1.0.75] - 2025-11-18

### Fixed
- **Role detection consolidated to SINGLE source of truth**
  - **Problem**: Role was checked in 5 different places, all potentially out of sync
  - **Root cause**: `player.role` checked Group.slaves (Python objects) instead of device API state
  - **Solution**: Added `_detected_role` field set during refresh from device API via `detect_role()`
  - Role property now returns `_detected_role` - always accurate regardless of Group objects
  - Group objects are for linking Player objects (HA coordinator), role is independent
  - **Impact**: Role is always correct whether monitoring one device or multiple devices

## [1.0.74] - 2025-11-18

### Fixed
- **Multiroom group detection failure on firmware with null multiroom field**
  - Fixed `get_multiroom_status()` not detecting master devices when `getStatusEx` returns `multiroom: null`
  - Added automatic fallback to `multiroom:getSlaveList` endpoint when multiroom field is empty
  - Master devices now correctly report slave count and slave list even when firmware doesn't populate multiroom field
  - Affects WiiM firmware 4.8.731953 and potentially other versions
  - **Impact**: Monitor/CLI now correctly shows "master → slave" role, Home Assistant correctly tracks group membership
- **Group state synchronization not notifying slave players**
  - Fixed `_synchronize_group_state()` not calling `on_state_changed` callbacks when group membership changes
  - Added notifications to all group members when slaves are added/removed during automatic group sync
  - **Impact**: In Home Assistant, slave player entities now update immediately when master detects group changes

## [1.0.73] - 2025-11-18

### Fixed
- **Source persisting in Idle state after leaving group**
  - Fixed slaves showing stale master name as source when group disbanded while idle
  - Added explicit check to clear source field when device becomes solo and idle
  - Source now correctly shows as None (empty) after leaving group in idle state
  - Previously only worked if device was playing when leaving group
  - **Impact**: Home Assistant now shows correct empty source state for idle solo players

## [1.0.72] - 2025-11-18

### Fixed
- **Volume optimistic state update unit mismatch**
  - Fixed `set_volume()` passing incorrect format to state synchronizer (0.0-1.0 float instead of 0-100 int)
  - Caused Home Assistant to briefly display 0% volume before device confirmation corrected it
  - Volume changes now display correctly immediately without bouncing through zero

## [1.0.71] - 2025-11-18

### Added
- **Source-aware shuffle and repeat control**
  - Added `Player.shuffle_supported` property - checks if shuffle can be controlled on current source
  - Added `Player.repeat_supported` property - checks if repeat can be controlled on current source
  - Device-controlled sources: USB, Line In, Optical, Coaxial, Playlist, Preset, HTTP
  - External-controlled sources: AirPlay, Bluetooth, DLNA, Spotify, Tidal, Amazon Music, Qobuz, Deezer, iHeartRadio, Pandora, TuneIn, Multiroom

### Changed
- **BREAKING: Shuffle and repeat properties now return None for external sources**
  - `Player.shuffle_state` returns `None` instead of stale values when playing from AirPlay, Bluetooth, etc.
  - `Player.repeat_mode` returns `None` instead of stale values when playing from external sources
  - **Rationale**: External sources (AirPlay, Bluetooth, streaming services) control shuffle/repeat from the source app, not the WiiM device. Returning cached values is misleading.
  - **Technical Background**: LinkPlay/WiiM devices operate as a "Split Brain" system where control authority shifts based on transport protocol:
    - **AirPlay**: Device is passive sink; iOS device owns playback queue
    - **Spotify Connect**: Hybrid model; shuffle state managed by Spotify Cloud API, not local `setPlayerCmd:loopmode`
    - **Bluetooth/DLNA**: Source device/app controls transport
    - **USB/Local**: WiiM device is control point; full API control (subject to ~1000-2000 track RAM queue limit on A98 hardware)
  - The `setPlayerCmd:loopmode` endpoint in LinkPlay HTTP API is functional ONLY when device acts as control point
  - Sending shuffle/repeat commands to AirPlay or Spotify sessions either fails silently or updates a local register that has no effect on actual playback
  - See `docs/design/LINKPLAY_ARCHITECTURE.md` for comprehensive analysis of transport protocols and hardware constraints
  - Use `shuffle_supported` / `repeat_supported` to check before reading these properties
  - **BREAKING: set_shuffle() and set_repeat() now raise WiiMError for external sources**
  - Previously would send commands that did nothing or failed silently
  - Now raises clear error: "Shuffle/Repeat cannot be controlled when playing from '<source>'"
  - Prevents confusing behavior where commands appear to work but have no effect
  - For Spotify automation: Use Spotify Web API (`spotify.shuffle` service in HA) instead of LinkPlay API
  - For AirPlay automation: Control shuffle/repeat on source device (iOS/macOS)
  - Monitor CLI now displays "N/A (controlled by source)" for shuffle/repeat when playing from AirPlay, Bluetooth, etc.

### Fixed
- **Monitor now properly detects shuffle and repeat mode changes**
  - Added shuffle and repeat to state change tracking in `on_state_changed()`
  - Previously, changing shuffle/repeat would not appear in "Recent Events" or trigger state change counter
  - Monitor now shows shuffle/repeat changes in real-time when playing from supported sources

## [1.0.70] - 2025-11-18

### Changed
- **Play state normalization: "stop" now maps to "pause" for modern UX**
  - Devices reporting "stop" or "stopped" now appear as "paused" to users
  - Aligns with Home Assistant conventions (no STATE_STOPPED for media players)
  - Follows Sonos/soco library pattern (IDLE for empty queue, not STOPPED)
  - Rationale: Modern streaming devices maintain position whether "paused" or "stopped" - the distinction is meaningless to users
  - Affects: `Player.play_state` property, monitor CLI display, all state reporting
  - Impact: Monitor will now show "PAUSED" instead of "STOPPED" when playback is halted
  - Updated documentation: STATE_MANAGEMENT.md, API_REFERENCE.md

## [1.0.70] - 2025-11-18

### Fixed
- **All player control methods now use optimistic state updates and fire callbacks immediately**
  - Fixed shuffle/repeat methods (`set_shuffle()`, `set_repeat()`) to fire `on_state_changed` callbacks instead of calling `refresh()`
  - Fixed media control methods (`play()`, `pause()`, `resume()`, `stop()`, `next_track()`, `previous_track()`, `seek()`) to fire callbacks
  - Fixed playback methods (`play_url()`, `play_playlist()`, `play_notification()`, `play_preset()`, `clear_playlist()`) to fire callbacks
  - Fixed volume methods (`set_volume()`, `set_mute()`) to update state synchronizer and fire callbacks
  - Fixed audio configuration methods (`set_source()`, `set_audio_output_mode()`, EQ methods) to fire callbacks
  - Fixed Bluetooth methods (`connect_bluetooth_device()`, `disconnect_bluetooth_device()`) to fire callbacks
  - Removed all remaining `refresh()` calls from control methods (replaced with optimistic updates + callbacks)
  - Home Assistant integrations now receive instant UI updates (<1ms) for all player commands
  - Optimistic state updates ensure UI responsiveness before UPnP events or polling confirms changes

### Changed
- **Consistent state management pattern across all player control methods**
  - All state-changing methods now follow the pattern: Call API → Update cached state → Fire callback
  - Cached `_status_model` fields updated optimistically (play_state, volume, mute, loop_mode, source, eq_preset, position)
  - State synchronizer updated for volume/mute changes
  - Callbacks fire immediately after successful API calls, triggering coordinator listeners

### Documentation
- **Updated HA_INTEGRATION.md to reflect optimistic state update workflow**
  - Added "Optimistic State Updates + Callbacks" as primary state update mechanism (<1ms latency)
  - Documented that ALL player commands fire callbacks immediately, not just group operations
  - Updated examples to show three-layer state update: callbacks (instant) → UPnP (immediate) → polling (5-10s)
  - Clarified that UI updates happen instantly from cached state with no network delay

## [1.0.69] - 2025-11-18

### Added
- **Smart play/pause method for Home Assistant integration**
  - Added `player.media_play_pause()` method that intelligently handles play/pause/resume semantics
  - Automatically uses `resume()` when paused to avoid restarting streaming tracks from the beginning
  - Solves Issue #102 where `play()` restarts Amazon Music/Spotify tracks instead of resuming
  - Recommended for Home Assistant's `media_play_pause` service implementation
  - Follows HA media player conventions: resume when paused, pause when playing, play when stopped

### Changed
- **Enhanced media control method documentation**
  - Added comprehensive docstrings to `play()`, `pause()`, `resume()`, `stop()`, and `media_play_pause()` methods
  - Documented play vs resume behavior on streaming sources (play() may restart, resume() continues)
  - Documented WebRadio/WiFi stop() behavior (may not stay stopped, use pause() instead)
  - Added Home Assistant integration examples for proper usage

### Documentation
- **Added "Known Device Behaviors" section to README.md**
  - Documented play vs resume distinction for streaming sources (Spotify, Amazon Music, etc.)
  - Documented WebRadio/WiFi source stop behavior (Issues #49, #45)
  - Added workarounds and best practices for Home Assistant integrations
  - Explained that behaviors originate from LinkPlay firmware across all vendors
- **Updated HA_INTEGRATION.md with service mapping guide**
  - Added recommended service-to-method mapping table for media player services
  - Shows proper usage of play/pause/resume/stop/media_play_pause methods

## [1.0.68] - 2025-11-18

### Added
- **Device capability database for reliable input source detection**
  - Created `pywiim/device_capabilities.py` with device-specific input definitions
  - Database contains accurate physical input lists for WiiM Mini, Pro, Pro Plus, Amp, Ultra, and Arylic devices
  - Replaces unreliable `plm_support` bitmask with authoritative hardware-based input lists
  - Supports device-specific bit filtering (e.g., ignore USB bit for WiiM Pro where USB-C is power only)
  - Enables vendor-agnostic input detection across WiiM, Arylic, and generic LinkPlay devices

### Fixed
- **Corrected input source enumeration across all device types**
  - Fixed missing physical inputs (line_in, optical, coaxial) when `input_list` is None
  - `plm_support` bitmask is now recognized as unreliable across ALL vendors:
    - WiiM: Marks `plm_support` as "Reserved" in official docs (not a supported API field)
    - Arylic: Documents `plm_support` but firmware often reports incomplete/incorrect values
    - Reality: Tested devices show `plm_support` missing critical inputs like line_in
  - Fixed WiiM Pro incorrectly showing coaxial input (has Coax OUT only, not Coax IN)
  - Fixed WiiM Pro showing USB input (USB-C is power only, not audio input)
  - Fixed Arylic UP2STREAM_AMP_V4 missing line_in and optical (not in `plm_support`)
  - Fixed Arylic H50 missing line_in, optical, usb, phono, hdmi (not in `plm_support`)
  - Added device-specific filtering to remove spurious inputs reported by `plm_support`
  - Solution: Multi-layered approach using `plm_support` + `input_list` + device capability database

### Changed
- **Input source detection strategy updated to use device capability database**
  - When `input_list` is None (common for all tested devices), device database is now authoritative source
  - `plm_support` is parsed but filtered through device-specific ignore lists
  - Database augments incomplete `plm_support` data with known hardware capabilities
  - Logs debug warnings when `plm_support` parsing fails or contains unknown bits
  - Logs all set bits in `plm_support` to help identify new/undocumented bit mappings
- **Monitor CLI enhanced with input source debugging**
  - Now displays both `input_list` and `plm_support` raw values for troubleshooting
  - Shows `plm_support` bit breakdown with human-readable input names
  - Displays unknown bits separately to identify new input types on newer devices
  - Always shows available inputs (even when no current source active)
  - Marks current input in available sources list for clarity

### Documentation
- Added comprehensive comments in `device_capabilities.py` explaining why database is needed
- Documented that `plm_support` is "Reserved" per WiiM's official HTTP API documentation
- Noted that Arylic documents `plm_support` but firmware implementation is incomplete/unreliable
- Updated property docstrings to clarify device capability database as source of truth

## [1.0.67] - 2025-11-18

### Added
- **Real device testing tools for playback controls**
  - Added `scripts/test-playback-controls.py` - Automated test script for play/pause/shuffle/repeat verification
  - Added `scripts/interactive-playback-test.py` - Interactive menu-driven testing tool
  - Both scripts verify Player object playback control methods against real hardware
- Added `docs/testing/REAL-DEVICE-TESTING.md` - Comprehensive guide for testing against real devices
- Updated `scripts/README.md` with documentation for new playback control test scripts

## [1.0.66] - 2025-11-18

### Added
- **Active position timer for smooth media position updates**
  - Background async task updates position every 1 second while playing
  - Automatically triggers `on_state_changed` callback when position changes
  - Provides smooth UI updates for clients displaying media position (e.g., Home Assistant media player)
  - Timer automatically starts when playback begins and stops when paused/stopped
  - Handles track changes and seeks by resetting timer appropriately
  - Follows Python asyncio best practices with proper task management and cleanup
  - Gracefully degrades to lazy calculation if no event loop is available (sync context)

### Changed
- **Position tracking now uses active timer instead of lazy calculation**
  - Position updates automatically every 1 second while playing (not just on property access)
  - Integrations receive automatic callbacks for position changes without needing to poll
  - Improves user experience with smooth, real-time position updates in UI

### Documentation
- **Updated STATE_MANAGEMENT.md with active timer implementation details**
  - Documented hybrid position tracking with active timer
  - Added implementation details and lifecycle management
  - Explained automatic callback mechanism for UI updates

## [1.0.65] - 2025-11-18

### Added
- **Player now caches ALL state internally - integrations no longer need separate caching**
  - Added `player.eq_presets` property: List of available EQ preset names (cached during refresh)
  - Added `player.metadata` property: Audio quality metadata (bitrate, sample rate, codec info) (cached during refresh)
  - Added `player.audio_output_status` property: Full audio output status dict (exposes existing cache)
  - StateManager.refresh() now automatically fetches and caches eq_presets and metadata if supported
  - All data fetched conditionally based on device capabilities (no unnecessary calls)
  - Integrations now access ALL state via player properties - no manual fetching needed

### Changed
- **Simplified integration pattern: "Call refresh(), read properties, that's it!"**
  - Integrations should NOT manually call get_eq_presets(), get_meta_info(), get_audio_output_status()
  - All state is automatically fetched and cached during player.refresh()
  - Data dict should be built entirely from player properties, not separate fetch calls
  - This eliminates integration-side caching and reduces code complexity

### Documentation
- **Reinforced "pywiim manages all state internally" design philosophy**
  - Integrations should never cache state separately - Player is the single source of truth
  - Clear separation: pywiim owns state management, integrations own scheduling

### Benefits
- **Simpler integration code**: No manual fetching or caching needed
- **Single source of truth**: All state lives in Player object
- **Atomic state updates**: All state fetched together during refresh()
- **No integration-side cache**: Eliminates cache management code in integrations
- **Framework-agnostic**: Works identically for HA, CLI, scripts, etc.

## [1.0.64] - 2025-11-18

### Changed
- **Group operations now automatically notify ALL group members**
  - join_group(), leave_group(), and disband() now call on_state_changed callback on all affected players
  - Previously only notified the directly involved players (joiner + master)
  - Now notifies all members of the new group AND all members of the old group (if applicable)
  - Ensures all coordinators/integrations receive immediate state updates for all group members
  - Integration developers no longer need to call async_force_multiroom_refresh() after group operations
  - All group member UIs update immediately without any manual refresh calls
  - This aligns with the "pywiim manages all state internally" design philosophy

### Documentation
- **Updated group operation documentation across all docs**
  - Clarified that async_force_multiroom_refresh() is no longer needed for group operations
  - Updated HA_INTEGRATION.md with automatic group-wide notification details
  - Updated OPERATION_PATTERNS.md to document the notification strategy
  - Added clear explanation of which players receive callbacks during group operations

### Benefits
- **Simpler integration code**: No need to track and refresh all group members manually
- **More reliable**: Can't forget to notify other group members
- **Better UX**: All group member UIs update immediately
- **Framework-agnostic**: Works automatically for any integration (HA, CLI, scripts)

## [1.0.63] - 2025-11-18

### Changed
- **Removed internal refresh() calls from Player command methods for faster execution**
  - Play, pause, resume, seek, play_url, play_playlist, and play_preset no longer call refresh() internally
  - Commands now execute ~2x faster (single HTTP call instead of command + refresh)
  - State updates happen via UPnP events (immediate) and coordinator polling (5-10 seconds)
  - This eliminates redundant network calls and potential race conditions with UPnP events
  - Integration developers should NOT call async_request_refresh() after Player commands
  - For one-off scripts without polling, users can explicitly call await player.refresh() when needed

### Added
- **Comprehensive documentation for state management pattern**
  - Updated OPERATION_PATTERNS.md with explicit refresh() usage guidelines
  - Added "Player Command Methods - No Manual Refresh Required" section to HA_INTEGRATION.md
  - Added "When to Use refresh()" section to API_REFERENCE.md
  - Clear examples showing when to use explicit refresh (scripts, testing) vs when not to (integrations)
  - Documents the three-layer state update system: UPnP events, coordinator polling, explicit refresh

### Performance
- **Significant performance improvement for multiroom operations**
  - create_group(), join_group(), and other operations are faster without internal refresh calls
  - Commands that previously took multiple seconds now complete in <1 second
  - Reduced network traffic by eliminating double HTTP calls

## [1.0.62] - 2025-11-18

### Fixed
- **Cover art fetching from HTTPS device URLs now works correctly**
  - Fixed `fetch_cover_art()` to use client's SSL context for HTTPS artwork URLs
  - WiiM devices serve artwork via HTTPS with self-signed certificates
  - Previously failed silently (returned None) when fetching from device HTTPS URLs
  - Now properly disables certificate verification for device artwork URLs
  - External artwork URLs (Spotify, Tidal, etc.) continue to use standard SSL verification
  - Tested successfully with AirPlay artwork on WiiM Pro devices

### Changed
- **Reduced repetitive debug logging to minimize noise**
  - Removed automatic logging of full HTTP responses on every poll (api/base.py)
  - Removed metadata parsing debug logs that occurred on every status fetch (api/parser.py)
  - Removed AirPlay-specific debug logging that occurred on every poll for AirPlay sources
  - These changes significantly reduce log spam when DEBUG logging is enabled
  - Important events (track changes, errors, state transitions) are still logged appropriately
  - Raw data remains available for debugging but is not automatically logged on every poll cycle

### Added
- **Logging best practices documentation**
  - Added comprehensive logging guidelines in `docs/LOGGING_BEST_PRACTICES.md`
  - Documents when and how to use each log level (ERROR, WARNING, INFO, DEBUG)
  - Provides examples of good vs. bad logging patterns
  - Explains anti-patterns to avoid (logging on every poll, logging unchanged values)
  - Includes integration-specific guidelines for Home Assistant and other frequent pollers
  - Philosophy: "Log when it matters, not on every poll"

## [1.0.61] - 2025-11-18

### Changed
- Version bump (no functional changes)

## [1.0.60] - 2025-11-18

### Fixed
- **Alarm clock (setAlarmClock) now handles non-JSON responses gracefully**
  - Fixed `WiiMResponseError` when setting alarms on WiiM devices that return plain "OK" text instead of JSON
  - Added `setAlarmClock` to the whitelist of commands that can return non-JSON or empty responses
  - Device behavior: WiiM devices return plain text "OK" for successful alarm configuration instead of JSON
  - The library now treats "OK" and empty responses from `setAlarmClock:*` commands as success (`{"raw": "OK"}`)
  - Affects all alarm operations: daily alarms, one-time alarms, weekly alarms, monthly alarms
  - See WiiM HTTP API documentation: https://www.wiimhome.com/pdf/HTTP%20API%20for%20WiiM%20Products.pdf

## [1.0.59] - 2025-11-17

### Fixed
- **Slave devices now clear metadata and artwork when leaving a group**
  - When a slave leaves a multiroom group, metadata (title, artist, album) and artwork (entity_picture, cover_url) are now cleared
  - Prevents stale group playback information from persisting on slave after leaving
  - Device will show WiiM default state (no metadata/artwork) instead of outdated track information
  - Applies to both status model and state synchronizer to prevent refresh() from restoring stale data
- **Source enumeration now combines all available information sources**
  - Fixed missing physical inputs (Line In, Optical, etc.) when device firmware's `input_list` was incomplete
  - Now combines device's `input_list` + hardware capability bitmask (`plm_support`) + model-based detection
  - Previous behavior: Trusted `input_list` exclusively and returned immediately, missing inputs not reported by firmware
  - New behavior: Augments `input_list` with `plm_support` bitmask to catch inputs firmware forgot to report
  - Returns physical inputs (Line In, USB, Bluetooth, Optical, Coaxial, HDMI) + current streaming source (if active)
  - Current streaming service (Spotify, AirPlay, DLNA, etc.) included only when active for proper Home Assistant state display

## [1.0.55] - 2025-01-17

### Added
- **Unified output selection with Bluetooth device support** (Issues [mjcumming/wiim#79](https://github.com/mjcumming/wiim/issues/79), [#86](https://github.com/mjcumming/wiim/issues/86))
  - New property `bluetooth_output_devices`: Lists paired Bluetooth output devices (Audio Sinks only)
    - Returns list of dicts with `name`, `mac`, `connected` keys
    - Automatically filters out Audio Source devices (input devices like phones)
  - New property `available_outputs`: Combines hardware output modes with paired BT devices
    - Hardware modes: "Line Out", "Optical Out", "Coax Out", "Bluetooth Out", "Headphone Out", "HDMI Out"
    - Paired devices: "BT: Device Name" format
    - Example: `["Line Out", "Optical Out", "BT: Sony Speaker", "BT: JBL Headphones"]`
  - New method `player.audio.select_output(name)`: Smart output selection
    - Hardware mode: `await player.audio.select_output("Optical Out")`
    - Specific BT device: `await player.audio.select_output("BT: Sony Speaker")`
    - Automatically sets hardware mode to Bluetooth and connects to device
  - Bluetooth history fetched during `player.refresh()` with 60-second cache (pairing rarely changes)
  - Enables automation scenarios like "When movie starts, switch to BT soundbar"
  - Eliminates need for WiiM app to select outputs and connect BT devices

### Fixed
- **Source switching (switchmode) now handles empty/non-JSON responses gracefully**
  - Fixed `WiiMResponseError` when switching to certain sources (e.g., Bluetooth) that return empty responses
  - Added `switchmode` to the whitelist of commands that can return empty or non-JSON responses
  - Device behavior: Some WiiM devices return empty responses for successful source switches instead of JSON
  - The library now treats empty responses from `switchmode:*` commands as success (`{"raw": "OK"}`)

### Changed
- **Smart filtering of `available_sources` property**
  - Now filters out unconfigured streaming services (Spotify, Tidal, Amazon, Qobuz, Deezer, Pandora, iHeartRadio, TuneIn)
  - Only returns physical/hardware sources (USB, Bluetooth, AirPlay, DLNA, Optical, Coax, Aux, HDMI) by default
  - Includes streaming services only if they're the currently active source
  - AirPlay and DLNA always included as they don't require account configuration
  - Integration code no longer needs workarounds to filter out unusable sources
- **Major refactoring: Player class modularization**
  - Refactored monolithic `player.py` (2,592 lines) into clean modular structure with 12 focused modules (2,485 lines total)
  - Created `pywiim/player/` package with clear separation of concerns:
    - `base.py` (5.4K) - Core initialization and basic properties
    - `statemgr.py` (14K) - State management, refresh, and UPnP integration
    - `volume.py` (1.4K) - Volume and mute control
    - `media.py` (5.6K) - Media playback control
    - `audio.py` (4.8K) - Audio configuration (EQ, LED, output modes)
    - `playback.py` (2.8K) - Shuffle, repeat, and loop modes
    - `coverart.py` (4.5K) - Cover art fetching and caching
    - `properties.py` (19K) - All property getters (media metadata, status)
    - `groupops.py` (9.0K) - Group operations (create, join, leave)
    - `diagnostics.py` (6.6K) - Diagnostics collection
    - `bluetooth.py` (1.6K) - Bluetooth operations
  - **Zero breaking changes**: All existing code works unchanged, imports remain the same
  - **All 708 unit tests pass**: Complete test coverage maintained
  - **Improved maintainability**: Each module has clear, single responsibility (60-500 lines each)
  - **Better code organization**: Find and navigate code faster with logical grouping
  - **Enhanced type safety**: All type hints properly resolved, mypy compliant
  - **Updated package configuration**: Added `pywiim.player` to setuptools packages

## [1.0.52] - 2025-01-16

### Added
- **Cover art fetching and caching**: Added direct cover art image fetching to Player class
  - New methods: `fetch_cover_art(url=None)` and `get_cover_art_bytes(url=None)`
  - Automatic in-memory caching (max 10 images per player, 1 hour TTL)
  - Uses client's HTTP session for fetching, creates temporary session if needed
  - Handles expired URLs gracefully and provides more reliable cover art than using URLs directly
  - Returns both image bytes and content type for integration use
  - Cache cleanup automatically removes expired entries
  - Updated Home Assistant integration documentation with `async_get_media_image()` example
  - Updated API reference with cover art methods and features

### Changed
- Updated Home Assistant integration guide with cover art handling section
  - Documents when to use direct image fetching vs URL-based approach
  - Provides example implementation for `async_get_media_image()` method
  - Explains benefits of caching and reliability improvements

## [1.0.51] - 2025-01-16

### Changed
- **CI/CD workflow**: Removed redundant `release` trigger from PyPI publish workflow
  - Workflow now only triggers on version tags (v*), which is sufficient for automated publishing
  - Simplifies workflow configuration and avoids duplicate triggers

## [1.0.50] - 2025-11-16

### Changed
- Version bump (no functional changes)

## [1.0.49] - 2025-11-16

### Added
- **Player repeat control method**: Added `set_repeat(mode)` method to Player class
  - Completes the shuffle/repeat API abstraction alongside `set_shuffle()`
  - Accepts "off", "one", or "all" as repeat mode values
  - Automatically preserves current shuffle state when changing repeat mode
  - Covers all 6 valid loop modes (0=normal, 1=repeat_one, 2=repeat_all, 4=shuffle, 5=shuffle+repeat_one, 6=shuffle+repeat_all)
  - Updated Home Assistant integration documentation with `set_repeat()` examples and service method implementations

### Fixed
- **setLoopMode response handling**: Fixed handling of empty/non-JSON responses for `setLoopMode` commands
  - Some devices (especially Audio Pro or certain firmware versions) return empty or non-JSON responses for shuffle/repeat commands
  - Added `setLoopMode` to the list of commands that gracefully handle empty/non-JSON responses (like `reboot` and `eqload`)
  - Prevents `WiiMResponseError` when devices return empty responses for shuffle/repeat operations
  - Resolves integration errors: "Invalid JSON response from setLoopMode: Expecting value: line 1 column 1 (char 0)"

### Changed
- Updated Home Assistant integration documentation:
  - Added `set_repeat()` to control helpers section with usage examples
  - Added `MediaPlayerEntityFeature.SHUFFLE_SET` and `REPEAT_SET` to supported features
  - Added `async_set_shuffle()` and `async_set_repeat()` service method implementation examples
  - Documented that both methods preserve the other setting and handle device response variations

## [1.0.48] - 2025-11-16

### Fixed
- **Role detection fix**: Fixed `Player.role` property to correctly identify solo devices
  - A master must have at least one slave - if a group exists but has no slaves, the device is now correctly identified as "solo"
  - Prevents incorrect "master" role assignment when a device is in an empty group
  - Role detection now properly handles edge case where group exists but has no members

### Changed
- **Monitor CLI refactoring**: Simplified role state management and group info handling
  - Removed redundant role state tracking - now uses `Player.role` directly (single source of truth)
  - Simplified group info caching to only track fetch timing, not duplicate data
  - Improved role change detection to use Player's authoritative role property
  - Added source name formatting helper for better display of input sources (handles acronyms like DLNA, USB, HDMI)
  - Code cleanup: removed duplicate state storage that was redundant with Player's internal state

### Removed
- Moved `test_eqlists_inputs.py` from project root to `scripts/` directory for better organization

## [1.0.47] - 2025-11-16

### Added
- **Discovery performance optimization**: Added quick filtering to skip validation of known non-LinkPlay devices
  - Uses SSDP `SERVER` headers to identify non-LinkPlay devices (Chromecast, Denon Heos, Sony, Kodi, etc.) before validation
  - Conservative approach: Only filters devices we're 100% certain are not LinkPlay-compatible
  - Generic "Linux" headers (used by Audio Pro, Arylic, WiiM) pass through to validation for safety
  - Reduces discovery time by 50-70% when non-LinkPlay devices are present on the network
  - Added `ssdp_response` field to `DiscoveredDevice` for internal filtering (not serialized in `to_dict()`)
  - Updated discovery documentation with performance optimization details
- **Complete Player high-level API**: Added all missing methods to Player class so integrations never need to access `player.client.*`
  - **Control helpers**: `clear_playlist()`, `set_shuffle(enabled)`, `set_led(enabled)`, `set_led_brightness(brightness)`, `set_channel_balance(balance)`, `sync_time(ts)`
  - **Status/metadata fetchers**: `get_multiroom_status()`, `get_audio_output_status()`, `get_meta_info()`
  - **Bluetooth workflow**: `get_bluetooth_history()`, `connect_bluetooth_device(mac)`, `disconnect_bluetooth_device()`, `get_bluetooth_pair_status()`, `scan_for_bluetooth_devices(duration)`
  - **Connection info properties**: `port`, `timeout` (read-only properties)
  - All methods properly documented with full signatures and examples
  - Updated HA integration guide and API reference to reflect complete Player API
  - Updated monitor CLI to use Player methods directly instead of `player.client.*`
- **Home Assistant integration documentation**: Added comprehensive "Division of Responsibilities" section to `HA_INTEGRATION.md`
  - Clarifies who controls polling schedule (HA), who recommends intervals (pywiim), and who orchestrates (integration)
  - Documents responsibility matrix for polling, updates, and roles
  - Explains design patterns used (Strategy, Template Method, Observer, State Synchronization)
  - Provides best practices and flow diagrams for integration developers
  - Ensures clear separation of concerns between framework, library, and integration layers

### Removed
- Removed `POLLING_STRATEGY_ANALYSIS.md` design document (feature has been implemented)

### Changed
- Updated documentation references to point to `HA_INTEGRATION.md` for polling strategy information

## [1.0.39] - 2025-01-15

### Changed
- **Protocol detection improvements**: Enhanced endpoint discovery with lazy probing
  - Endpoint is now probed and cached on first use rather than at initialization
  - Supports optional `port` and `protocol` parameters for explicit configuration
  - Improved handling of IPv6 addresses and port parsing
  - More efficient connection establishment with better error handling
- **API client refactoring**: Simplified BaseWiiMClient initialization and endpoint management
  - Removed hardcoded protocol priority assumptions
  - Endpoint caching now persists for the lifetime of the client instance
  - Better separation of concerns between discovery and connection

### Removed
- Removed obsolete design documentation files (consolidation analysis, design summaries)
- Cleaned up outdated design documents to reduce repository clutter

### Fixed
- Improved Home Assistant integration documentation with updated examples
- Enhanced group test CLI with better error handling and state management

## [1.0.36] - 2025-11-15

### Changed
- **Presets removed from inputs list**: Presets are no longer included in `Player.available_sources`
  - Presets should be handled via media browser functionality, not as selectable input sources
  - Use `client.get_presets()` to retrieve preset list and `player.play_preset(preset_number)` to play them
  - This aligns with Home Assistant's media player architecture where presets are browsable content
- **Preset count detection**: `get_max_preset_slots()` now uses `preset_key` from API only
  - Removed fallback that inferred max slots from preset list (which only shows configured presets)
  - Defaults to 6 slots only if `preset_key` is not available from the API
  - Supports up to 20 presets as determined by device's `preset_key` field

### Added
- Monitor CLI: Added preset count display in device info (e.g., "Presets: 20")
  - Preset count is fetched every 60 seconds when presets are supported
  - Shows maximum number of preset slots supported by the device

### Fixed
- Fixed group operation tests to use separate client instances for master and slave players
  - Tests now properly mock multiroom status and player status for each player independently

## [1.0.35] - 2025-11-15

### Added
- StateSynchronizer: Local timer-based position estimation for smooth position updates between polls/events
  - Position is estimated locally using elapsed time when playing
  - Provides smooth position updates between HTTP polls and UPnP events
  - Automatically corrects on track changes, seeks, and periodic polling
- Added missing Player properties for Home Assistant integration:
  - `Player.shuffle` - Shuffle state (bool | None, alias for shuffle_state)
  - `Player.repeat` - Repeat mode (str | None, alias for repeat_mode)
  - `Player.wifi_rssi` - Wi-Fi signal strength in dBm (int | None)
  - `Player.eq_preset` - Already existed, now documented for integration use
- **Slave source handling**: Enhanced source display for slave devices in multiroom groups
  - Slave devices now show master device name instead of "multiroom" placeholder
  - Automatically resolves master name from Group object or master_ip
  - Source is automatically cleared when device leaves group and becomes solo
  - Improved source tracking for better Home Assistant integration
- **Group volume control improvements**: Enhanced volume synchronization for multiroom groups
  - Virtual master volume calculation (MAX of all devices in group)
  - Absolute volume change distribution across all devices in group
  - Proper volume initialization when all devices are at 0
  - Explicit mute state management (mute states do not propagate between devices)
- Updated Home Assistant integration guide with new property examples
- Monitor CLI TUI mode: Fixed-window display that updates in place (no scrolling)
  - Comprehensive player information display (device info, playback status, track info, EQ, audio I/O, grouping, network)
  - Progress bar visualization for track position
  - Recent events log (last 5 events: state changes, group joins/unjoins)
  - Use `--no-tui` flag to disable TUI mode and use scrolling log instead
- Monitor CLI group join/unjoin detection: Automatically detects and logs when players join or leave groups
- Monitor CLI adaptive polling: Automatically increases polling frequency when UPnP events are not working
  - Polls every 1 second when playing without UPnP events (instead of relying on stale UPnP data)
  - Fetches EQ data every 5 seconds when UPnP not working (instead of every 30 seconds)

### Fixed
- Monitor CLI EQ preset display: Now correctly shows current EQ preset from `get_eq()` API response
  - Previously showed stale "flat" preset from cached status model
  - Now reads preset from actual EQ data with fallback to status model
  - Handles preset name variations (e.g., "hiphop" vs "hip-hop")
- Monitor CLI input display: Added dedicated Input section showing current input and available inputs
- StateSynchronizer: Improved metadata handling for Spotify source
  - Spotify requires UPnP events for metadata as HTTP API does not provide metadata when Spotify is active
  - Updated documentation and code comments to clarify Spotify metadata dependency on UPnP events
  - Without UPnP events, Spotify metadata will be unavailable

### Changed
- **StateSynchronizer metadata handling**: Improved metadata field tracking
  - Metadata fields (title, artist, album, image_url) are now always present in state (even if None)
  - Prevents stale metadata from persisting when tracks change
  - Better synchronization between HTTP and UPnP metadata sources
- **Player refresh() method**: Enhanced state merging and source management
  - Cached status_model now reflects merged state from both HTTP and UPnP sources
  - Automatic source replacement for slaves (multiroom → master name)
  - Automatic source clearing when device transitions from slave to solo
  - Better handling of None values in metadata fields
- Monitor CLI: EQ data is now fetched in all modes (not just TUI mode) for accurate state updates
- StateSynchronizer: Enhanced metadata priority logic with Spotify-specific handling
- UPnP integration: Updated position/duration handling documentation
  - Clarified that UPnP events provide position/duration when track starts (not continuously)
  - Position is estimated locally during playback with periodic HTTP polling to correct drift
  - Updated all documentation to reflect correct UPnP event behavior

### Removed
- Removed deprecated `UpnpEventer.is_upnp_working()` method
  - Method was fundamentally flawed (UPnP has no heartbeat, can't reliably detect health)
  - Removed associated unit tests
  - Updated diagnostics documentation to remove references
  - Kept practical heuristics (playing-state detection) and resubscription failure detection

## [1.0.22] - 2025-11-14

### Changed
- `Player.available_sources` now filters out WiFi from input sources list
- WiFi is excluded as it's not a selectable source (it's the network connection that enables other services)
- Only selectable input sources (bluetooth, line_in, optical, etc.) are now returned

## [1.0.21] - 2025-11-14

### Added
- Queue management support via UPnP AVTransport actions:
  - `Player.add_to_queue(url, metadata="")` - Add URL to end of queue
  - `Player.insert_next(url, metadata="")` - Insert URL after current track
  - `Player.play_url(url, enqueue="add|next|replace|play")` - Play URL with optional enqueue support
- `upnp_client` parameter to `Player.__init__()` for queue management and UPnP operations
- Comprehensive queue management tests (10 new test cases)
- Updated Home Assistant integration guide with queue management documentation

### Changed
- Reduced SSL client certificate loading log level from INFO to DEBUG (expected behavior for Audio Pro devices)

## [1.0.19] - 2025-11-14

### Added
- Comprehensive unit test coverage improvements:
  - Added 50+ tests for `player.py` module (coverage increased from 48% to 79%)
  - Added tests for media metadata properties (duration, position, title, artist, album, image URL)
  - Added tests for shuffle and repeat mode detection
  - Added tests for audio output mode properties and available modes
  - Added tests for device info properties (model, firmware, MAC, UUID)
  - Added tests for playback methods (play_playlist, play_notification, play_preset, set_source, set_audio_output_mode)
  - Added tests for EQ methods (set_eq_preset, set_eq_custom, set_eq_enabled)
  - Added tests for diagnostics collection (comprehensive, with UPnP, with groups, error handling)
  - Added tests for refresh error handling and media position estimation
  - Added tests for group operations edge cases
- All 127 unit tests now passing

### Changed
- Improved test coverage for critical Player class functionality
- Enhanced test suite reliability and maintainability

## [1.0.18] - 2025-11-14

### Fixed
- Fixed scene restoration failure when restoring EQ preset settings
- EQLoad commands now gracefully handle empty or non-JSON responses (similar to reboot commands)
- Resolves issue where some devices (e.g., up2stream pro) return invalid JSON for EQLoad:Flat command
- Scene restoration with media players that include EQ preset state now works correctly

## [1.0.17] - 2025-11-14

### Changed
- Reorganized README to prioritize CLI tools section (moved after Installation)
- Added comprehensive Windows-specific installation and usage instructions
- Added "Getting Started with CLI Tools (Windows)" section with step-by-step guide
- Enhanced Installation section with Windows prerequisites and PATH configuration notes
- Improved documentation structure for better user onboarding
- Discovery logic now separates UPnP description port from HTTP API port
- Enhanced discovery logging to show both UPnP port and API port for clarity
- Updated validation to use standard HTTP API port (80) regardless of SSDP discovery port

### Fixed
- Fixed SSDP discovery to use port 80 for HTTP API instead of UPnP description port (49152)
- Port 49152 is now correctly recognized as UPnP description port only, not for API calls
- Discovery now properly validates WiiM devices by connecting to the correct API port
- Improved protocol priority handling based on discovered protocol (HTTP vs HTTPS)

## [1.0.15] - 2025-11-14

### Added
- Automated release script (`scripts/release.sh`) for linting, version bumping, and pushing
- PyPI publishing automation on version tags

### Changed
- Improved CI workflow with proper formatting, linting, and testing steps
- Enhanced release process documentation

## [1.0.14] - 2025-01-15

### Fixed
- Fixed custom EQ command format: Changed from `setEQ:custom:` to `EQSetBand:` (correct LinkPlay API format)
- Fixed LMS integration test to mark as "not supported" instead of failed when device doesn't support it
- Fixed f-string linting error in verify_cli.py

### Changed
- Improved verify CLI test suite:
  - Removed LED test (no safe read-only test available)
  - Converted all "skipped" tests to "not_supported" category for clearer results
  - Removed empty input_list warning (expected behavior)
  - Better source switching test with playback state handling
  - All tests now have clear results: Passed, Failed, or Not supported (no skipped tests)

## [1.0.13] - 2025-11-14

### Fixed
- Fixed SSL context handling in protocol fallback to lazily obtain SSL context when missing
- Fixed test failures in retry logic tests by allowing protocol probing to continue when SSL context is None
- Fixed all mypy type checking errors (64 errors resolved)
- Added proper type annotations for `slave_hosts` lists in role detection and group APIs
- Fixed `Optional` attribute access with proper `None` checks in base API client
- Added type casts for JSON responses to satisfy mypy's `no-any-return` checks
- Fixed type annotations for dictionary variables in UPnP eventer
- Removed unused `type: ignore` comments throughout codebase
- Fixed variable redefinition issues in CLI tools
- Added proper type annotations for SSL context handling

### Changed
- Improved type safety across the entire codebase
- Enhanced type checking in CI pipeline (now passes with 0 errors)

## [1.0.10] - 2025-11-13

### Fixed
- Fixed linting errors: removed unused variables and imports
- Fixed line length violations in verify_cli.py and test files
- Fixed f-string formatting issues in integration tests
- Removed trailing whitespace in documentation strings

## [1.0.9] - 2025-11-13

### Added
- Comprehensive features documentation in README
- Detailed CLI tools documentation with usage examples and options
- Acknowledgments section crediting libraries and resources that provided API information
- Documentation for all four CLI tools: `wiim-discover`, `wiim-diagnostics`, `wiim-monitor`, `wiim-verify`

### Changed
- Enhanced README with complete feature list organized by category
- Expanded CLI tools section with detailed usage instructions, options, and example outputs
- Improved documentation structure for better discoverability

## [1.0.8] - 2025-11-13

### Added
- `wiim-monitor` CLI tool for real-time device monitoring
- Adaptive polling strategy with UPnP event support in monitor tool
- Real-time playback state, volume, and track information display
- Device role detection (solo/master/slave) in monitor
- Statistics tracking for HTTP polls and UPnP events

### Changed
- Enhanced diagnostics tool with improved data collection
- Improved verify CLI tool with better error handling and reporting
- Refined discovery module with better validation and error handling
- Updated documentation for monitor tool and UPnP setup

### Fixed
- Improved error handling in CLI tools
- Better network detection for UPnP callback URLs

## [1.0.7] - 2025-11-13

### Added
- Hybrid position tracking system for smooth playback position updates
- Local position estimation during playback (reduces network traffic by 80%)
- Automatic seek detection and position correction
- Comprehensive documentation for hybrid position tracking approach

### Changed
- Polling interval during playback: 1 second → 5 seconds (with hybrid estimation)
- `media_position` property now uses hybrid estimation for smooth updates
- Position updates are now continuous (estimated) rather than discrete (polled)
- Improved position tracking accuracy with automatic drift correction

### Fixed
- Fixed double-counting bug in UPnP event statistics
- Position updates now handle seeks and track changes correctly
- Reduced network overhead during continuous playback

## [1.0.6] - 2025-11-13

### Added
- `wiim-verify` CLI tool for testing all device features and endpoints
- Comprehensive feature verification suite with safety constraints (volume max 10%)
- State save/restore functionality to prevent disruption during testing
- Feature testing for all device capabilities (playback, volume, source, EQ, presets, etc.)

### Changed
- Version bumped to 1.0.6

## [1.0.5] - Previous

### Added
- Device discovery module with SSDP/UPnP and network scanning
- `wiim-discover` CLI tool for discovering devices
- Comprehensive discovery documentation
- `DiscoveredDevice` model for discovered devices
- Discovery API functions (`discover_devices`, `discover_via_ssdp`, `scan_network`, `validate_device`)
- Audio Pro response handling module (`api/audio_pro.py`)
- SSL/TLS context management module (`api/ssl.py`)
- PEP 561 type marker (`py.typed`)

### Changed
- Updated public API exports to include discovery functions
- Enhanced README with discovery tool information
- Refactored `api/base.py` (reduced from 988 to 755 lines, 24% reduction)
- Improved error handling with device context in error messages
- Enhanced type hints across codebase (replaced `Any` with proper types)
- Added pragma comments for justified large cohesive files

### Fixed
- Improved error logging with device context (host, model, firmware)
- Better type safety with proper type hints in key modules

## [1.0.0] - 

### Added
- Initial release of pywiim library
- HTTP API client with all mixins (12 API modules)
- UPnP client and event handling
- Capability detection system
- State synchronization
- Diagnostic tool (`wiim-diagnostics`)
- Comprehensive test suite
- Full documentation

[1.0.62]: https://github.com/mjcumming/pywiim/compare/v1.0.61...v1.0.62
[1.0.61]: https://github.com/mjcumming/pywiim/compare/v1.0.60...v1.0.61
[1.0.60]: https://github.com/mjcumming/pywiim/compare/v1.0.59...v1.0.60
[1.0.59]: https://github.com/mjcumming/pywiim/compare/v1.0.55...v1.0.59
[1.0.55]: https://github.com/mjcumming/pywiim/compare/v1.0.52...v1.0.55
[1.0.52]: https://github.com/mjcumming/pywiim/compare/v1.0.51...v1.0.52
[1.0.51]: https://github.com/mjcumming/pywiim/compare/v1.0.50...v1.0.51
[1.0.50]: https://github.com/mjcumming/pywiim/compare/v1.0.49...v1.0.50
[1.0.49]: https://github.com/mjcumming/pywiim/compare/v1.0.48...v1.0.49
[1.0.48]: https://github.com/mjcumming/pywiim/compare/v1.0.47...v1.0.48
[1.0.47]: https://github.com/mjcumming/pywiim/compare/v1.0.46...v1.0.47
[1.0.39]: https://github.com/mjcumming/pywiim/compare/v1.0.38...v1.0.39
[Unreleased]: https://github.com/mjcumming/pywiim/compare/v1.0.62...HEAD
[1.0.38]: https://github.com/mjcumming/pywiim/compare/v1.0.36...v1.0.38
[1.0.36]: https://github.com/mjcumming/pywiim/compare/v1.0.35...v1.0.36
[1.0.35]: https://github.com/mjcumming/pywiim/compare/v1.0.34...v1.0.35
[1.0.22]: https://github.com/mjcumming/pywiim/compare/v1.0.21...v1.0.22
[1.0.21]: https://github.com/mjcumming/pywiim/compare/v1.0.19...v1.0.21
[1.0.19]: https://github.com/mjcumming/pywiim/compare/v1.0.18...v1.0.19
[1.0.18]: https://github.com/mjcumming/pywiim/compare/v1.0.17...v1.0.18
[1.0.17]: https://github.com/mjcumming/pywiim/compare/v1.0.16...v1.0.17
[1.0.16]: https://github.com/mjcumming/pywiim/compare/v1.0.15...v1.0.16
[1.0.15]: https://github.com/mjcumming/pywiim/compare/v1.0.14...v1.0.15
[1.0.14]: https://github.com/mjcumming/pywiim/compare/v1.0.13...v1.0.14
[1.0.13]: https://github.com/mjcumming/pywiim/compare/v1.0.10...v1.0.13
[1.0.10]: https://github.com/mjcumming/pywiim/compare/v1.0.9...v1.0.10
[1.0.9]: https://github.com/mjcumming/pywiim/compare/v1.0.8...v1.0.9
[1.0.8]: https://github.com/mjcumming/pywiim/compare/v1.0.7...v1.0.8
[1.0.7]: https://github.com/mjcumming/pywiim/compare/v1.0.6...v1.0.7
[1.0.6]: https://github.com/mjcumming/pywiim/compare/v1.0.5...v1.0.6
[1.0.5]: https://github.com/mjcumming/pywiim/compare/v1.0.0...v1.0.5
[1.0.0]: https://github.com/mjcumming/pywiim/releases/tag/v1.0.0
