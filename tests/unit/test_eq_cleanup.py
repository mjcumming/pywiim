"""Regressions for WiiM issues 187, 301, 302 and 165."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pywiim.api.base import ApiResponse
from pywiim.api.peq import PEQSettings
from pywiim.capabilities import WiiMCapabilities
from pywiim.client import WiiMClient
from pywiim.exceptions import WiiMResponseError
from pywiim.models import DeviceInfo, PlayerStatus
from pywiim.player import Player

A10_PRESETS = [
    "Flat",
    "Acoustic",
    "Bass Booster",
    "Bass Reducer",
    "Classical",
    "Dance",
    "Deep",
    "Electronic",
    "Game",
    "Hip-Hop",
    "Jazz",
    "Latin",
    "Loudness",
    "Lounge",
    "Movie",
    "Piano",
    "Pop",
    "R&B",
    "Rock",
    "Small Speakers",
    "Spoken Word",
    "Treble Booster",
    "Treble Reducer",
    "Vocal Booster",
]


@pytest.mark.asyncio
async def test_a10_legacy_transport_preserves_reported_preset_list():
    """A valid EQGetList array must survive legacy response validation."""
    client = WiiMClient("192.0.2.1", capabilities={"is_legacy_device": True, "supports_eq": True})
    client._ensure_session = AsyncMock()
    client._request_with_protocol_fallback = AsyncMock(return_value=ApiResponse(parsed=A10_PRESETS, raw=None))
    assert await client.get_eq_presets() == A10_PRESETS


@pytest.mark.asyncio
async def test_first_request_can_discover_endpoint_from_a_json_array(mock_aiohttp_session):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.text = AsyncMock(return_value=json.dumps(A10_PRESETS))
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    mock_aiohttp_session.request = AsyncMock(return_value=response)
    mock_aiohttp_session.closed = False
    client = WiiMClient("192.0.2.1", session=mock_aiohttp_session, capabilities={"is_legacy_device": True})
    with patch.object(client, "_get_ssl_context", new_callable=AsyncMock):
        assert await client.get_eq_presets() == A10_PRESETS


@pytest.mark.asyncio
async def test_failed_eq_response_cannot_look_like_off_or_an_empty_list(mock_client):
    mock_client._request = AsyncMock(
        return_value=ApiResponse(parsed={"status": "failed", "EQStat": "Off", "EQList": []}, raw=None)
    )
    assert await mock_client.get_eq_status() is None
    with pytest.raises(WiiMResponseError):
        await mock_client.get_eq_presets()


@pytest.mark.asyncio
@pytest.mark.parametrize("has_list", [False, True])
async def test_eq_capability_requires_a_real_eq_response(mock_client, has_list):
    async def response(endpoint, **_kwargs):
        if "EQGetList" in endpoint and has_list:
            return ApiResponse(parsed=A10_PRESETS, raw=None)
        if any(name in endpoint for name in ("EQGetBand", "EQGetList", "EQGetStat")):
            return ApiResponse(parsed=None, raw="unknown command")
        return ApiResponse(parsed={"status": "ok"}, raw=None)

    mock_client._request = AsyncMock(side_effect=response)
    info = DeviceInfo(uuid="test", model="YAS_109", firmware="1.0")
    capabilities = await WiiMCapabilities().detect_capabilities(mock_client, info)
    assert capabilities["supports_eq"] is has_list


@pytest.mark.asyncio
@pytest.mark.parametrize("has_peq", [False, True])
async def test_peq_capability_requires_a_valid_list_response(mock_client, has_peq):
    async def response(endpoint, **_kwargs):
        if "EQv2GetList" in endpoint:
            if has_peq:
                return ApiResponse(parsed={"custom": [], "preset": []}, raw=None)
            return ApiResponse(parsed=None, raw="unknown command")
        return ApiResponse(parsed={"status": "ok"}, raw=None)

    mock_client._request = AsyncMock(side_effect=response)
    capabilities = await WiiMCapabilities().detect_capabilities(mock_client, DeviceInfo(uuid="test", model="A10"))
    assert capabilities["supports_peq"] is has_peq


@pytest.mark.asyncio
async def test_generic_legacy_tone_status_does_not_claim_preset_eq(mock_client):
    """An actual UP2STREAM_AMP_V4 returns this for both EQGetBand and EQGetList."""

    async def response(endpoint, **_kwargs):
        if any(name in endpoint for name in ("EQGetBand", "EQGetList", "EQGetStat")):
            return ApiResponse(parsed={"EQEnable": 0, "Treble": 0, "Bass": 0}, raw=None)
        return ApiResponse(parsed={"status": "ok"}, raw=None)

    mock_client._request = AsyncMock(side_effect=response)
    info = DeviceInfo(uuid="test", model="UP2STREAM_AMP_V4", firmware="4.6.415145")
    capabilities = await WiiMCapabilities().detect_capabilities(mock_client, info)
    assert capabilities["supports_eq"] is False


def test_empty_graphic_name_clears_previous_preset(mock_client):
    """The Pro Plus reports unsaved graphic bands with an empty Name."""
    player = Player(mock_client)
    player._status_model = PlayerStatus(source="wifi", eq_preset="flat")
    player._state_mgr._remember_eq_band({"EQStat": "On", "Name": "Flat"})
    player._state_mgr._remember_eq_band({"EQStat": "On", "Name": "", "EQBand": [50, 40, 92]})
    assert player.eq_preset == "Custom"


def test_unknown_eq_status_does_not_default_to_flat(mock_client):
    player = Player(mock_client)
    player._status_model = PlayerStatus(source="wifi", eq_preset="flat")
    assert player.eq_preset is None


def test_invalid_eq_status_does_not_erase_known_state(mock_client):
    player = Player(mock_client)
    player._status_model = PlayerStatus(source="wifi", eq_preset="flat")
    player._state_mgr._remember_eq_band({"EQStat": "On", "Name": "Bass Booster"})
    player._state_mgr._remember_eq_band({"EQStat": "unknown", "Name": "Other"})
    assert player.eq_preset == "Bass Booster"
    player._state_mgr._remember_eq_band({"error": "failed", "EQStat": "Off"})
    assert player.eq_preset == "Bass Booster"


@pytest.mark.asyncio
async def test_failed_peq_refresh_preserves_known_state(mock_client):
    player = Player(mock_client)
    player._peq_presets = ["Night"]
    mock_client.get_peq_bands = AsyncMock(
        side_effect=[PEQSettings(enabled=True, name="Night"), WiiMResponseError("unavailable")]
    )
    await player.refresh_peq_preset()
    with pytest.raises(WiiMResponseError):
        await player.refresh_peq_preset()
    assert player.peq_preset == "Night"


@pytest.mark.asyncio
async def test_active_peq_clears_the_graphic_custom_flag(mock_client):
    player = Player(mock_client)
    player._state_mgr._remember_eq_band({"EQStat": "On", "Name": ""})
    player.client.get_peq_bands = AsyncMock(return_value=PEQSettings(enabled=True, name="Night"))
    await player.refresh_peq_preset()
    assert player.eq_preset == "Off"
    assert player.eq_is_custom is False


@pytest.mark.asyncio
async def test_a10_eq_follows_each_input_and_failed_switch_is_unknown(mock_client):
    player = Player(mock_client)
    player.client._capabilities = {
        "supports_eq": True,
        "supports_subwoofer": False,
        "source_command_overrides": {"line_in": "auxIn"},
    }
    player.client.get_eq_presets = AsyncMock(return_value=A10_PRESETS)
    player.client.get_eq = AsyncMock(
        side_effect=[
            {"source_name": "wifi", "EQStat": "On", "Name": "Bass Booster"},
            {"source_name": "auxIn", "EQStat": "On", "Name": "Spoken Word"},
            {"source_name": "bluetooth", "EQStat": "On", "Name": "Bass Booster"},
            WiiMResponseError("unavailable"),
        ]
    )
    for source, expected in [("wifi", "Bass Booster"), ("line_in", "Spoken Word"), ("bluetooth", "Bass Booster")]:
        status = PlayerStatus(source=source, eq_preset="flat")
        player._status_model = status
        await player._state_mgr._refresh_periodic_data(True, status, False)
        assert player.eq_preset == expected
        assert player.eq_presets == ["Off", *A10_PRESETS]
    status = PlayerStatus(source="line_in", eq_preset="flat")
    player._status_model = status
    await player._state_mgr._refresh_periodic_data(False, status, False)
    assert player.eq_preset is None


@pytest.mark.asyncio
async def test_unapplied_graphic_preset_is_detected_by_readback(mock_client):
    player = Player(mock_client)
    player._status_model = PlayerStatus(source="wifi", eq_preset="rock")
    player._eq_presets = ["Rock", "Flat"]
    player._state_mgr._remember_eq_band({"EQStat": "On", "Name": "Rock"})
    player.client.set_eq_preset = AsyncMock()
    player.client.get_eq = AsyncMock(return_value={"EQStat": "On", "Name": "Rock"})
    player.client.get_peq_bands = AsyncMock(return_value=PEQSettings(enabled=False))
    with pytest.raises(WiiMResponseError):
        await player.set_eq_preset("Flat")
    assert player.eq_preset == "Rock"


@pytest.mark.asyncio
async def test_failed_post_command_readback_marks_graphic_state_unknown(mock_client):
    player = Player(mock_client)
    player._eq_presets = ["Rock", "Flat"]
    player._state_mgr._remember_eq_band({"EQStat": "On", "Name": "Rock"})
    player.client.set_eq_preset = AsyncMock()
    player.client.get_eq = AsyncMock(side_effect=WiiMResponseError("unavailable"))
    with pytest.raises(WiiMResponseError):
        await player.set_eq_preset("Flat")
    assert player.eq_preset is None


@pytest.mark.asyncio
async def test_failed_graphic_command_preserves_previous_state(mock_client):
    player = Player(mock_client)
    player._eq_presets = ["Rock", "Flat"]
    player._state_mgr._remember_eq_band({"EQStat": "On", "Name": "Rock"})
    player.client.set_eq_preset = AsyncMock(side_effect=WiiMResponseError("rejected"))
    with pytest.raises(WiiMResponseError):
        await player.set_eq_preset("Flat")
    assert player.eq_preset == "Rock"


@pytest.mark.asyncio
async def test_peq_off_is_read_back_and_does_not_disable_active_graphic_eq(mock_client):
    player = Player(mock_client)
    player._peq_presets = ["Night"]
    player._peq_enabled = True
    player._peq_preset = "Night"
    player.client.set_peq_enabled = AsyncMock()
    player.client.get_peq_bands = AsyncMock(
        side_effect=[PEQSettings(enabled=True, name="Night"), PEQSettings(enabled=False), PEQSettings(enabled=False)]
    )
    player.client.get_eq = AsyncMock(return_value={"EQStat": "Off", "Name": "Flat"})
    await player.set_peq_preset("Off")
    player.client.set_peq_enabled.assert_awaited_once_with(False)
    assert player.peq_enabled is False
    assert player.eq_preset == "Off"
    player._state_mgr._remember_eq_band({"EQStat": "On", "Name": "Flat"})
    await player.set_peq_preset("Off")
    player.client.set_peq_enabled.assert_awaited_once_with(False)
    assert player.eq_preset == "Flat"


@pytest.mark.asyncio
async def test_peq_off_checks_for_external_changes_before_noop(mock_client):
    player = Player(mock_client)
    player._peq_presets = ["Night"]
    player._peq_enabled = False  # Previously observed graphic EQ, now stale.
    player.client.set_peq_enabled = AsyncMock()
    player.client.get_peq_bands = AsyncMock(
        side_effect=[PEQSettings(enabled=True, name="Night"), PEQSettings(enabled=False)]
    )
    player.client.get_eq = AsyncMock(return_value={"EQStat": "Off", "Name": "Flat"})
    await player.set_peq_preset("Off")
    player.client.set_peq_enabled.assert_awaited_once_with(False)
    assert player.peq_enabled is False


@pytest.mark.asyncio
async def test_peq_off_raises_when_device_still_reports_peq_on(mock_client):
    player = Player(mock_client)
    player._peq_presets = ["Night"]
    player._peq_enabled = True
    player._peq_preset = "Night"
    player.client.set_peq_enabled = AsyncMock()
    player.client.get_peq_bands = AsyncMock(return_value=PEQSettings(enabled=True, name="Night"))
    player.client.get_eq = AsyncMock(return_value={"EQStat": "Off", "Name": "Flat"})
    with pytest.raises(WiiMResponseError):
        await player.set_peq_preset("Off")
    assert player.peq_preset == "Night"
    assert player.peq_enabled is True


@pytest.mark.asyncio
async def test_peq_selection_reconciles_graphic_state(mock_client):
    player = Player(mock_client)
    player._peq_presets = ["Night"]
    player._state_mgr._remember_eq_band({"EQStat": "On", "Name": ""})
    player.client.load_peq = AsyncMock(return_value=PEQSettings(enabled=True, name="Night"))
    player.client.get_eq = AsyncMock(return_value={"EQStat": "Off", "Name": "Flat"})
    player.client.get_peq_bands = AsyncMock(return_value=PEQSettings(enabled=True, name="Night"))
    await player.set_peq_preset("Night")
    assert player.eq_preset == "Off"
    assert player.eq_is_custom is False
    assert player.peq_enabled is True
    assert player.peq_preset == "Night"


@pytest.mark.asyncio
async def test_saved_peq_preset_named_off_remains_loadable(mock_client):
    player = Player(mock_client)
    player._peq_presets = ["Off"]
    player.client.load_peq = AsyncMock(return_value=PEQSettings(enabled=True, name="Off"))
    player.client.get_eq = AsyncMock(return_value={"EQStat": "Off", "Name": "Flat"})
    player.client.get_peq_bands = AsyncMock(return_value=PEQSettings(enabled=True, name="Off"))
    await player.set_peq_preset("Off")
    player.client.load_peq.assert_awaited_once_with("Off")
    assert player.peq_enabled is True


@pytest.mark.asyncio
async def test_verified_source_change_immediately_reads_new_inputs_eq(mock_client):
    player = Player(mock_client)
    player.client._capabilities["source_command_overrides"] = {"line_in": "auxIn"}
    player._status_model = PlayerStatus(source="wifi", eq_preset="flat")
    player._state_mgr._set_eq_source("wifi")
    player._state_mgr._remember_eq_band({"EQStat": "On", "Name": "Bass Booster", "source_name": "wifi"})
    player.client.set_source = AsyncMock()
    player._audio_config._verify_source_switch = AsyncMock(return_value=True)
    player.client.get_eq = AsyncMock(return_value={"EQStat": "On", "Name": "Spoken Word", "source_name": "auxIn"})
    await player.set_source("Line In")
    assert player.eq_preset == "Spoken Word"


@pytest.mark.asyncio
async def test_preset_list_failure_retries_and_preserves_previous_list(mock_client):
    player = Player(mock_client)
    player.client._capabilities = {"supports_eq": True, "supports_subwoofer": False}
    player.client.get_eq = AsyncMock(return_value={"EQStat": "On", "Name": "Bass Booster"})
    player.client.get_eq_presets = AsyncMock(
        side_effect=[WiiMResponseError("unavailable"), A10_PRESETS, WiiMResponseError("unavailable")]
    )
    status = PlayerStatus(source="wifi", eq_preset="0")
    player._status_model = status
    await player._state_mgr._refresh_periodic_data(True, status, False)
    await player._state_mgr._refresh_periodic_data(False, status, False)
    assert player.client.get_eq_presets.await_count == 1
    player._last_eq_presets_check -= 61
    await player._state_mgr._refresh_periodic_data(False, status, False)
    assert player.eq_presets == ["Off", *A10_PRESETS]
    await player._state_mgr._refresh_periodic_data(True, status, False)
    assert player.eq_presets == ["Off", *A10_PRESETS]


def test_eq_readback_for_previous_input_is_rejected(mock_client):
    player = Player(mock_client)
    player._state_mgr._set_eq_source("line_in")
    accepted = player._state_mgr._remember_eq_band({"source_name": "wifi", "EQStat": "On", "Name": "Rock"})
    assert accepted is False
    assert player.eq_preset is None


def test_source_change_does_not_reuse_previous_inputs_preset_list(mock_client):
    player = Player(mock_client)
    player._state_mgr._set_eq_source("wifi")
    player._eq_presets = ["Network preset"]
    player._state_mgr._set_eq_source("line_in")
    assert player.eq_presets == []


@pytest.mark.asyncio
async def test_inflight_preset_list_from_old_input_is_not_cached(mock_client):
    player = Player(mock_client)
    player.client._capabilities = {"supports_eq": True, "supports_subwoofer": False}
    player._status_model = PlayerStatus(source="wifi")
    player._state_mgr._set_eq_source("wifi")

    async def old_list():
        player._state_mgr._set_eq_source("line_in")
        return ["Network preset"]

    player.client.get_eq_presets = AsyncMock(side_effect=old_list)
    player.client.get_eq = AsyncMock(return_value={"EQStat": "Off", "Name": "Flat"})
    await player._state_mgr._refresh_periodic_data(True, player._status_model, False)
    assert player.eq_presets == []


def test_aux_and_line_in_are_only_equivalent_when_device_advertises_it(mock_client):
    player = Player(mock_client)
    player._state_mgr._set_eq_source("line_in")
    response = {"source_name": "auxIn", "EQStat": "On", "Name": "Spoken Word"}
    assert player._state_mgr._remember_eq_band(response) is False
    player.client._capabilities["source_command_overrides"] = {"line_in": "auxIn"}
    assert player._state_mgr._remember_eq_band(response) is True


@pytest.mark.asyncio
async def test_inflight_eq_read_cannot_overwrite_a_new_input(mock_client):
    player = Player(mock_client)
    player.client._capabilities = {"supports_eq": True, "supports_subwoofer": False}
    player.client.get_eq_presets = AsyncMock(return_value=A10_PRESETS)
    player._status_model = PlayerStatus(source="wifi")
    player._state_mgr._set_eq_source("wifi")

    async def old_input_response():
        player._state_mgr._set_eq_source("line_in")
        return {"source_name": "wifi", "EQStat": "On", "Name": "Bass Booster"}

    player.client.get_eq = AsyncMock(side_effect=old_input_response)
    await player._state_mgr._refresh_periodic_data(True, player._status_model, False)
    assert player.eq_preset is None
    assert player._eq_band_reconcile is True


@pytest.mark.asyncio
async def test_inflight_eq_read_cannot_overwrite_a_command_on_same_input(mock_client):
    player = Player(mock_client)
    player.client._capabilities = {"supports_eq": True, "supports_subwoofer": False}
    player.client.get_eq_presets = AsyncMock(return_value=A10_PRESETS)
    player._status_model = PlayerStatus(source="wifi")
    player._state_mgr._set_eq_source("wifi")

    async def old_response():
        player._state_mgr._invalidate_eq_state()
        return {"source_name": "wifi", "EQStat": "On", "Name": "Rock"}

    player.client.get_eq = AsyncMock(side_effect=old_response)
    await player._state_mgr._refresh_periodic_data(True, player._status_model, False)
    assert player.eq_preset is None
    assert player._eq_band_reconcile is True


@pytest.mark.asyncio
async def test_peq_state_is_read_even_when_no_saved_presets_exist(mock_client):
    player = Player(mock_client)
    player.client.get_peq_preset_list = AsyncMock(return_value={"custom": [], "preset": []})
    player.client.get_peq_bands = AsyncMock(return_value=PEQSettings(enabled=True, name=""))
    await player.initialize_peq_presets()
    assert player.peq_presets == []
    assert player.peq_enabled is True
    assert player.peq_preset is None


@pytest.mark.asyncio
async def test_periodic_refresh_reads_peq_before_preset_discovery(mock_client):
    player = Player(mock_client)
    player.client._capabilities = {"supports_eq": True, "supports_peq": True, "supports_subwoofer": False}
    player.client.get_eq_presets = AsyncMock(return_value=A10_PRESETS)
    player.client.get_eq = AsyncMock(return_value={"EQStat": "Off", "Name": "Flat"})
    player.client.get_peq_bands = AsyncMock(return_value=PEQSettings(enabled=True, name="Night"))
    player._status_model = PlayerStatus(source="wifi")
    await player._state_mgr._refresh_periodic_data(True, player._status_model, False)
    assert player.peq_enabled is True
    assert player.peq_preset == "Night"


@pytest.mark.asyncio
async def test_failed_initial_peq_state_keeps_the_preset_list_and_can_retry(mock_client):
    player = Player(mock_client)
    player.client.get_peq_preset_list = AsyncMock(return_value={"custom": ["Night"], "preset": []})
    player.client.get_peq_bands = AsyncMock(
        side_effect=[WiiMResponseError("unavailable"), PEQSettings(enabled=True, name="Night")]
    )
    await player.initialize_peq_presets()
    assert player.peq_presets == ["Night"]
    assert player.peq_enabled is None
    await player.refresh_peq_preset()
    assert player.peq_enabled is True
    assert player.peq_preset == "Night"
