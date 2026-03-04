"""Unit tests for GroupAPI mixin.

Tests multiroom group operations, role detection, and slave management.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pywiim.api.base import ApiResponse
from pywiim.exceptions import WiiMError
from pywiim.models import DeviceGroupInfo, DeviceInfo


class TestGroupAPIStatus:
    """Test GroupAPI status methods."""

    @pytest.mark.asyncio
    async def test_get_multiroom_status(self, mock_client):
        """Test getting multiroom status."""
        mock_status = {
            "multiroom": {
                "master": "192.168.1.100",
                "slaves": ["192.168.1.101", "192.168.1.102"],
            }
        }
        mock_client.get_status = AsyncMock(return_value=mock_status)
        # host is a property from base client
        type(mock_client).host = "192.168.1.100"

        result = await mock_client.get_multiroom_status()

        assert result == mock_status["multiroom"]
        assert mock_client._group_master == "192.168.1.100"
        assert mock_client._group_slaves == ["192.168.1.101", "192.168.1.102"]

    @pytest.mark.asyncio
    async def test_get_multiroom_status_solo(self, mock_client):
        """Test getting multiroom status when solo."""
        mock_status = {"multiroom": {}}
        mock_client.get_status = AsyncMock(return_value=mock_status)
        # Mock getSlaveList fallback for solo device
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed={"slaves": 0, "slave_list": []}, raw=None))
        type(mock_client).host = "192.168.1.100"

        result = await mock_client.get_multiroom_status()

        # Solo device returns empty slave list from getSlaveList fallback
        assert result == {"slaves": 0, "slave_list": []}
        assert mock_client._group_master is None
        assert mock_client._group_slaves == []


class TestGroupAPIRole:
    """Test GroupAPI role properties."""

    def test_is_master_true(self, mock_client):
        """Test is_master property when device is master."""
        mock_client._group_master = "192.168.1.100"
        type(mock_client).host = "192.168.1.100"

        assert mock_client.is_master is True

    def test_is_master_false(self, mock_client):
        """Test is_master property when device is not master."""
        mock_client._group_master = "192.168.1.101"
        type(mock_client).host = "192.168.1.100"

        assert mock_client.is_master is False

    def test_is_master_no_group(self, mock_client):
        """Test is_master property when not in group."""
        mock_client._group_master = None
        type(mock_client).host = "192.168.1.100"

        assert mock_client.is_master is False

    def test_is_slave_true(self, mock_client):
        """Test is_slave property when device is slave."""
        mock_client._group_master = "192.168.1.101"
        type(mock_client).host = "192.168.1.100"

        assert mock_client.is_slave is True

    def test_is_slave_false(self, mock_client):
        """Test is_slave property when device is master."""
        mock_client._group_master = "192.168.1.100"
        type(mock_client).host = "192.168.1.100"

        assert mock_client.is_slave is False

    def test_is_slave_no_group(self, mock_client):
        """Test is_slave property when not in group."""
        mock_client._group_master = None
        type(mock_client).host = "192.168.1.100"

        assert mock_client.is_slave is False

    def test_group_master_property(self, mock_client):
        """Test group_master property."""
        mock_client._group_master = "192.168.1.101"

        assert mock_client.group_master == "192.168.1.101"

    def test_group_master_property_none(self, mock_client):
        """Test group_master property when None."""
        mock_client._group_master = None

        assert mock_client.group_master is None

    def test_group_slaves_property_master(self, mock_client):
        """Test group_slaves property when master."""
        mock_client._group_master = "192.168.1.100"
        mock_client._group_slaves = ["192.168.1.101", "192.168.1.102"]
        type(mock_client).host = "192.168.1.100"

        assert mock_client.group_slaves == ["192.168.1.101", "192.168.1.102"]

    def test_group_slaves_property_slave(self, mock_client):
        """Test group_slaves property when slave."""
        mock_client._group_master = "192.168.1.101"
        mock_client._group_slaves = ["192.168.1.102"]
        type(mock_client).host = "192.168.1.100"

        assert mock_client.group_slaves == []


class TestGroupAPIOperations:
    """Test GroupAPI group operations."""

    @pytest.mark.asyncio
    async def test_create_group(self, mock_client):
        """Test creating a group."""
        type(mock_client).host = "192.168.1.100"

        await mock_client.create_group()

        assert mock_client._group_master == "192.168.1.100"
        assert mock_client._group_slaves == []

    @pytest.mark.asyncio
    async def test_delete_group(self, mock_client):
        """Test deleting a group."""
        mock_client._group_master = "192.168.1.100"
        mock_client._group_slaves = ["192.168.1.101"]
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.delete_group()

        assert mock_client._group_master is None
        assert mock_client._group_slaves == []
        mock_client._request.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_group_not_in_group(self, mock_client):
        """Test deleting group when not in group."""
        mock_client._group_master = None

        with pytest.raises(RuntimeError, match="Not part of a multiroom group"):
            await mock_client.delete_group()

    @pytest.mark.asyncio
    async def test_join_slave(self, mock_client):
        """Test joining as slave with router-based mode (default)."""
        master_ip = "192.168.1.101"
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))
        type(mock_client).host = "192.168.1.100"

        await mock_client.join_slave(master_ip)

        assert mock_client._group_master == master_ip
        assert mock_client._group_slaves == []
        mock_client._request.assert_called_once()
        # Verify router-based mode command format
        call_args = mock_client._request.call_args[0][0]
        assert f"ConnectMasterAp:JoinGroupMaster:eth{master_ip}:wifi0.0.0.0" in call_args

    @pytest.mark.asyncio
    async def test_join_slave_wifi_direct_mode(self, mock_client):
        """Test joining as slave with WiFi Direct mode for Gen1 devices."""
        import binascii

        master_ip = "192.168.1.101"
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))
        type(mock_client).host = "192.168.1.100"

        from pywiim.models import DeviceInfo

        # Create master device info for Gen1 device (wmrm_version 2.0) with SSID and channel
        master_device_info = DeviceInfo(
            uuid="master-uuid",
            model="Audio Pro A26",
            wmrm_version="2.0",
            firmware="4.2.5000",  # Old firmware < 4.2.8020
            ssid="MyWiFiNetwork",
            wifi_channel=6,
        )

        await mock_client.join_slave(master_ip, master_device_info=master_device_info)

        assert mock_client._group_master == master_ip
        assert mock_client._group_slaves == []
        mock_client._request.assert_called_once()

        # Verify WiFi Direct mode command format
        call_args = mock_client._request.call_args[0][0]
        ssid_hex = binascii.hexlify(b"MyWiFiNetwork").decode()
        assert f"ConnectMasterAp:ssid={ssid_hex}:ch=6:auth=OPEN:encry=NONE:pwd=:chext=0" in call_args

    @pytest.mark.asyncio
    async def test_join_slave_wifi_direct_mode_missing_ssid(self, mock_client):
        """Test WiFi Direct mode fallback when SSID is missing."""
        master_ip = "192.168.1.101"
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))
        type(mock_client).host = "192.168.1.100"

        from pywiim.models import DeviceInfo

        # Create master device info for Gen1 device but without SSID
        master_device_info = DeviceInfo(
            uuid="master-uuid",
            model="Audio Pro A26",
            wmrm_version="2.0",
            firmware="4.2.5000",
            ssid=None,  # Missing SSID
            wifi_channel=6,
        )

        await mock_client.join_slave(master_ip, master_device_info=master_device_info)

        assert mock_client._group_master == master_ip
        assert mock_client._group_slaves == []
        mock_client._request.assert_called_once()

        # Should fall back to router-based mode when SSID is missing
        call_args = mock_client._request.call_args[0][0]
        assert f"ConnectMasterAp:JoinGroupMaster:eth{master_ip}:wifi0.0.0.0" in call_args

    @pytest.mark.asyncio
    async def test_leave_group(self, mock_client):
        """Test leaving a group."""
        mock_client._group_master = "192.168.1.101"
        mock_client._group_slaves = []
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.leave_group()

        assert mock_client._group_master is None
        assert mock_client._group_slaves == []
        mock_client._request.assert_called_once()


class TestGroupAPISlaveManagement:
    """Test GroupAPI slave management methods."""

    @pytest.mark.asyncio
    async def test_get_slaves(self, mock_client):
        """Test getting slave list."""
        mock_response = {
            "slaves": [
                {"ip": "192.168.1.101"},
                {"ip": "192.168.1.102"},
            ]
        }
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=mock_response, raw=None))

        result = await mock_client.get_slaves()

        assert result == ["192.168.1.101", "192.168.1.102"]

    @pytest.mark.asyncio
    async def test_get_slaves_empty(self, mock_client):
        """Test getting slave list when empty."""
        mock_response = {"slaves": []}
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=mock_response, raw=None))

        result = await mock_client.get_slaves()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_slaves_string_list(self, mock_client):
        """Test getting slave list with string IPs."""
        mock_response = {"slaves": ["192.168.1.101", "192.168.1.102"]}
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=mock_response, raw=None))

        result = await mock_client.get_slaves()

        assert result == ["192.168.1.101", "192.168.1.102"]

    @pytest.mark.asyncio
    async def test_get_slaves_no_slaves_key(self, mock_client):
        """Test getting slave list when key missing."""
        mock_response = {}
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=mock_response, raw=None))

        result = await mock_client.get_slaves()

        assert result == []

    @pytest.mark.asyncio
    async def test_get_slaves_info(self, mock_client):
        """Test getting full slave info with UUIDs."""
        mock_response = {
            "slaves": 2,
            "slave_list": [
                {"ip": "10.10.10.92", "uuid": "uuid:ABC123", "name": "Slave1"},
                {"ip": "10.10.10.93", "uuid": "uuid:DEF456", "name": "Slave2"},
            ],
        }
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=mock_response, raw=None))

        result = await mock_client.get_slaves_info()

        assert len(result) == 2
        assert result[0]["uuid"] == "uuid:ABC123"
        assert result[1]["ip"] == "10.10.10.93"

    @pytest.mark.asyncio
    async def test_kick_slave(self, mock_client):
        """Test kicking a slave."""
        mock_client._group_master = "192.168.1.100"
        type(mock_client).host = "192.168.1.100"
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.kick_slave("192.168.1.101")

        mock_client._request.assert_called_once()
        call_args = mock_client._request.call_args[0]
        assert "multiroom:SlaveKickout:192.168.1.101" in call_args[0]

    @pytest.mark.asyncio
    async def test_kick_slave_not_master(self, mock_client):
        """Test kicking slave when not master."""
        mock_client._group_master = "192.168.1.101"
        type(mock_client).host = "192.168.1.100"

        with pytest.raises(RuntimeError, match="Not a group master"):
            await mock_client.kick_slave("192.168.1.102")

    @pytest.mark.asyncio
    async def test_mute_slave(self, mock_client):
        """Test muting a slave."""
        mock_client._group_master = "192.168.1.100"
        type(mock_client).host = "192.168.1.100"
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.mute_slave("192.168.1.101", True)

        mock_client._request.assert_called_once()
        call_args = mock_client._request.call_args[0]
        assert "multiroom:SlaveMute:192.168.1.101:1" in call_args[0]

    @pytest.mark.asyncio
    async def test_unmute_slave(self, mock_client):
        """Test unmuting a slave."""
        mock_client._group_master = "192.168.1.100"
        type(mock_client).host = "192.168.1.100"
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.mute_slave("192.168.1.101", False)

        call_args = mock_client._request.call_args[0]
        assert "multiroom:SlaveMute:192.168.1.101:0" in call_args[0]

    @pytest.mark.asyncio
    async def test_mute_slave_not_master(self, mock_client):
        """Test muting slave when not master."""
        mock_client._group_master = "192.168.1.101"
        type(mock_client).host = "192.168.1.100"

        with pytest.raises(RuntimeError, match="Not a group master"):
            await mock_client.mute_slave("192.168.1.102", True)


class TestGroupAPIDeviceGroupInfo:
    """Test GroupAPI device group info methods."""

    @pytest.mark.asyncio
    async def test_get_device_group_info_master(self, mock_client):
        """Test getting device group info as master."""
        mock_status = {
            "multiroom": {
                "slaves": [
                    {"ip": "192.168.1.101", "uuid": "uuid:slave-uuid-1"},
                    {"ip": "192.168.1.102", "uuid": "uuid:slave-uuid-2"},
                ],
                "slave_count": 2,
            }
        }
        mock_device_info = DeviceInfo(
            model="WiiM Pro",
            group="1",
            master_uuid="master-uuid",
            master_ip="192.168.1.100",
        )
        mock_client.get_status = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_device_info)
        type(mock_client).host = "192.168.1.100"

        result = await mock_client.get_device_group_info()

        assert isinstance(result, DeviceGroupInfo)
        assert result.role == "master"
        assert result.master_host == "192.168.1.100"
        assert len(result.slave_hosts) == 2
        assert result.slave_count == 2
        # Verify slave UUIDs are extracted (for WiFi Direct matching)
        assert len(result.slave_uuids) == 2
        assert "slave-uuid-1" in result.slave_uuids
        assert "slave-uuid-2" in result.slave_uuids

    @pytest.mark.asyncio
    async def test_get_device_group_info_slave(self, mock_client):
        """Test getting device group info as slave."""
        mock_status = {
            "multiroom": {
                "master": "192.168.1.101",
            }
        }
        mock_device_info = DeviceInfo(
            model="WiiM Pro",
            group="1",
            master_uuid="master-uuid",
            master_ip="192.168.1.101",
        )
        mock_client.get_status = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_device_info)
        type(mock_client).host = "192.168.1.100"

        result = await mock_client.get_device_group_info()

        assert isinstance(result, DeviceGroupInfo)
        assert result.role == "slave"
        assert result.master_host == "192.168.1.101"
        assert result.master_uuid == "master-uuid"
        assert len(result.slave_hosts) == 0

    @pytest.mark.asyncio
    async def test_get_device_group_info_slave_fallback_multiroom(self, mock_client):
        """Test getting device group info as slave with master_ip from multiroom section.

        Some devices only report master IP in the multiroom section, not in device info.
        This tests the fallback behavior.
        """
        mock_status = {
            "multiroom": {
                "master": "192.168.1.101",  # Master IP only in multiroom section
            }
        }
        mock_device_info = DeviceInfo(
            model="WiiM Pro",
            group="1",
            master_uuid="master-uuid",
            master_ip=None,  # master_ip not in device info
        )
        mock_client.get_status = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_device_info)
        type(mock_client).host = "192.168.1.100"

        result = await mock_client.get_device_group_info()

        assert isinstance(result, DeviceGroupInfo)
        assert result.role == "slave"
        assert result.master_host == "192.168.1.101"  # Should get from multiroom.master
        assert result.master_uuid == "master-uuid"
        assert len(result.slave_hosts) == 0

    @pytest.mark.asyncio
    async def test_get_device_group_info_solo(self, mock_client):
        """Test getting device group info when solo."""
        mock_status = {"multiroom": {}}
        mock_device_info = DeviceInfo(model="WiiM Pro", group="0")
        mock_client.get_status = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_device_info)
        type(mock_client).host = "192.168.1.100"

        result = await mock_client.get_device_group_info()

        assert isinstance(result, DeviceGroupInfo)
        assert result.role == "solo"
        assert result.master_host is None
        assert len(result.slave_hosts) == 0

    @pytest.mark.asyncio
    async def test_get_device_group_info_fallback(self, mock_client):
        """Test getting device group info with fallback to status."""
        mock_status = {
            "multiroom": {},
            "group": "0",
            "master_uuid": None,
            "master_ip": None,
        }
        mock_client.get_status = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(side_effect=WiiMError("Failed"))
        mock_client.host = "192.168.1.100"

        result = await mock_client.get_device_group_info()

        assert isinstance(result, DeviceGroupInfo)
        assert result.role == "solo"
