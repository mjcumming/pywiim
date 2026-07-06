"""Audio configuration - EQ, output modes, LED, etc."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from ..api.constants import API_ENDPOINT_GET_CHANNEL_BALANCE
from ..capabilities import _channel_balance_probe_success
from ..exceptions import WiiMError
from ..normalize import source_rename_reverse

if TYPE_CHECKING:
    from . import Player

_LOGGER = logging.getLogger(__name__)


class AudioConfiguration:
    """Manages audio configuration."""

    def __init__(self, player: Player) -> None:
        """Initialize audio configuration.

        Args:
            player: Parent Player instance.
        """
        self.player = player

    async def set_source(self, source: str) -> None:
        """Set audio input source.

        Args:
            source: Source to switch to. Accepts various formats (e.g., "Line In", "Line-in", "line_in", "linein")
                   and normalizes to API format (lowercase with hyphens for multi-word sources).
        """
        # Normalize source name to API format (lowercase with hyphens for multi-word)
        # Handles variations: "Line In", "Line-in", "line_in", "linein" → "line-in"
        normalized_source = self._normalize_source_for_api(source)
        source_id = self._source_id_for_capabilities(source)

        # Capability-driven blocklist for device-specific switchmode quirks.
        blocked_ids = self._get_non_selectable_source_ids()
        if source_id in blocked_ids:
            raise ValueError(
                f"Source '{source}' is not directly selectable on this device " f"(blocked source id: {source_id})"
            )

        # Call API (raises on failure)
        await self.player.client.set_source(normalized_source)

        # Verify switch if device reports source promptly.
        # Some firmwares return "OK" for switchmode but do nothing.
        if not await self._verify_source_switch(normalized_source):
            raise WiiMError(f"Device acknowledged source switch to '{source}' but did not change source state.")

        # Update cached state immediately (optimistic)
        # Command verified/sent, so use normalized source for immediate UI response.
        if self.player._status_model:
            self.player._status_model.source = normalized_source

        # Update state synchronizer (for immediate property reads)
        # This ensures player.source returns the new value before the next poll
        self.player._state_synchronizer.update_from_http({"source": normalized_source})

        # Track when source was set for preserving optimistic update during refresh
        # Device status endpoint may return stale source data after a switch
        self.player._last_source_set_time = time.time()

        # Call callback to notify state change
        if self.player._on_state_changed:
            self.player._on_state_changed()

    def _normalize_source_for_api(self, source: str) -> str:
        """Normalize source name to API format for switchmode command.

        The WiiM/LinkPlay API's switchmode command expects specific formats:
        - Multi-word sources use hyphens: "line-in" (NOT "line_in")
        - Single-word sources are lowercase: "wifi", "bluetooth", "optical"

        Highly resilient: accepts "Line In", "line_in", "line-in", "linein" → "line-in".

        Args:
            source: Source name in any format (from UI or available_sources)

        Returns:
            Normalized source name for API (format expected by switchmode command)
        """
        if not source:
            return source

        source_lower = source.lower().strip()

        # Resolve a user custom label (getModeRename) back to its canonical id so
        # selecting the renamed source (e.g. "TV") still switches the right input.
        # Canonical/normalized names below keep working, so existing automations
        # that pass "Optical In" / "optical" are unaffected.
        rename_map = self.player.client.capabilities.get("source_rename") if self.player.client else None
        resolved_id = source_rename_reverse(rename_map).get(source_lower)
        if resolved_id:
            source = resolved_id
            source_lower = resolved_id.lower()

        # Handle "Network" display name mapping back to "wifi"
        if source_lower == "network":
            return "wifi"

        # Normalize separators - replace underscores and spaces with hyphens for comparison
        normalized = source_lower.replace("_", "-").replace(" ", "-")

        # Handle known source name mappings to API format
        # The WiiM API switchmode command expects these specific strings
        source_mappings = {
            # Line In variations → "line-in" (hyphenated)
            "linein": "line-in",
            "line-in": "line-in",
            # Line In 2 variations
            "linein-2": "line-in-2",
            "line-in-2": "line-in-2",
            "linein2": "line-in-2",
            # Coaxial variations
            "coax": "coaxial",
            "coaxial": "coaxial",
            "coaxial-in": "coaxial",
            "coaxial_in": "coaxial",
            # Optical variations
            "optical": "optical",
            "optical-in": "optical",
            "optical_in": "optical",
            # Phono variations
            "phono": "phono",
            "phono-in": "phono",
            "phono_in": "phono",
            # HDMI variations
            "hdmi": "hdmi",
            "hdmi-in": "hdmi",
            "hdmi_in": "hdmi",
            "hdmi-arc": "hdmi",
            # USB variations
            "usb": "usb",
            "usb-in": "usb",
            "usb_in": "usb",
            "usb-audio": "usb",
            "usb_audio": "usb",
            # WiFi/Ethernet variations
            "wifi": "wifi",
            "wi-fi": "wifi",
            "wi_fi": "wifi",
            "ethernet": "wifi",  # Ethernet maps to WiFi mode
            "network": "wifi",
            # Single-word sources (no change needed)
            "bluetooth": "bluetooth",
            "aux": "line-in",  # Map "Aux" to "line-in" (standard LinkPlay)
            "aux-in": "line-in",
            # RCA variations (Audio Pro specific)
            "rca": "RCA",
            "rca-in": "RCA",
            # Streaming services (pass through as-is)
            "airplay": "airplay",
            "dlna": "dlna",
            "spotify": "spotify",
            "amazon": "amazon",
            "tidal": "tidal",
            "qobuz": "qobuz",
            "deezer": "deezer",
        }

        # Check if we have a direct mapping (use normalized form for lookup)
        if normalized in source_mappings:
            return source_mappings[normalized]

        # Smart fallback: check device's own input_list if available
        # This handles cases where the device uses underscores (line_in) or
        # other non-standard variations that we didn't hardcode.
        if self.player._device_info and self.player._device_info.input_list:
            # Create a simplified version of the input source for comparison
            source_simple = "".join(c for c in source_lower if c.isalnum())
            for raw_input in self.player._device_info.input_list:
                if not raw_input:
                    continue
                # Normalize raw input from device list for comparison
                # "line_in" -> "linein", "Line In" -> "linein"
                device_simple = "".join(c for c in raw_input.lower() if c.isalnum())
                if source_simple == device_simple:
                    _LOGGER.debug("Mapping source '%s' to device-reported '%s'", source, raw_input)
                    return raw_input

        # Also check the original lowercase form (handles "linein" without separators)
        if source_lower in source_mappings:
            return source_mappings[source_lower]

        # If it contains "line" and "in", it's likely line-in
        if "line" in source_lower and "in" in source_lower:
            if "2" in source_lower:
                return "line-in-2"
            return "line-in"

        # For unknown sources, return lowercase with hyphens (safer default for API)
        return normalized

    def _get_non_selectable_source_ids(self) -> set[str]:
        """Get capability-driven non-selectable source IDs."""
        raw_blocked = self.player.client.capabilities.get("non_selectable_source_ids", [])
        if not isinstance(raw_blocked, list):
            return set()
        return {str(item).strip().lower() for item in raw_blocked if str(item).strip()}

    def _source_id_for_capabilities(self, source: str) -> str:
        """Convert user source string to canonical source ID for capability checks."""
        source_lower = source.strip().lower()
        normalized_source = self._normalize_source_for_api(source)
        normalized_lower = normalized_source.strip().lower()

        if source_lower in ("network", "wifi", "wi-fi", "ethernet") or normalized_lower == "wifi":
            return "network"
        if normalized_lower in ("line-in", "line_in", "linein"):
            return "line_in"
        if normalized_lower in ("line-in-2", "line_in_2", "linein2"):
            return "line_in_2"
        if normalized_lower in ("optical", "optical-in", "optical_in"):
            return "optical"
        if normalized_lower in ("coaxial", "coax", "coaxial-in", "coaxial_in"):
            return "coaxial"
        if normalized_lower in ("rca",):
            return "rca"
        if normalized_lower in ("aux", "aux-in", "aux_in"):
            return "aux"
        return normalized_lower.replace("-", "_")

    async def _verify_source_switch(self, expected_source: str) -> bool:
        """Verify switchmode by checking fresh status for source change.

        Returns:
            True when verified or inconclusive; False only on confirmed no-op.
        """
        expected = self._source_id_for_capabilities(expected_source)
        # Short retries keep this fast while catching silent no-op responses.
        for _ in range(3):
            await asyncio.sleep(0.3)
            try:
                status = await self.player.client.get_player_status_model()
            except Exception as err:
                _LOGGER.debug("Source switch verification skipped (status fetch failed): %s", err)
                return True
            observed_raw = status.source if status else None
            if not observed_raw:
                # Inconclusive: keep optimistic behavior.
                return True
            observed = self._source_id_for_capabilities(observed_raw)
            if observed == expected:
                return True
        return False

    async def set_audio_output_mode(self, mode: str | int) -> None:
        """Set audio output mode by friendly name or integer.

        Args:
            mode: Either a friendly name string or mode integer (0-4).
        """
        # Call API (raises on failure)
        await self.player.client.set_audio_output_mode(mode)

        # Refresh to update audio output status cache
        # Use full=True to ensure audio output status is fetched
        await self.player.refresh(full=True)

        # Call callback to notify state change (audio output status changed)
        if self.player._on_state_changed:
            self.player._on_state_changed()

    async def select_output(self, output: str) -> None:
        """Select an output by name (hardware mode or specific BT device).

        This method handles both hardware output modes and specific Bluetooth devices:
        - Hardware modes: "Line Out", "Optical Out", "Coax Out", "Headphone Out"
        - BT devices: "BT: Device Name" (must be already paired)
        - "Bluetooth Out": Activates last connected BT device

        When selecting a BT device:
        1. Connects to the specific device (this automatically activates BT output mode)

        Args:
            output: Output name from available_outputs list

        Raises:
            ValueError: If output name is not recognized or device not paired

        Example:
            # Select hardware output
            await player.audio.select_output("Optical Out")
            await player.audio.select_output("Headphone Out")

            # Select specific BT device
            await player.audio.select_output("BT: Sony Speaker")
        """
        # Check if it's a Bluetooth device selection
        if output.startswith("BT: "):
            device_name = output[4:]  # Remove "BT: " prefix

            # Find the device in paired devices
            bt_devices = self.player._properties.bluetooth_output_devices
            matching_device = None
            for device in bt_devices:
                if device["name"] == device_name:
                    matching_device = device
                    break

            if not matching_device:
                raise ValueError(
                    f"Bluetooth device '{device_name}' not found in paired devices. "
                    f"Available BT devices: {[d['name'] for d in bt_devices]}"
                )

            # Connect to the specific device (this automatically activates BT output mode)
            await self.player.connect_bluetooth_device(matching_device["mac"])

        elif output.lower() in ("bluetooth out", "bluetooth"):
            # Generic Bluetooth Out - connect to the last connected device
            bt_devices = self.player._properties.bluetooth_output_devices
            if not bt_devices:
                raise ValueError("No paired Bluetooth devices found. Pair a device first.")

            # Find the last connected device (ct=1) or first in list
            last_device = next((d for d in bt_devices if d.get("connected")), bt_devices[0])
            await self.player.connect_bluetooth_device(last_device["mac"])

        else:
            # It's a hardware output mode (Line Out, Optical Out, Coax Out, Headphone Out, etc.)
            # If Bluetooth is currently active, disconnect it first
            if self.player.is_bluetooth_output_active:
                try:
                    await self.player.disconnect_bluetooth_device()
                except Exception:
                    # If disconnect fails, continue anyway - the hardware mode change might still work
                    pass

            # Set the hardware output mode
            await self.set_audio_output_mode(output)

    async def set_led(self, enabled: bool) -> None:
        """Set LED on/off state.

        Args:
            enabled: True to enable LED, False to disable.
        """
        await self.player.client.set_led(enabled)

    async def set_led_brightness(self, brightness: int) -> None:
        """Set LED brightness level.

        Args:
            brightness: Brightness level from 0 to 100.
        """
        if not 0 <= brightness <= 100:
            raise ValueError(f"Brightness must be between 0 and 100, got {brightness}")
        await self.player.client.set_led_brightness(brightness)

    async def get_channel_balance(self) -> float | None:
        """Read stereo channel balance from the device (HTTP getChannelBalance).

        Returns:
            Balance -1.0 (left) to 1.0 (right), or None if unsupported or unreadable.

        Does not update the player cache — use ``Player.get_channel_balance()`` for that.
        """
        if not self.player.client.capabilities.get("supports_channel_balance", False):
            return None
        try:
            response = await self.player.client._request(API_ENDPOINT_GET_CHANNEL_BALANCE)
            if not _channel_balance_probe_success(response):
                return None
            val = response.parsed if response.parsed is not None else response.raw
            if isinstance(val, bool):
                return None
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                return float(val.strip())
            return None
        except (WiiMError, TypeError, ValueError) as err:
            _LOGGER.debug("get_channel_balance failed for %s: %s", self.player.host, err)
            return None

    async def set_channel_balance(self, balance: float) -> None:
        """Set channel balance (left/right stereo balance).

        Args:
            balance: Balance value from -1.0 to 1.0.
        """
        if not -1.0 <= balance <= 1.0:
            raise ValueError(f"Balance must be between -1.0 and 1.0, got {balance}")
        await self.player.client.set_channel_balance(balance)
        self.player._channel_balance = balance
        if self.player._on_state_changed:
            self.player._on_state_changed()

    async def set_eq_preset(self, preset: str) -> None:
        """Set equalizer preset or disable EQ.

        Args:
            preset: Preset name. Can be any case (e.g., "jazz", "Jazz", "JAZZ")
                   or display name from get_eq_presets() (e.g., "Jazz").
                   Special value "Off" disables EQ entirely.
                   The method normalizes the preset name internally.
        """
        import asyncio
        import time

        # Handle "Off" - disable EQ instead of setting a preset
        if preset.lower() == "off":
            await self.set_eq_enabled(False)
            return

        # Resolve against cached device presets first so dynamic/custom labels work.
        available_presets = [item for item in self.player.eq_presets if item and item != "Off"]
        normalized_preset = self.player.client._normalize_eq_preset_name(
            preset,
            available_presets=available_presets or None,
        )

        # Ensure EQ is enabled before setting a preset
        # (user may be switching from "Off" to a preset)
        if self.player._eq_enabled is False:
            await self.player.client.set_eq_enabled(True)
            self.player._eq_enabled = True

        # Call API (raises on failure)
        await self.player.client.set_eq_preset(
            preset,
            available_presets=available_presets or None,
        )

        # Update cached state immediately (optimistic) with normalized preset
        if self.player._status_model:
            self.player._status_model.eq_preset = normalized_preset

        # Track when EQ was set for preserving optimistic update during refresh
        # Device status endpoint returns stale EQ data for many seconds
        self.player._last_eq_preset_set_time = time.time()

        # Verify by querying the authoritative EQ endpoint after a brief delay
        # This ensures we have the correct value even if status endpoint is stale
        try:
            await asyncio.sleep(0.3)  # Brief delay for device to apply
            eq_data = await self.player.client.get_eq()
            verified_preset = eq_data.get("Name") or eq_data.get("name")
            if verified_preset and self.player._status_model:
                self.player._status_model.eq_preset = verified_preset
                _LOGGER.debug("EQ preset verified: %s", verified_preset)
        except Exception as err:
            # If verification fails, keep the optimistic update
            _LOGGER.debug("EQ verification failed, keeping optimistic value: %s", err)

        # Call callback to notify state change
        if self.player._on_state_changed:
            self.player._on_state_changed()

    async def set_eq_custom(self, eq_values: list[int]) -> None:
        """Set custom 10-band equalizer values.

        Args:
            eq_values: List of exactly 10 integer values.
        """
        # Call API (raises on failure)
        await self.player.client.set_eq_custom(eq_values)

        # Call callback to notify state change (EQ values changed)
        if self.player._on_state_changed:
            self.player._on_state_changed()

    async def set_eq_enabled(self, enabled: bool) -> None:
        """Enable or disable the equalizer.

        Args:
            enabled: True to enable EQ, False to disable.
        """
        # Call API (raises on failure)
        await self.player.client.set_eq_enabled(enabled)

        # Update cached state immediately (optimistic)
        self.player._eq_enabled = enabled

        # Call callback to notify state change (EQ enabled/disabled)
        if self.player._on_state_changed:
            self.player._on_state_changed()

    async def get_eq(self) -> dict[str, Any]:
        """Get current equalizer band values."""
        return await self.player.client.get_eq()

    async def get_eq_presets(self) -> list[str]:
        """Get list of available equalizer presets."""
        return await self.player.client.get_eq_presets()

    async def get_eq_status(self) -> bool:
        """Get current equalizer enabled status."""
        return await self.player.client.get_eq_status()

    async def get_multiroom_status(self) -> dict[str, Any]:
        """Get multiroom group status information."""
        return await self.player.client.get_multiroom_status()

    async def get_audio_output_status(self) -> dict[str, Any] | None:
        """Get current audio output status.

        Fetches audio output status from the device and updates the player's
        internal cache so that audio_output_mode property works correctly.

        Returns:
            Dict with audio output info (hardware, source, etc.), or None if not supported.
        """
        status = await self.player.client.get_audio_output_status()
        # Update player's internal cache so audio_output_mode property works
        self.player._audio_output_status = status
        return status

    async def get_meta_info(self) -> dict[str, Any]:
        """Get detailed metadata information about current track."""
        return await self.player.client.get_meta_info()
