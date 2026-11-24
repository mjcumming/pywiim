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
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=HID_CONNECTED, raw=None))
        player._ble_remote_identity = None
        assert player.ble_remote is None

    def test_no_state_before_first_read(self, mock_client):
        assert _make_player(mock_client).ble_remote is None

    @pytest.mark.asyncio
    async def test_identity_refresh_sets_connected_battery(self, mock_client):
        player = _make_player(mock_client)
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=HID_CONNECTED, raw=None))
        await player._refresh_ble_remote_identity()
        state = player.ble_remote
        assert isinstance(state, BleRemoteState)
        assert (state.connected, state.battery, state.rssi, state.firmware, state.paired) == (
            True,
            100,
            -61,
            "0054",
            True,
        )
        player._on_state_changed.assert_called_once()
        mock_client.get_device_info = AsyncMock()
        mock_client.get_device_info.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unchanged_read_does_not_notify(self, mock_client):
        player = _make_player(mock_client)
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=HID_CONNECTED, raw=None))
        await player._refresh_ble_remote_identity()
        player._on_state_changed.reset_mock()
        await player._refresh_ble_remote_identity()
        player._on_state_changed.assert_not_called()

    @pytest.mark.asyncio
    async def test_battery_change_notifies(self, mock_client):
        player = _make_player(mock_client)
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=HID_CONNECTED, raw=None))
        await player._refresh_ble_remote_identity()
        player._on_state_changed.reset_mock()
        low = {**HID_CONNECTED, "battery": 40}
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=low, raw=None))
        await player._refresh_ble_remote_identity()
        player._on_state_changed.assert_called_once()
        assert player.ble_remote is not None
        assert player.ble_remote.battery == 40

    @pytest.mark.asyncio
    async def test_disconnect_hides_battery_and_rssi(self, mock_client):
        from tests.unit.ble_remote_fixtures import HID_NOT_CONNECTED

        player = _make_player(mock_client)
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=HID_CONNECTED, raw=None))
        await player._refresh_ble_remote_identity()
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=HID_NOT_CONNECTED, raw=None))
        await player._refresh_ble_remote_identity()
        state = player.ble_remote
        assert state is not None
        assert state.connected is False and state.battery is None and state.rssi is None
        assert state.paired is True

    @pytest.mark.asyncio
    async def test_failed_read_keeps_previous_state(self, mock_client):
        player = _make_player(mock_client)
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=HID_CONNECTED, raw=None))
        await player._refresh_ble_remote_identity()
        mock_client._request = AsyncMock(side_effect=WiiMError("timeout"))
        await player._refresh_ble_remote_identity()
        assert player.ble_remote is not None
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
    async def test_get_ble_remote_state_reads_hid(self, mock_client):
        player = _make_player(mock_client)
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=HID_CONNECTED, raw=None))
        state = await player.get_ble_remote_state()
        assert state == player.ble_remote
        assert state is not None
        assert (state.paired, state.connected, state.battery) == (True, True, 100)

    @pytest.mark.asyncio
    async def test_get_ble_remote_state_unsupported(self, mock_client):
        player = _make_player(mock_client, supported=False)
        mock_client._request = AsyncMock()
        assert await player.get_ble_remote_state() is None
        mock_client._request.assert_not_awaited()


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
    def test_paired_remote_uses_the_60_second_tier(self):
        strategy = PollingStrategy({})
        assert strategy.should_fetch_ble_remote(0, True, paired=True, now=1000.0) is True
        assert strategy.should_fetch_ble_remote(1000.0 - 59, True, paired=True, now=1000.0) is False
        assert strategy.should_fetch_ble_remote(1000.0 - 60, True, paired=True, now=1000.0) is True

    def test_unpaired_remote_uses_the_5_minute_tier(self):
        strategy = PollingStrategy({})
        assert strategy.BLE_REMOTE_IDENTITY_INTERVAL > strategy.CONFIGURATION_INTERVAL
        assert strategy.should_fetch_ble_remote(1000.0 - 60, True, paired=False, now=1000.0) is False
        assert (
            strategy.should_fetch_ble_remote(
                1000.0 - strategy.BLE_REMOTE_IDENTITY_INTERVAL, True, paired=False, now=1000.0
            )
            is True
        )

    def test_unsupported_never_fetches(self):
        strategy = PollingStrategy({})
        assert strategy.should_fetch_ble_remote(0, False, paired=True) is False
        assert strategy.should_fetch_ble_remote(None, True, paired=False) is True


class TestDiagnostics:
    @pytest.mark.asyncio
    async def test_diagnostics_include_remote_with_masked_mac(self, mock_client):
        from pywiim.player.diagnostics import DiagnosticsCollector

        player = _make_player(mock_client)
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
