# Code Examples

Practical examples for using the `pywiim` library.

## Table of Contents

- [Basic Usage](#basic-usage)
- [Device Discovery](#device-discovery)
- [Playback Control](#playback-control)
- [Multiroom Groups](#multiroom-groups)
- [Presets](#presets)
- [Equalizer](#equalizer)
- [Bluetooth](#bluetooth)
- [Error Handling](#error-handling)
- [Capability Detection](#capability-detection)
- [State Monitoring](#state-monitoring)

## Basic Usage

### Connect and Get Device Info

```python
import asyncio
from pywiim import WiiMClient

async def main():
    # Create client
    client = WiiMClient("192.168.1.100")
    
    try:
        # Get device information
        device_info = await client.get_device_info_model()
        print(f"Device: {device_info.name}")
        print(f"Model: {device_info.model}")
        print(f"Firmware: {device_info.firmware}")
        print(f"MAC: {device_info.mac}")
        
        # Get player status
        status = await client.get_player_status()
        print(f"State: {status.get('play_state')}")
        print(f"Volume: {status.get('volume')}")
        print(f"Source: {status.get('source')}")
        
    finally:
        await client.close()

asyncio.run(main())
```

### Simple Playback Control

```python
import asyncio
from pywiim import WiiMClient

async def main():
    client = WiiMClient("192.168.1.100")
    
    try:
        # Set volume to 50%
        await client.set_volume(0.5)
        
        # Play
        await client.play()
        
        # Wait a bit
        await asyncio.sleep(5)
        
        # Pause
        await client.pause()
        
        # Resume
        await client.resume()
        
        # Stop
        await client.stop()
        
    finally:
        await client.close()

asyncio.run(main())
```

## Device Discovery

### Find Devices on Network

```python
import asyncio
from pywiim import WiiMClient

async def discover_devices():
    """Simple device discovery by trying common IP ranges."""
    devices = []
    
    # Try common IP ranges (adjust for your network)
    base_ip = "192.168.1"
    
    for i in range(1, 255):
        ip = f"{base_ip}.{i}"
        client = WiiMClient(ip, timeout=1.0)
        
        try:
            # Try to get device info (quick test)
            info = await client.get_device_info_model()
            devices.append({
                "ip": ip,
                "name": info.name,
                "model": info.model,
                "firmware": info.firmware,
            })
            print(f"Found: {info.name} at {ip}")
        except Exception:
            pass  # Not a WiiM device
        finally:
            await client.close()
    
    return devices

# Run discovery
devices = asyncio.run(discover_devices())
print(f"\nFound {len(devices)} devices")
```

## Playback Control

### Control Playback with Status Monitoring

```python
import asyncio
from pywiim import WiiMClient

async def monitor_and_control():
    client = WiiMClient("192.168.1.100")
    
    try:
        # Get initial status
        status = await client.get_player_status()
        print(f"Initial state: {status.get('play_state')}")
        
        # Start playing
        await client.play()
        
        # Monitor for 10 seconds
        for i in range(10):
            await asyncio.sleep(1)
            status = await client.get_player_status()
            play_state = status.get('play_state')
            position = status.get('position', 0)
            duration = status.get('duration', 0)
            
            if play_state == "play":
                print(f"Playing: {position}/{duration}s - "
                      f"{status.get('title', 'Unknown')}")
        
        # Stop
        await client.stop()
        
    finally:
        await client.close()

asyncio.run(monitor_and_control())
```

### Play from URL

```python
import asyncio
from pywiim import WiiMClient

async def play_stream():
    client = WiiMClient("192.168.1.100")
    
    try:
        # Play a stream URL
        url = "http://stream.example.com/radio.mp3"
        await client.play_url(url)
        
        print("Stream started")
        
        # Monitor playback
        while True:
            status = await client.get_player_status()
            if status.get('play_state') != 'play':
                break
            await asyncio.sleep(1)
        
    finally:
        await client.close()

asyncio.run(play_stream())
```

## Multiroom Groups

### Create and Manage Groups

```python
import asyncio
from pywiim import WiiMClient

async def manage_group():
    master = WiiMClient("192.168.1.100")
    slave = WiiMClient("192.168.1.101")
    
    try:
        # Check current status
        print(f"Master is master: {master.is_master}")
        print(f"Slave is slave: {slave.is_slave}")
        
        # Create group (on master)
        await master.create_group()
        print("Group created")
        
        # Join slave to group
        await slave.join_slave("192.168.1.100")
        print("Slave joined group")
        
        # Get group info
        multiroom = await master.get_multiroom_status()
        slaves = await master.get_slaves()
        print(f"Group has {len(slaves)} slaves")
        
        # Play on master (will sync to slaves)
        await master.play()
        
        # Wait
        await asyncio.sleep(10)
        
        # Leave group
        await slave.leave_group()
        print("Slave left group")
        
        # Delete group
        await master.delete_group()
        print("Group deleted")
        
    finally:
        await master.close()
        await slave.close()

asyncio.run(manage_group())
```

## Presets

### List and Play Presets

```python
import asyncio
from pywiim import WiiMClient

async def use_presets():
    client = WiiMClient("192.168.1.100")
    
    try:
        # Check if presets are supported
        if not client.capabilities.get("supports_presets"):
            print("Presets not supported on this device")
            return
        
        # Get all presets
        presets = await client.get_presets()
        print(f"Found {len(presets)} presets:")
        
        for preset in presets:
            print(f"  {preset.get('number')}: {preset.get('name')}")
        
        # Get max preset slots
        max_slots = await client.get_max_preset_slots()
        print(f"\nMax preset slots: {max_slots}")
        
        # Play a preset
        if presets:
            preset_num = presets[0].get('number')
            print(f"\nPlaying preset {preset_num}...")
            await client.play_preset(preset_num)
        
    finally:
        await client.close()

asyncio.run(use_presets())
```

## Equalizer

### Adjust EQ Settings

```python
import asyncio
from pywiim import WiiMClient

async def adjust_eq():
    client = WiiMClient("192.168.1.100")
    
    try:
        # Get available EQ presets
        presets = await client.get_eq_presets()
        print(f"Available EQ presets: {presets}")
        
        # Set EQ preset
        await client.set_eq_preset("jazz")
        print("EQ set to jazz")
        
        # Get current EQ
        eq = await client.get_eq()
        print(f"Current EQ: {eq}")
        
        # Set custom EQ
        await client.set_eq_custom([6, 3, 1, 0, 0, 0, 0, 1, 2, 3])  # ten gains in dB
        print("Custom EQ applied")
        
        # Enable/disable EQ
        await client.set_eq_enabled(True)
        
    finally:
        await client.close()

asyncio.run(adjust_eq())
```

## Bluetooth

### Scan and Connect Bluetooth Devices

```python
import asyncio
from pywiim import WiiMClient

async def bluetooth_example():
    client = WiiMClient("192.168.1.100")
    
    try:
        # Start Bluetooth scan
        print("Scanning for Bluetooth devices...")
        await client.start_bluetooth_discovery(duration=5)
        
        # Wait for scan to complete
        while await client.is_bluetooth_scan_in_progress():
            await asyncio.sleep(0.5)
        
        # Get scan results
        result = await client.get_bluetooth_discovery_result()
        device_count = await client.get_bluetooth_device_count()
        
        print(f"Found {device_count} Bluetooth devices")
        
        # Get Bluetooth history (previously paired devices)
        history = await client.get_bluetooth_history()
        print(f"\nBluetooth history ({len(history)} devices):")
        for device in history[:5]:  # Show first 5
            print(f"  {device.get('name')} - {device.get('mac')}")
        
        # Connect to a device (if available)
        if history:
            mac = history[0].get('mac')
            print(f"\nConnecting to {mac}...")
            await client.connect_bluetooth_device(mac)
        
    finally:
        await client.close()

asyncio.run(bluetooth_example())
```

## Error Handling

### Comprehensive Error Handling

```python
import asyncio
from pywiim import (
    WiiMClient,
    WiiMError,
    WiiMRequestError,
    WiiMResponseError,
    WiiMTimeoutError,
    WiiMConnectionError,
)

async def robust_control():
    client = WiiMClient("192.168.1.100", timeout=3.0)
    
    try:
        # Try to get device info with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                info = await client.get_device_info_model()
                print(f"Connected to: {info.name}")
                break
            except WiiMTimeoutError:
                if attempt < max_retries - 1:
                    print(f"Timeout, retrying ({attempt + 1}/{max_retries})...")
                    await asyncio.sleep(1)
                else:
                    print("Connection timeout after retries")
                    return
            except WiiMConnectionError as e:
                print(f"Connection error: {e}")
                return
        
        # Try to control playback
        try:
            await client.set_volume(0.5)
            await client.play()
        except WiiMResponseError as e:
            print(f"Device returned error: {e}")
            print(f"Endpoint: {e.endpoint}")
            if e.device_info:
                print(f"Device: {e.device_info.get('device_model')}")
        except WiiMRequestError as e:
            print(f"Request failed: {e}")
            print(f"Attempts: {e.attempts}")
        
    except WiiMError as e:
        print(f"WiiM error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        await client.close()

asyncio.run(robust_control())
```

## Capability Detection

### Check and Use Capabilities

```python
import asyncio
from pywiim import WiiMClient

async def capability_aware():
    client = WiiMClient("192.168.1.100")
    
    try:
        # Capabilities are auto-detected on first use
        info = await client.get_device_info_model()
        
        # Check capabilities
        caps = client.capabilities
        print(f"Vendor: {caps.get('vendor')}")
        print(f"Device type: {'WiiM' if caps.get('is_wiim_device') else 'Legacy'}")
        
        # Use features based on capabilities
        if caps.get("supports_presets"):
            presets = await client.get_presets()
            print(f"Presets supported: {len(presets)} available")
        else:
            print("Presets not supported")
        
        if caps.get("supports_eq"):
            eq_presets = await client.get_eq_presets()
            print(f"EQ supported: {len(eq_presets)} presets")
        else:
            print("EQ not supported")
        
        if caps.get("supports_audio_output"):
            output_status = await client.get_audio_output_status()
            print(f"Audio output control supported")
        else:
            print("Audio output control not supported")
        
    finally:
        await client.close()

asyncio.run(capability_aware())
```

## State Monitoring

### Monitor Device State

```python
import asyncio
from pywiim import WiiMClient

async def monitor_state():
    client = WiiMClient("192.168.1.100")
    
    try:
        last_state = None
        last_track = None
        
        print("Monitoring device state (Ctrl+C to stop)...")
        
        while True:
            status = await client.get_player_status()
            
            # Check for state changes
            current_state = status.get('play_state')
            if current_state != last_state:
                print(f"State changed: {last_state} -> {current_state}")
                last_state = current_state
            
            # Check for track changes
            current_track = status.get('title')
            if current_track and current_track != last_track:
                print(f"Track changed: {current_track}")
                print(f"  Artist: {status.get('artist')}")
                print(f"  Album: {status.get('album')}")
                last_track = current_track
            
            # Show current status
            if current_state == "play":
                position = status.get('position', 0)
                duration = status.get('duration', 0)
                volume = status.get('volume', 0)
                print(f"Playing: {position}/{duration}s @ {volume:.0%} volume")
            
            await asyncio.sleep(2)  # Poll every 2 seconds
            
    except KeyboardInterrupt:
        print("\nMonitoring stopped")
    finally:
        await client.close()

asyncio.run(monitor_state())
```

## Advanced Examples

### Multiple Devices

```python
import asyncio
from pywiim import WiiMClient

async def control_multiple_devices():
    devices = [
        WiiMClient("192.168.1.100"),
        WiiMClient("192.168.1.101"),
        WiiMClient("192.168.1.102"),
    ]
    
    try:
        # Get info from all devices in parallel
        tasks = [d.get_device_info_model() for d in devices]
        infos = await asyncio.gather(*tasks)
        
        for device, info in zip(devices, infos):
            print(f"{info.name} ({device.host}): {info.model}")
        
        # Set volume on all devices
        tasks = [d.set_volume(0.5) for d in devices]
        await asyncio.gather(*tasks)
        print("Volume set to 50% on all devices")
        
    finally:
        for device in devices:
            await device.close()

asyncio.run(control_multiple_devices())
```

