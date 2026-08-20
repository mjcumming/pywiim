# pywiim

Python library for WiiM and LinkPlay device control with command-line tools for discovery, diagnostics, and monitoring.

[![CI](https://github.com/mjcumming/pywiim/actions/workflows/ci.yml/badge.svg)](https://github.com/mjcumming/pywiim/actions/workflows/ci.yml) [![Security](https://github.com/mjcumming/pywiim/actions/workflows/security.yml/badge.svg)](https://github.com/mjcumming/pywiim/actions/workflows/security.yml) [![codecov](https://codecov.io/gh/mjcumming/pywiim/branch/main/graph/badge.svg)](https://codecov.io/gh/mjcumming/pywiim) [![PyPI version](https://img.shields.io/pypi/v/pywiim)](https://pypi.org/project/pywiim/) [![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black) [![Type checking: mypy](https://img.shields.io/badge/type%20checking-mypy-blue.svg)](https://mypy.readthedocs.io/) [![Linting: ruff](https://img.shields.io/badge/linting-ruff-yellow.svg)](https://github.com/astral-sh/ruff)

## Overview

`pywiim` provides control of WiiM and LinkPlay-based audio devices through a Python API and command-line tools. The library handles playback control, volume management, queues, multiroom audio, EQ settings, presets, and more.

## Key Features

- **MCP Server** - Expose WiiM control to Cursor, Claude Desktop, and other MCP hosts. `pip install pywiim[mcp]` then `wiim-mcp`. Control playback, volume, and more via AI assistants.
- **Playback Control** - Play, pause, stop, next/previous track, seek
- **Queue Management** - Enqueue, insert, play, remove, and browse via AVTransport `AddURIToQueue` or WiiM PlayQueue (Pro / Pro Plus). `queue_count` / `queue_position` overlay when HTTP fields are empty.
- **Volume & Audio** - Volume, mute, channel balance, and model-specific audio outputs (Line Out, Optical, Coax, Speaker Out, USB Out, HDMI Out, headphone). Paired Bluetooth devices appear as `BT: …`.
- **Sources** - Intelligent model-specific source management (Bluetooth, Line In, Optical In, Coaxial, USB, HDMI ARC, Phono) and streaming services. Authoritative hardware filtering and UI-ready formatting.
- **Source Catalog** - Structured source metadata via `player.source_catalog` (source type, selectability, and per-source capability flags) for integrations like Music Assistant.
- **Multiroom Audio** - Create/join/leave groups, synchronized volume and playback
- **EQ & Presets** - 10-band EQ with presets, 20 preset stations; **Parametric EQ (PEQ)** on WiiM (10-band per-source, stereo/L-R, presets; see [PR #12]
- **Timers & Alarms** - Sleep timers and alarm clocks (WiiM devices)
- **State Synchronization** - UPnP events with HTTP polling fallback
- **Device Discovery** - SSDP/UPnP discovery with network scanning fallback
- **Multi-vendor Support** - WiiM, Arylic, Audio Pro, and generic LinkPlay devices

**Device Compatibility:**
- **All LinkPlay devices**: Core playback, volume, sources, multiroom, presets
- **Device-dependent features**: EQ support (varies by device)
- **WiiM devices only**: Alarm clocks, sleep timers, audio output mode selection, and **Parametric EQ (PEQ)** (LV2 PEQ API). Output lists are model-specific (for example Speaker Out on Sound / Sound Lite).

The library automatically detects device capabilities and adapts functionality accordingly.

## Installation

Install `pywiim` to use the command-line tools for discovering, testing, and monitoring your WiiM/LinkPlay devices, or to use the Python library in your projects.

### Prerequisites

- Python 3.11 or later
- pip (usually included with Python)

**Installing Python:**
- **Linux/macOS**: Usually pre-installed. If not, use your package manager or download from [python.org](https://www.python.org/downloads/)
- **Windows**: Download from [python.org](https://www.python.org/downloads/) and check "Add Python to PATH" during installation

### Install pywiim

```bash
pip install pywiim
```

The CLI tools (`wiim-discover`, `wiim-diagnostics`, `wiim-monitor`, `wiim-verify`) are automatically installed and available in your PATH.

**Verify installation:**
```bash
wiim-discover --help
```

**Note for Windows users:** If the commands are not found after installation, ensure Python's Scripts directory is in your PATH (usually `C:\Users\YourName\AppData\Local\Programs\Python\Python3X\Scripts`), or restart your terminal.

## Command-Line Tools

The library includes four powerful CLI tools that are automatically installed with `pywiim`. These tools provide an easy way to discover, diagnose, monitor, and test your WiiM/LinkPlay devices without writing any code.

### Quick Start

1. **Discover devices on your network:**
   ```bash
   wiim-discover
   ```

2. **Test a device** (replace `192.168.1.100` with your device IP):
   ```bash
   wiim-verify 192.168.1.100
   ```

3. **Monitor a device in real-time:**
   ```bash
   wiim-monitor 192.168.1.100
   ```

4. **Run diagnostics:**
   ```bash
   wiim-diagnostics 192.168.1.100
   ```

### 1. Device Discovery (`wiim-discover`)

Discover all WiiM/LinkPlay devices on your network using SSDP/UPnP or network scanning.

**What it does:**
- Automatically finds all WiiM and LinkPlay-based devices on your local network
- Validates discovered devices by testing their API
- Displays device information (name, model, firmware, IP, MAC, UUID)
- Supports multiple discovery methods for maximum compatibility

**Usage:**
```bash
# Basic discovery (SSDP/UPnP)
wiim-discover

# Output as JSON (useful for scripting)
wiim-discover --output json

# Skip API validation (faster, less detailed)
wiim-discover --no-validate

# Verbose logging
wiim-discover --verbose

# Custom SSDP timeout
wiim-discover --ssdp-timeout 10
```

**Options:**
- `--ssdp-timeout <seconds>` - SSDP discovery timeout (default: 5)
- `--no-validate` - Skip API validation of discovered devices
- `--output <text|json>` - Output format (default: text)
- `--verbose, -v` - Enable verbose logging

**Example Output:**
```
🔍 Discovering WiiM/LinkPlay devices via SSDP...

Device: WiiM Mini
  IP Address: 192.168.1.100:80
  Protocol: HTTP
  Model: WiiM Mini
  Firmware: 4.8.123456
  MAC Address: AA:BB:CC:DD:EE:FF
  UUID: 12345678-1234-1234-1234-123456789abc
  Vendor: WiiM
  Discovered via: SSDP
  Status: Validated ✓
```

See [Discovery Documentation](docs/user/DISCOVERY.md) for more information.

### 2. Diagnostic Tool (`wiim-diagnostics`)

Comprehensive diagnostic tool for troubleshooting device issues and gathering information for support.

**What it does:**
- Gathers complete device information (model, firmware, MAC, UUID, capabilities)
- Includes UPnP `description.xml` capability enrichment (advertised services like PlayQueue/QPlay)
- Tests all API endpoints to verify functionality
- Tests feature support (presets, EQ, multiroom, Bluetooth, etc.)
- Generates detailed JSON reports for sharing with developers
- Identifies errors and warnings

**Usage:**
```bash
# Basic diagnostic
wiim-diagnostics 192.168.1.100

# Save report to file (for sharing with support)
wiim-diagnostics 192.168.1.100 --output report.json

# HTTPS device
wiim-diagnostics 192.168.1.100 --port 443

# Verbose output
wiim-diagnostics 192.168.1.100 --verbose
```

**Options:**
- `<device_ip>` - Device IP address or hostname (required)
- `--port <port>` - Device port (default: 80, use 443 for HTTPS)
- `--output <file>` - Save report to JSON file
- `--verbose` - Enable detailed logging

**What it tests:**
- Device information retrieval
- Capability detection
- All status endpoints
- Feature support detection
- API endpoint availability
- Error conditions

**Example Output:**
```
🔍 Starting comprehensive device diagnostic...
   Device: 192.168.1.100:80

📋 Gathering device information...
   ✓ Device: WiiM Mini (WiiM Mini)
   ✓ Firmware: 4.8.123456
   ✓ MAC: AA:BB:CC:DD:EE:FF

🔧 Detecting device capabilities...
   ✓ Vendor: WiiM
   ✓ Device Type: WiiM
   ✓ Supports EQ: Yes
   ✓ Supports Presets: Yes
   ...
```

See [Diagnostics Documentation](docs/user/DIAGNOSTICS.md) for more information.

### 3. Real-time Monitor (`wiim-monitor`)

Monitor your device in real-time with adaptive polling and UPnP event support.

**What it does:**
- Displays live device status with automatic updates
- Uses UPnP events for instant updates when available
- Falls back to adaptive HTTP polling
- Shows play state, volume, mute, track info, and playback position
- Displays device role in multiroom groups
- Tracks statistics (poll count, state changes, UPnP events)

**Usage:**
```bash
# Basic monitoring
wiim-monitor 192.168.1.100

# Specify callback host for UPnP (if auto-detection fails)
wiim-monitor 192.168.1.100 --callback-host 192.168.1.254

# Verbose logging
wiim-monitor 192.168.1.100 --verbose

# Custom log level
wiim-monitor 192.168.1.100 --log-level DEBUG

# Verbose UPnP event logging (shows full event JSON/XML)
wiim-monitor 192.168.1.100 --upnp-verbose
```

**Options:**
- `<device_ip>` - Device IP address or hostname (required)
- `--callback-host <ip>` - Override UPnP callback host (auto-detected by default)
- `--verbose, -v` - Enable verbose logging
- `--log-level <level>` - Set log level (DEBUG, INFO, WARNING, ERROR)
- `--upnp-verbose` - Enable verbose UPnP event logging (shows full event JSON/XML data)

**What it displays:**
- Play state (playing, paused, stopped)
- Volume level and mute status
- Current track (title, artist, album)
- Playback position and duration
- Device role (solo/master/slave)
- Group information (if in a group)
- Update source (polling or UPnP event)
- Statistics on exit

**Example Output:**
```
🎵 Monitoring WiiM Mini (192.168.1.100)...
   UPnP: Enabled ✓ (events: 0)
   Polling: Adaptive (interval: 2.0s)

📊 Status:
   State: playing
   Volume: 50% (muted: No)
   Source: wifi
   Role: solo

🎶 Track:
   Title: Song Title
   Artist: Artist Name
   Album: Album Name
   Position: 1:23 / 3:45

[UPnP] State changed: volume → 55%
```

Press `Ctrl+C` to stop monitoring and view statistics.

### 4. Feature Verification (`wiim-verify`)

Comprehensive testing tool that verifies all device features and endpoints with safety constraints.

**What it does:**
- Tests all playback controls (play, pause, stop, next, previous)
- Tests volume controls (safely, never exceeds 10%)
- Tests source switching
- Tests audio output modes
- Tests EQ controls (if supported)
- Tests group operations (if applicable)
- Tests preset playback
- Tests all status endpoints
- Saves and restores original device state
- Generates detailed test report

**Usage:**
```bash
# Basic verification
wiim-verify 192.168.1.100

# Verbose output (shows detailed test data)
wiim-verify 192.168.1.100 --verbose

# HTTPS device
wiim-verify 192.168.1.100 --port 443
```

**Options:**
- `<device_ip>` - Device IP address or hostname (required)
- `--port <port>` - Device port (default: 80, use 443 for HTTPS)
- `--verbose, -v` - Enable verbose output (shows detailed test data)

**Safety Features:**
- Volume never exceeds 10% during testing
- Original device state is saved and restored
- Non-destructive testing (doesn't disrupt normal use)
- Graceful error handling

**What it tests:**
- Status endpoints (get_player_status, get_device_info, etc.)
- Playback controls (play, pause, resume, stop, next, previous)
- Volume controls (set_volume, set_mute)
- Source controls (set_source, get_source)
- Audio output controls (set_audio_output_mode)
- EQ controls (get_eq, set_eq_preset, set_eq_custom, etc.)
- Group operations (create_group, join_group, leave_group)
- Preset operations (play_preset)
- And more...

**Example Output:**
```
💾 Saving original device state...
   ✓ Volume: 0.5
   ✓ Mute: False
   ✓ Source: wifi
   ✓ Play state: playing

📊 Testing Status Endpoints...
   ✓ get_player_status
   ✓ get_player_status_model
   ✓ get_meta_info

▶️  Testing Playback Controls...
   ✓ play
   ✓ pause
   ✓ resume
   ✓ stop
   ✓ next_track
   ✓ previous_track

🔊 Testing Volume Controls (max 10%)...
   ✓ set_volume (5%)
   ✓ set_volume (10%)
   ✓ set_mute (True)
   ✓ set_mute (False)

...

🔄 Restoring original device state...
   ✓ Volume restored
   ✓ Mute restored
   ✓ Source restored

============================================================
Total tests: 45
✅ Passed: 42
❌ Failed: 0
⊘ Skipped: 3
```

**Exit Codes:**
- `0` - All tests passed
- `1` - One or more tests failed or interrupted

### MCP Server (`wiim-mcp`)

Expose WiiM/LinkPlay control as an [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server for use with Cursor, Claude Desktop, and other MCP hosts.

**Install:**
```bash
pip install pywiim[mcp]
```

**Run:**
```bash
wiim-mcp
# or
python -m pywiim.mcp
```

**Config** (config file or env vars; env overrides file):

Config file: `~/.config/wiim/config.json` (or `WIIM_CONFIG_FILE` to override path). Copy from example:
```bash
mkdir -p ~/.config/wiim
cp $(python -c "import pywiim.mcp, os; print(os.path.join(os.path.dirname(pywiim.mcp.__file__), 'config.example.json'))") ~/.config/wiim/config.json
```
Edit with your device IPs (e.g. 192.168.1.115, 192.168.1.116, 192.168.1.68).

Config file keys: `default_device`, `named_devices`, `discovery_disabled`, `timeout`, `discovery_timeout`

Env vars (override file): `WIIM_DEFAULT_DEVICE`, `WIIM_NAMED_DEVICES` (JSON), `WIIM_DISCOVERY_DISABLED`, `WIIM_TIMEOUT`, `WIIM_DISCOVERY_TIMEOUT`, `WIIM_CONFIG_FILE`

**WSL / discovery doesn't work?** Set `discovery_disabled: true` in config and use pre-configured `named_devices` with your device IPs.

**Tools:** `wiim_discover`, `wiim_status`, `wiim_play`, `wiim_pause`, `wiim_media_play_pause`, `wiim_stop`, `wiim_next_track`, `wiim_previous_track`, `wiim_volume`, `wiim_mute`, `wiim_unmute`, `wiim_sources`, `wiim_set_source`, `wiim_play_url`, `wiim_group_join`, `wiim_group_leave`

**Cursor config** (add to MCP settings):
```json
{
  "mcpServers": {
    "wiim": {
      "command": "wiim-mcp",
      "args": []
    }
  }
}
```

**Claude Desktop config** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "wiim": {
      "command": "wiim-mcp",
      "args": []
    }
  }
}
```

## Quick Start

```python
import asyncio
from pywiim import Player

async def main():
    player = Player("192.168.1.100")
    await player.refresh()  # Load initial state
    
    # Access device properties
    print(f"Device: {player.name} ({player.model_name or player.model})")
    print(f"Playing: {player.play_state}")
    print(f"Volume: {player.volume}")
    
    # Control playback
    await player.set_volume(0.5)
    await player.play()
    
    await player.close()

asyncio.run(main())
```

See [API Reference](docs/integration/API_REFERENCE.md) for complete Player API documentation.


## Notification Playback Limitations

`play_notification()` uses a source-aware strategy so notifications are audible across more real-world scenarios:

- **Prompt path** (`playPromptUrl`) on device-controlled sources when the library considers them "native" (e.g. wifi, tunein, USB). When firmware supports it, the device can duck, play the prompt, and resume.
- **Fallback path** (`play_url`) on unsupported or unknown sources so the notification is always heard (interrupts current playback).
- **`force_interrupt=True`** — use for TTS when the prompt path is unreliable: always uses `play_url` so the notification is guaranteed audible.
- Returned result object reports what happened: `method_used`, `source_before`, `likely_interrupted`, `reason`.

### Why fallback exists

Prompt behavior (duck, play, resume) is **firmware- and source-dependent**. Some devices/sources return OK for `playPromptUrl` but do not play the prompt or do not resume. In those cases the library falls back to `play_url` so the notification is heard.

### Practical limitations

- Fallback playback is interruptive by design and may stop/replace the previous source session.
- Unknown/unmapped sources default to fallback for reliability.
- Do not overclaim duck/resume in integration release notes — behavior varies by device and firmware.

## Documentation

### User Guides
- [Discovery Guide](docs/user/DISCOVERY.md) - Device discovery via SSDP/UPnP
- [Diagnostics Guide](docs/user/DIAGNOSTICS.md) - Using the diagnostic tool
- [Real-time Monitor Guide](docs/user/MONITOR.md) - Real-time device monitoring

### Integration Guides
- [Home Assistant Integration](docs/integration/HA_INTEGRATION.md) - Complete guide for HA integrations
  - DataUpdateCoordinator patterns
  - Adaptive polling strategies
  - UPnP event integration
  - Queue management
  - Source-aware shuffle/repeat control
- [API Reference](docs/integration/API_REFERENCE.md) - Complete API documentation

### Design Documentation
- [Architecture & Data Flow](docs/design/ARCHITECTURE_DATA_FLOW.md) - System architecture
- [State Management](docs/design/STATE_MANAGEMENT.md) - State synchronization patterns
- [Operation Patterns](docs/design/OPERATION_PATTERNS.md) - Common operation patterns
- [LinkPlay Architecture](docs/design/LINKPLAY_ARCHITECTURE.md) - **In-depth analysis of LinkPlay/WiiM streaming architecture**
  - "Split Brain" control authority model
  - Transport protocol analysis (AirPlay, Spotify, USB, Bluetooth)
  - Hardware constraints (A98 SoM, RAM limits, queue management)
  - Why shuffle/repeat controls work differently for different sources
  - Integration strategies for automation systems

## Development Setup

See [SETUP.md](SETUP.md) for detailed development setup instructions.

Quick start:
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/unit/ -v

# Run code quality checks
make lint typecheck
```

## Acknowledgments

This library was made possible by the work of many developers who have reverse-engineered and documented the WiiM/LinkPlay API. We would like to acknowledge the following projects and resources that provided valuable API information and implementation insights:

### Libraries and Implementations
- **[python-linkplay](https://pypi.org/project/python-linkplay/)** - Python library for LinkPlay devices that provided insights into state detection and API patterns (enhanced state detection logic from v0.2.9)
- **[linkplay-cli](https://github.com/ramikg/linkplay-cli)** - Command-line tool for LinkPlay devices (provided SSL certificate reference for Audio Pro devices)
- **[WiiM HTTP API OpenAPI Specification](https://github.com/cvdlinden/wiim-httpapi)** - Comprehensive OpenAPI 3.0 specification for WiiM HTTP API endpoints
- **[Home Assistant WiiM Integration](https://github.com/mjcumming/wiim)** - Production-tested implementation that informed many design decisions, polling strategies, and state management patterns
- **[WiiM Play](https://github.com/shumatech/wiimplay)** - UPnP-based implementation that provided UPnP integration insights
- **[Velleman python-linkplay](https://github.com/Velleman/python-linkplay)** - Provided valuable API information and patterns for LinkPlay device communication
- **[Home Assistant LinkPlay Custom Component](https://github.com/nagyrobi/home-assistant-custom-components-linkplay)** - Custom Home Assistant integration for LinkPlay devices
- **[LinkPlay A31 Alternative Firmware](https://github.com/hn/linkplay-a31)** - Alternative firmware project that provided insights into LinkPlay hardware capabilities

### Official Documentation
- [Arylic LinkPlay API Documentation](https://developer.arylic.com/httpapi/) - Official LinkPlay protocol documentation
- [WiiM HTTP API PDF](https://www.wiimhome.com/pdf/HTTP%20API%20for%20WiiM%20Products.pdf) - Official WiiM API documentation

### Contributors and Notable Contributions
- **[jeromeof](https://github.com/jeromeof)** – Full Parametric EQ (PEQ) API ([PR #12](https://github.com/mjcumming/pywiim/pull/12)): WiiM LV2 PEQ support (10-band per-source, stereo/L-R channel modes, preset save/load/delete/rename). Implemented with capability probing (`supports_peq`) and integration tests against real devices.

### Additional Resources
- Various GitHub repositories and community contributions that helped document the LinkPlay protocol and WiiM-specific enhancements
- The LinkPlay and WiiM developer communities for sharing API discoveries and reverse-engineering efforts

If you know of other libraries or resources that should be acknowledged, please [open an issue](https://github.com/mjcumming/pywiim/issues) or submit a pull request.

## License

MIT License
