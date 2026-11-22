"""An unsaved custom graphic EQ survives switching EQ off and can be switched back on.

Fixtures are the EQGetBand responses of a WiiM Pro Plus (Linkplay.4.8.833841), same band format.
"""

from unittest.mock import AsyncMock

import pytest

from pywiim.api.peq import PEQSettings
from pywiim.exceptions import WiiMResponseError
from pywiim.player import Player


def _bands(values: list[int]) -> list[dict[str, int | str]]:
    names = "31hz 63hz 125hz 250hz 500hz 1khz 2khz 4khz 8khz 16khz".split()
    return [
        {"index": i, "param_name": f"band{n}", "value": v} for i, (n, v) in enumerate(zip(names, values, strict=True))
    ]


CUSTOM_BANDS = _bands([89, 50, 50, 50, 50, 50, 50, 50, 50, 50])
JAZZ_BANDS = _bands([67, 63, 56, 59, 44, 44, 50, 56, 63, 66])

CUSTOM_ON = {"EQStat": "On", "Name": "", "EQBand": CUSTOM_BANDS}
CUSTOM_OFF = {"EQStat": "Off", "Name": "", "EQBand": CUSTOM_BANDS}
JAZZ_OFF = {"EQStat": "Off", "Name": "Jazz", "EQBand": JAZZ_BANDS}


def test_custom_stored_while_off_keeps_eq_off(mock_client):
    player = Player(mock_client)
    player._state_mgr._remember_eq_band(CUSTOM_OFF)
    assert player.eq_preset == "Off"
    assert player.eq_is_custom is False
    assert player.eq_custom_stored is True


def test_saved_preset_switched_off_is_not_custom(mock_client):
    player = Player(mock_client)
    player._state_mgr._remember_eq_band(JAZZ_OFF)
    assert player.eq_preset == "Off"
    assert player.eq_custom_stored is False


def test_whitespace_name_while_off_counts_as_empty(mock_client):
    player = Player(mock_client)
    player._state_mgr._remember_eq_band({**CUSTOM_OFF, "Name": "  "})
    assert player.eq_custom_stored is True


def test_nothing_stored_before_any_read_or_when_name_is_missing(mock_client):
    player = Player(mock_client)
    assert player.eq_custom_stored is False
    player._state_mgr._remember_eq_band({"EQStat": "Off"})
    assert player.eq_custom_stored is False


def test_custom_stored_is_false_while_eq_is_on(mock_client):
    player = Player(mock_client)
    player._state_mgr._remember_eq_band(CUSTOM_OFF)
    player._state_mgr._remember_eq_band(CUSTOM_ON)
    assert player.eq_preset == "Custom"
    assert player.eq_is_custom is True
    assert player.eq_custom_stored is False


def test_later_saved_preset_replaces_stored_custom(mock_client):
    player = Player(mock_client)
    player._state_mgr._remember_eq_band(CUSTOM_OFF)
    player._state_mgr._remember_eq_band(JAZZ_OFF)
    assert player.eq_custom_stored is False


def test_source_change_forgets_stored_custom(mock_client):
    player = Player(mock_client)
    player._state_mgr._remember_eq_band(CUSTOM_OFF)
    player._state_mgr._invalidate_eq_state()
    assert player.eq_custom_stored is False


@pytest.mark.asyncio
async def test_active_peq_clears_stored_custom(mock_client):
    player = Player(mock_client)
    player._state_mgr._remember_eq_band(CUSTOM_OFF)
    player.client.get_peq_bands = AsyncMock(return_value=PEQSettings(enabled=True, name="Night"))
    await player.refresh_peq_preset()
    assert player.eq_custom_stored is False


@pytest.mark.asyncio
async def test_selecting_custom_while_off_turns_eq_back_on(mock_client):
    player = Player(mock_client)
    player._state_mgr._remember_eq_band(CUSTOM_OFF)
    player.client.set_eq_enabled = AsyncMock()
    player.client.set_eq_preset = AsyncMock()
    player.client.get_peq_bands = AsyncMock(return_value=PEQSettings(enabled=False))
    player.client.get_eq = AsyncMock(return_value=CUSTOM_ON)
    await player.set_eq_preset("Custom")
    player.client.set_eq_enabled.assert_awaited_once_with(True)
    player.client.set_eq_preset.assert_not_awaited()
    assert player.eq_preset == "Custom"
    assert player.eq_is_custom is True
    assert player.eq_custom_stored is False


@pytest.mark.asyncio
async def test_selecting_custom_raises_when_device_does_not_confirm(mock_client):
    player = Player(mock_client)
    player._state_mgr._remember_eq_band(CUSTOM_OFF)
    player.client.set_eq_enabled = AsyncMock()
    player.client.get_peq_bands = AsyncMock(return_value=PEQSettings(enabled=False))
    player.client.get_eq = AsyncMock(return_value=CUSTOM_OFF)
    with pytest.raises(WiiMResponseError):
        await player.set_eq_preset("custom")


@pytest.mark.asyncio
async def test_saved_preset_while_off_still_uses_eqon_then_eqload(mock_client):
    player = Player(mock_client)
    player._eq_presets = ["Flat", "Jazz"]
    player._state_mgr._remember_eq_band(CUSTOM_OFF)
    player.client.set_eq_enabled = AsyncMock()
    player.client.set_eq_preset = AsyncMock()
    player.client.get_peq_bands = AsyncMock(return_value=PEQSettings(enabled=False))
    player.client.get_eq = AsyncMock(return_value={"EQStat": "On", "Name": "Jazz"})
    await player.set_eq_preset("Jazz")
    player.client.set_eq_enabled.assert_awaited_once_with(True)
    player.client.set_eq_preset.assert_awaited_once()
    assert player.eq_preset == "Jazz"
