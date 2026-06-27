# Diagnostic Tool

The `pywiim` library includes a comprehensive diagnostic tool that can help troubleshoot device issues and gather information for support.

## Quick Start

```bash
# Install the library
pip install pywiim

# Run diagnostics on your device
python -m pywiim.diagnostics 192.168.1.100

# Or use the command-line script (after installation)
wiim-diagnostics 192.168.1.100
```

## Usage

### Basic Diagnostic

```bash
python -m pywiim.diagnostics <device_ip>
```

This will:
- Connect to your device
- Gather device information (model, firmware, MAC address)
- Detect device capabilities
- Test all API endpoints
- Test supported features
- Display a summary report

### Save Report to File

```bash
python -m pywiim.diagnostics 192.168.1.100 --output report.json
```

This saves a complete JSON report that can be shared with developers for troubleshooting.

### HTTPS Devices

For devices that require HTTPS:

```bash
python -m pywiim.diagnostics 192.168.1.100 --port 443
```

### Discovered WiiM API Probe

To probe only the read-only WiiM APIs discovered from app traffic:

```bash
python -m pywiim.cli.diagnostics 192.168.1.100 --discovered-apis-only --output discovered-apis.json
```

This checks `getAudioInputEnable`, `getModeRename`, `GetAcousticCapability`,
`getAllRoutines`, and `getSoundCardModeSupportList` without running the full
diagnostic feature suite.

### Verbose Output

For detailed logging:

```bash
python -m pywiim.diagnostics 192.168.1.100 --verbose
```

## Report Contents

The diagnostic report includes:

### Device Information
- Device name and model
- Firmware version
- MAC address
- UUID
- Available input sources
- Preset slot count

### Capabilities
- Vendor (WiiM, Arylic, Audio Pro, etc.)
- Device type (WiiM vs Legacy)
- Generation (for Audio Pro devices)
- Supported features list
- UPnP `description.xml` enrichment (when available):
  - `upnp_friendly_name`, `upnp_model_name`, `upnp_udn`
  - Advertised service flags: `upnp_has_playqueue`, `upnp_has_qplay`, `upnp_has_content_directory`
- Protocol preferences
- Timeout settings

### Status
- Current play state
- Volume level
- Mute status
- Current source
- Playback position
- Track metadata (if available)

### Endpoint Testing
Tests all API endpoints and reports:
- Which endpoints work
- Which endpoints fail
- Error messages for failures

### Feature Testing
Tests specific features:
- Presets support
- EQ support
- Multiroom support
- Bluetooth support
- Audio settings support
- LMS integration support

### Errors and Warnings
Lists any errors or warnings encountered during testing.

## Example Output

```
🔍 Starting comprehensive device diagnostic...
   Device: 192.168.1.100:80

📋 Gathering device information...
   ✓ Device: Living Room (WiiM Pro)
   ✓ Firmware: 5.0.1
   ✓ MAC: AA:BB:CC:DD:EE:FF

🔧 Detecting device capabilities...
   ✓ Vendor: wiim
   ✓ Type: WiiM
   ✓ Supported features: enhanced grouping, audio output, metadata, presets, eq

📊 Gathering device status...
   ✓ Play state: play
   ✓ Volume: 0.5
   ✓ Source: spotify

🧪 Testing API endpoints...
   ✓ getStatusEx: OK
   ✓ getDeviceInfo: OK
   ✓ getPlayerStatus: OK
   ✓ getPresets: OK
   ✓ getEQ: OK
   ...

🎯 Testing specific features...
   ✓ Presets: supported
   ✓ EQ: supported
   ✓ Multiroom: supported
   ...

============================================================
📋 DIAGNOSTIC REPORT SUMMARY
============================================================

Device: WiiM Pro (Firmware: 5.0.1)
Vendor: wiim

Endpoints: 8/8 successful
Features: 6/6 supported

============================================================

💡 Tip: Use --output to save full report to JSON file
```

## Sharing Reports

When reporting issues, you can share the diagnostic report:

1. **Run diagnostics and save to file:**
   ```bash
   python -m pywiim.diagnostics 192.168.1.100 --output my-device-report.json
   ```

2. **Share the JSON file** with developers or attach to GitHub issues.

The JSON report contains all the information needed to understand your device configuration and troubleshoot issues.

## Troubleshooting

### Connection Errors

If you get connection errors:
- Verify the device IP address is correct
- Check that the device is on the same network
- Try using `--port 443` for HTTPS devices
- Check firewall settings

### Timeout Errors

If requests timeout:
- The device may be slow to respond (legacy devices)
- Network connectivity issues
- Device may be busy

### Missing Features

If features show as "not supported":
- This is normal - not all devices support all features
- Check the device model and firmware version
- Some features require specific firmware versions

## Integration with Support

This diagnostic tool is designed to make it easy to gather information for support:

1. **User runs diagnostics:**
   ```bash
   python -m pywiim.diagnostics <device_ip> --output report.json
   ```

2. **User shares report.json** with support/developers

3. **Support can analyze:**
   - Device capabilities
   - Firmware version
   - Which endpoints work/fail
   - Error messages
   - Feature support

This eliminates the need for back-and-forth questions about device configuration.
