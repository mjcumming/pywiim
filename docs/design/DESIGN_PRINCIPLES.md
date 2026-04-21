# Design Principles and Goals

## Primary Goals

### 1. Separation of Concerns
- **Goal**: Clean separation between device communication and framework-specific code
- **Rationale**: Enables library reuse across different frameworks and applications
- **Success Metric**: Library has zero Home Assistant dependencies
- **Implementation**: Extract all device communication logic, keep framework code in integration

### 2. Device Compatibility
- **Goal**: Support all WiiM and LinkPlay devices (including Arylic, Audio Pro, etc.) with graceful degradation
- **Rationale**: Device variations and vendor differences require capability detection, not hardcoded assumptions
- **Success Metric**: Library works with all known device types, vendors, and firmware versions
- **Implementation**: Vendor-aware capability detection with multi-layered device registry and strategy pattern
- **Integrations**: Optional HTTP features are gated only on **`WiiMClient.capabilities`** (and `Player` properties that mirror it), not on model name alone — see **[ADR 018](adr/018-capabilities-dict-source-of-truth.md)**

### 3. Maintainability
- **Goal**: Code is easy to understand, modify, and extend
- **Rationale**: Long-term maintenance requires clear structure and documentation
- **Success Metric**: Code follows established patterns, well-documented, testable
- **Implementation**: Modular design, comprehensive documentation, high test coverage

### 4. Type Safety
- **Goal**: Catch errors at development time, not runtime
- **Rationale**: Type hints and Pydantic models prevent common errors
- **Success Metric**: All public APIs typed, mypy passes, Pydantic validation throughout
- **Implementation**: Type hints everywhere, Pydantic models for all data structures

### 5. Reliability
- **Goal**: Library handles errors gracefully and provides useful feedback
- **Rationale**: Network devices are unreliable; library must be resilient
- **Success Metric**: No crashes on device variations, comprehensive error context
- **Implementation**: Retry logic, graceful fallbacks, comprehensive error handling

## Core Design Principles

### 1. Fail Gracefully
- **Principle**: Never crash on device variations or firmware differences
- **Implementation**: Capability detection before API calls, graceful fallbacks, comprehensive error handling
- **Example**: If getMetaInfo fails, mark as unsupported and continue without metadata

### 2. Log Comprehensively
- **Principle**: Every log message includes device context for troubleshooting
- **Implementation**: Structured logging with device info (host, firmware, model) in every message
- **Example**: "API call: endpoint=getStatusEx, device=192.168.1.100, firmware=5.0.1, attempt=1/3"

### 3. Follow Python Best Practices
- **Principle**: Use standard Python patterns and idioms
- **Implementation**: Async/await throughout, context managers, type hints, Pydantic models
- **Example**: Use `asyncio.timeout` instead of deprecated `async_timeout`

### 4. Document Decisions
- **Principle**: Document why decisions were made, not just what was implemented
- **Implementation**: Architecture docs, design decisions, trade-offs documented. For significant committed decisions (user-facing stability, API contracts), use [Architecture Decision Records (ADRs)](adr/README.md) (indexed there; see ADR 001–017).
- **Example**: Document why capability detection is multi-layered vs single check

### 5. Framework Agnostic with HA Integration Support
- **Principle**: Library works standalone but supports HA integration patterns
- **Implementation**: Accept optional aiohttp session (HA can pass `async_get_clientsession(hass)`)
- **Example**: HTTP client accepts optional session for connection pooling, UPnP uses async-upnp-client (same as HA)

### 6. Learn from Past Challenges
- **Principle**: Design to avoid known issues from integration changelog
- **Implementation**: Address state synchronization, Audio Pro challenges, metadata preservation, UPnP health, endpoint variations proactively
- **Example**: State synchronization with freshness windows, endpoint abstraction with fallback chains, metadata preservation logic

### 7. Reference Existing Implementations
- **Principle**: Research existing codebases before creating new patterns
- **Implementation**: Check HA integration codebase and other LinkPlay libraries on GitHub before implementing new functionality
- **Rationale**: Avoid reinventing patterns, learn from proven solutions, maintain consistency
- **Process**: See [REFERENCE_IMPLEMENTATIONS.md](REFERENCE_IMPLEMENTATIONS.md) for detailed research process
- **Example**: Before creating a helper function, check if HA integration has a similar pattern or if other libraries use a different approach

### 8. Follow Home Assistant Patterns (for Integration)
- **Principle**: Integration code follows HA patterns for consistency
- **Implementation**: Coordinator pattern, config entry pattern, entity pattern
- **Note**: This applies to integration code, not library code

## API Design: Client Methods vs Helper Functions

### Problem: Redundant Helper Functions

We created `build_group_state()` as a standalone helper function that was just a thin wrapper around `master_client.get_group_state()`. This violated our design principles and created unnecessary API surface.

### Design Rule: When to Use Client Methods vs Helper Functions

#### ✅ Use Client Methods When:

1. **Operation is specific to a single client instance**
   - Example: `client.get_group_state()` - operates on that specific client
   - Example: `client.get_player_status()` - queries that specific device
   - Example: `client.set_volume()` - controls that specific device

2. **Operation naturally belongs to the client**
   - The client has the context and state needed
   - The operation is part of the client's core responsibilities

3. **You already have a client instance**
   - No need to create a helper when you can call the method directly

#### ✅ Use Standalone Helper Functions When:

1. **Operation works across multiple clients**
   - Example: `build_group_state_from_players()` - aggregates state from multiple Player instances

2. **Operation works with different object types**
   - Example: `build_group_state_from_players()` - works with `Player` instances, not `WiiMClient`
   - Example: `normalize_device_info()` - works with `DeviceInfo` models

3. **Operation discovers or creates clients**
   - Example: `discover_devices()` - discovers devices and creates clients
   - Note: Don't create helpers just to get a list and create clients - users can do that themselves

4. **Operation doesn't naturally belong to a single client**
   - Example: `detect_role()` - works with status/models, not a specific client
   - Example: `normalize_device_info()` - transforms data, doesn't need a client

### The `build_group_state()` Mistake

**What we did wrong:**
```python
# BAD: Redundant helper function
async def build_group_state(master_client, ...):
    return await master_client.get_group_state(...)  # Just a wrapper!
```

**Why it's wrong:**
- It's just a thin wrapper around a client method
- If you have `master_client`, just call `master_client.get_group_state()` directly
- Adds no value, just adds API surface area
- Violates "don't wrap what doesn't need wrapping"

**What we should have done:**
- If you have a client: `await master_client.get_group_state(...)`
- If you have Players: `await build_group_state_from_players(...)`
- If you need slave clients: `slave_ips = await master.get_slaves()` then create clients yourself

### Design Checklist

Before creating a helper function, ask:

1. **Does it work across multiple clients/objects?** → Helper function ✅
2. **Does it work with different object types?** → Helper function ✅
3. **Does it discover/create clients?** → Helper function ✅
4. **Is it just a wrapper around a client method?** → ❌ Don't create it, use the method directly
5. **Does it add unique value beyond the client method?** → If no, don't create it

### Examples

#### ✅ Good Helper Functions

```python
# Works across multiple clients - discovers and creates them
async def discover_group_devices(master_client):
    # Discovers slaves, creates clients - can't be a client method
    ...

# Works with different object types (Player, not Client)
async def build_group_state_from_players(master_player, slave_players):
    # Uses Player instances with cached state - different from client method
    ...

# Works with models, not clients
def normalize_device_info(device_info: DeviceInfo):
    # Transforms data - doesn't need a client
    ...
```

#### ❌ Bad Helper Functions (Don't Create These)

```python
# Just a wrapper - use client method directly
async def build_group_state(master_client, ...):
    return await master_client.get_group_state(...)  # Redundant!

# Just a wrapper - use client method directly  
async def get_status(client):
    return await client.get_player_status()  # Redundant!
```

### Key Principle

**"If you have a client instance, use the client method. Only create helpers when you need to work across clients, with different types, or discover/create clients."**

### Lessons Learned

1. **Don't create helpers "just because"** - They should add unique value
2. **Client methods are the primary API** - Helpers are for special cases
3. **Question redundancy** - If it's just a wrapper, don't create it
4. **Design before coding** - Ask "does this need to be a helper?" before creating it
5. **Reference existing implementations** - Check HA integration and other LinkPlay libraries before creating new patterns

### Updated Design Process

When adding new functionality:

1. **First**: Research existing implementations
   - Check our HA integration codebase (`wiim-source/`) for how we handle this
   - Search GitHub for other LinkPlay/WiiM Python libraries
   - Understand established patterns before creating new ones
   - See [REFERENCE_IMPLEMENTATIONS.md](REFERENCE_IMPLEMENTATIONS.md) for detailed process
2. **Second**: Consider if it's a client method (most operations are)
3. **Third**: Only create a helper if it meets the criteria above
4. **Fourth**: Document why it's a helper, not a method (and reference existing implementations)
5. **Fifth**: Review for redundancy before committing

## Success Metrics

### Code Quality Metrics
- **Test Coverage**: 90%+ (measured by pytest-cov)
- **Type Coverage**: 100% of public APIs (measured by mypy)
- **Linting**: Zero errors (measured by Ruff)
- **File Size**: No files > 600 LOC, most < 400 LOC

### Functionality Metrics
- **Device Support**: All known device types work
- **API Coverage**: All documented endpoints implemented
- **Error Handling**: All error paths tested and documented
- **Performance**: Requests complete within timeout limits

### Documentation Metrics
- **API Documentation**: All public APIs documented
- **Usage Examples**: README includes working examples
- **Architecture Docs**: System design documented
- **Device Registry**: All known quirks documented

## Trade-offs

### Trade-off 1: Protocol Detection vs User Control
- **Decision**: Probe protocol/port once, cache permanently. Respect user-specified settings.
- **Rationale**: Device protocol/port never changes during normal operation. Connection failures are transient.
- **Impact**: 
  - Fast operation after initial probe (no reprobe on connection failures)
  - Users can specify exact protocol/port to skip probing entirely
  - Manual `reprobe()` method for rare cases (firmware updates)
- **Details**: See [PROTOCOL_DETECTION.md](PROTOCOL_DETECTION.md)

### Trade-off 2: Capability Detection vs Performance
- **Decision**: Probe capabilities on first connection, cache results
- **Rationale**: Device variations require detection, but we don't want to probe every time
- **Impact**: Slight delay on first connection, faster subsequent calls

### Trade-off 3: UPnP vs HTTP Polling
- **Decision**: Prefer UPnP events, fallback to HTTP polling
- **Rationale**: UPnP is more efficient, but not always available
- **Impact**: Best of both worlds, but more complex implementation

### Trade-off 4: Type Safety vs Flexibility
- **Decision**: Strict type hints and Pydantic validation
- **Rationale**: Catch errors early, better IDE support, self-documenting code
- **Impact**: More verbose code, but fewer runtime errors

### Trade-off 5: Modularity vs Simplicity
- **Decision**: Mixin pattern for API organization
- **Rationale**: Keeps code organized, allows incremental development
- **Impact**: More files, but easier to understand and maintain

### Trade-off 6: Comprehensive Logging vs Performance
- **Decision**: Log all significant operations with device context
- **Rationale**: Debugging device issues requires comprehensive logging
- **Impact**: Slight performance overhead, but much easier troubleshooting

## Design Patterns Used

### 1. Mixin Pattern
- **Purpose**: Organize API functionality into logical modules
- **Implementation**: Each API domain (playback, device, group, etc.) is a mixin class
- **Benefits**: Modular code, easy to test, clear separation of concerns

### 2. Facade Pattern
- **Purpose**: Provide simple interface to complex subsystem
- **Implementation**: WiiMClient composes all mixins, provides single entry point
- **Benefits**: Simple API for users, complex implementation hidden

### 3. Strategy Pattern
- **Purpose**: Handle device variations via capability detection
- **Implementation**: Different strategies based on detected capabilities
- **Benefits**: Graceful handling of device differences

### 4. Adapter Pattern
- **Purpose**: Adapt UPnP events to library's state model
- **Implementation**: UPnP event handlers adapt events to WiiMState
- **Benefits**: Unified state model regardless of source (UPnP or HTTP)

### 5. Factory Pattern
- **Purpose**: Create UPnP clients with proper configuration
- **Implementation**: UpnpClient.create() factory method
- **Benefits**: Encapsulates complex initialization logic

## Future Considerations

### Potential Enhancements
- **Device Discovery**: Add SSDP/Zeroconf discovery support
- **Connection Pooling**: Enhanced connection pooling across multiple devices
- **Caching**: Response caching for frequently accessed data
- **WebSocket**: Support for WebSocket connections if available
- **Async Context Managers**: Better resource management patterns

### Maintenance Considerations
- **Firmware Updates**: New firmware versions may add/remove features
- **Device Models**: New device models may have different capabilities
- **API Changes**: WiiM may change API endpoints or responses
- **Dependencies**: Keep dependencies up to date, monitor for security issues
