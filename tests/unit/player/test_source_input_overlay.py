"""Tests for the WiiM input-metadata overlay on source enumeration.

Covers the read-only ``getAudioInputCapbility`` / ``getAudioInputEnable`` /
``getModeRename`` overlay: authoritative gap-fill, enable-filtering, and user
custom labels applied to ``available_sources`` / ``source_catalog`` and resolved
back through ``set_source``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pywiim.models import (
    AudioInputCapability,
    AudioInputCapabilityItem,
    AudioInputEnable,
    AudioInputEnableItem,
    DeviceInfo,
    PlayerStatus,
)
from pywiim.player import Player


def _entry(catalog, source_id):
    for e in catalog:
        if e.get("id") == source_id:
            return e
    raise AssertionError(f"id {source_id!r} not in {[e['id'] for e in catalog]}")


class TestRenameOverlay:
    @pytest.mark.asyncio
    async def test_rename_shows_custom_label_but_keeps_stable_id(self, mock_client):
        """A renamed input surfaces its label while its catalog id stays canonical."""
        mock_client.capabilities["source_rename"] = {"optical": "TV"}
        player = Player(mock_client)
        player._device_info = DeviceInfo(uuid="t", input_list=["wifi", "bluetooth", "optical"])
        player._status_model = PlayerStatus(source="wifi", play_state="play")

        assert "TV" in player.available_sources
        assert "Optical In" not in player.available_sources

        optical = _entry(player.source_catalog, "optical")
        assert optical["name"] == "TV"
        assert optical["id"] == "optical"
        assert optical["selectable"] is True

    @pytest.mark.asyncio
    async def test_label_collision_prefers_hardware_id(self, mock_client):
        """When optical+SPDIF-In share a label, the catalog keeps the optical id.

        Mirrors a real WiiM device that returns getModeRename with both
        ``optical`` and ``SPDIF-In`` pointing at the same custom label.
        """
        mock_client.capabilities["source_rename"] = {"optical": "Optical Mike", "spdif_in": "Optical Mike"}
        player = Player(mock_client)
        player._device_info = DeviceInfo(uuid="t", input_list=["wifi", "bluetooth", "optical"])
        player._status_model = PlayerStatus(source="wifi", play_state="play")

        optical = _entry(player.source_catalog, "optical")
        assert optical["name"] == "Optical Mike"
        assert optical["selectable"] is True
        assert all(e["id"] != "spdif_in" for e in player.source_catalog)

    @pytest.mark.asyncio
    async def test_rename_applies_to_current_source_name(self, mock_client):
        """The current-source display name honors the custom label too."""
        mock_client.capabilities["source_rename"] = {"optical": "TV"}
        player = Player(mock_client)
        player._device_info = DeviceInfo(uuid="t", input_list=["wifi", "optical"])
        player._status_model = PlayerStatus(source="optical", play_state="play")

        assert player.source == "optical"  # stable id unchanged
        assert player.source_name == "TV"  # display overlaid

    @pytest.mark.asyncio
    async def test_no_rename_map_leaves_names_untouched(self, mock_client):
        """Without a rename map, enumeration keeps canonical display names."""
        mock_client.capabilities.pop("source_rename", None)
        player = Player(mock_client)
        player._device_info = DeviceInfo(uuid="t", input_list=["wifi", "optical"])
        player._status_model = PlayerStatus(source="wifi", play_state="play")

        assert "Optical In" in player.available_sources


class TestEnableFilter:
    @pytest.mark.asyncio
    async def test_disabled_input_is_hidden(self, mock_client):
        """An input disabled in the WiiM app is dropped from the source list."""
        mock_client.capabilities["wiim_input_enable"] = {
            "network": True,
            "bluetooth": True,
            "optical": False,
        }
        player = Player(mock_client)
        player._device_info = DeviceInfo(uuid="t", input_list=["wifi", "bluetooth", "optical"])
        player._status_model = PlayerStatus(source="wifi", play_state="play")

        assert "Optical In" not in player.available_sources
        assert "Bluetooth" in player.available_sources

    @pytest.mark.asyncio
    async def test_disabled_input_kept_when_currently_active(self, mock_client):
        """A disabled input still shows when it is the active source (state display)."""
        mock_client.capabilities["wiim_input_enable"] = {"optical": False}
        player = Player(mock_client)
        player._device_info = DeviceInfo(uuid="t", input_list=["wifi", "bluetooth", "optical"])
        player._status_model = PlayerStatus(source="optical", play_state="play")

        assert "Optical In" in player.available_sources


class TestCapabilityGapFill:
    @pytest.mark.asyncio
    async def test_capability_adds_missing_physical_input(self, mock_client):
        """Authoritative capability list fills an input enumeration missed."""
        mock_client.capabilities["wiim_input_capability"] = ["coaxial", "optical"]
        player = Player(mock_client)
        # No model -> device-capability DB filter is skipped; input_list lacks coaxial.
        player._device_info = DeviceInfo(uuid="t", input_list=["wifi", "bluetooth", "optical"])
        player._status_model = PlayerStatus(source="wifi", play_state="play")

        assert "Coaxial" in player.available_sources

    @pytest.mark.asyncio
    async def test_capability_does_not_duplicate_existing(self, mock_client):
        """Gap-fill dedupes by canonical id (no duplicate network/wifi)."""
        mock_client.capabilities["wiim_input_capability"] = ["wifi", "optical"]
        player = Player(mock_client)
        player._device_info = DeviceInfo(uuid="t", input_list=["wifi", "optical"])
        player._status_model = PlayerStatus(source="wifi", play_state="play")

        sources = player.available_sources
        assert sources.count("Network") == 1


class TestSetSourceRenameResolution:
    @pytest.fixture
    def audio_config(self, mock_client):
        from pywiim.player.audio import AudioConfiguration

        player = Player(mock_client)
        player._status_model = PlayerStatus()
        player._on_state_changed = None
        return AudioConfiguration(player)

    @pytest.mark.asyncio
    async def test_select_by_custom_label_resolves_to_canonical(self, audio_config, mock_client):
        """Selecting the renamed label switches the correct physical input."""
        mock_client.capabilities["source_rename"] = {"optical": "TV"}
        mock_client.set_source = AsyncMock()

        await audio_config.set_source("TV")

        mock_client.set_source.assert_called_once_with("optical")

    @pytest.mark.asyncio
    async def test_canonical_name_still_works_with_rename_active(self, audio_config, mock_client):
        """Existing callers passing the canonical name are unaffected by rename."""
        mock_client.capabilities["source_rename"] = {"optical": "TV"}
        mock_client.set_source = AsyncMock()

        await audio_config.set_source("Optical In")

        mock_client.set_source.assert_called_once_with("optical")


class TestInputMetadataProbe:
    @pytest.mark.asyncio
    async def test_probe_populates_capabilities_for_wiim(self):
        """The connect-time probe normalizes and stores all three payloads."""
        from pywiim.capabilities import _probe_wiim_input_metadata

        client = MagicMock()
        client.host = "1.2.3.4"
        client.get_audio_input_capability = AsyncMock(
            return_value=AudioInputCapability(
                audio_input=[AudioInputCapabilityItem(mode="line-in"), AudioInputCapabilityItem(mode="HDMI")]
            )
        )
        client.get_audio_input_enable = AsyncMock(
            return_value=AudioInputEnable(
                audio_input=[
                    AudioInputEnableItem(mode="optical", enable=0),
                    AudioInputEnableItem(mode="line-in", enable=1),
                ]
            )
        )
        client.get_mode_rename = AsyncMock(return_value={"optical": "TV"})

        caps: dict = {"is_wiim_device": True}
        await _probe_wiim_input_metadata(client, caps)

        assert caps["wiim_input_capability"] == ["line_in", "hdmi"]
        assert caps["wiim_input_enable"] == {"optical": False, "line_in": True}
        assert caps["source_rename"] == {"optical": "TV"}

    @pytest.mark.asyncio
    async def test_probe_skipped_for_non_wiim(self):
        """Non-WiiM devices are not probed and get no overlay keys."""
        from pywiim.capabilities import _probe_wiim_input_metadata

        client = MagicMock()
        client.get_audio_input_capability = AsyncMock()
        caps: dict = {"is_wiim_device": False}

        await _probe_wiim_input_metadata(client, caps)

        client.get_audio_input_capability.assert_not_called()
        assert "wiim_input_capability" not in caps
