"""Diagnostic tool for WiiM devices.

This module provides a comprehensive diagnostic tool that can be used to gather
device information, test endpoints, and generate reports for troubleshooting.

Usage:
    wiim-diagnostics <device_ip> [--output report.json] [--verbose]
    # or
    python -m pywiim.cli.diagnostics <device_ip> [--output report.json] [--verbose]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any

from ..client import WiiMClient
from ..exceptions import WiiMError

_LOGGER = logging.getLogger(__name__)


class DeviceDiagnostics:
    """Comprehensive diagnostic tool for WiiM devices."""

    def __init__(self, client: WiiMClient) -> None:
        """Initialize diagnostics with a WiiM client.

        Args:
            client: WiiMClient instance connected to device.
        """
        self.client = client
        self.report: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "device": {},
            "capabilities": {},
            "endpoints": {},
            "status": {},
            "debug_info": {},
            "errors": [],
            "warnings": [],
        }

    async def run_full_diagnostic(self) -> dict[str, Any]:
        """Run complete diagnostic suite.

        Returns:
            Complete diagnostic report dictionary.
        """
        print("🔍 Starting comprehensive device diagnostic...")
        print(f"   Device: {self.client.host}:{self.client.port}\n")

        # Gather device information
        await self._gather_device_info()
        await self._gather_capabilities()
        await self._gather_status()
        await self._gather_debug_info()
        await self._gather_discovered_api_info()
        await self._test_endpoints()
        await self._test_features()

        # Summary
        self.report["summary"] = self._generate_summary()

        return self.report

    async def _gather_device_info(self) -> None:
        """Gather basic device information."""
        print("📋 Gathering device information...")
        try:
            device_info = await self.client.get_device_info_model()
            self.report["device"] = {
                "uuid": device_info.uuid,
                "name": device_info.name,
                "model": device_info.model,
                "firmware": device_info.firmware,
                "mac": device_info.mac,
                "ip": device_info.ip,
                "preset_key": device_info.preset_key,
                "input_list": device_info.input_list,
            }
            print(f"   ✓ Device: {device_info.name} ({device_info.model})")
            print(f"   ✓ Firmware: {device_info.firmware}")
            print(f"   ✓ MAC: {device_info.mac}")
        except Exception as err:
            error_msg = f"Failed to get device info: {err}"
            self.report["errors"].append(error_msg)
            print(f"   ✗ {error_msg}")

    async def _gather_capabilities(self) -> None:
        """Gather device capabilities."""
        print("\n🔧 Detecting device capabilities...")
        try:
            if not self.client._capabilities_detected:
                await self.client._detect_capabilities()

            self.report["capabilities"] = self.client.capabilities.copy()

            vendor = self.client.capabilities.get("vendor", "unknown")
            is_wiim = self.client.capabilities.get("is_wiim_device", False)
            is_legacy = self.client.capabilities.get("is_legacy_device", False)
            generation = self.client.capabilities.get("audio_pro_generation", "unknown")

            print(f"   ✓ Vendor: {vendor}")
            print(f"   ✓ Type: {'WiiM' if is_wiim else 'Legacy' if is_legacy else 'Unknown'}")
            if generation != "unknown":
                print(f"   ✓ Generation: {generation}")

            # List supported features
            features = []
            for key, value in self.client.capabilities.items():
                if key.startswith("supports_") and value:
                    feature = key.replace("supports_", "").replace("_", " ")
                    features.append(feature)

            if features:
                print(f"   ✓ Supported features: {', '.join(features)}")

            # Show UPnP description.xml enrichment if available
            if self.client.capabilities.get("upnp_description_available"):
                upnp_flags = []
                if self.client.capabilities.get("upnp_has_playqueue"):
                    upnp_flags.append("PlayQueue")
                if self.client.capabilities.get("upnp_has_qplay"):
                    upnp_flags.append("QPlay")
                if self.client.capabilities.get("upnp_has_content_directory"):
                    upnp_flags.append("ContentDirectory")

                upnp_model = self.client.capabilities.get("upnp_model_name")
                upnp_name = self.client.capabilities.get("upnp_friendly_name")
                if upnp_model:
                    print(f"   ✓ UPnP model: {upnp_model}")
                if upnp_name:
                    print(f"   ✓ UPnP friendly name: {upnp_name}")
                if upnp_flags:
                    print(f"   ✓ UPnP advertised services: {', '.join(upnp_flags)}")

        except Exception as err:
            error_msg = f"Failed to detect capabilities: {err}"
            self.report["errors"].append(error_msg)
            print(f"   ✗ {error_msg}")

    async def _gather_status(self) -> None:
        """Gather current device status."""
        print("\n📊 Gathering device status...")
        try:
            status = await self.client.get_player_status()
            self.report["status"] = {
                "play_state": status.get("play_state") or status.get("state"),
                "volume": status.get("volume"),
                "mute": status.get("mute"),
                "source": status.get("source"),
                "position": status.get("position"),
                "duration": status.get("duration"),
                "title": status.get("title"),
                "artist": status.get("artist"),
                "album": status.get("album"),
            }
            print(f"   ✓ Play state: {self.report['status'].get('play_state')}")
            print(f"   ✓ Volume: {self.report['status'].get('volume')}")
            print(f"   ✓ Source: {self.report['status'].get('source')}")
        except Exception as err:
            error_msg = f"Failed to get status: {err}"
            self.report["errors"].append(error_msg)
            print(f"   ✗ {error_msg}")

    async def _gather_debug_info(self) -> None:
        """Gather device debug info (getDebugInfo) for troubleshooting."""
        print("\n🔧 Gathering debug info...")
        try:
            debug_info = await self.client.get_debug_info()
            self.report["debug_info"] = debug_info
            if debug_info:
                print(f"   ✓ getDebugInfo: {len(debug_info)} fields")
            else:
                print("   ✓ getDebugInfo: (empty)")
        except Exception as err:
            error_msg = f"Failed to get debug info: {err}"
            self.report["warnings"].append(error_msg)
            print(f"   ⚠ getDebugInfo: {err} (optional endpoint)")

    async def _gather_discovered_api_info(self) -> None:
        """Gather read-only WiiM app API payloads discovered from app traffic."""
        print("\n🔎 Probing discovered WiiM APIs...")
        discovered: dict[str, Any] = {}

        async def probe(name: str, func: Any) -> None:
            def serialize_probe_value(item: Any) -> Any:
                if hasattr(item, "model_dump"):
                    return item.model_dump()
                if is_dataclass(item) and not isinstance(item, type):
                    return asdict(item)
                return item

            try:
                value = await func()
                if hasattr(value, "model_dump") or is_dataclass(value):
                    value = serialize_probe_value(value)
                elif isinstance(value, list):
                    value = [serialize_probe_value(item) for item in value]
                discovered[name] = {
                    "supported": value is not None and value != [],
                    "value": value,
                }
                status = "OK" if discovered[name]["supported"] else "not supported / empty"
                print(f"   ✓ {name}: {status}")
            except Exception as err:
                discovered[name] = {
                    "supported": False,
                    "error": str(err),
                    "error_type": type(err).__name__,
                }
                print(f"   ⚠ {name}: {err}")

        await probe("getAudioInputEnable", self.client.get_audio_input_enable)
        await probe("getAudioInputCapbility", self.client.get_audio_input_capability)
        await probe("getModeRename", self.client.get_mode_rename)
        await probe("GetAcousticCapability", self.client.get_acoustic_capability)
        await probe("getAllRoutines", self.client.get_all_routines)
        await probe("getSoundCardModeSupportList", self.client.get_sound_card_mode_support_list)
        await probe("Eq10HP", self.client.get_graphic_eq_bands)
        await probe("Eq10HPPresetList", self.client.get_graphic_eq_preset_list)
        await probe("RoomCorrGet", self.client.get_room_correction)

        self.report["discovered_apis"] = discovered

    async def _test_endpoints(self) -> None:
        """Test various API endpoints."""
        print("\n🧪 Testing API endpoints...")

        endpoints_to_test = [
            ("getStatusEx", lambda: self.client.get_status()),
            ("getDeviceInfo", lambda: self.client.get_device_info()),
            ("getPlayerStatus", lambda: self.client.get_player_status()),
            ("getDebugInfo", lambda: self.client.get_debug_info()),
            ("getPresets", lambda: self.client.get_presets()),
            ("getEQ", lambda: self.client.get_eq()),
            ("getMultiroomStatus", lambda: self.client.get_multiroom_status()),
            ("getAudioOutputStatus", lambda: self.client.get_audio_output_status()),
            ("getTriggeroutStatus", lambda: self.client.get_trigger_out_status()),
            ("getFirmwareInfo", lambda: self.client.get_firmware_info()),
        ]

        for name, test_func in endpoints_to_test:
            try:
                result = await test_func()
                self.report["endpoints"][name] = {
                    "status": "success",
                    "result_type": type(result).__name__,
                    "has_data": bool(result),
                }
                print(f"   ✓ {name}: OK")
            except WiiMError as err:
                self.report["endpoints"][name] = {
                    "status": "error",
                    "error": str(err),
                    "error_type": type(err).__name__,
                }
                print(f"   ✗ {name}: {err}")
            except Exception as err:
                self.report["endpoints"][name] = {
                    "status": "error",
                    "error": str(err),
                    "error_type": type(err).__name__,
                }
                self.report["warnings"].append(f"Unexpected error testing {name}: {err}")
                print(f"   ⚠ {name}: {err}")

    async def _test_features(self) -> None:
        """Test specific features and capabilities."""
        print("\n🎯 Testing specific features...")

        features_to_test = [
            ("Presets", self._test_presets),
            ("EQ", self._test_eq),
            ("Multiroom", self._test_multiroom),
            ("Bluetooth", self._test_bluetooth),
            ("Audio Settings", self._test_audio_settings),
            ("Channel Balance", self._test_channel_balance),
            ("LMS Integration", self._test_lms),
            ("Source Selection", self._test_sources),
            ("Audio Output Modes", self._test_audio_output),
            ("Subwoofer", self._test_subwoofer),
            ("12V Trigger", self._test_trigger_out),
            ("LED Indicator", self._test_led_indicator),
            ("Display", self._test_display),
            ("PEQ (Advanced EQ)", self._test_peq),
            ("Graphic EQ", self._test_graphic_eq),
            ("Room Correction", self._test_room_correction),
        ]

        self.report["features"] = {}

        for name, test_func in features_to_test:
            try:
                result = await test_func()
                self.report["features"][name] = result
                status = "supported" if result.get("supported") else "not supported"
                print(f"   ✓ {name}: {status}")

                # Special handling for source selection to show ALL sources
                if name == "Source Selection" and result.get("supported"):
                    current = result.get("current_source", "None")
                    enumerable_sources = result.get("enumerable_sources", [])
                    all_selectable = result.get("all_selectable_sources", [])
                    print(f"      Current Source: {current}")
                    enumerable_str = (
                        ", ".join(enumerable_sources)
                        if enumerable_sources
                        else "None (device does not return input_list)"
                    )
                    print(f"      Enumerable Sources ({len(enumerable_sources)}): {enumerable_str}")
                    print(f"      All Selectable Sources ({len(all_selectable)}):")
                    if all_selectable:
                        # Print in columns for readability
                        for i, source in enumerate(all_selectable, 1):
                            marker = " ← current" if source == current else ""
                            print(f"         {i:2d}. {source}{marker}")
                    else:
                        print("         (none)")

                # Special handling for audio output modes to show ALL modes
                if name == "Audio Output Modes" and result.get("supported"):
                    current_mode = result.get("current_mode_name", "None")
                    available_modes = result.get("available_modes", [])
                    model = result.get("model", "Unknown")
                    bluetooth_active = result.get("bluetooth_output_active", False)
                    print(f"      Model: {model}")
                    print(f"      Current Mode: {current_mode}")
                    print(f"      Available Output Modes ({len(available_modes)}):")
                    if available_modes:
                        for i, mode in enumerate(available_modes, 1):
                            marker = " ← current" if mode == current_mode else ""
                            print(f"         {i}. {mode}{marker}")
                    else:
                        print("         (none)")
                    if bluetooth_active:
                        print("      ⚠️  Note: Bluetooth output is active (takes precedence over hardware mode)")

                # Special handling for EQ to show ALL presets
                if name == "EQ" and result.get("supported"):
                    current_preset = result.get("current_preset")
                    available_presets = result.get("available_presets", [])
                    print(f"      Current EQ Preset: {current_preset or 'Unknown'}")
                    print(f"      Available EQ Presets ({len(available_presets)}):")
                    if available_presets:
                        for i, preset in enumerate(available_presets, 1):
                            # Check if this is the current preset (handle case variations)
                            is_current = False
                            if current_preset:
                                preset_lower = str(preset).lower()
                                current_lower = str(current_preset).lower()
                                is_current = (
                                    preset_lower == current_lower
                                    or preset_lower in current_lower
                                    or current_lower in preset_lower
                                )
                            marker = " ← current" if is_current else ""
                            print(f"         {i:2d}. {preset}{marker}")
                    else:
                        print("         (none)")

                # Special handling for Presets to show ALL button presets
                if name == "Presets" and result.get("supported"):
                    presets = result.get("presets", [])
                    max_slots = result.get("max_slots", 0)
                    preset_count = result.get("preset_count", 0)
                    presets_full_data = result.get("presets_full_data", False)

                    # Show capability info
                    if presets_full_data:
                        print("      Capability: Full preset data (WiiM) - names and URLs available")
                    else:
                        print("      Capability: Count only (LinkPlay) - preset names not available")

                    print(f"      Button Presets ({preset_count}/{max_slots} slots used):")
                    if presets:
                        for preset in presets:
                            number = preset.get("number", "?")
                            preset_name = preset.get("name", "Unnamed")
                            source = preset.get("source", "Unknown")
                            url = preset.get("url", "")
                            print(f"         Preset {number}: {preset_name} (source: {source})")
                            if url and url not in ["unknow", "unknown", ""]:
                                print(f"                  URL: {url}")
                    else:
                        if presets_full_data:
                            print("         (no presets configured)")
                        else:
                            print(f"         (preset names not available - can play by number 1-{max_slots})")
                    if max_slots > 0 and preset_count < max_slots:
                        print(f"      Available slots: {max_slots - preset_count}")

                # Channel balance (stereo L/R)
                if name == "Channel Balance" and result.get("supported"):
                    print(f"      Current balance: {result.get('balance', 'Unknown')} (-1=left … +1=right)")

                # Special handling for Subwoofer to show settings
                if name == "Subwoofer" and result.get("supported"):
                    print(f"      Enabled: {result.get('enabled', 'Unknown')}")
                    print(f"      Crossover: {result.get('crossover_hz', 'Unknown')} Hz")
                    print(f"      Phase: {result.get('phase_degrees', 'Unknown')}°")
                    print(f"      Level: {result.get('level_db', 'Unknown')} dB")
                    print(f"      Delay: {result.get('delay_ms', 'Unknown')} ms")
                    print(f"      Bass to Mains: {result.get('bass_to_mains', 'Unknown')}")
                    print(f"      Filter Bypassed: {result.get('filter_bypassed', 'Unknown')}")

                # Special handling for 12V Trigger
                if name == "12V Trigger" and result.get("supported"):
                    state = result.get("state")
                    state_str = "ON" if state else "OFF" if state is False else "Unknown"
                    print(f"      State: {state_str}")

                # Special handling for PEQ (Advanced EQ)
                if name == "PEQ (Advanced EQ)" and result.get("supported"):
                    custom = result.get("custom_presets", [])
                    preset = result.get("preset_names", [])
                    print(f"      Custom presets: {len(custom)}")
                    if custom:
                        for p in custom[:15]:
                            print(f"         - {p}")
                        if len(custom) > 15:
                            print(f"         ... and {len(custom) - 15} more")
                    print(f"      Built-in presets: {len(preset)}")
                    if preset:
                        for p in preset[:10]:
                            print(f"         - {p}")
                        if len(preset) > 10:
                            print(f"         ... and {len(preset) - 10} more")

                # Special handling for Graphic EQ
                if name == "Graphic EQ" and result.get("supported"):
                    print(f"      Current preset: {result.get('name') or 'Unknown'}")
                    print(f"      Enabled: {result.get('enabled')}")
                    print(f"      Bands: {result.get('band_count', 0)}")
                    preset = result.get("preset_names", [])
                    print(f"      Built-in presets: {len(preset)}")

                # Special handling for Room Correction
                if name == "Room Correction" and result.get("supported"):
                    print(f"      Enabled: {result.get('enabled')}")
                    print(f"      Source: {result.get('source_name') or 'Unknown'}")
                    print(f"      Bands: {result.get('band_count', 0)}")
            except Exception as err:
                self.report["features"][name] = {
                    "supported": False,
                    "error": str(err),
                }
                print(f"   ✗ {name}: {err}")

    async def _test_presets(self) -> dict[str, Any]:
        """Test preset functionality."""
        try:
            presets = await self.client.get_presets()
            max_slots = await self.client.get_max_preset_slots()
            # Check if full preset data is available
            presets_full_data = self.client.capabilities.get("presets_full_data", False)
            return {
                "supported": True,
                "preset_count": len(presets),
                "max_slots": max_slots,
                "presets": presets,  # Return ALL presets
                "presets_full_data": presets_full_data,  # Whether names/URLs are available
            }
        except WiiMError:
            return {"supported": False}

    async def _test_eq(self) -> dict[str, Any]:
        """Test EQ functionality."""
        try:
            eq = await self.client.get_eq()
            presets = await self.client.get_eq_presets()
            # Get current preset name from EQ response
            current_preset = None
            if isinstance(eq, dict):
                # Try multiple field names for current preset
                current_preset = eq.get("Name") or eq.get("name") or eq.get("preset") or eq.get("EQPreset")
            return {
                "supported": True,
                "current_preset": current_preset,
                "available_presets": presets,  # Return ALL presets
            }
        except WiiMError:
            return {"supported": False}

    async def _test_multiroom(self) -> dict[str, Any]:
        """Test multiroom functionality."""
        try:
            await self.client.get_multiroom_status()  # Verify multiroom is supported
            slaves = await self.client.get_slaves()
            return {
                "supported": True,
                "is_master": self.client.is_master,
                "is_slave": self.client.is_slave,
                "slave_count": len(slaves) if slaves else 0,
            }
        except WiiMError:
            return {"supported": False}

    async def _test_bluetooth(self) -> dict[str, Any]:
        """Test Bluetooth functionality."""
        try:
            # Just check if we can get Bluetooth status (don't start scan)
            history = await self.client.get_bluetooth_history()
            return {
                "supported": True,
                "history_count": len(history) if history else 0,
            }
        except WiiMError:
            return {"supported": False}

    async def _test_audio_settings(self) -> dict[str, Any]:
        """Test audio settings functionality."""
        try:
            status = await self.client.get_audio_settings_status()
            return {
                "supported": True,
                "has_status": bool(status),
            }
        except WiiMError:
            return {"supported": False}

    async def _test_channel_balance(self) -> dict[str, Any]:
        """Stereo channel balance (WiiM getChannelBalance / setChannelBalance); gated by capability probe."""
        if not self.client.capabilities.get("supports_channel_balance", False):
            return {"supported": False, "reason": "Not supported (non-WiiM or firmware)"}
        try:
            balance = await self.client.get_channel_balance()
            return {"supported": True, "balance": balance}
        except WiiMError:
            return {"supported": False, "reason": "getChannelBalance failed"}
        except Exception as err:
            return {"supported": False, "error": str(err)}

    async def _test_lms(self) -> dict[str, Any]:
        """Test LMS integration."""
        try:
            state = await self.client.get_squeezelite_state()
            return {
                "supported": True,
                "has_state": bool(state),
            }
        except WiiMError:
            return {"supported": False}

    async def _test_audio_output(self) -> dict[str, Any]:
        """Test audio output mode capabilities."""
        try:
            if not self.client.capabilities.get("supports_audio_output", False):
                return {"supported": False}

            # Get current audio output status
            status = await self.client.get_audio_output_status()
            if not status:
                return {"supported": False}

            # Get device info for model-based mode detection
            device_info = await self.client.get_device_info_model()
            model = device_info.model or "Unknown"

            # Determine available modes (would need Player instance, but we can infer from model)
            # For diagnostics, we'll show what the device reports and model-based inference
            hardware_mode = status.get("hardware")
            bluetooth_source = status.get("source")

            # Model-based available modes (simplified - matches Player logic)
            # IMPORTANT: Order matters - check more specific models first
            model_lower = model.lower()
            if "amp ultra" in model_lower or ("ultra" in model_lower and "amp" in model_lower):
                # WiiM Amp Ultra: Has USB Out, HDMI Out (ARC)
                available_modes = ["Line Out", "USB Out", "HDMI Out"]
            elif "ultra" in model_lower:
                # WiiM Ultra (non-Amp): Has USB Out, Headphone Out, multiple digital outputs
                available_modes = ["Line Out", "Optical Out", "Coax Out", "USB Out", "Headphone Out", "HDMI Out"]
            elif "amp pro" in model_lower or ("pro" in model_lower and "amp" in model_lower):
                # WiiM Amp Pro: Has USB Out
                available_modes = ["Line Out", "USB Out"]
            elif "wiim amp" in model_lower or ("amp" in model_lower and "wiim" in model_lower):
                # WiiM Amp (standard): Has USB Out
                available_modes = ["Line Out", "USB Out"]
            elif "wiim mini" in model_lower:
                available_modes = ["Line Out", "Optical Out"]
            elif "wiim pro" in model_lower or "wiim" in model_lower:
                available_modes = ["Line Out", "Optical Out", "Coax Out"]
            else:
                available_modes = ["Line Out", "Optical Out", "Coax Out"]

            # Convert hardware mode to name
            from pywiim.api.constants import AUDIO_OUTPUT_MODE_MAP

            current_mode_name = None
            if hardware_mode is not None:
                try:
                    mode_int = int(hardware_mode)
                    current_mode_name = AUDIO_OUTPUT_MODE_MAP.get(mode_int)
                    # Check if Bluetooth output is active (takes precedence)
                    if bluetooth_source == 1:
                        current_mode_name = "Bluetooth Out"
                except (ValueError, TypeError):
                    pass

            return {
                "supported": True,
                "model": model,
                "current_hardware_mode": hardware_mode,
                "current_mode_name": current_mode_name,
                "bluetooth_output_active": bluetooth_source == 1,
                "available_modes": available_modes,
                "available_mode_count": len(available_modes),
                "raw_status": status,
            }
        except Exception as err:
            return {
                "supported": False,
                "error": str(err),
            }

    async def _test_sources(self) -> dict[str, Any]:
        """Test source enumeration and selection capabilities."""
        from pywiim.api.constants import MODE_MAP

        try:
            # Get enumerable sources (from input_list)
            device_info = await self.client.get_device_info_model()
            enumerable_sources = device_info.input_list or []

            # Get current source
            status = await self.client.get_player_status()
            current_source = status.get("source")

            # Known selectable sources (from MODE_MAP and common services)
            # These are sources that can be selected but may not be in input_list
            known_selectable_sources = [
                "wifi",
                "bluetooth",
                "line_in",
                "optical",
                "coaxial",
                "usb",
                "hdmi",  # Physical inputs
                "spotify",
                "airplay",
                "dlna",
                "amazon",
                "tidal",
                "qobuz",
                "deezer",  # Streaming services
                "iheartradio",
                "pandora",
                "tunein",  # Internet radio
                # Note: Presets are NOT included here - they should be handled via media browser
                #      (use get_presets() to retrieve preset list and play_preset() to play them)
            ]

            # Get all unique values from MODE_MAP (these are selectable)
            mode_map_sources = list(set(MODE_MAP.values()))

            # Combine enumerable + known selectable sources (remove duplicates)
            all_selectable_sources = list(
                dict.fromkeys(enumerable_sources + known_selectable_sources + mode_map_sources)
            )

            # Remove None/empty values
            all_selectable_sources = [s for s in all_selectable_sources if s and s != "idle" and s != "follower"]

            return {
                "supported": True,
                "current_source": current_source,
                "enumerable_sources": enumerable_sources,
                "enumerable_count": len(enumerable_sources),
                "all_selectable_sources": sorted(all_selectable_sources),
                "selectable_count": len(all_selectable_sources),
                "mode_map_sources": sorted([s for s in mode_map_sources if s and s not in ["idle", "follower"]]),
                "distinction": {
                    "enumerable": "Physical inputs reported by device in input_list",
                    "selectable": "All sources that can be switched to (includes services not in input_list)",
                    "note": "Some sources (like streaming services) can be selected but aren't enumerable",
                },
            }
        except Exception as err:
            return {
                "supported": False,
                "error": str(err),
            }

    async def _test_subwoofer(self) -> dict[str, Any]:
        """Test subwoofer control capabilities (WiiM devices only)."""
        try:
            status = await self.client.get_subwoofer_status()
            if status is None:
                return {"supported": False, "reason": "No response from device"}

            # Note: main_filter_enabled=True means bass is NOT sent to main speakers
            # sub_filter_enabled=True means filtering is active (not bypassed)
            return {
                "supported": True,
                "enabled": status.enabled,
                "crossover_hz": status.crossover,
                "phase_degrees": status.phase,
                "level_db": status.level,
                "delay_ms": status.sub_delay,
                "bass_to_mains": not status.main_filter_enabled,  # Inverted logic
                "filter_bypassed": not status.sub_filter_enabled,  # Inverted logic
            }
        except WiiMError:
            return {"supported": False, "reason": "WiiM devices only"}
        except Exception as err:
            error_str = str(err).lower()
            if "unknown command" in error_str:
                return {"supported": False, "reason": "WiiM devices only (Arylic/LinkPlay not supported)"}
            return {"supported": False, "error": str(err)}

    async def _test_trigger_out(self) -> dict[str, Any]:
        """Test 12V trigger output (WiiM Ultra / Pro / Pro Plus)."""
        try:
            status = await self.client.get_trigger_out_status()
            if status is None:
                return {"supported": False, "reason": "No response or not supported"}
            return {
                "supported": True,
                "state": status,
            }
        except WiiMError:
            return {"supported": False, "reason": "WiiM Ultra/Pro/Pro Plus only"}
        except Exception as err:
            return {"supported": False, "error": str(err)}

    async def _test_led_indicator(self) -> dict[str, Any]:
        """Test LED indicator (ADR 005; Arylic + WiiM). Read returns on/off or assume on."""
        try:
            if not self.client.capabilities.get("supports_led_switch", False):
                return {"supported": False, "reason": "LED indicator not supported"}
            state = await self.client.get_led_indicator()
            return {"supported": True, "state": "on" if state else "off"}
        except Exception as err:
            return {"supported": False, "error": str(err)}

    async def _test_display(self) -> dict[str, Any]:
        """Test display/LCD (WiiM Ultra only)."""
        try:
            if not self.client.capabilities.get("supports_display_config", False):
                return {"supported": False, "reason": "Display not supported (WiiM Ultra only)"}
            return {"supported": True, "note": "set_display_enabled / set_display_config available"}
        except Exception as err:
            return {"supported": False, "error": str(err)}

    async def _test_peq(self) -> dict[str, Any]:
        """Test PEQ (Parametric / Advanced EQ) - WiiM LV2 PEQ API."""
        try:
            if not self.client.capabilities.get("supports_peq", False):
                return {"supported": False, "reason": "PEQ not supported (WiiM only)"}
            preset_list = await self.client.get_peq_preset_list()
            return {
                "supported": True,
                "custom_presets": list(preset_list.get("custom", [])),
                "preset_names": list(preset_list.get("preset", [])),
            }
        except WiiMError:
            return {"supported": False, "reason": "PEQ not available"}
        except Exception as err:
            return {"supported": False, "error": str(err)}

    async def _test_graphic_eq(self) -> dict[str, Any]:
        """Test read-only WiiM LV2 graphic EQ (Eq10HP)."""
        try:
            if not self.client.capabilities.get("supports_peq", False):
                return {"supported": False, "reason": "Graphic EQ not supported (WiiM only)"}
            settings = await self.client.get_graphic_eq_bands()
            preset_list = await self.client.get_graphic_eq_preset_list()
            return {
                "supported": True,
                "enabled": settings.enabled,
                "name": settings.name,
                "source_name": settings.source_name,
                "eq_level": settings.eq_level,
                "band_count": len(settings.bands),
                "bands": [asdict(band) for band in settings.bands],
                "custom_presets": list(preset_list.get("custom", [])),
                "preset_names": list(preset_list.get("preset", [])),
            }
        except WiiMError:
            return {"supported": False, "reason": "Graphic EQ not available"}
        except Exception as err:
            return {"supported": False, "error": str(err)}

    async def _test_room_correction(self) -> dict[str, Any]:
        """Test read-only WiiM room-correction state."""
        try:
            if not self.client.capabilities.get("supports_peq", False):
                return {"supported": False, "reason": "Room correction not supported (WiiM only)"}
            settings = await self.client.get_room_correction()
            return {
                "supported": True,
                "enabled": settings.enabled,
                "name": settings.name,
                "source_name": settings.source_name,
                "eq_level": settings.eq_level,
                "plugin_uri": settings.plugin_uri,
                "band_count": len(settings.bands),
                "bands": [asdict(band) for band in settings.bands],
            }
        except WiiMError:
            return {"supported": False, "reason": "Room correction not available"}
        except Exception as err:
            return {"supported": False, "error": str(err)}

    def _generate_summary(self) -> dict[str, Any]:
        """Generate diagnostic summary."""
        device = self.report.get("device", {})
        capabilities = self.report.get("capabilities", {})
        endpoints = self.report.get("endpoints", {})
        features = self.report.get("features", {})

        successful_endpoints = sum(1 for ep in endpoints.values() if ep.get("status") == "success")
        total_endpoints = len(endpoints)

        supported_features = sum(1 for feat in features.values() if feat.get("supported"))

        return {
            "device_model": device.get("model", "Unknown"),
            "firmware": device.get("firmware", "Unknown"),
            "vendor": capabilities.get("vendor", "unknown"),
            "endpoints_tested": total_endpoints,
            "endpoints_successful": successful_endpoints,
            "features_supported": supported_features,
            "total_features": len(features),
            "errors": len(self.report.get("errors", [])),
            "warnings": len(self.report.get("warnings", [])),
        }

    def print_report(self) -> None:
        """Print human-readable diagnostic report."""
        print("\n" + "=" * 60)
        print("📋 DIAGNOSTIC REPORT SUMMARY")
        print("=" * 60)

        summary = self.report.get("summary", {})
        print(f"\nDevice: {summary.get('device_model')} (Firmware: {summary.get('firmware')})")
        print(f"Vendor: {summary.get('vendor')}")
        print(f"\nEndpoints: {summary.get('endpoints_successful')}/{summary.get('endpoints_tested')} successful")
        print(f"Features: {summary.get('features_supported')}/{summary.get('total_features')} supported")

        if self.report.get("errors"):
            print(f"\n❌ Errors ({len(self.report['errors'])}):")
            for error in self.report["errors"]:
                print(f"   - {error}")

        if self.report.get("warnings"):
            print(f"\n⚠️  Warnings ({len(self.report['warnings'])}):")
            for warning in self.report["warnings"]:
                print(f"   - {warning}")

        print("\n" + "=" * 60)

    async def collect_diagnostic_data(
        self,
        include_endpoint_tests: bool = False,
        include_feature_tests: bool = False,
    ) -> dict[str, Any]:
        """Collect diagnostic data programmatically.

        This method gathers core diagnostic information and optionally includes
        detailed endpoint and feature testing. Useful for programmatic access
        without CLI output.

        Args:
            include_endpoint_tests: If True, test all API endpoints
            include_feature_tests: If True, test specific features

        Returns:
            Complete diagnostic report dictionary.
        """
        # Gather core info
        await self._gather_device_info()
        await self._gather_capabilities()
        await self._gather_status()
        await self._gather_debug_info()
        await self._gather_discovered_api_info()

        # Optional detailed testing
        if include_endpoint_tests:
            await self._test_endpoints()
        if include_feature_tests:
            await self._test_features()

        # Add API statistics
        try:
            self.report["api_stats"] = self.client.api_stats
        except Exception:
            self.report["api_stats"] = None

        # Add connection statistics
        try:
            self.report["connection_stats"] = self.client.connection_stats
        except Exception:
            self.report["connection_stats"] = None

        # Add multiroom information
        try:
            multiroom = await self.client.get_multiroom_status()
            self.report["multiroom"] = multiroom
        except Exception:
            self.report["multiroom"] = None

        # Add group info
        try:
            group_info = await self.client.get_device_group_info()
            self.report["group_info"] = {
                "role": group_info.role,
                "master_host": group_info.master_host,
                "master_uuid": group_info.master_uuid,
                "slave_hosts": group_info.slave_hosts,
                "slave_count": group_info.slave_count,
            }
        except Exception:
            self.report["group_info"] = None

        # Add EQ settings
        try:
            if self.client.capabilities.get("supports_eq", False):
                eq = await self.client.get_eq()
                self.report["eq"] = eq
            else:
                self.report["eq"] = None
        except Exception:
            self.report["eq"] = None

        # Channel balance (WiiM; capability-gated)
        try:
            if self.client.capabilities.get("supports_channel_balance", False):
                self.report["channel_balance"] = {
                    "supported": True,
                    "balance": await self.client.get_channel_balance(),
                }
            else:
                self.report["channel_balance"] = {"supported": False}
        except Exception:
            self.report["channel_balance"] = {"supported": False}

        # Add audio output status
        try:
            if self.client.capabilities.get("supports_audio_output", False):
                audio_output = await self.client.get_audio_output_status()
                self.report["audio_output"] = audio_output
            else:
                self.report["audio_output"] = None
        except Exception:
            self.report["audio_output"] = None

        # Add subwoofer status (WiiM devices only)
        try:
            subwoofer_status = await self.client.get_subwoofer_status()
            if subwoofer_status:
                # Note: main_filter_enabled=True means bass is NOT sent to main speakers
                # sub_filter_enabled=True means filtering is active (not bypassed)
                self.report["subwoofer"] = {
                    "supported": True,
                    "enabled": subwoofer_status.enabled,
                    "crossover_hz": subwoofer_status.crossover,
                    "phase_degrees": subwoofer_status.phase,
                    "level_db": subwoofer_status.level,
                    "delay_ms": subwoofer_status.sub_delay,
                    "bass_to_mains": not subwoofer_status.main_filter_enabled,
                    "filter_bypassed": not subwoofer_status.sub_filter_enabled,
                }
            else:
                self.report["subwoofer"] = {"supported": False}
        except Exception:
            self.report["subwoofer"] = {"supported": False}

        # Add 12V trigger status (WiiM Ultra / Pro / Pro Plus)
        try:
            if self.client.capabilities.get("supports_trigger_out", False):
                trigger_state = await self.client.get_trigger_out_status()
                self.report["trigger_out"] = {
                    "supported": True,
                    "state": "on" if trigger_state else "off" if trigger_state is False else "unknown",
                }
            else:
                self.report["trigger_out"] = {"supported": False}
        except Exception:
            self.report["trigger_out"] = {"supported": False}

        # LED Indicator (ADR 005)
        try:
            if self.client.capabilities.get("supports_led_switch", False):
                led_state = await self.client.get_led_indicator()
                self.report["led_indicator"] = {"supported": True, "state": "on" if led_state else "off"}
            else:
                self.report["led_indicator"] = {"supported": False}
        except Exception:
            self.report["led_indicator"] = {"supported": False}

        # Display (WiiM Ultra)
        try:
            self.report["display"] = {
                "supported": bool(self.client.capabilities.get("supports_display_config", False)),
            }
        except Exception:
            self.report["display"] = {"supported": False}

        # Add PEQ (Advanced EQ) preset list if supported
        try:
            if self.client.capabilities.get("supports_peq", False):
                preset_list = await self.client.get_peq_preset_list()
                self.report["peq"] = {
                    "supported": True,
                    "custom_presets": preset_list.get("custom", []),
                    "preset_names": preset_list.get("preset", []),
                }
            else:
                self.report["peq"] = {"supported": False}
        except Exception:
            self.report["peq"] = {"supported": False}

        # Add Graphic EQ (Eq10HP) state if supported
        try:
            self.report["graphic_eq"] = await self._test_graphic_eq()
        except Exception:
            self.report["graphic_eq"] = {"supported": False}

        # Add room-correction state if supported
        try:
            self.report["room_correction"] = await self._test_room_correction()
        except Exception:
            self.report["room_correction"] = {"supported": False}

        # Generate summary
        self.report["summary"] = self._generate_summary()

        return self.report

    def save_report(self, filename: str) -> None:
        """Save diagnostic report to JSON file."""
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.report, f, indent=2, default=str)
        print(f"\n💾 Report saved to: {filename}")


async def main() -> None:
    """Main entry point for diagnostic tool."""
    parser = argparse.ArgumentParser(
        description="WiiM Device Diagnostic Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic diagnostic
  python -m pywiim.diagnostics 192.168.1.100

  # Save report to file
  python -m pywiim.diagnostics 192.168.1.100 --output report.json

  # Verbose output
  python -m pywiim.diagnostics 192.168.1.100 --verbose

  # HTTPS device
  python -m pywiim.diagnostics 192.168.1.100 --port 443

  # Probe only read-only WiiM APIs discovered from app traffic
  python -m pywiim.diagnostics 192.168.1.100 --discovered-apis-only
        """,
    )
    parser.add_argument(
        "host",
        help="Device IP address or hostname",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=80,
        help="Device port (default: 80, use 443 for HTTPS)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Save report to JSON file",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--discovered-apis-only",
        action="store_true",
        help="Only probe read-only WiiM APIs discovered from app traffic",
    )

    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )

    # Create client and run diagnostics
    client = WiiMClient(host=args.host, port=args.port)
    diagnostics = DeviceDiagnostics(client)

    try:
        if args.discovered_apis_only:
            print("🔎 Starting discovered WiiM API probe...")
            print(f"   Device: {client.host}:{client.port}\n")
            await diagnostics._gather_device_info()
            await diagnostics._gather_discovered_api_info()
        else:
            await diagnostics.run_full_diagnostic()
            diagnostics.print_report()

        if args.output:
            diagnostics.save_report(args.output)
        else:
            print("\n💡 Tip: Use --output to save full report to JSON file")

    except KeyboardInterrupt:
        print("\n\n⚠️  Diagnostic interrupted by user")
        sys.exit(1)
    except Exception as err:
        print(f"\n❌ Fatal error: {err}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)
    finally:
        await client.close()


def cli_main() -> None:
    """CLI entry point for setuptools script."""
    asyncio.run(main())


if __name__ == "__main__":
    cli_main()
