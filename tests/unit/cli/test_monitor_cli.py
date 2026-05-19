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
