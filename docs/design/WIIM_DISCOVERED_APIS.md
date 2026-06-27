# WiiM Discovered Read-Only APIs

This note records WiiM HTTP APIs discovered from app traffic and reported in
[pywiim issue #20](https://github.com/mjcumming/pywiim/issues/20). Treat these
as WiiM-specific until real-device testing proves broader LinkPlay/OEM support.

pywiim exposes these endpoints as read-only helpers first. Do not wire them into
source selection, audio-output selection, or Home Assistant behavior until the
payloads have been tested across real devices and firmware versions.

## Endpoint Summary

| Command | pywiim helper | Model | Current use |
| --- | --- | --- | --- |
| `getAudioInputEnable` | `client.get_audio_input_enable()` | `AudioInputEnable` | Read-only input enable metadata |
| `getModeRename` | `client.get_mode_rename()` | `dict[str, str]` | Read-only user source-label map |
| `GetAcousticCapability` | `client.get_acoustic_capability()` | `AcousticCapability` | Read-only acoustic capability blocks |
| `getAllRoutines` | `client.get_all_routines()` | `RoutineList` | Read-only routine list |
| `getSoundCardModeSupportList` | `client.get_sound_card_mode_support_list()` | `list[SoundCardModeSupport]` | Read-only output hardware metadata |

Unsupported endpoints, plain `Failed`, `unknown command`, non-JSON bodies, and
transport errors should not make discovery fail. Helpers return `None` or an
empty list, depending on the natural shape of the API.

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

Possible later use: enrich `source_catalog` with per-device input enablement.
This should be an overlay on stable source IDs and profile/hardware knowledge,
not a replacement for source identity.

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

Possible later use: add user-facing label metadata to source catalog entries.
Do not use renamed labels as stable source IDs. For example, if the user names
Optical "Phono", the stable source ID remains `optical`.

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

Possible later use: enrich audio-output availability, especially USB DAC
presence and capability metadata. Do not replace the existing output probe
strategy until this endpoint is tested on multiple WiiM models and firmware
versions.

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
