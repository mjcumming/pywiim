"""Regression tests for verified WiiM LV2 EQ writes and profile operations."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock
from urllib.parse import unquote

import pytest

from pywiim.api.base import ApiResponse
from pywiim.api.constants import GEQ_PLUGIN_URI, PEQ_PLUGIN_URI
from pywiim.api.peq import GraphicEQBand, PEQBand
from pywiim.exceptions import WiiMResponseError


def state(plugin: str, bands: list[dict], *, source: str = "wifi", name: str = "", enabled: bool = True) -> dict:
    return {
        "status": "OK",
        "pluginURI": plugin,
        "source_name": source,
        "EQStat": "On" if enabled else "Off",
        "channelMode": "Stereo",
        "Name": name,
        "EQBand": bands,
    }


def result(data: object) -> ApiResponse:
    return ApiResponse(
        parsed=data if isinstance(data, (dict, list)) else None, raw=data if isinstance(data, str) else None
    )


def command_payload(call) -> dict:
    return json.loads(unquote(call.args[0]).split(":", 1)[1])


def full_peq(gain: float = 2.0, *, name: str = "") -> dict:
    bands = [PEQBand(letter, mode=1, frequency=90, q=1, gain=gain if letter == "a" else 0) for letter in "abcdefghij"]
    return state(PEQ_PLUGIN_URI, [param for band in bands for param in band.to_api_params()], name=name)


@pytest.mark.asyncio
async def test_graphic_band_write_checks_device_and_readback_without_peq_capability(mock_client):
    mock_client._capabilities = {"supports_eq": True, "supports_peq": False}
    initial = state(GEQ_PLUGIN_URI, [{"param_name": "band31hz", "value": 5.0}], name="Acoustic")
    applied = state(GEQ_PLUGIN_URI, [{"param_name": "band31hz", "value": -2.0}])
    mock_client._request = AsyncMock(side_effect=[result(initial), result({"status": "OK"}), result(applied)])

    settings = await mock_client.set_graphic_eq_bands([GraphicEQBand("band31hz", -2.0)], source_name="wifi")

    assert settings.bands[0].gain == -2.0
    write = mock_client._request.await_args_list[1]
    assert "EQSetLV2SourceBand" in write.args[0]
    assert command_payload(write) == {
        "source_name": "wifi",
        "pluginURI": GEQ_PLUGIN_URI,
        "channelMode": "Stereo",
        "EQBand": [{"param_name": "band31hz", "value": -2.0}],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bands",
    [
        [],
        [GraphicEQBand("band31hz", 13)],
        [GraphicEQBand("band31hz", float("nan"))],
        [GraphicEQBand("unknown", 0)],
        [GraphicEQBand("band31hz", 1), GraphicEQBand("band31hz", 2)],
    ],
)
async def test_graphic_band_rejects_invalid_input_before_any_request(mock_client, bands):
    with pytest.raises(ValueError):
        await mock_client.set_graphic_eq_bands(bands)
    mock_client._request.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_readback",
    [
        state(GEQ_PLUGIN_URI, [{"param_name": "band31hz", "value": 5.0}]),
        state(GEQ_PLUGIN_URI, []),
        state(GEQ_PLUGIN_URI, [{"param_name": "band31hz", "value": -2.0}], source="bluetooth"),
        state(PEQ_PLUGIN_URI, [{"param_name": "band31hz", "value": -2.0}]),
    ],
)
async def test_graphic_ok_does_not_hide_failed_or_wrong_source_write(mock_client, bad_readback):
    initial = state(GEQ_PLUGIN_URI, [{"param_name": "band31hz", "value": 5.0}])
    mock_client._request = AsyncMock(side_effect=[result(initial), result({"status": "OK"}), result(bad_readback)])
    with pytest.raises(WiiMResponseError):
        await mock_client.set_graphic_eq_bands([GraphicEQBand("band31hz", -2.0)], source_name="wifi")


@pytest.mark.asyncio
async def test_one_tenth_db_noop_does_not_pass_rounding_tolerance(mock_client):
    unchanged = state(GEQ_PLUGIN_URI, [{"param_name": "band31hz", "value": 1.0}])
    mock_client._request = AsyncMock(side_effect=[result(unchanged), result({"status": "OK"}), result(unchanged)])
    with pytest.raises(WiiMResponseError):
        await mock_client.set_graphic_eq_bands([GraphicEQBand("band31hz", 1.1)], source_name="wifi")


@pytest.mark.asyncio
async def test_graphic_preflight_rejects_unproved_plugin_and_explicit_failure(mock_client):
    mock_client._request = AsyncMock(return_value=result({"status": "OK"}))
    with pytest.raises(WiiMResponseError):
        await mock_client.set_graphic_eq_bands([GraphicEQBand("band31hz", 1)])
    assert mock_client._request.await_count == 1


@pytest.mark.asyncio
async def test_graphic_preset_list_does_not_depend_on_peq_capability(mock_client):
    mock_client._capabilities = {"supports_eq": True, "supports_peq": False}
    mock_client._request = AsyncMock(return_value=result({"status": "OK", "custom": [], "preset": ["Acoustic"]}))
    assert await mock_client.get_graphic_eq_preset_list() == {"custom": [], "preset": ["Acoustic"]}


@pytest.mark.asyncio
async def test_graphic_preset_list_does_not_treat_a_failed_response_as_empty(mock_client):
    mock_client._request = AsyncMock(return_value=result({"status": "Failed"}))
    with pytest.raises(WiiMResponseError):
        await mock_client.get_graphic_eq_preset_list()


@pytest.mark.asyncio
async def test_peq_write_requires_observed_values_and_rejects_silent_noop(mock_client):
    before = state(PEQ_PLUGIN_URI, [{"param_name": "a_gain", "value": 0}], enabled=False)
    after = state(PEQ_PLUGIN_URI, [{"param_name": "a_gain", "value": 0}])
    mock_client._request = AsyncMock(side_effect=[result(before), result({"status": "OK"}), result(after)])
    with pytest.raises(WiiMResponseError):
        await mock_client.set_peq_bands([PEQBand("a", mode=1, frequency=90, q=1, gain=2)], source_name="wifi")


@pytest.mark.asyncio
async def test_peq_lr_write_verifies_both_channels(mock_client):
    before = full_peq()
    left = PEQBand("a", mode=1, frequency=90, q=1, gain=2)
    right = PEQBand("a", mode=1, frequency=90, q=1, gain=-2)
    applied = state(PEQ_PLUGIN_URI, [])
    applied["channelMode"] = "L/R"
    applied["EQBandL"] = left.to_api_params()
    applied["EQBandR"] = right.to_api_params()
    mock_client._request = AsyncMock(side_effect=[result(before), result({"status": "OK"}), result(applied)])
    await mock_client.set_peq_bands_lr([left], [right], source_name="wifi")
    assert command_payload(mock_client._request.await_args_list[1])["EQBandR"] == right.to_api_params()

    applied["EQBandR"] = left.to_api_params()
    mock_client._request = AsyncMock(side_effect=[result(before), result({"status": "OK"}), result(applied)])
    with pytest.raises(WiiMResponseError, match="a_gain"):
        await mock_client.set_peq_bands_lr([left], [right], source_name="wifi")


@pytest.mark.asyncio
async def test_peq_rejects_invalid_or_duplicate_bands_before_writing(mock_client):
    for bands in ([], [PEQBand("z")], [PEQBand("a"), PEQBand("a")], [PEQBand("a", gain=13)]):
        with pytest.raises(ValueError):
            await mock_client.set_peq_bands(bands, source_name="wifi")
    mock_client._request.assert_not_awaited()


@pytest.mark.asyncio
async def test_peq_save_rejects_existing_profile_without_explicit_overwrite(mock_client):
    mock_client.get_peq_preset_list = AsyncMock(return_value={"custom": ["Listening"], "preset": []})
    with pytest.raises(ValueError, match="already exists"):
        await mock_client.save_peq("Listening", source_name="wifi")
    mock_client._request.assert_not_awaited()


@pytest.mark.asyncio
async def test_peq_save_detects_missing_new_profile_despite_ok(mock_client):
    mock_client.get_peq_preset_list = AsyncMock(return_value={"custom": [], "preset": []})
    peq = full_peq()
    mock_client._request = AsyncMock(side_effect=[result(peq), result({"status": "OK"})])
    with pytest.raises(WiiMResponseError):
        await mock_client.save_peq("Listening", source_name="wifi")
    assert mock_client._request.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("overwrite", [False, True])
async def test_peq_save_loads_and_verifies_saved_curve(mock_client, overwrite):
    before_list = {"custom": ["Listening"] if overwrite else [], "preset": []}
    mock_client.get_peq_preset_list = AsyncMock(side_effect=[before_list, {"custom": ["Listening"], "preset": []}])
    before = full_peq()
    saved = full_peq(name="Listening")
    mock_client._request = AsyncMock(
        side_effect=[result(before), result({"status": "OK"}), result(saved), result(saved), result(saved)]
    )

    await mock_client.save_peq("Listening", source_name="wifi", overwrite=overwrite)

    assert "EQv2SourceLoad" in mock_client._request.await_args_list[3].args[0]
    assert mock_client._request.await_count == 5


@pytest.mark.asyncio
async def test_peq_overwrite_reloads_stale_preset_and_restores_edited_bands(mock_client):
    mock_client.get_peq_preset_list = AsyncMock(return_value={"custom": ["Listening"], "preset": []})
    edited = full_peq()
    named_edited = full_peq(name="Listening")
    stale = full_peq(-3.0, name="Listening")
    restored = full_peq()
    mock_client._request = AsyncMock(
        side_effect=[
            result(edited),
            result({"status": "OK"}),
            result(named_edited),
            result(stale),
            result(stale),
            result(stale),
            result({"status": "OK"}),
            result(restored),
        ]
    )
    with pytest.raises(WiiMResponseError, match="previous bands were restored"):
        await mock_client.save_peq("Listening", source_name="wifi", overwrite=True)
    assert "EQSetLV2SourceBand" in mock_client._request.await_args_list[6].args[0]


@pytest.mark.asyncio
async def test_peq_delete_requires_absence_in_fresh_list(mock_client):
    mock_client.get_peq_preset_list = AsyncMock(return_value={"custom": ["Listening"], "preset": []})
    mock_client._request = AsyncMock(return_value=result({"status": "OK"}))
    with pytest.raises(WiiMResponseError):
        await mock_client.delete_peq("Listening")


@pytest.mark.asyncio
async def test_peq_rename_rejects_collision_and_checks_result(mock_client):
    mock_client.get_peq_preset_list = AsyncMock(return_value={"custom": ["Old", "Existing"], "preset": []})
    with pytest.raises(ValueError, match="already exists"):
        await mock_client.rename_peq("Old", "Existing")
    mock_client._request.assert_not_awaited()
    mock_client.get_peq_preset_list = AsyncMock(return_value={"custom": ["Old"], "preset": []})
    mock_client._request = AsyncMock(return_value=result({"status": "OK"}))
    with pytest.raises(WiiMResponseError):
        await mock_client.rename_peq("Old", "New")


@pytest.mark.asyncio
async def test_peq_load_requires_independent_current_state_readback(mock_client):
    before = full_peq(name="Old")
    claimed = full_peq(name="Listening")
    mock_client._request = AsyncMock(side_effect=[result(before), result(claimed), result(before)])
    with pytest.raises(WiiMResponseError, match="not confirmed"):
        await mock_client.load_peq("Listening", source_name="wifi")


@pytest.mark.asyncio
async def test_peq_load_does_not_fabricate_missing_band_values(mock_client):
    before = full_peq(name="Old")
    claimed = full_peq(name="Listening")
    missing = state(PEQ_PLUGIN_URI, [], name="Listening")
    mock_client._request = AsyncMock(side_effect=[result(before), result(claimed), result(missing)])
    with pytest.raises(WiiMResponseError, match="incomplete"):
        await mock_client.load_peq("Listening", source_name="wifi")


@pytest.mark.asyncio
async def test_current_source_change_is_not_reported_as_success(mock_client):
    before = state(GEQ_PLUGIN_URI, [{"param_name": "band31hz", "value": 5.0}])
    applied = state(GEQ_PLUGIN_URI, [{"param_name": "band31hz", "value": -2.0}])
    switched = state(GEQ_PLUGIN_URI, [{"param_name": "band31hz", "value": 0}], source="bluetooth")
    mock_client._request = AsyncMock(
        side_effect=[result(before), result({"status": "OK"}), result(applied), result(switched)]
    )
    with pytest.raises(WiiMResponseError, match="source changed"):
        await mock_client.set_graphic_eq_bands([GraphicEQBand("band31hz", -2.0)])
