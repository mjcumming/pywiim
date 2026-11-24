"""Unit tests for diagnostics CLI helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pywiim.api.constants import PEQ_PLUGIN_URI
from pywiim.api.peq import GraphicEQBand, GraphicEQSettings, PEQBand, PEQSettings, RoomCorrectionSettings
from pywiim.cli.diagnostics import DeviceDiagnostics


class DummyClient:
    """Minimal client stub for diagnostics tests."""

    def __init__(self) -> None:
        self.host = "192.168.1.100"
        self.port = 80
        self._capabilities_detected = True
        self._detect_capabilities = AsyncMock()
        self.get_debug_info = AsyncMock(return_value={})
        self.get_audio_input_enable = AsyncMock(return_value=None)
        self.get_audio_input_capability = AsyncMock(return_value=None)
        self.get_mode_rename = AsyncMock(return_value=None)
        self.get_acoustic_capability = AsyncMock(return_value=None)
        self.get_all_routines = AsyncMock(return_value=None)
        self.get_sound_card_mode_support_list = AsyncMock(return_value=[])
        self.get_graphic_eq_bands = AsyncMock(return_value=GraphicEQSettings())
        self.get_graphic_eq_preset_list = AsyncMock(return_value={"custom": [], "preset": []})
        self.get_room_correction = AsyncMock(return_value=RoomCorrectionSettings())
        self.get_room_correction_profiles = AsyncMock(return_value=[])
        self.capabilities = {
            "vendor": "wiim",
            "is_wiim_device": True,
            "upnp_description_available": True,
            "upnp_model_name": "WiiM Pro Receiver",
            "upnp_friendly_name": "Living Room",
            "upnp_has_playqueue": True,
            "upnp_has_qplay": True,
            "upnp_has_content_directory": True,
        }


@pytest.mark.asyncio
async def test_gather_capabilities_prints_upnp_description_enrichment(capsys):
    """Diagnostics output shows UPnP description.xml enrichment details."""
    diagnostics = DeviceDiagnostics(DummyClient())  # type: ignore[arg-type]

    await diagnostics._gather_capabilities()
    output = capsys.readouterr().out

    assert "UPnP model: WiiM Pro Receiver" in output
    assert "UPnP friendly name: Living Room" in output
    assert "UPnP advertised services: PlayQueue, QPlay, ContentDirectory" in output
    assert diagnostics.report["capabilities"]["upnp_description_available"] is True


@pytest.mark.asyncio
async def test_gather_device_info_prints_ethernet_mac(capsys):
    """Diagnostics prints the Ethernet MAC next to the Wi-Fi MAC."""
    from pywiim.models import DeviceInfo

    client = DummyClient()
    client.get_device_info_model = AsyncMock(  # type: ignore[attr-defined]
        return_value=DeviceInfo.model_validate({"MAC": "C0:F5:35:D7:18:B5", "ETH_MAC": "00:22:6C:30:45:66"})
    )
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    await diagnostics._gather_device_info()
    output = capsys.readouterr().out

    assert "MAC: C0:F5:35:D7:18:B5" in output
    assert "Ethernet MAC: 00:22:6C:30:45:66" in output
    assert diagnostics.report["device"]["eth_mac"] == "00:22:6C:30:45:66"


@pytest.mark.asyncio
async def test_gather_debug_info_success(capsys):
    """_gather_debug_info stores result and prints count when get_debug_info returns data."""
    client = DummyClient()
    client.get_debug_info = AsyncMock(return_value={"system_ready": "1", "slave_status": "0", "play_status": "0"})
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    await diagnostics._gather_debug_info()

    assert diagnostics.report["debug_info"] == {
        "system_ready": "1",
        "slave_status": "0",
        "play_status": "0",
    }
    assert "Gathering debug info" in capsys.readouterr().out
    client.get_debug_info.assert_called_once()


@pytest.mark.asyncio
async def test_gather_debug_info_success_empty(capsys):
    """_gather_debug_info handles empty dict from get_debug_info."""
    client = DummyClient()
    client.get_debug_info = AsyncMock(return_value={})
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    await diagnostics._gather_debug_info()

    assert diagnostics.report["debug_info"] == {}
    out = capsys.readouterr().out
    assert "getDebugInfo" in out
    assert "empty" in out or "0 fields" in out


@pytest.mark.asyncio
async def test_gather_debug_info_failure_adds_warning(capsys):
    """_gather_debug_info on exception adds warning and does not raise."""
    client = DummyClient()
    client.get_debug_info = AsyncMock(side_effect=Exception("Not supported"))
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    await diagnostics._gather_debug_info()

    assert diagnostics.report["debug_info"] == {}
    assert len(diagnostics.report["warnings"]) == 1
    assert "Failed to get debug info" in diagnostics.report["warnings"][0]
    assert "Not supported" in diagnostics.report["warnings"][0]
    out = capsys.readouterr().out
    assert "getDebugInfo" in out
    assert "optional endpoint" in out


@pytest.mark.asyncio
async def test_gather_discovered_api_info_stores_read_only_probe_results(capsys):
    """_gather_discovered_api_info records discovered WiiM endpoint payloads."""
    client = DummyClient()
    client.get_mode_rename = AsyncMock(return_value={"optical": "TV"})
    client.get_sound_card_mode_support_list = AsyncMock(return_value=[{"mode": "usb"}])
    client.get_graphic_eq_bands = AsyncMock(
        return_value=GraphicEQSettings(name="Flat", bands=[GraphicEQBand(name="band31hz", gain=0.0)])
    )
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    await diagnostics._gather_discovered_api_info()

    result = diagnostics.report["discovered_apis"]
    assert result["getAudioInputEnable"]["supported"] is False
    assert result["getAudioInputCapbility"]["supported"] is False
    assert result["getModeRename"]["supported"] is True
    assert result["getModeRename"]["value"] == {"optical": "TV"}
    assert result["getSoundCardModeSupportList"]["supported"] is True
    assert result["Eq10HP"]["supported"] is True
    assert result["Eq10HP"]["value"]["name"] == "Flat"
    assert result["RoomFit"]["supported"] is True
    assert "Probing discovered WiiM APIs" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_gather_discovered_api_info_catches_probe_errors():
    """_gather_discovered_api_info keeps later probes running after one error."""
    client = DummyClient()
    client.get_audio_input_enable = AsyncMock(side_effect=Exception("boom"))
    client.get_mode_rename = AsyncMock(return_value={"line_in": "Turntable"})
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    await diagnostics._gather_discovered_api_info()

    result = diagnostics.report["discovered_apis"]
    assert result["getAudioInputEnable"]["supported"] is False
    assert result["getAudioInputEnable"]["error"] == "boom"
    assert result["getModeRename"]["supported"] is True


@pytest.mark.asyncio
async def test_channel_balance_feature_supported():
    """_test_channel_balance reads balance when capability flag is set."""
    client = DummyClient()
    client.capabilities = {**client.capabilities, "supports_channel_balance": True}
    client.get_channel_balance = AsyncMock(return_value=0.1)
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    result = await diagnostics._test_channel_balance()

    assert result["supported"] is True
    assert result["balance"] == 0.1
    client.get_channel_balance.assert_called_once()


@pytest.mark.asyncio
async def test_channel_balance_feature_skipped_without_capability():
    """_test_channel_balance does not call HTTP when capability is false."""
    client = DummyClient()
    client.capabilities = {**client.capabilities, "supports_channel_balance": False}
    client.get_channel_balance = AsyncMock(return_value=0.0)
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    result = await diagnostics._test_channel_balance()

    assert result["supported"] is False
    client.get_channel_balance.assert_not_called()


@pytest.mark.asyncio
async def test_output_channel_feature_supported():
    """_test_output_channel reads the channel when the capability flag is set."""
    client = DummyClient()
    client.capabilities = {**client.capabilities, "supports_output_channel": True}
    client.get_output_channel = AsyncMock(return_value="left")
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    result = await diagnostics._test_output_channel()

    assert result == {"supported": True, "channel": "left"}


@pytest.mark.asyncio
async def test_output_channel_reports_independent_standalone_mode():
    """Report the group channel separately from the standalone output mode."""
    client = DummyClient()
    client.capabilities = {
        **client.capabilities,
        "supports_output_channel": True,
        "supports_output_channel_mode": True,
    }
    client.get_output_channel = AsyncMock(return_value="left")
    client.get_channel_mode = AsyncMock(return_value="right")
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    assert await diagnostics._test_output_channel() == {
        "supported": True,
        "channel": "left",
        "channel_source": "group",
        "standalone_mode": "right",
    }


@pytest.mark.asyncio
async def test_output_channel_reports_unknown_mode_when_probe_inconclusive():
    """Do not report the group channel as the standalone mode after a failed probe."""
    client = DummyClient()
    client.capabilities = {
        **client.capabilities,
        "supports_output_channel": True,
        "supports_output_channel_mode": None,
    }
    client.get_output_channel = AsyncMock(return_value="left")
    client.get_channel_mode = AsyncMock()
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    assert await diagnostics._test_output_channel() == {
        "supported": True,
        "channel": "left",
        "channel_source": "group",
        "standalone_mode": None,
    }
    client.get_channel_mode.assert_not_called()


@pytest.mark.asyncio
async def test_output_channel_feature_skipped_without_capability():
    """_test_output_channel does not call HTTP when the capability is false."""
    client = DummyClient()
    client.capabilities = {**client.capabilities, "supports_output_channel": False}
    client.get_output_channel = AsyncMock(return_value="stereo")
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    result = await diagnostics._test_output_channel()

    assert result["supported"] is False
    client.get_output_channel.assert_not_called()


@pytest.mark.asyncio
async def test_graphic_eq_feature_supported():
    """_test_graphic_eq summarizes read-only graphic EQ state."""
    client = DummyClient()
    client.capabilities = {**client.capabilities, "supports_peq": True}
    client.get_graphic_eq_bands = AsyncMock(
        return_value=GraphicEQSettings(
            enabled=True,
            name="Acoustic",
            bands=[GraphicEQBand(name="band31hz", gain=5.0)],
        )
    )
    client.get_graphic_eq_preset_list = AsyncMock(return_value={"custom": [], "preset": ["Flat", "Acoustic"]})
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    result = await diagnostics._test_graphic_eq()

    assert result["supported"] is True
    assert result["name"] == "Acoustic"
    assert result["band_count"] == 1
    assert result["preset_names"] == ["Flat", "Acoustic"]


@pytest.mark.asyncio
async def test_graphic_eq_probe_does_not_depend_on_peq_or_preset_list():
    client = DummyClient()
    client.capabilities["supports_peq"] = False
    client.get_graphic_eq_bands = AsyncMock(
        return_value=GraphicEQSettings(
            enabled=True, source_name="line-in", bands=[GraphicEQBand(name="band31hz", gain=-2)]
        )
    )
    client.get_graphic_eq_preset_list = AsyncMock(side_effect=RuntimeError("list unavailable"))

    result = await DeviceDiagnostics(client)._test_graphic_eq()  # type: ignore[arg-type]

    assert result["supported"] is True
    assert result["source_name"] == "line-in"
    assert result["bands"] == [{"name": "band31hz", "gain": -2}]
    assert result["preset_names"] is None
    assert "list unavailable" in result["preset_list_error"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ({"source_name": "wifi", "EQStat": "On", "Name": ""}, "Custom"),
        ({"source_name": "wifi", "EQStat": "Off", "Name": "Rock"}, "Off"),
        ({"source_name": "wifi", "EQStat": "On", "Name": "Night", "pluginURI": PEQ_PLUGIN_URI}, "Off"),
        ({"source_name": "wifi", "Name": "Flat"}, None),
    ],
)
async def test_eq_feature_reports_device_state_without_inventing_a_preset(response, expected):
    client = DummyClient()
    client.get_eq = AsyncMock(return_value=response)  # type: ignore[attr-defined]
    client.get_eq_presets = AsyncMock(return_value=["Flat", "Rock"])  # type: ignore[attr-defined]
    result = await DeviceDiagnostics(client)._test_eq()  # type: ignore[arg-type]
    assert result["current_preset"] == expected
    assert result["source_name"] == "wifi"
    if expected == "Custom":
        assert result["is_custom"] is True


@pytest.mark.asyncio
async def test_peq_feature_exposes_active_bands_and_survives_list_failure():
    client = DummyClient()
    client.capabilities["supports_peq"] = True
    client.get_peq_bands = AsyncMock(  # type: ignore[attr-defined]
        return_value=PEQSettings(source_name="wifi", enabled=True, name="Night", bands=[PEQBand("a", gain=2)])
    )
    client.get_peq_preset_list = AsyncMock(side_effect=RuntimeError("list unavailable"))  # type: ignore[attr-defined]

    result = await DeviceDiagnostics(client)._test_peq()  # type: ignore[arg-type]

    assert result["supported"] is True
    assert result["enabled"] is True
    assert result["source_name"] == "wifi"
    assert result["name"] == "Night"
    assert result["bands"][0]["gain"] == 2
    assert result["custom_presets"] is None
    assert "list unavailable" in result["preset_list_error"]


@pytest.mark.asyncio
async def test_peq_feature_keeps_list_when_state_is_unavailable():
    client = DummyClient()
    client.capabilities["supports_peq"] = True
    client.get_peq_bands = AsyncMock(side_effect=RuntimeError("state unavailable"))  # type: ignore[attr-defined]
    client.get_peq_preset_list = AsyncMock(  # type: ignore[attr-defined]
        return_value={"custom": ["Night"], "preset": ["Flat"]}
    )

    result = await DeviceDiagnostics(client)._test_peq()  # type: ignore[arg-type]

    assert result["enabled"] is None
    assert result["custom_presets"] == ["Night"]
    assert "state unavailable" in result["state_error"]


@pytest.mark.asyncio
async def test_eq_feature_keeps_state_when_preset_list_is_unavailable():
    client = DummyClient()
    client.get_eq = AsyncMock(return_value={"EQStat": "On", "Name": "", "source_name": "wifi"})  # type: ignore[attr-defined]
    client.get_eq_presets = AsyncMock(side_effect=RuntimeError("list unavailable"))  # type: ignore[attr-defined]

    result = await DeviceDiagnostics(client)._test_eq()  # type: ignore[arg-type]

    assert result["current_preset"] == "Custom"
    assert result["available_presets"] is None
    assert "list unavailable" in result["preset_list_error"]


@pytest.mark.asyncio
async def test_feature_output_distinguishes_unsaved_graphic_and_active_peq(capsys):
    diagnostics = DeviceDiagnostics(DummyClient())  # type: ignore[arg-type]
    for name in vars(DeviceDiagnostics):
        if name.startswith("_test_") and name != "_test_features":
            setattr(diagnostics, name, AsyncMock(return_value={"supported": False}))
    diagnostics._test_eq = AsyncMock(
        return_value={
            "supported": True,
            "source_name": "wifi",
            "current_preset": "Custom",
            "is_custom": True,
            "available_presets": ["Custom", "Rock"],
        }
    )
    diagnostics._test_peq = AsyncMock(
        return_value={
            "supported": True,
            "source_name": "wifi",
            "enabled": True,
            "name": "Night",
            "channel_mode": "Stereo",
            "bands": [{"letter": "a", "mode": 1, "frequency": 100, "q": 1, "gain": 2}],
            "custom_presets": ["Night"],
            "preset_names": ["Flat"],
        }
    )
    diagnostics._test_graphic_eq = AsyncMock(
        return_value={
            "supported": True,
            "source_name": "wifi",
            "enabled": False,
            "name": "Stale preset",
            "band_count": 1,
            "bands": [{"name": "band31hz", "gain": 2}],
            "preset_names": None,
        }
    )

    await diagnostics._test_features()

    output = capsys.readouterr().out
    assert "Current graphic EQ: Custom (unsaved)" in output
    assert "Custom ← current" not in output
    assert "Current PEQ: Night" in output
    assert "gain=2 dB" in output
    assert "Current preset: Off" in output
    assert "Built-in presets: Unknown" in output


@pytest.mark.asyncio
async def test_room_correction_feature_supported():
    """_test_room_correction summarizes read-only room correction state."""
    client = DummyClient()
    client.capabilities = {**client.capabilities, "supports_peq": True}
    client.get_room_correction = AsyncMock(
        return_value=RoomCorrectionSettings(
            enabled=False,
            source_name="default",
        )
    )
    client.get_room_correction_profiles = AsyncMock(return_value=["test"])
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    result = await diagnostics._test_room_correction()

    assert result["supported"] is True
    assert result["enabled"] is False
    assert result["source_name"] == "default"
    assert result["profiles"] == ["test"]


# ---------------------------------------------------------------------------
# WiiM Voice Remote (ADR 025): parsed state only, MAC masked, read-only
# ---------------------------------------------------------------------------


def _ble_client(*, supported=True, status_ex=None, hid=None, step=2):
    from pywiim.api.ble_remote import parse_ble_remote_identity
    from tests.unit.ble_remote_fixtures import (
        HID_CONNECTED,
        STATUS_EX_BASE,
        STATUS_EX_REMOTE_CONNECTED,
    )

    client = DummyClient()
    client.capabilities = {**client.capabilities, "supports_ble_remote": supported}
    client.get_device_info = AsyncMock(
        return_value={**STATUS_EX_BASE, **(STATUS_EX_REMOTE_CONNECTED if status_ex is None else status_ex)}
    )
    client.get_ble_remote_identity = AsyncMock(
        return_value=parse_ble_remote_identity(HID_CONNECTED if hid is None else hid)
    )
    client.get_remote_volume_step = AsyncMock(return_value=step)
    client.set_remote_volume_step = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_ble_remote_section_has_parsed_state_and_masked_mac(capsys):
    import json

    from tests.unit.ble_remote_fixtures import FAKE_REMOTE_MAC

    client = _ble_client()
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    await diagnostics._gather_ble_remote_info()

    remote = diagnostics.report["ble_remote"]
    assert remote == {
        "supported": True,
        "paired": True,
        "connected": True,
        "name": "WiiM Voice Remote",
        "mac": "XX:XX:XX:XX:XX:XX",
        "firmware": "0054",
        "battery": 100,
        "rssi": -61,
        "volume_step": 2,
        "volume_step_label": "Small Step",
    }
    dumped = json.dumps(diagnostics.report) + capsys.readouterr().out
    assert FAKE_REMOTE_MAC not in dumped
    # parsed state only, never the raw getblehidstatus body
    assert "doubleclickdisable" not in dumped
    assert "powerstatus" not in dumped


@pytest.mark.asyncio
async def test_ble_remote_section_not_connected_and_not_paired():
    from tests.unit.ble_remote_fixtures import HID_SCANNING, STATUS_EX_REMOTE_NOT_CONNECTED

    client = _ble_client(status_ex=STATUS_EX_REMOTE_NOT_CONNECTED, hid=HID_SCANNING, step=None)
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    await diagnostics._gather_ble_remote_info()

    remote = diagnostics.report["ble_remote"]
    assert (remote["paired"], remote["connected"]) == (False, False)
    assert remote["battery"] is None and remote["rssi"] is None and remote["mac"] is None
    assert remote["volume_step"] is None and remote["volume_step_label"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("supported", [False, None])
async def test_ble_remote_section_skipped_when_not_supported(supported):
    client = _ble_client(supported=supported)
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    await diagnostics._gather_ble_remote_info()

    assert "ble_remote" not in diagnostics.report
    client.get_ble_remote_identity.assert_not_awaited()
    client.get_remote_volume_step.assert_not_awaited()


@pytest.mark.asyncio
async def test_ble_remote_section_is_read_only():
    client = _ble_client()
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    await diagnostics._gather_ble_remote_info()

    client.set_remote_volume_step.assert_not_awaited()


@pytest.mark.asyncio
async def test_ble_remote_section_error_keeps_report_and_hides_mac():
    import json

    from tests.unit.ble_remote_fixtures import FAKE_REMOTE_MAC

    client = _ble_client()
    client.get_ble_remote_identity = AsyncMock(side_effect=RuntimeError(f"boom {FAKE_REMOTE_MAC}"))
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    await diagnostics._gather_ble_remote_info()

    remote = diagnostics.report["ble_remote"]
    assert remote["supported"] is True
    assert remote["error_type"] == "RuntimeError"
    assert FAKE_REMOTE_MAC not in json.dumps(diagnostics.report)


@pytest.mark.asyncio
async def test_ble_remote_section_detects_capabilities_first_in_discovered_only_mode():
    client = _ble_client()
    client._capabilities_detected = False
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    await diagnostics._gather_ble_remote_info()

    client._detect_capabilities.assert_awaited_once()


@pytest.mark.asyncio
async def test_full_diagnostic_and_discovered_only_both_gather_ble_remote():
    from unittest.mock import patch

    diagnostics = DeviceDiagnostics(_ble_client())  # type: ignore[arg-type]
    names = [
        "_gather_device_info",
        "_gather_capabilities",
        "_gather_status",
        "_gather_debug_info",
        "_gather_discovered_api_info",
        "_gather_ble_remote_info",
        "_test_endpoints",
        "_test_features",
    ]
    with (
        patch.multiple(diagnostics, **{n: AsyncMock() for n in names}),
        patch.object(diagnostics, "_generate_summary", return_value={}),
    ):
        await diagnostics.run_full_diagnostic()
        diagnostics._gather_ble_remote_info.assert_awaited_once()

    import inspect

    from pywiim.cli import diagnostics as module

    assert "_gather_ble_remote_info" in inspect.getsource(module.main)
