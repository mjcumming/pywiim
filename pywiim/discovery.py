"""Device discovery for WiiM and LinkPlay devices.

This module provides SSDP/UPnP discovery to find WiiM and LinkPlay devices
on the local network (matches HA integration behavior).
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import ssl
from dataclasses import dataclass
from typing import Any

import aiohttp

try:
    from async_upnp_client.search import async_search
except ImportError:
    async_search = None  # type: ignore[assignment]

from .client import WiiMClient
from .exceptions import WiiMConnectionError

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "DiscoveredDevice",
    "discover_devices",
    "discover_via_ssdp",
    "is_known_linkplay",
    "is_linkplay_device",
    "validate_device",
    "validate_device_strict",
]

# Known LinkPlay/WiiM server patterns (devices we're CERTAIN are LinkPlay)
# These patterns are specific to LinkPlay devices that identify themselves in SSDP.
# If a device matches these patterns, we can skip the API probe and go directly
# to full validation - saves time and network calls.
#
# NOTE: Many LinkPlay devices (Arylic, Audio Pro) use GENERIC "Linux" headers
# and will NOT match these patterns. That's okay - they'll go through the API probe.
# Only add patterns here that are CONFIRMED to appear in real SSDP responses.
KNOWN_LINKPLAY_SERVER_PATTERNS = [
    # CONFIRMED patterns (from real device SSDP responses):
    "WiiM",  # WiiM devices: "Linux UPnP/1.0 WiiM/4.8.5"
    "Linkplay",  # Some devices include "Linkplay" in SERVER header
    "LinkPlay",  # Case variant
    # SPECULATIVE patterns (may work, needs confirmation from real devices):
    # Many of these devices use generic "Linux" headers, so they may not match.
    # If a device doesn't match, it just goes through the API probe (still works).
    "Arylic",  # Arylic devices - UNCONFIRMED if they expose this in SSDP
    "iEAST",  # iEAST/Muzo devices - UNCONFIRMED if they expose this in SSDP
    "Audio Pro",  # Audio Pro devices - likely use generic "Linux" headers
    "AudioPro",  # Audio Pro variant
    "Muzo",  # Muzo devices (LinkPlay OEM)
    # Add more as we discover them from real device SSDP responses
]

# Known non-LinkPlay server patterns (ONLY devices we're CERTAIN are not LinkPlay)
# These patterns are specific to non-LinkPlay devices that clearly identify themselves
# ⚠️ CONSERVATIVE: Only filter devices we're 100% certain are not LinkPlay.
# Audio Pro, Arylic, and other LinkPlay devices use generic "Linux" headers
# and will pass through this filter (which is correct - they need validation).
NON_LINKPLAY_SERVER_PATTERNS = [
    "Chromecast",  # Google Chromecast - definitely not LinkPlay
    "Denon-Heos",  # Denon Heos - definitely not LinkPlay
    "MINT-X",  # Sony devices - definitely not LinkPlay
    "KnOS",  # Kodi/OSMC - definitely not LinkPlay
    "Sonos",  # Sonos devices - definitely not LinkPlay
    "Samsung",  # Samsung TVs and devices - definitely not LinkPlay
    "SEC_HHP",  # Samsung Electronics pattern - definitely not LinkPlay
    "SmartThings",  # Samsung SmartThings - definitely not LinkPlay
    # Add more ONLY if we're 100% certain they're not LinkPlay-compatible
    # DO NOT add generic patterns like "Linux" - Audio Pro uses this!
]

# Known non-LinkPlay ST (service type) patterns (ONLY devices we're CERTAIN are not LinkPlay)
# These are UPnP device/service types that are definitely not LinkPlay-compatible
# ⚠️ CONSERVATIVE: Only filter devices we're 100% certain are not LinkPlay.
NON_LINKPLAY_ST_PATTERNS = [
    "urn:schemas-upnp-org:device:ZonePlayer",  # Sonos ZonePlayer - definitely not LinkPlay
    "urn:schemas-upnp-org:service:ZoneGroupTopology",  # Sonos service - definitely not LinkPlay
    "urn:schemas-upnp-org:service:GroupRenderingControl",  # Sonos service - definitely not LinkPlay
    "urn:roku-com:device",  # Roku devices - definitely not LinkPlay
    "urn:dial-multiscreen-org:device:dial",  # DIAL protocol (Chromecast, etc.) - definitely not LinkPlay
    "urn:samsung.com:device",  # Samsung devices - definitely not LinkPlay
    "urn:samsung.com:service",  # Samsung services - definitely not LinkPlay
    # Add more ONLY if we're 100% certain they're not LinkPlay-compatible
]


@dataclass
class DiscoveredDevice:
    """Represents a discovered WiiM/LinkPlay device."""

    ip: str
    name: str | None = None
    model: str | None = None
    firmware: str | None = None
    mac: str | None = None
    uuid: str | None = None
    port: int = 80
    protocol: str = "http"  # "http" or "https"
    vendor: str | None = None  # "wiim", "arylic", "audio_pro", etc.
    discovery_method: str = "unknown"  # "ssdp", "manual"
    validated: bool = False  # Whether device was validated via API
    ssdp_response: dict[str, Any] | None = None  # Store SSDP response for filtering

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "ip": self.ip,
            "name": self.name,
            "model": self.model,
            "firmware": self.firmware,
            "mac": self.mac,
            "uuid": self.uuid,
            "port": self.port,
            "protocol": self.protocol,
            "vendor": self.vendor,
            "discovery_method": self.discovery_method,
            "validated": self.validated,
        }

    def __str__(self) -> str:
        """String representation."""
        name = self.name or "Unknown"
        model = f" ({self.model})" if self.model else ""
        return f"{name}{model} @ {self.ip}"


async def discover_via_ssdp(
    timeout: int = 5,
    target: str | None = None,
) -> list[DiscoveredDevice]:
    """Discover devices via SSDP/UPnP.

    Args:
        timeout: Discovery timeout in seconds
        target: Optional SSDP search target (default: "upnp:rootdevice")

    Returns:
        List of discovered devices
    """
    if async_search is None:
        _LOGGER.warning(
            "async-upnp-client not available, SSDP discovery disabled. Install with: pip install async-upnp-client"
        )
        return []

    devices: list[DiscoveredDevice] = []
    seen_ips: set[str] = set()

    try:
        _LOGGER.info("Starting SSDP discovery (timeout=%ds)...", timeout)
        # Default to MediaRenderer target (matches long-standing LinkPlay discovery pattern).
        # A custom target can still be provided for troubleshooting.
        search_target = target or "urn:schemas-upnp-org:device:MediaRenderer:1"

        # New API requires async_callback instead of async generator
        async def process_response(response: dict[str, Any]) -> None:
            """Process a single SSDP response (matches HA integration pattern)."""
            try:
                _LOGGER.debug(
                    "SSDP response received, keys: %s",
                    list(response.keys()) if hasattr(response, "keys") else "no keys",
                )

                # Extract location URL (CaseInsensitiveDict handles case)
                # Try multiple key variations
                location = (
                    response.get("location", "")
                    or response.get("LOCATION", "")
                    or response.get("_location_original", "")
                )
                _LOGGER.debug("Extracted location: %s", location)

                if not location:
                    _LOGGER.debug(
                        "No location in SSDP response, skipping. Response keys: %s",
                        list(response.keys()) if hasattr(response, "keys") else "unknown",
                    )
                    return

                # Parse IP from location URL
                ip = _extract_ip_from_url(location)
                _LOGGER.debug("Extracted IP: %s from location: %s", ip, location)

                if not ip:
                    _LOGGER.debug("Could not extract IP from location: %s", location)
                    return

                if ip in seen_ips:
                    _LOGGER.debug("Already seen IP: %s, skipping", ip)
                    return

                _LOGGER.debug("Processing new device with IP: %s", ip)
                seen_ips.add(ip)

                # Extract port and protocol from UPnP description URL
                # NOTE: This port (typically 49152) is ONLY for UPnP description.xml, NOT for HTTP API
                # The HTTP API is always on port 80 (or 443 for HTTPS)
                upnp_port, protocol = _extract_port_and_protocol(location)

                # Extract device info from SSDP response
                usn = response.get("usn", "") or response.get("USN", "")
                name = None
                if usn:
                    name = usn.split("::")[0]
                    if name and name.startswith("uuid:"):
                        name = None

                # Extract UUID from USN if present (format: uuid:xxxx-xxxx-xxxx-xxxx::...)
                uuid = None
                if usn.startswith("uuid:"):
                    uuid_part = usn.split("::")[0]
                    if uuid_part.startswith("uuid:"):
                        uuid = uuid_part[5:]

                # Accept all SSDP responses - validation will filter LinkPlay devices
                # This matches HA integration behavior
                # IMPORTANT: Use port 80 for HTTP API (not the UPnP description port)
                # The UPnP port (49152) is only for description.xml, not for API calls
                api_port = 80  # HTTP API is always on port 80 (or 443 for HTTPS)
                device = DiscoveredDevice(
                    ip=ip,
                    name=name,
                    model=None,  # Will be filled during validation
                    uuid=uuid,
                    port=api_port,  # Use standard HTTP API port, not UPnP port
                    protocol=protocol,
                    discovery_method="ssdp",
                    ssdp_response=response,  # Store full SSDP response for filtering
                )

                devices.append(device)
                _LOGGER.debug(
                    "SSDP discovered device: %s @ %s (UPnP port: %d, API port: %d)",
                    device.name or "Unknown",
                    ip,
                    upnp_port,
                    api_port,
                )

            except Exception as e:
                _LOGGER.warning("Error processing SSDP response: %s", e, exc_info=True)

        # Use new callback-based API (matches HA integration)
        # Note: async_search expects CaseInsensitiveDict but we use dict[str, Any]
        # This is compatible at runtime, so we suppress the type check
        if async_search is None:
            raise RuntimeError("async_upnp_client.search.async_search is not available")
        # Type ignore needed: async_search expects CaseInsensitiveDict but dict[str, Any] is compatible
        await async_search(
            async_callback=process_response,  # type: ignore[arg-type]
            timeout=timeout,
            search_target=search_target,
        )

    except Exception as e:
        _LOGGER.warning("SSDP discovery failed: %s", e)

    _LOGGER.info("SSDP discovery found %d device(s)", len(devices))
    return devices


async def is_linkplay_device(
    host: str,
    port: int = 80,
    timeout: float = 3.0,
) -> bool:
    """Quick check if a device responds to LinkPlay API endpoints.

    Tries standard LinkPlay endpoints (getPlayerStatusEx, getStatusEx, getStatus).
    If endpoint probing is inconclusive, falls back to a lightweight WiiMClient
    status request. If either method succeeds, the device is confirmed as
    LinkPlay-compatible.

    This is the definitive test - Samsung TVs, Sonos, and other non-LinkPlay
    devices will NOT respond to /httpapi.asp?command=getStatusEx with valid JSON.

    Args:
        host: Device IP address
        port: API port hint from discovery (default 80). If probing this port fails,
            the probe will also try standard LinkPlay API ports.
        timeout: Request timeout in seconds

    Returns:
        True if device responds to LinkPlay endpoints with valid JSON, False otherwise
    """
    # Standard LinkPlay endpoints to try (in order of preference)
    # getPlayerStatusEx is widely supported across modern WiiM devices.
    endpoints = [
        "/httpapi.asp?command=getPlayerStatusEx",  # Modern/primary
        "/httpapi.asp?command=getStatusEx",  # Modern devices
        "/httpapi.asp?command=getStatus",  # Fallback/legacy
    ]

    # Create SSL context that accepts self-signed certs (WiiM uses these)
    # Use executor to avoid blocking event loop (Python 3.13 detects blocking calls)
    ssl_context = await asyncio.to_thread(ssl.create_default_context)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    connector = aiohttp.TCPConnector(ssl=ssl_context)
    client_timeout = aiohttp.ClientTimeout(total=timeout)

    # Probe order aligned with established LinkPlay behavior:
    #   1) HTTPS 443
    #   2) HTTPS 4443 (some models)
    #   3) HTTP 80 fallback
    # If discovery provides a port hint, try it first, then the standard order.
    probe_ports = [port]
    for standard_port in [443, 4443, 80]:
        if standard_port not in probe_ports:
            probe_ports.append(standard_port)

    try:
        async with aiohttp.ClientSession(connector=connector, timeout=client_timeout) as session:
            for probe_port in probe_ports:
                for endpoint in endpoints:
                    # Use likely protocol first for each port
                    protocols = ["https", "http"] if probe_port in (443, 4443, 8443) else ["http", "https"]
                    for protocol in protocols:
                        try:
                            url = f"{protocol}://{host}:{probe_port}{endpoint}"
                            async with session.get(url) as resp:
                                if resp.status == 200:
                                    try:
                                        data = await resp.json()
                                        # Valid LinkPlay response = non-empty dict
                                        if isinstance(data, dict) and len(data) > 0:
                                            _LOGGER.debug(
                                                "LinkPlay device confirmed at %s via %s (keys: %s)",
                                                host,
                                                endpoint,
                                                list(data.keys())[:5],  # Log first 5 keys
                                            )
                                            return True
                                    except (json.JSONDecodeError, aiohttp.ContentTypeError):
                                        # Not JSON = not LinkPlay
                                        _LOGGER.debug(
                                            "Device %s responded to %s but not with JSON",
                                            host,
                                            endpoint,
                                        )
                                        continue
                        except TimeoutError:
                            _LOGGER.debug(
                                "Timeout probing %s://%s:%d%s",
                                protocol,
                                host,
                                probe_port,
                                endpoint,
                            )
                            continue
                        except aiohttp.ClientError as e:
                            _LOGGER.debug(
                                "Connection error probing %s://%s:%d%s: %s",
                                protocol,
                                host,
                                probe_port,
                                endpoint,
                                e,
                            )
                            continue
                        except Exception as e:
                            _LOGGER.debug(
                                "Error probing %s://%s:%d%s: %s",
                                protocol,
                                host,
                                probe_port,
                                endpoint,
                                e,
                            )
                            continue
    except Exception as e:
        _LOGGER.debug("Failed to create session for probing %s: %s", host, e)

    # Fallback: use WiiMClient's own endpoint/protocol discovery and parser logic.
    # Some devices respond with payloads that are valid for the client path but
    # fail strict JSON checks in the lightweight probe.
    try:
        client = WiiMClient(host=host, timeout=max(timeout, 5.0))
        # Probe context: a failure here just means "not a LinkPlay device".
        # Keep capability-detection failures at debug (issue mjcumming/wiim#249).
        client._quiet_capabilities = True
        try:
            status = await client.get_player_status()
            if isinstance(status, dict) and len(status) > 0:
                _LOGGER.debug(
                    "LinkPlay device confirmed at %s via WiiMClient fallback (endpoint=%s)",
                    host,
                    client.base_url,
                )
                return True
        finally:
            await client.close()
    except Exception as e:
        _LOGGER.debug("WiiMClient fallback probe failed for %s: %s", host, e)

    _LOGGER.debug("Device %s does not respond to LinkPlay API endpoints", host)
    return False


async def validate_device(device: DiscoveredDevice) -> DiscoveredDevice:
    """Validate a discovered device by querying its API.

    Uses HTTP probe as the definitive check (like velleman linkplay library).
    This ensures non-LinkPlay devices (Samsung TV, Sonos, etc.) are filtered out
    regardless of their SSDP headers.

    Args:
        device: Device to validate

    Returns:
        Updated device with full information (validated=True if successful)
    """
    if device.validated:
        return device

    # HTTP probe is the definitive check - probe every device
    # This is fast and reliable - non-LinkPlay devices fail here immediately
    if not await is_linkplay_device(device.ip, device.port, timeout=3.0):
        _LOGGER.debug(
            "Skipping %s - does not respond to LinkPlay API (not a WiiM/LinkPlay device)",
            device.ip,
        )
        return device  # validated stays False

    _LOGGER.debug("Device %s confirmed as LinkPlay via HTTP probe, proceeding with full validation", device.ip)

    # Phase 2: Full validation - get device info and capabilities
    try:
        # Do not trust SSDP LOCATION protocol/port as API transport hints.
        # Let WiiMClient perform protocol/port discovery (443/4443/80, etc.).
        client = WiiMClient(
            device.ip,
            timeout=5.0,
        )
        # Discovery validation is soft-fail (see docstring): a capability-detection
        # failure here is benign, so keep it at debug (issue mjcumming/wiim#249).
        client._quiet_capabilities = True

        try:
            # Ensure capabilities are detected (triggers vendor detection)
            await client._detect_capabilities()

            # Get device info
            device_info = await client.get_device_info_model()
            await client.get_player_status()  # Refresh player status

            # Update device with full info
            device.name = device_info.name or device.name
            device.model = device_info.model or device.model
            device.firmware = device_info.firmware or device.firmware
            device.mac = device_info.mac or device.mac
            device.uuid = device_info.uuid or device.uuid

            # Update port to the actual API port (may differ from discovered UPnP port)
            device.port = client.port
            # Keep displayed protocol aligned with the validated transport endpoint.
            device.protocol = "https" if client.port in (443, 4443, 8443) else "http"

            # Detect vendor from capabilities (normalized)
            # Capabilities are now guaranteed to be detected
            from .capabilities import detect_vendor
            from .normalize import normalize_vendor

            if client.capabilities and client.capabilities.get("vendor"):
                vendor = client.capabilities.get("vendor")
                device.vendor = normalize_vendor(vendor)
            else:
                # Fallback: detect vendor from device info
                vendor = detect_vendor(device_info)
                device.vendor = normalize_vendor(vendor)

            device.validated = True

            await client.close()

        except Exception as e:
            await client.close()
            _LOGGER.debug("Full validation failed for %s: %s", device.ip, e)

    except Exception as e:
        _LOGGER.debug("Could not validate device %s: %s", device.ip, e)

    return device


async def validate_device_strict(device: DiscoveredDevice) -> DiscoveredDevice:
    """Validate a discovered device and raise if it is not usable.

    ``validate_device()`` is intentionally soft-fail for bulk discovery: it
    returns the input device with ``validated=False`` when the host does not
    pass the LinkPlay/WiiM probe. Use this helper for manual setup flows or
    other code paths where an unvalidated device is an error.

    Args:
        device: Device to validate.

    Returns:
        Updated device with full information.

    Raises:
        WiiMConnectionError: If the host cannot be validated as LinkPlay/WiiM.
    """
    validated_device = await validate_device(device)
    if not validated_device.validated:
        raise WiiMConnectionError(
            f"Device at {device.ip} did not validate as a LinkPlay/WiiM device",
            operation_context="device_validation",
        )
    return validated_device


async def discover_devices(
    methods: list[str] | None = None,
    validate: bool = True,
    ssdp_timeout: int = 5,
) -> list[DiscoveredDevice]:
    """Discover WiiM/LinkPlay devices via SSDP/UPnP (like HA integration).

    Args:
        methods: Discovery methods to use (default: ["ssdp"])
            Only "ssdp" is supported (network scanning removed to match HA integration)
        validate: Whether to validate discovered devices via API
        ssdp_timeout: SSDP discovery timeout in seconds

    Returns:
        List of discovered and validated devices
    """
    if methods is None:
        methods = ["ssdp"]

    all_devices: list[DiscoveredDevice] = []
    seen_ips: set[str] = set()

    # SSDP discovery (only method, like HA integration)
    if "ssdp" in methods:
        _LOGGER.info("Discovering devices via SSDP...")
        ssdp_devices = await discover_via_ssdp(timeout=ssdp_timeout)

        # Collect discovered devices.
        # HTTP probe remains the definitive filter for ambiguous devices.
        for device in ssdp_devices:
            if device.ip in seen_ips:
                continue
            # Skip obvious non-LinkPlay devices before HTTP probe when validation is enabled.
            # This avoids unnecessary network noise for devices such as Sonos/Chromecast.
            if validate and device.ssdp_response and is_likely_non_linkplay(device.ssdp_response):
                _LOGGER.debug(
                    "Skipping %s - SSDP headers indicate non-LinkPlay device",
                    device.ip,
                )
                continue
            all_devices.append(device)
            seen_ips.add(device.ip)

    # Validate devices if requested
    # HTTP probe is the definitive filter - every device is probed to check if it
    # responds to LinkPlay API endpoints. This ensures non-LinkPlay devices
    # (Samsung TV, Sonos, etc.) are filtered out regardless of SSDP headers.
    if validate:
        _LOGGER.info(
            "Validating %d discovered device(s) via HTTP probe to confirm LinkPlay/WiiM compatibility...",
            len(all_devices),
        )
        validation_tasks = [validate_device(device) for device in all_devices]
        validated_devices = await asyncio.gather(*validation_tasks)

        # Filter to only include devices that successfully validated
        # (devices that respond to LinkPlay API - definitive check)
        all_devices = [device for device in validated_devices if device.validated]

        if len(validated_devices) != len(all_devices):
            _LOGGER.info(
                "Filtered out %d non-LinkPlay device(s) (did not respond to LinkPlay API)",
                len(validated_devices) - len(all_devices),
            )

    # Remove duplicates (by IP)
    unique_devices: list[DiscoveredDevice] = []
    seen_ips_again: set[str] = set()
    for device in all_devices:
        if device.ip not in seen_ips_again:
            unique_devices.append(device)
            seen_ips_again.add(device.ip)

    _LOGGER.info("Discovery complete: found %d unique device(s)", len(unique_devices))
    return unique_devices


def _extract_ip_from_url(url: str) -> str | None:
    """Extract IP address from URL."""
    try:
        # Remove protocol
        if "://" in url:
            url = url.split("://", 1)[1]

        # Remove path
        if "/" in url:
            url = url.split("/", 1)[0]

        # Remove port
        if ":" in url:
            url = url.split(":")[0]

        # Validate IP
        ipaddress.ip_address(url)
        return url
    except Exception:
        return None


def _extract_port_and_protocol(url: str) -> tuple[int, str]:
    """Extract port and protocol from URL."""
    protocol = "https" if url.startswith("https://") else "http"
    default_port = 443 if protocol == "https" else 80

    try:
        # Remove protocol
        if "://" in url:
            url = url.split("://", 1)[1]

        # Extract port
        if ":" in url:
            port_str = url.split(":")[1].split("/")[0]
            port = int(port_str)
            return port, protocol
    except Exception:
        pass

    return default_port, protocol


def is_likely_non_linkplay(ssdp_response: dict[str, Any]) -> bool:
    """Quick check if device is likely not a LinkPlay device based on SSDP headers.

    ⚠️ CONSERVATIVE: Only filters devices we're 100% certain are not LinkPlay.
    Audio Pro, Arylic, and other LinkPlay devices use generic "Linux" headers
    and will pass through this filter (which is correct - they need validation).

    Checks both SERVER header patterns and ST (service type) patterns for more
    reliable filtering. For example, Sonos devices can be identified by both
    their SERVER header containing "Sonos" and their ST header containing
    "urn:schemas-upnp-org:device:ZonePlayer".

    Args:
        ssdp_response: SSDP response dictionary containing headers

    Returns:
        True if device is CERTAINLY not a LinkPlay device, False otherwise
    """
    # Check ST (service type) header first - more reliable for some devices
    st = ssdp_response.get("st", "") or ssdp_response.get("ST", "")
    if st:
        st_lower = st.lower()
        if any(pattern.lower() in st_lower for pattern in NON_LINKPLAY_ST_PATTERNS):
            return True

    # Check SERVER header
    server = ssdp_response.get("SERVER", "") or ssdp_response.get("server", "")
    if server:
        server_upper = server.upper()
        if any(pattern.upper() in server_upper for pattern in NON_LINKPLAY_SERVER_PATTERNS):
            return True

    # No matching patterns - can't filter, must validate
    return False


def is_known_linkplay(ssdp_response: dict[str, Any]) -> bool:
    """Check if device is DEFINITELY a LinkPlay device based on SSDP headers.

    This is the positive counterpart to is_likely_non_linkplay(). If this returns
    True, we can skip the API probe and go directly to full validation - the device
    has identified itself as LinkPlay/WiiM in its SSDP response.

    Args:
        ssdp_response: SSDP response dictionary containing headers

    Returns:
        True if device is DEFINITELY a LinkPlay device (skip API probe)
        False if we need to probe to determine
    """
    if not ssdp_response:
        return False

    # Check SERVER header for known LinkPlay patterns
    server = ssdp_response.get("SERVER", "") or ssdp_response.get("server", "")
    if server:
        server_upper = server.upper()
        for pattern in KNOWN_LINKPLAY_SERVER_PATTERNS:
            if pattern.upper() in server_upper:
                _LOGGER.debug(
                    "Device identified as LinkPlay via SSDP SERVER header: %s (matched: %s)",
                    server,
                    pattern,
                )
                return True

    return False
