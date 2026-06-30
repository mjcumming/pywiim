# Manual HTTP API probes with `curl` (local devices)

Use this when you want **raw responses** from a WiiM or LinkPlay device on your LAN—firmware checks, comparing states, or **research** (for example [DLNA Cast output](https://github.com/mjcumming/wiim/issues/225)) before anything is added to pywiim.

For automated library tests, prefer [REAL-DEVICE-TESTING.md](REAL-DEVICE-TESTING.md) and `WIIM_TEST_DEVICE`.

## Prerequisites

- **`curl`** installed.
- Device **IP** (router, WiiM app, or `tests/devices.yaml` `default_device` in this repo).
- PC on the **same network** as the player.

## WiiM: HTTPS, port 443, self-signed certificates

Modern WiiM firmware typically serves the HTTP API over **HTTPS on port 443** with a **self-signed** certificate. Use **`curl -k`** (`--insecure`) so TLS verification does not fail. This matches project practice (see [.cursorrules](../../.cursorrules) and [API_DESIGN_PATTERNS.md](../design/API_DESIGN_PATTERNS.md)).

```bash
DEVICE=192.168.1.115   # your player

# JSON pretty-print (optional)
curl -ks "https://${DEVICE}:443/httpapi.asp?command=getStatusEx" | python3 -m json.tool
```

**Template:**

```text
https://DEVICE_IP:443/httpapi.asp?command=COMMAND
```

Some older or mixed setups still answer on **HTTP port 80**; if HTTPS fails, try:

```bash
curl -s "http://${DEVICE}:80/httpapi.asp?command=getStatusEx" | python3 -m json.tool
```

## Read-only commands (safe starting points)

These are **GET**-style URLs (read-only). Good for baselines before/after you change something in the WiiM app.

| Command | Purpose |
|--------|---------|
| `getStatusEx` | Device info, inputs, build flags. Fields here (e.g. `audiocast`) are **not** the same semantics as `audiocast` inside output-status JSON—compare **endpoint to endpoint**. |
| `getNewAudioOutputHardwareMode` | **Preferred on WiiM** for current output: `hardware`, Bluetooth-out `source`, **`audiocast`** (cast-style output active 0/1). Matches [wiim-httpapi](https://github.com/cvdlinden/wiim-httpapi/blob/main/openapi.md) “Audio Output Control”. |
| `getAudioOutputStatus` | **Legacy** read; same *shape* as above on devices that implement it. Many WiiM units (e.g. **WiiM Pro** on current firmware) return plain **`unknown command`**—use **`getNewAudioOutputHardwareMode`** instead. |
| `getPlayerStatus` | Basic playback JSON |
| `getPlayerStatusEx` | Richer playback JSON (when supported) |
| `getMetaInfo` | Track metadata (may be empty on some sources) |
| `getAudioInputEnable` | WiiM input enablement metadata; see [WiiM Discovered Read-Only APIs](../design/WIIM_DISCOVERED_APIS.md). |
| `getAudioInputCapbility` | WiiM input capability metadata. Firmware spelling is `Capbility`. |
| `getModeRename` | WiiM user-renamed input labels; may return plain `Failed` when no labels are renamed. |
| `GetAcousticCapability` | WiiM acoustic capability blocks (GEQ/PEQ/RC/output delay/etc.). |
| `getAllRoutines` | WiiM routines (device-side action sequences, not playback presets). |
| `getSoundCardModeSupportList` | WiiM output sound-card support list; key by `mode`, not `index`. |
| `RoomCorrGet` | WiiM room-correction state; read-only in pywiim. |
| `EQv2GetList:http://moddevices.com/plugins/caps/Eq10HP` | WiiM graphic EQ preset names. |

Examples:

```bash
DEVICE=192.168.1.115

curl -ks "https://${DEVICE}:443/httpapi.asp?command=getStatusEx" | python3 -m json.tool

curl -ks "https://${DEVICE}:443/httpapi.asp?command=getNewAudioOutputHardwareMode" | python3 -m json.tool

curl -ks "https://${DEVICE}:443/httpapi.asp?command=getPlayerStatus" | python3 -m json.tool

curl -ks "https://${DEVICE}:443/httpapi.asp?command=getPlayerStatusEx" | python3 -m json.tool

# Optional: only if the device accepts this command name (may be "unknown command" on WiiM Pro)
curl -ks "https://${DEVICE}:443/httpapi.asp?command=getAudioOutputStatus"

# WiiM-only research endpoints from pywiim#20
curl -ks "https://${DEVICE}:443/httpapi.asp?command=getAudioInputEnable" | python3 -m json.tool
curl -ks "https://${DEVICE}:443/httpapi.asp?command=getAudioInputCapbility" | python3 -m json.tool
curl -ks "https://${DEVICE}:443/httpapi.asp?command=getModeRename" | python3 -m json.tool
curl -ks "https://${DEVICE}:443/httpapi.asp?command=GetAcousticCapability" | python3 -m json.tool
curl -ks "https://${DEVICE}:443/httpapi.asp?command=getAllRoutines" | python3 -m json.tool
curl -ks "https://${DEVICE}:443/httpapi.asp?command=getSoundCardModeSupportList" | python3 -m json.tool

# Daily-use EQ research endpoints (read-only)
curl -ks "https://${DEVICE}:443/httpapi.asp?command=RoomCorrGet" | python3 -m json.tool
curl -ks "https://${DEVICE}:443/httpapi.asp?command=EQv2GetList:http://moddevices.com/plugins/caps/Eq10HP" | python3 -m json.tool
```

**Note:** Output field meanings (`hardware`, `source`, `audiocast`) for the **JSON object** are documented in [API_DESIGN_PATTERNS.md](../design/API_DESIGN_PATTERNS.md). pywiim probes **`getNewAudioOutputHardwareMode` first**, then **`getAudioOutputStatus`**, matching real firmware differences (see [mjcumming/wiim#144](https://github.com/mjcumming/wiim/issues/144) and `WiiMCapabilities.detect_capabilities` in `pywiim/capabilities.py`).

## State-changing commands (be careful)

Commands such as `setAudioOutputHardwareMode:…`, `setPlayerCmd:…`, Bluetooth `connectbta2dpsynk:…`, etc. **change device behavior**. Use a **lab** player if possible, or know how to **revert in the app**. Prefer read-only curls first.

## DLNA Cast output (community findings — verify on your hardware)

Home Assistant integration issue: **[Support for DLNA Output #225](https://github.com/mjcumming/wiim/issues/225)**.

A beta WiiM Ultra user reported (paraphrased):

- With **DLNA Cast** active, **`getPlayerStatus`** may show **`mode: 5`** (not in older public mode tables).
- **`getStatusEx`** may include an **`audiocast`** field (device / capability blob)—**do not assume** it equals **`audiocast`** in **`getNewAudioOutputHardwareMode`** without diffing both endpoints on your firmware.
- **Listing / pairing / switching** DLNA Cast targets via `httpapi.asp` was **not** found by extensive guessing; **TLS pinning** blocked app traffic decryption in their setup.

**What to do with `curl` here:** treat these as **hypotheses** to **confirm on your firmware**:

1. Capture **read-only** JSON with DLNA Cast **off** (lines in, idle, or normal output).
2. Enable **only** what you need in the WiiM app (DLNA Cast paired and active).
3. Run the **same** `curl` commands and **diff** responses (`getStatusEx`, `getPlayerStatus` / `Ex`, **`getNewAudioOutputHardwareMode`**, and `getAudioOutputStatus` only if it is not `unknown command`).

If `mode` / `audiocast` / other fields move in lockstep with the app, document the **exact JSON snippets** and **firmware version** in the GitHub issue—that is the data pywiim would need before adding any client API.

**Further reading (unofficial, community-maintained):** [wiim-httpapi `openapi.md` history](https://github.com/cvdlinden/wiim-httpapi/commits/main/openapi.md) — useful for command names when they appear; still verify on device.

## Arylic and other LinkPlay devices

Many commands return plain text **`unknown command`** or an **empty** body on Arylic. That is expected; do not assume WiiM-only fields (e.g. certain output commands) exist on every vendor.

## See also

- [REAL-DEVICE-TESTING.md](REAL-DEVICE-TESTING.md) — pytest tiers, `WIIM_TEST_DEVICE`, `scripts/run_tests.py`
- [API_DESIGN_PATTERNS.md](../design/API_DESIGN_PATTERNS.md) — defensive patterns, audio output `curl` examples
- [DIAGNOSTICS.md](../user/DIAGNOSTICS.md) — `wiim-diagnostics` for structured reports
