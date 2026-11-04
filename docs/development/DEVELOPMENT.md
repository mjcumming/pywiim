# Development Guide

This document provides development patterns and examples. The current
[contribution guide](../../CONTRIBUTING.md), CI workflow, and
[release process](../RELEASE_PROCESS.md) define the working process.

## Table of Contents

1. [Development Setup](#development-setup)
2. [Project Structure](#project-structure)
3. [Code Style](#code-style)
4. [File Organization](#file-organization)
5. [Naming Conventions](#naming-conventions)
6. [Documentation](#documentation)
7. [Error Handling](#error-handling)
8. [Logging](#logging)
9. [Testing](#testing)
10. [Async/Await](#asyncawait)
11. [Capability Detection](#capability-detection)
12. [Common Patterns](#common-patterns)
13. [TODO / Roadmap](#todo--roadmap)
14. [Resources](#resources)

## Development Setup

### Prerequisites

- Python 3.11 or higher
- Git
- pip

### Initial Setup

**1. Clone the Repository**

```bash
git clone <repository-url>
cd pywiim
```

**2. Create Virtual Environment**

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
# On Linux/macOS:
source .venv/bin/activate

# On Windows:
.venv\Scripts\activate
```

**3. Install Dependencies**

```bash
# Install the package in development mode with dev dependencies
pip install -e ".[dev]"

```

**4. Verify Installation**

```bash
# Check that pywiim is installed
python -c "import pywiim; print(pywiim.__version__)"

# Run tests
pytest tests/unit/ -v

# Check code quality
make lint
```

### Git Setup

**Git Configuration**

Recommended `.git/config` settings:

```ini
[user]
    name = Your Name
    email = your.email@example.com

[core]
    autocrlf = input  # Linux/macOS
    # autocrlf = true  # Windows

[init]
    defaultBranch = main
```

**Branching Strategy**

- `main` - Stable, production-ready code
- `develop` - Development branch
- `feature/*` - Feature branches
- `fix/*` - Bug fix branches

### Environment Variables

For integration testing:

```bash
export WIIM_TEST_DEVICE=192.168.1.100  # Device IP
export WIIM_TEST_PORT=80               # Optional port (default: 80)
export WIIM_TEST_HTTPS=false           # Use HTTPS (default: false)
```

### IDE Setup

**VS Code**

Recommended extensions:
- Python
- Pylance
- Ruff
- Black Formatter

Settings (`.vscode/settings.json`):
```json
{
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
    "python.formatting.provider": "black",
    "python.linting.enabled": true,
    "python.linting.ruffEnabled": true,
    "[python]": {
        "editor.formatOnSave": true,
        "editor.codeActionsOnSave": {
            "source.organizeImports": true
        }
    }
}
```

**PyCharm**

1. Open project
2. Configure Python interpreter: `.venv/bin/python`
3. Enable type checking
4. Configure code style: Black, 120 char line length

### Troubleshooting

**Virtual Environment Issues**

If you have issues with the virtual environment:

```bash
# Create a separate environment to preserve any existing one
python3 -m venv .venv-new
source .venv-new/bin/activate
pip install -e ".[dev]"
```

**Import Errors**

If you get import errors:

```bash
# Make sure you're in the virtual environment
which python  # Should show .venv/bin/python

# Reinstall in development mode
pip install -e .
```

**Pre-commit Hook Issues**

If pre-commit hooks fail, inspect the reported check and use the project's
virtual environment. Preserve existing hook configuration.

## Development Workflow

### Running Tests

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run with coverage
pytest tests/unit/ --cov=pywiim --cov-report=html

# Run integration tests (requires device)
export WIIM_TEST_DEVICE=192.168.1.100
pytest tests/integration/ -m integration -v
```

### Code Quality

```bash
# Format code
make format

# Lint code
make lint

# Type check
make typecheck

# Run all checks
make lint typecheck
```

### Pre-commit Hooks

Hooks are optional. Preserve existing Git hook configuration.

```bash
# Install pre-commit hooks
pre-commit install

# Run hooks manually
pre-commit run --all-files
```

## Project Structure

### Directory Structure

```
pywiim/
├── pywiim/                    # Main package
│   ├── __init__.py            # Public API exports
│   ├── client.py              # Main WiiMClient facade
│   ├── exceptions.py          # Exception classes
│   ├── models.py              # Pydantic models
│   ├── capabilities.py        # Capability detection
│   ├── state.py               # State synchronization
│   ├── discovery.py           # Discovery module
│   ├── cli/                   # Command-line tools
│   │   ├── __init__.py
│   │   ├── diagnostics.py     # Diagnostic CLI tool
│   │   ├── discovery_cli.py   # Discovery CLI tool
│   │   ├── monitor_cli.py     # Real-time monitoring CLI
│   │   ├── verify_cli.py      # Feature verification CLI
│   │   ├── group_test_cli.py  # Group testing CLI
│   │   └── join_test_cli.py   # Join/unjoin testing CLI
│   ├── api/                   # API mixin modules
│   │   ├── __init__.py
│   │   ├── base.py            # Base HTTP client
│   │   ├── parser.py          # Response parser
│   │   ├── constants.py       # API constants
│   │   ├── endpoints.py       # Endpoint abstraction
│   │   ├── device.py          # Device operations
│   │   ├── playback.py        # Playback controls
│   │   ├── group.py           # Multiroom groups
│   │   ├── eq.py              # Equalizer
│   │   ├── preset.py          # Presets
│   │   ├── diagnostics.py    # Diagnostics API
│   │   ├── bluetooth.py       # Bluetooth
│   │   ├── audio_settings.py  # Audio settings
│   │   ├── lms.py             # LMS integration
│   │   ├── misc.py            # Miscellaneous
│   │   ├── firmware.py        # Firmware info
│   │   └── timer.py           # Timer/alarm
│   └── upnp/                  # UPnP modules
│       ├── __init__.py
│       ├── client.py          # UPnP client
│       └── eventer.py         # UPnP event handler
│
├── tests/                     # Test suite
│   ├── __init__.py
│   ├── conftest.py            # Pytest fixtures
│   ├── README.md              # Test documentation
│   ├── unit/                  # Unit tests (mocked)
│   │   ├── __init__.py
│   │   ├── test_client.py
│   │   └── test_exceptions.py
│   └── integration/           # Integration tests (real devices)
│       ├── __init__.py
│       └── test_real_device.py
│
├── docs/                      # Documentation
│   ├── user/                  # User documentation
│   │   ├── QUICK_START.md     # Quick start guide
│   │   ├── EXAMPLES.md        # Code examples
│   │   └── DISCOVERY.md       # Discovery tool guide
│   └── integration/           # Integration guides
│       ├── API_REFERENCE.md   # Complete API reference
│       └── HA_INTEGRATION.md  # Home Assistant integration
│
├── scripts/                   # Utility scripts (optional)
│   └── test_my_devices.py     # Quick device test script
│
├── .github/                   # GitHub configuration (if using)
│   └── workflows/            # CI/CD workflows
│
├── pyproject.toml             # Project configuration
├── Makefile                   # Development commands
├── .pre-commit-config.yaml    # Pre-commit hooks
├── .gitignore                 # Git ignore rules
├── .gitattributes             # Git attributes
├── LICENSE                    # License file
└── README.md                  # Main README
```

### File Organization Principles

**1. Package Structure (`pywiim/`)**

**Core Modules** (root of package):
- `client.py` - Main facade (composes all mixins)
- `exceptions.py` - Exception hierarchy
- `models.py` - Pydantic models
- `capabilities.py` - Capability detection
- `state.py` - State synchronization
- `discovery.py` - Discovery module

**CLI Tools** (`pywiim/cli/`):
- `diagnostics.py` - Comprehensive diagnostic tool
- `discovery_cli.py` - Device discovery tool
- `monitor_cli.py` - Real-time player monitoring
- `verify_cli.py` - Feature verification and testing
- `group_test_cli.py` - Group operations testing
- `join_test_cli.py` - Join/unjoin operations testing

**API Modules** (`pywiim/api/`):
- All API mixin modules
- Base client and parser
- Constants and endpoints

**UPnP Modules** (`pywiim/upnp/`):
- UPnP client and event handler

**2. Documentation Structure**

**User Documentation** (`docs/user/`):
- Quick start guides
- API reference
- Code examples
- Tool documentation
- Requirements

**Design Documentation** (`docs/design/`):
- Architecture and design decisions (and **Architecture Decision Records** in `docs/design/adr/`)
- Patterns and best practices
- Lessons learned
- Design principles
- Before implementing features that touch behavior covered by an ADR, check the [ADR index](../design/adr/README.md); for significant new decisions, add an ADR per the format there.

**Development Guides** (`docs/development/`):
- Setup instructions
- Development standards
- Testing guides
- Project structure

**Integration Guides** (`docs/integration/`):
- Framework integration patterns
- Home Assistant integration
- Polling architecture

**3. Test Structure**

**Unit Tests** (`tests/unit/`):
- Mocked tests
- Fast execution
- High coverage

**Integration Tests** (`tests/integration/`):
- Real device tests
- Marked with `@pytest.mark.slow`
- Optional execution

**4. Scripts and Tools**

**Utility Scripts** (`scripts/` or root):
- Quick test scripts
- Development helpers
- Not part of package distribution

### Maintaining structure

Keep related behavior cohesive. Split modules when it improves clarity or reuse;
line count alone is not a reason to create more files.

## Code Style

### Formatting
- **Tool**: Black
- **Line Length**: 120 characters
- **Target Version**: Python 3.11+
- **Configuration**: See `pyproject.toml`

```bash
# Format code
make format
# or
black pywiim tests
```

### Linting
- **Tool**: Ruff
- **Rules**: E, W, F, I, B, C4, UP
- **Configuration**: See `pyproject.toml`

```bash
# Lint code
make lint
# or
ruff check pywiim tests
```

### Type Checking
- **Tool**: mypy
- **Mode**: Strict where possible
- **Configuration**: See `pyproject.toml`

```bash
# Type check
make typecheck
# or
mypy pywiim
```

### Import Sorting
- **Tool**: isort
- **Known First Party**: pywiim
- **Configuration**: See `pyproject.toml`

```bash
# Sort imports (included in make format)
isort pywiim tests
```

## File Organization

### File size

Prefer cohesive modules and clear functions. There is no hard line-count limit
or issue/pragma requirement for larger files.

### Module Organization
- **One Responsibility**: Each module should have a single, clear responsibility
- **Clear Boundaries**: No circular dependencies
- **Related Classes**: Can be in same file if closely related

### Import Organization

1. Standard library imports
2. Third-party imports
3. Local imports (pywiim)
4. Type-only imports (if using `TYPE_CHECKING`)

## Naming Conventions

### Files
- **Modules**: `snake_case.py`
- **Classes**: `PascalCase`
- **Functions**: `snake_case`
- **Constants**: `UPPER_SNAKE_CASE`

### Directories
- **Packages**: `snake_case` (no underscores per project convention)
- **Tests**: `tests/` with subdirectories

### Classes
- **Style**: PascalCase
- **Examples**: `WiiMClient`, `DeviceCapabilities`, `PlayerStatus`

### Functions
- **Style**: snake_case
- **Examples**: `get_player_status()`, `detect_capabilities()`, `parse_response()`

### Constants
- **Style**: UPPER_SNAKE_CASE
- **Examples**: `DEFAULT_PORT`, `MAX_RETRIES`, `API_ENDPOINT_STATUS`

### Private
- **Style**: Leading underscore
- **Examples**: `_request()`, `_capabilities`, `_parse_data()`

### Type Variables
- **Style**: Single uppercase letter
- **Examples**: `_T`, `_P`, `_R` (for generic types)

## Documentation

### Docstrings
- **Style**: Google style
- **Required**: All public APIs
- **Optional**: Private methods (but recommended for complex logic)

```python
def get_player_status(self) -> PlayerStatus:
    """Get current player status from device.
    
    Retrieves playback state, volume, position, and metadata from the device.
    Uses getPlayerStatusEx endpoint if available, falls back to getStatusEx.
    
    Returns:
        PlayerStatus model with current device state.
        
    Raises:
        WiiMRequestError: If the request fails after retries.
        WiiMResponseError: If the response is invalid.
        
    Example:
        >>> status = await client.get_player_status()
        >>> print(status.play_state)
        'play'
    """
    ...
```

### Inline Comments
- **Purpose**: Explain "why", not "what"
- **When**: Complex logic, non-obvious decisions, workarounds

```python
# Audio Pro MkII doesn't provide volume via HTTP, use UPnP instead
if capabilities.audio_pro_generation == "mkii":
    return await self._get_volume_upnp()
```

### Type Hints
- **Required**: All function signatures
- **Style**: Use `from __future__ import annotations` for forward references
- **Models**: Use Pydantic models for data structures

```python
from __future__ import annotations

from typing import Any

def parse_response(
    data: dict[str, Any],
    device_info: DeviceInfo | None = None,
) -> PlayerStatus:
    """Parse API response into PlayerStatus model."""
    ...
```

## Error Handling

### Exception Hierarchy
```python
WiiMError (base)
├── WiiMConnectionError
├── WiiMTimeoutError
├── WiiMRequestError
├── WiiMResponseError
└── WiiMInvalidDataError
```

### Error Context
All exceptions should include device context:

```python
raise WiiMRequestError(
    f"Failed to get player status: {error}",
    endpoint="/httpapi.asp?command=getPlayerStatusEx",
    attempts=3,
    last_error=error,
    device_info={
        "firmware_version": self.device_info.firmware,
        "device_model": self.device_info.model,
        "is_wiim_device": self.capabilities.is_wiim_device,
    },
    operation_context="get_player_status",
)
```

### Graceful Degradation
Never crash on device variations:

```python
# Check capability before calling endpoint
if not self.capabilities.supports_metadata:
    _LOGGER.debug(
        "Device %s does not support metadata endpoint, skipping",
        self.host,
    )
    return None

try:
    return await self._request(API_ENDPOINT_METADATA)
except WiiMRequestError as e:
    # Mark as unsupported and continue
    self.capabilities.supports_metadata = False
    _LOGGER.info(
        "Metadata endpoint not supported on %s, marking as unavailable",
        self.host,
    )
    return None
```

## Logging

### Philosophy

**Log when it matters, not on every poll.**

The purpose of logging is to help developers and users understand what's happening in the system, especially when things go wrong or change. Logging the same unchanged information every few seconds creates noise that obscures real issues.

### Logger Setup

```python
import logging

_LOGGER = logging.getLogger(__name__)
```

### Logging Levels

#### ERROR
Use for unrecoverable errors that prevent functionality:
- Failed connections after all retries
- Invalid configuration
- Critical parsing errors

```python
_LOGGER.error("Failed to connect to device at %s after %d retries: %s", host, retries, error)
```

#### WARNING
Use for recoverable errors or degraded functionality:
- Transient connection issues
- Unexpected but handled response formats  
- Deprecated feature usage

```python
_LOGGER.warning("Device returned unexpected format, using fallback parser: %s", error)
```

#### INFO
Use for significant events and state changes:
- Track changes (music playing)
- Device discovery results
- Group formation/disbanding
- Major state transitions

```python
_LOGGER.info("🎵 Track changed: %s", track_name)
_LOGGER.info("Group disbanded (master: %s)", master_host)
```

#### DEBUG
Use sparingly for diagnostic information **only when values change**:
- State changes (not every poll result)
- Protocol fallbacks
- Capability detection
- Group synchronization changes

```python
# ✅ GOOD: Log when value changes
if new_source != old_source:
    _LOGGER.debug("Source changed from %s to %s", old_source, new_source)

# ❌ BAD: Log on every poll
_LOGGER.debug("Current source: %s", current_source)
```

### Anti-Patterns to Avoid

#### ❌ Logging on Every Poll

**Don't do this:**
```python
async def get_status():
    status = await device.get_status()
    _LOGGER.debug("Status: %s", status)  # Spams logs every 5 seconds!
    return status
```

**Do this instead:**
```python
async def get_status():
    status = await device.get_status()
    # Status available for debugging if needed, but not logged
    # to avoid spam on every poll cycle
    return status
```

#### ❌ Logging Unchanged Metadata

**Don't do this:**
```python
_LOGGER.debug("Parsing: Title=%s, Artist=%s", title, artist)  # Every poll!
```

**Do this instead:**
```python
# Only log when track actually changes
if current_track != last_track:
    _LOGGER.info("🎵 Track changed: %s", current_track)
```

#### ❌ Logging Raw API Responses

**Don't do this:**
```python
response = await api_call()
_LOGGER.debug("API response: %s", response)  # Huge JSON blob every poll!
```

**Do this instead:**
```python
response = await api_call()
# Response available for debugging if needed, but not logged
# to avoid spam on every poll cycle
```

### Best Practices

#### 1. Log State Changes, Not State

```python
# ✅ GOOD
if play_state != previous_play_state:
    _LOGGER.debug("Play state changed: %s -> %s", previous_play_state, play_state)

# ❌ BAD  
_LOGGER.debug("Play state: %s", play_state)
```

#### 2. Use Conditional Logging for Expensive Operations

```python
# ✅ GOOD: Check if DEBUG is enabled before expensive operations
if _LOGGER.isEnabledFor(logging.DEBUG):
    formatted_data = format_complex_data(large_object)
    _LOGGER.debug("Complex data: %s", formatted_data)
```

#### 3. Provide Context in Error Messages

```python
# ✅ GOOD: Include relevant context
_LOGGER.warning(
    "Failed to refresh state for %s (model=%s, firmware=%s): %s",
    host, model, firmware, error
)

# ❌ BAD: Minimal context
_LOGGER.warning("Refresh failed: %s", error)
```

#### 4. Use Emojis Sparingly for Important Events

```python
# ✅ GOOD: Makes track changes easy to spot
_LOGGER.info("🎵 Track changed: %s", track)

# ✅ GOOD: Highlights AirPlay issues
_LOGGER.debug("🔍 AirPlay position parsing issue: %s", details)

# ❌ BAD: Overuse makes them meaningless
_LOGGER.debug("🔧 Getting status...")  # Every poll!
```

#### 5. Track Changes with State Variables

```python
class Parser:
    def __init__(self):
        self._last_track = None
    
    def parse(self, data):
        current_track = data.get('title')
        
        # Only log when track changes
        if current_track != self._last_track:
            _LOGGER.info("🎵 Track changed: %s", current_track)
            self._last_track = current_track
```

#### 6. Log Startup/Initialization Events at INFO

```python
# ✅ GOOD: Startup events at INFO level
_LOGGER.info("Discovering devices via SSDP...")
_LOGGER.info("Discovery complete: found %d device(s)", count)

# ✅ GOOD: Capability detection at DEBUG
_LOGGER.debug("Device %s supports EQ (detected via %s)", host, endpoint)
```

#### 7. Aggregate Repeated Events

```python
# ✅ GOOD: Log summary instead of every item
_LOGGER.info("Discovery found %d device(s)", len(devices))

# ❌ BAD: Log each item
for device in devices:
    _LOGGER.info("Found device: %s", device)  # Spams logs
```

### Integration-Specific Guidelines

For Home Assistant and other integrations that poll frequently:

1. **First Load**: Log at DEBUG or INFO to capture initial state
2. **Subsequent Polls with No Changes**: Don't log anything
3. **When Values Change**: Log at DEBUG with the change
4. **Errors**: Always log at WARNING/ERROR

Example for HA coordinator:
```python
async def _async_update_data(self):
    """Fetch data from device."""
    new_data = await self.device.get_status()
    
    # Only log if something changed or it's first load
    if self._first_load:
        _LOGGER.debug("Initial data for %s: sources=%s", self.name, new_data.sources)
        self._first_load = False
    elif new_data != self._last_data:
        _LOGGER.debug("Data changed for %s: %s", self.name, changes)
    
    self._last_data = new_data
    return new_data
```

### When to Use Each Level - Quick Reference

| Level | When to Use | Examples |
|-------|-------------|----------|
| **ERROR** | Unrecoverable failures | Connection failed after retries, critical parse error |
| **WARNING** | Recoverable issues, degraded state | Unexpected response format, fallback used |
| **INFO** | Significant events, user-visible changes | Track changed, device discovered, group formed |
| **DEBUG** | Diagnostic details **only when changed** | Source changed, capability detected, state transition |

### Testing Your Logging

Before committing, check that your logging:

1. ✅ Doesn't log on every poll when nothing changes
2. ✅ Does log when meaningful state changes occur  
3. ✅ Provides enough context to understand the issue
4. ✅ Isn't using expensive string operations without checking log level
5. ✅ Uses appropriate log levels for the severity

### Summary

**Good logging is:**
- Event-driven (logs changes, not states)
- Contextual (includes relevant information)
- Appropriately leveled (ERROR for failures, DEBUG for diagnostics)
- Efficient (checks log level before expensive operations)

**Bad logging is:**
- Polling-driven (logs every status check)
- Noisy (logs unchanged values repeatedly)
- Overly verbose (huge data dumps at DEBUG)
- Missing context (just "Error: failed")

Remember: **The best debug log is one that helps you find bugs without drowning in noise.**

## Testing

### Test Organization Strategy

**Directory Structure**

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── README.md                # Testing guide
│
├── unit/                    # Fast unit tests with mocks
│   ├── __init__.py
│   ├── test_client.py       # ✅ Client initialization
│   ├── test_exceptions.py   # ✅ Exception hierarchy
│   ├── test_models.py       # ✅ Pydantic models
│   ├── test_capabilities.py # ✅ Capability detection
│   ├── test_state.py        # ✅ State synchronization
│   ├── test_discovery.py    # ✅ Device discovery
│   ├── test_normalize.py    # ✅ Normalization helpers
│   ├── test_group_helpers.py # ✅ Group utilities
│   ├── test_polling.py      # ✅ Polling strategies
│   ├── test_backoff.py      # ✅ Backoff controllers
│   ├── test_parser.py       # ✅ Response parsing
│   ├── test_player.py       # ✅ Player functionality
│   ├── test_role.py         # ✅ Role management
│   ├── test_group.py        # ✅ Group functionality
│   │
│   ├── api/                 # API mixin tests
│   │   ├── __init__.py
│   │   ├── test_base.py     # ✅ Base HTTP client
│   │   ├── test_parser.py   # ✅ Response parsing
│   │   ├── test_endpoints.py # ✅ Endpoint abstraction
│   │   ├── test_device.py   # ✅ Device API
│   │   ├── test_playback.py # ✅ Playback API
│   │   ├── test_group.py    # ✅ Group API
│   │   ├── test_eq.py       # ✅ EQ API
│   │   ├── test_preset.py   # ✅ Preset API
│   │   ├── test_bluetooth.py # ✅ Bluetooth API
│   │   ├── test_audio_settings.py # ✅ Audio settings
│   │   ├── test_lms.py      # ✅ LMS integration
│   │   ├── test_misc.py     # ✅ Misc API
│   │   ├── test_firmware.py # ✅ Firmware API
│   │   ├── test_timer.py    # ✅ Timer API
│   │   ├── test_ssl.py      # ✅ SSL/TLS handling
│   │   └── test_diagnostics.py # ❌ Missing - Diagnostics API
│   │
│   └── upnp/                # UPnP tests
│       ├── test_client.py   # ✅ UPnP client
│       └── test_eventer.py  # ✅ UPnP event handling
│
└── integration/             # Tests with real devices
    ├── __init__.py
    └── test_real_device.py  # ✅ Integration tests
```

### Test Categories and Best Practices

**1. Unit Tests (Fast, Isolated, Mocked)**

**Purpose:** Test individual functions and classes in isolation with mocked dependencies.

**Best Practices:**
- ✅ Use mocks for all external dependencies (HTTP, UPnP, network)
- ✅ Test one thing at a time (single responsibility)
- ✅ Test both success and failure paths
- ✅ Test edge cases and boundary conditions
- ✅ Keep tests fast (< 100ms each)
- ✅ Use descriptive test names: `test_<function>_<scenario>_<expected_result>`

**Example Structure:**
```python
@pytest.mark.asyncio
async def test_set_volume_valid_range(mock_client):
    """Test setting volume within valid range."""
    mock_client._request = AsyncMock(return_value={"status": "ok"})
    
    await mock_client.set_volume(0.5)
    
    mock_client._request.assert_called_once()
    call_args = mock_client._request.call_args
    assert "vol" in str(call_args)

@pytest.mark.asyncio
async def test_set_volume_out_of_range(mock_client):
    """Test setting volume outside valid range raises error."""
    with pytest.raises(ValueError, match="Volume must be"):
        await mock_client.set_volume(1.5)
```

**2. Integration Tests (Real Devices)**

**Purpose:** Test actual communication with real devices to catch protocol issues.

**Best Practices:**
- ✅ Use environment variables for device configuration
- ✅ Skip tests if device not available (don't fail CI)
- ✅ Mark slow tests that change device state
- ✅ Restore device state after tests when possible
- ✅ Test happy paths and common scenarios
- ✅ Test with different device types (WiiM, Audio Pro, etc.)

**Example Structure:**
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_player_status_real_device(real_device_client, integration_test_marker):
    """Test getting player status from real device."""
    status = await real_device_client.get_player_status()
    
    assert status is not None
    assert "play_state" in status or "state" in status
```

### Test Structure
- Mirror source structure in `tests/unit/`
- Use descriptive test names
- Group related tests in classes
- Use fixtures for common setup

### Test Naming
```python
def test_get_player_status_returns_valid_model():
    """Test that get_player_status returns valid PlayerStatus model."""
    ...

def test_get_player_status_handles_timeout():
    """Test that get_player_status handles timeout errors gracefully."""
    ...

class TestCapabilityDetection:
    """Test capability detection for different device types."""
    
    def test_detects_wiim_device(self):
        """Test detection of WiiM devices."""
        ...
    
    def test_detects_audio_pro_mkii(self):
        """Test detection of Audio Pro MkII devices."""
        ...
```

### Mocking
- Mock all external dependencies (HTTP, UPnP)
- Use `unittest.mock` or `pytest-mock`
- Verify mock calls when appropriate

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_get_player_status():
    """Test getting player status."""
    client = WiiMClient("192.168.1.100")
    
    with patch.object(client, "_request") as mock_request:
        mock_request.return_value = {"play_status": "play", "vol": 50}
        
        status = await client.get_player_status()
        
        assert status.play_state == "play"
        assert status.volume == 50
        mock_request.assert_called_once()
```

### Coverage

Use coverage to find untested behavior, not as a substitute for meaningful
tests. Current enforced thresholds are in [codecov.yml](../../codecov.yml) and
the [CI workflow](../../.github/workflows/ci.yml).

### Test Execution Strategy

**Running Tests**

```bash
# Run all unit tests (fast)
pytest tests/unit/ -v

# Run all tests with coverage
pytest tests/unit/ --cov=pywiim --cov-report=html --cov-report=term

# Run integration tests (requires device)
WIIM_TEST_DEVICE=192.168.1.100 pytest tests/integration/ -m integration -v

# Run specific test file
pytest tests/unit/test_playback.py -v

# Run specific test
pytest tests/unit/test_playback.py::TestPlaybackAPI::test_play_success -v

# Run tests matching pattern
pytest tests/unit/ -k "volume" -v

# Run fast tests only (skip slow integration tests)
pytest tests/ -v -m "not slow"
```

**CI/CD Integration**

GitHub CI runs formatting, lint, type checks, and tests marked as non-integration
on supported Python versions. Device tests are separate and run when suitable
hardware is available; see [tests/README.md](../../tests/README.md).

### Testing Async Code

**Best Practices for Async Tests:**

1. **Always use `@pytest.mark.asyncio`** for async test functions
2. **Use `AsyncMock`** for mocking async functions
3. **Test async context managers** properly
4. **Handle async cleanup** in fixtures
5. **Test concurrent operations** when relevant

**Example:**
```python
@pytest.mark.asyncio
async def test_concurrent_requests(mock_client):
    """Test handling concurrent API requests."""
    mock_client._request = AsyncMock(return_value={"status": "ok"})
    
    # Make concurrent requests
    results = await asyncio.gather(
        mock_client.get_player_status(),
        mock_client.get_device_info_model(),
        mock_client.get_volume(),
    )
    
    assert len(results) == 3
    assert mock_client._request.call_count == 3
```

### Real-device testing

Test device- or firmware-dependent behavior on suitable hardware when available.
Check what a test changes, preserve and restore device settings, and record the
model, firmware, and any limitations. Do not claim a device test was run when it
was not. See [tests/README.md](../../tests/README.md) for current commands.

```bash
WIIM_TEST_DEVICE=192.168.1.100 pytest tests/integration/ -m integration -v
```

Use `wiim-discover` to find devices. Run
`wiim-diagnostics <device_ip> --output report.json` to capture diagnostics.
Remove sensitive information before
sharing the report. For read-only HTTP probes, see the
[curl HTTP API guide](../testing/CURL_HTTPAPI.md).

## Async/Await

### Best Practices
- Use `async`/`await` for all I/O operations
- Use `asyncio.timeout` instead of deprecated `async_timeout`
- Use context managers for resource cleanup
- Avoid blocking operations in event loop

```python
# Good: Async with timeout
async def get_status(self) -> PlayerStatus:
    async with asyncio.timeout(5.0):
        response = await self.session.get(url)
        return await response.json()

# Bad: Blocking operation
async def get_status(self) -> PlayerStatus:
    time.sleep(1)  # Don't do this!
    ...
```

## Capability Detection

### Principles
- **Never Assume**: Always check capabilities before calling endpoints
- **Graceful Fallback**: If endpoint fails, mark as unsupported and continue
- **Firmware Detection**: Detect firmware version and apply known workarounds
- **Log Decisions**: Log how capabilities were determined

### Implementation
```python
# Check capability before API call
if not self.capabilities.supports_metadata:
    return None

# Probe endpoint if capability unknown
if self.capabilities.supports_metadata is None:
    try:
        await self._request(API_ENDPOINT_METADATA)
        self.capabilities.supports_metadata = True
    except WiiMRequestError:
        self.capabilities.supports_metadata = False
        _LOGGER.info("Metadata endpoint not supported")
        return None
```

## Common Patterns

### Retry Logic
```python
max_retries = 3
for attempt in range(1, max_retries + 1):
    try:
        return await self._request(endpoint)
    except WiiMTimeoutError:
        if attempt == max_retries:
            raise
        await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

### Capability-Aware Requests
```python
async def get_metadata(self) -> TrackMetadata | None:
    """Get track metadata if supported."""
    if not self.capabilities.supports_metadata:
        return None
    return await self._request(API_ENDPOINT_METADATA)
```

### State Management
```python
def apply_state_update(self, changes: dict[str, Any]) -> bool:
    """Apply state changes and return True if changed."""
    changed = False
    for key, value in changes.items():
        if getattr(self.state, key) != value:
            setattr(self.state, key, value)
            changed = True
    return changed
```

## TODO / Roadmap

This section tracks architectural improvements and technical debt identified during code reviews.

### Priority 1: High Impact

(No high-priority items currently pending)

---

### Priority 2: Medium Impact


---

### Priority 3: Future Improvements

(No future improvement items currently pending)

---

### Code Review Summary (Dec 2025)

| Aspect | Grade | Notes |
|--------|-------|-------|
| **Architecture** | A | Profile system, state sync, mixin pattern excellent |
| **Documentation** | A | 15+ design docs is exceptional |
| **Test Quantity** | A | 1,390 tests (comprehensive coverage) |
| **Test Quality** | B+ | Focus on behavior tests over shallow mocks, Player class coverage 79% (up from 48%), core logic well tested |
| **Code Organization** | A- | StateManager refactored (Jan 2025) ✅ |
| **Error Handling** | A- | Good exception hierarchy, graceful degradation |
| **Maintainability** | A- | Clear patterns, well documented |

---

## Resources

- [Python Type Hints](https://docs.python.org/3/library/typing.html)
- [Pydantic v2 Documentation](https://docs.pydantic.dev/)
- [Black Documentation](https://black.readthedocs.io/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [mypy Documentation](https://mypy.readthedocs.io/)
- [pytest Documentation](https://docs.pytest.org/)
