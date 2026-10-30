"""A10 MkII input evidence from wiim#187; no command assumptions for other devices."""

from unittest.mock import AsyncMock

import pytest

from pywiim.capabilities import _probe_wiim_input_metadata, detect_device_capabilities
from pywiim.exceptions import WiiMError
from pywiim.models import AudioInputCapability, DeviceInfo, PlayerStatus
from pywiim.player import Player


@pytest.fixture(params=["AudioPro_A10MKII_WiiM", "Audio Pro A10 MkII"])
def a10_client(mock_client, request):
    info = DeviceInfo(uuid="a10", model=request.param, firmware="Linkplay.5.2.825329")
    mock_client._capabilities = detect_device_capabilities(info)
    mock_client.get_audio_input_capability = AsyncMock(
        return_value=AudioInputCapability.model_validate(
            {"ver": "1.0", "audioInput": [{"mode": mode} for mode in ["wifi", "auxIn", "bluetooth"]]}
        )
    )
    mock_client.get_audio_input_enable = AsyncMock(return_value=None)
    mock_client.get_mode_rename = AsyncMock(return_value={})
    return mock_client


async def test_a10_probe_and_catalog(a10_client):
    await _probe_wiim_input_metadata(a10_client, a10_client.capabilities)
    a10_client.get_audio_input_capability.assert_awaited_once()
    if not a10_client.capabilities["is_wiim_device"]:
        a10_client.get_audio_input_enable.assert_not_called()
        a10_client.get_mode_rename.assert_not_called()
    player = Player(a10_client)
    player._device_info = DeviceInfo(
        uuid="a10",
        model="AudioPro_A10MKII_WiiM",
        input_list=["wifi", "bluetooth", "line-in", "aux", "optical", "RCA"],
    )
    player._status_model = PlayerStatus(source="wifi")
    assert set(player.available_sources) == {"Network", "Bluetooth", "Line In"}
    assert {entry["id"] for entry in player.source_catalog if entry["selectable"]} == {
        "network",
        "bluetooth",
        "line_in",
    }


@pytest.mark.parametrize("source", ["Aux In", "aux", "aux-in", "auxIn", "Line In", "line_in", "line-in"])
async def test_a10_switch_preserves_wire_case_and_mode60_identity(a10_client, source):
    await _probe_wiim_input_metadata(a10_client, a10_client.capabilities)
    player = Player(a10_client)
    player._status_model = PlayerStatus(source="wifi")
    a10_client.get_player_status_model = AsyncMock(return_value=PlayerStatus.model_validate({"mode": "60"}))
    await player.set_source(source)
    a10_client._request.assert_awaited_once_with("/httpapi.asp?command=setPlayerCmd:switchmode:auxIn")
    assert player.source == "line_in"
    assert player.source_name == "Line In"


async def test_a10_unlisted_input_rejected_even_when_current(a10_client):
    await _probe_wiim_input_metadata(a10_client, a10_client.capabilities)
    player = Player(a10_client)
    player._device_info = DeviceInfo(uuid="a10", input_list=["wifi", "optical"])
    player._status_model = PlayerStatus(source="optical")
    assert "Optical In" not in player.available_sources
    assert not next(entry for entry in player.source_catalog if entry["id"] == "optical")["selectable"]
    with pytest.raises(ValueError, match="not directly selectable"):
        await player.set_source("Optical In")
    a10_client._request.assert_not_called()


@pytest.mark.parametrize(
    "response",
    [None, {}, {"audioInput": []}, {"audioInput": [{"mode": "line-in"}]}, {"audioInput": [{"mode": "auxin"}]}],
)
async def test_a10_without_exact_auxin_evidence_keeps_block(a10_client, response):
    a10_client.get_audio_input_capability.return_value = (
        AudioInputCapability.model_validate(response) if response is not None else None
    )
    before = a10_client.capabilities.copy()
    await _probe_wiim_input_metadata(a10_client, a10_client.capabilities)
    assert a10_client.capabilities["non_selectable_source_ids"] == before["non_selectable_source_ids"]
    assert not a10_client.capabilities.get("source_command_overrides")
    assert a10_client.capabilities.get("selectable_source_ids") is None
    if before["non_selectable_source_ids"]:
        with pytest.raises(ValueError, match="not directly selectable"):
            await Player(a10_client).set_source("Aux In")
        a10_client._request.assert_not_called()


async def test_a10_query_failure_preserves_fallback(a10_client):
    a10_client.get_audio_input_capability.side_effect = WiiMError("unknown command")
    before = a10_client.capabilities.copy()
    await _probe_wiim_input_metadata(a10_client, a10_client.capabilities)
    assert a10_client.capabilities == before


@pytest.mark.parametrize("model", ["AudioPro_A15MKII", "AudioPro_A10", "AudioPro_A100MKII", "Arylic A10"])
async def test_unverified_devices_not_probed_or_changed(a10_client, model):
    caps = detect_device_capabilities(DeviceInfo(uuid="other", model=model))
    before = caps.copy()
    await _probe_wiim_input_metadata(a10_client, caps)
    a10_client.get_audio_input_capability.assert_not_called()
    assert caps == before


@pytest.mark.parametrize(
    "source,command",
    [
        ("Aux In", "line-in"),
        ("Line In", "line-in"),
        ("Bluetooth", "bluetooth"),
        ("Network", "wifi"),
        ("Optical In", "optical"),
        ("RCA", "RCA"),
    ],
)
async def test_existing_source_commands_unchanged(mock_client, source, command):
    player = Player(mock_client)
    mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus())
    await player.set_source(source)
    mock_client._request.assert_awaited_once_with(f"/httpapi.asp?command=setPlayerCmd:switchmode:{command}")


async def test_runtime_detection_retains_a10_input_evidence(a10_client):
    from pywiim.capabilities import WiiMCapabilities

    detector = WiiMCapabilities()
    caps = await detector.detect_capabilities(
        a10_client,
        DeviceInfo(uuid="a10", model=a10_client.capabilities["device_type"], firmware="Linkplay.5.2.825329"),
    )
    assert caps["source_command_overrides"]["line_in"] == "auxIn"
    assert caps["selectable_source_ids"] == ["network", "line_in", "bluetooth"]


async def test_a10_acknowledged_noop_does_not_update_state(a10_client):
    await _probe_wiim_input_metadata(a10_client, a10_client.capabilities)
    player = Player(a10_client)
    player._status_model = PlayerStatus(source="wifi")
    a10_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(source="wifi"))
    with pytest.raises(WiiMError, match="did not change source"):
        await player.set_source("Line In")
    assert player.source == "network"


async def test_force_refresh_clears_obsolete_command_evidence(a10_client):
    from pywiim.capabilities import WiiMCapabilities

    detector = WiiMCapabilities()
    info = DeviceInfo(uuid="a10", model=a10_client.capabilities["device_type"])
    detected = await detector.detect_capabilities(a10_client, info)
    a10_client.capabilities.update(detected)
    assert a10_client.capabilities["source_command_overrides"]["line_in"] == "auxIn"
    a10_client.get_audio_input_capability.side_effect = WiiMError("unknown command")
    detected = await detector.detect_capabilities(a10_client, info, force=True)
    a10_client.capabilities.update(detected)
    assert a10_client.capabilities["source_command_overrides"] == {}
    assert a10_client.capabilities["selectable_source_ids"] is None
