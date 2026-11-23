"""Player-level tests for the WiiM Voice Remote: cached state, refresh helpers, volume step, diagnostics."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from pywiim.api.base import ApiResponse
from pywiim.api.ble_remote import BleRemoteState
from pywiim.exceptions import WiiMError
from pywiim.models import DeviceInfo
from pywiim.player import Player
from pywiim.polling import PollingStrategy
from tests.unit.ble_remote_fixtures import (
    FAKE_REMOTE_MAC,
    HID_CONNECTED,
    HID_SCANNING,
    STATUS_EX_BASE,
    STATUS_EX_REMOTE_CONNECTED,
    STATUS_EX_REMOTE_NOT_CONNECTED,
)


def _make_player(mock_client, *, supported=True):
    type(mock_client).capabilities = PropertyMock(return_value={"supports_ble_remote": supported})
    player = Player(mock_client)
    player._on_state_changed = MagicMock()
    return player


class TestPlayerState:
    def test_supports_flag_follows_capabilities(self, mock_client):
        assert _make_player(mock_client, supported=True).supports_ble_remote is True
        assert _make_player(mock_client, supported=False).supports_ble_remote is False

    def test_supports_flag_inconclusive_is_false(self, mock_client):
        type(mock_client).capabilities = PropertyMock(return_value={"supports_ble_remote": None})
        assert Player(mock_client).supports_ble_remote is False

    def test_no_state_when_unsupported(self, mock_client):
        player = _make_player(mock_client, supported=False)
        player._ble_remote_status_ex = dict(STATUS_EX_REMOTE_CONNECTED)
        assert player.ble_remote is None

    def test_no_state_before_first_read(self, mock_client):
        assert _make_player(mock_client).ble_remote is None

    @pytest.mark.asyncio
    async def test_status_refresh_from_client(self, mock_client):
        player = _make_player(mock_client)
        mock_client.get_device_info = AsyncMock(return_value={**STATUS_EX_BASE, **STATUS_EX_REMOTE_CONNECTED})
        changed = await player._refresh_ble_remote_status()
        assert changed is True  # connection state became known
        state = player.ble_remote
        assert isinstance(state, BleRemoteState)
        assert (state.connected, state.battery, state.rssi, state.firmware) == (True, 100, -61, "0054")
        assert state.paired is None  # identity not read yet
        player._on_state_changed.assert_called_once()

    @pytest.mark.asyncio
    async def test_status_refresh_from_cached_device_info_makes_no_request(self, mock_client):
        player = _make_player(mock_client)
        mock_client.get_device_info = AsyncMock()
        player._device_info = DeviceInfo.model_validate({**STATUS_EX_BASE, **STATUS_EX_REMOTE_CONNECTED})
        await player._refresh_ble_remote_status(from_device_info=True)
        mock_client.get_device_info.assert_not_awaited()
        assert player.ble_remote.battery == 100

    @pytest.mark.asyncio
    async def test_unchanged_status_does_not_notify_or_report_change(self, mock_client):
        player = _make_player(mock_client)
        mock_client.get_device_info = AsyncMock(return_value={**STATUS_EX_BASE, **STATUS_EX_REMOTE_CONNECTED})
        await player._refresh_ble_remote_status()
        player._on_state_changed.reset_mock()
        assert await player._refresh_ble_remote_status() is False
        player._on_state_changed.assert_not_called()

    @pytest.mark.asyncio
    async def test_battery_change_notifies_but_is_not_a_connection_change(self, mock_client):
        player = _make_player(mock_client)
        mock_client.get_device_info = AsyncMock(return_value={**STATUS_EX_BASE, **STATUS_EX_REMOTE_CONNECTED})
        await player._refresh_ble_remote_status()
        player._on_state_changed.reset_mock()
        low = {**STATUS_EX_REMOTE_CONNECTED, "BleRemoteBatterylevel": "40"}
        mock_client.get_device_info = AsyncMock(return_value={**STATUS_EX_BASE, **low})
        assert await player._refresh_ble_remote_status() is False
        player._on_state_changed.assert_called_once()
        assert player.ble_remote.battery == 40

    @pytest.mark.asyncio
    async def test_disconnect_is_a_connection_change_and_missing_keys_parse(self, mock_client):
        player = _make_player(mock_client)
        mock_client.get_device_info = AsyncMock(return_value={**STATUS_EX_BASE, **STATUS_EX_REMOTE_CONNECTED})
        await player._refresh_ble_remote_status()
        mock_client.get_device_info = AsyncMock(return_value={**STATUS_EX_BASE, **STATUS_EX_REMOTE_NOT_CONNECTED})
        assert await player._refresh_ble_remote_status() is True
        state = player.ble_remote
        assert state.connected is False and state.battery is None and state.rssi is None

    @pytest.mark.asyncio
    async def test_failed_status_read_keeps_previous_state(self, mock_client):
        player = _make_player(mock_client)
        mock_client.get_device_info = AsyncMock(return_value={**STATUS_EX_BASE, **STATUS_EX_REMOTE_CONNECTED})
        await player._refresh_ble_remote_status()
        mock_client.get_device_info = AsyncMock(side_effect=WiiMError("timeout"))
        with pytest.raises(WiiMError):
            await player._refresh_ble_remote_status()
        assert player.ble_remote.battery == 100

    @pytest.mark.asyncio
    async def test_identity_refresh(self, mock_client):
        player = _make_player(mock_client)
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=HID_CONNECTED, raw=None))
        await player._refresh_ble_remote_identity()
        state = player.ble_remote
        assert state.paired is True
        assert state.name == "WiiM Voice Remote"
        assert state.mac == FAKE_REMOTE_MAC

    @pytest.mark.asyncio
    async def test_identity_refresh_not_paired(self, mock_client):
        player = _make_player(mock_client)
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=HID_SCANNING, raw=None))
        await player._refresh_ble_remote_identity()
        assert player.ble_remote.paired is False
        assert player.ble_remote.mac is None

    @pytest.mark.asyncio
    async def test_unreadable_identity_keeps_previous(self, mock_client):
        player = _make_player(mock_client)
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=HID_CONNECTED, raw=None))
        await player._refresh_ble_remote_identity()
        mock_client._request = AsyncMock(side_effect=WiiMError("timeout"))
        await player._refresh_ble_remote_identity()
        assert player.ble_remote.paired is True

    @pytest.mark.asyncio
    async def test_get_ble_remote_state_reads_both_sources(self, mock_client):
        player = _make_player(mock_client)
        mock_client.get_device_info = AsyncMock(return_value={**STATUS_EX_BASE, **STATUS_EX_REMOTE_CONNECTED})
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=HID_CONNECTED, raw=None))
        state = await player.get_ble_remote_state()
        assert state == player.ble_remote
        assert (state.paired, state.connected, state.battery) == (True, True, 100)

    @pytest.mark.asyncio
    async def test_get_ble_remote_state_unsupported(self, mock_client):
        player = _make_player(mock_client, supported=False)
        mock_client.get_device_info = AsyncMock()
        assert await player.get_ble_remote_state() is None
        mock_client.get_device_info.assert_not_awaited()


class TestPlayerVolumeStep:
    @pytest.mark.asyncio
    async def test_get_updates_cache(self, mock_client):
        player = _make_player(mock_client)
        mock_client.get_remote_volume_step = AsyncMock(return_value=3)
        assert player.remote_volume_step is None
        assert await player.get_remote_volume_step() == 3
        assert player.remote_volume_step == 3

    @pytest.mark.asyncio
    async def test_unreadable_get_keeps_cache(self, mock_client):
        player = _make_player(mock_client)
        player._remote_volume_step = 2
        mock_client.get_remote_volume_step = AsyncMock(return_value=None)
        assert await player.get_remote_volume_step() is None
        assert player.remote_volume_step == 2

    @pytest.mark.asyncio
    async def test_set_caches_verified_value_and_notifies(self, mock_client):
        player = _make_player(mock_client)
        mock_client.set_remote_volume_step = AsyncMock(return_value=2)
        await player.set_remote_volume_step(2)
        mock_client.set_remote_volume_step.assert_awaited_once_with(2)
        assert player.remote_volume_step == 2
        player._on_state_changed.assert_called_once()

    @pytest.mark.asyncio
    async def test_failed_set_leaves_cache(self, mock_client):
        player = _make_player(mock_client)
        player._remote_volume_step = 1
        mock_client.set_remote_volume_step = AsyncMock(side_effect=WiiMError("reports 1"))
        with pytest.raises(WiiMError):
            await player.set_remote_volume_step(4)
        assert player.remote_volume_step == 1
        player._on_state_changed.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_value_raises_value_error(self, mock_client):
        player = _make_player(mock_client)
        mock_client._request = AsyncMock()
        with pytest.raises(ValueError):
            await player.set_remote_volume_step(9)
        mock_client._request.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unsupported_raises(self, mock_client):
        player = _make_player(mock_client, supported=False)
        mock_client.set_remote_volume_step = AsyncMock()
        with pytest.raises(WiiMError, match="not supported"):
            await player.set_remote_volume_step(2)
        mock_client.set_remote_volume_step.assert_not_awaited()
        mock_client.get_remote_volume_step = AsyncMock()
        assert await player.get_remote_volume_step() is None
        mock_client.get_remote_volume_step.assert_not_awaited()


class TestPollingStrategy:
    def test_status_tier_is_configuration_interval(self):
        strategy = PollingStrategy({})
        assert strategy.should_fetch_ble_remote_status(0, True, now=1000.0) is True
        assert strategy.should_fetch_ble_remote_status(1000.0 - 59, True, now=1000.0) is False
        assert strategy.should_fetch_ble_remote_status(1000.0 - 60, True, now=1000.0) is True

    def test_identity_tier_is_slower_than_status_tier(self):
        strategy = PollingStrategy({})
        assert strategy.BLE_REMOTE_IDENTITY_INTERVAL > strategy.CONFIGURATION_INTERVAL
        assert strategy.should_fetch_ble_remote_identity(0, True, now=1000.0) is True
        assert strategy.should_fetch_ble_remote_identity(1000.0 - 60, True, now=1000.0) is False
        assert (
            strategy.should_fetch_ble_remote_identity(1000.0 - strategy.BLE_REMOTE_IDENTITY_INTERVAL, True, now=1000.0)
            is True
        )

    def test_unsupported_never_fetches(self):
        strategy = PollingStrategy({})
        assert strategy.should_fetch_ble_remote_status(0, False) is False
        assert strategy.should_fetch_ble_remote_identity(0, False) is False
        assert strategy.should_fetch_ble_remote_status(None, True) is True


class TestDiagnostics:
    @pytest.mark.asyncio
    async def test_diagnostics_include_remote_with_masked_mac(self, mock_client):
        from pywiim.player.diagnostics import DiagnosticsCollector

        player = _make_player(mock_client)
        player._ble_remote_status_ex = dict(STATUS_EX_REMOTE_CONNECTED)
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=HID_CONNECTED, raw=None))
        await player._refresh_ble_remote_identity()
        player._remote_volume_step = 2
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo.model_validate(STATUS_EX_BASE))

        report = await DiagnosticsCollector(player).get_diagnostics()

        remote = report["ble_remote"]
        assert remote["battery"] == 100 and remote["connected"] is True
        assert remote["volume_step"] == 2
        assert remote["mac"] == "XX:XX:XX:XX:XX:XX"
        assert FAKE_REMOTE_MAC not in str(report)

    @pytest.mark.asyncio
    async def test_diagnostics_omit_remote_when_unsupported(self, mock_client):
        from pywiim.player.diagnostics import DiagnosticsCollector

        player = _make_player(mock_client, supported=False)
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo.model_validate(STATUS_EX_BASE))
        report = await DiagnosticsCollector(player).get_diagnostics()
        assert "ble_remote" not in report
