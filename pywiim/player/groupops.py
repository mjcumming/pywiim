"""Group operations.

# pragma: allow-long-file groupops-cohesive
# This file exceeds the 600 LOC hard limit (680 lines) but is kept as a single
# cohesive unit because:
# 1. Single responsibility: Group operations (create, join, leave, synchronize)
# 2. Well-organized: Clear sections for group management and metadata propagation
# 3. Tight coupling: All methods work together for group operations
# 4. Maintainable: Clear structure, follows group operations design pattern
# 5. Natural unit: Represents one concept (group operations)
# Splitting would add complexity without clear benefit.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..group import Group
    from . import Player

_LOGGER = logging.getLogger(__name__)


class GroupOperations:
    """Manages group operations."""

    def __init__(self, player: Player) -> None:
        """Initialize group operations.

        Args:
            player: Parent Player instance.
        """
        self.player = player

    def _find_slave_player(self, slave_host: str, slave_uuid: str | None) -> Any:
        """Find a slave Player by host or UUID.

        For WiFi Direct multiroom (older LinkPlay devices), slaves join the
        master's internal network (10.10.10.x) and are no longer reachable
        from the main LAN. In this case, IP-based matching fails and we need
        to fall back to UUID-based matching.

        Lookup order:
        1. By IP via player_finder (works for router-based multiroom)
        2. By UUID via player_finder (if integration supports UUID lookups)
        3. By UUID via all_players_finder search (handles WiFi Direct without
           requiring integration to implement UUID lookups)

        Args:
            slave_host: Slave IP address (may be internal 10.10.10.x for WiFi Direct)
            slave_uuid: Slave UUID for fallback matching (may be None)

        Returns:
            Player instance if found, None otherwise.
        """
        _LOGGER.debug(
            "Searching for slave player: host=%s, uuid=%s, player_finder=%s, all_players_finder=%s",
            slave_host,
            slave_uuid,
            self.player._player_finder is not None,
            self.player._all_players_finder is not None,
        )

        # Try by host/IP first (works for normal router-based multiroom)
        if self.player._player_finder:
            slave_player = self.player._player_finder(slave_host)
            if slave_player:
                _LOGGER.debug(
                    "Found slave by IP via player_finder: host=%s",
                    slave_host,
                )
                return slave_player

            _LOGGER.debug(
                "IP lookup failed (expected for WiFi Direct): host=%s",
                slave_host,
            )

            # Fallback 1: Try by UUID via player_finder (for integrations that support it)
            if slave_uuid:
                slave_player = self.player._player_finder(slave_uuid)
                if slave_player:
                    _LOGGER.debug(
                        "Found slave by UUID via player_finder: host=%s, uuid=%s",
                        slave_host,
                        slave_uuid,
                    )
                    return slave_player

                _LOGGER.debug(
                    "UUID lookup via player_finder failed: uuid=%s",
                    slave_uuid,
                )

        # Fallback 2: Search by UUID using internal player registry
        # This handles WiFi Direct multiroom AUTOMATICALLY - no integration changes needed!
        # pywiim maintains a class-level registry of all Player instances
        if slave_uuid:
            from .base import PlayerBase

            # Use provided callback if available, otherwise use internal registry
            if self.player._all_players_finder:
                try:
                    all_players = self.player._all_players_finder()
                except Exception as err:
                    _LOGGER.debug("all_players_finder callback failed: %s, using internal registry", err)
                    all_players = list(PlayerBase._all_instances)
            else:
                # Use internal registry - this is automatic, no callback needed!
                all_players = list(PlayerBase._all_instances)

            normalized_target = self._normalize_uuid(slave_uuid)

            _LOGGER.debug(
                "Searching %d players for UUID match: target=%s (normalized=%s)",
                len(all_players) if all_players else 0,
                slave_uuid,
                normalized_target,
            )

            for player in all_players:
                if player is self.player:
                    continue  # Skip self

                player_uuid = getattr(player, "uuid", None)
                player_host = getattr(player, "host", "unknown")

                if player_uuid:
                    normalized_player = self._normalize_uuid(player_uuid)
                    if normalized_player == normalized_target:
                        _LOGGER.debug(
                            "Found slave by UUID via registry search: host=%s, uuid=%s, matched_player=%s",
                            slave_host,
                            slave_uuid,
                            player_host,
                        )
                        return player
                    else:
                        _LOGGER.debug(
                            "UUID mismatch: player %s has uuid=%s (normalized=%s), target=%s (normalized=%s)",
                            player_host,
                            player_uuid,
                            normalized_player,
                            slave_uuid,
                            normalized_target,
                        )
                else:
                    _LOGGER.debug(
                        "Player %s has no UUID (device_info not populated yet?)",
                        player_host,
                    )

            _LOGGER.warning(
                "Could not find slave player for UUID %s - "
                "checked %d players, none matched (WiFi Direct multiroom linking failed)",
                slave_uuid,
                len(all_players) if all_players else 0,
            )
        elif not slave_uuid:
            _LOGGER.debug(
                "No UUID available for slave at %s - cannot perform UUID-based lookup",
                slave_host,
            )

        return None

    def _notify_all_group_members(self, group: Group | None) -> None:
        """Notify all players in a group of state changes.

        This ensures all coordinators/integrations are notified when group
        membership changes, so UIs update immediately across all group members.

        Args:
            group: The group whose members should be notified, or None.
        """
        if not group:
            return

        for player in group.all_players:
            if player._on_state_changed:
                try:
                    player._on_state_changed()
                except Exception as err:
                    _LOGGER.debug("Error calling on_state_changed callback for %s: %s", player.host, err)

    async def _synchronize_group_state(self) -> None:
        """Synchronize group state from device API state.

        Uses a "Master-Centric" approach for robust role detection:
        1. Slaves often don't know who their master is.
        2. Only Masters reliably know their slave list.
        3. We use fast status-based detection to avoid expensive getDeviceInfo calls.
        4. The 'group' field is authoritative for slave detection:
           - group == "1" means device is a slave
           - group == "0" means device is solo or master (check slave list to determine)
        5. We only call get_device_group_info() (which uses getDeviceInfo) when:
           - Potential slave detected (group="1")
           - We have a group object (might be master, need to verify)
           - Device info is cached (full refresh happened, safe to check)
        6. When a slave is detected, the coordinator should trigger master detection
           on all players to find which one became the master.

        Note: We previously used mode=="99" to detect slaves, but this can get stuck
        after leaving a group (firmware bug). The 'group' field is always reliable.
        """
        if self.player._status_model is None:
            return

        status = self.player._status_model
        old_role = self.player._detected_role

        # Fast path: Use group field to detect potential slaves
        # group == "1" is the authoritative indicator that device is a slave
        # Note: mode=="99" can get stuck after leaving group (firmware bug), so we don't use it
        is_potential_slave = status.group == "1"

        # We only call get_device_group_info() (which uses getDeviceInfo) when:
        # 1. Potential slave detected (group="1")
        # 2. We have a group object (might be master, need to verify)
        # 3. We have device_info cached (full refresh happened, safe to check)
        should_check_role = False

        if is_potential_slave:
            # Potential slave detected via fast path - we need to check role
            should_check_role = True
            _LOGGER.debug(
                "Potential slave detected for %s (group=1) - checking role via get_device_group_info()",
                self.player.host,
            )
        elif self.player._group is not None:
            # We think we're in a group - need to verify (might be master)
            should_check_role = True
            _LOGGER.debug("Group object exists for %s - checking role via get_device_group_info()", self.player.host)
        elif self.player._device_info is not None:
            # Device info is cached (full refresh happened) - safe to check role
            # This handles the case where a master might also have group="0"
            should_check_role = True
            _LOGGER.debug("Device info cached for %s - checking role via get_device_group_info()", self.player.host)

        if should_check_role:
            # Call get_device_group_info() to determine role accurately
            try:
                group_info = await self.player.client.get_device_group_info()
                detected_role = group_info.role
                slave_hosts = group_info.slave_hosts
                slave_uuids = group_info.slave_uuids

                # Trust get_device_group_info() result - it checks group field and master info
                # No override needed - the group field is always correct
            except Exception as err:
                _LOGGER.warning(
                    "Failed to get device group info for %s: %s - keeping current role",
                    self.player.host,
                    err,
                )
                return
        else:
            # Fast path: No slave indicator (group != "1") and we're solo with no group
            # Skip expensive call - device is definitely solo
            detected_role = "solo"
            slave_hosts = []
            slave_uuids = []

        # Cross-coordinator role inference for WiFi Direct multiroom
        # WiFi Direct slaves report group="0" (solo) because they don't know they're in a group.
        # Only the master knows the slave list. Check if any known master lists us as a slave.
        if detected_role == "solo" and self.player.uuid and self.player._all_players_finder:
            inferred_role = await self._check_if_slave_of_any_master()
            if inferred_role == "slave":
                _LOGGER.info(
                    "Cross-coordinator inference: %s (%s) is SLAVE (found in a master's slave list)",
                    self.player.host,
                    self.player.uuid,
                )
                detected_role = "slave"

        # Detect role change (especially solo->slave, which triggers master detection)
        became_slave = old_role == "solo" and detected_role == "slave"

        # Update _detected_role - this is the single source of truth for player.role
        self.player._detected_role = detected_role

        # Clear source if not a slave but source is still "multiroom" (for UI clarity)
        if detected_role != "slave" and self.player._status_model:
            current_source = self.player._status_model.source
            if current_source == "multiroom":
                _LOGGER.debug(
                    "Clearing multiroom source for %s (role=%s, was=%s)",
                    self.player.host,
                    detected_role,
                    old_role,
                )
                self.player._status_model.source = None
                self.player._status_model._multiroom_mode = None
                # Also clear from state synchronizer to prevent refresh() from restoring it
                self.player._state_synchronizer.update_from_http({"source": None})

        # If we became a slave, log it (coordinator should trigger master detection on all players)
        if became_slave:
            _LOGGER.info(
                "Device %s became SLAVE (was solo) - coordinator should trigger master detection on all players",
                self.player.host,
            )

        from ..group import Group as GroupClass

        # Sync Group structure to match device API state
        # Case 1: Device is solo but we think it's in a group
        if detected_role == "solo" and self.player._group is not None:
            if self.player._group.master == self.player and len(self.player._group.slaves) == 0:
                _LOGGER.debug(
                    "Device %s is solo but has empty group object - keeping it (ready for slaves)", self.player.host
                )
            else:
                _LOGGER.debug("Device %s is solo but has group object - clearing group", self.player.host)
                old_group = self.player._group
                if self.player._group.master != self.player:
                    self.player._group.remove_slave(self.player)
                else:
                    for slave in list(self.player._group.slaves):
                        self.player._group.remove_slave(slave)
                    self.player._group.master._group = None
                self.player._group = None
                # Notify all members of the disbanded group
                self._notify_all_group_members(old_group)

        # Case 2: Device is master but we don't have a group object
        elif detected_role == "master" and self.player._group is None:
            _LOGGER.debug("Device %s is master but has no group object - creating group", self.player.host)
            group = GroupClass(self.player)
            self.player._group = group

            # Automatically link slave Player objects if player_finder is available
            # Use UUID fallback for WiFi Direct devices with internal 10.10.10.x IPs
            if slave_hosts and self.player._player_finder:
                for i, slave_host in enumerate(slave_hosts):
                    slave_uuid = slave_uuids[i] if i < len(slave_uuids) else None
                    try:
                        slave_player = self._find_slave_player(slave_host, slave_uuid)
                        if slave_player:
                            # If slave is already in another group, remove it first
                            if slave_player._group and slave_player._group != group:
                                slave_player._group.remove_slave(slave_player)

                            if slave_player not in group.slaves:
                                _LOGGER.debug("Auto-linking slave %s to master %s", slave_host, self.player.host)
                                group.add_slave(slave_player)
                    except Exception as err:
                        _LOGGER.debug("Failed to find/link slave Player %s: %s", slave_host, err)

            # Force an immediate role update notification
            # This ensures the master's role change (solo -> master) is broadcast
            if self.player._on_state_changed:
                try:
                    self.player._on_state_changed()
                except Exception as err:
                    _LOGGER.debug("Error calling on_state_changed callback for %s: %s", self.player.host, err)

        # Case 3: Device is master and we have a group - sync slave list
        elif detected_role == "master" and self.player._group is not None:
            slaves_changed = False

            if self.player._group.master != self.player:
                _LOGGER.warning("Device %s is master but group object says we're a slave - fixing", self.player.host)
                old_group = self.player._group
                self.player._group = None
                old_group.remove_slave(self.player)
                group = GroupClass(self.player)
                self.player._group = group
                slaves_changed = True

            if slave_hosts:
                device_slave_hosts = set(slave_hosts)
                linked_slave_hosts = {slave.host for slave in self.player._group.slaves}
                # Also track linked slaves by UUID for WiFi Direct matching
                linked_slave_uuids = {slave.uuid for slave in self.player._group.slaves if slave.uuid}

                # Remove slaves that are no longer in device state
                # Check both host and UUID to handle WiFi Direct slaves
                device_slave_uuids = set(slave_uuids) if slave_uuids else set()
                for slave in list(self.player._group.slaves):
                    slave_still_in_group = slave.host in device_slave_hosts or (
                        slave.uuid and slave.uuid in device_slave_uuids
                    )
                    if not slave_still_in_group:
                        _LOGGER.debug("Removing slave %s from group (no longer in device state)", slave.host)
                        self.player._group.remove_slave(slave)
                        slaves_changed = True

                # Automatically link new slave Player objects if player_finder is available
                # Use UUID fallback for WiFi Direct devices with internal 10.10.10.x IPs
                if self.player._player_finder:
                    for i, slave_host in enumerate(slave_hosts):
                        slave_uuid = slave_uuids[i] if i < len(slave_uuids) else None
                        # Check if already linked by host or UUID
                        already_linked = slave_host in linked_slave_hosts or (
                            slave_uuid and slave_uuid in linked_slave_uuids
                        )
                        if not already_linked:
                            try:
                                slave_player = self._find_slave_player(slave_host, slave_uuid)
                                if slave_player:
                                    # If slave is already in another group, remove it first
                                    if slave_player._group and slave_player._group != self.player._group:
                                        slave_player._group.remove_slave(slave_player)

                                    _LOGGER.debug(
                                        "Auto-linking new slave %s to master %s", slave_host, self.player.host
                                    )
                                    self.player._group.add_slave(slave_player)
                                    slaves_changed = True
                            except Exception as err:
                                _LOGGER.debug("Failed to find/link slave Player %s: %s", slave_host, err)

            # Notify all group members if slaves changed
            if slaves_changed:
                self._notify_all_group_members(self.player._group)

        # Case 4: Device is slave
        elif detected_role == "slave":
            # We do NOTHING here.
            # Slaves are passive. They are claimed by the Master.
            # If we are a slave, we wait for the Master's poll cycle to find us and add us.
            # Just ensure we aren't holding onto a stale Master identity if we know we are solo.

            # However, if we have a player_finder and we know the master IP from status (rare but possible),
            # we can try to link up proactively.
            pass

    async def create_group(self) -> Group:
        """Create a new group with this player as master."""
        if self.player.is_slave:
            _LOGGER.debug("Player %s is slave, leaving group before creating new group", self.player.host)
            await self.leave_group()

        if self.player.is_master:
            return self.player._group  # type: ignore[return-value]

        await self.player.client.create_group()

        if self.player._group is None:
            from ..group import Group as GroupClass

            group = GroupClass(self.player)
            self.player._group = group

        if self.player._on_state_changed:
            try:
                self.player._on_state_changed()
            except Exception as err:
                _LOGGER.debug("Error calling on_state_changed callback: %s", err)

        return self.player._group

    async def join_group(self, master: Any) -> None:
        """Join this player to another player's group.

        This method handles all preconditions automatically:
        - If this player is master: disbands its group first
        - If this player is slave: leaves current group first
        - If target is slave: has target leave its group first
        - If target is solo: creates a group on target first
        - Uses WiFi Direct mode for legacy firmware (< 4.2.8020)

        This method is idempotent: calling it multiple times with the same target
        is safe and will return success if already in the target group.

        The integration/caller doesn't need to check roles or handle preconditions -
        just call this method and it will orchestrate everything needed.

        Args:
            master: The player to join (will become or is already the master).
        """
        # Idempotent check: if already in the target master's group, return success (no-op)
        if self.player._group is not None and self.player._group.master is not None:
            if self.player._group.master.host == master.host:
                _LOGGER.debug(
                    "Player %s is already in target master %s's group - no action needed",
                    self.player.host,
                    master.host,
                )
                return

        old_group = self.player._group if self.player.is_slave else None

        if self.player.is_master:
            _LOGGER.debug("Player %s is master, disbanding group before join", self.player.host)
            await self.leave_group()

        # If this player is a slave in a DIFFERENT group, leave it first
        if self.player.is_slave and old_group is not None:
            _LOGGER.debug("Player %s is slave in different group, leaving first", self.player.host)
            await self.leave_group()
            old_group = None  # Already left, no need to remove later

        if master.is_slave:
            _LOGGER.debug("Target %s is slave, having it leave group first", master.host)
            await master.leave_group()
            # Device needs time to settle after leaving a group before it can accept new connections
            # Without this wait, the subsequent join may fail silently (API returns OK but device doesn't change state)
            await asyncio.sleep(2.0)
            await master.refresh(full=True)
            _LOGGER.debug("After leave_group + wait: %s role is now %s", master.host, master.role)

        if master.is_solo:
            _LOGGER.debug("Target %s is solo, creating group", master.host)
            await GroupOperations(master).create_group()

        # Ensure device_info is available (refresh if needed)
        if self.player._device_info is None:
            _LOGGER.debug("Device info not cached for %s, refreshing", self.player.host)
            await self.player.refresh(full=True)
        if master._device_info is None:
            _LOGGER.debug("Device info not cached for master %s, refreshing", master.host)
            await master.refresh(full=True)

        slave_info = self.player._device_info
        master_info = master._device_info

        # Check if WiFi Direct mode is needed (firmware < 4.2.8020)
        use_wifi_direct = (master_info and master_info.needs_wifi_direct_multiroom) or (
            slave_info and slave_info.needs_wifi_direct_multiroom
        )

        if use_wifi_direct:
            _LOGGER.info(
                "WiFi Direct mode required (legacy firmware). " "Slave: %s (firmware=%s), Master: %s (firmware=%s)",
                self.player.host,
                slave_info.firmware if slave_info else "unknown",
                master.host,
                master_info.firmware if master_info else "unknown",
            )

        # Get WiFi Direct info if needed
        master_ssid: str | None = None
        master_wifi_channel: int | None = None

        if use_wifi_direct and master_info:
            # Try DeviceInfo first, then fetch from API
            if master_info.ssid and master_info.wifi_channel:
                master_ssid = master_info.ssid
                master_wifi_channel = master_info.wifi_channel
                _LOGGER.debug(
                    "Using WiFi Direct info from DeviceInfo: ssid=%s, channel=%s", master_ssid, master_wifi_channel
                )
            else:
                _LOGGER.debug("Fetching WiFi Direct info from master %s", master.host)
                try:
                    master_ssid, master_wifi_channel = await master.client.get_wifi_direct_info()
                    if master_ssid and master_wifi_channel:
                        _LOGGER.debug("Fetched WiFi Direct info: ssid=%s, channel=%s", master_ssid, master_wifi_channel)
                    else:
                        _LOGGER.warning("Failed to get WiFi Direct info from master %s - join may fail", master.host)
                except Exception as e:
                    _LOGGER.warning("Failed to fetch WiFi Direct info from master %s: %s", master.host, e)

        _LOGGER.debug(
            "Joining: slave=%s -> master=%s (wifi_direct=%s)",
            self.player.host,
            master.host,
            use_wifi_direct,
        )

        await self.player.client.join_slave(
            master.host,
            master_device_info=master_info,
            master_ssid=master_ssid,
            master_wifi_channel=master_wifi_channel,
        )

        # Optimistic local state update for immediate UI feedback.
        # Keep verification below (device can still reject silently), but reflect the
        # intended grouping state right away so coordinators don't wait for retries.
        optimistic_group = master.group
        optimistic_link_applied = False
        if optimistic_group is not None and self.player not in optimistic_group.slaves:
            optimistic_group.add_slave(self.player)
            optimistic_link_applied = True
            self._notify_all_group_members(optimistic_group)

        # CRITICAL: join_slave() always returns "OK" even when it fails
        # For Gen1 devices (especially WiFi Direct), the device needs time to:
        # 1. Process the join command
        # 2. Connect to master's WiFi Direct network (if applicable)
        # 3. Update its internal state
        # 4. Update the group field from "0" to "1"
        # We need to wait and retry the check multiple times

        # Determine wait time based on device type
        if use_wifi_direct:
            # WiFi Direct mode (Gen1) - needs significant time for network connection
            # WiFi Direct connections can take 5-10+ seconds to establish
            initial_delay = 10.0
            retry_delay = 2.0
            max_retries = 3
        else:
            # Router-based mode (modern devices) - usually faster (just API state update)
            initial_delay = 1.0
            retry_delay = 0.5
            max_retries = 3

        # Wait initial delay before first check
        await asyncio.sleep(initial_delay)

        # Retry checking if device became a slave
        join_verified = False
        for attempt in range(max_retries):
            await self.player.refresh(full=False)

            if not self.player.is_solo:
                # Device is no longer solo - join succeeded!
                join_verified = True
                _LOGGER.debug(
                    "Join verified for %s after %d attempt(s) (delay=%.1fs)",
                    self.player.host,
                    attempt + 1,
                    initial_delay + (attempt * retry_delay),
                )
                break

            # Still solo - wait and retry
            if attempt < max_retries - 1:  # Don't wait after last attempt
                await asyncio.sleep(retry_delay)

        # Verify the join actually worked by checking device state
        # If still solo after all retries, the join failed (but API returned success)
        if not join_verified:
            # Re-fetch device info after refresh
            slave_info_after = self.player._device_info
            master_info_after = master._device_info

            # Log detailed error - include WiFi Direct info if that mode was used
            used_wifi_direct = (slave_info_after and slave_info_after.needs_wifi_direct_multiroom) or (
                master_info_after and master_info_after.needs_wifi_direct_multiroom
            )
            if used_wifi_direct:
                _LOGGER.error(
                    "WiFi Direct join failed - %s is still solo. "
                    "Slave: model=%s, firmware=%s. Master: model=%s, firmware=%s, ssid=%s, channel=%s. "
                    "Possible causes: SSID/channel mismatch, network issue, or incompatible devices.",
                    self.player.host,
                    slave_info_after.model if slave_info_after else "unknown",
                    slave_info_after.firmware if slave_info_after else "unknown",
                    master_info_after.model if master_info_after else "unknown",
                    master_info_after.firmware if master_info_after else "unknown",
                    master_info_after.ssid if master_info_after else "unknown",
                    master_info_after.wifi_channel if master_info_after else "unknown",
                )
            else:
                _LOGGER.warning(
                    "join_slave() returned success but %s is still solo - join may have failed.",
                    self.player.host,
                )

            # Roll back optimistic local link if verification failed.
            if optimistic_link_applied and optimistic_group is not None and self.player in optimistic_group.slaves:
                optimistic_group.remove_slave(self.player)
                self._notify_all_group_members(optimistic_group)
            return

        if old_group is not None:
            old_group.remove_slave(self.player)

        if master.group is not None:
            master.group.add_slave(self.player)

        # Notify all players in the new group (including the joiner and master)
        self._notify_all_group_members(master.group)

        # Also notify old group members if the joiner left a different group
        if old_group is not None and old_group != master.group:
            self._notify_all_group_members(old_group)

    async def _leave_via_master_kick(self, master: Any) -> None:
        """Leave group by having master kick us (for WiFi Direct mode).

        In WiFi Direct multiroom, slaves move to 10.10.10.x network and
        become unreachable. We find our 10.10.10.x IP by matching UUID
        in master's slave list, then have master kick us.
        """
        slave_uuid = self.player._device_info.uuid if self.player._device_info else None
        if not slave_uuid:
            _LOGGER.warning("No UUID for WiFi Direct kick, falling back to direct Ungroup")
            await self.player.client._request("/httpapi.asp?command=multiroom:Ungroup")
            return

        try:
            slaves_info = await master.client.get_slaves_info()
            for info in slaves_info:
                info_uuid = info.get("uuid", "")
                # Normalize UUIDs for comparison (remove prefix, dashes, lowercase)
                if self._normalize_uuid(info_uuid) == self._normalize_uuid(slave_uuid):
                    slave_ip = info.get("ip")
                    if slave_ip:
                        _LOGGER.info("Kicking via master: %s -> %s", slave_uuid, slave_ip)
                        await master.client.kick_slave(slave_ip)
                        return
            _LOGGER.warning("UUID not found in master's slave list, falling back to direct")
            await self.player.client._request("/httpapi.asp?command=multiroom:Ungroup")
        except Exception as e:
            _LOGGER.warning("Master kick failed: %s, falling back to direct", e)
            await self.player.client._request("/httpapi.asp?command=multiroom:Ungroup")

    @staticmethod
    def _normalize_uuid(uuid: str) -> str:
        """Normalize UUID for comparison."""
        return uuid.lower().replace("uuid:", "").replace("-", "")

    async def _check_if_slave_of_any_master(self) -> str | None:
        """Check if this player is a slave in any known master's slave list.

        Used for WiFi Direct multiroom where slaves report group="0" (solo)
        because they don't know they're in a group. Only the master knows.

        This method:
        1. Gets all known players via internal registry (automatic, no callback needed)
        2. For each known master, checks if their slave list contains our UUID
        3. For potential masters (not solo), queries their slave list directly

        Returns:
            "slave" if found in a master's slave list, None otherwise.
        """
        from .base import PlayerBase

        _LOGGER.debug(
            "Cross-coordinator slave check for %s: uuid=%s, internal_registry_size=%d",
            self.player.host,
            self.player.uuid,
            len(PlayerBase._all_instances),
        )

        if not self.player.uuid:
            _LOGGER.debug(
                "Cannot perform cross-coordinator check - no UUID for %s (device_info not populated yet?)",
                self.player.host,
            )
            return None

        # Use provided callback if available, otherwise use internal registry
        if self.player._all_players_finder:
            try:
                all_players = self.player._all_players_finder()
            except Exception as err:
                _LOGGER.debug("all_players_finder callback failed: %s, using internal registry", err)
                all_players = list(PlayerBase._all_instances)
        else:
            # Use internal registry - this is automatic, no callback needed!
            all_players = list(PlayerBase._all_instances)

        if not all_players:
            _LOGGER.debug("No players found in registry")
            return None

        _LOGGER.debug(
            "Cross-coordinator check: %s checking %d other players for master with our UUID",
            self.player.host,
            len(all_players),
        )

        my_uuid_normalized = self._normalize_uuid(self.player.uuid)

        # Phase 1: Check already-linked group structures (fast, no API calls)
        for other_player in all_players:
            # Skip self
            if other_player is self.player:
                continue

            # Check if this player's group contains us (linked via Player objects)
            group = getattr(other_player, "_group", None)
            if group is None:
                continue

            for slave in getattr(group, "slaves", []):
                slave_uuid = getattr(slave, "uuid", None)
                if slave_uuid and self._normalize_uuid(slave_uuid) == my_uuid_normalized:
                    _LOGGER.debug(
                        "Found self in master %s's linked slave list (uuid: %s)",
                        other_player.host,
                        slave_uuid,
                    )
                    # Ensure we're linked to the master's group
                    if self.player._group != group:
                        group.add_slave(self.player)
                    return "slave"

        # Phase 2: Query potential masters' slave lists (slower, requires API calls)
        # This handles the case where slave refreshes before master has linked it
        _LOGGER.debug(
            "Phase 2: Querying potential masters for slave list membership " "(my_uuid=%s, normalized=%s)",
            self.player.uuid,
            my_uuid_normalized,
        )

        for other_player in all_players:
            # Skip self
            if other_player is self.player:
                continue

            # Skip players we've already checked via group.slaves
            # Only query players that might be masters but haven't linked us yet
            detected_role = getattr(other_player, "_detected_role", "solo")

            # Only query players that are known masters or could potentially be masters
            # A master might not have detected their role yet if they haven't refreshed
            if detected_role not in ("master", "solo"):
                _LOGGER.debug(
                    "Skipping %s (role=%s, not a potential master)",
                    getattr(other_player, "host", "unknown"),
                    detected_role,
                )
                continue

            # For known masters or potential masters, query their slave list
            client = getattr(other_player, "client", None)
            if client is None:
                _LOGGER.debug(
                    "Skipping %s (no client available)",
                    getattr(other_player, "host", "unknown"),
                )
                continue

            other_host = getattr(other_player, "host", "unknown")
            try:
                # Query the device's slave list directly
                _LOGGER.debug(
                    "Querying slave list from potential master %s (role=%s)",
                    other_host,
                    detected_role,
                )
                slaves_info = await client.get_slaves_info()

                if not slaves_info:
                    _LOGGER.debug(
                        "Potential master %s has no slaves in its list",
                        other_host,
                    )
                    continue

                _LOGGER.debug(
                    "Master %s has %d slaves: %s",
                    other_host,
                    len(slaves_info),
                    [s.get("uuid", "no-uuid") for s in slaves_info],
                )

                for slave_info in slaves_info:
                    slave_uuid = slave_info.get("uuid", "")
                    if slave_uuid:
                        normalized_slave = self._normalize_uuid(slave_uuid)
                        if normalized_slave == my_uuid_normalized:
                            _LOGGER.info(
                                "Cross-coordinator: Found self in %s's slave list via API query "
                                "(uuid: %s, normalized: %s)",
                                other_host,
                                slave_uuid,
                                normalized_slave,
                            )
                            # Link ourselves to this master's group
                            group = getattr(other_player, "_group", None)
                            if group is None:
                                # Create group on master if it doesn't exist
                                from ..group import Group as GroupClass

                                group = GroupClass(other_player)
                                other_player._group = group
                                other_player._detected_role = "master"

                            if self.player not in getattr(group, "slaves", []):
                                group.add_slave(self.player)

                            return "slave"
                        else:
                            _LOGGER.debug(
                                "UUID mismatch with slave in %s's list: "
                                "slave_uuid=%s (normalized=%s) vs my_uuid=%s (normalized=%s)",
                                other_host,
                                slave_uuid,
                                normalized_slave,
                                self.player.uuid,
                                my_uuid_normalized,
                            )
            except Exception as err:
                _LOGGER.debug(
                    "Failed to query slave list from %s: %s",
                    other_host,
                    err,
                )
                continue

        _LOGGER.debug(
            "Cross-coordinator check complete: %s not found in any master's slave list",
            self.player.host,
        )
        return None

    async def leave_group(self) -> None:
        """Leave the current group.

        This method works for all player roles:
        - Solo: No-op (idempotent, returns immediately)
        - Master: Disbands the entire group (all players become solo)
        - Slave: Leaves the group (master and other slaves remain grouped)

        The integration/caller doesn't need to check player role - just call this method
        and it will do the right thing.
        """
        # Idempotent: if already solo, nothing to do
        if self.player.is_solo:
            _LOGGER.debug("Player %s is already solo, nothing to do", self.player.host)
            return

        group = self.player._group
        if group is None:
            # Shouldn't happen (is_solo should have caught this), but handle gracefully
            _LOGGER.warning("Player %s reports non-solo but has no group reference", self.player.host)
            return

        master = group.master if group else None

        if self.player.is_master:
            # Master leaving = disband the entire group
            _LOGGER.debug("Player %s is master, disbanding group", self.player.host)
            await group.disband()
        else:
            # Slave leaving = just leave the group
            _LOGGER.debug("Player %s is slave, leaving group", self.player.host)

            # WiFi Direct mode: slave is on 10.10.10.x, must kick via master
            if self.player._device_info and self.player._device_info.needs_wifi_direct_multiroom and master:
                await self._leave_via_master_kick(master)
            else:
                await self.player.client._request("/httpapi.asp?command=multiroom:Ungroup")

            group.remove_slave(self.player)
            # The leaving slave is no longer part of the group, so notify it explicitly.
            # This ensures integrations immediately see the post-leave solo state.
            if self.player._on_state_changed:
                try:
                    self.player._on_state_changed()
                except Exception as err:
                    _LOGGER.debug("Error calling on_state_changed callback for %s: %s", self.player.host, err)

            if len(group.slaves) == 0:
                _LOGGER.debug("Group is now empty, auto-disbanding (master: %s)", master.host if master else "unknown")
                await group.disband()
            else:
                # Notify remaining members after state mutation so callbacks observe
                # post-operation group membership/roles.
                self._notify_all_group_members(group)

    async def get_master_name(self) -> str | None:
        """Get master device name.

        Returns:
            Master device name if available, None otherwise.
        """

        # First try: Use Group object if available
        if (
            self.player._group is not None
            and self.player._group.master is not None
            and self.player._group.master != self.player
        ):
            if self.player._group.master._device_info is None or self.player._group.master.name is None:
                try:
                    await self.player._group.master.refresh()
                except Exception:
                    pass
            return self.player._group.master.name or self.player._group.master.host

        # Second try: Use master_ip from device_info/status
        device_info = self.player._device_info
        status = self.player._status_model
        if device_info:
            master_ip = device_info.master_ip or (status.master_ip if status else None)
            if master_ip:
                master_client = None
                try:
                    from ..client import WiiMClient

                    master_client = WiiMClient(master_ip)
                    master_name = await master_client.get_device_name()
                    return master_name
                except Exception as e:
                    _LOGGER.debug("Failed to get master name from IP %s: %s", master_ip, e)
                    return master_ip
                finally:
                    if master_client is not None:
                        try:
                            await master_client.close()
                        except Exception:
                            pass

        return None

    def propagate_metadata_to_slaves(self) -> None:
        """Propagate metadata from master to all linked slaves.

        This ensures slaves always have the latest metadata from the master,
        even when the master's metadata changes via UPnP or refresh.
        """
        if not self.player.is_master or not self.player._group or not self.player._group.slaves:
            return

        if not self.player._status_model:
            return

        master_status = self.player._status_model

        for slave in self.player._group.slaves:
            if not slave._status_model:
                continue

            # Copy audio-quality metadata (from getMetaInfo) so slave properties like
            # media_bit_rate/sample_rate/bit_depth work consistently in groups.
            # This is separate from the StateSynchronizer fields (title/artist/album/image_url).
            slave._metadata = self.player._metadata

            # Copy ALL playback metadata from master to slave
            slave._status_model.title = master_status.title
            slave._status_model.artist = master_status.artist
            slave._status_model.album = master_status.album
            slave._status_model.entity_picture = master_status.entity_picture
            slave._status_model.cover_url = master_status.cover_url
            slave._status_model.play_state = master_status.play_state
            slave._status_model.position = master_status.position
            slave._status_model.duration = master_status.duration

            # Update state synchronizer with master's metadata
            # Use source="propagated" to distinguish from slave's own device state
            # This helps conflict resolution prefer master's authoritative metadata
            slave._state_synchronizer.update_from_http(
                {
                    "title": master_status.title,
                    "artist": master_status.artist,
                    "album": master_status.album,
                    "image_url": master_status.entity_picture or master_status.cover_url,
                    "play_state": master_status.play_state,
                    "position": master_status.position,
                    "duration": master_status.duration,
                },
                source="propagated",
                force_metadata_update=True,
            )

            # Trigger callback on slave so HA integration updates
            if slave._on_state_changed:
                try:
                    slave._on_state_changed()
                except Exception as err:
                    _LOGGER.debug("Error calling on_state_changed callback for slave %s: %s", slave.host, err)

            _LOGGER.debug(
                "Propagated metadata from master %s to slave %s: '%s' by %s",
                self.player.host,
                slave.host,
                master_status.title,
                master_status.artist,
            )
