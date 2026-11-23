"""Unit tests for the WiiM Voice Remote API (parsing, client methods, capability probe, safety)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import pywiim
from pywiim.api.base import ApiResponse
from pywiim.api.ble_remote import (
    REMOTE_VOLUME_STEP_DEFAULT,
    REMOTE_VOLUME_STEP_MAX,
    REMOTE_VOLUME_STEP_MIN,
    REMOTE_VOLUME_STEPS,
    BleRemoteIdentity,
    BleRemoteState,
    build_ble_remote_state,
    extract_ble_remote_status_ex,
    mask_mac,
    parse_ble_remote_identity,
)
from pywiim.capabilities import WiiMCapabilities
from pywiim.exceptions import WiiMError
from pywiim.models import DeviceInfo
from tests.unit.ble_remote_fixtures import (
    FAKE_REMOTE_MAC,
    FORBIDDEN_REMOTE_COMMANDS,
    HID_CONNECTED,
    HID_CONNECTED_LAGGING_BATTERY,
    HID_CONNECTED_RAW,
    HID_NOT_CONNECTED,
    HID_NOT_CONNECTED_RAW,
    HID_SCANNING,
    HID_SCANNING_RAW,
    STATUS_EX_BASE,
    STATUS_EX_REMOTE_CONNECTED,
    STATUS_EX_REMOTE_NOT_CONNECTED,
    VOLUME_STEP_GET_RESPONSE,
    VOLUME_STEP_SET_RESPONSE,
)

PYWIIM_SOURCE = Path(pywiim.__file__).parent


class TestFixtures:
    """The raw captured bodies must be valid JSON despite the space before doubleclickdisable."""

    @pytest.mark.parametrize("raw", [HID_CONNECTED_RAW, HID_NOT_CONNECTED_RAW, HID_SCANNING_RAW])
    def test_raw_bodies_contain_the_device_space(self, raw):
        assert ', "doubleclickdisable":0}' in raw

    def test_decoded_bodies(self):
        assert HID_CONNECTED["status"] == "connected"
        assert HID_CONNECTED["doubleclickdisable"] == 0
        assert HID_SCANNING["mac"] == "00:00:00:00:00:00"


class TestExtractStatusEx:
    def test_connected_keys(self):
        fields = extract_ble_remote_status_ex({**STATUS_EX_BASE, **STATUS_EX_REMOTE_CONNECTED})
        assert fields["BleRemoteBatterylevel"] == "100"
        assert fields["BleRemoteRSSI"] == "-61"
        # Only BleRemote* keys are kept.
        assert "uuid" not in fields and "DeviceName" not in fields

    def test_not_connected_keys_are_missing_not_an_error(self):
        fields = extract_ble_remote_status_ex({**STATUS_EX_BASE, **STATUS_EX_REMOTE_NOT_CONNECTED})
        assert fields == {"BleRemoteControl": "1", "BleRemoteConnected": "0"}

    def test_no_remote_keys(self):
        assert extract_ble_remote_status_ex(STATUS_EX_BASE) == {}

    @pytest.mark.parametrize("bad", [None, [], "x", 3])
    def test_garbage_input(self, bad):
        assert extract_ble_remote_status_ex(bad) == {}


class TestParseIdentity:
    def test_connected(self):
        identity = parse_ble_remote_identity(HID_CONNECTED)
        assert identity == BleRemoteIdentity(
            status="connected", paired=True, name="WiiM Voice Remote", mac=FAKE_REMOTE_MAC, firmware="0054"
        )

    def test_not_connected_keeps_identity(self):
        identity = parse_ble_remote_identity(HID_NOT_CONNECTED)
        assert identity is not None
        assert identity.paired is True
        assert identity.status == "notconnect"
        assert identity.mac == FAKE_REMOTE_MAC

    def test_scanning_means_not_paired(self):
        identity = parse_ble_remote_identity(HID_SCANNING)
        assert identity is not None
        assert identity.paired is False
        assert identity.name is None
        assert identity.mac is None
        assert identity.firmware is None

    def test_name_without_real_mac_is_not_paired(self):
        identity = parse_ble_remote_identity({**HID_CONNECTED, "mac": "00:00:00:00:00:00"})
        assert identity is not None and identity.paired is False

    @pytest.mark.parametrize(
        "bad",
        [
            None,
            [],
            "unknown command",
            {},
            {"error": "unsupported_command"},
            {"status": "connected", "error": 3, "name": "x", "mac": FAKE_REMOTE_MAC},
            {"status": 5, "name": "x", "mac": FAKE_REMOTE_MAC},
            {"status": "connected"},
        ],
    )
    def test_invalid_shapes_return_none(self, bad):
        assert parse_ble_remote_identity(bad) is None

    def test_repr_hides_mac(self):
        identity = parse_ble_remote_identity(HID_CONNECTED)
        assert FAKE_REMOTE_MAC not in repr(identity)


class TestBuildState:
    def test_connected(self):
        state = build_ble_remote_state(
            extract_ble_remote_status_ex(STATUS_EX_REMOTE_CONNECTED), parse_ble_remote_identity(HID_CONNECTED)
        )
        assert state == BleRemoteState(
            paired=True,
            connected=True,
            name="WiiM Voice Remote",
            mac=FAKE_REMOTE_MAC,
            firmware="0054",
            battery=100,
            rssi=-61,
        )

    def test_battery_comes_from_status_ex_not_from_lagging_hid(self):
        state = build_ble_remote_state(
            extract_ble_remote_status_ex(STATUS_EX_REMOTE_CONNECTED),
            parse_ble_remote_identity(HID_CONNECTED_LAGGING_BATTERY),
        )
        assert state.battery == 100

    def test_not_connected_missing_keys(self):
        state = build_ble_remote_state(
            extract_ble_remote_status_ex(STATUS_EX_REMOTE_NOT_CONNECTED), parse_ble_remote_identity(HID_NOT_CONNECTED)
        )
        assert state.paired is True
        assert state.connected is False
        assert state.battery is None
        assert state.rssi is None  # hid rssi is only the last value; not reported as live
        assert state.name == "WiiM Voice Remote"
        assert state.mac == FAKE_REMOTE_MAC
        assert state.firmware == "0054"  # kept by getblehidstatus

    def test_not_paired(self):
        state = build_ble_remote_state(
            extract_ble_remote_status_ex(STATUS_EX_REMOTE_NOT_CONNECTED), parse_ble_remote_identity(HID_SCANNING)
        )
        assert (state.paired, state.connected) == (False, False)
        assert state.name is None and state.mac is None and state.firmware is None
        assert state.battery is None and state.rssi is None

    def test_identity_not_read_yet(self):
        state = build_ble_remote_state(extract_ble_remote_status_ex(STATUS_EX_REMOTE_CONNECTED), None)
        assert state.paired is None
        assert state.connected is True
        assert state.battery == 100
        assert state.firmware == "0054"  # from BleRemoteVersion
        assert state.name is None and state.mac is None

    def test_status_ex_not_read_yet_falls_back_to_hid_status(self):
        state = build_ble_remote_state({}, parse_ble_remote_identity(HID_CONNECTED))
        assert state.connected is True
        assert state.battery is None and state.rssi is None

    @pytest.mark.parametrize("battery", ["", "abc", "-1", "101", None])
    def test_bad_battery_is_none(self, battery):
        fields = {**STATUS_EX_REMOTE_CONNECTED, "BleRemoteBatterylevel": battery}
        assert build_ble_remote_state(fields, None).battery is None

    def test_bad_rssi_is_none(self):
        fields = {**STATUS_EX_REMOTE_CONNECTED, "BleRemoteRSSI": "n/a"}
        assert build_ble_remote_state(fields, None).rssi is None

    def test_repr_and_diagnostics_mask_the_mac(self):
        state = build_ble_remote_state(
            extract_ble_remote_status_ex(STATUS_EX_REMOTE_CONNECTED), parse_ble_remote_identity(HID_CONNECTED)
        )
        assert FAKE_REMOTE_MAC not in repr(state)
        diag = state.diagnostics_dict()
        assert FAKE_REMOTE_MAC not in str(diag)
        assert diag["mac"] == "XX:XX:XX:XX:XX:XX"
        assert diag["battery"] == 100

    def test_diagnostics_without_mac(self):
        state = build_ble_remote_state({}, parse_ble_remote_identity(HID_SCANNING))
        assert state.diagnostics_dict()["mac"] is None


class TestMaskMac:
    def test_masks_every_octet(self):
        assert mask_mac("AA:BB:CC:DD:EE:FF") == "XX:XX:XX:XX:XX:XX"

    @pytest.mark.parametrize("value", [None, ""])
    def test_empty(self, value):
        assert mask_mac(value) is None


class TestVolumeStepConstants:
    def test_five_labelled_steps(self):
        assert REMOTE_VOLUME_STEP_MIN == 1
        assert REMOTE_VOLUME_STEP_MAX == 5
        assert REMOTE_VOLUME_STEP_DEFAULT == 1
        assert dict(REMOTE_VOLUME_STEPS) == {
            1: "Fine Adjustment",
            2: "Small Step",
            3: "Medium Step",
            4: "Large Step",
            5: "Quick Adjustment",
        }

    def test_exported_from_package(self):
        assert pywiim.REMOTE_VOLUME_STEPS is REMOTE_VOLUME_STEPS
        assert pywiim.BleRemoteState is BleRemoteState


class TestClientMethods:
    @pytest.mark.asyncio
    async def test_get_identity(self, mock_client):
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=HID_CONNECTED, raw=None))
        identity = await mock_client.get_ble_remote_identity()
        assert identity is not None and identity.paired is True
        mock_client._request.assert_awaited_once_with("/httpapi.asp?command=getblehidstatus")

    @pytest.mark.asyncio
    async def test_get_identity_none_on_error_or_invalid(self, mock_client):
        mock_client._request = AsyncMock(side_effect=WiiMError("unknown command"))
        assert await mock_client.get_ble_remote_identity() is None
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="unknown command"))
        assert await mock_client.get_ble_remote_identity() is None

    @pytest.mark.asyncio
    async def test_get_volume_step(self, mock_client):
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=VOLUME_STEP_GET_RESPONSE, raw=None))
        assert await mock_client.get_remote_volume_step() == 1
        mock_client._request.assert_awaited_once_with("/httpapi.asp?command=get_remote_volume_step")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "parsed",
        [
            None,
            {"status": "OK"},
            {"status": "OK", "remote_volume_step": "x"},
            {"status": "OK", "remote_volume_step": 0},
            {"status": "OK", "remote_volume_step": 6},
            {"status": "OK", "remote_volume_step": True},
            {"error": "unsupported_command"},
        ],
    )
    async def test_get_volume_step_unreadable(self, mock_client, parsed):
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=parsed, raw=None))
        assert await mock_client.get_remote_volume_step() is None

    @pytest.mark.asyncio
    async def test_get_volume_step_accepts_numeric_string(self, mock_client):
        mock_client._request = AsyncMock(
            return_value=ApiResponse(parsed={"status": "OK", "remote_volume_step": "3"}, raw=None)
        )
        assert await mock_client.get_remote_volume_step() == 3

    @pytest.mark.asyncio
    async def test_get_volume_step_transport_error(self, mock_client):
        mock_client._request = AsyncMock(side_effect=WiiMError("timeout"))
        assert await mock_client.get_remote_volume_step() is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("step", [1, 2, 3, 4, 5])
    async def test_set_volume_step_sends_and_verifies(self, mock_client, step):
        sent: list[str] = []

        async def request(endpoint, **kwargs):
            sent.append(endpoint)
            if "set_remote_volume_step" in endpoint:
                return ApiResponse(parsed=VOLUME_STEP_SET_RESPONSE, raw=None)
            return ApiResponse(parsed={"status": "OK", "remote_volume_step": step}, raw=None)

        mock_client._request = AsyncMock(side_effect=request)
        assert await mock_client.set_remote_volume_step(step) == step
        assert sent == [
            f"/httpapi.asp?command=set_remote_volume_step:{step}",
            "/httpapi.asp?command=get_remote_volume_step",
        ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad", [0, 6, -1, 100, True, False, 2.0, "2", None])
    async def test_set_volume_step_rejects_invalid_before_sending(self, mock_client, bad):
        mock_client._request = AsyncMock()
        with pytest.raises(ValueError, match="between 1 and 5"):
            await mock_client.set_remote_volume_step(bad)
        mock_client._request.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_set_volume_step_readback_mismatch_raises(self, mock_client):
        async def request(endpoint, **kwargs):
            if "set_remote_volume_step" in endpoint:
                return ApiResponse(parsed=VOLUME_STEP_SET_RESPONSE, raw=None)
            return ApiResponse(parsed={"status": "OK", "remote_volume_step": 1}, raw=None)

        mock_client._request = AsyncMock(side_effect=request)
        with pytest.raises(WiiMError, match="reports 1"):
            await mock_client.set_remote_volume_step(4)

    @pytest.mark.asyncio
    async def test_set_volume_step_unreadable_readback_raises(self, mock_client):
        async def request(endpoint, **kwargs):
            if "set_remote_volume_step" in endpoint:
                return ApiResponse(parsed=VOLUME_STEP_SET_RESPONSE, raw=None)
            return ApiResponse(parsed=None, raw="")

        mock_client._request = AsyncMock(side_effect=request)
        with pytest.raises(WiiMError, match="could not be read back"):
            await mock_client.set_remote_volume_step(2)

    @pytest.mark.asyncio
    async def test_set_volume_step_rejected_by_device(self, mock_client):
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed={"status": "Failed"}, raw=None))
        with pytest.raises(WiiMError, match="rejected"):
            await mock_client.set_remote_volume_step(2)
        mock_client._request.assert_awaited_once()  # no read-back after a rejected set

    @pytest.mark.asyncio
    async def test_set_volume_step_plain_ok_body_is_accepted(self, mock_client):
        async def request(endpoint, **kwargs):
            if "set_remote_volume_step" in endpoint:
                return ApiResponse(parsed=None, raw="OK")
            return ApiResponse(parsed={"status": "OK", "remote_volume_step": 3}, raw=None)

        mock_client._request = AsyncMock(side_effect=request)
        assert await mock_client.set_remote_volume_step(3) == 3


def _probe_client(mock_client, hid_result):
    """Return the client with a _request that answers getblehidstatus with *hid_result*."""
    calls: list[str] = []

    def side_effect(endpoint, **kwargs):
        calls.append(endpoint)
        if "getblehidstatus" in endpoint:
            if isinstance(hid_result, Exception):
                raise hid_result
            return ApiResponse(parsed=hid_result, raw=None)
        return ApiResponse(parsed={"status": "ok"}, raw=None)

    mock_client._request = AsyncMock(side_effect=side_effect)
    mock_client.get_status = AsyncMock(return_value={"status": "ok"})
    return calls


def _is_remote_endpoint(endpoint: str) -> bool:
    return "blehid" in endpoint.lower() or "remote_volume_step" in endpoint.lower()


def _info(**extra):
    return DeviceInfo.model_validate({**STATUS_EX_BASE, **extra})


class TestCapabilityProbe:
    @pytest.mark.asyncio
    async def test_supported(self, mock_client):
        calls = _probe_client(mock_client, HID_CONNECTED)
        caps = await WiiMCapabilities().detect_capabilities(mock_client, _info(**STATUS_EX_REMOTE_CONNECTED))
        assert caps["supports_ble_remote"] is True
        assert sum("getblehidstatus" in c for c in calls) == 1

    @pytest.mark.asyncio
    async def test_supported_even_when_remote_not_paired(self, mock_client):
        _probe_client(mock_client, HID_SCANNING)
        caps = await WiiMCapabilities().detect_capabilities(mock_client, _info(**STATUS_EX_REMOTE_NOT_CONNECTED))
        assert caps["supports_ble_remote"] is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("extra", [{}, {"BleRemoteControl": "0"}, {"BleRemoteControl": ""}])
    async def test_no_remote_support_sends_no_remote_request(self, mock_client, extra):
        calls = _probe_client(mock_client, HID_CONNECTED)
        caps = await WiiMCapabilities().detect_capabilities(mock_client, _info(**extra))
        assert caps["supports_ble_remote"] is False
        assert not any(_is_remote_endpoint(c) for c in calls)

    @pytest.mark.asyncio
    async def test_unknown_command_is_false(self, mock_client):
        _probe_client(mock_client, WiiMError("unknown command"))
        caps = await WiiMCapabilities().detect_capabilities(mock_client, _info(BleRemoteControl="1"))
        assert caps["supports_ble_remote"] is False

    @pytest.mark.asyncio
    async def test_invalid_body_is_false(self, mock_client):
        _probe_client(mock_client, {"error": "unsupported_command"})
        caps = await WiiMCapabilities().detect_capabilities(mock_client, _info(BleRemoteControl="1"))
        assert caps["supports_ble_remote"] is False

    @pytest.mark.asyncio
    async def test_transient_error_is_inconclusive(self, mock_client):
        _probe_client(mock_client, WiiMError("connection reset"))
        caps = await WiiMCapabilities().detect_capabilities(mock_client, _info(BleRemoteControl="1"))
        assert caps["supports_ble_remote"] is None

    @pytest.mark.asyncio
    async def test_probe_only_reads(self, mock_client):
        calls = _probe_client(mock_client, HID_CONNECTED)
        await WiiMCapabilities().detect_capabilities(mock_client, _info(**STATUS_EX_REMOTE_CONNECTED))
        remote_calls = [c for c in calls if _is_remote_endpoint(c)]
        assert remote_calls == ["/httpapi.asp?command=getblehidstatus"]

    def test_static_detection_defaults_to_false(self):
        from pywiim.capabilities import detect_device_capabilities

        assert (
            detect_device_capabilities(_info(**STATUS_EX_REMOTE_CONNECTED)).get("supports_ble_remote", False) is False
        )


class TestPairingAndUpdateCommandsAreNeverSent:
    """Safety: pairing, removal and remote-update commands must not be sent by this feature."""

    # The speaker-firmware API that predates this feature (pywiim/api/firmware.py) uses
    # getMvRemoteUpdateStart / getMvRemoteUpdateStartCheck, and Player.check_for_updates documents
    # them. Nothing in the BLE remote code, the refresh path or the capability probe sends them.
    PRE_EXISTING_FIRMWARE_FILES = {"api/firmware.py", "player/__init__.py"}
    FIRMWARE_UPDATE_COMMANDS = {"getmvremoteupdatestart", "getmvremoteupdatestartcheck"}

    def test_library_source_never_mentions_pairing_or_removal_commands(self):
        offenders = []
        for path in PYWIIM_SOURCE.rglob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            offenders += [
                f"{path.name}: {cmd}"
                for cmd in FORBIDDEN_REMOTE_COMMANDS
                if cmd.lower() not in self.FIRMWARE_UPDATE_COMMANDS and cmd.lower() in text
            ]
        assert offenders == []

    def test_update_commands_only_in_the_pre_existing_firmware_api(self):
        found = set()
        for path in PYWIIM_SOURCE.rglob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            if any(cmd in text for cmd in self.FIRMWARE_UPDATE_COMMANDS):
                found.add(path.relative_to(PYWIIM_SOURCE).as_posix())
        assert found <= self.PRE_EXISTING_FIRMWARE_FILES

    @pytest.mark.asyncio
    async def test_every_remote_call_stays_on_the_allowed_endpoints(self, mock_client):
        sent: list[str] = []

        async def request(endpoint, **kwargs):
            sent.append(endpoint)
            if "getblehidstatus" in endpoint:
                return ApiResponse(parsed=HID_CONNECTED, raw=None)
            if "get_remote_volume_step" in endpoint:
                return ApiResponse(parsed={"status": "OK", "remote_volume_step": 2}, raw=None)
            return ApiResponse(parsed=VOLUME_STEP_SET_RESPONSE, raw=None)

        mock_client._request = AsyncMock(side_effect=request)
        await mock_client.get_ble_remote_identity()
        await mock_client.get_remote_volume_step()
        await mock_client.set_remote_volume_step(2)

        allowed = {
            "/httpapi.asp?command=getblehidstatus",
            "/httpapi.asp?command=get_remote_volume_step",
            "/httpapi.asp?command=set_remote_volume_step:2",
        }
        assert set(sent) <= allowed
        for endpoint in sent:
            assert not any(cmd.lower() in endpoint.lower() for cmd in FORBIDDEN_REMOTE_COMMANDS)
