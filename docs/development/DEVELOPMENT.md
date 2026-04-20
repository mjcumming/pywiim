# Development Guide

This document outlines coding standards, best practices, development guidelines, and testing strategies for pywiim.

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

# Or install dependencies separately:
pip install -e .
pip install -r requirements-dev.txt  # if you create one
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

**Initial Commit**

If this is a new repository:

```bash
# Initialize git (if not already done)
git init

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit: pywiim library extraction"
```

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
# Remove and recreate
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
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

If pre-commit hooks fail:

```bash
# Update hooks
pre-commit autoupdate

# Skip hooks for a commit (not recommended)
git commit --no-verify
```

## Development Workflow

### Running Tests

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run with coverage
pytest tests/unit/ --cov=pywiim --cov-report=html

# Run integration tests (requires device)
export WIIM_TEST_DEVICE=192.168.1.100
pytest tests/integration/ -v
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

### Current Organization Status

**Overall Assessment: ✅ Well Organized**

The project follows good Python packaging practices and maintains clear separation of concerns.

**✅ Strengths**

**Package Structure:**
- Clear module organization: `pywiim/`, `pywiim/api/`, `pywiim/upnp/`
- Logical grouping: Related functionality grouped together
- Public API: Clean exports in `__init__.py`
- Mixin pattern: Well-organized API mixins

**Documentation Structure:**
- User docs: Organized in `docs/` directory
- Design docs: Comprehensive design documentation
- Clear separation: User-facing vs developer-facing docs

**Test Structure:**
- Unit tests: Separate from integration tests
- Fixtures: Centralized in `conftest.py`
- Documentation: Test README explains structure

**Tooling:**
- CLI tools: Organized in `pywiim/cli/`, properly configured in `pyproject.toml`
- Code quality: Pre-commit hooks, Makefile
- Type hints: PEP 561 support (`py.typed`)

**⚠️ Areas for Improvement**

**File Size Compliance:**

Some files exceed recommended limits:

| File | Lines | Limit | Status |
|------|-------|-------|--------|
| `api/base.py` | 988 | 600 (hard) | ❌ **Exceeds hard limit** |
| `upnp/eventer.py` | 618 | 600 (hard) | ❌ **Exceeds hard limit** |
| `upnp/client.py` | 594 | 600 (hard) | ⚠️ **Close to limit** |
| `state.py` | 558 | 400 (soft) | ⚠️ **Exceeds soft limit** |
| `capabilities.py` | 500 | 400 (soft) | ⚠️ **Exceeds soft limit** |

**Recommendations:**
- `api/base.py`: Consider splitting transport layer from client logic
- `upnp/eventer.py`: Could extract event parsing to separate module
- `state.py`: Consider splitting synchronization from state models
- `capabilities.py`: Could split detection from registry

**Note**: Some files may be acceptable if they're cohesive and difficult to split. Document justification if keeping as-is.

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

### File Size Limits
- **Soft Limit**: 400 lines of code (LOC)
- **Hard Limit**: 600 LOC
- **Exceeding Hard Limit**: Requires `# pragma: allow-long-file <issue>` and justification

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

### Coverage Goals

**Target Coverage Levels:**
- **Overall Coverage:** 85%+ (aim for 90%+)
- **Core Modules:** 95%+ (client, base API, models, exceptions)
- **API Mixins:** 85%+ (all API methods)
- **Utilities:** 90%+ (helpers, normalization, parsing)
- **CLI Tools:** 70%+ (lower priority, integration-focused)

**Coverage Exclusions:**

**Acceptable to Exclude:**
- CLI entry points (`if __name__ == "__main__"`)
- Deprecated code paths
- Platform-specific code that can't be tested
- Integration test fixtures

**Use Coverage Comments:**
```python
def some_function():
    # pragma: no cover - CLI entry point
    if __name__ == "__main__":
        main()
```

### Test Execution Strategy

**Running Tests**

```bash
# Run all unit tests (fast)
pytest tests/unit/ -v

# Run all tests with coverage
pytest tests/unit/ --cov=pywiim --cov-report=html --cov-report=term

# Run integration tests (requires device)
WIIM_TEST_DEVICE=192.168.1.100 pytest tests/integration/ -v

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

**Recommended CI Strategy:**
1. **Unit Tests** - Run on every commit (fast, no external dependencies)
2. **Integration Tests** - Run on PRs and nightly builds (requires device)
3. **Coverage Reports** - Generate and track coverage trends
4. **Linting** - Run ruff, mypy, black checks

**Example GitHub Actions:**
```yaml
# Run unit tests on every push
- name: Run unit tests
  run: pytest tests/unit/ --cov=pywiim --cov-report=xml

# Run integration tests on schedule or manual trigger
- name: Run integration tests
  env:
    WIIM_TEST_DEVICE: ${{ secrets.WIIM_TEST_DEVICE }}
  run: pytest tests/integration/ -v
```

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

### Pre-Release Real Device Testing

**Current State**

**✅ What We Have:**
- **Comprehensive unit tests** with mocks - run in CI/CD for every commit
- **Minimal integration tests** (`test_real_device.py`) - 4 basic smoke tests
- **Comprehensive multiroom tests** (`test_multiroom_group.py`) - thorough group testing
- **CLI verification tool** (`wiim-verify`) - comprehensive but manual
- **Various test scripts** - for specific features (playback, shuffle/repeat, etc.)

**⚠️ Gaps:**
- **No Player-level integration tests** - only client-level basic tests
- **No playback control integration tests** - play/pause/shuffle/repeat only in scripts
- **No volume/audio integration tests** - only in `wiim-verify` CLI
- **No source switching integration tests**
- **No EQ/preset integration tests**
- **No state management/caching integration tests**
- **Integration tests not part of release process** - only unit tests run

**Strategy: Two-Tier Approach**

1. **Core Integration Tests** (always run if device available)
   - Expand `test_real_device.py` with essential Player-level tests
   - Keep fast, non-destructive tests
   - Run automatically if `WIIM_TEST_DEVICE` is set

2. **Pre-Release Integration Tests** (optional, before releases)
   - Comprehensive test suite covering all major features
   - Can be run manually before important releases
   - More thorough than core tests, but still automated

**Proposed Test Expansion**

**1. Core Integration Tests (`test_real_device.py`)**

Add these essential tests that should run if a device is available:

```python
# Player-level basic operations
- test_player_initialization
- test_player_refresh
- test_player_properties_access

# Playback controls (non-destructive)
- test_playback_state_read
- test_shuffle_repeat_state_read

# Volume controls (safe - low volume only)
- test_volume_read
- test_mute_read
- test_volume_set_safe (max 10%)

# Source and audio
- test_source_list
- test_audio_output_modes
- test_current_source_read

# State management
- test_state_caching
- test_state_refresh
```

**2. Pre-Release Integration Tests (`test_prerelease.py`)**

Create a new comprehensive test suite for pre-release validation:

```python
# Comprehensive playback testing
- test_playback_controls_full (play/pause/stop/resume)
- test_shuffle_controls_full (with state preservation)
- test_repeat_controls_full (all modes, state preservation)
- test_next_previous_track

# Volume and audio
- test_volume_controls_full (with restoration)
- test_mute_controls_full
- test_audio_output_switching

# Source management
- test_source_switching (if multiple sources available)
- test_source_specific_features

# EQ and presets (if supported)
- test_eq_presets
- test_eq_custom_settings
- test_preset_playback

# State management
- test_state_synchronization
- test_cache_consistency
- test_upnp_event_integration

# Error handling
- test_invalid_commands
- test_network_timeout_handling
- test_device_unavailable_handling
```

**When to Run Pre-Release Tests**

**Always Run Before:**
- **Major releases** (X.0.0) - breaking changes
- **Minor releases** (X.Y.0) - new features
- **After significant refactoring** - even for patch releases

**Optional Before:**
- **Patch releases** - if they touch core functionality
- **Regular development** - when working on Player/state management

**Not Required:**
- **Documentation-only releases**
- **Dependency updates** (unless major)
- **Minor bug fixes** (unless in critical paths)

**Test Organization**

**Markers for Test Selection:**

```python
@pytest.mark.integration          # All integration tests
@pytest.mark.integration.core     # Core tests (fast, safe)
@pytest.mark.integration.prerelease  # Pre-release tests (comprehensive)
@pytest.mark.integration.slow     # Slow tests (state changes, delays)
@pytest.mark.integration.destructive  # Tests that change device state
```

**Running Tests:**

```bash
# Core integration tests only (fast)
pytest tests/integration/ -m "integration.core" -v

# Pre-release tests (comprehensive)
pytest tests/integration/ -m "integration.prerelease" -v

# All integration tests
pytest tests/integration/ -v

# Skip slow/destructive tests
pytest tests/integration/ -m "not slow and not destructive" -v
```

**Safety Features**

All integration tests should:

1. **Save initial state** before making changes
2. **Restore state** after tests (in finally blocks)
3. **Use safe volumes** (max 10-20% during testing)
4. **Skip gracefully** if device unavailable
5. **Handle errors** without leaving device in bad state
6. **Log operations** for debugging

**Example: Expanded Core Test**

```python
@pytest.mark.integration
@pytest.mark.integration.core
@pytest.mark.asyncio
async def test_player_volume_controls_safe(real_device_client, integration_test_marker):
    """Test volume controls with safe limits and state restoration."""
    from pywiim.player import Player
    
    player = Player(real_device_client)
    await player.refresh()
    
    # Save initial state
    initial_volume = await player.get_volume()
    initial_mute = await player.get_muted()
    
    try:
        # Test volume read
        volume = await player.get_volume()
        assert volume is not None
        assert 0.0 <= volume <= 1.0
        
        # Test safe volume change (max 10%)
        safe_volume = min(0.10, volume + 0.05) if volume < 0.10 else 0.10
        await player.set_volume(safe_volume)
        await asyncio.sleep(0.5)
        
        new_volume = await player.get_volume()
        assert abs(new_volume - safe_volume) < 0.05
        
        # Test mute toggle
        await player.set_mute(True)
        await asyncio.sleep(0.5)
        assert await player.get_muted() is True
        
        await player.set_mute(False)
        await asyncio.sleep(0.5)
        assert await player.get_muted() is False
        
    finally:
        # Restore initial state
        await player.set_volume(initial_volume)
        await player.set_mute(initial_mute)
        await asyncio.sleep(0.5)
```

### Testing Against Real Devices

**Quick Test Script**

We've included a simple test script to quickly test your devices:

```bash
# Test a single device
python scripts/test_my_devices.py 192.168.1.100

# Test multiple devices
python scripts/test_my_devices.py 192.168.1.100 192.168.1.101
```

This script will:
- Connect to each device
- Get device information
- Detect capabilities
- Test basic features
- Show a summary

**Full Diagnostic Tool**

For comprehensive device analysis:

```bash
# Run full diagnostics (using console script)
wiim-diagnostics 192.168.1.100

# Or using Python module
python -m pywiim.cli.diagnostics 192.168.1.100

# Save report to file
wiim-diagnostics 192.168.1.100 --output device-report.json

# Verbose output
wiim-diagnostics 192.168.1.100 --verbose
```

**Raw HTTP with `curl`**

For manual `httpapi.asp` probes on your LAN (read-only checks, firmware diffs, research), see **[docs/testing/CURL_HTTPAPI.md](../testing/CURL_HTTPAPI.md)**.

**Integration Tests**

Run the full integration test suite:

```bash
# Set device IP
export WIIM_TEST_DEVICE=192.168.1.100

# Run all integration tests
pytest tests/integration/ -v

# Run specific test
pytest tests/integration/test_real_device.py::TestRealDevice::test_device_connection -v

# Skip slow tests (ones that change device state)
pytest tests/integration/ -v -m "not slow"
```

**Finding Your Device IP**

**Method 1: Router Admin Panel**
- Log into your router's admin panel
- Look for connected devices
- Find your WiiM device by name

**Method 2: Network Scan**
```bash
# Using nmap (if installed)
nmap -sn 192.168.1.0/24 | grep -B 2 "WiiM"

# Or use the discovery example in docs/EXAMPLES.md
```

**Method 3: Device Display**
- Some WiiM devices show their IP on the display
- Check the device's network settings menu

**Testing Different Device Types**

**WiiM Devices (Pro, Mini, Amp, Ultra)**
```bash
# Standard HTTP
python scripts/test_my_devices.py 192.168.1.100

# Should work with default settings
```

**Audio Pro Devices**
```bash
# May require HTTPS on port 4443
wiim-diagnostics 192.168.1.100 --port 4443

# Or test with HTTPS
python -c "
import asyncio
from pywiim import WiiMClient

async def test():
    client = WiiMClient('192.168.1.100', port=4443)
    info = await client.get_device_info_model()
    print(f'Device: {info.name}')
    await client.close()

asyncio.run(test())
"
```

**Arylic Devices**
```bash
# Should work with standard HTTP
python scripts/test_my_devices.py 192.168.1.100
```

**Common Issues**

**Connection Timeout**

If you get timeout errors:
- Verify the IP address is correct
- Check device is on the same network
- Try increasing timeout:
  ```python
  client = WiiMClient("192.168.1.100", timeout=10.0)
  ```

**HTTPS Required**

Some devices require HTTPS:
```python
client = WiiMClient("192.168.1.100", port=443)
```

**Port Issues**

Try different ports:
- 80 (HTTP)
- 443 (HTTPS)
- 4443 (Audio Pro MkII HTTPS)
- 8443 (Alternative HTTPS)

**Test Checklist**

When testing a new device, check:

- [ ] Device info retrieval
- [ ] Capability detection
- [ ] Player status
- [ ] Volume control
- [ ] Playback control (play/pause/stop)
- [ ] Presets (if supported)
- [ ] EQ (if supported)
- [ ] Multiroom (if supported)
- [ ] Bluetooth (if supported)
- [ ] Audio settings (if supported)

**Sharing Test Results**

If you find issues or want to share test results:

1. Run diagnostics:
   ```bash
   wiim-diagnostics <device_ip> --output report.json
   ```

2. Share the `report.json` file

3. Include:
   - Device model
   - Firmware version
   - What worked
   - What didn't work
   - Error messages

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
