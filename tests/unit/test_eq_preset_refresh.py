"""EQ preset lists refresh independently from active EQ state."""

import time
from unittest.mock import AsyncMock

import pytest

from pywiim.api.peq import PEQSettings
from pywiim.exceptions import WiiMResponseError
from pywiim.models import PlayerStatus
from pywiim.player import Player


@pytest.fixture
def eq_player(mock_client):
    """Provide a player with both EQ types and read-only device responses."""
    player = Player(mock_client)
    mock_client._capabilities = {"supports_eq": True, "supports_peq": True}
    mock_client.get_eq_presets = AsyncMock(return_value=["Flat"])
    mock_client.get_peq_preset_list = AsyncMock(return_value={"custom": ["Night"], "preset": []})
    mock_client.get_eq = AsyncMock(return_value={"EQStat": "Off", "Name": "Flat"})
    mock_client.get_peq_bands = AsyncMock(return_value=PEQSettings(enabled=False))
    player._status_model = PlayerStatus(source="wifi")
    return player


@pytest.mark.asyncio
async def test_preset_lists_refresh_after_fifteen_minutes_not_on_track_change(eq_player):
    player = eq_player
    status = player._status_model
    await player._state_mgr._refresh_periodic_data(True, status, False)
    assert player.eq_presets == ["Off", "Flat"]
    assert player.peq_presets == ["Night"]
    await player.initialize_peq_presets()
    player.client.get_peq_preset_list.assert_awaited_once()

    player.client.get_eq_presets.reset_mock(return_value=True)
    player.client.get_eq_presets.return_value = ["Flat", "Movie"]
    player.client.get_peq_preset_list.reset_mock(return_value=True)
    player.client.get_peq_preset_list.return_value = {"custom": ["Desk"], "preset": []}
    player._last_eq_presets_check = time.time() - 61
    player._last_peq_presets_check = time.time() - 61
    await player._state_mgr._refresh_periodic_data(False, status, True)
    player.client.get_eq_presets.assert_not_awaited()
    player.client.get_peq_preset_list.assert_not_awaited()

    player._last_eq_presets_check = time.time() - 899
    player._last_peq_presets_check = time.time() - 899
    await player._state_mgr._refresh_periodic_data(False, status, False)
    player.client.get_eq_presets.assert_not_awaited()
    player.client.get_peq_preset_list.assert_not_awaited()

    player._last_eq_presets_check = time.time() - 901
    player._last_peq_presets_check = time.time() - 901
    await player._state_mgr._refresh_periodic_data(False, status, False)
    assert player.eq_presets == ["Off", "Flat", "Movie"]
    assert player.peq_presets == ["Desk"]
    player.client.get_eq_presets.assert_awaited_once()
    player.client.get_peq_preset_list.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_initial_peq_list_is_retried_without_reloading(eq_player):
    player = eq_player
    status = player._status_model
    player.client.get_peq_preset_list.side_effect = [
        WiiMResponseError("unavailable"),
        {"custom": ["Recovered"], "preset": []},
    ]
    await player._state_mgr._refresh_periodic_data(True, status, False)
    assert player._peq_presets is None
    await player._state_mgr._refresh_periodic_data(False, status, False)
    assert player.client.get_peq_preset_list.await_count == 1

    player._last_peq_presets_check = time.time() - 61
    await player._state_mgr._refresh_periodic_data(False, status, False)
    assert player.peq_presets == ["Recovered"]
    assert player.client.get_peq_preset_list.await_count == 2


@pytest.mark.asyncio
async def test_failed_periodic_list_reads_preserve_previous_options(eq_player):
    player = eq_player
    status = player._status_model
    await player._state_mgr._refresh_periodic_data(True, status, False)
    player.client.get_eq_presets.side_effect = WiiMResponseError("unavailable")
    player.client.get_peq_preset_list.side_effect = WiiMResponseError("unavailable")
    player._last_eq_presets_check = time.time() - 901
    player._last_peq_presets_check = time.time() - 901
    await player._state_mgr._refresh_periodic_data(False, status, False)
    assert player.eq_presets == ["Off", "Flat"]
    assert player.peq_presets == ["Night"]
    await player._state_mgr._refresh_periodic_data(False, status, True)
    assert player.client.get_eq_presets.await_count == 2
    assert player.client.get_peq_preset_list.await_count == 2


@pytest.mark.asyncio
async def test_source_change_immediately_reads_new_graphic_preset_list(eq_player):
    player = eq_player
    player.client.get_eq_presets.side_effect = [["Network"], ["Line In"]]
    await player._state_mgr._refresh_periodic_data(True, PlayerStatus(source="wifi"), False)
    await player._state_mgr._refresh_periodic_data(False, PlayerStatus(source="line_in"), False)
    assert player.eq_presets == ["Off", "Line In"]
    assert player.client.get_eq_presets.await_count == 2


@pytest.mark.asyncio
async def test_valid_empty_peq_list_is_not_treated_as_a_failed_read(eq_player):
    player = eq_player
    player.client.get_peq_preset_list.return_value = {"custom": [], "preset": []}
    await player._state_mgr._refresh_periodic_data(True, player._status_model, False)
    player._last_peq_presets_check = time.time() - 61
    await player._state_mgr._refresh_periodic_data(False, player._status_model, False)
    assert player.peq_presets == []
    player.client.get_peq_preset_list.assert_awaited_once()


@pytest.mark.asyncio
async def test_unsupported_eq_lists_are_not_queried(eq_player):
    player = eq_player
    player.client._capabilities = {"supports_eq": False, "supports_peq": False}
    await player._state_mgr._refresh_periodic_data(True, player._status_model, False)
    player.client.get_eq_presets.assert_not_awaited()
    player.client.get_peq_preset_list.assert_not_awaited()
