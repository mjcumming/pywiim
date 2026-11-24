"""Diagnostics information."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from . import Player


class DiagnosticsCollector:
    """Collects diagnostic information."""

    def __init__(self, player: Player) -> None:
        """Initialize diagnostics collector.

        Args:
            player: Parent Player instance.
        """
        self.player = player

    async def get_diagnostics(self) -> dict[str, Any]:
        """Get comprehensive diagnostic information for this player."""
        # Import __version__ here to avoid circular import
        from .. import __version__

        diagnostics: dict[str, Any] = {
            "timestamp": time.time(),
            "host": self.player.host,
            "pywiim_version": __version__,
        }

        # Device information
        try:
            if self.player._device_info:
                diagnostics["device"] = {
                    "uuid": self.player._device_info.uuid,
                    "name": self.player._device_info.name,
                    "model": self.player._device_info.model,
                    "firmware": self.player._device_info.firmware,
                    "mac": self.player._device_info.mac,
                    "ip": self.player._device_info.ip,
                    "preset_key": self.player._device_info.preset_key,
                    "input_list": self.player._device_info.input_list,
                    "hardware": self.player._device_info.hardware,
                    "wmrm_version": self.player._device_info.wmrm_version,
                    "mcu_ver": self.player._device_info.mcu_ver,
                    "dsp_ver": self.player._device_info.dsp_ver,
                }
            else:
                from .statemgr import StateManager

                device_info = await StateManager(self.player).get_device_info()
                diagnostics["device"] = {
                    "uuid": device_info.uuid,
                    "name": device_info.name,
                    "model": device_info.model,
                    "firmware": device_info.firmware,
                    "mac": device_info.mac,
                    "ip": device_info.ip,
                    "preset_key": device_info.preset_key,
                    "input_list": device_info.input_list,
                    "hardware": device_info.hardware,
                    "wmrm_version": device_info.wmrm_version,
                    "mcu_ver": device_info.mcu_ver,
                    "dsp_ver": device_info.dsp_ver,
                }
        except Exception as err:
            diagnostics["device"] = {"error": str(err)}

        # WiiM Voice Remote (BLE MAC is masked)
        try:
            remote = self.player.ble_remote
            if remote is not None:
                remote_diag = remote.diagnostics_dict()
                remote_diag["volume_step"] = self.player.remote_volume_step
                diagnostics["ble_remote"] = remote_diag
        except Exception as err:
            diagnostics["ble_remote"] = {"error": str(err)}

        # Current status
        try:
            if self.player._status_model:
                diagnostics["status"] = {
                    "play_state": self.player._status_model.play_state,
                    "volume": self.player._status_model.volume,
                    "mute": self.player._status_model.mute,
                    "source": self.player._status_model.source,
                    "position": self.player._status_model.position,
                    "duration": self.player._status_model.duration,
                    "title": self.player._status_model.title,
                    "artist": self.player._status_model.artist,
                    "album": self.player._status_model.album,
                }
            else:
                from .statemgr import StateManager

                status = await StateManager(self.player).get_status()
                diagnostics["status"] = {
                    "play_state": status.play_state,
                    "volume": status.volume,
                    "mute": status.mute,
                    "source": status.source,
                    "position": status.position,
                    "duration": status.duration,
                    "title": status.title,
                    "artist": status.artist,
                    "album": status.album,
                }
        except Exception as err:
            diagnostics["status"] = {"error": str(err)}

        # Capabilities
        try:
            diagnostics["capabilities"] = self.player.client.capabilities.copy()
        except Exception as err:
            diagnostics["capabilities"] = {"error": str(err)}

        # Multiroom information
        try:
            multiroom = await self.player.client.get_multiroom_status()
            diagnostics["multiroom"] = multiroom
        except Exception:
            diagnostics["multiroom"] = None

        # Group info
        try:
            group_info = await self.player.client.get_device_group_info()
            diagnostics["group_info"] = {
                "role": group_info.role,
                "master_host": group_info.master_host,
                "master_uuid": group_info.master_uuid,
                "slave_hosts": group_info.slave_hosts,
                "slave_count": group_info.slave_count,
            }
        except Exception:
            diagnostics["group_info"] = None

        # UPnP statistics (if available)
        try:
            if hasattr(self.player, "_upnp_eventer") and self.player._upnp_eventer:
                diagnostics["upnp"] = self.player._upnp_eventer.statistics
            else:
                diagnostics["upnp"] = None
        except Exception:
            diagnostics["upnp"] = None

        # API statistics
        try:
            diagnostics["api_stats"] = self.player.client.api_stats
        except Exception:
            diagnostics["api_stats"] = None

        # Connection statistics
        try:
            diagnostics["connection_stats"] = self.player.client.connection_stats
        except Exception:
            diagnostics["connection_stats"] = None

        # Audio output status
        try:
            if self.player._audio_output_status:
                diagnostics["audio_output"] = self.player._audio_output_status
            else:
                if self.player.client.capabilities.get("supports_audio_output", False):
                    # Use player-level method which automatically updates the cache
                    audio_output = await self.player.get_audio_output_status()
                    diagnostics["audio_output"] = audio_output
                else:
                    diagnostics["audio_output"] = None
        except Exception:
            diagnostics["audio_output"] = None

        # EQ settings
        try:
            if self.player.client.capabilities.get("supports_eq", False):
                eq = await self.player.client.get_eq()
                diagnostics["eq"] = eq
            else:
                diagnostics["eq"] = None
        except Exception:
            diagnostics["eq"] = None

        # Role
        diagnostics["role"] = self.player.role
        diagnostics["available"] = self.player.available

        return diagnostics

    async def reboot(self) -> None:
        """Reboot the device.

        Note: This command may not return a response as the device will restart.
        The method handles this gracefully and considers the command successful
        even if the device stops responding.

        Raises:
            WiiMError: If the request fails before the device reboots.
        """
        await self.player.client.reboot()
        self.player._available = False

    async def sync_time(self, ts: int | None = None) -> None:
        """Synchronize device time with system time or provided timestamp.

        Args:
            ts: Unix timestamp (seconds since epoch). If None, uses current system time.

        Raises:
            WiiMError: If the request fails.
        """
        await self.player.client.sync_time(ts)

    async def get_multiroom_diagnostics(self) -> dict[str, Any]:
        """Get multiroom-specific diagnostic information.

        This method helps debug WiFi Direct multiroom linking issues by providing
        detailed information about:
        - This device's role and UUID
        - Linked Player objects (if any)
        - Raw device API group state
        - Available player_finder and all_players_finder callbacks

        Returns:
            Dictionary with multiroom diagnostic information.
        """
        diagnostics: dict[str, Any] = {
            "timestamp": time.time(),
            "host": self.player.host,
        }

        # This device's identity
        diagnostics["this_device"] = {
            "host": self.player.host,
            "uuid": self.player.uuid,
            "uuid_normalized": self._normalize_uuid(self.player.uuid) if self.player.uuid else None,
            "name": self.player.name,
            "role": self.player.role,
            "detected_role": self.player._detected_role,
            "device_info_populated": self.player._device_info is not None,
        }

        # Callbacks status
        diagnostics["callbacks"] = {
            "player_finder_set": self.player._player_finder is not None,
            "all_players_finder_set": self.player._all_players_finder is not None,
            "on_state_changed_set": self.player._on_state_changed is not None,
        }

        # Group object state (linked Player objects)
        if self.player._group:
            group = self.player._group
            master = group.master
            diagnostics["group_object"] = {
                "master": {
                    "host": master.host if master else None,
                    "uuid": master.uuid if master else None,
                    "name": master.name if master else None,
                },
                "slaves": [
                    {
                        "host": s.host,
                        "uuid": s.uuid,
                        "name": s.name,
                    }
                    for s in group.slaves
                ],
                "size": group.size,
            }
        else:
            diagnostics["group_object"] = None

        # Raw device API state
        try:
            group_info = await self.player.client.get_device_group_info()
            diagnostics["api_group_info"] = {
                "role": group_info.role,
                "master_host": group_info.master_host,
                "master_uuid": group_info.master_uuid,
                "slave_hosts": group_info.slave_hosts,
                "slave_uuids": group_info.slave_uuids,
                "slave_count": group_info.slave_count,
            }
        except Exception as err:
            diagnostics["api_group_info"] = {"error": str(err)}

        # Full slave list from API (if this device is master)
        try:
            slaves_info = await self.player.client.get_slaves_info()
            diagnostics["api_slaves_info"] = [
                {
                    "ip": s.get("ip"),
                    "uuid": s.get("uuid"),
                    "uuid_normalized": self._normalize_uuid(s.get("uuid", "")) if s.get("uuid") else None,
                    "name": s.get("name"),
                    "volume": s.get("volume"),
                }
                for s in slaves_info
            ]
        except Exception as err:
            diagnostics["api_slaves_info"] = {"error": str(err)}

        # All known players (if all_players_finder is available)
        if self.player._all_players_finder:
            try:
                all_players = self.player._all_players_finder()
                diagnostics["all_known_players"] = [
                    {
                        "host": getattr(p, "host", "unknown"),
                        "uuid": getattr(p, "uuid", None),
                        "uuid_normalized": (
                            self._normalize_uuid(getattr(p, "uuid", "") or "") if getattr(p, "uuid", None) else None
                        ),
                        "name": getattr(p, "name", None),
                        "role": getattr(p, "_detected_role", "unknown"),
                        "device_info_populated": getattr(p, "_device_info", None) is not None,
                        "is_self": p is self.player,
                    }
                    for p in all_players
                ]
            except Exception as err:
                diagnostics["all_known_players"] = {"error": str(err)}
        else:
            diagnostics["all_known_players"] = "all_players_finder not set"

        # Linking analysis
        diagnostics["linking_analysis"] = self._analyze_linking_issues(diagnostics)

        return diagnostics

    def _analyze_linking_issues(self, diagnostics: dict[str, Any]) -> dict[str, Any]:
        """Analyze multiroom diagnostics for potential linking issues.

        Args:
            diagnostics: The collected diagnostic data.

        Returns:
            Analysis with potential issues and recommendations.
        """
        issues: list[str] = []
        recommendations: list[str] = []

        # Check callbacks
        if not diagnostics["callbacks"]["all_players_finder_set"]:
            issues.append("all_players_finder callback not set")
            recommendations.append(
                "For WiFi Direct multiroom, the integration must provide an "
                "all_players_finder callback that returns all known Player objects"
            )

        # Check device info
        if not diagnostics["this_device"]["device_info_populated"]:
            issues.append("device_info not populated - UUID may be unavailable")
            recommendations.append("Ensure refresh(full=True) has been called to populate device_info")

        # Check for WiFi Direct scenario (internal IPs in slave list)
        api_slaves = diagnostics.get("api_slaves_info", [])
        if isinstance(api_slaves, list) and api_slaves:
            internal_ips = [s for s in api_slaves if s.get("ip", "").startswith("10.10.10.")]
            if internal_ips:
                issues.append(
                    f"WiFi Direct detected: {len(internal_ips)} slaves have internal 10.10.10.x IPs "
                    "which won't match HA config entries"
                )
                recommendations.append(
                    "WiFi Direct multiroom requires UUID-based matching. "
                    "Ensure all slave devices have device_info populated (check all_known_players)"
                )

        # Check for UUID matching issues
        all_players = diagnostics.get("all_known_players", [])
        if isinstance(all_players, list) and isinstance(api_slaves, list):
            api_slave_uuids = {s.get("uuid_normalized") for s in api_slaves if s.get("uuid_normalized")}
            known_player_uuids = {
                p.get("uuid_normalized") for p in all_players if p.get("uuid_normalized") and not p.get("is_self")
            }

            if api_slave_uuids and known_player_uuids:
                matched = api_slave_uuids.intersection(known_player_uuids)
                unmatched = api_slave_uuids - known_player_uuids

                if unmatched:
                    issues.append(
                        f"UUID mismatch: {len(unmatched)} slaves in API have UUIDs not found in known players: "
                        f"{unmatched}"
                    )

                if matched:
                    issues.append(f"UUID matches found: {len(matched)} slaves can be linked")

            # Check for players without UUIDs
            players_without_uuid = [p.get("host") for p in all_players if not p.get("uuid") and not p.get("is_self")]
            if players_without_uuid:
                issues.append(f"Players without UUID (need full refresh): {players_without_uuid}")
                recommendations.append("Call refresh(full=True) on these devices to populate their UUIDs")

        return {
            "issues": issues,
            "recommendations": recommendations,
            "linking_healthy": len(issues) == 0 or (len(issues) == 1 and "UUID matches found" in issues[0]),
        }

    @staticmethod
    def _normalize_uuid(uuid: str) -> str:
        """Normalize UUID for comparison."""
        return uuid.lower().replace("uuid:", "").replace("-", "")
