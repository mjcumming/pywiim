"""Saved parametric EQ preset behavior."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pywiim.api.base import ApiResponse
from pywiim.api.peq import PEQSettings
from pywiim.exceptions import WiiMError, WiiMResponseError
from pywiim.player import Player


@pytest.mark.asyncio
async def test_player_loads_preset_list_once_and_preserves_case(mock_client):
    player = Player(mock_client)
    mock_client.get_peq_preset_list = AsyncMock(return_value={"custom": ["Night", "Auto"], "preset": ["Night"]})
    mock_client.get_peq_bands = AsyncMock(return_value=PEQSettings(enabled=False, name="Auto"))
    await player.initialize_peq_presets()
    await player.initialize_peq_presets()
    assert player.peq_presets == ["Night", "Auto"]
    assert player.peq_preset is None
    mock_client.get_peq_preset_list.assert_awaited_once()


@pytest.mark.asyncio
async def test_player_selects_exact_preset_and_notifies(mock_client):
    callback = MagicMock()
    player = Player(mock_client, on_state_changed=callback)
    player._peq_presets = ["Night"]
    mock_client.load_peq = AsyncMock(return_value=PEQSettings(enabled=True, name="Night"))
    await player.set_peq_preset("Night")
    mock_client.load_peq.assert_awaited_once_with("Night")
    assert player.peq_preset == "Night"
    callback.assert_called_once()
    with pytest.raises(WiiMError):
        await player.set_peq_preset("Missing")


@pytest.mark.asyncio
async def test_failed_peq_load_does_not_update_player(mock_client):
    player = Player(mock_client)
    player._peq_presets = ["Night"]
    player._peq_preset = None
    mock_client.load_peq = AsyncMock(side_effect=WiiMResponseError("failed"))
    with pytest.raises(WiiMResponseError):
        await player.set_peq_preset("Night")
    assert player.peq_preset is None


@pytest.mark.asyncio
async def test_empty_list_is_cached_and_failed_list_can_be_retried(mock_client):
    player = Player(mock_client)
    mock_client.get_peq_preset_list = AsyncMock(side_effect=[WiiMResponseError("failed"), {"custom": [], "preset": []}])
    with pytest.raises(WiiMResponseError):
        await player.initialize_peq_presets()
    assert player._peq_presets is None
    await player.initialize_peq_presets()
    await player.initialize_peq_presets()
    assert player.peq_presets == []
    assert mock_client.get_peq_preset_list.await_count == 2


@pytest.mark.asyncio
async def test_refresh_tracks_external_selection_and_off(mock_client):
    player = Player(mock_client)
    player._peq_presets = ["Night", "Day"]
    mock_client.get_peq_bands = AsyncMock(
        side_effect=[
            PEQSettings(enabled=True, name="Night"),
            PEQSettings(enabled=True, name="Day"),
            PEQSettings(enabled=False, name="Day"),
            WiiMResponseError("unavailable"),
        ]
    )
    await player.refresh_peq_preset()
    assert player.peq_preset == "Night"
    await player.refresh_peq_preset()
    assert player.peq_preset == "Day"
    await player.refresh_peq_preset()
    assert player.peq_preset is None
    with pytest.raises(WiiMResponseError):
        await player.refresh_peq_preset()
    assert player.peq_preset is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response", [ApiResponse(parsed={"status": "Failed"}, raw=None), ApiResponse(parsed=None, raw="unknown command")]
)
async def test_failed_device_responses_do_not_look_like_valid_peq(mock_client, response):
    mock_client._request = AsyncMock(return_value=response)
    from pywiim.api.peq import PEQAPI

    for method in (PEQAPI.get_peq_preset_list, PEQAPI.get_peq_bands):
        with pytest.raises(WiiMResponseError):
            await method(mock_client)
    with pytest.raises(WiiMResponseError):
        await PEQAPI.load_peq(mock_client, "Night")
