"""Role-specific output channel behavior for WiiM and other LinkPlay players."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pywiim.api.base import ApiResponse
from pywiim.capabilities import WiiMCapabilities
from pywiim.exceptions import WiiMError, WiiMResponseError, WiiMTimeoutError
from pywiim.models import DeviceInfo, PlayerStatus
from pywiim.player import Player


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (ApiResponse(parsed=0, raw=None), "stereo"),
        (ApiResponse(parsed=1, raw=None), "left"),
        (ApiResponse(parsed=2, raw=None), "right"),
        (ApiResponse(parsed=3, raw=None), "mono"),
        (ApiResponse(parsed=None, raw=" 2 "), "right"),
        (ApiResponse(parsed=9, raw=None), None),
        (ApiResponse(parsed=True, raw=None), None),
        (ApiResponse(parsed=None, raw="unknown command"), None),
    ],
)
@pytest.mark.asyncio
async def test_read_solo_channel_mode(mock_client, response, expected):
    """The separate mode endpoint is decoded independently of player-status ch."""
    mock_client._request = AsyncMock(return_value=response)

    assert await mock_client.get_channel_mode() == expected
    mock_client._request.assert_awaited_once_with("/httpapi.asp?command=getChannelMode")


@pytest.mark.parametrize(("channel", "number"), [("stereo", 0), ("left", 1), ("right", 2)])
@pytest.mark.asyncio
async def test_write_solo_channel_mode(mock_client, channel, number):
    mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

    await mock_client.set_channel_mode(channel)

    mock_client._request.assert_awaited_once_with(f"/httpapi.asp?command=setChannelMode:{number}")


@pytest.mark.asyncio
async def test_rejected_solo_channel_mode_write(mock_client):
    mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="unknown command"))

    with pytest.raises(WiiMResponseError):
        await mock_client.set_channel_mode("left")


@pytest.mark.parametrize(
    ("mode_response", "supported"),
    [
        (ApiResponse(parsed=0, raw=None), True),
        (ApiResponse(parsed=3, raw=None), True),
        (ApiResponse(parsed=9, raw=None), True),
        (ApiResponse(parsed=None, raw="1"), True),
        (ApiResponse(parsed=True, raw=None), None),
        (ApiResponse(parsed=None, raw="unknown command"), False),
        (ApiResponse(parsed={}, raw=None), None),
    ],
)
@pytest.mark.asyncio
async def test_capability_probe_is_read_only(mock_client, mode_response, supported):
    device = DeviceInfo(uuid="channel-mode-test", model="WiiM Pro", firmware="4.8.827634")
    mock_client.get_status = AsyncMock(return_value={"status": "ok"})

    async def respond(endpoint, *args, **kwargs):
        if endpoint.endswith("getChannelMode"):
            return mode_response
        if endpoint.endswith("getPlayerStatusEx"):
            return ApiResponse(parsed={"ch": "0", "status": "stop", "vol": "0"}, raw=None)
        return ApiResponse(parsed={"status": "ok"}, raw=None)

    mock_client._request = AsyncMock(side_effect=respond)
    capabilities = await WiiMCapabilities().detect_capabilities(mock_client, device)

    assert capabilities["supports_output_channel_mode"] is supported
    assert capabilities["supports_output_channel"] is True
    assert not any("setChannelMode" in str(call) for call in mock_client._request.call_args_list)


@pytest.mark.asyncio
async def test_mode_alone_exposes_output_channel(mock_client):
    device = DeviceInfo(uuid="channel-mode-only", model="WiiM Pro", firmware="4.8.827634")
    mock_client.get_status = AsyncMock(return_value={"status": "ok"})

    async def respond(endpoint, *args, **kwargs):
        if endpoint.endswith("getChannelMode"):
            return ApiResponse(parsed=0, raw=None)
        if endpoint.endswith("getPlayerStatusEx"):
            return ApiResponse(parsed={"status": "stop", "vol": "0"}, raw=None)
        return ApiResponse(parsed={"status": "ok"}, raw=None)

    mock_client._request = AsyncMock(side_effect=respond)
    capabilities = await WiiMCapabilities().detect_capabilities(mock_client, device)

    assert capabilities["supports_output_channel_mode"] is True
    assert capabilities["supports_output_channel"] is True


@pytest.mark.asyncio
async def test_mode_probe_timeout_is_inconclusive(mock_client):
    device = DeviceInfo(uuid="channel-mode-timeout", model="WiiM Pro", firmware="4.8.827634")
    mock_client.get_status = AsyncMock(return_value={"status": "ok"})

    async def respond(endpoint, *args, **kwargs):
        if endpoint.endswith("getChannelMode"):
            raise WiiMTimeoutError("temporarily unavailable")
        if endpoint.endswith("getPlayerStatusEx"):
            return ApiResponse(parsed={"ch": "0", "status": "stop", "vol": "0"}, raw=None)
        return ApiResponse(parsed={"status": "ok"}, raw=None)

    mock_client._request = AsyncMock(side_effect=respond)
    capabilities = await WiiMCapabilities().detect_capabilities(mock_client, device)

    assert capabilities["supports_output_channel_mode"] is None
    assert capabilities["supports_output_channel"] is True


def test_role_selects_distinct_cached_values(mock_client):
    mock_client._capabilities.update(supports_output_channel=True, supports_output_channel_mode=True)
    player = Player(mock_client)
    player._status_model = PlayerStatus.model_validate({"ch": "2"})
    player._output_channel_mode = "left"

    assert player.output_channel == "left"
    player._detected_role = "master"
    assert player.output_channel == "right"
    player._detected_role = "slave"
    assert player.output_channel == "right"
    player._detected_role = "solo"
    assert player.output_channel == "left"


@pytest.mark.parametrize("role", ["solo", "master", "slave"])
@pytest.mark.asyncio
async def test_setting_channel_routes_by_live_role(mock_client, role):
    mock_client._capabilities.update(supports_output_channel=True, supports_output_channel_mode=True)
    mock_client.set_output_channel = AsyncMock()
    mock_client.set_channel_mode = AsyncMock()
    callback = MagicMock()
    player = Player(mock_client, on_state_changed=callback)
    player._detected_role = role
    player._status_model = PlayerStatus.model_validate({"ch": "2"})
    player._output_channel_mode = "stereo"

    await player.set_output_channel("left")

    assert player.output_channel == "left"
    if role == "solo":
        mock_client.set_channel_mode.assert_awaited_once_with("left")
        mock_client.set_output_channel.assert_not_awaited()
        assert player._status_model.output_channel == "right"
    else:
        mock_client.set_output_channel.assert_awaited_once_with("left")
        mock_client.set_channel_mode.assert_not_awaited()
        assert player._output_channel_mode == "stereo"
    callback.assert_called_once()


@pytest.mark.asyncio
async def test_legacy_solo_player_keeps_existing_channel_command(mock_client):
    mock_client._capabilities.update(supports_output_channel=True, supports_output_channel_mode=False)
    mock_client.set_output_channel = AsyncMock()
    mock_client.set_channel_mode = AsyncMock()
    player = Player(mock_client)
    player._status_model = PlayerStatus.model_validate({"ch": "0"})

    await player.set_output_channel("right")

    assert player.output_channel == "right"
    mock_client.set_output_channel.assert_awaited_once_with("right")
    mock_client.set_channel_mode.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_solo_write_does_not_change_cache_or_notify(mock_client):
    mock_client._capabilities.update(supports_output_channel=True, supports_output_channel_mode=True)
    mock_client.set_channel_mode = AsyncMock(side_effect=WiiMResponseError("unknown command"))
    callback = MagicMock()
    player = Player(mock_client, on_state_changed=callback)
    player._output_channel_mode = "stereo"

    with pytest.raises(WiiMResponseError):
        await player.set_output_channel("left")

    assert player.output_channel == "stereo"
    callback.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_reads_solo_mode_after_role_change(mock_client):
    mock_client._capabilities.update(supports_output_channel=True, supports_output_channel_mode=True)
    mock_client.get_channel_mode = AsyncMock(return_value="left")
    player = Player(mock_client)
    player._detected_role = "slave"
    player._status_model = PlayerStatus.model_validate({"ch": "2"})
    player._coverart_mgr.enrich_metadata_on_track_change = AsyncMock()

    async def become_solo(group_ops):
        group_ops.player._detected_role = "solo"

    with patch(
        "pywiim.player.groupops.GroupOperations._synchronize_group_state", autospec=True, side_effect=become_solo
    ):
        await player._state_mgr._finalize_refresh(False)

    assert player.output_channel == "left"
    mock_client.get_channel_mode.assert_awaited_once()


@pytest.mark.asyncio
async def test_unknown_solo_mode_does_not_fall_back_to_group_channel(mock_client):
    mock_client._capabilities.update(supports_output_channel=True, supports_output_channel_mode=True)
    player = Player(mock_client)
    player._status_model = PlayerStatus.model_validate({"ch": "1"})

    assert player.output_channel is None


@pytest.mark.asyncio
async def test_inconclusive_probe_does_not_write_group_channel_while_solo(mock_client):
    mock_client._capabilities.update(supports_output_channel=True, supports_output_channel_mode=None)
    mock_client.set_output_channel = AsyncMock()
    player = Player(mock_client)
    player._status_model = PlayerStatus.model_validate({"ch": "1"})

    assert player.output_channel is None
    with pytest.raises(WiiMError, match="not yet known"):
        await player.set_output_channel("right")
    mock_client.set_output_channel.assert_not_awaited()


@pytest.mark.parametrize(("probe_result", "expected"), [((True, "left"), "left"), ((False, None), "right")])
@pytest.mark.asyncio
async def test_inconclusive_probe_recovers_during_solo_refresh(mock_client, probe_result, expected):
    mock_client._capabilities.update(supports_output_channel=True, supports_output_channel_mode=None)
    mock_client._probe_channel_mode = AsyncMock(return_value=probe_result)
    player = Player(mock_client)
    player._status_model = PlayerStatus.model_validate({"ch": "2"})
    player._coverart_mgr.enrich_metadata_on_track_change = AsyncMock()

    with patch("pywiim.player.groupops.GroupOperations._synchronize_group_state", new=AsyncMock()):
        await player._state_mgr._finalize_refresh(False)

    assert player.output_channel == expected
    assert mock_client.capabilities["supports_output_channel_mode"] is probe_result[0]


@pytest.mark.asyncio
async def test_cached_pre_upgrade_capabilities_are_probed(mock_client):
    """An older capability cache must not silently select the group command."""
    mock_client._capabilities.update(supports_output_channel=True)
    mock_client._capabilities.pop("supports_output_channel_mode", None)
    mock_client._probe_channel_mode = AsyncMock(return_value=(True, "left"))
    player = Player(mock_client)
    player._status_model = PlayerStatus.model_validate({"ch": "2"})
    player._coverart_mgr.enrich_metadata_on_track_change = AsyncMock()

    assert player.output_channel is None
    with patch("pywiim.player.groupops.GroupOperations._synchronize_group_state", new=AsyncMock()):
        await player._state_mgr._finalize_refresh(False)

    assert player.output_channel == "left"
    assert mock_client.capabilities["supports_output_channel_mode"] is True
