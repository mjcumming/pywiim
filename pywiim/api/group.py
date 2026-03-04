"""Multi-room (group) helpers for WiiM HTTP client.

All networking is delegated to the base client; this mix-in keeps only the
minimal state necessary for helper convenience (`_group_master` and
`_group_slaves`).  No attempt is made to be 100% authoritative – callers should
still refresh via `get_multiroom_status` periodically.
"""

from __future__ import annotations

import binascii
import logging
import time
from typing import Any

from ..models import DeviceGroupInfo, DeviceInfo, GroupDeviceState, GroupState
from .constants import (
    API_ENDPOINT_GROUP_EXIT,
    API_ENDPOINT_GROUP_KICK,
    API_ENDPOINT_GROUP_SLAVE_MUTE,
    API_ENDPOINT_GROUP_SLAVES,
)

_LOGGER = logging.getLogger(__name__)


def _needs_wifi_direct_mode(device_info: DeviceInfo | None) -> bool:
    """Determine if device needs WiFi Direct mode for multiroom grouping.

    Devices with firmware < 4.2.8020 use WiFi Direct mode (older LinkPlay protocol).
    Modern devices (firmware >= 4.2.8020) use router-based mode.

    Args:
        device_info: Device information to check, or None.

    Returns:
        True if WiFi Direct mode is needed, False for router-based (default).
    """
    if device_info is None:
        return False

    return device_info.needs_wifi_direct_multiroom


class GroupAPI:
    """Helpers for creating / managing LinkPlay multi-room groups.

    This mixin provides methods for managing multi-room groups, including
    creating groups, joining/leaving groups, and managing slave devices.
    """

    # --------------------------
    # internal convenience state
    # --------------------------
    _group_master: str | None = None
    _group_slaves: list[str] = []

    # ------------------------------------------------------------------
    # WiFi Direct helpers (for Gen1 devices)
    # ------------------------------------------------------------------

    async def get_wifi_direct_info(self) -> tuple[str | None, int | None]:
        """Get SSID and WiFi channel for WiFi Direct multiroom mode.

        This method fetches the SSID and WiFi channel from the device's
        status endpoint, following the pattern from the old Linkplay
        integration. Gen1 devices (wmrm_version 2.0) require this info
        for WiFi Direct multiroom joining.

        The old Linkplay code:
        - Uses getStatus for HTTP devices, getStatusEx for HTTPS
        - Gets ssid (lowercase) and WifiChannel (PascalCase) fields
        - SSID is returned as plain text (caller must hex-encode)

        Returns:
            Tuple of (ssid, wifi_channel). Either may be None if not available.
        """
        import logging

        _logger = logging.getLogger(__name__)

        ssid: str | None = None
        wifi_channel: int | None = None

        # Try getStatusEx first (primary endpoint for modern devices)
        try:
            response = await self._request("/httpapi.asp?command=getStatusEx")  # type: ignore[attr-defined]
            if isinstance(response.parsed, dict):
                ssid = response.parsed.get("ssid")
                wifi_channel = response.parsed.get("WifiChannel")
                if ssid or wifi_channel:
                    _logger.debug(
                        "get_wifi_direct_info: Got from getStatusEx: ssid=%s, channel=%s",
                        ssid,
                        wifi_channel,
                    )
                    return ssid, wifi_channel
        except Exception as e:
            _logger.debug("get_wifi_direct_info: getStatusEx failed: %s", e)

        # Try getStatus as fallback (used by old Linkplay code for HTTP devices)
        try:
            response = await self._request("/httpapi.asp?command=getStatus")  # type: ignore[attr-defined]
            if isinstance(response.parsed, dict):
                ssid = response.parsed.get("ssid")
                wifi_channel = response.parsed.get("WifiChannel")
                if ssid or wifi_channel:
                    _logger.debug(
                        "get_wifi_direct_info: Got from getStatus: ssid=%s, channel=%s",
                        ssid,
                        wifi_channel,
                    )
                    return ssid, wifi_channel
        except Exception as e:
            _logger.debug("get_wifi_direct_info: getStatus failed: %s", e)

        _logger.warning(
            "get_wifi_direct_info: Could not get SSID/WifiChannel from device. "
            "WiFi Direct multiroom joining may fail for Gen1 devices."
        )
        return None, None

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    async def get_multiroom_status(self) -> dict[str, Any]:
        """Return the `multiroom` section from `getStatusEx` and update caches.

        This method fetches the current multiroom status and updates internal
        caches for `_group_master` and `_group_slaves`.

        If the multiroom section is null/empty from getStatusEx, this method will
        query the getSlaveList endpoint to detect if this device is actually a
        master with slaves (fallback for firmware that doesn't populate multiroom).

        Returns:
            Dictionary containing multiroom status information.

        Raises:
            WiiMError: If the request fails.
        """
        import logging

        _logger = logging.getLogger(__name__)

        status = await self.get_status()  # type: ignore[attr-defined]
        multiroom = status.get("multiroom", {}) if isinstance(status, dict) else {}

        # If multiroom is null/empty, try getSlaveList as fallback
        # Some firmware versions don't populate the multiroom field in getStatusEx
        if not multiroom or multiroom.get("slaves") is None:
            _logger.debug("get_multiroom_status: multiroom section is null/empty, checking getSlaveList as fallback")
            try:
                # Query getSlaveList endpoint directly
                slaves_resp = await self._request(API_ENDPOINT_GROUP_SLAVES)  # type: ignore[attr-defined]
                _logger.debug("get_multiroom_status: getSlaveList response: %s", slaves_resp.parsed or slaves_resp.raw)

                if isinstance(slaves_resp.parsed, dict):
                    # Extract slave count and list
                    slave_count = slaves_resp.parsed.get("slaves", 0)
                    slave_list = slaves_resp.parsed.get("slave_list", [])
                    wmrm_version = slaves_resp.parsed.get("wmrm_version")

                    # Build multiroom dict from getSlaveList data
                    multiroom = {
                        "slaves": slave_count,
                        "slave_list": slave_list,
                    }
                    if wmrm_version:
                        multiroom["wmrm_version"] = wmrm_version

                    _logger.debug(
                        "get_multiroom_status: Populated multiroom from getSlaveList: %d slaves",
                        slave_count,
                    )
            except Exception as err:
                _logger.debug("get_multiroom_status: Failed to query getSlaveList: %s", err)
                # Keep empty multiroom dict on error

        self._group_master = multiroom.get("master")
        self._group_slaves = multiroom.get("slaves", []) or []
        return multiroom

    # ------------------------------------------------------------------
    # Role helpers
    # ------------------------------------------------------------------

    @property
    def is_master(self) -> bool:
        """Return True if this device is the group master."""
        return bool(self._group_master == self.host)  # type: ignore[attr-defined]

    @property
    def is_slave(self) -> bool:
        """Return True if this device is a group slave."""
        return self._group_master is not None and not self.is_master

    @property
    def group_master(self) -> str | None:
        """Return the IP address of the group master, or None if not in a group."""
        return self._group_master

    @property
    def group_slaves(self) -> list[str]:
        """Return list of slave IP addresses (only valid if this device is master)."""
        return self._group_slaves if self.is_master else []

    # ------------------------------------------------------------------
    # Group operations (HTTP wrappers)
    # ------------------------------------------------------------------

    async def create_group(self) -> None:
        """Prepare this device to become master (no HTTP call required).

        This method sets internal state to mark this device as a master.
        Other devices can then join this device to form a group.
        """
        self._group_master = self.host  # type: ignore[attr-defined]
        self._group_slaves = []

    async def delete_group(self) -> None:
        """Disband the multiroom group (master operation).

        Raises:
            RuntimeError: If not part of a multiroom group.
            WiiMError: If the request fails.
        """
        if self._group_master is None:
            raise RuntimeError("Not part of a multiroom group")
        await self._request(API_ENDPOINT_GROUP_EXIT)  # type: ignore[attr-defined]
        self._group_master = None
        self._group_slaves = []

    async def join_slave(
        self,
        master_ip: str,
        master_device_info: DeviceInfo | None = None,
        master_ssid: str | None = None,
        master_wifi_channel: int | None = None,
    ) -> None:
        """Join the group hosted by *master_ip*.

        Supports both router-based and WiFi Direct modes:
        - Router-based mode: Used for modern devices (wmrm_version 4.2, firmware >= 4.2.8020)
        - WiFi Direct mode: Used for legacy devices (wmrm_version 2.0, firmware < 4.2.8020)

        Args:
            master_ip: IP address of the master device to join.
            master_device_info: Optional device info for the master device.
                If provided, used to determine join mode (WiFi Direct vs router-based).
                If None, defaults to router-based mode.
            master_ssid: Optional SSID for WiFi Direct mode (overrides device_info.ssid).
                Used when SSID is fetched separately from getStatus endpoint.
            master_wifi_channel: Optional WiFi channel for WiFi Direct mode.
                Used when channel is fetched separately from getStatus endpoint.

        Raises:
            WiiMError: If the request fails.
        """
        import logging

        _logger = logging.getLogger(__name__)

        # Determine if WiFi Direct mode is needed
        use_wifi_direct = _needs_wifi_direct_mode(master_device_info)

        if use_wifi_direct:
            # WiFi Direct mode for Gen1/legacy devices
            # Get SSID and WiFi channel - prefer explicit parameters, then device_info
            ssid = master_ssid or (master_device_info.ssid if master_device_info else None) or ""
            wifi_channel = master_wifi_channel or (master_device_info.wifi_channel if master_device_info else None) or 1

            if not ssid:
                _logger.warning(
                    "WiFi Direct mode required but SSID not available from master device %s. "
                    "Falling back to router-based mode. This may fail for Gen1 devices. "
                    "Ensure master device has ssid field in getStatusEx response.",
                    master_ip,
                )
                use_wifi_direct = False
            else:
                # Encode SSID as hex (as done in old Linkplay library)
                try:
                    ssid_hex = binascii.hexlify(ssid.encode("utf-8")).decode()
                    _logger.info(
                        "Using WiFi Direct mode for Gen1 device join: master=%s (%s), "
                        "ssid=%s (hex=%s), channel=%s, wmrm_version=%s, firmware=%s",
                        master_ip,
                        master_device_info.name if master_device_info else "unknown",
                        ssid,
                        ssid_hex,
                        wifi_channel,
                        master_device_info.wmrm_version if master_device_info else "unknown",
                        master_device_info.firmware if master_device_info else "unknown",
                    )
                    command = f"ConnectMasterAp:ssid={ssid_hex}:ch={wifi_channel}:auth=OPEN:encry=NONE:pwd=:chext=0"
                except Exception as e:
                    _logger.error(
                        "Failed to encode SSID for WiFi Direct mode: %s. Falling back to router-based mode.",
                        e,
                    )
                    use_wifi_direct = False

        if not use_wifi_direct:
            # Router-based mode (default for modern devices)
            _logger.debug(
                "Using router-based mode for join: master=%s, wmrm_version=%s, firmware=%s",
                master_ip,
                master_device_info.wmrm_version if master_device_info else "unknown",
                master_device_info.firmware if master_device_info else "unknown",
            )
            command = f"ConnectMasterAp:JoinGroupMaster:eth{master_ip}:wifi0.0.0.0"

        endpoint = f"/httpapi.asp?command={command}"
        _logger.debug("Sending join command to slave device: endpoint=%s", endpoint)
        await self._request(endpoint)  # type: ignore[attr-defined]
        self._group_master = master_ip
        self._group_slaves = []

    async def leave_group(self) -> None:
        """Leave the current multiroom group.

        Raises:
            WiiMError: If the request fails.
        """
        await self._request(API_ENDPOINT_GROUP_EXIT)  # type: ignore[attr-defined]
        self._group_master = None
        self._group_slaves = []

    # ------------------------------------------------------------------
    # Slave management (master-only helpers)
    # ------------------------------------------------------------------

    async def get_slaves(self) -> list[str]:
        """Get list of slave device IP addresses (master only).

        Returns:
            List of slave device IP addresses.

        Raises:
            WiiMError: If the request fails.
        """
        import logging

        _logger = logging.getLogger(__name__)
        resp = await self._request(API_ENDPOINT_GROUP_SLAVES)  # type: ignore[attr-defined]
        _logger.debug("get_slaves() raw response: %s", resp.parsed or resp.raw)

        # The API returns "slave_list" (array of objects) and "slaves" (count)
        # We need to extract from "slave_list"
        if isinstance(resp.parsed, dict):
            # Try slave_list first (the actual list of slave objects)
            data = resp.parsed.get("slave_list")
            # Fallback to "slaves" if slave_list is missing or not a list
            if not isinstance(data, list):
                data = resp.parsed.get("slaves", [])
        else:
            data = []

        _logger.debug("get_slaves() extracted data: %s (type: %s)", data, type(data).__name__)
        if isinstance(data, list):
            out: list[str] = []
            for item in data:
                if isinstance(item, dict):
                    ip = item.get("ip", "")
                    if ip:  # Only add non-empty IPs
                        out.append(ip)
                else:
                    ip_str = str(item).strip()
                    if ip_str:  # Only add non-empty strings
                        out.append(ip_str)
            _logger.debug("get_slaves() returning %d slaves: %s", len(out), out)
            return out
        _logger.debug("get_slaves() data is not a list, returning empty")
        return []

    async def get_slaves_info(self) -> list[dict]:
        """Get full slave info including UUID (master only).

        Used for WiFi Direct multiroom where slaves move to 10.10.10.x
        and must be matched by UUID to find their internal IP.

        Returns:
            List of slave dicts with ip, uuid, name, etc.
        """
        resp = await self._request(API_ENDPOINT_GROUP_SLAVES)  # type: ignore[attr-defined]
        if isinstance(resp.parsed, dict):
            slave_list = resp.parsed.get("slave_list", [])
            if isinstance(slave_list, list):
                return slave_list
        return []

    async def kick_slave(self, slave_ip: str) -> None:
        """Remove a slave device from the group (master only).

        Args:
            slave_ip: IP address of the slave device to remove.

        Raises:
            RuntimeError: If this device is not the group master.
            WiiMError: If the request fails.
        """
        if not self.is_master:
            raise RuntimeError("Not a group master")
        await self._request(f"{API_ENDPOINT_GROUP_KICK}{slave_ip}")  # type: ignore[attr-defined]

    async def mute_slave(self, slave_ip: str, mute: bool) -> None:
        """Mute or unmute a slave device (master only).

        Args:
            slave_ip: IP address of the slave device.
            mute: True to mute, False to unmute.

        Raises:
            RuntimeError: If this device is not the group master.
            WiiMError: If the request fails.
        """
        if not self.is_master:
            raise RuntimeError("Not a group master")
        await self._request(f"{API_ENDPOINT_GROUP_SLAVE_MUTE}{slave_ip}:{1 if mute else 0}")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Group state helpers
    # ------------------------------------------------------------------

    async def get_device_group_info(self) -> DeviceGroupInfo:
        """Get this device's view of its group membership.

        This method queries the device to determine its role in a multiroom
        group and returns structured information about the group.

        Returns:
            DeviceGroupInfo with role, master info, and slave list (if master).

        Note:
            For slave devices, `master_host` will typically be None due to a
            WiiM API limitation - slaves only receive the master's UUID, not
            its IP address. Use the Player.group object to access the master
            when you need the full Player reference.

        Raises:
            WiiMError: If the request fails.
        """
        import logging

        _logger = logging.getLogger(__name__)

        # Get device info to check if we're a slave
        device_host = self.host  # type: ignore[attr-defined]
        device_uuid: str | None = None
        status: dict | None = None
        multiroom: dict = {}
        try:
            device_info = await self.get_device_info_model()  # type: ignore[attr-defined]
            group_field = device_info.group or "0"
            master_uuid = device_info.master_uuid
            master_ip = device_info.master_ip
            device_uuid = device_info.uuid
        except Exception:
            device_info = None
            # Fallback to status if device_info fails
            status = await self.get_status()  # type: ignore[attr-defined]
            group_field = status.get("group", "0") or "0"
            master_uuid = status.get("master_uuid")
            master_ip = status.get("master_ip")
            device_uuid = status.get("uuid")

        # Also check multiroom section for master IP (some devices only report it there)
        # This is important for slave devices that may not have master_ip in device info
        if status is None:
            try:
                status = await self.get_status()  # type: ignore[attr-defined]
            except Exception:
                status = {}
        multiroom = status.get("multiroom", {}) if status else {}

        # Use multiroom.master as fallback for master_ip
        if not master_ip and multiroom:
            multiroom_master = multiroom.get("master")
            if multiroom_master:
                master_ip = multiroom_master
                _logger.debug("get_device_group_info: Got master_ip from multiroom section: %s", master_ip)

        # Step 1: Check if we're a slave (group != "0" and has master info pointing to another device)
        # Check if master info points to this device (then it's the master, not a slave)
        if group_field != "0" and (master_uuid or master_ip):
            is_master_self = (master_ip and device_host and master_ip == device_host) or (
                master_uuid and device_uuid and master_uuid == device_uuid
            )
            if not is_master_self:
                # Master info points to another device - we're a slave
                _logger.debug(
                    "get_device_group_info: Detected SLAVE (group=%s, master_ip=%s, master_uuid=%s)",
                    group_field,
                    master_ip,
                    master_uuid,
                )
                return DeviceGroupInfo(
                    role="slave",
                    master_host=master_ip,
                    master_uuid=master_uuid,
                    slave_hosts=[],
                    slave_uuids=[],
                    slave_count=0,
                )
            # else: master info points to self, continue to check if we have slaves

        # Step 2: Not a slave - check getSlaveList to determine master vs solo
        # Extract both IPs and UUIDs for WiFi Direct multiroom support
        # (WiFi Direct slaves use internal 10.10.10.x IPs, need UUID for matching)
        slave_ips: list[str] = []
        slave_uuids: list[str] = []

        # First try to get slaves from multiroom status (if available) as optimization
        if multiroom:
            # Extract slaves from multiroom status - try slave_list first, then slaves
            slaves_list = multiroom.get("slave_list", multiroom.get("slaves", []))
            if isinstance(slaves_list, list):
                for item in slaves_list:
                    if isinstance(item, dict):
                        ip = item.get("ip", "")
                        uuid = item.get("uuid", "")
                        if ip:
                            slave_ips.append(ip)
                            # Normalize UUID (remove "uuid:" prefix if present)
                            slave_uuids.append(uuid.replace("uuid:", "") if uuid else "")
                    elif item:
                        slave_ips.append(str(item))
                        slave_uuids.append("")

        # If no slaves from status, try get_slaves_info() API call to get IPs and UUIDs
        if not slave_ips:
            try:
                slaves_info = await self.get_slaves_info()
                for slave in slaves_info:
                    ip = slave.get("ip", "")
                    uuid = slave.get("uuid", "")
                    if ip:
                        slave_ips.append(ip)
                        # Normalize UUID (remove "uuid:" prefix if present)
                        slave_uuids.append(uuid.replace("uuid:", "") if uuid else "")
            except Exception as e:
                _logger.debug("get_device_group_info: get_slaves_info() failed: %s", e)

        if slave_ips and len(slave_ips) > 0:
            # Has slaves - we're a master
            _logger.debug(
                "get_device_group_info: Detected MASTER via get_slaves_info() - %d slaves: %s (uuids: %s)",
                len(slave_ips),
                slave_ips,
                slave_uuids,
            )
            return DeviceGroupInfo(
                role="master",
                master_host=self.host,  # type: ignore[attr-defined]
                master_uuid=None,
                slave_hosts=slave_ips,
                slave_uuids=slave_uuids,
                slave_count=len(slave_ips),
            )
        else:
            # No slaves - we're solo
            _logger.debug("get_device_group_info: Detected SOLO (get_slaves_info() returned empty)")
            return DeviceGroupInfo(
                role="solo",
                master_host=None,
                master_uuid=None,
                slave_hosts=[],
                slave_uuids=[],
                slave_count=0,
            )

    async def get_group_state(
        self,
        slave_clients: list[Any] | None = None,
        include_slave_details: bool = False,
    ) -> GroupState:
        """Get complete group state (master + all slaves).

        This method builds a complete GroupState by querying the master device
        (authoritative source) and optionally all slave devices. Only works when
        called on the master.

        State Flow Architecture:
        - Master Physical Player → Group Player → Slaves
        - Master is authoritative for playback state (play_state, position, metadata)
        - Volume/mute is aggregated from all devices (MAX volume, ALL muted)
        - Slaves receive synced playback state from master via LinkPlay protocol

        Args:
            slave_clients: Optional list of WiiMClient instances for slave devices.
                If not provided, only master state is included.
            include_slave_details: If True, query each slave for detailed state.
                If False, only include slave IPs from master's slave list.

        Returns:
            GroupState with complete group information:
            - Playback state from master (authoritative)
            - Volume/mute aggregated from all devices (MAX volume, ALL muted)
            - Individual device states for master and slaves

        Raises:
            RuntimeError: If this device is not the group master.
            WiiMError: If the request fails.
        """
        if not self.is_master:
            raise RuntimeError("get_group_state() can only be called on the master device")

        now = time.time()

        # Get master state
        master_status = await self.get_player_status_model()  # type: ignore[attr-defined]

        # Get slave list
        slave_hosts = await self.get_slaves()

        # Build master device state
        master_state = GroupDeviceState(
            host=self.host,  # type: ignore[attr-defined]
            role="master",
            volume=master_status.volume,
            mute=master_status.mute,
            play_state=master_status.play_state,
            position=master_status.position,
            duration=master_status.duration,
            source=master_status.source,
            title=master_status.title,
            album=master_status.album,
            last_updated=now,
        )

        # Build slave states
        slave_states: list[GroupDeviceState] = []

        if include_slave_details and slave_clients:
            # Query each slave for detailed state
            import asyncio

            async def get_slave_state(client: Any, host: str) -> GroupDeviceState | None:
                """Get state from a slave device."""
                try:
                    status = await client.get_player_status_model()
                    return GroupDeviceState(
                        host=host,
                        role="slave",
                        volume=status.volume,
                        mute=status.mute,
                        play_state=status.play_state,
                        position=status.position,
                        duration=status.duration,
                        source=status.source,
                        title=status.title,
                        album=status.album,
                        last_updated=now,
                    )
                except Exception:
                    # Slave query failed, return None
                    return None

            # Query all slaves in parallel
            tasks = [
                get_slave_state(client, host)
                for client, host in zip(slave_clients, slave_hosts, strict=False)
                if client is not None
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Filter out None and exceptions
            for result in results:
                if isinstance(result, GroupDeviceState):
                    slave_states.append(result)
        else:
            # Just create placeholder states with IPs
            for host in slave_hosts:
                slave_states.append(
                    GroupDeviceState(
                        host=host,
                        role="slave",
                        last_updated=now,
                    )
                )

        # Calculate group volume/mute (MAX volume, ALL muted)
        # Note: Volume/mute is per-device but aggregated for group view
        volumes = [s.volume for s in [master_state] + slave_states if s.volume is not None]
        mutes = [s.mute for s in [master_state] + slave_states if s.mute is not None]

        group_volume = max(volumes) if volumes else None
        group_muted = all(mutes) if mutes else None

        # Build GroupState following the architecture:
        # Master Physical Player (authoritative) → Group Player (aggregated) → Slaves (synced)
        return GroupState(
            master_host=self.host,  # type: ignore[attr-defined]
            slave_hosts=slave_hosts,
            master_state=master_state,
            slave_states=slave_states,
            # Playback state from master (authoritative - synced to all slaves)
            play_state=master_status.play_state,
            position=master_status.position,
            duration=master_status.duration,
            source=master_status.source,
            title=master_status.title,
            artist=master_status.artist,
            album=master_status.album,
            # Volume/mute aggregated from all devices (MAX volume, ALL muted)
            volume_level=group_volume,
            is_muted=group_muted,
            created_at=now,  # Could track actual creation time if available
            last_updated=now,
        )
