# ADR 005: LED Indicator and Display APIs

## Status
Accepted - 2026-03-10

## Context
WiiM and LinkPlay devices expose different hardware for status indication and screens:

- **LED Indicator**: A small status light (on/off). Controlled by different HTTP commands across vendors: standard LinkPlay `setLED`, or `LED_SWITCH_SET` (used by WiiM Pro and supported on some Arylic devices). Many devices do not expose a read-back API; state must be tracked by the integration (shadow state).
- **Display**: An LCD/screen (e.g. WiiM Ultra) with on/off and optional brightness, controlled by `setLightOperationBrightConfig`. Separate from the status LED.

We need a clear, consistent API and capability model so integrations (e.g. Home Assistant) can expose LED and Display controls without device-specific branching, following the same pattern as subwoofer and EQ.

## Decision

We expose **two distinct capability areas** and **player-level methods** that mirror the subwoofer/EQ pattern:

### 1. LED Indicator (on/off only)
- **Capability**: `supports_led_indicator` — True when the device supports turning the status LED on or off. Shown as `supports_led_switch` in capability dict; player exposes `supports_led_indicator` for clarity.
- **Control**: One path — `LED_SWITCH_SET`. For **WiiM** we probe at init; for **Arylic** we set capability True by vendor and **try-and-ignore**: call `LED_SWITCH_SET` and do not raise on failure.
- **Player API**: `set_led_indicator(enabled: bool)` — delegates to `client.set_led_switch(enabled)`. Integrations use this for the “LED Indicator” entity. We do **not** add a separate `set_led_enabled`; `set_led_indicator` is the single on/off method for the indicator.
- **Read**: We implement a read path. Try device read (e.g. getStatusEx fields, or vendor-specific getters such as Arylic `getMCUASCIICmd:LED`). If read fails or no API exists yet, **assume on** and log a warning. We do **not** persist state between sessions; during the process lifecycle we may use the last read or write value. When a device adds a read API later, we are ready to use it.
- **Legacy**: Existing `set_led` / `set_led_brightness` (setLED path) remain for devices that use them; prefer `set_led_indicator` and `supports_led_indicator` for the unified indicator control.

### 2. Display (on/off, optional brightness)
- **Capability**: `supports_display_config` — True for WiiM Ultra (model-based); no probe that changes screen state.
- **Control**: `setLightOperationBrightConfig` via `set_display_config` / `set_display_enabled` on client; **player** exposes `set_display_enabled(enabled)` and `set_display_config(...)` that delegate to client (same pattern as subwoofer).
- **Read**: Only when device includes `light_operation_bright_config` in status (e.g. future Ultra support); otherwise shadow state.

### 3. Implementation rules
- **Player methods**: LED Indicator → `set_led_indicator(enabled)`. Display → `set_display_enabled(enabled)`, `set_display_config(...)`. Both delegate to client; no duplicate logic on player.
- **Capability detection**: Arylic → set `supports_led_switch` True from vendor so we offer the control; client `set_led_switch` catches and ignores errors for Arylic. WiiM → probe `LED_SWITCH_SET` at init as today.
- **Naming in docs**: Use “LED Indicator” and “Display” consistently; capability names in code remain `supports_led_switch` and `supports_display_config`.
- **Assumption**: Devices with a display (e.g. WiiM Ultra) are assumed not to expose a separate controllable LED; we can revisit if we learn otherwise.

## Consequences
- Integrations get one clear method per feature: `set_led_indicator` and `set_display_enabled` / `set_display_config`, with capabilities `supports_led_indicator` and `supports_display_config`.
- No extra “set_led_enabled” method; `set_led_indicator` is the canonical LED Indicator on/off API.
- LED Indicator read: we always try to read; on failure we assume on and log a warning; no persistent state between restarts.
- Arylic devices get LED Indicator control without probe; failures are ignored to avoid maintainability cost.
- Display remains WiiM Ultra–only until more models are known; same pattern extends to new devices.
- Aligns with subwoofer/EQ: capability-driven, player delegates to client, docs use consistent names (LED Indicator, Display).
