# Protocol Detection Strategy

## Problem Statement

The library needs to communicate with WiiM and LinkPlay devices that may support different protocols (HTTP/HTTPS) and ports. However, the current implementation has several flaws:

1. **Ignores user intent**: Even if user specifies `port=443`, it probes all ports
2. **Reprobes constantly**: Every connection loss triggers a full protocol probe
3. **Wastes time**: Tries 5+ port/protocol combinations on every failure
4. **Spams logs**: "Connection lost" warnings on every transient network issue

## Key Insight

**A device's protocol and port never change during normal operation.** 

Connection failures are almost always transient:
- Temporary network blip → retry same endpoint
- Device temporarily offline → retry same endpoint  
- Device rebooted → comes back on same protocol/port

The protocol/port only changes when:
- Firmware update (rare, user can manually reprobe)
- Device factory reset (rare, user can manually reprobe)
- User manually changed device config (rare, user can manually reprobe)

## Design Principles

### 1. Respect User Intent

If the user specifies a port or protocol, **use only what they specified**:

```python
# User specified both - use exactly that, never probe alternatives
client = WiiMClient("192.168.1.115", port=443, protocol="https")

# User specified port - try both protocols on THAT PORT ONLY
client = WiiMClient("192.168.1.115", port=80)

# User specified nothing - probe standard combinations
client = WiiMClient("192.168.1.115")
```

### 2. Never Reprobe Automatically

Once a working endpoint is discovered, **cache it permanently**:

- ✅ Cache is never cleared automatically
- ✅ Connection failures just retry, don't reprobe
- ✅ Manual `reprobe()` method for firmware updates
- ❌ Never clear cache on connection errors

### 3. Connection Failures Are Transient

When a request fails:

- ✅ Re-raise the exception for caller to handle
- ✅ Let the caller decide retry strategy
- ❌ Don't clear the endpoint cache
- ❌ Don't automatically probe alternatives

### 4. Manual Control When Needed

Provide explicit control for rare cases:

```python
# After firmware update, manually reprobe
await client.reprobe()

# Or create new client with fresh probe
client = WiiMClient("192.168.1.115")
```

## Implementation Design

### Initialization

```python
class BaseWiiMClient:
    def __init__(
        self,
        host: str,
        port: int | None = None,
        protocol: str | None = None,  # NEW: Allow explicit protocol
        timeout: float = DEFAULT_TIMEOUT,
        ssl_context: ssl.SSLContext | None = None,
        session: ClientSession | None = None,
        capabilities: dict[str, Any] | None = None,
    ):
        self._host = host
        self._user_port = port  # User-specified port (None = probe)
        self._user_protocol = protocol  # User-specified protocol (None = probe)
        self._discovered_endpoint = None  # Cached: "https://192.168.1.115:443"
        self._endpoint_tested = False  # Track if we've tested user-specified endpoint
```

### Request Flow

```python
async def _request(self, endpoint: str, **kwargs) -> Any:
    """Make HTTP request with permanent endpoint caching."""
    
    # If we have a cached endpoint, use it FOREVER
    if self._discovered_endpoint:
        url = self._discovered_endpoint + endpoint
        try:
            return await self._make_http_request(url, **kwargs)
        except (aiohttp.ClientConnectorError, 
                aiohttp.ServerDisconnectedError,
                asyncio.TimeoutError) as e:
            # Transient failure - re-raise for caller to handle
            # DO NOT clear cache, DO NOT reprobe
            _LOGGER.debug(
                "Request failed (transient): %s - %s",
                url, e
            )
            raise
    
    # No cached endpoint - need to discover (one time only)
    await self._probe_and_cache_endpoint()
    
    # Now retry with discovered endpoint
    return await self._request(endpoint, **kwargs)
```

### Protocol Probing (One Time Only)

```python
async def _probe_and_cache_endpoint(self) -> None:
    """Discover working protocol/port. Cache result permanently."""
    
    if self._discovered_endpoint:
        return  # Already cached
    
    # Case 1: User specified both protocol and port
    if self._user_protocol and self._user_port:
        url = f"{self._user_protocol}://{self._host}:{self._user_port}"
        _LOGGER.info("Using user-specified endpoint: %s", url)
        
        if await self._test_endpoint(url, API_ENDPOINT_STATUS):
            self._discovered_endpoint = url
            self._endpoint_tested = True
            return
        
        raise WiiMConnectionError(
            f"User-specified endpoint {url} not reachable. "
            f"Check device is online and protocol/port are correct."
        )
    
    # Case 2: User specified port only (try both protocols)
    if self._user_port:
        _LOGGER.info(
            "Probing protocols for user-specified port %d",
            self._user_port
        )
        
        # Try HTTPS first (more secure, common on WiiM devices)
        for protocol in ["https", "http"]:
            url = f"{protocol}://{self._host}:{self._user_port}"
            if await self._test_endpoint(url, API_ENDPOINT_STATUS):
                self._discovered_endpoint = url
                self._endpoint_tested = True
                _LOGGER.info("Discovered working endpoint: %s", url)
                return
        
        raise WiiMConnectionError(
            f"Port {self._user_port} not reachable on HTTP or HTTPS. "
            f"Check device is online and port is correct."
        )
    
    # Case 3: User specified nothing (probe standard combinations)
    _LOGGER.info("Probing standard protocol/port combinations for %s", self._host)
    
    # Try common combinations based on device capabilities
    protocols = self._build_probe_list()
    
    for protocol, port in protocols:
        url = f"{protocol}://{self._host}:{port}"
        if await self._test_endpoint(url, API_ENDPOINT_STATUS):
            self._discovered_endpoint = url
            self._endpoint_tested = True
            _LOGGER.info(
                "Discovered working endpoint: %s (cached permanently)",
                url
            )
            return
    
    raise WiiMConnectionError(
        f"No working protocol/port found for {self._host}. "
        f"Tried: {', '.join(f'{p}:{port}' for p, port in protocols)}"
    )

def _build_probe_list(self) -> list[tuple[str, int]]:
    """Build list of protocol/port combinations to probe."""
    
    # Use preferred ports from capabilities if specified
    preferred_ports = self._capabilities.get("preferred_ports", [])
    
    if preferred_ports:
        # Audio Pro MkII: Use preferred ports
        return [("https", port) for port in preferred_ports]
    
    # When the vendor is already known (client constructed with cached
    # capabilities), honor the profile's protocol_priority so the *probe itself*
    # picks the right transport — HTTP-first for Arylic, HTTPS-first for WiiM.
    https = [("https", 443), ("https", 4443), ("https", 8443)]
    http = [("http", 80), ("http", 8080)]
    priority = self._capabilities.get("protocol_priority") or []
    if priority and priority[0] == "http":
        return http + https     # Arylic / generic — HTTP first, HTTPS fallback

    # Default (vendor unknown, or HTTPS-first profile): HTTPS first, HTTP fallback.
    return https + http
```

### 5. Vendor-Aware Protocol Correction (post-detection)

The initial probe is **HTTPS-first** because WiiM hardware only listens on HTTPS:443
(plain HTTP:80 is refused). The device vendor, however, is not known until **after** the
first request — the model string comes from `getStatusEx`, which itself needs a working
endpoint. So the very first probe cannot be vendor-aware.

Some LinkPlay devices (Arylic / Up2Stream / generic) answer on HTTPS:443 **and** HTTP:80,
but their embedded TLS handshake is slow (~250–470 ms vs ~25–85 ms over plain HTTP). For
those, HTTPS would otherwise win the probe and be cached permanently, making every poll
sluggish (see [mjcumming/wiim#248](https://github.com/mjcumming/wiim/issues/248)).

The **device profile** (`profiles.py`) is the single source of truth for protocol order
(`connection.protocol_priority`): WiiM and Audio Pro MkII/W-gen are HTTPS-first, Arylic /
generic / Audio Pro Original are HTTP-first. There are two cooperating mechanisms:

1. **Probe ordering (`_build_standard_probe_list`)** — when the client already has
   capabilities (the usual case for the coordinator/poll client, which is constructed with
   cached capabilities and *skips* `_detect_capabilities`), the probe list is ordered by
   `protocol_priority`, so the very first probe lands on — and caches/persists — the right
   transport. This is what makes the *persisted* endpoint correct.

2. **Post-detection correction (`_apply_protocol_preference`)** — for a cold client with no
   capabilities (the first-ever discovery probe), the probe is HTTPS-first; once
   `_detect_capabilities` populates the vendor, this performs a one-time **HTTPS→HTTP
   downgrade**, but only when the profile prefers HTTP **and** a probe of plain HTTP:80
   returns a valid body.

Both are conservative — they never upgrade HTTP→HTTPS and never select an endpoint without a
verified response. When a working endpoint is cached, `self.port` is updated to match it so
discovery/integration code that reads `client.port` persists the correct protocol. Net result:

- **WiiM** (HTTPS-only) always stays on HTTPS.
- **HTTP-only Arylic** (e.g. `UP2STREAM_AMP_V4`) caches HTTP directly — snappy and persisted.
- **HTTPS-only Arylic** (e.g. `ARYLIC_H50`, where HTTP:80 is refused) probes HTTP first, falls
  through to its working HTTPS endpoint, and keeps it.

> **Integration note:** the corrected endpoint only persists if the poll/coordinator client is
> constructed **with the device capabilities** (so `protocol_priority` is known at probe time)
> and is **not** pinned to a previously-cached HTTPS endpoint/port. A client given an explicit
> protocol/port is treated as user intent and is never re-probed.

```python

async def _test_endpoint(self, base_url: str, test_path: str) -> bool:
    """Test if endpoint is reachable."""
    try:
        url = base_url + test_path
        
        # Configure SSL for HTTPS
        kwargs = {}
        if base_url.startswith("https://"):
            kwargs["ssl"] = await self._get_ssl_context()
        
        # Use short timeout for fast failure detection
        timeout = aiohttp.ClientTimeout(connect=0.5, total=2.0)
        kwargs["timeout"] = timeout
        
        if self._session is None:
            raise RuntimeError("Session not started")
        
        async with asyncio.timeout(2.0):
            resp = await self._session.request("GET", url, **kwargs)
            async with resp:
                resp.raise_for_status()
                text = await resp.text()
                
                # Valid response (JSON or "OK")
                if text and (text.strip() == "OK" or text.strip().startswith("{")):
                    return True
        
        return False
        
    except Exception as e:
        _LOGGER.debug("Endpoint test failed: %s - %s", base_url, e)
        return False
```

### 6. Quiet Probing During Discovery

Home Assistant's SSDP matcher for the integration is deliberately broad
(`urn:schemas-upnp-org:device:MediaRenderer:1`) so that all LinkPlay OEMs
(WiiM, Arylic, Audio Pro, …) are auto-discovered — those OEMs do **not** reliably
advertise a `WiiM`/`LinkPlay` UPnP `manufacturer`, so a narrower match would
silently miss them. The cost of a broad match is that every DLNA renderer on the
LAN (AV receivers, TVs) is also handed to the config flow and probed.

That probe (`discovery.is_linkplay_device` / `discovery.validate_device`) is a
**soft-fail** check: a device failing to answer the LinkPlay HTTP API simply
isn't one. Such failures must stay at `debug`. Probe clients therefore set
`client._quiet_capabilities = True`, which downgrades the otherwise-`warning`
"Failed to detect capabilities for …" message (a *recoverable* path that falls
back to static detection) to `debug`. Configured-device setup leaves the flag
`False`, so a real capability-detection failure there still warns. See
[mjcumming/wiim#249](https://github.com/mjcumming/wiim/issues/249).

### Manual Reprobe

```python
async def reprobe(self) -> None:
    """Manually clear cache and reprobe protocol/port.
    
    Call this after:
    - Firmware updates
    - Device factory reset
    - Manual device configuration changes
    
    Raises:
        WiiMConnectionError: If no working endpoint found after reprobe
    """
    _LOGGER.info("Manual reprobe requested for %s", self._host)
    self._discovered_endpoint = None
    self._endpoint_tested = False
    
    # Reprobe (will cache new endpoint)
    await self._probe_and_cache_endpoint()
    
    _LOGGER.info("Reprobe complete: %s", self._discovered_endpoint)
```

## API Changes

### New Constructor Parameter

```python
client = WiiMClient(
    "192.168.1.115",
    port=443,           # Optional: specify port
    protocol="https",   # NEW: Optional: specify protocol ("http" or "https")
    timeout=5.0
)
```

### New Method

```python
await client.reprobe()  # Manually clear cache and reprobe
```

### Property Access

```python
# Read-only properties
client.discovered_endpoint  # "https://192.168.1.115:443"
client.is_https  # True if using HTTPS
client.discovered_port  # 443
```

## Benefits

### 1. No More Spam

Before (every connection loss):
```
[WARNING] Connection lost to 192.168.1.115, will retry with protocol probe
[INFO] Probing protocols for 192.168.1.115
[DEBUG] Trying https://192.168.1.115:443...
[DEBUG] Trying https://192.168.1.115:4443...
[DEBUG] Trying http://192.168.1.115:80... SUCCESS
```

After (probe once, use forever):
```
[INFO] Probing protocols for 192.168.1.115
[INFO] Discovered working endpoint: http://192.168.1.115:80 (cached permanently)
```

### 2. Faster Operation

- **Before**: 5+ connection attempts on every failure
- **After**: 1 retry with cached endpoint

### 3. Predictable Behavior

- **Before**: Behavior changes after every connection loss
- **After**: Once working, behavior never changes

### 4. User Control

- **Before**: No way to control probing behavior
- **After**: Explicit port/protocol control, manual reprobe when needed

## Migration Guide

### For Applications

No breaking changes! But can optimize:

**Before:**
```python
# Would probe on every connection loss
client = WiiMClient("192.168.1.115")
```

**After (same behavior, but better):**
```python
# Probes once, caches forever
client = WiiMClient("192.168.1.115")

# Or if you know the details:
client = WiiMClient("192.168.1.115", port=80, protocol="http")
```

**New capability:**
```python
# After firmware update
await client.reprobe()
```

### For Home Assistant Integration

Cache discovered endpoint in config entry data:

```python
# On initial setup or reprobe
client = WiiMClient(host)
await client.start()
endpoint = client.discovered_endpoint

# Store in config entry
hass.config_entries.async_update_entry(
    entry,
    data={**entry.data, "endpoint": endpoint}
)

# On next startup, pass cached endpoint
cached_endpoint = entry.data.get("endpoint")
if cached_endpoint:
    # Parse cached endpoint
    from urllib.parse import urlparse
    parsed = urlparse(cached_endpoint)
    client = WiiMClient(
        host,
        port=parsed.port,
        protocol=parsed.scheme
    )
else:
    # First time - will probe
    client = WiiMClient(host)
```

## Testing Strategy

### Unit Tests

```python
async def test_user_specified_protocol_port():
    """Test that user-specified protocol/port is respected."""
    client = WiiMClient("192.168.1.100", port=443, protocol="https")
    
    # Should only try user-specified endpoint
    # Should NOT probe alternatives
    
async def test_cache_persistence():
    """Test that endpoint cache is never cleared automatically."""
    client = WiiMClient("192.168.1.100")
    await client.start()
    
    # Get cached endpoint
    endpoint1 = client.discovered_endpoint
    
    # Simulate connection failure
    with pytest.raises(WiiMConnectionError):
        await client._request("/invalid")
    
    # Cache should still be set
    assert client.discovered_endpoint == endpoint1
    
async def test_manual_reprobe():
    """Test manual reprobe clears cache and reprobes."""
    client = WiiMClient("192.168.1.100")
    await client.start()
    
    endpoint1 = client.discovered_endpoint
    
    # Reprobe
    await client.reprobe()
    
    # Should have re-tested (may be same endpoint)
    assert client.discovered_endpoint is not None
```

### Integration Tests

Test with real devices to ensure:
1. Probe happens only once per client lifetime
2. Connection failures don't trigger reprobe
3. Manual reprobe works correctly

## Rollout Plan

### Phase 1: Implementation (This PR)
- [ ] Add `protocol` parameter to constructor
- [ ] Implement permanent endpoint caching
- [ ] Remove automatic reprobe on connection failure
- [ ] Add `reprobe()` method
- [ ] Add `discovered_endpoint` property
- [ ] Update unit tests

### Phase 2: Testing
- [ ] Test with real WiiM devices
- [ ] Test with Audio Pro devices
- [ ] Test connection failure scenarios
- [ ] Verify no reprobe spam in logs

### Phase 3: Documentation
- [ ] Update README with protocol parameter
- [ ] Update API documentation
- [ ] Add migration guide
- [ ] Document reprobe() use cases

## Open Questions

### Q: What if device IP changes?

**A:** User creates new client instance with new IP. The IP is part of initialization, not part of protocol detection.

### Q: What about firmware updates that change supported protocols?

**A:** User calls `client.reprobe()` after firmware update. This is a rare event.

### Q: Should we persist cache across application restarts?

**A:** Optional optimization for Home Assistant integration. Store in config entry data. Not required for library functionality.

## Summary

This design makes protocol detection:
- ✅ **Predictable**: Probe once, cache forever
- ✅ **Respectful**: Honor user-specified settings
- ✅ **Efficient**: No repeated probing
- ✅ **Controllable**: Manual reprobe when needed
- ✅ **Quiet**: No log spam on transient failures

The key insight: **Device protocol/port is static configuration, not dynamic state.**

