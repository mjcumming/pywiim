# WiiM Discovered Read-Only APIs

This note records WiiM HTTP APIs discovered from app traffic and reported in
[pywiim issue #20](https://github.com/mjcumming/pywiim/issues/20). Treat these
as WiiM-specific until real-device testing proves broader LinkPlay/OEM support.

pywiim exposes these endpoints as read-only helpers first. The three input
endpoints below are now consumed as a WiiM-only overlay on source enumeration
(verified on a real WiiM device); the others remain diagnostics-only until their
payloads are tested across more devices and firmware versions.

## Endpoint Summary

| Command | pywiim helper | Model | Current use |
| --- | --- | --- | --- |
| `getAudioInputEnable` | `client.get_audio_input_enable()` | `AudioInputEnable` | Enable-filter overlay: hides user-disabled inputs from `available_sources` |
| `getAudioInputCapbility` | `client.get_audio_input_capability()` | `AudioInputCapability` | Authoritative input list: gap-fills enumeration missed by `plm_support`/`InputList` |
| `getModeRename` | `client.get_mode_rename()` | `dict[str, str]` | Custom label overlay on `source_catalog` names (stable ids preserved) |
| `GetAcousticCapability` | `client.get_acoustic_capability()` | `AcousticCapability` | Read-only acoustic capability blocks |
| `getAllRoutines` | `client.get_all_routines()` | `RoutineList` | Read-only routine list |
| `getSoundCardModeSupportList` | `client.get_sound_card_mode_support_list()` | `list[SoundCardModeSupport]` | Read-only output hardware metadata |

Unsupported endpoints, plain `Failed`, `unknown command`, non-JSON bodies, and
transport errors should not make discovery fail. Helpers return `None` or an
empty list, depending on the natural shape of the API.

The WiiM Voice Remote endpoints are listed in [their own section](#wiim-voice-remote).

## `getAudioInputEnable`

Example shape:

```json
{
  "ver": "1.0",
  "audioInput": [
    {"mode": "wifi", "enable": 1},
    {"mode": "bluetooth", "enable": 1},
    {"mode": "line-in", "enable": 1},
    {"mode": "optical", "enable": 1},
    {"mode": "HDMI", "enable": 1},
    {"mode": "phono", "enable": 1}
  ]
}
```

Implemented: overlaid on stable source ids at connect (`wiim_input_enable` in
`capabilities`). `available_sources` drops inputs with `enable=0`, except the
currently active source, which stays visible for correct state display.

## `getAudioInputCapbility`

The firmware command is misspelled as `Capbility`. It returns available input
modes without the enable/disable state from `getAudioInputEnable`.

Example shape:

```json
{
  "ver": "1.0",
  "audioInput": [
    {"mode": "wifi"},
    {"mode": "line-in"},
    {"mode": "bluetooth"},
    {"mode": "optical"}
  ]
}
```

Implemented: gap-fills `available_sources` with authoritative physical inputs
that `plm_support`/`InputList` enumeration missed (`wiim_input_capability` in
`capabilities`). Modes are normalized through `canonical_source_key()` and deduped
by canonical id before use.

## `getModeRename`

Example shape:

```json
{
  "phono": "unused phono",
  "SPDIF-In": "Phono",
  "optical": "Phono"
}
```

Firmware may return plain `Failed` when no input has been renamed.

Implemented: overlaid as the display `name` on `source_catalog` entries and in
`available_sources` (`source_rename` in `capabilities`). Stable ids are never
changed — if the user names Optical "Phono", the id stays `optical`. `set_source()`
resolves the custom label back to the canonical id. When firmware points several
mode keys at one label (e.g. `optical` and `SPDIF-In` → "Optical Mike"), the
canonical hardware id wins (`source_rename_reverse()`).

## `GetAcousticCapability`

Example shape:

```json
{
  "Version": "1.0",
  "GEQ": {"Version": "1.0"},
  "PEQ": {"Version": "1.0", "Filters": ["OFF", "LS", "PK", "HS", "LP", "HP"]},
  "RC": {"Version": "1.0"},
  "HeadphoneEQ": {"Version": "1.0"},
  "SubLPF": {"Version": "1.0"},
  "Evaluation": {"Version": "1.1"},
  "EQBlock": {"Version": "1.0", "Blocks": [{"id": 1, "type": "EQ"}]},
  "OutputDelay": {
    "Version": "1.0",
    "PerOutputDelay": false,
    "EnableMicroDelay": true,
    "MinDelayUs": -1000000,
    "MaxDelayUs": 1000000,
    "StepDelayUs": 100
  }
}
```

Current model keeps capability blocks as dictionaries. This avoids committing
too early to HA controls or high-level pywiim feature flags for GEQ, PEQ, room
correction, headphone EQ, output delay, or evaluation APIs.

## `getAllRoutines`

Example shape:

```json
{
  "routines": [
    {
      "id": "0000000067570795",
      "name": "PC",
      "index": 3,
      "createDate": "2026-06-23T06:08:26Z",
      "updateDate": "2026-06-23T06:08:56Z",
      "steps": [
        {"type": "audioInput", "payload": {"input": "optical"}},
        {"type": "audioOutput", "payload": {"output": ""}},
        {"type": "loopMode", "payload": {"mode": 4}},
        {"type": "subwoofer", "payload": {"subOutput": 1}}
      ]
    }
  ]
}
```

Routines are not playback presets. They are device-side action sequences.
pywiim exposes read-only routine metadata only; execution and mutation endpoints
are not known yet.

## `getSoundCardModeSupportList`

Example shape:

```json
[
  {
    "index": 5,
    "mode": "AUDIO_OUTPUT_UAC_CARD_MODE",
    "soundCard": {
      "cardName": "SABRE-D70 Pro SABRE",
      "devName": "Topping D70 Pro SABRE at usb-xhci-hcd.0.auto-1.2, high speed",
      "cardId": "hw:1,0",
      "channelMax": 2,
      "bitDepthMax": 32,
      "sampleRateMax": 192000,
      "sampleRateSupportList": [44100, 48000, 88200, 96000, 176400, 192000],
      "HiFiSRCVersion": "1.1"
    }
  }
]
```

Field note: `index` does not appear to match the older output mode integer used
for reads or writes. Treat `mode` as identity and `index` as display/debug
metadata only.

WiiM Sound Lite (`WiiM_Sound_Lite_V2`, wiim #270) returns a single speaker
row (`AUDIO_OUTPUT_SPEAKER_MODE`, `devName: "Speaker Out"`). That list does
**not** include Bluetooth Out and does **not** change when the app is on
Bluetooth Out. Current output still comes from `getNewAudioOutputHardwareMode`
(`hardware` + `source`). This endpoint can later gap-fill Speaker Out for
unknown speaker models; it is not a complete output-mode catalog.

Possible later use: enrich audio-output availability, especially USB DAC
presence and capability metadata. Do not replace the existing output probe
strategy until this endpoint is tested on multiple WiiM models and firmware
versions.

## Related daily-use APIs

The same app-string sweep exposed a few endpoints that are closer to daily
listening than one-time setup:

| Command | pywiim helper | Model | Current use |
| --- | --- | --- | --- |
| `EQGetLV2Band:http://moddevices.com/plugins/caps/Eq10HP` | `client.get_graphic_eq_bands()` | `GraphicEQSettings` | Read-only graphic EQ state |
| `EQGetLV2SourceBandEx:{...Eq10HP...}` | `client.get_graphic_eq_bands(source_name=...)` | `GraphicEQSettings` | Read-only per-source graphic EQ state |
| `EQv2GetList:http://moddevices.com/plugins/caps/Eq10HP` | `client.get_graphic_eq_preset_list()` | `dict[str, list[str]]` | Read-only graphic EQ preset names |
| `EQGetLV2SourceBandEx` at EQLevel 2 | `client.get_room_correction()` | `RoomCorrectionSettings` | RoomFit on/off and active profile |
| `EQv2GetNewList` at EQLevel 2 | `client.get_room_correction_profiles()` | `list[str]` | Saved RoomFit profile names |
| `EQv2SourceLoad` / `EQSourceOff` at EQLevel 2 | `client.set_room_correction(name)` | none | Load a RoomFit profile, or turn it off |

Write commands for graphic EQ are intentionally not exposed yet. Use the WiiM
app for graphic EQ setup until write behavior is validated across more models
and firmware versions. RoomFit profile create and edit stay in the WiiM app.

## WiiM Voice Remote

Verified on a WiiM Pro Plus (firmware `Linkplay.4.8.833841`, pywiim 3.0.3 had none of
this). Other models and firmware are not tested. Design: [ADR 023](adr/023-wiim-voice-remote-state-and-volume-step.md).

| Command | pywiim helper | Model | Current use |
| --- | --- | --- | --- |
| `getStatusEx` `BleRemote*` keys | `Player.ble_remote` | `BleRemoteState` | Connected, battery, RSSI, version (live values) |
| `getblehidstatus` | `client.get_ble_remote_identity()` | `BleRemoteIdentity` | Name, MAC, paired vs not paired; also the capability probe |
| `get_remote_volume_step` | `client.get_remote_volume_step()` | `int` (1-5) | Read the remote's volume step |
| `set_remote_volume_step:N` | `client.set_remote_volume_step(N)` | none | Write the volume step (N = 1-5), verified by read-back |

`getStatusEx` while the remote is connected:

```text
"BleRemoteControl":"1","BleRemoteConnected":"1","BleRemoteException":"0","BleRemoteVersion":"0054",
"BleRemoteBatterylevel":"100","BleRemoteRSSI":"-61","BleRemote_dev_state":"normal",
"BleRemote_power_status":"0","BleRemote_has_new":"0","BleRemoteNewVersion":"",
"BleRemote_update_checked_counter":"11"
```

While not connected only `BleRemoteControl` `"1"` and `BleRemoteConnected` `"0"` are present; the
other keys are missing. `BleRemoteControl` is `"1"` in every state, so it means "the speaker
supports a remote", not "a remote is paired".

`getblehidstatus` (note the space before `doubleclickdisable` in the real response):

```text
connected:   {"status":"connected","error":0,"name":"WiiM Voice Remote","mac":"<BLE MAC>","battery":100,"ver":"0054","rssi":-61,"powerstatus":0, "doubleclickdisable":0}
notconnect:  same keys; name, mac and ver kept, rssi = last value (batteries out)
scanning:    not paired: name "", mac "00:00:00:00:00:00", ver "", rssi 0
```

| State | `getblehidstatus` `status` | `getStatusEx` |
| --- | --- | --- |
| Paired and connected | `connected` | `BleRemoteConnected` `1` plus the `BleRemote*` keys |
| Paired, not connected (batteries out) | `notconnect`, identity kept | `BleRemoteConnected` `0`, other keys missing |
| Not paired | `scanning`, empty name, zero MAC | `BleRemoteConnected` `0`, other keys missing |

`getblehidstatus` `battery` lags after a battery change (0 right after, 100 on a later read; the
delay is unknown) while `rssi` updates. `getStatusEx` `BleRemoteBatterylevel` updates
immediately, so battery comes from `getStatusEx`.

Volume step: `get_remote_volume_step` → `{"status":"OK","remote_volume_step":1}`;
`set_remote_volume_step:N` → `{"status":"OK"}` for N = 1-5 (app labels: 1 Fine Adjustment
(default), 2 Small Step, 3 Medium Step, 4 Large Step, 5 Quick Adjustment). Values outside 1-5
are not tested; pywiim rejects them before sending.

Never sent by pywiim (they pair, remove or update the remote): `blehidremoveall`,
`startblescan`, `blehidpair`, `getMvRemoteUpdateStart`, `getMvRemoteUpdateStartCheck`.
Device test scripts must block them in code. The BLE MAC is private: it is hidden from
`repr()`, never logged, and masked in diagnostics.

## Intentionally Not Exposed

One-off setup, account, network, update-server, token, static-IP, Wi-Fi, Alexa,
and factory-reset style commands from the app bundle are not good Home
Assistant surfaces. pywiim may keep selected read-only diagnostics over time,
but user-facing HA entities/services should focus on daily listening and
automation workflows.

## Real-Device Testing

Use the diagnostics CLI for a focused JSON report:

```bash
python -m pywiim.cli.diagnostics 192.168.1.100 --discovered-apis-only --output discovered-apis.json
```

Use `docs/testing/CURL_HTTPAPI.md` when raw HTTP payloads are needed. For each
endpoint, record:

- device model and firmware
- protocol/port used
- endpoint response when supported
- exact unsupported response when not supported
- whether the WiiM app setting changes the payload predictably

Once we have enough data, decide separately whether to wire these into:

- `source_catalog` metadata
- audio-output support lists
- capability flags
- diagnostics
- Home Assistant integration behavior

### Observed Devices

| Date | Device | Firmware | Supported discovered endpoints | Notes |
| --- | --- | --- | --- | --- |
| 2026-06-27 | Cabin Speakers (`WiiM_Pro_with_gc4a`) | `Linkplay.4.8.814756` | `getAudioInputEnable`, `GetAcousticCapability`, `getAllRoutines` | `getModeRename` returned empty/unsupported; `getSoundCardModeSupportList` returned empty. Inputs reported: `wifi`, `bluetooth`, `line-in`, `optical`. |
| 2026-06-27 | Main Deck (`ARYLIC_H50`) | `Linkplay.4.6.529755` | None | Optional endpoints returned firmware error payloads such as `unknown command` / `Fail`; helpers classify these as unsupported. |
| 2026-06-27 | Dock Speakers (`UP2STREAM_AMP_V4`) | `4.6.415145` | None | All five helpers returned unsupported/empty. |
