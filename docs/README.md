# Documentation

This directory contains all project documentation, organized by purpose and audience.

## Structure

### 📖 [User Documentation](user/)
Documentation for end users of the library:
- **QUICK_START.md** - Get started quickly
- **EXAMPLES.md** - Code examples
- **DISCOVERY.md** - Device discovery guide
- **DIAGNOSTICS.md** - Diagnostic tool guide
- **REQUIREMENTS.md** - Requirements specification

### 🏗️ [Design & Architecture](design/)
Design documentation, architecture decisions, and patterns:
- **ARCHITECTURE.md** - System architecture overview
- **ARCHITECTURE_DATA_FLOW.md** - State synchronization, data flow, and play state identification
- **DESIGN_PRINCIPLES.md** - Design principles, goals, and patterns
- **DEVICE_PROFILES.md** - Device profiles, vendor detection, endpoint abstraction, and device compatibility
- **LESSONS_LEARNED.md** - Key lessons from HA integration
- **API_DESIGN_PATTERNS.md** - API design patterns and defensive programming
- **UPNP_INTEGRATION.md** - UPnP integration patterns, architecture, and health tracking
- **LINKPLAY_ARCHITECTURE.md** - In-depth analysis of LinkPlay/WiiM streaming architecture and shuffle/repeat support
- **SOURCE_ENUMERATION_VS_SELECTION.md** - Source system documentation
- **OPERATION_PATTERNS.md** - Operation implementation patterns (trust API, handle preconditions)
- **PROTOCOL_DETECTION.md** - Protocol/port detection strategy

### 💻 [Development Guides](development/)
Guides for developers working on the project:
- **DEVELOPMENT.md** - Complete development guide (setup, standards, testing, project structure)

### 🧪 [Testing](testing/)
Real hardware and manual API probes:
- **REAL-DEVICE-TESTING.md** - Unified test runner, tiered suites, `WIIM_TEST_DEVICE`
- **CURL_HTTPAPI.md** - `curl` against local devices (HTTPS, read-only examples, DLNA cast research notes)

### 🔌 [Integration Guides](integration/)
Guides for integrating the library with frameworks:
- **HA_INTEGRATION.md** - Home Assistant integration guide (polling, session management, UPnP)
- **API_REFERENCE.md** - Complete API reference


## Quick Navigation

- **New to the project?** Start with [QUICK_START.md](user/QUICK_START.md)
- **Want to understand the design?** Read [ARCHITECTURE.md](design/ARCHITECTURE.md) and [ARCHITECTURE_DATA_FLOW.md](design/ARCHITECTURE_DATA_FLOW.md)
- **Setting up development?** See [DEVELOPMENT.md](development/DEVELOPMENT.md)
- **Probing devices with `curl`?** See [CURL_HTTPAPI.md](testing/CURL_HTTPAPI.md)
- **Integrating with Home Assistant?** Check [HA_INTEGRATION.md](integration/HA_INTEGRATION.md)
- **Looking for device compatibility?** See [DEVICE_PROFILES.md](design/DEVICE_PROFILES.md)
- **Understanding state synchronization?** See [ARCHITECTURE_DATA_FLOW.md](design/ARCHITECTURE_DATA_FLOW.md)
- **UPnP integration details?** See [UPNP_INTEGRATION.md](design/UPNP_INTEGRATION.md)

## Documentation Standards

- **User docs**: Clear, example-driven, assume minimal prior knowledge
- **Design docs**: Technical depth, explain decisions and trade-offs
- **Development docs**: Practical guides for contributors
- **Working docs**: Temporary analysis and discussions

## Contributing to Documentation

When adding new documentation:
1. Determine the appropriate category (user/design/development/integration)
2. Follow existing documentation style
3. Update this README if adding new major sections
4. Follow naming conventions: Use UPPER_SNAKE_CASE for file names

## Documentation Organization

This documentation is organized by purpose and audience:

- **User Documentation** (`user/`): End-user guides, API reference, examples, and tool documentation
- **Design Documentation** (`design/`): Architecture decisions, design patterns, and technical deep-dives
- **Development Guides** (`development/`): Setup guides, standards, and practices for contributors
- **Integration Guides** (`integration/`): Framework-specific integration documentation

