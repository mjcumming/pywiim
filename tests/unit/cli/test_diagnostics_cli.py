"""Unit tests for diagnostics CLI helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

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
        self.get_mode_rename = AsyncMock(return_value=None)
        self.get_acoustic_capability = AsyncMock(return_value=None)
        self.get_all_routines = AsyncMock(return_value=None)
        self.get_sound_card_mode_support_list = AsyncMock(return_value=[])
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
    diagnostics = DeviceDiagnostics(client)  # type: ignore[arg-type]

    await diagnostics._gather_discovered_api_info()

    result = diagnostics.report["discovered_apis"]
    assert result["getAudioInputEnable"]["supported"] is False
    assert result["getModeRename"]["supported"] is True
    assert result["getModeRename"]["value"] == {"optical": "TV"}
    assert result["getSoundCardModeSupportList"]["supported"] is True
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
