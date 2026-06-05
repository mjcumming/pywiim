# Device Discovery

The `pywiim` library includes comprehensive device discovery tools to find WiiM and LinkPlay devices on your network.

## Quick Start

### Command Line Tool

```bash
# Discover all devices (SSDP + network scan)
wiim-discover

# Discover via SSDP only
wiim-discover --methods ssdp

# Discover via network scan only
wiim-discover --methods network_scan

# Scan specific network
wiim-discover --network 192.168.0.0/24

# Output as JSON
wiim-discover --output json

# Save report to file
wiim-discover --output json > devices.json
```

### Python API

```python
import asyncio
from pywiim import discover_devices

async def main():
    # Discover all devices
    devices = await discover_devices()
    
    for device in devices:
        print(f"Found: {device.name} @ {device.ip}")
        print(f"  Model: {device.model}")
        print(f"  Firmware: {device.firmware}")
        print(f"  Vendor: {device.vendor}")

asyncio.run(main())
```

## Discovery Methods

### SSDP/UPnP Discovery

Discovers devices via SSDP (Simple Service Discovery Protocol) and UPnP.

**Advantages**:
- Fast (typically 1-5 seconds)
- Finds devices that advertise via UPnP
- Gets device information from UPnP description
- Optimized filtering: Automatically skips known non-LinkPlay devices (Chromecast, Denon Heos, Sony, Kodi, etc.) before validation for faster discovery

**Limitations**:
- Requires `async-upnp-client` library
- May not find all devices (some don't advertise)
- Network firewall may block SSDP

**Usage**:
```python
from pywiim import discover_via_ssdp

devices = await discover_via_ssdp(timeout=5)
```

### Network Scanning

Scans network IP ranges to find devices by attempting connections.

**Advantages**:
- Finds all devices (even if they don't advertise)
- Works when SSDP is blocked
- Can scan specific network ranges

**Limitations**:
- Slower (must probe each IP)
- More network traffic
- May trigger firewall alerts

**Usage**:
```python
from pywiim import scan_network

devices = await scan_network(
    network="192.168.1.0/24",
    timeout=1.0,
    ports=[80, 443, 4443]
)
```

## LinkPlay Device Identification

### The LinkPlay Ecosystem

LinkPlay Technology Inc. is a Shanghai-based ODM (Original Design Manufacturer) that provides the silicon and software stack for a vast array of networked audio devices. While these devices are sold under different brands, they share a common firmware architecture:

| Brand | Manufacturer Field | Notes |
|-------|-------------------|-------|
| **WiiM** | `Linkplay Technology Inc.` | First-party LinkPlay brand |
| **Arylic** | `Rakoit Technology(SZ) Co., Ltd.` | Rakoit is the hardware manufacturing arm |
| **Audio Pro** | `Audio Pro` | Swedish audio company using LinkPlay modules |
| **iEAST** | `iEAST` | Budget-friendly LinkPlay devices |
| **Muzo** | `Muzo` | Often shares iEAST/Rakoit identifiers |

### The "White Label" Challenge

Identifying LinkPlay devices on a network is challenging because manufacturers customize the SSDP/UPnP headers to maintain brand identity. The "LinkPlay" name is often scrubbed from user-facing metadata.

**Why this matters**: When SSDP discovers devices, it finds ALL UPnP devices on the network - including Samsung TVs, Sonos speakers, Chromecast, and other non-LinkPlay devices that we need to filter out.

### Network Discovery Identifiers

LinkPlay devices can be identified through several network protocols:

#### SSDP Headers

| Header | LinkPlay Pattern | Non-LinkPlay Examples |
|--------|-----------------|----------------------|
| `SERVER` | `Linux/x.x UPnP/1.0...` (generic) | `Sonos/70.1`, `Samsung/1.0` |
| `ST` | `urn:schemas-upnp-org:device:MediaRenderer:1` | `urn:schemas-upnp-org:device:ZonePlayer:1` (Sonos) |
| `LOCATION` port | Usually `49152` | Sonos: `1400`, Samsung: `9197`, Chromecast: `8008` |

**Important**: The `SERVER` header is **unreliable** for positive identification. Most LinkPlay devices (especially Arylic and Audio Pro) use generic `Linux/x.x.x UPnP/1.0 Portable SDK for UPnP devices/x.x.x` headers that are shared by thousands of IoT devices.

#### The "Wiimu" Namespace (Definitive Identifier)

The most reliable way to identify a LinkPlay device is the proprietary **"Wiimu"** service namespace in the UPnP description:

```xml
<service>
  <serviceType>urn:schemas-wiimu-com:service:PlayQueue:1</serviceType>
  <serviceId>urn:wiimu-com:serviceId:PlayQueue</serviceId>
</service>
```

"Wiimu" (WiFi Music) is LinkPlay's legacy trade name. This namespace is **unique to LinkPlay devices** - no other manufacturer uses it. If a device exposes `PlayQueue:1` in its UPnP services, it is definitively a LinkPlay device.

#### mDNS Service Type (Not Used)

LinkPlay devices also advertise via mDNS (Multicast DNS / Bonjour):

```
_linkplay._tcp.local.
```

While this is 100% reliable for identification, **pywiim does not use mDNS discovery**. The mDNS/TCP approach is legacy and not actively used in modern integrations. SSDP combined with HTTP API probing provides equivalent reliability with better compatibility across network environments.

### How pywiim Identifies LinkPlay Devices

The library uses a **three-tier validation approach**:

#### Tier 1: SSDP Pattern Filtering (Fast Reject)

Known non-LinkPlay devices are rejected immediately based on SSDP headers:

| Pattern Type | Examples |
|-------------|----------|
| **SERVER patterns** | `Sonos`, `Samsung`, `Chromecast`, `Denon-Heos`, `SmartThings` |
| **ST patterns** | `urn:schemas-upnp-org:device:ZonePlayer` (Sonos), `urn:samsung.com:device` |

This prevents unnecessary API probes to devices we know aren't LinkPlay.

#### Tier 2: Known LinkPlay Fast Path (Skip Probe)

Devices that identify themselves as LinkPlay in their SSDP `SERVER` header skip the API probe:

| Pattern | Example |
|---------|---------|
| `WiiM` | `Linux UPnP/1.0 WiiM/4.8.5` |
| `Linkplay` | `Linux/3.x.x Linkplay/4.8.5` |

**Note**: Many LinkPlay devices (Arylic, Audio Pro) use generic `Linux` headers and won't match these patterns. They proceed to Tier 3.

#### Tier 3: API Probe (Definitive Check)

For devices that pass Tier 1 but don't match Tier 2, pywiim probes the LinkPlay HTTP API:

```
/httpapi.asp?command=getStatusEx
/httpapi.asp?command=getStatus
```

If the device returns a valid JSON response, it's confirmed as LinkPlay. Non-LinkPlay devices (Samsung TVs, random Linux servers) will return 404, connection errors, or non-JSON responses.

### Device-Specific Notes

#### WiiM Devices
- Usually include "WiiM" in SERVER header → Fast path
- Modern devices (Pro, Amp, Ultra) support HTTPS API
- Port 49152 for UPnP description, Port 80/443 for HTTP API

#### Arylic Devices
- Use generic "Linux" SERVER headers → Require API probe
- Manufacturer: `Rakoit Technology(SZ) Co., Ltd.`
- Some models (LP10) are NOT LinkPlay-based

#### Audio Pro Devices
- Use generic "Linux" SERVER headers → Require API probe
- Some firmware versions hide the PlayQueue service from SSDP broadcasts
- Still expose it in the full `description.xml`

#### Hardware Generations

| Generation | Chipset | Kernel | Devices |
|------------|---------|--------|---------|
| **Legacy (MIPS)** | MediaTek MT7688AN | Linux 2.6/3.10 | Arylic Up2Stream v3, older Audio Pro |
| **Modern (ARM)** | Amlogic A113/A98 | Linux 4.x/5.x | WiiM Mini/Pro/Amp, newer devices |

## Discovery API

### `discover_devices()`

Main discovery function that uses multiple methods.

```python
from pywiim import discover_devices

devices = await discover_devices(
    methods=["ssdp", "network_scan"],  # Methods to use
    validate=True,                      # Validate via API
    network="192.168.1.0/24",          # Network for scanning
    ssdp_timeout=5                      # SSDP timeout
)
```

**Parameters**:
- `methods`: List of methods to use (`["ssdp"]`, `["network_scan"]`, or both)
- `validate`: Whether to validate devices via API (default: `True`)
- `network`: Network CIDR for network scanning (default: `"192.168.1.0/24"`)
- `ssdp_timeout`: SSDP discovery timeout in seconds (default: `5`)

**Returns**: List of `DiscoveredDevice` objects

### `DiscoveredDevice`

Represents a discovered device.

```python
@dataclass
class DiscoveredDevice:
    ip: str                    # IP address
    name: str | None           # Device name
    model: str | None          # Device model
    firmware: str | None       # Firmware version
    mac: str | None           # MAC address
    uuid: str | None          # Device UUID
    port: int                 # Port (80, 443, 4443)
    protocol: str             # "http" or "https"
    vendor: str | None        # "wiim", "arylic", "audio_pro", etc.
    discovery_method: str     # "ssdp", "network_scan", "manual"
    validated: bool           # Whether validated via API
    ssdp_response: dict[str, Any] | None = None  # Internal: SSDP response for filtering
```

**Methods**:
- `to_dict()`: Convert to dictionary
- `__str__()`: String representation

### `validate_device()`

Validate a discovered device by querying its API.

```python
from pywiim import validate_device, DiscoveredDevice

device = DiscoveredDevice(ip="192.168.1.100")
validated_device = await validate_device(device)

# Device now has full information:
# - name, model, firmware, mac, uuid
# - vendor (detected from capabilities)
# - validated = True
```

`validate_device()` is a soft validation helper for discovery scans. If the
host does not validate as a LinkPlay/WiiM device, it returns the device with
`validated = False` instead of raising. Callers must check `validated` before
creating persistent config entries or clients from user-supplied hosts.

For manual setup flows where an unvalidated host should be an error, use
`validate_device_strict()`:

```python
from pywiim import DiscoveredDevice, validate_device_strict

device = await validate_device_strict(DiscoveredDevice(ip="192.168.1.100"))
# Raises WiiMConnectionError if the host is not a valid LinkPlay/WiiM device.
```

## Examples

### Discover and List All Devices

```python
import asyncio
from pywiim import discover_devices

async def main():
    print("Discovering devices...")
    devices = await discover_devices()
    
    print(f"\nFound {len(devices)} device(s):\n")
    for i, device in enumerate(devices, 1):
        print(f"{i}. {device.name or 'Unknown'} ({device.model})")
        print(f"   IP: {device.ip}:{device.port}")
        print(f"   Firmware: {device.firmware}")
        print(f"   Vendor: {device.vendor}")
        print()

asyncio.run(main())
```

### Discover and Create Clients

```python
import asyncio
from pywiim import discover_devices, WiiMClient

async def main():
    # Discover devices
    devices = await discover_devices()
    
    # Create clients for all devices
    clients = []
    for device in devices:
        client = WiiMClient(device.ip, port=device.port)
        clients.append(client)
    
    # Use clients
    for client in clients:
        status = await client.get_player_status()
        print(f"{client.host}: {status.get('play_state')}")
        await client.close()

asyncio.run(main())
```

### Discover Specific Network

```python
import asyncio
from pywiim import discover_devices

async def main():
    # Scan office network
    office_devices = await discover_devices(
        methods=["network_scan"],
        network="10.0.0.0/24"
    )
    
    # Scan home network
    home_devices = await discover_devices(
        methods=["ssdp"],
        network="192.168.1.0/24"
    )
    
    print(f"Office: {len(office_devices)} devices")
    print(f"Home: {len(home_devices)} devices")

asyncio.run(main())
```

### Export to JSON

```python
import asyncio
import json
from pywiim import discover_devices

async def main():
    devices = await discover_devices()
    
    # Convert to JSON
    devices_dict = [device.to_dict() for device in devices]
    
    # Save to file
    with open("devices.json", "w") as f:
        json.dump(devices_dict, f, indent=2)
    
    print(f"Exported {len(devices)} devices to devices.json")

asyncio.run(main())
```

## Command Line Tool

### Installation

The `wiim-discover` command is installed automatically with `pywiim`:

```bash
pip install pywiim
```

### Usage

```bash
# Basic discovery
wiim-discover

# SSDP only
wiim-discover --methods ssdp

# Network scan only
wiim-discover --methods network_scan

# Custom network
wiim-discover --network 192.168.0.0/24

# JSON output
wiim-discover --output json

# Skip validation (faster)
wiim-discover --no-validate

# Verbose logging
wiim-discover --verbose
```

### Options

- `--methods`: Discovery methods (`ssdp`, `network_scan`, or both)
- `--network`: Network CIDR for scanning (default: `192.168.1.0/24`)
- `--ssdp-timeout`: SSDP timeout in seconds (default: `5`)
- `--no-validate`: Skip API validation (faster but less info)
- `--output`: Output format (`text` or `json`)
- `--verbose`: Enable verbose logging

## Troubleshooting

### No Devices Found

1. **Check network**: Ensure devices are on the same network
2. **Try network scan**: SSDP may be blocked
   ```bash
   wiim-discover --methods network_scan
   ```
3. **Check firewall**: SSDP uses UDP port 1900
4. **Try manual IP**: If you know the IP, use it directly
   ```python
   from pywiim import validate_device, DiscoveredDevice
   
   device = DiscoveredDevice(ip="192.168.1.100")
   validated = await validate_device(device)
   ```

### SSDP Not Working

If SSDP discovery fails:

1. **Install dependency**: Ensure `async-upnp-client` is installed
   ```bash
   pip install async-upnp-client
   ```
2. **Use network scan**: Fall back to network scanning
3. **Check network**: Ensure devices support UPnP/SSDP

### WSL2 Multicast Issues

If you're running in WSL2 and SSDP discovery doesn't work:

**Problem**: WSL2's default NAT networking mode doesn't support multicast properly, which SSDP requires.

**Solution**: Enable mirrored networking mode:

1. **Create/Edit `.wslconfig`** in your Windows user directory (`C:\Users\<YourUsername>\.wslconfig`):
   ```ini
   [wsl2]
   networkingMode=mirrored
   firewall=false
   ```

2. **Restart WSL** (run in PowerShell or Command Prompt):
   ```powershell
   wsl --shutdown
   ```

3. **Verify Windows Firewall** (run in PowerShell as Administrator):
   ```powershell
   Set-NetFirewallHyperVVMSetting -Name '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' -DefaultInboundAction Allow
   ```

4. **Test multicast**:
   ```bash
   # In WSL, test if multicast socket works
   python3 -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(('', 1900)); s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton('239.255.255.250') + socket.inet_aton('0.0.0.0')); print('Multicast OK')"
   ```

**Note**: Even with mirrored mode, SSDP may still not work perfectly in WSL. Use network scanning as a fallback:
   ```bash
   wiim-discover --methods network_scan
   ```

### Slow Discovery

Network scanning can be slow on large networks:

1. **Use SSDP**: Faster but may miss devices
2. **Limit network range**: Scan smaller subnet
3. **Skip validation**: Use `--no-validate` for faster discovery
4. **Reduce timeout**: Lower `--ssdp-timeout` (may miss devices)

## Integration with Home Assistant

The discovery module can be used in HA integration:

```python
# In config_flow.py
from pywiim import discover_devices

async def async_step_discovery(self):
    devices = await discover_devices(methods=["ssdp"])
    
    # Show discovered devices to user
    options = [f"{d.name} ({d.ip})" for d in devices]
    # ... show form with options
```

## Best Practices

1. **Use SSDP first**: Faster and less network traffic
2. **Fall back to network scan**: If SSDP doesn't find devices
3. **Validate devices**: Always validate to get full information
4. **Cache results**: Discovery can be slow, cache results when possible
5. **Handle errors**: Discovery may fail, handle gracefully

## Performance

- **SSDP**: Typically 1-5 seconds
- **Network scan**: Depends on network size (192.168.1.0/24 ≈ 30-60 seconds)
- **Validation**: ~1 second per device

### Performance Optimization

The discovery system uses a **three-tier validation approach** to minimize network traffic and discovery time:

#### Tier 1: SSDP Pattern Filtering (Instant)
Known non-LinkPlay devices are rejected immediately based on SSDP headers:
- Sonos, Samsung, Chromecast, Denon-Heos, SmartThings, Roku, etc.
- No network calls required - pure string matching

#### Tier 2: Known LinkPlay Fast Path (~0ms)
Devices that identify themselves as LinkPlay (e.g., "WiiM" in SERVER header) skip the API probe and go directly to full validation.

#### Tier 3: API Probe (~1-3 seconds)
For devices with generic headers (Arylic, Audio Pro), we probe the LinkPlay API endpoints (`getStatusEx`/`getStatus`) to confirm compatibility.

**Performance characteristics**:

| Device Type | Tier | Time | Network Calls |
|-------------|------|------|--------------|
| Samsung TV | 1 (rejected) | ~0ms | 0 |
| Sonos | 1 (rejected) | ~0ms | 0 |
| WiiM | 2 (fast path) | ~1s | 1 (full validation) |
| Arylic | 3 (probe) | ~2-4s | 2 (probe + validation) |
| Random device | 3 (probe fails) | ~3s | 1 (probe timeout) |

**Example**: If SSDP discovers 5 devices (3 non-LinkPlay + 1 WiiM + 1 Arylic):
- **Before optimization**: ~25 seconds (validates all 5 devices)
- **After optimization**: ~5 seconds (skips 3, fast-paths 1, probes 1)

For best performance:
- Use SSDP when possible (includes automatic filtering)
- Limit network scan range
- Validate devices in parallel
- Cache discovery results
