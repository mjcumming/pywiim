# Architecture Documentation

## Overview

pywiim is a Python library for communicating with WiiM and LinkPlay-based audio devices. It provides a clean, async interface for device control, status monitoring, and multiroom management.

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Application Layer                     │
│  (Home Assistant Integration, CLI, Custom Apps, etc.)   │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│                    pywiim Library                        │
│  ┌──────────────────────────────────────────────────┐   │
│  │           WiiMClient (Facade)                    │   │
│  │  - Composes all API mixins                       │   │
│  │  - Provides unified interface                   │   │
│  └──────────────┬───────────────────────────────────┘   │
│                 │                                        │
│  ┌──────────────┴──────────────┐                       │
│  │      API Mixin Modules       │                       │
│  │  - DeviceAPI                 │                       │
│  │  - PlaybackAPI                │                       │
│  │  - GroupAPI                   │                       │
│  │  - EQAPI                      │                       │
│  │  - PresetAPI                  │                       │
│  │  - DiagnosticsAPI              │                       │
│  │  - BluetoothAPI (unofficial)   │                       │
│  │  - AudioSettingsAPI (unofficial)│                    │
│  │  - LMSAPI (unofficial)         │                       │
│  │  - MiscAPI (unofficial)         │                       │
│  └──────────────┬───────────────┘                       │
│                 │                                        │
│  ┌──────────────┴──────────────┐                       │
│  │      Core Components          │                       │
│  │  - BaseAPI (transport layer)  │                       │
│  │  - Parser (response parsing)   │                       │
│  │  - Constants (API endpoints)   │                       │
│  │  - Capabilities (device detection)│                    │
│  └──────────────┬───────────────┘                       │
│                 │                                        │
│  ┌──────────────┴──────────────┐                       │
│  │      UPnP Module             │                       │
│  │  - UpnpClient                │                       │
│  │  - UpnpEventer                │                       │
│  │  - State Management           │                       │
│  └──────────────┬───────────────┘                       │
│                 │                                        │
│  ┌──────────────┴──────────────┐                       │
│  │      Data Models              │                       │
│  │  - DeviceInfo                 │                       │
│  │  - PlayerStatus               │                       │
│  │  - MultiroomInfo               │                       │
│  │  - TrackMetadata              │                       │
│  │  - EQInfo                     │                       │
│  └───────────────────────────────┘                       │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              External Dependencies                       │
│  - aiohttp (HTTP client)                                 │
│  - async-upnp-client (UPnP support)                      │
│  - pydantic (data validation)                           │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              WiiM/LinkPlay Devices                       │
│  - HTTP/HTTPS API                                        │
│  - UPnP/DLNA Services                                    │
└─────────────────────────────────────────────────────────┘
```

## Core Components

### 1. WiiMClient (Facade)

**Location**: `pywiim/client.py`

**Purpose**: Main entry point for the library. Composes all API mixins and provides a unified interface.

**Responsibilities**:
- Compose all API mixin classes
- Provide connection management
- Handle device discovery (optional)
- Expose clean public API

**Design Pattern**: Facade Pattern

### 2. Base API Client

**Location**: `pywiim/api/base.py`

**Purpose**: Core HTTP transport layer with retry logic, error handling, and SSL support.

**Responsibilities**:
- HTTP request handling with aiohttp
- Retry logic with exponential backoff
- SSL/TLS certificate handling
- Error handling and exception raising
- Connection management

**Key Features**:
- Transport abstraction (allows custom aiohttp sessions)
  - Accepts optional `session` parameter for connection pooling
  - HA integration can pass `async_get_clientsession(hass)` for shared session
  - Creates own session if not provided (framework-agnostic)
- Capability-aware request routing
- Comprehensive logging with device context

### 3. API Parser

**Location**: `pywiim/api/parser.py`

**Purpose**: Parse and normalize API responses from devices.

**Responsibilities**:
- Parse raw API responses
- Normalize field names and values
- Handle time unit conversion (ms vs microseconds)
- Decode hex-encoded text strings
- Map API fields to model fields

**Design**: Stateless functions for testability

### 4. API Constants and Endpoint Registry

**Location**: `pywiim/api/constants.py` and `pywiim/api/endpoints.py`

**Purpose**: Centralized API endpoint definitions, mappings, and endpoint abstraction.

**Responsibilities**:
- Define all API endpoint paths
- Provide field mapping dictionaries
- Define mode and status mappings
- Organize constants by category
- **Endpoint Registry**: Map logical endpoint names to vendor/generation-specific endpoint chains
- **Endpoint Resolver**: Resolve logical endpoints to actual paths based on device capabilities

**Key Features**:
- Logical endpoint names (e.g., "player_status") instead of literal paths
- Vendor-specific endpoint chains (WiiM, Arylic, Audio Pro)
- Generation-specific endpoint chains (MkII, W-Generation, Original)
- Fallback chains for graceful degradation
- Runtime endpoint probing and caching

### 5. Capability Detection

**Location**: `pywiim/capabilities.py` (detection); merged results live on **`WiiMClient.capabilities`**

**Purpose**: Detect device capabilities and handle device variations across multiple LinkPlay vendors.

**Responsibilities**:
- Detect vendor (WiiM, Arylic, Audio Pro, etc.)
- Detect device type (WiiM vs Legacy)
- Detect firmware version
- Detect Audio Pro generation
- Probe endpoint availability
- Cache capability results
- Apply vendor-specific and device-specific workarounds

**Design Pattern**: Strategy Pattern with Vendor Registry (different strategies based on vendor and capabilities)

**Source of truth (applications and docs)** — For optional HTTP API features (EQ, PEQ, presets, subwoofer, 12V trigger, channel balance, metadata, alarms, etc.), **the merged `player.client.capabilities` dict is authoritative** after detection (and after any documented corrective updates). Integrations such as Home Assistant **must gate** entities and services on these keys (or on `Player` properties explicitly documented as mirroring them), **not** on device model or marketing name alone. Static helpers such as `device_capabilities.py` address **source/input catalog** layout; they do not replace runtime `supports_*` for unrelated endpoints. See **[ADR 018: Client `capabilities` Dict — Single Source of Truth](adr/018-capabilities-dict-source-of-truth.md)**.

### 6. Data Models

**Location**: `pywiim/models.py`

**Purpose**: Pydantic models for type-safe data structures.

**Models**:
- `DeviceInfo`: Device information
- `PlayerStatus`: Playback state and metadata
- `MultiroomInfo`: Group information
- `TrackMetadata`: Track details
- `EQInfo`: Equalizer settings
- `SlaveInfo`: Slave device information

**Features**:
- Pydantic v2 validation
- Field aliases for API key mapping
- Validators for normalization
- Type hints throughout

### 7. UPnP Module

**Location**: `pywiim/upnp/`

**Purpose**: UPnP/DLNA event subscriptions and state management.

**Components**:
- `client.py`: UPnP client wrapper using async-upnp-client
- `eventer.py`: Event subscription manager
- `state.py`: State management and diff tracking

**Features**:
- Real-time event subscriptions
- AVTransport and RenderingControl services
- SSL support for HTTPS devices
- Automatic reconnection on failure
- Uses `async-upnp-client` library (same as HA integrations)
- Creates own aiohttp session for SSL handling (may accept optional session for future optimization)

### 8. State Synchronization

**Location**: `pywiim/state.py`

**Purpose**: Intelligently merge state from HTTP polling and UPnP events.

**Responsibilities**:
- Merge overlapping data from HTTP and UPnP sources
- Resolve conflicts using freshness windows and source priority
- Handle stale data (ignore if too old)
- Handle missing data (fill gaps from other source)
- Preserve metadata during transitions
- Track source availability and health

**Key Features**:
- Timestamped fields with source tracking
- Freshness windows for each field type
- Source priority rules (UPnP for real-time, HTTP for metadata)
- Conflict resolution with clear rules
- Graceful degradation when one source unavailable
- Metadata preservation during play state transitions

**Design Pattern**: State Synchronization Pattern with Conflict Resolution

### 9. Polling Strategy

**Location**: `pywiim/polling.py`

**Purpose**: Provide polling strategy recommendations and helpers for applications.

**Responsibilities**:
- Recommend optimal polling intervals based on device state
- Provide conditional fetching helpers (device info, multiroom, metadata, EQ)
- Track fetch timing for conditional logic
- Detect track changes for metadata fetching
- Provide parallel execution helpers

**Key Features**:
- Adaptive intervals: 1s playing / 5s idle (WiiM), 3s playing / 15s idle (Legacy)
- Conditional fetching: Device info (60s), Multiroom (15s), Metadata (on track change), EQ (60s)
- Capability-aware: Skips unsupported endpoints
- Framework-agnostic: Applications manage their own polling loops
- Performance optimized: Parallel execution helpers

**Design Pattern**: Strategy Pattern (recommendations, not enforcement)

## Design Patterns

### 1. Mixin Pattern

**Purpose**: Organize API functionality into logical modules.

**Implementation**: Each API domain (playback, device, group, etc.) is a mixin class that provides specific methods. The main client composes all mixins via multiple inheritance.

**Benefits**:
- Modular code organization
- Easy to test individual modules
- Clear separation of concerns
- Incremental development

### 2. Facade Pattern

**Purpose**: Provide simple interface to complex subsystem.

**Implementation**: `WiiMClient` composes all mixins and provides a single, clean entry point.

**Benefits**:
- Simple API for users
- Complex implementation hidden
- Easy to maintain and extend

### 3. Strategy Pattern

**Purpose**: Handle device variations via capability detection.

**Implementation**: Different strategies (endpoint selection, protocol selection, etc.) based on detected device capabilities.

**Benefits**:
- Graceful handling of device differences
- No hardcoded assumptions
- Easy to add new device types

### 4. Adapter Pattern

**Purpose**: Adapt UPnP events to library's state model.

**Implementation**: UPnP event handlers adapt events to `WiiMState` dataclass.

**Benefits**:
- Unified state model
- Works with both UPnP and HTTP sources
- Easy to extend with new event types

### 5. Factory Pattern

**Purpose**: Create UPnP clients with proper configuration.

**Implementation**: `UpnpClient.create()` factory method handles complex initialization.

**Benefits**:
- Encapsulates initialization logic
- Handles errors during creation
- Returns properly configured instances

## Data Flow

### HTTP API Request Flow

```
User Code
    │
    ▼
WiiMClient.get_player_status()
    │
    ▼
PlaybackAPI.get_player_status() (mixin)
    │
    ▼
BaseAPI._request() (transport)
    │
    ├─► Capability Check
    │   └─► Route to appropriate endpoint
    │
    ├─► Retry Logic
    │   └─► Exponential backoff on failure
    │
    ├─► SSL/TLS Handling
    │   └─► Client cert for Audio Pro MkII
    │
    ▼
aiohttp ClientSession
    │
    ▼
Device HTTP/HTTPS API
    │
    ▼
Response
    │
    ▼
Parser.parse_player_status()
    │
    ▼
PlayerStatus Model (Pydantic validation)
    │
    ▼
Return to User
```

### UPnP Event Flow

```
Device UPnP Service
    │
    ▼
UpnpEventer (subscription manager)
    │
    ▼
Event Callback
    │
    ▼
State.apply_diff() (state management)
    │
    ▼
State Change Detected?
    │
    ├─► Yes ──► Log state transition
    │          └─► Notify application (via callback)
    │
    └─► No ──► Ignore (no change)
```

## Error Handling

### Exception Hierarchy

```
WiiMError (base)
├── WiiMConnectionError
│   └── Connection failures
├── WiiMTimeoutError
│   └── Request timeouts
├── WiiMRequestError
│   └── Request failures (with context)
├── WiiMResponseError
│   └── Invalid responses
└── WiiMInvalidDataError
    └── Data validation errors
```

### Error Context

All exceptions include:
- Device information (host, firmware, model)
- Endpoint that failed
- Attempt count
- Last error (if applicable)
- Operation context

### Graceful Degradation

- Capability checks before API calls
- Fallback mechanisms (UPnP → HTTP)
- Mark endpoints as unsupported on failure
- Continue operation when possible

## Logging Strategy

### Structured Logging

All log messages include device context:
- Device host/IP
- Firmware version
- Device model
- Operation being performed

### Log Levels

- **DEBUG**: Detailed operation information
- **INFO**: Significant events (state changes, capability detection)
- **WARNING**: Recoverable issues (fallbacks, retries)
- **ERROR**: Errors with full context

### Log Categories

- **API Calls**: Endpoint, device, attempt count
- **Capability Detection**: How capabilities were determined
- **State Transitions**: What changed, when, why, trigger
- **Errors**: Full context including device info

## Testing Strategy

### Unit Tests

- Mock all external dependencies (HTTP, UPnP)
- Test all API endpoints
- Test error handling paths
- Test model validation
- Test capability detection

### Integration Tests

- Optional tests against real devices
- Test UPnP subscriptions
- Test firmware variations
- Document manual testing procedures

### Test Coverage

- Target: 90%+ coverage
- Focus: All public APIs, error paths, edge cases

## Dependencies

### Core Dependencies

- **aiohttp** (>=3.8.0): HTTP client
- **pydantic** (>=2.0.0): Data validation
- **async-upnp-client** (>=0.40.0): UPnP support

### Development Dependencies

- **black**: Code formatting
- **ruff**: Linting
- **mypy**: Type checking
- **pytest**: Testing framework
- **pytest-asyncio**: Async test support
- **pytest-cov**: Coverage reporting

## Future Considerations

### Potential Enhancements

- **Device Discovery**: SSDP/Zeroconf discovery support
- **Connection Pooling**: Enhanced pooling across devices
- **Caching**: Response caching for frequently accessed data
- **WebSocket**: Support for WebSocket connections
- **Async Context Managers**: Better resource management

### Maintenance

- **Firmware Updates**: Monitor for API changes
- **Device Models**: Add support for new models
- **Dependencies**: Keep dependencies up to date
- **Security**: Monitor for security issues

## References

- [Home Assistant Integration Quality Scale](https://developers.home-assistant.io/docs/core/integration-quality-scale/)
- [Python Design Patterns](https://python-patterns.guide/)
- [Pydantic v2 Documentation](https://docs.pydantic.dev/)
- [async-upnp-client Documentation](https://github.com/StevenLooman/async_upnp_client)

