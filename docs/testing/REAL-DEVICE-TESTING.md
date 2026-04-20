# Real Device Testing Guide

This guide covers testing pywiim functionality against real WiiM/LinkPlay devices.

## Prerequisites

1. **Activate the virtual environment:**
```bash
cd /home/mike/projects/pywiim
source .venv/bin/activate
```

2. **Find your device IP address** (check your router or WiiM app)

3. **Ensure device is on the network and accessible**

4. **For HTTPS devices**, use port 443 (most modern devices)

## Manual HTTP probes (`curl`)

To hit **`httpapi.asp` directly** from the shell (read-only checks, firmware diffs, research such as [DLNA output #225](https://github.com/mjcumming/wiim/issues/225)), see **[CURL_HTTPAPI.md](CURL_HTTPAPI.md)** — HTTPS, `-k`, and safe starter commands.

## Quick Start: Unified Test Runner

The **recommended way** to test pywiim is using the unified test runner:

```bash
# List configured devices
python scripts/run_tests.py --list-devices

# Run smoke tests (Tier 1) - always works, no setup needed
python scripts/run_tests.py --tier smoke --device 192.168.1.115

# Run playback tests (Tier 2) - needs media playing
python scripts/run_tests.py --tier playback --device 192.168.1.115 --yes

# Run all tiers (1-4) for pre-release validation
python scripts/run_tests.py --prerelease --device 192.168.1.115 --yes
```

See [Unified Test Runner](#unified-test-runner) section below for details.

## Unified Test Runner

The **unified test runner** (`scripts/run_tests.py`) is the primary tool for comprehensive real-device testing. It supports tiered test suites with colorful real-time output.

### Test Tiers

| Tier | Name | Tests | Prerequisites |
|------|------|-------|---------------|
| 1 | Smoke | 8 | None - always works |
| 2 | Playback | 5 | Media playing on device |
| 3 | Controls | 5 | Album/playlist (NOT radio/station) |
| 4 | Features | 5 | Device-specific (EQ, PEQ, outputs) |
| 5 | Groups | 9 | Multiple devices (--master, --slave) |
| 6 | Advanced | TBD | Manual setup (BT, etc.) |

### Basic Usage

```bash
# Run smoke tests (Tier 1) - always works
python scripts/run_tests.py --tier smoke --device 192.168.1.115

# Run playback tests (Tier 2) - needs media playing
python scripts/run_tests.py --tier playback --device 192.168.1.115 --yes

# Run controls tests (Tier 3) - needs album/playlist (NOT radio)
python scripts/run_tests.py --tier controls --device 192.168.1.115 --yes

# Run features tests (Tier 4) - EQ, outputs, presets
python scripts/run_tests.py --tier features --device 192.168.1.115 --yes

# Run pre-release suite (Tiers 1-4)
python scripts/run_tests.py --prerelease --device 192.168.1.115 --yes

# Run all tiers
python scripts/run_tests.py --all --device 192.168.1.115 --yes
```

### Group Tests (Tier 5)

```bash
# Run group tests with master and slave
python scripts/run_tests.py --tier groups --master 192.168.1.115 --slave 192.168.1.116 --yes
```

Group tests verify:
- Ensure devices start as solo
- Create group on master
- Slave joins group
- Role detection (master/slave)
- Volume propagation
- Mute propagation (mute_all)
- Command routing (slave commands → master)
- Metadata propagation
- Group disband (both return to solo)

### Device Configuration

Configure devices in `scripts/test_devices.yaml` (or `tests/devices.yaml` for pytest integration tests):

```yaml
devices:
  - ip: 192.168.1.115
    name: "Living Room Pro"
    model: wiim_pro
    capabilities:
      - eq
      - peq    # Parametric EQ (WiiM only; probed at runtime)
      - presets
    notes: "Primary test device"

default_device: 192.168.1.115
```

**PEQ integration tests:** Run Parametric EQ tests against a WiiM device with `pytest tests/integration/test_peq.py -v -m integration` (requires `WIIM_TEST_DEVICE` or default from config). See [PR #12](https://github.com/mjcumming/pywiim/pull/12) for the PEQ API contribution.

**LED Indicator and Display:** To verify LED indicator and display capabilities on a device, run the diagnostics CLI. It reports `supports_led_indicator` (LED Indicator) and `supports_display_config` (Display, WiiM Ultra only).

```bash
python -m pywiim.cli.diagnostics <device_ip>
# or: wiim-diagnostics <device_ip>
```

Validation results (six test devices, 2026-03-10):

| Device IP     | Model / Name           | Vendor | supports_led_indicator | supports_display_config |
|---------------|------------------------|--------|------------------------|-------------------------|
| 192.168.1.115 | WiiM Pro (Outdoor)     | wiim   | Yes                    | No                      |
| 192.168.1.116 | WiiM Pro (Master Bedroom) | wiim | Yes                    | No                      |
| 192.168.1.68  | WiiM Pro (Main Floor)  | wiim   | Yes                    | No                      |
| 192.168.6.95  | UP2STREAM_AMP_V4 (Dock) | arylic | Yes                    | No                      |
| 192.168.6.50  | ARYLIC_H50 (Main Deck) | arylic | Yes                    | No                      |
| 192.168.6.223 | WiiM Pro (Cabin)       | wiim   | Yes                    | No                      |

### Options

- `--device IP` - Specify device IP (default from config)
- `--yes` / `-y` - Skip confirmation prompts
- `--list-devices` - Show configured test devices
- `--config PATH` - Custom config file
- `--master IP` - Master device for group tests
- `--slave IP` - Slave device for group tests

### Interactive Manual Testing

For hands-on manual testing and exploration:

```bash
python scripts/manual/interactive-playback-test.py <device_ip>
```

**Available commands:**
```
  1  - Play
  2  - Pause
  3  - Resume
  4  - Stop
  5  - Next Track
  6  - Previous Track
  s  - Show Current Status
  h+ - Shuffle ON
  h- - Shuffle OFF
  r0 - Repeat OFF
  r1 - Repeat ONE
  ra - Repeat ALL
  q  - Quit
```

## Method Details

### Play/Pause Methods

**Available methods:**
```python
await player.play()      # Start playback
await player.pause()     # Pause playback
await player.resume()    # Resume from pause
await player.stop()      # Stop playback
```

**Properties:**
```python
player.play_state        # Returns: "play", "pause", "stop", etc.
```

### Shuffle Control

**Methods:**
```python
await player.set_shuffle(True)   # Enable shuffle
await player.set_shuffle(False)  # Disable shuffle
```

**Properties:**
```python
player.shuffle_state     # Returns: True/False/None
player.shuffle          # Alias for shuffle_state
```

**Important:** Setting shuffle preserves the current repeat mode.

### Repeat Control

**Methods:**
```python
await player.set_repeat("off")   # Disable repeat
await player.set_repeat("one")   # Repeat current track
await player.set_repeat("all")   # Repeat all tracks
```

**Properties:**
```python
player.repeat_mode      # Returns: "off", "one", "all", or None
player.repeat          # Alias for repeat_mode
```

**Important:** Setting repeat preserves the current shuffle state.

## Loop Mode Mapping

Under the hood, shuffle and repeat are controlled by a single `loop_mode` value:

| Mode | Shuffle | Repeat | loop_mode Value |
|------|---------|--------|-----------------|
| Normal | Off | Off | 0 |
| Repeat One | Off | One | 1 |
| Repeat All | Off | All | 2 |
| Shuffle | On | Off | 4 |
| Shuffle + Repeat One | On | One | 5 |
| Shuffle + Repeat All | On | All | 6 |

The Player class automatically manages these combinations to preserve state when you change shuffle or repeat individually.

## Troubleshooting

### Device not responding
- Verify device IP address
- Check device is powered on and connected to network
- Try pinging the device: `ping <device_ip>`
- Check firewall settings

### Tests fail but device works manually
- Ensure device has media in queue
- Try refreshing player state: `await player.refresh()`
- Check device firmware is up to date

### State not updating
- Allow 1-2 seconds for state changes to propagate
- Call `await player.refresh()` to force state update
- Some older firmware versions may have delays

## Integration Tests (pytest)

For pytest-based integration tests:

### Single Device Tests

```bash
# Set environment variable
export WIIM_TEST_DEVICE=192.168.1.115

# Run core integration tests (fast, safe)
pytest tests/integration/test_real_device.py -v -m core

# Run pre-release integration tests (comprehensive)
pytest tests/integration/test_prerelease.py -v -m prerelease

# For HTTPS devices
export WIIM_TEST_PORT=443
export WIIM_TEST_HTTPS=true
pytest tests/integration/test_real_device.py -v -m integration
```

### Multi-Device Group Tests

Use the multi-room integration test to verify master/slave logic, volume/mute propagation, and command routing:

**Environment Setup:**
```bash
export WIIM_TEST_GROUP_MASTER=192.168.1.115
export WIIM_TEST_GROUP_SLAVES="192.168.1.116,192.168.1.117"
# Optional overrides:
export WIIM_TEST_PORT=443
export WIIM_TEST_HTTPS=true
```

**Run Tests:**
```bash
pytest tests/integration/test_multiroom_group.py -v
```

**What It Verifies:**
- SOLO ➜ MASTER ➜ SLAVE transitions via `Player.create_group()` / `join_group()`
- `get_device_group_info()` consistency for master and every slave
- Virtual master state feeding slaves (metadata + source pointer)
- Group volume/mute rules (`Group.set_volume_all` & `Group.mute_all`)
- Routing of `Group.next_track()` / `Group.previous_track()` back to the physical master

**Checklist Before Running:**
1. All devices reachable on the same network (no existing group sessions)
2. Optional: start playback so next/previous commands succeed
3. Virtualenv activated
4. Run the test and watch the console for PASS/SKIP results

### Group Testing CLI Tool

For focused group testing, use the CLI tool:

```bash
# Interactive mode with visual verification
wiim-group-test 192.168.1.115 192.168.1.116 --interactive

# Automated test with pauses
wiim-group-test 192.168.1.115 192.168.1.116 --pause 5

# See GROUP_TEST_CLI.md for full documentation
```

See [GROUP_TEST_CLI.md](GROUP_TEST_CLI.md) for complete CLI tool documentation.

## Testing Workflow Recommendations

### Pre-Release Validation

1. **Run smoke tests** (Tier 1) - Always works, no setup needed
   ```bash
   python scripts/run_tests.py --tier smoke --device 192.168.1.115
   ```

2. **Start media playing**, then run playback tests (Tier 2)
   ```bash
   python scripts/run_tests.py --tier playback --device 192.168.1.115 --yes
   ```

3. **Ensure album/playlist is playing** (NOT radio), run controls tests (Tier 3)
   ```bash
   python scripts/run_tests.py --tier controls --device 192.168.1.115 --yes
   ```

4. **Run feature tests** (Tier 4) - EQ, outputs, presets
   ```bash
   python scripts/run_tests.py --tier features --device 192.168.1.115 --yes
   ```

5. **Or run all at once** with pre-release suite
   ```bash
   python scripts/run_tests.py --prerelease --device 192.168.1.115 --yes
   ```

6. **Test groups** (if you have multiple devices) - Tier 5
   ```bash
   python scripts/run_tests.py --tier groups --master 192.168.1.115 --slave 192.168.1.116 --yes
   ```

### Quick Verification

For quick verification of specific features:
- **Playback controls**: Use `scripts/manual/interactive-playback-test.py`
- **Group operations**: Use `wiim-group-test` CLI tool
- **Integration tests**: Use pytest with environment variables

## Related Documentation

- [GROUP_TEST_CLI.md](GROUP_TEST_CLI.md) - Group testing CLI tool guide
- [GROUP_ROUTING_TESTS.md](GROUP_ROUTING_TESTS.md) - Group routing and testing details
- [tests/README.md](../../tests/README.md) - Test suite documentation
- [scripts/README.md](../../scripts/README.md) - Scripts documentation

