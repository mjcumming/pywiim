# Source Enumeration vs Selection

## Overview

WiiM devices have a **two-layer source system** that creates an important distinction between sources that can be **enumerated** (listed) and sources that can be **selected** (switched to).

## The Two Layers

### Layer 1: Physical Inputs (Authoritative Model-Specific)
These are the **physical and connection-level inputs** that are physically present on the device hardware. 

Historically, we relied on the device's `input_list` or `plm_support` bitmask, but these are often incorrect (e.g., a WiiM Pro reporting a USB port it doesn't have). **`pywiim` now acts as the "UI Master"**, using an internal hardware database (`device_capabilities.py`) to strictly filter the available sources for each model:

- **Network** - Unified "Streaming Mode" (standardized from WiFi/Ethernet)
- **Bluetooth** - Bluetooth audio input  
- **Line In** - Analog audio input
- **Optical In** - Digital optical input
- **Coaxial** - Digital coaxial input (Stable name)
- **USB** - USB audio input (WiiM Ultra/Amp only)
- **HDMI** - HDMI audio input (WiiM Ultra/Amp only)
- **Phono** - Turntable input (WiiM Ultra only)
- **Aux In** - Friendly name for Line In on specific models (WiiM Sound, etc.)

**Model-Specific Exclusions:**
- **WiiM Pro / Pro Plus**: Automatically excludes `USB` and `Coaxial` (Pro Plus hardware has Coaxial, but it is excluded from the standard integration source list per user preference).
- **WiiM Sound**: Excludes `USB`, `Line In`, `Optical`, and `Coaxial`, leaving only `Network`, `Bluetooth`, and `Aux In`.
- **WiiM Mini**: Excludes `Ethernet` and `Coaxial`.

### Layer 2: Services/Content (Selectable but not always enumerable)
These are **streaming services and protocols** that can be selected but may not appear in `input_list`:

- **Amazon Music** - Streaming service
- **Spotify** - Streaming service  
- **Tidal** - Streaming service
- **Qobuz** - Streaming service
- **Deezer** - Streaming service
- **AirPlay** - Apple casting protocol
- **DLNA** - Network media protocol
- **iHeartRadio** - Internet radio service
- **Other streaming services** - Various internet radio and streaming services

These are **selectable** - you can switch to them using `switchmode:`, but they may not appear in `input_list` because they're not physical inputs.

**Note on Presets**: Presets (saved stations/playlists) are **NOT** input sources. They should be handled via media browser functionality:
- Use `get_presets()` to retrieve the list of presets (returns list of dicts with number, name, url, picurl)
- Use `play_preset(preset_number, index=None)` to play a preset (optional 1-based `index` to start at a specific track, e.g. `index=1` from beginning)
- Presets should be exposed in Home Assistant's media browser, not as selectable input sources

## Key Distinction

### Enumerable Sources (`input_list`)
- **Source**: `getStatusEx` API response
- **Field**: `input_list` in `DeviceInfo`
- **Contains**: Physical hardware inputs only
- **Purpose**: Shows what physical inputs are available on the device
- **Example**: `["wifi", "bluetooth", "line_in", "optical"]`

### User-Selectable Sources (For Home Assistant UI)
These are the sources to show in Home Assistant's `source_list` dropdown. **`pywiim` provides a "UI-Ready" list** via the `Player.available_sources` property.

- **Standardized Naming (ADR 001)**: All sources follow a consistent and STABLE naming convention to prevent automation breakage:
  - **"Network"**: Replaces all variations of `wifi`, `ethernet`, and `wi-fi`.
  - **"Line In", "Optical In", "Aux In"**: Standard Title Case with "In" suffix.
  - **"Coaxial", "HDMI", "Phono", "USB"**: Stable names WITHOUT "In" suffix.
  - **Acronyms**: Proper capitalization for `USB`, `HDMI`, `SPDIF`, `RCA`, `DLNA`.
- **Essential Source Injection**: The **"Network"** source is always injected, ensuring users on a physical input (like Optical) always have a way to switch back to streaming mode.
- **Current Source**:
  - `player.source` returns a stable source id (matches `source_catalog[*]["id"]`)
  - `player.source_name` returns the UI-ready display name (and is guaranteed to match an entry in `player.available_sources`)

## Implementation Pattern: "Thin Integration"

By moving this logic into `pywiim`, we follow a "Thin Integration" pattern where the library takes full responsibility for:
1. **Filtering**: Knowing what hardware exists on each model.
2. **Formatting**: Providing strings ready for display.
3. **Smart Normalization**: Automatically mapping various UI strings back to the correct API command using alphanumeric matching and device-reported input lists.

### Correct Pattern (Current)

```python
# Get UI-ready list
available_sources = player.available_sources
# Result: ["Network", "Bluetooth", "Line In", "Optical In", "Coaxial"]

# Get current source
current_id = player.source
# Result: "network" or "line_in" or "spotify"

current_name = player.source_name
# Result: "Network" or "Line In" or "Spotify"

# Selection is highly resilient (Smart Normalization)
await player.set_source("Line In")     # OK -> "line-in"
await player.set_source("line_in")     # OK -> "line-in"
await player.set_source("Optical In")  # OK -> "optical"
await player.set_source("Coaxial")     # OK -> "coaxial"
```
