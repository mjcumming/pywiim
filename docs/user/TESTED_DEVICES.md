# Tested devices

This is the hardware that pywiim and the [WiiM Audio integration for Home Assistant](https://github.com/mjcumming/wiim) have been run against. Both projects use this one list.

A device is on the list when there's a record of it working: a maintainer's own test, or a user's report that was fixed and closed. "Reports as" is the model string the device returns, which is what pywiim matches on. "Firmware" is the version in that record, so another version may behave differently. A cell that says "not recorded" means nobody wrote it down, and you're welcome to fill it in.

| Brand | Model | Reports as | Firmware | Profile | Record |
| --- | --- | --- | --- | --- | --- |
| WiiM | Pro | `WiiM_Pro_with_gc4a` | `Linkplay.4.8.833748` | WiiM | UPnP event testing for pywiim 3.0.6 ([wiim#327](https://github.com/mjcumming/wiim/pull/327)) |
| WiiM | Pro Plus | not recorded | not recorded | WiiM | Playback queue ([wiim#264](https://github.com/mjcumming/wiim/issues/264)) |
| WiiM | Ultra | not recorded | not recorded | WiiM | USB and headphone outputs ([wiim#160](https://github.com/mjcumming/wiim/issues/160), [wiim#117](https://github.com/mjcumming/wiim/issues/117)) |
| WiiM | Sound | not recorded | not recorded | WiiM | Display control ([wiim#281](https://github.com/mjcumming/wiim/issues/281)) |
| WiiM | Sound Lite | not recorded | not recorded | WiiM | Audio output modes ([wiim#270](https://github.com/mjcumming/wiim/issues/270)) |
| Audio Pro | A10 MkII | not recorded | not recorded | Audio Pro MkII | Line-in switching and EQ presets ([wiim#187](https://github.com/mjcumming/wiim/issues/187)) |
| Arylic | H50 | not recorded | `4.6.529755` | Arylic | Audio output reads, noted in [API design patterns](../design/API_DESIGN_PATTERNS.md) |
| Arylic | Up2Stream Amp V4 | `UP2STREAM_AMP_V4` | `4.6.415145` | Arylic | Audio output not supported, noted in [API design patterns](../design/API_DESIGN_PATTERNS.md) |
| Edifier | MS50A | `EDIFIER MS50A` | `Linkplay.4.6.430230` | LinkPlay generic | Setup and playback ([wiim#275](https://github.com/mjcumming/wiim/issues/275)) |

## Handled in code, with no record here yet

pywiim has model handling or a profile for these, but this page has no test record for them: WiiM Mini, Amp, Amp Pro and Amp Ultra; Audio Pro Addon C5, C5A, C10, A15 and A28; Arylic S10+; and speakers from DOSS, Dayton Audio and iEast. Some of them are in daily use. They move into the table when someone records the details.

The [device catalog](../design/DEVICE_PROFILES.md#device-catalog) describes how each profile differs.

## Add a device

1. Run the diagnostics tool against the speaker, or download the device diagnostics in Home Assistant:

   ```bash
   wiim-diagnostics 192.168.1.100 --output report.json
   ```

2. Note the model string and the firmware version from the report.
3. Open an issue or a pull request in [pywiim](https://github.com/mjcumming/pywiim/issues) with those two values and what you tested. A pull request adds one row to the table above.

A device that doesn't work is worth reporting too. It goes in the table once the problem is fixed.
