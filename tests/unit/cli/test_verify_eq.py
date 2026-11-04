"""Tests for the verification CLI's non-mutating EQ checks."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pywiim.cli.verify_cli import FeatureTester


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "eq",
    [
        {"EQStat": "On", "Name": "", "EQBand": [{"value": 71}] * 10},
        {"EQStat": "Off", "Name": "", "PEQ": "My custom profile"},
    ],
)
async def test_eq_verification_never_changes_a_custom_curve(eq):
    player = MagicMock()
    client = player.client
    client.capabilities = {"supports_eq": True}
    client.get_eq = AsyncMock(return_value=eq)
    client.get_eq_presets = AsyncMock(return_value=["Flat", "Rock"])
    client.get_eq_status = AsyncMock(return_value=True)
    client.set_eq_preset = AsyncMock()
    client.set_eq_enabled = AsyncMock()
    client.set_eq_custom = AsyncMock()
    tester = FeatureTester(player)

    await tester.test_eq_controls()

    client.get_eq.assert_awaited_once()
    client.get_eq_presets.assert_awaited_once()
    client.get_eq_status.assert_awaited_once()
    client.set_eq_preset.assert_not_awaited()
    client.set_eq_enabled.assert_not_awaited()
    client.set_eq_custom.assert_not_awaited()
    assert any("write" in result for result in tester.results["skipped"])


@pytest.mark.asyncio
async def test_eq_verification_reports_unknown_and_keeps_other_reads():
    player = MagicMock()
    client = player.client
    client.capabilities = {"supports_eq": True}
    client.get_eq = AsyncMock(side_effect=RuntimeError("temporarily unavailable"))
    client.get_eq_presets = AsyncMock(return_value=["Flat"])
    client.get_eq_status = AsyncMock(return_value=None)
    client.set_eq_preset = AsyncMock()
    client.set_eq_enabled = AsyncMock()
    client.set_eq_custom = AsyncMock()
    tester = FeatureTester(player)

    await tester.test_eq_controls()

    client.get_eq_presets.assert_awaited_once()
    client.get_eq_status.assert_awaited_once()
    assert any("get_eq" in result for result in tester.results["warnings"])
    assert "eq: get_eq_status" not in tester.results["passed"]
    assert any("get_eq_status" in result for result in tester.results["warnings"])
    client.set_eq_preset.assert_not_awaited()
    client.set_eq_enabled.assert_not_awaited()
    client.set_eq_custom.assert_not_awaited()


@pytest.mark.asyncio
async def test_eq_verification_skips_unsupported_devices():
    player = MagicMock()
    player.client.capabilities = {"supports_eq": False}
    player.client.get_eq = AsyncMock()
    tester = FeatureTester(player)

    await tester.test_eq_controls()

    player.client.get_eq.assert_not_awaited()
    assert "eq: Not supported" in tester.results["skipped"]
