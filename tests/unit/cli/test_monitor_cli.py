"""Unit tests for wiim-monitor hardware polling helpers."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, PropertyMock

from pywiim.cli.monitor_cli import PlayerMonitor


def _make_monitor(
    *,
    supports_trigger_out: bool = False,
    supports_subwoofer: bool = False,
    supports_led_indicator: bool = False,
    trigger_out_on: bool | None = None,
    led_indicator_on: bool | None = None,
    hardware_poll_interval: float = 10.0,
) -> PlayerMonitor:
    player = MagicMock()
    player.client.capabilities = {
        "supports_eq": False,
        "supports_peq": False,
        "supports_trigger_out": supports_trigger_out,
        "supports_subwoofer": supports_subwoofer,
        "supports_led_switch": supports_led_indicator,
    }
    player.supports_trigger_out = supports_trigger_out
    player.supports_subwoofer = supports_subwoofer
    player.supports_led_indicator = supports_led_indicator
    player.trigger_out_on = trigger_out_on
    player.led_indicator_on = led_indicator_on
    monitor = PlayerMonitor(player)
    monitor.hardware_poll_interval = hardware_poll_interval
    return monitor


def test_eq_display_uses_reconciled_state_without_rewriting_preset_names():
    monitor = _make_monitor()
    player = monitor.player
    player.client.capabilities.update(supports_eq=True, supports_peq=True)
    player.eq_preset = None
    player.peq_enabled = None
    assert monitor._format_eq_display() == ["Graphic EQ: Unknown", "PEQ: Unknown"]

    player.eq_preset = "Custom"
    player.peq_enabled = False
    assert monitor._format_eq_display() == ["Graphic EQ: Custom", "PEQ: Off"]

    player.eq_preset = "Off"
    player.peq_enabled = True
    player.peq_preset = "My PEQ"
    assert monitor._format_eq_display() == ["Graphic EQ: Off", "PEQ: My PEQ"]
    player.peq_preset = None
    assert monitor._format_eq_display() == ["Graphic EQ: Off", "PEQ: On (unnamed)"]


def test_eq_display_omits_unsupported_features():
    monitor = _make_monitor()
    assert monitor._format_eq_display() == []


def test_tui_and_line_show_the_current_input_eq_state(capsys):
    from pywiim.client import WiiMClient
    from pywiim.models import PlayerStatus
    from pywiim.player import Player

    client = WiiMClient("192.0.2.1", capabilities={"supports_eq": True, "supports_peq": True})
    player = Player(client)
    player._available = True
    player._status_model = PlayerStatus(source="wifi")
    player._state_mgr._remember_eq_band({"source_name": "wifi", "EQStat": "On", "Name": ""})
    player._peq_enabled = False
    monitor = PlayerMonitor(player)

    monitor._display_tui("solo", 5)
    output = capsys.readouterr().out
    assert "Graphic EQ: Custom" in output
    assert "PEQ: Off" in output

    player._eq_enabled = False
    player._peq_enabled = True
    player._peq_preset = "My PEQ"
    monitor._display_line_status("solo", 5)
    output = capsys.readouterr().out
    assert "Graphic EQ: Off" in output
    assert "PEQ: My PEQ" in output


class TestMonitorHardwarePolling:
    """Monitor-local fast poll helpers (separate from library CONFIGURATION_INTERVAL)."""

    def test_should_fetch_hardware_first_time(self):
        monitor = _make_monitor()
        assert monitor._should_fetch_hardware_status(0, True, time.time()) is True

    def test_should_fetch_hardware_not_supported(self):
        monitor = _make_monitor()
        assert monitor._should_fetch_hardware_status(0, False, time.time()) is False

    def test_should_fetch_hardware_after_interval(self):
        monitor = _make_monitor(hardware_poll_interval=10.0)
        now = time.time()
        assert monitor._should_fetch_hardware_status(now - 11.0, True, now) is True

    def test_should_fetch_hardware_too_soon(self):
        monitor = _make_monitor(hardware_poll_interval=10.0)
        now = time.time()
        assert monitor._should_fetch_hardware_status(now - 5.0, True, now) is False

    def test_format_trigger_out_unsupported(self):
        monitor = _make_monitor(supports_trigger_out=False)
        assert monitor._format_trigger_out_display() is None

    def test_format_trigger_out_on_with_age(self):
        monitor = _make_monitor(supports_trigger_out=True, trigger_out_on=True)
        monitor.last_trigger_out_check = time.time() - 3
        text = monitor._format_trigger_out_display()
        assert text is not None
        assert "12V Trigger: ON" in text
        assert "read" in text

    def test_format_trigger_out_unknown(self):
        monitor = _make_monitor(supports_trigger_out=True, trigger_out_on=None)
        assert monitor._format_trigger_out_display() == "12V Trigger: unknown"

    def test_format_led_indicator_off(self):
        monitor = _make_monitor(supports_led_indicator=True, led_indicator_on=False)
        assert monitor._format_led_indicator_display() == "Status LED: OFF"

    def test_format_led_indicator_with_age(self):
        monitor = _make_monitor(supports_led_indicator=True, led_indicator_on=True)
        monitor.last_led_indicator_check = time.time() - 2
        text = monitor._format_led_indicator_display()
        assert text is not None
        assert "Status LED: ON" in text
        assert "read 2s ago" in text

    def test_on_state_changed_includes_hardware_keys(self):
        monitor = _make_monitor(
            supports_trigger_out=True,
            supports_subwoofer=True,
            supports_led_indicator=True,
            trigger_out_on=True,
            led_indicator_on=False,
        )
        monitor.player.available = True
        type(monitor.player).play_state = PropertyMock(return_value="idle")
        type(monitor.player).volume_level = PropertyMock(return_value=0.0)
        type(monitor.player).is_muted = PropertyMock(return_value=False)
        type(monitor.player).source = PropertyMock(return_value="wifi")
        type(monitor.player).media_title = PropertyMock(return_value=None)
        type(monitor.player).media_artist = PropertyMock(return_value=None)
        type(monitor.player).media_position = PropertyMock(return_value=None)
        type(monitor.player).media_duration = PropertyMock(return_value=None)
        type(monitor.player).media_image_url = PropertyMock(return_value=None)
        type(monitor.player).shuffle_state = PropertyMock(return_value=None)
        type(monitor.player).repeat_mode = PropertyMock(return_value=None)
        type(monitor.player).subwoofer_enabled = PropertyMock(return_value=True)

        monitor.on_state_changed()
        assert monitor.last_state.get("trigger_out") is True
        assert monitor.last_state.get("led_indicator") is False
        assert monitor.last_state.get("subwoofer") is True
