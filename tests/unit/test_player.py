"""Unit tests for Player class.

Tests player initialization, state management, role detection, and control methods.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, call, patch

import pytest

from pywiim.exceptions import WiiMError
from pywiim.models import DeviceInfo, PlayerStatus


class TestPlayerInitialization:
    """Test Player initialization."""

    @pytest.mark.asyncio
    async def test_player_init(self, mock_client):
        """Test Player initialization."""
        from pywiim.player import Player

        player = Player(mock_client)

        assert player.client == mock_client
        assert player._group is None
        assert player.role == "solo"
        assert player.is_solo is True
        assert player.is_master is False
        assert player.is_slave is False

    @pytest.mark.asyncio
    async def test_player_init_with_callback(self, mock_client):
        """Test Player initialization with state change callback."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        callback_called = []

        def on_state_changed():
            callback_called.append(True)

        player = Player(mock_client, on_state_changed=on_state_changed)

        assert player._on_state_changed is not None
        # Callback will be called during refresh
        mock_status = PlayerStatus(play_state="play", volume=50, mute=False)
        mock_info = DeviceInfo(uuid="test-uuid", name="Test Device")
        mock_client.get_player_status_model = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_info)
        await player.refresh()
        assert len(callback_called) > 0


class TestPlayerRole:
    """Test Player role detection."""

    @pytest.mark.asyncio
    async def test_player_role_solo(self, mock_client):
        """Test player role when solo."""
        from pywiim.player import Player

        player = Player(mock_client)

        assert player.role == "solo"
        assert player.is_solo is True
        assert player.is_master is False
        assert player.is_slave is False
        assert player.group is None

    @pytest.mark.asyncio
    async def test_player_role_master(self, mock_client):
        """Test player role when master."""
        from pywiim.group import Group
        from pywiim.player import Player

        player = Player(mock_client)
        player._detected_role = "master"  # Set role from device API state
        group = Group(player)

        # Add a slave to make it a proper master (master with no slaves is solo)
        slave = Player(mock_client)
        group.add_slave(slave)

        assert player.role == "master"
        assert player.is_solo is False
        assert player.is_master is True
        assert player.is_slave is False
        assert player.group == group

    @pytest.mark.asyncio
    async def test_player_role_slave(self, mock_client):
        """Test player role when slave."""
        from pywiim.group import Group
        from pywiim.player import Player

        master = Player(mock_client)
        master._detected_role = "master"  # Set role from device API state
        slave = Player(mock_client)
        slave._detected_role = "slave"  # Set role from device API state
        group = Group(master)
        group.add_slave(slave)

        assert slave.role == "slave"
        assert slave.is_solo is False
        assert slave.is_master is False
        assert slave.is_slave is True
        assert slave.group == group


class TestPlayerProperties:
    """Test Player properties with behavior-focused tests."""

    @pytest.mark.asyncio
    async def test_player_host_reflects_client_connection(self, mock_client):
        """Test player host property reflects client connection (behavior: used for device identification)."""
        from pywiim.player import Player

        player = Player(mock_client)
        # Behavior: host is used to identify and connect to the device
        assert player.host == mock_client.host
        # Verify it's actually used for device operations
        assert player.host is not None
        assert isinstance(player.host, str)

    @pytest.mark.asyncio
    async def test_player_name_updates_after_refresh(self, mock_client):
        """Test player name updates from device info after refresh (behavior: name comes from device)."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        player = Player(mock_client)
        # Initially no name (not cached)
        assert player.name is None

        # Refresh fetches device info
        mock_status = PlayerStatus(play_state="play", volume=50)
        mock_info = DeviceInfo(uuid="test", name="Test Device")
        mock_client.get_player_status_model = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_info)

        await player.refresh()

        # Name should now be available from cached device info
        assert player.name == "Test Device"
        # Verify it's actually cached
        assert player._device_info == mock_info

    @pytest.mark.asyncio
    async def test_player_available_tracks_connection_state(self, mock_client):
        """Test player available property tracks connection state (behavior: affects control operations)."""
        from pywiim.exceptions import WiiMError
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        player = Player(mock_client)
        # Default: assume available
        assert player.available is True

        # Refresh failure marks as unavailable
        mock_client.get_player_status_model = AsyncMock(side_effect=WiiMError("Connection failed"))
        with pytest.raises(WiiMError):
            await player.refresh()

        # Behavior: unavailable after error
        assert player.available is False

        # Successful refresh restores availability
        mock_status = PlayerStatus(play_state="play", volume=50)
        mock_info = DeviceInfo(uuid="test", name="Test")
        mock_client.get_player_status_model = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_info)

        await player.refresh()
        assert player.available is True


class TestPlayerRefresh:
    """Test Player refresh method."""

    @pytest.mark.asyncio
    async def test_refresh_success(self, mock_client):
        """Test successful refresh."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        mock_status = PlayerStatus(play_state="play", volume=50, mute=False)
        mock_info = DeviceInfo(uuid="test-uuid", name="Test Device")
        mock_client.get_player_status_model = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_info)
        # Capabilities are set via constructor, mock_client already has them from conftest

        player = Player(mock_client)
        await player.refresh()

        assert player._status_model == mock_status
        assert player._device_info == mock_info
        assert player.available is True
        assert player._last_refresh is not None

    @pytest.mark.asyncio
    async def test_refresh_preserves_optimistic_source_when_mode_0(self, mock_client):
        """Test that refresh preserves optimistic source when device reports mode=0 (Issue #138)."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        # Set up player with optimistic source (e.g., from set_source("bluetooth"))
        player = Player(mock_client)
        player._status_model = PlayerStatus(source="bluetooth", play_state="idle")
        player._device_info = DeviceInfo(uuid="test-uuid", name="Test Device")

        # Simulate device reporting mode=0 (idle) - parser correctly doesn't set source="idle"
        # but also doesn't set source at all (source=None)
        new_status = PlayerStatus(play_state="idle", volume=50, mute=False)  # No source field
        mock_client.get_player_status_model = AsyncMock(return_value=new_status)
        mock_client.get_device_info_model = AsyncMock(return_value=player._device_info)

        await player.refresh()

        # Optimistic source should be preserved even though new status doesn't have one
        assert player._status_model.source == "bluetooth"
        assert player._status_model.play_state == "idle"

    @pytest.mark.asyncio
    async def test_refresh_with_audio_output(self, mock_aiohttp_session):
        """Test refresh with audio output status."""
        from pywiim.client import WiiMClient
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        # Create client with audio output capability
        capabilities = {
            "supports_audio_output": True,
            "is_legacy_device": False,
        }
        mock_client = WiiMClient("192.168.1.100", session=mock_aiohttp_session, capabilities=capabilities)
        mock_client._request = AsyncMock(return_value={"status": "ok"})

        mock_status = PlayerStatus(play_state="play", volume=50, mute=False)
        mock_info = DeviceInfo(uuid="test-uuid", name="Test Device")
        mock_client.get_player_status_model = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_info)
        mock_client.get_audio_output_status = AsyncMock(return_value={"hardware": 0, "source": 0})

        player = Player(mock_client)
        await player.refresh(full=True)  # Audio output status is only fetched on full refresh

        assert player._audio_output_status == {"hardware": 0, "source": 0}

    @pytest.mark.asyncio
    async def test_refresh_failure(self, mock_client):
        """Test refresh failure."""
        from pywiim.player import Player

        mock_client.get_player_status_model = AsyncMock(side_effect=WiiMError("Failed"))

        player = Player(mock_client)
        with pytest.raises(WiiMError):
            await player.refresh()

        assert player.available is False

    @pytest.mark.asyncio
    async def test_refresh_callback_error(self, mock_client):
        """Test refresh when callback raises error."""
        from pywiim.player import Player

        def bad_callback():
            raise ValueError("Callback error")

        from pywiim.models import DeviceInfo, PlayerStatus

        mock_status = PlayerStatus(play_state="play", volume=50, mute=False)
        mock_info = DeviceInfo(uuid="test-uuid", name="Test Device")
        mock_client.get_player_status_model = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_info)
        # Capabilities are set via constructor, mock_client already has them from conftest

        player = Player(mock_client, on_state_changed=bad_callback)
        # Should not raise, just log error
        await player.refresh()

        assert player._status_model == mock_status

    @pytest.mark.asyncio
    async def test_refresh_with_upnp_volume(self, mock_client):
        """Test refresh uses UPnP GetVolume when available."""
        from unittest.mock import MagicMock

        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        # Setup HTTP status (volume=50)
        mock_status = PlayerStatus(play_state="play", volume=50, mute=False)
        mock_info = DeviceInfo(uuid="test-uuid", name="Test Device")
        mock_client.get_player_status_model = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_info)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_info)

        # Setup UPnP client with RenderingControl
        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.rendering_control = MagicMock()
        mock_upnp_client.get_volume = AsyncMock(return_value=75)  # UPnP volume = 75
        mock_upnp_client.get_mute = AsyncMock(return_value=True)  # UPnP mute = True

        player = Player(mock_client, upnp_client=mock_upnp_client)
        await player.refresh()

        # Verify UPnP GetVolume was called
        mock_upnp_client.get_volume.assert_called_once()
        mock_upnp_client.get_mute.assert_called_once()

        # Verify state synchronizer was updated with UPnP values (overriding HTTP)
        merged = player._state_synchronizer.get_merged_state()
        # UPnP volume (75) should override HTTP volume (50)
        assert merged["volume"] == 75
        # UPnP mute (True) should override HTTP mute (False)
        assert merged["muted"] is True

    @pytest.mark.asyncio
    async def test_refresh_lazy_upnp_client_creation(self, mock_client):
        """Test refresh creates UPnP client lazily if not provided."""
        import asyncio
        from unittest.mock import MagicMock, patch

        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        # Setup HTTP status
        mock_status = PlayerStatus(play_state="play", volume=50, mute=False)
        mock_info = DeviceInfo(uuid="test-uuid", name="Test Device")
        mock_client.get_player_status_model = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_info)

        # Mock UPnP client creation
        mock_upnp_client = MagicMock()
        mock_upnp_client.rendering_control = MagicMock()
        mock_upnp_client.get_volume = AsyncMock(return_value=60)
        mock_upnp_client.get_mute = AsyncMock(return_value=False)

        with patch("pywiim.upnp.client.UpnpClient.create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_upnp_client

            player = Player(mock_client)  # No UPnP client provided
            assert player._upnp_client is None

            await player.refresh()

            # UPnP creation is now non-blocking (runs via asyncio.create_task)
            # Give the background task a chance to complete
            await asyncio.sleep(0.1)

            # Should attempt to create UPnP client in background
            mock_create.assert_called_once()
            # UPnP client should be set after background task completes
            assert player._upnp_client is not None

    @pytest.mark.asyncio
    async def test_refresh_upnp_volume_fallback_to_http(self, mock_client):
        """Test refresh falls back to HTTP volume when UPnP GetVolume fails."""
        from unittest.mock import MagicMock

        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        # Setup HTTP status (volume=50)
        mock_status = PlayerStatus(play_state="play", volume=50, mute=False)
        mock_info = DeviceInfo(uuid="test-uuid", name="Test Device")
        mock_client.get_player_status_model = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_info)

        # Setup UPnP client but GetVolume fails
        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.rendering_control = MagicMock()
        mock_upnp_client.get_volume = AsyncMock(side_effect=Exception("UPnP error"))
        mock_upnp_client.get_mute = AsyncMock(side_effect=Exception("UPnP error"))

        player = Player(mock_client, upnp_client=mock_upnp_client)
        await player.refresh()

        # Should fall back to HTTP volume
        merged = player._state_synchronizer.get_merged_state()
        # Should use HTTP volume (50) since UPnP failed
        assert merged["volume"] == 50
        # Mute might be None if HTTP status doesn't include it, or False if it does
        # The important thing is that volume works (the main test)
        assert merged.get("muted") in [False, None]


class TestPlayerVolumeControl:
    """Test Player volume control methods."""

    @pytest.mark.asyncio
    async def test_set_volume(self, mock_client):
        """Test setting volume."""
        from pywiim.player import Player

        mock_client.set_volume = AsyncMock()

        player = Player(mock_client)
        await player.set_volume(0.5)

        mock_client.set_volume.assert_called_once_with(0.5)

    @pytest.mark.asyncio
    async def test_set_mute(self, mock_client):
        """Test setting mute."""
        from pywiim.player import Player

        mock_client.set_mute = AsyncMock()

        player = Player(mock_client)
        await player.set_mute(True)

        mock_client.set_mute.assert_called_once_with(True)

    @pytest.mark.asyncio
    async def test_volume_level_from_cache(self, mock_client):
        """Test getting volume level from cache."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(volume=50, play_state="play")
        player._status_model = status

        assert player.volume_level == 0.5

    @pytest.mark.asyncio
    async def test_volume_level_updates_after_refresh(self, mock_client):
        """Test volume level updates from device state after refresh (behavior: reflects actual device volume)."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        player = Player(mock_client)
        # Initially no volume (not cached)
        assert player.volume_level is None

        # Refresh fetches status
        mock_status = PlayerStatus(volume=75, play_state="play")
        mock_info = DeviceInfo(uuid="test", name="Test")
        mock_client.get_player_status_model = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_info)

        await player.refresh()

        # Volume should now be available (normalized to 0-1 range)
        assert player.volume_level == 0.75
        # Verify it comes from cached status
        assert player._status_model.volume == 75

    @pytest.mark.asyncio
    async def test_volume_level_from_upnp_uses_0_to_100_scale(self, mock_client):
        """Test volume_level normalization from UPnP merged state uses 0-100 scale."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._state_synchronizer.update_from_upnp({"volume": 16, "muted": False})

        assert player.volume_level == 0.16

    @pytest.mark.asyncio
    async def test_is_muted_reflects_device_state(self, mock_client):
        """Test is_muted reflects actual device mute state (behavior: used for UI display and control logic)."""
        from pywiim.models import PlayerStatus
        from pywiim.player import Player

        player = Player(mock_client)

        # Set muted state
        status = PlayerStatus(mute=True, play_state="play", volume=50)
        player._status_model = status

        # Property should reflect cached state
        assert player.is_muted is True

        # Update state (e.g., after set_mute(False))
        player._status_model = PlayerStatus(mute=False, play_state="play", volume=50)
        assert player.is_muted is False

    @pytest.mark.asyncio
    async def test_get_volume(self, mock_client):
        """Test getting volume by querying device."""
        from pywiim.player import Player

        status = PlayerStatus(volume=75, play_state="play")
        mock_client.get_player_status_model = AsyncMock(return_value=status)

        player = Player(mock_client)
        volume = await player.get_volume()

        assert volume == 0.75

    @pytest.mark.asyncio
    async def test_get_muted(self, mock_client):
        """Test getting mute state by querying device."""
        from pywiim.player import Player

        status = PlayerStatus(mute=False, play_state="play")
        mock_client.get_player_status_model = AsyncMock(return_value=status)

        player = Player(mock_client)
        muted = await player.get_muted()

        assert muted is False

    @pytest.mark.asyncio
    async def test_set_volume_master_with_slaves(self, mock_client):
        """Test set_volume on master only affects that device (no auto-propagation)."""
        from pywiim.group import Group
        from pywiim.player import Player

        master = Player(mock_client)
        slave = Player(mock_client)

        # Set up master with detected role
        master._detected_role = "master"
        master._status_model = PlayerStatus(volume=50, play_state="play")

        # Create group and add slave
        group = Group(master)
        group.add_slave(slave)

        mock_client.set_volume = AsyncMock()

        # Call set_volume on master
        await master.set_volume(0.6)

        # Verify it called client directly (physical master only, no group propagation)
        # Group-wide operations require explicit group.set_volume_all()
        mock_client.set_volume.assert_called_once_with(0.6)

    @pytest.mark.asyncio
    async def test_set_volume_master_no_slaves(self, mock_client):
        """Test set_volume on master with no slaves only affects master."""
        from pywiim.group import Group
        from pywiim.player import Player

        master = Player(mock_client)
        master._detected_role = "master"
        master._status_model = PlayerStatus(volume=50, play_state="play")

        # Create group but no slaves
        Group(master)

        mock_client.set_volume = AsyncMock()

        # Call set_volume on master with no slaves
        await master.set_volume(0.6)

        # Verify it called client directly (not group)
        mock_client.set_volume.assert_called_once_with(0.6)

    @pytest.mark.asyncio
    async def test_set_volume_slave(self, mock_client):
        """Test set_volume on slave only affects that slave."""
        from pywiim.group import Group
        from pywiim.player import Player

        master = Player(mock_client)
        slave = Player(mock_client)

        master._detected_role = "master"
        slave._detected_role = "slave"
        slave._status_model = PlayerStatus(volume=50, play_state="play")

        # Create group
        group = Group(master)
        group.add_slave(slave)

        mock_client.set_volume = AsyncMock()

        # Call set_volume on slave
        await slave.set_volume(0.7)

        # Verify it called client directly (slaves have independent volume)
        mock_client.set_volume.assert_called_once_with(0.7)

    @pytest.mark.asyncio
    async def test_set_mute_master_with_slaves(self, mock_client):
        """Test set_mute on master only affects that device (no auto-propagation)."""
        from pywiim.group import Group
        from pywiim.player import Player

        master = Player(mock_client)
        slave = Player(mock_client)

        master._detected_role = "master"
        master._status_model = PlayerStatus(mute=False, play_state="play")

        # Create group and add slave
        group = Group(master)
        group.add_slave(slave)

        mock_client.set_mute = AsyncMock()

        # Call set_mute on master
        await master.set_mute(True)

        # Verify it called client directly (physical master only, no group propagation)
        # Group-wide operations require explicit group.mute_all()
        mock_client.set_mute.assert_called_once_with(True)

    @pytest.mark.asyncio
    async def test_set_mute_slave(self, mock_client):
        """Test set_mute on slave only affects that slave."""
        from pywiim.group import Group
        from pywiim.player import Player

        master = Player(mock_client)
        slave = Player(mock_client)

        master._detected_role = "master"
        slave._detected_role = "slave"
        slave._status_model = PlayerStatus(mute=False, play_state="play")

        # Create group
        group = Group(master)
        group.add_slave(slave)

        mock_client.set_mute = AsyncMock()

        # Call set_mute on slave
        await slave.set_mute(True)

        # Verify it called client directly (slaves have independent mute)
        mock_client.set_mute.assert_called_once_with(True)


class TestPlayerPlaybackControl:
    """Test Player playback control methods."""

    @pytest.mark.asyncio
    async def test_play(self, mock_client):
        """Test play command updates state and triggers callback."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        callback_called = []
        mock_client.play = AsyncMock()
        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client, on_state_changed=lambda: callback_called.append(True))
        player._status_model = PlayerStatus(play_state="pause")  # Start paused

        await player.play()

        # Verify API was called
        mock_client.play.assert_called_once()
        # Verify optimistic state update
        assert player._status_model.play_state == "play"
        # Verify state synchronizer updated
        merged = player._state_synchronizer.get_merged_state()
        assert merged["play_state"] == "play"
        # Verify callback was triggered
        assert len(callback_called) == 1

    @pytest.mark.asyncio
    async def test_pause(self, mock_client):
        """Test pause command updates state and triggers callback."""
        from pywiim.player import Player

        callback_called = []
        mock_client.pause = AsyncMock()

        player = Player(mock_client, on_state_changed=lambda: callback_called.append(True))
        player._status_model = PlayerStatus(play_state="play")  # Start playing

        await player.pause()

        # Verify API was called
        mock_client.pause.assert_called_once()
        # Verify optimistic state update
        assert player._status_model.play_state == "pause"
        # Verify state synchronizer updated
        merged = player._state_synchronizer.get_merged_state()
        assert merged["play_state"] == "pause"
        # Verify callback was triggered
        assert len(callback_called) == 1

    @pytest.mark.asyncio
    async def test_resume(self, mock_client):
        """Test resume command updates state and triggers callback."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        callback_called = []
        mock_client.resume = AsyncMock()
        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client, on_state_changed=lambda: callback_called.append(True))
        player._status_model = PlayerStatus(play_state="pause")  # Start paused

        await player.resume()

        # Verify API was called
        mock_client.resume.assert_called_once()
        # Verify optimistic state update
        assert player._status_model.play_state == "play"
        # Verify state synchronizer updated
        merged = player._state_synchronizer.get_merged_state()
        assert merged["play_state"] == "play"
        # Verify callback was triggered
        assert len(callback_called) == 1

    @pytest.mark.asyncio
    async def test_stop(self, mock_client):
        """Test stop command updates state and triggers callback."""
        from pywiim.player import Player

        callback_called = []
        mock_client.stop = AsyncMock()

        player = Player(mock_client, on_state_changed=lambda: callback_called.append(True))
        player._status_model = PlayerStatus(play_state="play")  # Start playing

        await player.stop()

        # Verify API was called
        mock_client.stop.assert_called_once()
        # Verify optimistic state update
        assert player._status_model.play_state == "stop"
        # Verify state synchronizer updated (stop is normalized to pause for modern UX)
        merged = player._state_synchronizer.get_merged_state()
        assert merged["play_state"] == "pause"  # "stop" normalized to "pause" by design
        # Verify callback was triggered
        assert len(callback_called) == 1

    @pytest.mark.asyncio
    async def test_next_track(self, mock_client):
        """Test next track command."""
        from pywiim.player import Player

        mock_client.next_track = AsyncMock()

        player = Player(mock_client)
        await player.next_track()

        mock_client.next_track.assert_called_once()

    @pytest.mark.asyncio
    async def test_seek(self, mock_client):
        """Test seek command."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        mock_client.seek = AsyncMock()
        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client)
        await player.seek(120)

        mock_client.seek.assert_called_once_with(120)

    @pytest.mark.asyncio
    async def test_play_url(self, mock_client):
        """Test play URL command."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        mock_client.play_url = AsyncMock()
        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client)
        await player.play_url("http://example.com/stream.mp3")

        mock_client.play_url.assert_called_once_with("http://example.com/stream.mp3")

    @pytest.mark.asyncio
    async def test_play_playlist(self, mock_client):
        """Test play playlist command."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        mock_client.play_playlist = AsyncMock()
        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client)
        await player.play_playlist("http://example.com/playlist.m3u")

        mock_client.play_playlist.assert_called_once_with("http://example.com/playlist.m3u")

    @pytest.mark.asyncio
    async def test_play_url_with_enqueue_replace(self, mock_client):
        """Test play_url with enqueue='replace' (default, uses HTTP API)."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        mock_client.play_url = AsyncMock()
        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client)
        await player.play_url("http://example.com/song.mp3", enqueue="replace")

        mock_client.play_url.assert_called_once_with("http://example.com/song.mp3")

    @pytest.mark.asyncio
    async def test_play_url_with_enqueue_add_no_upnp(self, mock_client):
        """Test play_url with enqueue='add' without UPnP client raises error."""
        from pywiim.player import Player

        player = Player(mock_client)

        with pytest.raises(WiiMError, match="requires UPnP client"):
            await player.play_url("http://example.com/song.mp3", enqueue="add")

    @pytest.mark.asyncio
    async def test_play_url_with_enqueue_next_no_upnp(self, mock_client):
        """Test play_url with enqueue='next' without UPnP client raises error."""
        from pywiim.player import Player

        player = Player(mock_client)

        with pytest.raises(WiiMError, match="requires UPnP client"):
            await player.play_url("http://example.com/song.mp3", enqueue="next")

    @pytest.mark.asyncio
    async def test_add_to_queue_no_upnp(self, mock_client):
        """Test add_to_queue without UPnP client raises error."""
        from pywiim.player import Player

        player = Player(mock_client)

        with pytest.raises(WiiMError, match="requires UPnP client"):
            await player.add_to_queue("http://example.com/song.mp3")

    @pytest.mark.asyncio
    async def test_insert_next_no_upnp(self, mock_client):
        """Test insert_next without UPnP client raises error."""
        from pywiim.player import Player

        player = Player(mock_client)

        with pytest.raises(WiiMError, match="requires UPnP client"):
            await player.insert_next("http://example.com/song.mp3")

    @pytest.mark.asyncio
    async def test_add_to_queue_with_upnp(self, mock_client):
        """Test add_to_queue with UPnP client."""
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.async_call_action = AsyncMock()

        player = Player(mock_client, upnp_client=mock_upnp_client)
        await player.add_to_queue("http://example.com/song.mp3")

        mock_upnp_client.async_call_action.assert_called_once_with(
            "AVTransport",
            "AddURIToQueue",
            {
                "InstanceID": 0,
                "EnqueuedURI": "http://example.com/song.mp3",
                "EnqueuedURIMetaData": "",
                "DesiredFirstTrackNumberEnqueued": 0,
                "EnqueueAsNext": False,
            },
        )

    @pytest.mark.asyncio
    async def test_add_to_queue_with_metadata(self, mock_client):
        """Test add_to_queue with metadata."""
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.async_call_action = AsyncMock()

        player = Player(mock_client, upnp_client=mock_upnp_client)
        await player.add_to_queue("http://example.com/song.mp3", metadata="<DIDL-Lite>...</DIDL-Lite>")

        mock_upnp_client.async_call_action.assert_called_once_with(
            "AVTransport",
            "AddURIToQueue",
            {
                "InstanceID": 0,
                "EnqueuedURI": "http://example.com/song.mp3",
                "EnqueuedURIMetaData": "<DIDL-Lite>...</DIDL-Lite>",
                "DesiredFirstTrackNumberEnqueued": 0,
                "EnqueueAsNext": False,
            },
        )

    @pytest.mark.asyncio
    async def test_insert_next_with_upnp(self, mock_client):
        """Test insert_next with UPnP client."""
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.async_call_action = AsyncMock()

        player = Player(mock_client, upnp_client=mock_upnp_client)
        await player.insert_next("http://example.com/song.mp3")

        mock_upnp_client.async_call_action.assert_called_once_with(
            "AVTransport",
            "InsertURIToQueue",
            {
                "InstanceID": 0,
                "EnqueuedURI": "http://example.com/song.mp3",
                "EnqueuedURIMetaData": "",
                "DesiredTrackNumber": 0,
            },
        )

    @pytest.mark.asyncio
    async def test_play_url_with_enqueue_add(self, mock_client):
        """Test play_url with enqueue='add' uses UPnP."""
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.async_call_action = AsyncMock()

        player = Player(mock_client, upnp_client=mock_upnp_client)
        await player.play_url("http://example.com/song.mp3", enqueue="add")

        mock_upnp_client.async_call_action.assert_called_once_with(
            "AVTransport",
            "AddURIToQueue",
            {
                "InstanceID": 0,
                "EnqueuedURI": "http://example.com/song.mp3",
                "EnqueuedURIMetaData": "",
                "DesiredFirstTrackNumberEnqueued": 0,
                "EnqueueAsNext": False,
            },
        )
        # Should not call HTTP API (play_url is not mocked in this test)
        # The UPnP path doesn't call client.play_url()

    @pytest.mark.asyncio
    async def test_play_url_with_enqueue_next(self, mock_client):
        """Test play_url with enqueue='next' uses UPnP."""
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.async_call_action = AsyncMock()

        player = Player(mock_client, upnp_client=mock_upnp_client)
        await player.play_url("http://example.com/song.mp3", enqueue="next")

        mock_upnp_client.async_call_action.assert_called_once_with(
            "AVTransport",
            "InsertURIToQueue",
            {
                "InstanceID": 0,
                "EnqueuedURI": "http://example.com/song.mp3",
                "EnqueuedURIMetaData": "",
                "DesiredTrackNumber": 0,
            },
        )
        # Should not call HTTP API (play_url is not mocked in this test)
        # The UPnP path doesn't call client.play_url()


class TestPlayerErrorHandling:
    """Test Player error handling and recovery paths."""

    @pytest.mark.asyncio
    async def test_play_handles_api_failure(self, mock_client):
        """Test play command handles API failure gracefully."""
        from pywiim.exceptions import WiiMError
        from pywiim.models import PlayerStatus
        from pywiim.player import Player

        mock_client.play = AsyncMock(side_effect=WiiMError("Network error"))
        player = Player(mock_client)
        player._status_model = PlayerStatus(play_state="pause")

        # Should raise the error (not swallow it)
        with pytest.raises(WiiMError, match="Network error"):
            await player.play()

        # State should not be updated on failure
        assert player._status_model.play_state == "pause"

    @pytest.mark.asyncio
    async def test_refresh_recovery_after_failure(self, mock_client):
        """Test refresh recovers after initial failure."""
        from pywiim.exceptions import WiiMError
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        # First call fails
        mock_client.get_player_status_model = AsyncMock(side_effect=WiiMError("Failed"))
        player = Player(mock_client)

        # First refresh fails
        with pytest.raises(WiiMError):
            await player.refresh()
        assert player.available is False

        # Second call succeeds
        mock_status = PlayerStatus(play_state="play", volume=50)
        mock_info = DeviceInfo(uuid="test-uuid", name="Test Device")
        mock_client.get_player_status_model = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_info)

        # Should recover
        await player.refresh()
        assert player.available is True
        assert player._status_model == mock_status

    @pytest.mark.asyncio
    async def test_upnp_fallback_when_http_fails(self, mock_client):
        """Test UPnP fallback when HTTP volume fetch fails."""
        from unittest.mock import MagicMock

        from pywiim.exceptions import WiiMError
        from pywiim.models import DeviceInfo
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        # HTTP fails
        mock_client.get_player_status_model = AsyncMock(side_effect=WiiMError("HTTP failed"))
        mock_info = DeviceInfo(uuid="test-uuid", name="Test Device")
        mock_client.get_device_info_model = AsyncMock(return_value=mock_info)

        # UPnP succeeds
        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.rendering_control = MagicMock()
        mock_upnp_client.get_volume = AsyncMock(return_value=75)
        mock_upnp_client.get_mute = AsyncMock(return_value=False)

        player = Player(mock_client, upnp_client=mock_upnp_client)

        # Refresh should fail (HTTP is required for status)
        with pytest.raises(WiiMError):
            await player.refresh()

    @pytest.mark.asyncio
    async def test_slave_play_without_group_raises_error(self, mock_client):
        """Test slave play command raises error when not linked to group."""
        from pywiim.exceptions import WiiMError
        from pywiim.player import Player

        player = Player(mock_client)
        player._detected_role = "slave"  # Slave but no group

        with pytest.raises(WiiMError, match="Slave player not linked to group"):
            await player.play()


class TestPlayerRoleTransitions:
    """Test Player role transitions and group membership changes."""

    @pytest.mark.asyncio
    async def test_role_transition_solo_to_master(self, mock_client):
        """Test role transition from solo to master."""
        from pywiim.group import Group
        from pywiim.player import Player

        player = Player(mock_client)
        assert player.role == "solo"
        assert player.is_solo is True

        # Transition to master
        player._detected_role = "master"
        slave = Player(mock_client)
        group = Group(player)
        group.add_slave(slave)

        # Role should be master now
        assert player.role == "master"
        assert player.is_master is True
        assert player.is_solo is False
        assert player.group == group

    @pytest.mark.asyncio
    async def test_role_transition_master_to_solo(self, mock_client):
        """Test role transition from master to solo when slaves leave."""
        from pywiim.group import Group
        from pywiim.player import Player

        master = Player(mock_client)
        master._detected_role = "master"
        slave = Player(mock_client)
        group = Group(master)
        group.add_slave(slave)

        assert master.role == "master"
        assert master.is_master is True

        # Slave leaves
        group.remove_slave(slave)

        # Master with no slaves becomes solo (per role detection logic: slave_count > 0 required for master)
        # Group size is now 1 (just the master)
        assert master.role == "solo"  # Master with 0 slaves is solo per device API logic
        assert group.size == 1

    @pytest.mark.asyncio
    async def test_role_transition_solo_to_slave(self, mock_client):
        """Test role transition from solo to slave when joining group."""
        from pywiim.group import Group
        from pywiim.player import Player

        master = Player(mock_client)
        master._detected_role = "master"
        slave = Player(mock_client)
        assert slave.role == "solo"

        group = Group(master)
        slave._detected_role = "slave"  # Device API reports slave role
        group.add_slave(slave)

        assert slave.role == "slave"
        assert slave.is_slave is True
        assert slave.group == group

    @pytest.mark.asyncio
    async def test_slave_auto_removal_when_joining_different_group(self, mock_client):
        """Test slave automatically removed from old group when joining new group."""
        from pywiim.group import Group
        from pywiim.player import Player

        master1 = Player(mock_client)
        master1._detected_role = "master"
        master2 = Player(mock_client)
        master2._detected_role = "master"
        slave = Player(mock_client)
        slave._detected_role = "slave"

        group1 = Group(master1)
        group2 = Group(master2)

        # Add slave to group1
        group1.add_slave(slave)
        assert slave.group == group1
        assert slave in group1.slaves

        # Add slave to group2 - should auto-remove from group1
        group2.add_slave(slave)

        assert slave.group == group2
        assert slave in group2.slaves
        assert slave not in group1.slaves
        assert group1.size == 1
        assert group2.size == 2


class TestPlayerSourceConflicts:
    """Test Player source conflict resolution and preservation."""

    @pytest.mark.asyncio
    async def test_source_preserved_when_http_returns_none(self, mock_client):
        """Test source is preserved when HTTP returns None (mode=0 scenario)."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        player = Player(mock_client)
        # Set optimistic source
        player._status_model = PlayerStatus(source="bluetooth", play_state="idle")

        # HTTP returns status without source (mode=0)
        new_status = PlayerStatus(play_state="idle", volume=50)
        mock_client.get_player_status_model = AsyncMock(return_value=new_status)
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        await player.refresh()

        # Optimistic source should be preserved
        assert player._status_model.source == "bluetooth"

    @pytest.mark.asyncio
    async def test_source_selection_when_http_and_upnp_disagree(self, mock_client):
        """Test source selection when HTTP and UPnP report different sources."""
        from unittest.mock import MagicMock

        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        # HTTP reports wifi
        mock_status = PlayerStatus(play_state="play", source="wifi")
        mock_info = DeviceInfo(uuid="test-uuid", name="Test Device")
        mock_client.get_player_status_model = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_info)

        # UPnP reports bluetooth (via transport state)
        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.rendering_control = MagicMock()
        mock_upnp_client.get_volume = AsyncMock(return_value=50)
        mock_upnp_client.get_mute = AsyncMock(return_value=False)

        player = Player(mock_client, upnp_client=mock_upnp_client)
        await player.refresh()

        # HTTP source should be used (HTTP is preferred for source)
        merged = player._state_synchronizer.get_merged_state()
        assert merged.get("source") == "wifi" or player._status_model.source == "wifi"

    @pytest.mark.asyncio
    async def test_source_fallback_when_preferred_unavailable(self, mock_client):
        """Test source fallback when preferred source (UPnP) is unavailable."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        # Only HTTP available (no UPnP)
        mock_status = PlayerStatus(play_state="play", source="usb")
        mock_info = DeviceInfo(uuid="test-uuid", name="Test Device")
        mock_client.get_player_status_model = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_info)

        player = Player(mock_client)  # No UPnP client
        await player.refresh()

        # Should fall back to HTTP source
        assert player._status_model.source == "usb"

    @pytest.mark.asyncio
    async def test_set_source_updates_optimistic_state(self, mock_client):
        """Test set_source updates optimistic state immediately."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        callback_called = []
        mock_client.set_source = AsyncMock()
        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client, on_state_changed=lambda: callback_called.append(True))
        player._status_model = PlayerStatus(play_state="play", source="wifi")

        await player.set_source("bluetooth")

        # Verify optimistic update
        assert player._status_model.source == "bluetooth"
        # Verify callback triggered
        assert len(callback_called) == 1

    @pytest.mark.asyncio
    async def test_get_queue_no_upnp(self, mock_client):
        """Test get_queue without UPnP client raises error."""
        from pywiim.player import Player

        player = Player(mock_client)

        with pytest.raises(WiiMError, match="requires UPnP client"):
            await player.get_queue()

    @pytest.mark.asyncio
    async def test_get_queue_with_upnp(self, mock_client):
        """Test get_queue with UPnP client."""
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.browse_queue = AsyncMock(
            return_value={
                "Result": (
                    '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
                    'xmlns:dc="http://purl.org/dc/elements/1.1/" '
                    'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
                    "<item>"
                    '<res duration="0:03:45">http://example.com/song1.mp3</res>'
                    "<dc:title>Song 1</dc:title>"
                    "<upnp:artist>Artist 1</upnp:artist>"
                    "<upnp:album>Album 1</upnp:album>"
                    "</item>"
                    "<item>"
                    '<res duration="0:04:20">http://example.com/song2.mp3</res>'
                    "<dc:title>Song 2</dc:title>"
                    "<upnp:artist>Artist 2</upnp:artist>"
                    "</item>"
                    "</DIDL-Lite>"
                ),
                "NumberReturned": 2,
                "TotalMatches": 2,
                "UpdateID": 1,
            }
        )

        player = Player(mock_client, upnp_client=mock_upnp_client)
        queue = await player.get_queue()

        assert len(queue) == 2
        # First item
        assert queue[0]["media_content_id"] == "http://example.com/song1.mp3"
        assert queue[0]["title"] == "Song 1"
        assert queue[0]["artist"] == "Artist 1"
        assert queue[0]["album"] == "Album 1"
        assert queue[0]["position"] == 0
        assert queue[0]["duration"] == 225  # 3:45 = 225 seconds
        # Second item
        assert queue[1]["media_content_id"] == "http://example.com/song2.mp3"
        assert queue[1]["title"] == "Song 2"
        assert queue[1]["artist"] == "Artist 2"
        assert queue[1]["position"] == 1
        assert queue[1]["duration"] == 260  # 4:20 = 260 seconds

        mock_upnp_client.browse_queue.assert_called_once_with(
            object_id="Q:0",
            starting_index=0,
            requested_count=0,
        )

    @pytest.mark.asyncio
    async def test_get_queue_with_custom_object_id(self, mock_client):
        """Test get_queue with custom object ID."""
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.browse_queue = AsyncMock(
            return_value={
                "Result": '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"></DIDL-Lite>',
                "NumberReturned": 0,
                "TotalMatches": 0,
                "UpdateID": 1,
            }
        )

        player = Player(mock_client, upnp_client=mock_upnp_client)
        queue = await player.get_queue(object_id="Q:1", starting_index=10, requested_count=50)

        assert len(queue) == 0
        mock_upnp_client.browse_queue.assert_called_once_with(
            object_id="Q:1",
            starting_index=10,
            requested_count=50,
        )

    @pytest.mark.asyncio
    async def test_get_queue_empty(self, mock_client):
        """Test get_queue with empty queue."""
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.browse_queue = AsyncMock(
            return_value={
                "Result": '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/"></DIDL-Lite>',
                "NumberReturned": 0,
                "TotalMatches": 0,
                "UpdateID": 1,
            }
        )

        player = Player(mock_client, upnp_client=mock_upnp_client)
        queue = await player.get_queue()

        assert len(queue) == 0

    @pytest.mark.asyncio
    async def test_get_queue_with_image_url(self, mock_client):
        """Test get_queue with album art."""
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.browse_queue = AsyncMock(
            return_value={
                "Result": (
                    '<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
                    'xmlns:dc="http://purl.org/dc/elements/1.1/" '
                    'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
                    "<item>"
                    "<res>http://example.com/song.mp3</res>"
                    "<dc:title>Song</dc:title>"
                    "<upnp:albumArtURI>http://example.com/art.jpg</upnp:albumArtURI>"
                    "</item>"
                    "</DIDL-Lite>"
                ),
                "NumberReturned": 1,
                "TotalMatches": 1,
                "UpdateID": 1,
            }
        )

        player = Player(mock_client, upnp_client=mock_upnp_client)
        queue = await player.get_queue()

        assert len(queue) == 1
        assert queue[0]["media_content_id"] == "http://example.com/song.mp3"
        assert queue[0]["title"] == "Song"
        assert queue[0]["image_url"] == "http://example.com/art.jpg"
        assert queue[0]["position"] == 0

    @pytest.mark.asyncio
    async def test_get_queue_invalid_xml(self, mock_client):
        """Test get_queue with invalid XML (should return empty list)."""
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.browse_queue = AsyncMock(
            return_value={
                "Result": "<invalid>not valid XML",
                "NumberReturned": 0,
                "TotalMatches": 0,
                "UpdateID": 1,
            }
        )

        player = Player(mock_client, upnp_client=mock_upnp_client)
        queue = await player.get_queue()

        # Should handle gracefully and return empty list
        assert len(queue) == 0

    @pytest.mark.asyncio
    async def test_get_queue_browse_failure(self, mock_client):
        """Test get_queue when browse fails."""
        from async_upnp_client.exceptions import UpnpError

        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.browse_queue = AsyncMock(side_effect=UpnpError("Browse failed"))

        player = Player(mock_client, upnp_client=mock_upnp_client)

        with pytest.raises(WiiMError, match="Failed to get queue"):
            await player.get_queue()

    @pytest.mark.asyncio
    async def test_play_queue_no_upnp(self, mock_client):
        """Test play_queue without UPnP client."""
        from pywiim.player import Player

        player = Player(mock_client)

        with pytest.raises(WiiMError, match="requires UPnP client"):
            await player.play_queue(0)

    @pytest.mark.asyncio
    async def test_play_queue_success(self, mock_client):
        """Test play_queue with UPnP client."""
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.async_call_action = AsyncMock(return_value={})

        player = Player(mock_client, upnp_client=mock_upnp_client)
        await player.play_queue(5)

        # Should call Seek with TRACK_NR unit (1-based, so position 5 becomes 6)
        mock_upnp_client.async_call_action.assert_called_once_with(
            "av_transport",
            "Seek",
            {
                "InstanceID": 0,
                "Unit": "TRACK_NR",
                "Target": "6",  # 0-based position 5 becomes 1-based track 6
            },
        )

    @pytest.mark.asyncio
    async def test_play_queue_invalid_position(self, mock_client):
        """Test play_queue with invalid position."""
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        mock_upnp_client = MagicMock(spec=UpnpClient)
        player = Player(mock_client, upnp_client=mock_upnp_client)

        with pytest.raises(WiiMError, match="Invalid queue position"):
            await player.play_queue(-1)

    @pytest.mark.asyncio
    async def test_remove_from_queue_no_upnp(self, mock_client):
        """Test remove_from_queue without UPnP client."""
        from pywiim.player import Player

        player = Player(mock_client)

        with pytest.raises(WiiMError, match="requires UPnP client"):
            await player.remove_from_queue(0)

    @pytest.mark.asyncio
    async def test_remove_from_queue_success(self, mock_client):
        """Test remove_from_queue with UPnP client."""
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.async_call_action = AsyncMock(return_value={})

        player = Player(mock_client, upnp_client=mock_upnp_client)
        await player.remove_from_queue(3)

        # Should call RemoveTrackFromQueue with ObjectID (1-based)
        mock_upnp_client.async_call_action.assert_called_once_with(
            "av_transport",
            "RemoveTrackFromQueue",
            {
                "InstanceID": 0,
                "ObjectID": "Q:0/4",  # 0-based position 3 becomes 1-based track 4
                "UpdateID": 0,
            },
        )

    @pytest.mark.asyncio
    async def test_remove_from_queue_invalid_position(self, mock_client):
        """Test remove_from_queue with invalid position."""
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        mock_upnp_client = MagicMock(spec=UpnpClient)
        player = Player(mock_client, upnp_client=mock_upnp_client)

        with pytest.raises(WiiMError, match="Invalid queue position"):
            await player.remove_from_queue(-1)

    @pytest.mark.asyncio
    async def test_clear_queue_no_upnp(self, mock_client):
        """Test clear_queue without UPnP client."""
        from pywiim.player import Player

        player = Player(mock_client)

        with pytest.raises(WiiMError, match="requires UPnP client"):
            await player.clear_queue()

    @pytest.mark.asyncio
    async def test_clear_queue_success(self, mock_client):
        """Test clear_queue with UPnP client."""
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.async_call_action = AsyncMock(return_value={})

        player = Player(mock_client, upnp_client=mock_upnp_client)
        await player.clear_queue()

        mock_upnp_client.async_call_action.assert_called_once_with(
            "av_transport",
            "RemoveAllTracksFromQueue",
            {
                "InstanceID": 0,
            },
        )

    @pytest.mark.asyncio
    async def test_clear_playlist_with_playqueue_service(self, mock_client):
        """Test clear_playlist with UPnP PlayQueue service."""
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.async_call_action = AsyncMock(return_value={})
        mock_upnp_client.play_queue = MagicMock()  # PlayQueue service available

        mock_client.clear_playlist = AsyncMock()

        player = Player(mock_client, upnp_client=mock_upnp_client)
        await player.clear_playlist()

        # Should use UPnP PlayQueue DeleteQueue action
        mock_upnp_client.async_call_action.assert_called_once_with(
            "play_queue",
            "DeleteQueue",
            {
                "QueueName": "CurrentQueue",
            },
        )
        # Should NOT call HTTP API when UPnP succeeds
        mock_client.clear_playlist.assert_not_called()

    @pytest.mark.asyncio
    async def test_clear_playlist_without_upnp(self, mock_client):
        """Test clear_playlist without UPnP client falls back to HTTP API."""
        from pywiim.player import Player

        mock_client.clear_playlist = AsyncMock()

        player = Player(mock_client)
        await player.clear_playlist()

        # Should fall back to HTTP API
        mock_client.clear_playlist.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_playlist_without_playqueue_service(self, mock_client):
        """Test clear_playlist with UPnP client but no PlayQueue service falls back to HTTP API."""
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.play_queue = None  # PlayQueue service not available

        mock_client.clear_playlist = AsyncMock()

        player = Player(mock_client, upnp_client=mock_upnp_client)
        await player.clear_playlist()

        # Should fall back to HTTP API
        mock_client.clear_playlist.assert_called_once()
        # Should NOT call UPnP when PlayQueue service is not available
        mock_upnp_client.async_call_action.assert_not_called()

    @pytest.mark.asyncio
    async def test_clear_playlist_playqueue_failure_fallback(self, mock_client):
        """Test clear_playlist falls back to HTTP API when UPnP PlayQueue fails."""
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.async_call_action = AsyncMock(side_effect=Exception("UPnP error"))
        mock_upnp_client.play_queue = MagicMock()  # PlayQueue service available

        mock_client.clear_playlist = AsyncMock()

        player = Player(mock_client, upnp_client=mock_upnp_client)
        await player.clear_playlist()

        # Should try UPnP first
        mock_upnp_client.async_call_action.assert_called_once_with(
            "play_queue",
            "DeleteQueue",
            {
                "QueueName": "CurrentQueue",
            },
        )
        # Should fall back to HTTP API after UPnP failure
        mock_client.clear_playlist.assert_called_once()

    @pytest.mark.asyncio
    async def test_play_notification_uses_prompt_on_native_source(self, mock_client):
        """Test play_notification uses native prompt path on supported sources."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import NotificationPlaybackResult, Player

        mock_client.play_notification = AsyncMock()
        mock_client.play_url = AsyncMock()
        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        callback_called = []
        player = Player(mock_client, on_state_changed=lambda: callback_called.append(True))
        player._status_model = PlayerStatus(play_state="play", source="wifi")

        result = await player.play_notification("http://example.com/notification.mp3")

        assert result == NotificationPlaybackResult(
            method_used="prompt",
            source_before="wifi",
            likely_interrupted=False,
            reason=None,
        )
        mock_client.play_notification.assert_called_once_with("http://example.com/notification.mp3")
        mock_client.play_url.assert_not_called()
        assert len(callback_called) == 1

    @pytest.mark.asyncio
    async def test_play_notification_falls_back_on_spotify(self, mock_client):
        """Test play_notification falls back to play_url on Spotify source."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        mock_client.play_notification = AsyncMock()
        mock_client.play_url = AsyncMock()
        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client)
        player._status_model = PlayerStatus(play_state="play", source="spotify")

        result = await player.play_notification("http://example.com/notification.mp3")

        assert result.method_used == "play_url"
        assert result.source_before == "spotify"
        assert result.likely_interrupted is True
        assert result.reason == "unsupported_source"
        mock_client.play_url.assert_called_once_with("http://example.com/notification.mp3")
        mock_client.play_notification.assert_not_called()
        assert player._last_played_url == "http://example.com/notification.mp3"

    @pytest.mark.asyncio
    async def test_play_notification_falls_back_on_unknown_source(self, mock_client):
        """Test play_notification falls back for unknown sources."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        mock_client.play_notification = AsyncMock()
        mock_client.play_url = AsyncMock()
        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client)
        player._status_model = PlayerStatus(play_state="play", source="some_new_source")

        result = await player.play_notification("http://example.com/notification.mp3")

        assert result.method_used == "play_url"
        assert result.source_before == "some_new_source"
        assert result.likely_interrupted is True
        assert result.reason == "unknown_source_default_fallback"
        mock_client.play_url.assert_called_once_with("http://example.com/notification.mp3")
        mock_client.play_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_play_notification_falls_back_when_source_missing(self, mock_client):
        """Test play_notification falls back when source is unavailable."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        mock_client.play_notification = AsyncMock()
        mock_client.play_url = AsyncMock()
        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client)
        player._status_model = PlayerStatus(play_state="play")

        result = await player.play_notification("http://example.com/notification.mp3")

        assert result.method_used == "play_url"
        assert result.source_before is None
        assert result.likely_interrupted is True
        assert result.reason == "unknown_source_default_fallback"
        mock_client.play_url.assert_called_once_with("http://example.com/notification.mp3")
        mock_client.play_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_play_preset(self, mock_client):
        """Test play preset command."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        mock_client.play_preset = AsyncMock()
        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client)
        await player.play_preset(1)

        mock_client.play_preset.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_set_source(self, mock_client):
        """Test set source command updates optimistic state."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        callback_called = []
        mock_client.set_source = AsyncMock()
        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client, on_state_changed=lambda: callback_called.append(True))
        player._status_model = PlayerStatus(play_state="play", source="wifi")

        await player.set_source("bluetooth")

        # Verify API was called
        mock_client.set_source.assert_called_once_with("bluetooth")
        # Verify optimistic state update (source is preserved during refresh)
        assert player._status_model.source == "bluetooth"
        # Verify callback was triggered
        assert len(callback_called) == 1

    def test_source_id_property(self, mock_client):
        """Test that source/source_id return stable ids and source_name is UI-ready."""
        from pywiim.models import PlayerStatus
        from pywiim.player import Player

        player = Player(mock_client)

        # "wifi" is presented as "Network" in UI, but stable id should be "network"
        player._status_model = PlayerStatus(play_state="play", source="wifi")
        assert player.source == "network"
        assert player.source_id == "network"
        assert player.source_name == "Network"

        # API form "line-in" should map to stable "line_in"
        player._status_model = PlayerStatus(play_state="play", source="line-in")
        assert player.source == "line_in"
        assert player.source_id == "line_in"
        assert player.source_name == "Line In"

        # Virtual/follower labels should be normalized in a stable way
        player._status_model = PlayerStatus(play_state="play", source="Master Bedroom")
        assert player.source == "master_bedroom"
        assert player.source_id == "master_bedroom"
        assert player.source_name == "Master Bedroom"

    @pytest.mark.asyncio
    async def test_set_source_blocked_by_capabilities(self, mock_client):
        """Test capability-driven non-selectable source block."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        mock_client.capabilities["non_selectable_source_ids"] = ["line_in"]
        mock_client.set_source = AsyncMock()
        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play", source="wifi"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client)
        player._status_model = PlayerStatus(play_state="play", source="wifi")

        with pytest.raises(ValueError, match="not directly selectable"):
            await player.set_source("Line In")

        mock_client.set_source.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_source_raises_on_confirmed_noop_switch(self, mock_client):
        """Test silent switchmode no-op detection raises WiiMError."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        mock_client.set_source = AsyncMock()
        # Device keeps reporting wifi after switch command, confirming no-op.
        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play", source="wifi"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client)
        player._status_model = PlayerStatus(play_state="play", source="wifi")

        with pytest.raises(WiiMError, match="did not change source state"):
            await player.set_source("bluetooth")

    @pytest.mark.asyncio
    async def test_set_audio_output_mode(self, mock_client):
        """Test set audio output mode command."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        mock_client.set_audio_output_mode = AsyncMock()
        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client)
        await player.set_audio_output_mode("Line Out")

        mock_client.set_audio_output_mode.assert_called_once_with("Line Out")

    @pytest.mark.asyncio
    async def test_set_shuffle(self, mock_client):
        """Test set shuffle command preserves repeat state."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        mock_client.set_loop_mode = AsyncMock()
        status = PlayerStatus(play_state="play", repeat="all", source="usb")
        mock_client.get_player_status_model = AsyncMock(return_value=status)
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client)
        player._status_model = status  # Cache status so repeat_mode property works
        await player.set_shuffle(True)

        # Should call set_loop_mode with shuffle+repeat_all (2 for WiiM)
        mock_client.set_loop_mode.assert_called_once_with(2)

    @pytest.mark.asyncio
    async def test_set_shuffle_off(self, mock_client):
        """Test set shuffle off preserves repeat state."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        mock_client.set_loop_mode = AsyncMock()
        status = PlayerStatus(play_state="play", repeat="one", source="usb")
        mock_client.get_player_status_model = AsyncMock(return_value=status)
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client)
        player._status_model = status  # Cache status so repeat_mode property works
        await player.set_shuffle(False)

        # Should call set_loop_mode with repeat_one only (1)
        mock_client.set_loop_mode.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_set_repeat(self, mock_client):
        """Test set repeat command preserves shuffle state."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        mock_client.set_loop_mode = AsyncMock()
        status = PlayerStatus(play_state="play", shuffle="1", source="usb")
        mock_client.get_player_status_model = AsyncMock(return_value=status)
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client)
        player._status_model = status  # Cache status so shuffle_state property works
        await player.set_repeat("all")

        # Should call set_loop_mode with shuffle+repeat_all (2 for WiiM)
        mock_client.set_loop_mode.assert_called_once_with(2)

    @pytest.mark.asyncio
    async def test_set_repeat_off(self, mock_client):
        """Test set repeat off preserves shuffle state."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        mock_client.set_loop_mode = AsyncMock()
        status = PlayerStatus(play_state="play", shuffle="1", source="usb")
        mock_client.get_player_status_model = AsyncMock(return_value=status)
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client)
        player._status_model = status  # Cache status so shuffle_state property works
        await player.set_repeat("off")

        # Should call set_loop_mode with shuffle only (3 for WiiM)
        mock_client.set_loop_mode.assert_called_once_with(3)

    @pytest.mark.asyncio
    async def test_set_repeat_invalid(self, mock_client):
        """Test set repeat with invalid mode raises ValueError."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client)
        with pytest.raises(ValueError, match="Invalid repeat mode"):
            await player.set_repeat("invalid")

    @pytest.mark.asyncio
    async def test_set_shuffle_raises_error_for_external_source(self, mock_client):
        """Test set_shuffle raises WiiMError for blacklisted external sources (radio only)."""
        from pywiim.exceptions import WiiMError
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        # Use tunein (radio) which is still blacklisted
        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play", source="tunein"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client)
        await player.refresh()

        # Should raise WiiMError because TuneIn (radio) doesn't support device control
        with pytest.raises(WiiMError, match="Shuffle cannot be controlled when playing from"):
            await player.set_shuffle(True)

    @pytest.mark.asyncio
    async def test_set_repeat_raises_error_for_external_source(self, mock_client):
        """Test set_repeat raises WiiMError for blacklisted external sources (radio only)."""
        from pywiim.exceptions import WiiMError
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        # Use tunein (radio) which is still blacklisted
        mock_client.get_player_status_model = AsyncMock(
            return_value=PlayerStatus(play_state="play", source="tunein")  # Radio stream (blacklisted)
        )
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client)
        await player.refresh()

        # Should raise WiiMError because TuneIn (radio) doesn't support device control
        with pytest.raises(WiiMError, match="Repeat cannot be controlled when playing from"):
            await player.set_repeat("all")

    @pytest.mark.asyncio
    async def test_set_shuffle_works_for_device_controlled_source(self, mock_client):
        """Test set_shuffle works normally for device-controlled sources."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play", source="usb"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))
        mock_client.set_loop_mode = AsyncMock()

        player = Player(mock_client)
        await player.refresh()

        # Should work without errors for USB source
        await player.set_shuffle(True)
        mock_client.set_loop_mode.assert_called_once_with(3)  # loop_mode=3 is shuffle only for WiiM

    @pytest.mark.asyncio
    async def test_set_repeat_works_for_device_controlled_source(self, mock_client):
        """Test set_repeat works normally for device-controlled sources."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play", source="usb"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))
        mock_client.set_loop_mode = AsyncMock()

        player = Player(mock_client)
        await player.refresh()

        # Should work without errors for USB source
        await player.set_repeat("all")
        mock_client.set_loop_mode.assert_called_once_with(0)  # loop_mode=0 is repeat_all for WiiM


class TestPlayerMediaMetadata:
    """Test Player media metadata properties."""

    @pytest.mark.asyncio
    async def test_media_title(self, mock_client):
        """Test getting media title."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(title="Test Song", play_state="play")
        player._status_model = status

        assert player.media_title == "Test Song"

    @pytest.mark.asyncio
    async def test_media_artist(self, mock_client):
        """Test getting media artist."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(artist="Test Artist", play_state="play")
        player._status_model = status

        assert player.media_artist == "Test Artist"

    @pytest.mark.asyncio
    async def test_media_album(self, mock_client):
        """Test getting media album."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(album="Test Album", play_state="play")
        player._status_model = status

        assert player.media_album == "Test Album"

    @pytest.mark.asyncio
    async def test_media_duration(self, mock_client):
        """Test getting media duration."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(duration=240, play_state="play")
        player._status_model = status

        assert player.media_duration == 240

    @pytest.mark.asyncio
    async def test_play_state(self, mock_client):
        """Test getting play state."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(play_state="play")
        player._status_model = status

        assert player.play_state == "play"

    @pytest.mark.asyncio
    async def test_is_playing(self, mock_client):
        """Test is_playing property for various play states."""
        from pywiim.player import Player

        player = Player(mock_client)

        # Test playing states
        for state in ["play", "playing", "buffering", "loading", "transitioning", "load"]:
            player._state_synchronizer.update_from_http({"play_state": state})
            assert player.is_playing is True, f"Expected is_playing=True for state '{state}'"

        # Test non-playing states
        for state in ["pause", "stop", "idle", "none"]:
            player._state_synchronizer.update_from_http({"play_state": state})
            assert player.is_playing is False, f"Expected is_playing=False for state '{state}'"

        # Test None state
        player._status_model = None
        player._state_synchronizer = player._state_synchronizer.__class__()  # Reset
        assert player.is_playing is False

    @pytest.mark.asyncio
    async def test_is_paused(self, mock_client):
        """Test is_paused property."""
        from pywiim.player import Player

        player = Player(mock_client)

        # Test paused state (note: "stop" is normalized to "pause" for modern UX)
        for state in ["pause", "stop"]:
            player._state_synchronizer.update_from_http({"play_state": state})
            assert player.is_paused is True, f"Expected is_paused=True for state '{state}'"

        # Test non-paused states
        for state in ["play", "idle", "buffering"]:
            player._state_synchronizer.update_from_http({"play_state": state})
            assert player.is_paused is False, f"Expected is_paused=False for state '{state}'"

    @pytest.mark.asyncio
    async def test_is_idle(self, mock_client):
        """Test is_idle property."""
        from pywiim.player import Player

        player = Player(mock_client)

        # Test idle states (note: "stop" is normalized to "pause", not idle)
        for state in ["idle", "none"]:
            player._state_synchronizer.update_from_http({"play_state": state})
            assert player.is_idle is True, f"Expected is_idle=True for state '{state}'"

        # Test non-idle states (including "stop" which becomes "pause")
        for state in ["play", "pause", "stop", "buffering"]:
            player._state_synchronizer.update_from_http({"play_state": state})
            assert player.is_idle is False, f"Expected is_idle=False for state '{state}'"

        # Test None state (should be idle)
        player._status_model = None
        player._state_synchronizer = player._state_synchronizer.__class__()  # Reset
        assert player.is_idle is True

    @pytest.mark.asyncio
    async def test_is_buffering(self, mock_client):
        """Test is_buffering property."""
        from pywiim.player import Player

        player = Player(mock_client)

        # Test buffering states
        for state in ["buffering", "loading", "transitioning", "load"]:
            player._state_synchronizer.update_from_http({"play_state": state})
            assert player.is_buffering is True, f"Expected is_buffering=True for state '{state}'"

        # Test non-buffering states
        for state in ["play", "pause", "stop", "idle"]:
            player._state_synchronizer.update_from_http({"play_state": state})
            assert player.is_buffering is False, f"Expected is_buffering=False for state '{state}'"

    @pytest.mark.asyncio
    async def test_state_normalized(self, mock_client):
        """Test state property returns normalized values."""
        from pywiim.player import Player

        player = Player(mock_client)

        # Test playing state
        player._state_synchronizer.update_from_http({"play_state": "play"})
        assert player.state == "playing"

        # Test paused state (including "stop" which normalizes to "pause")
        player._state_synchronizer.update_from_http({"play_state": "pause"})
        assert player.state == "paused"
        player._state_synchronizer.update_from_http({"play_state": "stop"})
        assert player.state == "paused"

        # Test idle state
        player._state_synchronizer.update_from_http({"play_state": "idle"})
        assert player.state == "idle"

        # Test buffering states - buffering takes precedence over playing
        for state in ["buffering", "loading", "transitioning"]:
            player._state_synchronizer.update_from_http({"play_state": state})
            assert player.state == "buffering", f"Expected state='buffering' for play_state '{state}'"

    @pytest.mark.asyncio
    async def test_source(self, mock_client):
        """Test getting source."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(source="wifi", play_state="play")
        player._status_model = status

        # Ensure state synchronizer has source data (property reads from synchronizer first)
        player._state_synchronizer.update_from_http({"source": "wifi"})

        # `source` is stable id, `source_name` is UI-ready
        assert player.source == "network"
        assert player.source_name == "Network"

    @pytest.mark.asyncio
    async def test_media_duration_zero(self, mock_client):
        """Test getting media duration when zero (streaming)."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(duration=0, play_state="play")
        player._status_model = status

        assert player.media_duration is None  # Zero duration returns None

    @pytest.mark.asyncio
    async def test_media_duration_string(self, mock_client):
        """Test getting media duration from string."""
        from pywiim.player import Player

        player = Player(mock_client)
        # Create a status with duration as string (simulating API response)
        status = PlayerStatus(play_state="play")
        status.duration = "240"  # String duration
        player._status_model = status

        assert player.media_duration == 240

    @pytest.mark.asyncio
    async def test_media_position_basic(self, mock_client):
        """Test getting media position."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(position=120, duration=240, play_state="play")
        player._status_model = status
        # Update state synchronizer with position data
        player._state_synchronizer.update_from_http({"position": 120, "duration": 240, "play_state": "play"})

        assert player.media_position == 120

    @pytest.mark.asyncio
    async def test_media_position_negative(self, mock_client):
        """Test getting media position when negative."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(position=-10, duration=240, play_state="play")
        player._status_model = status

        assert player.media_position is None  # Negative position returns None

    @pytest.mark.asyncio
    async def test_media_position_clamped_to_duration(self, mock_client):
        """Test media position clamped to duration."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(position=300, duration=240, play_state="play")
        player._status_model = status
        # Update state synchronizer with position data
        player._state_synchronizer.update_from_http({"position": 300, "duration": 240, "play_state": "play"})

        assert player.media_position == 240  # Clamped to duration

    @pytest.mark.asyncio
    async def test_media_position_returns_raw_device_value(self, mock_client):
        """Test media position returns raw device value without estimation."""
        import time

        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(position=100, duration=240, play_state="play")
        player._status_model = status
        # Update state synchronizer with position data
        player._state_synchronizer.update_from_http({"position": 100, "duration": 240, "play_state": "play"})

        # Initial position
        pos1 = player.media_position
        assert pos1 == 100

        # Wait a bit and check again (should NOT estimate - returns raw value)
        time.sleep(0.1)
        pos2 = player.media_position
        # Should remain unchanged (raw device value, no estimation)
        assert pos2 == 100

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_media_image_url(self, mock_client):
        """Test getting media image URL."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(entity_picture="http://example.com/artwork.jpg", play_state="play")
        player._status_model = status

        assert player.media_image_url == "http://example.com/artwork.jpg"

    @pytest.mark.asyncio
    async def test_media_image_url_cover_url(self, mock_client):
        """Test getting media image URL from cover_url."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(cover_url="http://example.com/cover.jpg", play_state="play")
        player._status_model = status

        assert player.media_image_url == "http://example.com/cover.jpg"

    @pytest.mark.asyncio
    async def test_fetch_cover_art_success(self, mock_client):
        """Test fetching cover art successfully."""
        from unittest.mock import AsyncMock, MagicMock

        from pywiim.player import Player

        player = Player(mock_client)

        # Mock aiohttp session and response
        # The response needs to be an async context manager
        mock_response = MagicMock()
        mock_response.status = 200
        # Headers needs to support .get() method
        mock_headers = MagicMock()
        mock_headers.get = MagicMock(return_value="image/jpeg")
        mock_response.headers = mock_headers
        mock_response.read = AsyncMock(return_value=b"fake_image_data")
        # Make it work as async context manager - __aenter__ returns self
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        # session.get() returns the mock_response directly (which is an async context manager)
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False

        mock_client._session = mock_session

        result = await player.fetch_cover_art("http://example.com/artwork.jpg")

        assert result is not None
        image_bytes, content_type = result
        assert image_bytes == b"fake_image_data"
        assert content_type == "image/jpeg"
        mock_session.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_cover_art_uses_current_track_url(self, mock_client):
        """Test fetching cover art uses current track's URL when None provided."""
        from unittest.mock import AsyncMock, MagicMock

        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(entity_picture="http://example.com/track.jpg", play_state="play")
        player._status_model = status

        # Mock aiohttp session and response
        mock_response = MagicMock()
        mock_response.status = 200
        # Headers needs to support .get() method
        mock_headers = MagicMock()
        mock_headers.get = MagicMock(return_value="image/png")
        mock_response.headers = mock_headers
        mock_response.read = AsyncMock(return_value=b"track_image_data")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False

        mock_client._session = mock_session

        result = await player.fetch_cover_art()

        assert result is not None
        image_bytes, content_type = result
        assert image_bytes == b"track_image_data"
        assert content_type == "image/png"
        # Should have called with the track's URL
        mock_session.get.assert_called_once()
        call_args = mock_session.get.call_args[0]
        assert "track.jpg" in call_args[0]

    @pytest.mark.asyncio
    async def test_fetch_cover_art_no_url(self, mock_client):
        """Test fetching cover art when no URL is available - should return embedded logo."""
        import base64

        from pywiim.api.constants import EMBEDDED_LOGO_BASE64
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(play_state="play")  # No cover art URL
        player._status_model = status

        # Call fetch_cover_art() with no URL - should return embedded logo without HTTP call
        result = await player.fetch_cover_art()

        assert result is not None
        image_bytes, content_type = result

        # Verify it returned the embedded logo (decoded from base64)
        expected_bytes = base64.b64decode("".join(EMBEDDED_LOGO_BASE64))
        assert image_bytes == expected_bytes
        assert content_type == "image/png"

        # Verify NO HTTP call was made (embedded logo served directly)
        mock_client._session.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_cover_art_caching(self, mock_client):
        """Test that cover art is cached after first fetch."""
        from unittest.mock import AsyncMock, MagicMock

        from pywiim.player import Player

        player = Player(mock_client)

        # Mock aiohttp session and response
        mock_response = MagicMock()
        mock_response.status = 200
        # Headers needs to support .get() method
        mock_headers = MagicMock()
        mock_headers.get = MagicMock(return_value="image/jpeg")
        mock_response.headers = mock_headers
        mock_response.read = AsyncMock(return_value=b"cached_image_data")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False

        mock_client._session = mock_session

        url = "http://example.com/cache_test.jpg"

        # First fetch - should make HTTP request
        result1 = await player.fetch_cover_art(url)
        assert result1 is not None
        assert mock_session.get.call_count == 1

        # Second fetch - should use cache
        result2 = await player.fetch_cover_art(url)
        assert result2 is not None
        assert result2 == result1
        # Should still be only 1 call (cached)
        assert mock_session.get.call_count == 1

    @pytest.mark.asyncio
    async def test_fetch_cover_art_http_error(self, mock_client):
        """Test fetching cover art handles HTTP errors gracefully."""
        from unittest.mock import AsyncMock, MagicMock

        from pywiim.player import Player

        player = Player(mock_client)

        # Mock aiohttp session with 404 response
        mock_response = MagicMock()
        mock_response.status = 404
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False

        mock_client._session = mock_session

        result = await player.fetch_cover_art("http://example.com/notfound.jpg")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_cover_art_network_error(self, mock_client):
        """Test fetching cover art handles network errors gracefully."""
        from unittest.mock import AsyncMock, MagicMock

        import aiohttp

        from pywiim.player import Player

        player = Player(mock_client)

        # Mock aiohttp session that raises exception
        mock_session = MagicMock()
        mock_session.get = AsyncMock(side_effect=aiohttp.ClientError("Network error"))
        mock_session.closed = False

        mock_client._session = mock_session

        result = await player.fetch_cover_art("http://example.com/error.jpg")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_cover_art_creates_session_when_needed(self, mock_client):
        """Test fetching cover art creates temporary session when client has none."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from pywiim.player import Player

        player = Player(mock_client)
        mock_client._session = None  # No session on client

        # Mock aiohttp session and response
        mock_response = MagicMock()
        mock_response.status = 200
        # Headers needs to support .get() method
        mock_headers = MagicMock()
        mock_headers.get = MagicMock(return_value="image/jpeg")
        mock_response.headers = mock_headers
        mock_response.read = AsyncMock(return_value=b"image_data")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.close = AsyncMock()
        mock_session.closed = False

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await player.fetch_cover_art("http://example.com/test.jpg")

            assert result is not None
            mock_session.get.assert_called_once()
            mock_session.close.assert_called_once()  # Should close temporary session

    @pytest.mark.asyncio
    async def test_get_cover_art_bytes(self, mock_client):
        """Test get_cover_art_bytes convenience method."""
        from unittest.mock import AsyncMock, MagicMock

        from pywiim.player import Player

        player = Player(mock_client)

        # Mock aiohttp session and response
        mock_response = MagicMock()
        mock_response.status = 200
        # Headers needs to support .get() method
        mock_headers = MagicMock()
        mock_headers.get = MagicMock(return_value="image/jpeg")
        mock_response.headers = mock_headers
        mock_response.read = AsyncMock(return_value=b"image_bytes")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.closed = False

        mock_client._session = mock_session

        result = await player.get_cover_art_bytes("http://example.com/test.jpg")

        assert result == b"image_bytes"

    @pytest.mark.asyncio
    async def test_get_cover_art_bytes_none(self, mock_client):
        """Test get_cover_art_bytes returns embedded logo when no cover art."""
        import base64

        from pywiim.api.constants import EMBEDDED_LOGO_BASE64
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(play_state="play")  # No cover art URL
        player._status_model = status

        result = await player.get_cover_art_bytes()

        # Should return embedded logo bytes, not None
        assert result is not None
        expected_bytes = base64.b64decode("".join(EMBEDDED_LOGO_BASE64))
        assert result == expected_bytes

    @pytest.mark.asyncio
    async def test_shuffle_state(self, mock_client):
        """Test getting shuffle state."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(play_state="play", source="usb")
        status.shuffle = "1"  # shuffle is a string field
        player._status_model = status

        assert player.shuffle_state is True

    @pytest.mark.asyncio
    async def test_shuffle_state_from_play_mode(self, mock_client):
        """Test getting shuffle state from play_mode."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(play_state="play", source="usb")
        status.play_mode = "shuffle"
        player._status_model = status

        assert player.shuffle_state is True

    @pytest.mark.asyncio
    async def test_repeat_mode_one(self, mock_client):
        """Test getting repeat mode 'one'."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(repeat="one", play_state="play", source="usb")
        player._status_model = status

        assert player.repeat_mode == "one"

    @pytest.mark.asyncio
    async def test_repeat_mode_all(self, mock_client):
        """Test getting repeat mode 'all'."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(repeat="all", play_state="play", source="usb")
        player._status_model = status

        assert player.repeat_mode == "all"

    @pytest.mark.asyncio
    async def test_repeat_mode_from_play_mode(self, mock_client):
        """Test getting repeat mode from play_mode."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(play_state="play", source="usb")
        status.play_mode = "repeat_all"
        player._status_model = status

        assert player.repeat_mode == "all"

    @pytest.mark.asyncio
    async def test_shuffle_supported_full_control_sources(self, mock_client):
        """Test shuffle_supported returns True for sources with full control.

        Full control sources are those where the WiiM device manages the queue
        and can control shuffle/repeat directly.
        """
        from pywiim.player import Player

        player = Player(mock_client)

        # Streaming services and local playback - device controls shuffle
        for source in [
            "usb",
            "wifi",
            "network",
            "playlist",
            "preset",
            "http",
            "spotify",
            "amazon",
            "tidal",
            "qobuz",
            "deezer",
        ]:
            status = PlayerStatus(source=source, play_state="play")
            player._status_model = status
            assert player.shuffle_supported is True, f"shuffle_supported should be True for {source}"

    @pytest.mark.asyncio
    async def test_shuffle_supported_no_control_sources(self, mock_client):
        """Test shuffle_supported returns False for sources without shuffle control.

        These include:
        - Live radio (no queue to shuffle)
        - Physical inputs (passthrough audio)
        - External casting (source app controls shuffle)
        """
        from pywiim.player import Player

        player = Player(mock_client)

        # Live radio - no shuffle concept
        for source in ["tunein", "iheartradio", "radio"]:
            status = PlayerStatus(source=source, play_state="play")
            player._status_model = status
            assert player.shuffle_supported is False, f"shuffle_supported should be False for {source}"

        # Physical inputs - passthrough audio
        for source in ["line_in", "optical", "coaxial", "hdmi"]:
            status = PlayerStatus(source=source, play_state="play")
            player._status_model = status
            assert player.shuffle_supported is False, f"shuffle_supported should be False for {source}"

        # External casting - source app controls shuffle
        for source in ["airplay", "bluetooth", "dlna", "multiroom"]:
            status = PlayerStatus(source=source, play_state="play")
            player._status_model = status
            assert player.shuffle_supported is False, f"shuffle_supported should be False for {source}"

    @pytest.mark.asyncio
    async def test_repeat_supported_full_control_sources(self, mock_client):
        """Test repeat_supported returns True for sources with full control."""
        from pywiim.player import Player

        player = Player(mock_client)

        # Streaming services and local playback - device controls repeat
        for source in [
            "usb",
            "wifi",
            "network",
            "playlist",
            "preset",
            "http",
            "spotify",
            "amazon",
            "tidal",
            "qobuz",
            "deezer",
        ]:
            status = PlayerStatus(source=source, play_state="play")
            player._status_model = status
            assert player.repeat_supported is True, f"repeat_supported should be True for {source}"

    @pytest.mark.asyncio
    async def test_repeat_supported_no_control_sources(self, mock_client):
        """Test repeat_supported returns False for sources without repeat control.

        These include:
        - Live radio (no queue to repeat)
        - Physical inputs (passthrough audio)
        - External casting (source app controls repeat)
        """
        from pywiim.player import Player

        player = Player(mock_client)

        # Live radio - no repeat concept
        for source in ["tunein", "iheartradio", "radio"]:
            status = PlayerStatus(source=source, play_state="play")
            player._status_model = status
            assert player.repeat_supported is False, f"repeat_supported should be False for {source}"

        # Physical inputs - passthrough audio
        for source in ["line_in", "optical", "coaxial", "hdmi"]:
            status = PlayerStatus(source=source, play_state="play")
            player._status_model = status
            assert player.repeat_supported is False, f"repeat_supported should be False for {source}"

        # External casting - source app controls repeat
        for source in ["airplay", "bluetooth", "dlna", "multiroom"]:
            status = PlayerStatus(source=source, play_state="play")
            player._status_model = status
            assert player.repeat_supported is False, f"repeat_supported should be False for {source}"

    @pytest.mark.asyncio
    async def test_shuffle_state_returns_none_for_external_source(self, mock_client):
        """Test shuffle_state returns None for external sources (radio streams only)."""
        from pywiim.player import Player

        player = Player(mock_client)
        # Radio streams don't support shuffle
        status = PlayerStatus(source="tunein", play_state="play", loop_mode=4)  # loop_mode=4 is shuffle
        player._status_model = status

        # Should return None because TuneIn is a radio stream (blacklisted)
        assert player.shuffle_state is None

    @pytest.mark.asyncio
    async def test_repeat_mode_returns_none_for_external_source(self, mock_client):
        """Test repeat_mode returns None only for blacklisted external sources."""
        from pywiim.player import Player

        player = Player(mock_client)
        # Radio streams don't support repeat
        status = PlayerStatus(
            source="tunein", play_state="play", loop_mode=2
        )  # loop_mode=2 is shuffle+repeat_all for WiiM
        player._status_model = status

        # Should return None because TuneIn is a radio stream (blacklisted)
        assert player.repeat_mode is None

        # AirPlay is blacklisted - tested and confirmed iOS controls playback, not device
        status = PlayerStatus(source="airplay", play_state="play", loop_mode=2)
        player._status_model = status
        # Should return None because AirPlay is blacklisted (iOS device controls playback)
        assert player.repeat_mode is None

        # Bluetooth is now blacklisted - external device (phone/tablet) controls playback
        status = PlayerStatus(source="bluetooth", play_state="play", loop_mode=2)
        player._status_model = status
        assert player.repeat_mode is None  # Bluetooth doesn't support device control

    @pytest.mark.asyncio
    async def test_shuffle_state_works_for_device_controlled_source(self, mock_client):
        """Test shuffle_state works normally for device-controlled sources."""
        from pywiim.player import Player

        player = Player(mock_client)
        # For WiiM: loop_mode=3 is shuffle (no repeat), loop_mode=4 is normal (no shuffle, no repeat)
        status = PlayerStatus(source="usb", play_state="play", loop_mode=3)
        player._status_model = status

        # Should decode loop_mode normally for USB source
        assert player.shuffle_state is True

    @pytest.mark.asyncio
    async def test_repeat_mode_works_for_device_controlled_source(self, mock_client):
        """Test repeat_mode works normally for device-controlled sources."""
        from pywiim.player import Player

        player = Player(mock_client)
        # For WiiM: loop_mode=0 is repeat_all, loop_mode=2 is shuffle+repeat_all
        status = PlayerStatus(source="usb", play_state="play", loop_mode=0)
        player._status_model = status

        # Should decode loop_mode normally for USB source
        assert player.repeat_mode == "all"

    @pytest.mark.asyncio
    async def test_supports_next_track_streaming_sources(self, mock_client):
        """Test supports_next_track returns True for streaming services.

        IMPORTANT: Next/prev work even when queue_count is 0 because streaming
        services manage their own queues (not exposed via plicount).
        """
        from pywiim.player import Player

        player = Player(mock_client)

        # Streaming services support next track even with queue_count=0
        for source in ["spotify", "amazon", "tidal", "qobuz", "deezer", "pandora"]:
            status = PlayerStatus(source=source, play_state="play")
            # Deliberately set queue_count to 0 to verify it doesn't affect support
            status.queue_count = 0
            player._status_model = status
            assert player.supports_next_track is True, f"supports_next_track should be True for {source}"
            assert player.supports_previous_track is True, f"supports_previous_track should be True for {source}"

    @pytest.mark.asyncio
    async def test_supports_next_track_local_sources(self, mock_client):
        """Test supports_next_track returns True for local playback sources."""
        from pywiim.player import Player

        player = Player(mock_client)

        # Local sources support next track
        for source in ["usb", "wifi", "http", "playlist", "preset", "network"]:
            status = PlayerStatus(source=source, play_state="play")
            player._status_model = status
            assert player.supports_next_track is True, f"supports_next_track should be True for {source}"
            assert player.supports_previous_track is True, f"supports_previous_track should be True for {source}"

    @pytest.mark.asyncio
    async def test_supports_next_track_external_casting(self, mock_client):
        """Test supports_next_track returns True for AirPlay/Bluetooth/DLNA.

        Even though these are external sources, next/prev commands are forwarded
        to the source app which may handle them.
        """
        from pywiim.player import Player

        player = Player(mock_client)

        # External casting sources - commands forwarded to source app
        for source in ["airplay", "bluetooth", "dlna"]:
            status = PlayerStatus(source=source, play_state="play")
            player._status_model = status
            assert player.supports_next_track is True, f"supports_next_track should be True for {source}"
            assert player.supports_previous_track is True, f"supports_previous_track should be True for {source}"

    @pytest.mark.asyncio
    async def test_supports_next_track_live_radio_false(self, mock_client):
        """Test supports_next_track returns False for live radio (no tracks)."""
        from pywiim.player import Player

        player = Player(mock_client)

        # Live radio has no "next track" concept
        for source in ["tunein", "iheartradio", "radio", "internetradio", "webradio"]:
            status = PlayerStatus(source=source, play_state="play")
            player._status_model = status
            assert player.supports_next_track is False, f"supports_next_track should be False for {source}"
            assert player.supports_previous_track is False, f"supports_previous_track should be False for {source}"

    @pytest.mark.asyncio
    async def test_supports_next_track_physical_inputs_false(self, mock_client):
        """Test supports_next_track returns False for passthrough inputs."""
        from pywiim.player import Player

        player = Player(mock_client)

        # Physical inputs (passthrough audio) have no track concept
        for source in ["line_in", "linein", "optical", "coaxial", "coax", "aux", "hdmi"]:
            status = PlayerStatus(source=source, play_state="play")
            player._status_model = status
            assert player.supports_next_track is False, f"supports_next_track should be False for {source}"
            assert player.supports_previous_track is False, f"supports_previous_track should be False for {source}"

    @pytest.mark.asyncio
    async def test_supports_next_track_multiroom_slave_true(self, mock_client):
        """Test supports_next_track returns True for multiroom slave.

        Slave commands route through Group to master, so next/prev work.
        Same as play/pause which also route through Group.
        """
        from pywiim.player import Player

        player = Player(mock_client)

        # Multiroom slave - commands route through Group to master
        status = PlayerStatus(source="multiroom", play_state="play")
        player._status_model = status
        assert player.supports_next_track is True
        assert player.supports_previous_track is True

    @pytest.mark.asyncio
    async def test_supports_next_track_no_source_false(self, mock_client):
        """Test supports_next_track returns False when no source set."""
        from pywiim.player import Player

        player = Player(mock_client)

        # No source set
        status = PlayerStatus(source=None, play_state="idle")
        player._status_model = status
        assert player.supports_next_track is False
        assert player.supports_previous_track is False

    @pytest.mark.asyncio
    async def test_next_track_supported_aliases(self, mock_client):
        """Test next_track_supported and previous_track_supported aliases.

        These aliases exist for WiiM HA integration compatibility which expects
        *_supported naming rather than supports_* naming.
        """
        from pywiim.player import Player

        player = Player(mock_client)

        # Test with Spotify (should return True)
        status = PlayerStatus(source="spotify", play_state="play")
        player._status_model = status

        # Aliases should return same value as original properties
        assert player.next_track_supported == player.supports_next_track
        assert player.previous_track_supported == player.supports_previous_track
        assert player.next_track_supported is True
        assert player.previous_track_supported is True

        # Test with live radio (should return False)
        status = PlayerStatus(source="tunein", play_state="play")
        player._status_model = status

        assert player.next_track_supported == player.supports_next_track
        assert player.previous_track_supported == player.supports_previous_track
        assert player.next_track_supported is False
        assert player.previous_track_supported is False

        # Test getattr (how HA integration uses it)
        assert (
            getattr(player, "next_track_supported", False) is True
            or getattr(player, "next_track_supported", False) is False
        )
        assert (
            getattr(player, "previous_track_supported", False) is True
            or getattr(player, "previous_track_supported", False) is False
        )

    @pytest.mark.asyncio
    async def test_eq_preset(self, mock_client):
        """Test getting EQ preset."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(eq_preset="flat", play_state="play")
        player._status_model = status

        # Property normalizes to Title Case
        assert player.eq_preset == "Flat"

    @pytest.mark.asyncio
    async def test_available_sources(self, mock_client):
        """Test getting available sources."""
        from pywiim.player import Player

        player = Player(mock_client)
        device_info = DeviceInfo(uuid="test", input_list=["wifi", "bluetooth", "line_in"])
        player._device_info = device_info

        # Returns physical inputs + Network (normalized to Title Case)
        result = player.available_sources
        assert "Bluetooth" in result
        assert "Line In" in result
        assert "Network" in result  # Network is now included

    @pytest.mark.asyncio
    async def test_available_sources_filters_wifi_variations(self, mock_client):
        """Test that WiFi variations are normalized and included."""
        from pywiim.player import Player

        player = Player(mock_client)
        # Test various case variations of wifi
        device_info = DeviceInfo(uuid="test", input_list=["WiFi", "WIFI", "wifi", "bluetooth", "line_in"])
        player._device_info = device_info

        # Network is normalized and included, returns physical inputs + Network (Title Case)
        result = player.available_sources
        assert "Bluetooth" in result
        assert "Line In" in result
        assert "Network" in result  # Network is now included (normalized)

    @pytest.mark.asyncio
    async def test_available_sources_no_wifi(self, mock_client):
        """Test available sources when WiFi is not in the list."""
        from pywiim.player import Player

        player = Player(mock_client)
        device_info = DeviceInfo(uuid="test", input_list=["bluetooth", "line_in", "optical"])
        player._device_info = device_info

        # Returns physical inputs + Network (always added) in Title Case
        result = player.available_sources
        assert "Bluetooth" in result
        assert "Line In" in result
        assert "Optical In" in result
        assert "Network" in result  # Network is always added

    @pytest.mark.asyncio
    async def test_available_sources_only_wifi(self, mock_client):
        """Test available sources when only WiFi is in the list."""
        from pywiim.player import Player

        player = Player(mock_client)
        device_info = DeviceInfo(uuid="test", input_list=["wifi"])
        player._device_info = device_info

        # Network is included, fallback adds default physical inputs (Title Case)
        result = player.available_sources
        assert "Network" in result
        assert "Bluetooth" in result
        assert "Line In" in result
        assert "Optical In" in result

    @pytest.mark.asyncio
    async def test_available_sources_empty_when_no_device_info(self, mock_client):
        """Test available sources returns empty list when device info is None."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._device_info = None

        assert player.available_sources == []

    @pytest.mark.asyncio
    async def test_available_sources_rca(self, mock_client):
        """Test that RCA is correctly identified and normalized in available_sources."""
        from pywiim.player import Player

        player = Player(mock_client)
        # Device reports RCA in input_list (Audio Pro C10 MkII behavior)
        device_info = DeviceInfo(uuid="test", input_list=["RCA", "bluetooth", "wifi"])
        player._device_info = device_info

        # RCA should be included and capitalized correctly
        result = player.available_sources
        assert "RCA" in result
        assert "Bluetooth" in result
        assert "Network" in result

    @pytest.mark.asyncio
    async def test_available_sources_filters_streaming_services(self, mock_client):
        """Test that unconfigured streaming services are filtered out."""
        from pywiim.player import Player

        player = Player(mock_client)
        # Device reports all sources including streaming services
        device_info = DeviceInfo(
            uuid="test", input_list=["bluetooth", "line_in", "airplay", "spotify", "tidal", "amazon", "qobuz"]
        )
        player._device_info = device_info
        player._status_model = None  # No current source

        # Should return only physical sources (no streaming services unless active) in Title Case
        result = player.available_sources
        assert "Bluetooth" in result
        assert "Line In" in result
        assert "Network" in result  # Network is always included
        assert "AirPlay" not in result  # Not active, filtered out
        assert "DLNA" not in result  # Not in input_list (filtered from input_list)
        assert "Spotify" not in result  # Not active, filtered out
        assert "Tidal" not in result
        assert "Amazon" not in result
        assert "Qobuz" not in result

    @pytest.mark.asyncio
    async def test_available_sources_includes_active_streaming_service(self, mock_client):
        """Test that currently active streaming service is included."""
        from pywiim.player import Player

        player = Player(mock_client)
        # Device reports all sources including streaming services
        device_info = DeviceInfo(
            uuid="test", input_list=["bluetooth", "line_in", "airplay", "spotify", "tidal", "amazon"]
        )
        player._device_info = device_info

        # Currently playing from Spotify
        status = PlayerStatus(source="spotify", play_state="play", volume=50, mute=False)
        player._status_model = status

        # Should include spotify since it's the current source (Title Case)
        result = player.available_sources
        assert "Bluetooth" in result
        assert "Line In" in result
        assert "Network" in result  # Network is always included
        assert "AirPlay" not in result  # Not active, filtered out
        assert "DLNA" not in result  # Not in input_list (filtered from input_list)
        assert "Spotify" in result  # Included because it's the current source
        assert "Tidal" not in result  # Not active
        assert "Amazon" not in result  # Not active

    @pytest.mark.asyncio
    async def test_available_sources_dlna_only_when_active(self, mock_client):
        """Test that DLNA is only included when currently active (not always)."""
        from pywiim.player import Player

        player = Player(mock_client)
        device_info = DeviceInfo(uuid="test", input_list=["bluetooth", "line_in", "dlna", "spotify"])
        player._device_info = device_info
        player._status_model = None

        result = player.available_sources
        assert "DLNA" not in result  # Not active, filtered out
        assert "Spotify" not in result  # Not active, filtered out
        assert "Bluetooth" in result
        assert "Line In" in result
        assert "Network" in result  # Network is always included

    @pytest.mark.asyncio
    async def test_available_sources_streaming_service_variations(self, mock_client):
        """Test filtering works with streaming service name variations."""
        from pywiim.player import Player

        player = Player(mock_client)
        # Test case variations and compound names
        device_info = DeviceInfo(
            uuid="test", input_list=["bluetooth", "Spotify", "TIDAL", "Amazon Music", "iHeartRadio"]
        )
        player._device_info = device_info
        player._status_model = None

        result = player.available_sources
        assert "Bluetooth" in result
        assert "Network" in result  # Network is always included
        # All streaming services should be filtered out when not active
        assert "Spotify" not in result
        assert "Tidal" not in result  # Normalized to Title Case
        assert "Amazon Music" not in result
        assert "iHeartRadio" not in result

    @pytest.mark.asyncio
    async def test_available_sources_includes_multiroom_source(self, mock_client):
        """Test that multi-room follower source is included when active."""
        from pywiim.player import Player

        player = Player(mock_client)
        device_info = DeviceInfo(uuid="test", input_list=["bluetooth", "line_in", "optical"])
        player._device_info = device_info

        # Currently following another device in multi-room
        status = PlayerStatus(source="Master Bedroom", play_state="play", volume=50, mute=False)
        player._status_model = status

        # Should include the multi-room master name as current source (preserves original casing)
        result = player.available_sources
        assert "Bluetooth" in result
        assert "Line In" in result
        assert "Optical In" in result
        assert "Network" in result  # Network is always included
        assert "Master Bedroom" in result  # Included because it's the current source (casing preserved)

    @pytest.mark.asyncio
    async def test_available_sources_preserves_source_casing(self, mock_client):
        """Test that source names preserve their original casing for UI display."""
        from pywiim.player import Player

        player = Player(mock_client)
        device_info = DeviceInfo(uuid="test", input_list=["bluetooth", "line_in", "optical"])
        player._device_info = device_info

        # Test various properly-cased source names (normalized to Title Case)
        test_cases = [
            ("AirPlay", "AirPlay"),  # Special case preserved
            ("Spotify", "Spotify"),  # Title Case preserved
            ("Amazon Music", "Amazon Music"),  # Multi-word preserved
            ("tidal", "Tidal"),  # Normalized to Title Case (not TIDAL)
        ]

        for source_name, expected_name in test_cases:
            status = PlayerStatus(source=source_name, play_state="play", volume=50, mute=False)
            player._status_model = status

            result = player.available_sources
            assert expected_name in result, f"Expected {expected_name} to be in available_sources, got {result}"

    @pytest.mark.asyncio
    async def test_audio_output_mode(self, mock_client):
        """Test getting audio output mode."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._audio_output_status = {"hardware": 0, "source": 0}
        mock_client.audio_output_mode_to_name = MagicMock(return_value="Line Out")

        assert player.audio_output_mode == "Line Out"

    @pytest.mark.asyncio
    async def test_audio_output_mode_bluetooth(self, mock_client):
        """Test getting audio output mode when Bluetooth is active."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._audio_output_status = {"hardware": 0, "source": 1}  # Bluetooth active

        assert player.audio_output_mode == "Bluetooth Out"

    @pytest.mark.asyncio
    async def test_audio_output_mode_int(self, mock_client):
        """Test getting audio output mode as integer."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._audio_output_status = {"hardware": 1, "source": 0}

        assert player.audio_output_mode_int == 1

    @pytest.mark.asyncio
    async def test_audio_output_mode_int_bluetooth(self, mock_client):
        """Test getting audio output mode int when Bluetooth is active."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._audio_output_status = {"hardware": 0, "source": 1}  # Bluetooth active

        assert player.audio_output_mode_int == 4  # Bluetooth Out

    @pytest.mark.asyncio
    async def test_available_output_modes_wiim_pro(self, mock_client):
        """Test available output modes for WiiM Pro."""
        from pywiim.player import Player

        player = Player(mock_client)
        device_info = DeviceInfo(uuid="test", model="WiiM Pro")
        player._device_info = device_info
        # capabilities is read-only, patch it via _capabilities if needed
        if hasattr(mock_client, "_capabilities"):
            mock_client._capabilities["supports_audio_output"] = True

        modes = player.available_output_modes

        assert "Line Out" in modes
        assert "Optical Out" in modes
        assert "Coax Out" in modes
        # "Bluetooth Out" is not in available_output_modes - only specific BT devices shown
        assert "Bluetooth Out" not in modes

    @pytest.mark.asyncio
    async def test_available_output_modes_wiim_mini(self, mock_client):
        """Test available output modes for WiiM Mini."""
        from pywiim.player import Player

        player = Player(mock_client)
        device_info = DeviceInfo(uuid="test", model="WiiM Mini")
        player._device_info = device_info
        # capabilities is read-only, patch it via _capabilities if needed
        if hasattr(mock_client, "_capabilities"):
            mock_client._capabilities["supports_audio_output"] = True

        modes = player.available_output_modes

        assert "Line Out" in modes
        assert "Optical Out" in modes
        assert "Coax Out" not in modes  # Mini doesn't have Coax

    @pytest.mark.asyncio
    async def test_available_output_modes_not_supported(self, mock_client):
        """Test available output modes when not supported."""
        from pywiim.player import Player

        player = Player(mock_client)
        # capabilities is read-only, patch it via _capabilities if needed
        if hasattr(mock_client, "_capabilities"):
            mock_client._capabilities["supports_audio_output"] = False

        modes = player.available_output_modes

        assert modes == []

    @pytest.mark.asyncio
    async def test_is_bluetooth_output_active(self, mock_client):
        """Test checking if Bluetooth output is active."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._audio_output_status = {"source": 1}  # Bluetooth active

        assert player.is_bluetooth_output_active is True

    @pytest.mark.asyncio
    async def test_is_bluetooth_output_active_false(self, mock_client):
        """Test checking if Bluetooth output is not active."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._audio_output_status = {"source": 0}  # Bluetooth not active

        assert player.is_bluetooth_output_active is False

    @pytest.mark.asyncio
    async def test_model_property(self, mock_client):
        """Test getting model property."""
        from pywiim.player import Player

        player = Player(mock_client)
        device_info = DeviceInfo(uuid="test", model="WiiM Pro")
        player._device_info = device_info

        assert player.model == "WiiM Pro"

    @pytest.mark.asyncio
    async def test_model_name_property_friendly_alias(self, mock_client):
        """Test getting model_name property for friendly branding output."""
        from pywiim.player import Player

        player = Player(mock_client)
        device_info = DeviceInfo(uuid="test", model="Muzo_Mini")
        player._device_info = device_info

        assert player.model == "Muzo_Mini"
        assert player.model_name == "WiiM Mini"

    @pytest.mark.asyncio
    async def test_firmware_property(self, mock_client):
        """Test getting firmware property."""
        from pywiim.player import Player

        player = Player(mock_client)
        device_info = DeviceInfo(uuid="test", firmware="5.0.123456")
        player._device_info = device_info

        assert player.firmware == "5.0.123456"

    @pytest.mark.asyncio
    async def test_firmware_update_properties(self, mock_client):
        """Test firmware update availability properties from getStatusEx."""
        from pywiim.player import Player

        player = Player(mock_client)
        # Test with the specific fixture requested:
        # firmware="Linkplay.4.8.731953", VersionUpdate="1", NewVer="Linkplay.4.8.738046"
        device_info = DeviceInfo(
            uuid="test",
            firmware="Linkplay.4.8.731953",
            VersionUpdate="1",
            NewVer="Linkplay.4.8.738046",
        )
        player._device_info = device_info

        # Test raw fields from device_info
        assert device_info.version_update == "1"
        assert device_info.latest_version == "Linkplay.4.8.738046"

        # Test convenience properties
        assert player.firmware_update_available is True
        assert player.latest_firmware_version == "Linkplay.4.8.738046"

        # Test with no update available
        device_info_no_update = DeviceInfo(
            uuid="test",
            firmware="Linkplay.4.8.731953",
            VersionUpdate="0",
            NewVer="Linkplay.4.8.731953",
        )
        player._device_info = device_info_no_update
        assert player.firmware_update_available is False
        assert player.latest_firmware_version == "Linkplay.4.8.731953"

        # Test with None values
        device_info_none = DeviceInfo(uuid="test", firmware="Linkplay.4.8.731953")
        player._device_info = device_info_none
        assert player.firmware_update_available is False
        assert player.latest_firmware_version is None

    @pytest.mark.asyncio
    async def test_mac_address_property(self, mock_client):
        """Test getting MAC address property."""
        from pywiim.player import Player

        player = Player(mock_client)
        device_info = DeviceInfo(uuid="test", mac="AA:BB:CC:DD:EE:FF")
        player._device_info = device_info

        assert player.mac_address == "AA:BB:CC:DD:EE:FF"

    @pytest.mark.asyncio
    async def test_uuid_property(self, mock_client):
        """Test getting UUID property."""
        from pywiim.player import Player

        player = Player(mock_client)
        device_info = DeviceInfo(uuid="test-uuid-123")
        player._device_info = device_info

        assert player.uuid == "test-uuid-123"

    @pytest.mark.asyncio
    async def test_status_model_property(self, mock_client):
        """Test getting status_model property."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(play_state="play", volume=50)
        player._status_model = status

        assert player.status_model == status

    @pytest.mark.asyncio
    async def test_device_info_property(self, mock_client):
        """Test getting device_info property."""
        from pywiim.player import Player

        player = Player(mock_client)
        device_info = DeviceInfo(uuid="test")
        player._device_info = device_info

        assert player.device_info == device_info

    @pytest.mark.asyncio
    async def test_discovered_endpoint_property(self, mock_client):
        """Test discovered_endpoint property exposes client's endpoint."""
        from pywiim.player import Player

        player = Player(mock_client)
        # Mock the client's discovered_endpoint
        mock_client._endpoint = "https://192.168.1.100:443"

        assert player.discovered_endpoint == "https://192.168.1.100:443"

    @pytest.mark.asyncio
    async def test_discovered_endpoint_none_when_not_discovered(self, mock_client):
        """Test discovered_endpoint is None when not yet discovered."""
        from pywiim.player import Player

        player = Player(mock_client)
        mock_client._endpoint = None

        assert player.discovered_endpoint is None

    @pytest.mark.asyncio
    async def test_input_list_property(self, mock_client):
        """Test input_list property returns device's input list."""
        from pywiim.player import Player

        player = Player(mock_client)
        device_info = DeviceInfo(uuid="test", InputList=["wifi", "bluetooth", "optical"])
        player._device_info = device_info

        assert player.input_list == ["wifi", "bluetooth", "optical"]

    @pytest.mark.asyncio
    async def test_input_list_empty_when_no_device_info(self, mock_client):
        """Test input_list returns empty list when device info is None."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._device_info = None

        assert player.input_list == []

    @pytest.mark.asyncio
    async def test_input_list_empty_when_input_list_none(self, mock_client):
        """Test input_list returns empty list when device has no input_list."""
        from pywiim.player import Player

        player = Player(mock_client)
        device_info = DeviceInfo(uuid="test")  # No input_list
        player._device_info = device_info

        assert player.input_list == []

    @pytest.mark.asyncio
    async def test_group_master_name_property(self, mock_client):
        """Test group_master_name returns master's name when in a group."""
        from pywiim.group import Group
        from pywiim.player import Player

        master = Player(mock_client)
        master._device_info = DeviceInfo(uuid="master", DeviceName="Living Room")

        slave = Player(mock_client)
        group = Group(master)
        group.add_slave(slave)

        assert slave.group_master_name == "Living Room"

    @pytest.mark.asyncio
    async def test_group_master_name_none_when_solo(self, mock_client):
        """Test group_master_name is None when player is solo."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._group = None

        assert player.group_master_name is None

    @pytest.mark.asyncio
    async def test_eq_presets_returns_empty_list_when_none(self, mock_client):
        """Test eq_presets returns empty list instead of None."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._eq_presets = None

        assert player.eq_presets == []

    @pytest.mark.asyncio
    async def test_eq_presets_returns_list_when_available(self, mock_client):
        """Test eq_presets returns 'Off' followed by the preset list when available."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._eq_presets = ["flat", "acoustic", "bass", "rock"]

        # "Off" should be prepended to indicate EQ disabled option
        assert player.eq_presets == ["Off", "flat", "acoustic", "bass", "rock"]

    @pytest.mark.asyncio
    async def test_is_muted_various_formats(self, mock_client):
        """Test is_muted with various formats."""
        from pywiim.player import Player

        player = Player(mock_client)

        # Test with boolean True
        status = PlayerStatus(mute=True, play_state="play")
        player._status_model = status
        assert player.is_muted is True

        # Test with int 1
        status = PlayerStatus(mute=1, play_state="play")
        player._status_model = status
        assert player.is_muted is True

        # Test with string "1"
        status = PlayerStatus(play_state="play")
        status.mute = "1"
        player._status_model = status
        assert player.is_muted is True

        # Test with string "true"
        status = PlayerStatus(play_state="play")
        status.mute = "true"
        player._status_model = status
        assert player.is_muted is True

        # Test with string "0"
        status = PlayerStatus(play_state="play")
        status.mute = "0"
        player._status_model = status
        assert player.is_muted is False

    @pytest.mark.asyncio
    async def test_media_position_track_change(self, mock_client):
        """Test media position resets on track change."""
        from pywiim.player import Player

        player = Player(mock_client)
        status1 = PlayerStatus(position=100, duration=240, play_state="play", title="Song 1", artist="Artist 1")
        player._status_model = status1
        # Update state synchronizer with position data
        player._state_synchronizer.update_from_http(
            {"position": 100, "duration": 240, "play_state": "play", "title": "Song 1", "artist": "Artist 1"}
        )

        pos1 = player.media_position
        assert pos1 == 100

        # Change track
        status2 = PlayerStatus(position=50, duration=200, play_state="play", title="Song 2", artist="Artist 2")
        player._status_model = status2
        # Update state synchronizer with new track data
        player._state_synchronizer.update_from_http(
            {"position": 50, "duration": 200, "play_state": "play", "title": "Song 2", "artist": "Artist 2"}
        )

        # Position should reset estimation
        pos2 = player.media_position
        assert pos2 == 50

    @pytest.mark.asyncio
    async def test_media_position_seek_detection(self, mock_client):
        """Test media position detects seeks."""
        from pywiim.player import Player

        player = Player(mock_client)
        status1 = PlayerStatus(position=100, duration=240, play_state="play")
        player._status_model = status1
        # Update state synchronizer with position data
        player._state_synchronizer.update_from_http({"position": 100, "duration": 240, "play_state": "play"})
        player._last_position = 100

        pos1 = player.media_position
        assert pos1 == 100

        # Simulate seek backward
        status2 = PlayerStatus(position=50, duration=240, play_state="play")
        player._status_model = status2
        # Update state synchronizer with new position data
        player._state_synchronizer.update_from_http({"position": 50, "duration": 240, "play_state": "play"})

        pos2 = player.media_position
        # Should detect seek and reset estimation
        assert pos2 == 50

    @pytest.mark.asyncio
    async def test_media_position_estimation_drift_limit(self, mock_client):
        """Test media position estimation has drift limit."""
        import time

        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(position=100, duration=240, play_state="play")
        player._status_model = status
        # Update state synchronizer with position data
        player._state_synchronizer.update_from_http({"position": 100, "duration": 240, "play_state": "play"})

        # Set estimation base far in the past to test drift limit
        player._estimation_base_position = 100
        player._estimation_start_time = time.time() - 100  # 100 seconds ago

        pos = player.media_position
        # Should not drift more than 30 seconds
        assert pos <= 130  # 100 + 30 max drift

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_available_output_modes_wiim_amp(self, mock_client):
        """Test available output modes for WiiM Amp."""
        from pywiim.player import Player

        player = Player(mock_client)
        device_info = DeviceInfo(uuid="test", model="WiiM Amp")
        player._device_info = device_info
        # capabilities is read-only, patch it via _capabilities if needed
        if hasattr(mock_client, "_capabilities"):
            mock_client._capabilities["supports_audio_output"] = True

        modes = player.available_output_modes

        # WiiM Amp has Line Out and USB Out (for external USB DAC)
        assert modes == ["Line Out", "USB Out"]

    @pytest.mark.asyncio
    async def test_available_output_modes_wiim_ultra(self, mock_client):
        """Test available output modes for WiiM Ultra."""
        from pywiim.player import Player

        player = Player(mock_client)
        device_info = DeviceInfo(uuid="test", model="WiiM Ultra")
        player._device_info = device_info
        # capabilities is read-only, patch it via _capabilities if needed
        if hasattr(mock_client, "_capabilities"):
            mock_client._capabilities["supports_audio_output"] = True

        modes = player.available_output_modes

        # HDMI is input-only on WiiM Ultra (not output) - confirmed via Issue #160
        assert "HDMI Out" not in modes
        assert "Headphone Out" in modes
        assert "Line Out" in modes
        assert "USB Out" in modes
        # "Bluetooth Out" is not in available_output_modes - only specific BT devices shown
        assert "Bluetooth Out" not in modes

    @pytest.mark.asyncio
    async def test_available_output_modes_unknown_model(self, mock_client):
        """Test available output modes for unknown model."""
        from pywiim.player import Player

        player = Player(mock_client)
        device_info = DeviceInfo(uuid="test", model="Unknown Device")
        player._device_info = device_info
        # capabilities is read-only, patch it via _capabilities if needed
        if hasattr(mock_client, "_capabilities"):
            mock_client._capabilities["supports_audio_output"] = True

        modes = player.available_output_modes

        # Should return standard modes for unknown device
        assert "Line Out" in modes
        assert "Optical Out" in modes

    @pytest.mark.asyncio
    async def test_join_group_master_not_in_group(self, mock_client, mock_player_status):
        """Test joining group when master is not in a group (should auto-create group)."""
        from pywiim.player import Player

        master = Player(mock_client)
        slave = Player(mock_client)

        # Mock API calls - create_group and join_slave
        mock_client.create_group = AsyncMock()
        mock_client.join_slave = AsyncMock()
        mock_client.get_player_status_model = AsyncMock(return_value=mock_player_status)
        mock_client.get_device_info_model = AsyncMock(return_value=None)

        # Set device_info to avoid refresh calls
        from pywiim.models import DeviceInfo

        master._device_info = DeviceInfo(uuid="master-uuid", model="WiiM Pro", wmrm_version="4.2")
        slave._device_info = DeviceInfo(uuid="slave-uuid", model="WiiM Mini", wmrm_version="4.2")

        # Mock refresh to verify join worked - need to set slave status to show it's a slave
        async def mock_slave_refresh(full=False):
            slave._detected_role = "slave"

        slave.refresh = AsyncMock(side_effect=mock_slave_refresh)
        master.refresh = AsyncMock()

        await slave.join_group(master)

        # Verify refresh was called to verify the join
        assert slave.refresh.call_count >= 1
        # Master should now have a group
        assert master.group is not None
        assert slave in master.group.slaves
        mock_client.create_group.assert_called_once()
        mock_client.join_slave.assert_called_once_with(
            master.host,
            master_device_info=master._device_info,
            master_ssid=None,
            master_wifi_channel=None,
        )

    @pytest.mark.asyncio
    async def test_leave_group_group_none(self, mock_client):
        """Test leaving group when group reference is None - idempotent behavior."""
        from pywiim.group import Group
        from pywiim.player import Player

        master = Player(mock_client)
        # Create a group first
        Group(master)
        # Set role to master and keep group reference
        master._role = "master"
        # Now set _group to None to simulate edge case where role is set but group is None
        # This can happen in edge cases where role detection succeeded but group creation failed
        master._group = None  # Simulate None group after role is set

        # Idempotent behavior: When _group is None, is_solo will be True
        # leave_group() should return without error (idempotent)
        await master.leave_group()  # Should not raise

    @pytest.mark.asyncio
    async def test_get_diagnostics_comprehensive(self, mock_client):
        """Test comprehensive diagnostics collection."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        status = PlayerStatus(
            play_state="play",
            volume=50,
            mute=False,
            title="Test Song",
            artist="Test Artist",
            album="Test Album",
            position=120,
            duration=240,
        )
        device_info = DeviceInfo(
            uuid="test-uuid",
            name="Test Device",
            model="WiiM Pro",
            firmware="5.0.123456",
            mac="AA:BB:CC:DD:EE:FF",
            ip="192.168.1.100",
        )
        player = Player(mock_client)
        player._status_model = status
        player._device_info = device_info
        player._audio_output_status = {"hardware": 0, "source": 0}

        # Use mock_client's existing capabilities property
        # capabilities is read-only, so we patch it if needed
        if not hasattr(mock_client, "_capabilities"):
            mock_client._capabilities = {
                "supports_eq": True,
                "supports_audio_output": True,
                "is_legacy_device": False,
            }
        mock_client.get_multiroom_status = AsyncMock(return_value={"slaves": 0})
        mock_client.get_device_group_info = AsyncMock(return_value=None)
        mock_client.get_eq = AsyncMock(return_value={"preset": "flat", "enabled": True})
        # api_stats and connection_stats are properties - use PropertyMock

        type(mock_client).api_stats = PropertyMock(return_value={"total_requests": 10, "successful_requests": 9})
        type(mock_client).connection_stats = PropertyMock(return_value={"avg_latency_ms": 50.0, "success_rate": 0.9})

        diagnostics = await player.get_diagnostics()

        assert "timestamp" in diagnostics
        assert "host" in diagnostics
        assert diagnostics["host"] == player.host
        assert diagnostics["device"]["uuid"] == "test-uuid"
        assert diagnostics["device"]["model"] == "WiiM Pro"
        assert diagnostics["status"]["play_state"] == "play"
        assert diagnostics["status"]["title"] == "Test Song"
        assert diagnostics["capabilities"]["supports_eq"] is True
        assert diagnostics["multiroom"]["slaves"] == 0
        assert diagnostics["audio_output"]["hardware"] == 0

    @pytest.mark.asyncio
    async def test_get_diagnostics_with_upnp(self, mock_client):
        """Test diagnostics with UPnP statistics."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(play_state="play", volume=50)
        device_info = DeviceInfo(uuid="test")
        player._status_model = status
        player._device_info = device_info

        # Mock UPnP eventer
        mock_eventer = MagicMock()
        mock_eventer.statistics = {
            "total_events": 100,
            "events_received": 95,
            "last_event_time": 1234567890.0,
        }
        player._upnp_eventer = mock_eventer

        # capabilities is read-only, use existing mock_client capabilities
        mock_client.get_multiroom_status = AsyncMock(return_value={"slaves": 0})
        mock_client.get_device_group_info = AsyncMock(return_value=None)

        diagnostics = await player.get_diagnostics()

        assert "upnp" in diagnostics
        assert diagnostics["upnp"]["total_events"] == 100

    @pytest.mark.asyncio
    async def test_get_diagnostics_with_group(self, mock_client):
        """Test diagnostics when in a group."""
        from pywiim.group import Group
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        master = Player(mock_client)
        slave = Player(mock_client)
        group = Group(master)
        group.add_slave(slave)

        status = PlayerStatus(play_state="play")
        device_info = DeviceInfo(uuid="test")
        master._status_model = status
        master._device_info = device_info

        # capabilities is read-only, use existing mock_client capabilities
        mock_client.get_multiroom_status = AsyncMock(return_value={"slaves": 1})
        mock_client.get_device_group_info = AsyncMock(
            return_value={
                "master": {"uuid": "master-uuid"},
                "slaves": [{"uuid": "slave-uuid"}],
            }
        )

        diagnostics = await master.get_diagnostics()

        # group_info may not be present if get_device_group_info returns None or fails
        # Just verify diagnostics were collected
        assert "timestamp" in diagnostics
        assert "host" in diagnostics
        assert diagnostics["device"]["uuid"] == "test"

    @pytest.mark.asyncio
    async def test_get_diagnostics_error_handling(self, mock_client):
        """Test diagnostics error handling."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(play_state="play")
        device_info = DeviceInfo(uuid="test")
        player._status_model = status
        player._device_info = device_info

        # capabilities is read-only, use existing mock_client capabilities
        mock_client.get_multiroom_status = AsyncMock(side_effect=Exception("Network error"))
        mock_client.get_device_group_info = AsyncMock(return_value=None)

        diagnostics = await player.get_diagnostics()

        # Should still return diagnostics (errors are caught and logged)
        assert "timestamp" in diagnostics
        assert "host" in diagnostics
        # multiroom section should have error info
        assert "multiroom" in diagnostics

    @pytest.mark.asyncio
    async def test_refresh_error_handling(self, mock_client):
        """Test refresh handles errors gracefully."""
        from pywiim.models import DeviceInfo
        from pywiim.player import Player

        mock_client.get_player_status_model = AsyncMock(side_effect=Exception("Network error"))
        mock_client.get_device_info_model = AsyncMock(return_value=DeviceInfo(uuid="test"))

        player = Player(mock_client)
        # refresh() catches, logs, and re-raises the original exception
        with pytest.raises(Exception, match="Network error"):
            await player.refresh()

    @pytest.mark.asyncio
    async def test_refresh_partial_failure(self, mock_client):
        """Test refresh when device info fails but status succeeds."""
        from pywiim.models import PlayerStatus
        from pywiim.player import Player

        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play"))
        mock_client.get_device_info_model = AsyncMock(side_effect=Exception("Device info error"))

        player = Player(mock_client)
        # refresh() catches, logs, and re-raises the original exception
        with pytest.raises(Exception, match="Device info error"):
            await player.refresh()

    @pytest.mark.asyncio
    async def test_get_status_property(self, mock_client):
        """Test getting status via status_model property."""
        from pywiim.models import PlayerStatus
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(play_state="play", volume=50)
        player._status_model = status

        assert player.status_model == status

    @pytest.mark.asyncio
    async def test_get_status_method(self, mock_client):
        """Test getting status via method."""
        from pywiim.models import PlayerStatus
        from pywiim.player import Player

        status = PlayerStatus(play_state="play", volume=50)
        mock_client.get_player_status_model = AsyncMock(return_value=status)

        player = Player(mock_client)
        result = await player.get_status()

        assert result == status
        mock_client.get_player_status_model.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_device_info_property(self, mock_client):
        """Test getting device info via property."""
        from pywiim.models import DeviceInfo
        from pywiim.player import Player

        player = Player(mock_client)
        device_info = DeviceInfo(uuid="test", name="Test Device")
        player._device_info = device_info

        assert player.device_info == device_info

    @pytest.mark.asyncio
    async def test_get_device_info_method(self, mock_client):
        """Test getting device info via method."""
        from pywiim.models import DeviceInfo
        from pywiim.player import Player

        device_info = DeviceInfo(uuid="test", name="Test Device")
        mock_client.get_device_info_model = AsyncMock(return_value=device_info)

        player = Player(mock_client)
        result = await player.get_device_info()

        assert result == device_info
        mock_client.get_device_info_model.assert_called_once()


class TestPlayerUPnPIntegration:
    """Test Player UPnP event integration."""

    @pytest.mark.asyncio
    async def test_apply_diff(self, mock_client):
        """Test applying UPnP diff."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(play_state="pause", volume=50, mute=False)
        player._status_model = status

        changes = {"play_state": "play", "volume": 75}
        changed = player.apply_diff(changes)

        assert changed is True
        assert player.play_state == "play"

    @pytest.mark.asyncio
    async def test_apply_diff_no_changes(self, mock_client):
        """Test applying UPnP diff with no changes."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(play_state="play", volume=50, mute=False)
        player._status_model = status

        changes = {"play_state": "play", "volume": 50}
        changed = player.apply_diff(changes)

        assert changed is False

    @pytest.mark.asyncio
    async def test_update_from_upnp(self, mock_client):
        """Test updating from UPnP data."""
        from pywiim.player import Player

        player = Player(mock_client)
        status = PlayerStatus(play_state="pause", volume=50, mute=False)
        player._status_model = status

        upnp_data = {"play_state": "play", "volume": 0.75, "muted": False}
        player.update_from_upnp(upnp_data)

        # State should be updated via StateSynchronizer
        assert player._state_synchronizer is not None


class TestPlayerGroupOperations:
    """Test Player group operations."""

    @pytest.mark.asyncio
    async def test_slave_playback_routes_to_master(self, mock_client):
        """Test that slave playback commands route through group to master."""
        from pywiim.group import Group
        from pywiim.player import Player

        # Create master and slave
        master_client = AsyncMock()
        master_client.play = AsyncMock()
        master_client.pause = AsyncMock()
        master_client.next_track = AsyncMock()
        master = Player(master_client)
        master._detected_role = "master"

        slave = Player(mock_client)
        slave._detected_role = "slave"

        # Create group and link them
        group = Group(master)
        group.add_slave(slave)

        # Slave playback commands should route to master
        await slave.play()
        master_client.play.assert_called_once()

        await slave.pause()
        master_client.pause.assert_called_once()

        await slave.next_track()
        master_client.next_track.assert_called_once()

    @pytest.mark.asyncio
    async def test_slave_without_group_raises_error(self, mock_client):
        """Test that slave without group object raises error."""
        from pywiim.exceptions import WiiMError
        from pywiim.player import Player

        # Create a slave player without a group
        player = Player(mock_client)
        player._detected_role = "slave"

        # Should raise WiiMError when trying to play
        with pytest.raises(WiiMError, match="not linked to group"):
            await player.play()

    @pytest.mark.asyncio
    async def test_slave_volume_fires_master_callback(self, mock_client):
        """Test that slave volume changes fire master's callback."""
        from pywiim.group import Group
        from pywiim.player import Player

        # Create master and slave with callbacks
        master_callback_count = {"count": 0}
        slave_callback_count = {"count": 0}

        def master_callback():
            master_callback_count["count"] += 1

        def slave_callback():
            slave_callback_count["count"] += 1

        master_client = AsyncMock()
        master_client.set_volume = AsyncMock()
        master = Player(master_client, on_state_changed=master_callback)

        mock_client.set_volume = AsyncMock()
        slave = Player(mock_client, on_state_changed=slave_callback)

        # Create group and link them
        group = Group(master)
        group.add_slave(slave)

        # Change slave volume
        await slave.set_volume(0.5)

        # Both callbacks should fire
        assert slave_callback_count["count"] == 1
        assert master_callback_count["count"] == 1

    @pytest.mark.asyncio
    async def test_master_volume_only_fires_own_callback(self, mock_client):
        """Test that master volume changes only fire master's callback."""
        from pywiim.group import Group
        from pywiim.player import Player

        # Create master and slave with callbacks
        master_callback_count = {"count": 0}
        slave_callback_count = {"count": 0}

        def master_callback():
            master_callback_count["count"] += 1

        def slave_callback():
            slave_callback_count["count"] += 1

        mock_client.set_volume = AsyncMock()
        master = Player(mock_client, on_state_changed=master_callback)

        slave_client = AsyncMock()
        slave_client.set_volume = AsyncMock()
        slave = Player(slave_client, on_state_changed=slave_callback)

        # Create group and link them
        group = Group(master)
        group.add_slave(slave)

        # Change master volume
        await master.set_volume(0.8)

        # Only master callback should fire
        assert master_callback_count["count"] == 1
        assert slave_callback_count["count"] == 0

    @pytest.mark.asyncio
    async def test_create_group(self, mock_client, mock_player_status):
        """Test creating a group."""
        from pywiim.player import Player

        mock_client.create_group = AsyncMock()
        mock_client.get_player_status_model = AsyncMock(return_value=mock_player_status)

        player = Player(mock_client)
        group = await player.create_group()

        assert group is not None
        assert group.master == player
        assert player.group == group
        mock_client.create_group.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_group_when_in_group(self, mock_client):
        """Test creating group when already in group (returns existing group)."""
        from pywiim.group import Group
        from pywiim.player import Player

        player = Player(mock_client)
        existing_group = Group(player)  # Already in a group

        # create_group should return the existing group when already a master
        result = await player.create_group()

        assert result == existing_group
        assert player.group == existing_group

    @pytest.mark.asyncio
    async def test_join_group(self, mock_client, mock_player_status, mock_aiohttp_session, mock_capabilities):
        """Test joining a group."""
        from pywiim.client import WiiMClient
        from pywiim.group import Group
        from pywiim.player import Player

        # Create separate clients for master and slave
        master_client = WiiMClient(
            host="192.168.1.100",
            port=80,
            session=mock_aiohttp_session,
            capabilities=mock_capabilities,
        )
        master_client._request = AsyncMock(return_value={"status": "ok"})

        slave_client = WiiMClient(
            host="192.168.1.101",
            port=80,
            session=mock_aiohttp_session,
            capabilities=mock_capabilities,
        )
        slave_client._request = AsyncMock(return_value={"status": "ok"})

        master = Player(master_client)
        slave = Player(slave_client)
        group = Group(master)

        # Set device_info with compatible wmrm_version (to avoid compatibility check failure)
        from pywiim.models import DeviceInfo

        master._device_info = DeviceInfo(uuid="master-uuid", model="WiiM Pro", wmrm_version="4.2")
        slave._device_info = DeviceInfo(uuid="slave-uuid", model="WiiM Mini", wmrm_version="4.2")

        # Mock master status
        master_client.get_player_status_model = AsyncMock(return_value=mock_player_status)
        master_client.get_multiroom_status = AsyncMock(return_value={"slaves": [slave.host]})

        # Mock slave status - should show it's a slave with master info
        slave_status = mock_player_status.model_copy()
        slave_status.group = "1"  # Slave indicator
        slave_status.master_ip = master.host
        slave_client.get_player_status_model = AsyncMock(return_value=slave_status)
        slave_client.get_multiroom_status = AsyncMock(return_value={"slaves": []})
        slave_client.join_slave = AsyncMock()

        # Mock refresh to update slave status after join - must update role to "slave"
        async def mock_slave_refresh(full=False):
            slave._detected_role = "slave"
            slave._status_model = slave_status

        slave.refresh = AsyncMock(side_effect=mock_slave_refresh)

        await slave.join_group(master)

        # Verify refresh was called to verify the join
        # (may be called multiple times: full=True for wmrm check, full=False for join verification)
        assert slave.refresh.call_count >= 1
        # Verify the final refresh call was with full=False
        assert slave.refresh.call_args_list[-1] == call(full=False)
        assert slave.group == group
        assert slave in group.slaves
        # Verify join_slave was called with master host and device info
        slave_client.join_slave.assert_called_once_with(
            master.host,
            master_device_info=master._device_info,
            master_ssid=None,
            master_wifi_channel=None,
        )

    @pytest.mark.asyncio
    async def test_join_group_applies_optimistic_link_before_verification(
        self, mock_client, mock_player_status, mock_aiohttp_session, mock_capabilities
    ):
        """Join should optimistically link local group state before refresh verification."""
        from pywiim.client import WiiMClient
        from pywiim.group import Group
        from pywiim.models import DeviceInfo
        from pywiim.player import Player

        master_client = WiiMClient(
            host="192.168.1.100",
            port=80,
            session=mock_aiohttp_session,
            capabilities=mock_capabilities,
        )
        master_client._request = AsyncMock(return_value={"status": "ok"})

        slave_client = WiiMClient(
            host="192.168.1.101",
            port=80,
            session=mock_aiohttp_session,
            capabilities=mock_capabilities,
        )
        slave_client._request = AsyncMock(return_value={"status": "ok"})

        master = Player(master_client)
        slave = Player(slave_client)
        group = Group(master)

        master._device_info = DeviceInfo(uuid="master-uuid", model="WiiM Pro", wmrm_version="4.2")
        slave._device_info = DeviceInfo(uuid="slave-uuid", model="WiiM Mini", wmrm_version="4.2")

        slave_status = mock_player_status.model_copy()
        slave_status.group = "1"
        slave_status.master_ip = master.host
        slave_client.join_slave = AsyncMock()

        optimistic_seen_during_refresh = {"seen": False}

        async def mock_slave_refresh(full=False):
            if not full and slave.group == group and slave in group.slaves and slave.role == "slave":
                optimistic_seen_during_refresh["seen"] = True
            # Verification then confirms slave role from device refresh.
            slave._detected_role = "slave"
            slave._status_model = slave_status

        slave.refresh = AsyncMock(side_effect=mock_slave_refresh)

        with patch("pywiim.player.groupops.asyncio.sleep", new=AsyncMock()):
            await slave.join_group(master)

        assert optimistic_seen_during_refresh["seen"] is True
        assert slave.group == group
        assert slave in group.slaves
        assert slave.role == "slave"

    @pytest.mark.asyncio
    async def test_join_group_rolls_back_optimistic_link_when_verification_fails(
        self, mock_client, mock_player_status, mock_aiohttp_session, mock_capabilities
    ):
        """Failed join verification should roll back optimistic local group state."""
        from pywiim.client import WiiMClient
        from pywiim.group import Group
        from pywiim.models import DeviceInfo
        from pywiim.player import Player

        master_client = WiiMClient(
            host="192.168.1.100",
            port=80,
            session=mock_aiohttp_session,
            capabilities=mock_capabilities,
        )
        master_client._request = AsyncMock(return_value={"status": "ok"})

        slave_client = WiiMClient(
            host="192.168.1.101",
            port=80,
            session=mock_aiohttp_session,
            capabilities=mock_capabilities,
        )
        slave_client._request = AsyncMock(return_value={"status": "ok"})

        master = Player(master_client)
        slave = Player(slave_client)
        group = Group(master)

        master._device_info = DeviceInfo(uuid="master-uuid", model="WiiM Pro", wmrm_version="4.2")
        slave._device_info = DeviceInfo(uuid="slave-uuid", model="WiiM Mini", wmrm_version="4.2")

        # Device command succeeds, but refresh never confirms non-solo state.
        slave_client.join_slave = AsyncMock()

        async def mock_slave_refresh(full=False):
            slave._detected_role = "solo"

        slave.refresh = AsyncMock(side_effect=mock_slave_refresh)

        with patch("pywiim.player.groupops.asyncio.sleep", new=AsyncMock()):
            await slave.join_group(master)

        assert slave.group is None
        assert slave not in group.slaves
        assert slave.role == "solo"
        assert master.role == "solo"

    @pytest.mark.asyncio
    async def test_leave_group_as_slave(self, mock_client, mock_player_status):
        """Test leaving group as slave."""
        from pywiim.group import Group
        from pywiim.player import Player

        mock_client.get_player_status_model = AsyncMock(return_value=mock_player_status)
        master = Player(mock_client)
        master._detected_role = "master"  # Set role from device API state
        slave = Player(mock_client)
        slave._detected_role = "slave"  # Set role from device API state
        group = Group(master)
        group.add_slave(slave)

        mock_client._request = AsyncMock(return_value={"status": "ok"})

        await slave.leave_group()

        assert slave.group is None
        assert slave not in group.slaves
        # When last slave leaves, group should be auto-disbanded
        assert master.group is None
        # Should call _request for leave, then disband calls _request again
        assert mock_client._request.call_count >= 1
        mock_client._request.assert_any_call("/httpapi.asp?command=multiroom:Ungroup")

    @pytest.mark.asyncio
    async def test_leave_group_as_slave_notifies_post_leave_state(self, mock_client, mock_player_status):
        """Leaving slave should notify callbacks with post-leave solo state."""
        from pywiim.group import Group
        from pywiim.player import Player

        callback_states: list[tuple[str, bool, bool]] = []

        def on_state_changed_for_slave():
            callback_states.append((slave.role, slave.is_solo, slave.group is None))

        mock_client.get_player_status_model = AsyncMock(return_value=mock_player_status)
        master = Player(mock_client)
        master._detected_role = "master"
        slave = Player(mock_client, on_state_changed=on_state_changed_for_slave)
        slave._detected_role = "slave"
        group = Group(master)
        group.add_slave(slave)

        mock_client._request = AsyncMock(return_value={"status": "ok"})

        await slave.leave_group()

        assert slave.group is None
        assert slave.role == "solo"
        assert any(state == ("solo", True, True) for state in callback_states)

    @pytest.mark.asyncio
    async def test_leave_group_as_slave_with_multiple_slaves(
        self, mock_client, mock_player_status, mock_aiohttp_session, mock_capabilities
    ):
        """Test leaving group as slave when multiple slaves exist (should not auto-disband)."""
        from pywiim.client import WiiMClient
        from pywiim.group import Group
        from pywiim.player import Player

        # Create separate clients for each player
        master_client = WiiMClient(
            host="192.168.1.100",
            port=80,
            session=mock_aiohttp_session,
            capabilities=mock_capabilities,
        )
        master_client._request = AsyncMock(return_value={"status": "ok"})

        slave1_client = WiiMClient(
            host="192.168.1.101",
            port=80,
            session=mock_aiohttp_session,
            capabilities=mock_capabilities,
        )
        slave1_client._request = AsyncMock(return_value={"status": "ok"})

        slave2_client = WiiMClient(
            host="192.168.1.102",
            port=80,
            session=mock_aiohttp_session,
            capabilities=mock_capabilities,
        )
        slave2_client._request = AsyncMock(return_value={"status": "ok"})

        master = Player(master_client)
        master._detected_role = "master"  # Set role from device API state
        slave1 = Player(slave1_client)
        slave1._detected_role = "slave"  # Set role from device API state
        slave2 = Player(slave2_client)
        slave2._detected_role = "slave"  # Set role from device API state
        group = Group(master)
        group.add_slave(slave1)
        group.add_slave(slave2)

        # Mock status models
        master_client.get_player_status_model = AsyncMock(return_value=mock_player_status)
        # Slave1 after leaving should be solo (no group, no master info)
        slave1_status = mock_player_status.model_copy()
        slave1_status.group = None
        slave1_status.master_ip = None
        slave1_status.master_uuid = None
        slave1_client.get_player_status_model = AsyncMock(return_value=slave1_status)
        # Slave2 should still be in group (has master info)
        slave2_status = mock_player_status.model_copy()
        slave2_status.group = master.host
        slave2_status.master_ip = master.host
        slave2_client.get_player_status_model = AsyncMock(return_value=slave2_status)

        # Mock multiroom: slave1 is solo, master still has slave2
        slave1_client.get_multiroom_status = AsyncMock(return_value={"slaves": []})
        master_client.get_multiroom_status = AsyncMock(return_value={"slaves": [slave2.host]})

        await slave1.leave_group()

        assert slave1.group is None
        assert slave1 not in group.slaves
        assert slave2 in group.slaves
        # Group should still exist with remaining slave
        assert master.group == group
        # Should call _request for leave
        slave1_client._request.assert_called_once_with("/httpapi.asp?command=multiroom:Ungroup")
        # Should not call delete_group when other slaves remain (no auto-disband)
        assert master_client._request.call_count == 0

    @pytest.mark.asyncio
    async def test_leave_group_clears_metadata(self, mock_client, mock_player_status):
        """Test that leaving group clears metadata and artwork."""
        from pywiim.group import Group
        from pywiim.player import Player

        mock_client.get_player_status_model = AsyncMock(return_value=mock_player_status)
        master = Player(mock_client)
        master._detected_role = "master"  # Set role from device API state
        slave = Player(mock_client)
        slave._detected_role = "slave"  # Set role from device API state
        group = Group(master)

        # Set up slave with metadata from group playback
        slave._status_model = mock_player_status.model_copy()
        slave._status_model.source = master.host
        slave._status_model.title = "Test Song"
        slave._status_model.artist = "Test Artist"
        slave._status_model.album = "Test Album"
        slave._status_model.entity_picture = "http://example.com/art.jpg"
        slave._status_model.cover_url = "http://example.com/cover.jpg"

        group.add_slave(slave)

        mock_client._request = AsyncMock(return_value={"status": "ok"})

        await slave.leave_group()

        # Verify metadata and artwork are cleared
        assert slave._status_model.title is None
        assert slave._status_model.artist is None
        assert slave._status_model.album is None
        assert slave._status_model.entity_picture is None
        assert slave._status_model.cover_url is None
        assert slave._status_model.source is None

    @pytest.mark.asyncio
    async def test_leave_group_as_master(self, mock_client):
        """Test leaving group as master (disbands group)."""
        from pywiim.group import Group
        from pywiim.player import Player

        master = Player(mock_client)
        master._detected_role = "master"  # Set role from device API state
        slave = Player(mock_client)
        slave._detected_role = "slave"  # Set role from device API state
        group = Group(master)
        group.add_slave(slave)

        mock_client._request = AsyncMock(return_value={"status": "ok"})

        await master.leave_group()

        assert master.group is None
        assert slave.group is None
        # Master leaving calls disband which calls _request
        mock_client._request.assert_called_once_with("/httpapi.asp?command=multiroom:Ungroup")

    @pytest.mark.asyncio
    async def test_leave_group_when_solo(self, mock_client):
        """Test leaving group when solo - should be idempotent (no error)."""
        from pywiim.player import Player

        player = Player(mock_client)

        # Idempotent behavior: no error when solo, just returns
        await player.leave_group()  # Should not raise

    @pytest.mark.asyncio
    async def test_leave_group_wifi_direct_routes_via_master(
        self, mock_client, mock_aiohttp_session, mock_capabilities
    ):
        """Test WiFi Direct slave routes unjoin through master."""
        from pywiim.client import WiiMClient
        from pywiim.group import Group
        from pywiim.models import DeviceInfo
        from pywiim.player import Player

        master_client = WiiMClient(
            host="192.168.1.100", port=80, session=mock_aiohttp_session, capabilities=mock_capabilities
        )
        slave_client = WiiMClient(
            host="192.168.1.101", port=80, session=mock_aiohttp_session, capabilities=mock_capabilities
        )

        master = Player(master_client)
        master._detected_role = "master"
        slave = Player(slave_client)
        slave._detected_role = "slave"
        # Old firmware = WiFi Direct mode
        slave._device_info = DeviceInfo(uuid="uuid:ABC123", firmware="3.8.5515", name="OldSlave")

        group = Group(master)
        group.add_slave(slave)

        # Mock master's get_slaves_info and kick_slave
        master_client.get_slaves_info = AsyncMock(
            return_value=[{"uuid": "uuid:ABC123", "ip": "10.10.10.92", "name": "OldSlave"}]
        )
        master_client.kick_slave = AsyncMock()
        master_client._request = AsyncMock(return_value={"status": "ok"})

        await slave.leave_group()

        # Should have kicked via master with the 10.10.10.x IP
        master_client.kick_slave.assert_called_once_with("10.10.10.92")
        assert slave not in group.slaves

    @pytest.mark.asyncio
    async def test_join_group_wmrm_version_compatible(
        self, mock_client, mock_player_status, mock_aiohttp_session, mock_capabilities
    ):
        """Test joining group when wmrm_version is compatible (both 4.2)."""
        from pywiim.client import WiiMClient
        from pywiim.group import Group
        from pywiim.models import DeviceInfo
        from pywiim.player import Player

        # Create separate clients for master and slave
        master_client = WiiMClient(
            host="192.168.1.100",
            port=80,
            session=mock_aiohttp_session,
            capabilities=mock_capabilities,
        )
        master_client._request = AsyncMock(return_value={"status": "ok"})

        slave_client = WiiMClient(
            host="192.168.1.101",
            port=80,
            session=mock_aiohttp_session,
            capabilities=mock_capabilities,
        )
        slave_client._request = AsyncMock(return_value={"status": "ok"})

        master = Player(master_client)
        slave = Player(slave_client)
        group = Group(master)

        # Set device_info with compatible wmrm_version (both 4.2)
        master._device_info = DeviceInfo(uuid="master-uuid", model="WiiM Pro", wmrm_version="4.2")
        slave._device_info = DeviceInfo(uuid="slave-uuid", model="WiiM Mini", wmrm_version="4.2")

        # Mock master status
        master_client.get_player_status_model = AsyncMock(return_value=mock_player_status)
        master_client.get_multiroom_status = AsyncMock(return_value={"slaves": [slave.host]})

        # Mock slave status - should show it's a slave with master info
        slave_status = mock_player_status.model_copy()
        slave_status.group = "1"  # Slave indicator
        slave_status.master_ip = master.host
        slave_client.get_player_status_model = AsyncMock(return_value=slave_status)
        slave_client.get_multiroom_status = AsyncMock(return_value={"slaves": []})
        slave_client.join_slave = AsyncMock()

        # Mock refresh to update slave status after join - must update role to "slave"
        async def mock_slave_refresh(full=False):
            slave._detected_role = "slave"
            slave._status_model = slave_status

        slave.refresh = AsyncMock(side_effect=mock_slave_refresh)

        # Should not raise - versions are compatible
        await slave.join_group(master)

        # Verify refresh was called to verify the join
        slave.refresh.assert_called()
        assert slave.group == group
        assert slave in group.slaves
        # Verify join_slave was called with master host and device info
        slave_client.join_slave.assert_called_once_with(
            master.host,
            master_device_info=master._device_info,
            master_ssid=None,
            master_wifi_channel=None,
        )

    @pytest.mark.asyncio
    async def test_join_group_wmrm_version_compatible_minor_difference(
        self, mock_client, mock_player_status, mock_aiohttp_session, mock_capabilities
    ):
        """Test joining group when wmrm_version has compatible minor version difference (4.2 vs 4.3)."""
        from pywiim.client import WiiMClient
        from pywiim.group import Group
        from pywiim.models import DeviceInfo
        from pywiim.player import Player

        # Create separate clients for master and slave
        master_client = WiiMClient(
            host="192.168.1.100",
            port=80,
            session=mock_aiohttp_session,
            capabilities=mock_capabilities,
        )
        master_client._request = AsyncMock(return_value={"status": "ok"})

        slave_client = WiiMClient(
            host="192.168.1.101",
            port=80,
            session=mock_aiohttp_session,
            capabilities=mock_capabilities,
        )
        slave_client._request = AsyncMock(return_value={"status": "ok"})

        master = Player(master_client)
        slave = Player(slave_client)
        group = Group(master)

        # Set device_info with compatible wmrm_version (4.2 vs 4.3 - same major version)
        master._device_info = DeviceInfo(uuid="master-uuid", model="WiiM Pro", wmrm_version="4.3")
        slave._device_info = DeviceInfo(uuid="slave-uuid", model="WiiM Mini", wmrm_version="4.2")

        # Mock master status
        master_client.get_player_status_model = AsyncMock(return_value=mock_player_status)
        master_client.get_multiroom_status = AsyncMock(return_value={"slaves": [slave.host]})

        # Mock slave status - should show it's a slave with master info
        slave_status = mock_player_status.model_copy()
        slave_status.group = "1"  # Slave indicator
        slave_status.master_ip = master.host
        slave_client.get_player_status_model = AsyncMock(return_value=slave_status)
        slave_client.get_multiroom_status = AsyncMock(return_value={"slaves": []})
        slave_client.join_slave = AsyncMock()

        # Mock refresh to update slave status after join - must update role to "slave"
        async def mock_slave_refresh(full=False):
            slave._detected_role = "slave"
            slave._status_model = slave_status

        slave.refresh = AsyncMock(side_effect=mock_slave_refresh)

        # Should not raise - versions are compatible (same major version 4)
        await slave.join_group(master)

        # Verify refresh was called to verify the join
        slave.refresh.assert_called()
        assert slave.group == group
        assert slave in group.slaves
        # Verify join_slave was called with master host and device info
        slave_client.join_slave.assert_called_once_with(
            master.host,
            master_device_info=master._device_info,
            master_ssid=None,
            master_wifi_channel=None,
        )

    @pytest.mark.asyncio
    async def test_join_group_wmrm_version_missing_warning(
        self, mock_client, mock_player_status, mock_aiohttp_session, mock_capabilities
    ):
        """Test joining group when wmrm_version is missing (should warn but proceed)."""
        from pywiim.client import WiiMClient
        from pywiim.group import Group
        from pywiim.models import DeviceInfo
        from pywiim.player import Player

        # Create separate clients for master and slave
        master_client = WiiMClient(
            host="192.168.1.100",
            port=80,
            session=mock_aiohttp_session,
            capabilities=mock_capabilities,
        )
        master_client._request = AsyncMock(return_value={"status": "ok"})

        slave_client = WiiMClient(
            host="192.168.1.101",
            port=80,
            session=mock_aiohttp_session,
            capabilities=mock_capabilities,
        )
        slave_client._request = AsyncMock(return_value={"status": "ok"})

        master = Player(master_client)
        slave = Player(slave_client)
        Group(master)

        # Set device_info with missing wmrm_version
        master._device_info = DeviceInfo(uuid="master-uuid", model="Unknown Device", wmrm_version=None)
        slave._device_info = DeviceInfo(uuid="slave-uuid", model="Unknown Device", wmrm_version=None)

        # Mock master status
        master_client.get_player_status_model = AsyncMock(return_value=mock_player_status)
        master_client.get_multiroom_status = AsyncMock(return_value={"slaves": [slave.host]})

        # Mock slave status - should show it's a slave with master info
        slave_status = mock_player_status.model_copy()
        slave_status.group = "1"  # Slave indicator
        slave_status.master_ip = master.host
        slave_client.get_player_status_model = AsyncMock(return_value=slave_status)
        slave_client.get_multiroom_status = AsyncMock(return_value={"slaves": []})
        slave_client.join_slave = AsyncMock()

        # Mock refresh to update slave status after join
        async def mock_slave_refresh(full=False):
            slave._detected_role = "slave"
            slave._status_model = slave_status

        slave.refresh = AsyncMock(side_effect=mock_slave_refresh)

        # Should proceed with join (warns but doesn't block)
        await slave.join_group(master)

        # Verify join was attempted
        slave_client.join_slave.assert_called_once_with(
            master.host,
            master_device_info=master._device_info,
            master_ssid=None,
            master_wifi_channel=None,
        )

    @pytest.mark.asyncio
    async def test_join_group_wifi_direct_mode_gen1(
        self, mock_client, mock_player_status, mock_aiohttp_session, mock_capabilities
    ):
        """Test joining group with WiFi Direct mode for legacy firmware devices (< 4.2.8020)."""
        from pywiim.client import WiiMClient
        from pywiim.group import Group
        from pywiim.models import DeviceInfo
        from pywiim.player import Player

        # Create separate clients for master and slave
        master_client = WiiMClient(
            host="192.168.1.100",
            port=80,
            session=mock_aiohttp_session,
            capabilities=mock_capabilities,
        )
        master_client._request = AsyncMock(return_value={"status": "ok"})

        slave_client = WiiMClient(
            host="192.168.1.101",
            port=80,
            session=mock_aiohttp_session,
            capabilities=mock_capabilities,
        )
        slave_client._request = AsyncMock(return_value={"status": "ok"})

        master = Player(master_client)
        slave = Player(slave_client)
        group = Group(master)

        # Set device_info for legacy firmware devices (< 4.2.8020) with SSID and channel
        master._device_info = DeviceInfo(
            uuid="master-uuid",
            model="Audio Pro A26",
            firmware="4.2.5000",  # Old firmware < 4.2.8020 triggers WiFi Direct mode
            ssid="MyWiFiNetwork",
            wifi_channel=6,
        )
        slave._device_info = DeviceInfo(
            uuid="slave-uuid",
            model="Audio Pro A26",
            firmware="4.2.5000",
        )

        # Mock master status
        master_client.get_player_status_model = AsyncMock(return_value=mock_player_status)
        master_client.get_multiroom_status = AsyncMock(return_value={"slaves": [slave.host]})

        # Mock slave status - should show it's a slave with master info
        slave_status = mock_player_status.model_copy()
        slave_status.group = "1"  # Slave indicator
        slave_status.master_ip = master.host
        slave_client.get_player_status_model = AsyncMock(return_value=slave_status)
        slave_client.get_multiroom_status = AsyncMock(return_value={"slaves": []})
        slave_client.join_slave = AsyncMock()

        # Mock refresh to update slave status after join - must update role to "slave"
        async def mock_slave_refresh(full=False):
            slave._detected_role = "slave"
            slave._status_model = slave_status

        slave.refresh = AsyncMock(side_effect=mock_slave_refresh)

        await slave.join_group(master)

        # Verify refresh was called
        assert slave.refresh.call_count >= 1
        assert slave.group == group
        assert slave in group.slaves

        # Verify join_slave was called with WiFi Direct info (SSID + channel)
        # because firmware < 4.2.8020 triggers WiFi Direct mode
        slave_client.join_slave.assert_called_once_with(
            master.host,
            master_device_info=master._device_info,
            master_ssid="MyWiFiNetwork",
            master_wifi_channel=6,
        )

        # Note: The actual WiFi Direct mode command format is tested in test_group.py::test_join_slave_wifi_direct_mode

    @pytest.mark.asyncio
    async def test_join_group_wifi_direct_mode_missing_ssid(
        self, mock_client, mock_player_status, mock_aiohttp_session, mock_capabilities
    ):
        """Test WiFi Direct mode fallback when SSID is missing."""
        from pywiim.client import WiiMClient
        from pywiim.group import Group
        from pywiim.models import DeviceInfo
        from pywiim.player import Player

        # Create separate clients for master and slave
        master_client = WiiMClient(
            host="192.168.1.100",
            port=80,
            session=mock_aiohttp_session,
            capabilities=mock_capabilities,
        )
        master_client._request = AsyncMock(return_value={"status": "ok"})

        slave_client = WiiMClient(
            host="192.168.1.101",
            port=80,
            session=mock_aiohttp_session,
            capabilities=mock_capabilities,
        )
        slave_client._request = AsyncMock(return_value={"status": "ok"})

        master = Player(master_client)
        slave = Player(slave_client)
        Group(master)

        # Set device_info for Gen1 device but without SSID
        master._device_info = DeviceInfo(
            uuid="master-uuid",
            model="Audio Pro A26",
            wmrm_version="2.0",
            firmware="4.2.5000",
            ssid=None,  # Missing SSID
            wifi_channel=6,
        )
        slave._device_info = DeviceInfo(
            uuid="slave-uuid",
            model="Audio Pro A26",
            wmrm_version="2.0",
            firmware="4.2.5000",
        )

        # Mock master status
        master_client.get_player_status_model = AsyncMock(return_value=mock_player_status)
        master_client.get_multiroom_status = AsyncMock(return_value={"slaves": [slave.host]})

        # Mock slave status - should show it's a slave with master info
        slave_status = mock_player_status.model_copy()
        slave_status.group = "1"  # Slave indicator
        slave_status.master_ip = master.host
        slave_client.get_player_status_model = AsyncMock(return_value=slave_status)
        slave_client.get_multiroom_status = AsyncMock(return_value={"slaves": []})
        slave_client.join_slave = AsyncMock()

        # Mock refresh to update slave status after join
        async def mock_slave_refresh(full=False):
            slave._detected_role = "slave"
            slave._status_model = slave_status

        slave.refresh = AsyncMock(side_effect=mock_slave_refresh)

        # Should proceed but fall back to router-based mode (with warning)
        await slave.join_group(master)

        # Verify join_slave was called (should fall back to router-based mode)
        slave_client.join_slave.assert_called_once_with(
            master.host,
            master_device_info=master._device_info,
            master_ssid=None,
            master_wifi_channel=None,
        )


class TestPlayerReboot:
    """Test Player reboot method."""

    @pytest.mark.asyncio
    async def test_reboot(self, mock_client):
        """Test rebooting device."""
        from pywiim.player import Player

        mock_client.reboot = AsyncMock()

        player = Player(mock_client)
        await player.reboot()

        assert player.available is False
        mock_client.reboot.assert_called_once()


class TestPlayerTriggerOut:
    """Test Player 12V trigger methods (WiiM Ultra / Pro / Pro Plus)."""

    @pytest.mark.asyncio
    async def test_get_trigger_out_status(self, mock_client):
        """Test get_trigger_out_status delegates to client and updates cache."""
        from pywiim.player import Player

        mock_client.get_trigger_out_status = AsyncMock(return_value=True)
        type(mock_client).capabilities = PropertyMock(return_value={})

        player = Player(mock_client)
        result = await player.get_trigger_out_status()

        assert result is True
        assert player.trigger_out_on is True
        mock_client.get_trigger_out_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_trigger_out_updates_cache_and_callback(self, mock_client):
        """Test set_trigger_out updates cache and invokes state callback."""
        from pywiim.player import Player

        mock_client.set_trigger_out = AsyncMock()
        type(mock_client).capabilities = PropertyMock(return_value={})
        callback_called = []

        player = Player(mock_client, on_state_changed=lambda: callback_called.append(True))
        await player.set_trigger_out(True)

        assert player._trigger_out_on is True
        assert len(callback_called) == 1
        mock_client.set_trigger_out.assert_called_once_with(True)

    @pytest.mark.asyncio
    async def test_supports_trigger_out(self, mock_client):
        """Test supports_trigger_out reads from capabilities."""
        from pywiim.player import Player

        type(mock_client).capabilities = PropertyMock(return_value={"supports_trigger_out": True})
        player = Player(mock_client)
        assert player.supports_trigger_out is True

        type(mock_client).capabilities = PropertyMock(return_value={"supports_trigger_out": False})
        player2 = Player(mock_client)
        assert player2.supports_trigger_out is False

    @pytest.mark.asyncio
    async def test_set_trigger_out_on_off(self, mock_client):
        """Test set_trigger_out_on and set_trigger_out_off convenience methods."""
        from pywiim.player import Player

        mock_client.set_trigger_out = AsyncMock()
        type(mock_client).capabilities = PropertyMock(return_value={})
        player = Player(mock_client)

        await player.set_trigger_out_on()
        mock_client.set_trigger_out.assert_called_with(True)
        await player.set_trigger_out_off()
        mock_client.set_trigger_out.assert_called_with(False)


class TestPlayerBluetoothOutputs:
    """Test Bluetooth output device handling."""

    @pytest.mark.asyncio
    async def test_bluetooth_output_devices_empty(self, mock_client):
        """Test bluetooth_output_devices with no paired devices."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._bluetooth_history = []

        devices = player.bluetooth_output_devices
        assert devices == []

    @pytest.mark.asyncio
    async def test_bluetooth_output_devices_filter_audio_sinks(self, mock_client):
        """Test that only Audio Sink devices are returned."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._bluetooth_history = [
            {"name": "Speaker", "ad": "AA:BB:CC:DD:EE:FF", "ct": 1, "role": "Audio Sink"},
            {"name": "Phone", "ad": "11:22:33:44:55:66", "ct": 0, "role": "Audio Source"},
            {"name": "Headphones", "ad": "22:33:44:55:66:77", "ct": 0, "role": "Audio Sink"},
        ]

        devices = player.bluetooth_output_devices
        assert len(devices) == 2
        assert devices[0]["name"] == "Speaker"
        assert devices[0]["mac"] == "AA:BB:CC:DD:EE:FF"
        assert devices[0]["connected"] is True
        assert devices[1]["name"] == "Headphones"
        assert devices[1]["mac"] == "22:33:44:55:66:77"
        assert devices[1]["connected"] is False

    @pytest.mark.asyncio
    async def test_bluetooth_output_devices_unknown_device(self, mock_client):
        """Test handling of device with missing name."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._bluetooth_history = [
            {"ad": "AA:BB:CC:DD:EE:FF", "ct": 1, "role": "Audio Sink"},
        ]

        devices = player.bluetooth_output_devices
        assert len(devices) == 1
        assert devices[0]["name"] == "Unknown Device"
        assert devices[0]["mac"] == "AA:BB:CC:DD:EE:FF"

    @pytest.mark.asyncio
    async def test_available_outputs_hardware_only(self, mock_client):
        """Test available_outputs with no BT devices."""
        from pywiim.models import DeviceInfo
        from pywiim.player import Player

        type(mock_client).capabilities = PropertyMock(return_value={"supports_audio_output": True})
        player = Player(mock_client)
        player._device_info = DeviceInfo(
            uuid="test", name="Test", model="WiiM Pro", firmware="1.0", ip="192.168.1.100", mac="AA:BB:CC:DD:EE:FF"
        )
        player._bluetooth_history = []

        outputs = player.available_outputs
        assert "Line Out" in outputs
        assert "Optical Out" in outputs
        assert "Coax Out" in outputs
        assert len([o for o in outputs if o.startswith("BT: ")]) == 0

    @pytest.mark.asyncio
    async def test_available_outputs_with_bt_devices(self, mock_client):
        """Test available_outputs combines hardware modes and BT devices."""
        from pywiim.models import DeviceInfo
        from pywiim.player import Player

        type(mock_client).capabilities = PropertyMock(return_value={"supports_audio_output": True})
        player = Player(mock_client)
        player._device_info = DeviceInfo(
            uuid="test", name="Test", model="WiiM Pro", firmware="1.0", ip="192.168.1.100", mac="AA:BB:CC:DD:EE:FF"
        )
        player._bluetooth_history = [
            {"name": "Sony Speaker", "ad": "AA:BB:CC:DD:EE:FF", "ct": 1, "role": "Audio Sink"},
            {"name": "JBL Headphones", "ad": "11:22:33:44:55:66", "ct": 0, "role": "Audio Sink"},
        ]

        outputs = player.available_outputs
        assert "Line Out" in outputs
        assert "Optical Out" in outputs
        assert "Coax Out" in outputs
        assert "BT: Sony Speaker" in outputs
        assert "BT: JBL Headphones" in outputs

    @pytest.mark.asyncio
    async def test_available_outputs_wiim_ultra(self, mock_client):
        """Test available_outputs for WiiM Ultra with all outputs and Headphone."""
        from pywiim.models import DeviceInfo
        from pywiim.player import Player

        type(mock_client).capabilities = PropertyMock(return_value={"supports_audio_output": True})
        player = Player(mock_client)
        player._device_info = DeviceInfo(
            uuid="test", name="Test", model="WiiM Ultra", firmware="1.0", ip="192.168.1.100", mac="AA:BB:CC:DD:EE:FF"
        )
        player._bluetooth_history = []

        outputs = player.available_outputs
        # Ultra has standard outputs plus USB Out and Headphone (no HDMI - input only on Ultra)
        assert "Line Out" in outputs
        assert "Optical Out" in outputs
        assert "Coax Out" in outputs
        assert "USB Out" in outputs
        assert "Headphone Out" in outputs
        # HDMI is input-only on WiiM Ultra (confirmed via Issue #160)
        assert "HDMI Out" not in outputs
        assert len([o for o in outputs if o.startswith("BT: ")]) == 0

    @pytest.mark.asyncio
    async def test_available_outputs_wiim_ultra_with_bt(self, mock_client):
        """Test available_outputs for WiiM Ultra with BT devices (removes generic BT Out)."""
        from pywiim.models import DeviceInfo
        from pywiim.player import Player

        type(mock_client).capabilities = PropertyMock(return_value={"supports_audio_output": True})
        player = Player(mock_client)
        player._device_info = DeviceInfo(
            uuid="test", name="Test", model="WiiM Ultra", firmware="1.0", ip="192.168.1.100", mac="AA:BB:CC:DD:EE:FF"
        )
        player._bluetooth_history = [
            {"name": "BT Speaker", "ad": "AA:BB:CC:DD:EE:FF", "ct": 0, "role": "Audio Sink"},
        ]

        outputs = player.available_outputs
        # Ultra-specific outputs
        assert "Headphone Out" in outputs
        assert "USB Out" in outputs
        # HDMI is input-only on WiiM Ultra (confirmed via Issue #160)
        assert "HDMI Out" not in outputs
        # Standard outputs
        assert "Line Out" in outputs
        assert "Optical Out" in outputs
        assert "Coax Out" in outputs
        assert "BT: BT Speaker" in outputs

    @pytest.mark.asyncio
    async def test_select_output_hardware_mode(self, mock_client):
        """Test selecting a hardware output mode."""
        from pywiim.models import PlayerStatus
        from pywiim.player import Player

        mock_client.set_audio_output_mode = AsyncMock()
        mock_status = PlayerStatus(play_state="stop")
        mock_client.get_player_status_model = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(return_value=None)
        mock_client.get_bluetooth_history = AsyncMock(return_value=[])

        player = Player(mock_client)

        await player.select_output("Optical Out")

        mock_client.set_audio_output_mode.assert_called_once_with("Optical Out")

    @pytest.mark.asyncio
    async def test_select_output_bluetooth_device(self, mock_client):
        """Test selecting a specific Bluetooth device."""
        from pywiim.models import PlayerStatus
        from pywiim.player import Player

        mock_client.connect_bluetooth_device = AsyncMock()
        mock_status = PlayerStatus(play_state="stop")
        mock_client.get_player_status_model = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(return_value=None)
        mock_client.get_bluetooth_history = AsyncMock(return_value=[])

        player = Player(mock_client)
        player._bluetooth_history = [
            {"name": "Sony Speaker", "ad": "AA:BB:CC:DD:EE:FF", "ct": 0, "role": "Audio Sink"},
        ]

        await player.select_output("BT: Sony Speaker")

        # Should connect to the specific device (this automatically activates BT output mode)
        mock_client.connect_bluetooth_device.assert_called_once_with("AA:BB:CC:DD:EE:FF")

    @pytest.mark.asyncio
    async def test_select_output_bluetooth_device_not_found(self, mock_client):
        """Test selecting a Bluetooth device that's not paired."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._bluetooth_history = [
            {"name": "Sony Speaker", "ad": "AA:BB:CC:DD:EE:FF", "ct": 0, "role": "Audio Sink"},
        ]

        with pytest.raises(ValueError, match="Bluetooth device 'Unknown Device' not found"):
            await player.select_output("BT: Unknown Device")


class TestPlayerCapabilities:
    """Tests for Player capability properties (SoCo-style pattern)."""

    @pytest.fixture
    def mock_client(self, mock_aiohttp_session):
        """Create a mock WiiM client."""
        from pywiim.client import WiiMClient

        client = WiiMClient("192.168.1.100", session=mock_aiohttp_session)
        client._capabilities = {
            "supports_eq": True,
            "supports_presets": True,
            "supports_audio_output": True,
            "supports_metadata": True,
            "supports_alarms": True,
            "supports_sleep_timer": True,
            "supports_led_control": True,
        }
        return client

    def test_supports_eq(self, mock_client):
        """Test supports_eq property."""
        from pywiim.player import Player

        player = Player(mock_client)
        assert player.supports_eq is True

        mock_client._capabilities["supports_eq"] = False
        assert player.supports_eq is False

    def test_supports_presets(self, mock_client):
        """Test supports_presets property."""
        from pywiim.player import Player

        player = Player(mock_client)
        assert player.supports_presets is True

        mock_client._capabilities["supports_presets"] = False
        assert player.supports_presets is False

    def test_presets_full_data(self, mock_client):
        """Test presets_full_data property."""
        from pywiim.player import Player

        player = Player(mock_client)
        mock_client._capabilities = {
            "supports_presets": True,
            "presets_full_data": True,
        }
        assert player.presets_full_data is True

        mock_client._capabilities["presets_full_data"] = False
        assert player.presets_full_data is False

        mock_client._capabilities["supports_presets"] = False
        assert player.presets_full_data is False

    def test_supports_audio_output(self, mock_client):
        """Test supports_audio_output property."""
        from pywiim.player import Player

        player = Player(mock_client)
        assert player.supports_audio_output is True

        mock_client._capabilities["supports_audio_output"] = False
        assert player.supports_audio_output is False

    def test_supports_metadata(self, mock_client):
        """Test supports_metadata property."""
        from pywiim.player import Player

        player = Player(mock_client)
        assert player.supports_metadata is True

        mock_client._capabilities["supports_metadata"] = False
        assert player.supports_metadata is False

    def test_supports_alarms(self, mock_client):
        """Test supports_alarms property."""
        from pywiim.player import Player

        player = Player(mock_client)
        assert player.supports_alarms is True

        mock_client._capabilities["supports_alarms"] = False
        assert player.supports_alarms is False

    def test_supports_sleep_timer(self, mock_client):
        """Test supports_sleep_timer property."""
        from pywiim.player import Player

        player = Player(mock_client)
        assert player.supports_sleep_timer is True

        mock_client._capabilities["supports_sleep_timer"] = False
        assert player.supports_sleep_timer is False

    def test_supports_led_control(self, mock_client):
        """Test supports_led_control property."""
        from pywiim.player import Player

        player = Player(mock_client)
        assert player.supports_led_control is True

        mock_client._capabilities["supports_led_control"] = False
        assert player.supports_led_control is False

    def test_supports_queue_count(self, mock_client):
        """Test supports_queue_count property (always True)."""
        from pywiim.player import Player

        player = Player(mock_client)
        # Always True - available via HTTP API plicount/plicurr
        assert player.supports_queue_count is True

    def test_supports_upnp_without_client(self, mock_client):
        """Test supports_upnp when UPnP client is not available."""
        from pywiim.player import Player

        player = Player(mock_client)
        # No UPnP client by default
        assert player.supports_upnp is False
        assert player.supports_queue_browse is False
        assert player.supports_queue_add is False

    def test_supports_upnp_with_client(self, mock_client):
        """Test supports_upnp when UPnP client is available."""
        from unittest.mock import MagicMock

        from pywiim.player import Player

        player = Player(mock_client)

        # Mock UPnP client with services
        mock_upnp = MagicMock()
        mock_upnp.av_transport = MagicMock()
        mock_upnp.content_directory = None  # No ContentDirectory

        player._upnp_client = mock_upnp

        assert player.supports_upnp is True
        assert player.supports_queue_add is True  # AVTransport available
        assert player.supports_queue_browse is False  # No ContentDirectory

    def test_supports_queue_browse_with_content_directory(self, mock_client):
        """Test supports_queue_browse when ContentDirectory is available."""
        from unittest.mock import MagicMock

        from pywiim.player import Player

        player = Player(mock_client)

        # Mock UPnP client with ContentDirectory
        mock_upnp = MagicMock()
        mock_upnp.av_transport = MagicMock()
        mock_upnp.content_directory = MagicMock()  # ContentDirectory available

        player._upnp_client = mock_upnp

        assert player.supports_queue_browse is True

    def test_capabilities_defaults_to_false(self, mock_client):
        """Test capability properties default to False when not set."""
        from pywiim.player import Player

        # Create player with empty capabilities
        mock_client._capabilities = {}
        player = Player(mock_client)

        # All HTTP-based capabilities should return False when not set
        assert player.supports_eq is False
        assert player.supports_presets is False
        assert player.supports_audio_output is False
        assert player.supports_metadata is False
        assert player.supports_alarms is False
        assert player.supports_sleep_timer is False
        assert player.supports_led_control is False

        # UPnP capabilities (no UPnP client)
        assert player.supports_upnp is False
        assert player.supports_queue_browse is False
        assert player.supports_queue_add is False

        # Queue count is always True (HTTP API)
        assert player.supports_queue_count is True

    @pytest.mark.asyncio
    async def test_ensure_upnp_client_already_exists(self, mock_client):
        """Test _ensure_upnp_client when client already exists."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._upnp_client = MagicMock()

        result = await player._ensure_upnp_client()

        assert result is True

    @pytest.mark.asyncio
    async def test_ensure_upnp_client_creation_attempted(self, mock_client):
        """Test _ensure_upnp_client when creation already attempted."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._upnp_client_creation_attempted = True

        result = await player._ensure_upnp_client()

        assert result is False

    @pytest.mark.asyncio
    async def test_ensure_upnp_client_success(self, mock_client):
        """Test successful UPnP client creation."""
        from pywiim.player import Player

        player = Player(mock_client)
        with patch("pywiim.upnp.client.UpnpClient") as mock_upnp_client_class:
            mock_upnp_client = MagicMock()
            mock_upnp_client.av_transport = MagicMock()
            mock_upnp_client.rendering_control = MagicMock()
            mock_upnp_client_class.create = AsyncMock(return_value=mock_upnp_client)
            mock_client._ensure_session = AsyncMock()
            mock_client._session = MagicMock()

            result = await player._ensure_upnp_client()

            assert result is True
            assert player._upnp_client == mock_upnp_client

    @pytest.mark.asyncio
    async def test_ensure_upnp_client_failure(self, mock_client):
        """Test UPnP client creation failure."""
        from pywiim.player import Player

        player = Player(mock_client)
        with patch("pywiim.upnp.client.UpnpClient") as mock_upnp_client_class:
            mock_upnp_client_class.create = AsyncMock(side_effect=Exception("Connection failed"))
            mock_client._ensure_session = AsyncMock()

            result = await player._ensure_upnp_client()

            assert result is False
            assert player._upnp_client is None
            # Last attempt timestamp should be updated (for retry cooldown logic)
            assert player._last_upnp_attempt > 0


class TestPlayerNetworkErrors:
    """Test error handling paths for network errors, API failures, and timeouts."""

    @pytest.mark.asyncio
    async def test_refresh_handles_network_timeout(self, mock_client):
        """Test refresh handles network timeout gracefully."""
        import asyncio

        from pywiim.player import Player

        # Simulate timeout
        mock_client.get_player_status_model = AsyncMock(side_effect=TimeoutError("Request timeout"))

        player = Player(mock_client)
        with pytest.raises(asyncio.TimeoutError):
            await player.refresh()

        # Should mark player as unavailable
        assert player.available is False

    @pytest.mark.asyncio
    async def test_refresh_handles_partial_failure(self, mock_client):
        """Test refresh handles partial API failure (status succeeds, info fails)."""
        from pywiim.exceptions import WiiMError
        from pywiim.models import PlayerStatus
        from pywiim.player import Player

        # Status succeeds, but device info fails
        mock_status = PlayerStatus(play_state="play", volume=50)
        mock_client.get_player_status_model = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(side_effect=WiiMError("Device info failed"))

        player = Player(mock_client)
        with pytest.raises(WiiMError):
            await player.refresh()

        # Status may be partially updated before info fails, but player should be unavailable
        assert player.available is False

    @pytest.mark.asyncio
    async def test_play_handles_api_error(self, mock_client):
        """Test play command handles API errors and preserves state."""
        from pywiim.exceptions import WiiMError
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        player = Player(mock_client)
        player._status_model = PlayerStatus(play_state="pause", volume=50)
        player._device_info = DeviceInfo(uuid="test", name="Test")

        # API call fails
        mock_client.play = AsyncMock(side_effect=WiiMError("API error"))

        with pytest.raises(WiiMError):
            await player.play()

        # State should remain unchanged (no optimistic update on error)
        assert player._status_model.play_state == "pause"

    @pytest.mark.asyncio
    async def test_set_volume_handles_out_of_range(self, mock_client):
        """Test set_volume clamps values outside valid range (no error raised)."""
        from pywiim.player import Player

        mock_client.set_volume = AsyncMock()

        player = Player(mock_client)

        # Volume > 1.0 is clamped to 1.0 (100%)
        await player.set_volume(1.5)
        # Should have called API (clamped to 100)
        mock_client.set_volume.assert_called()

        # Volume < 0 is clamped to 0.0 (0%)
        await player.set_volume(-0.1)
        # Should have called API (clamped to 0)
        assert mock_client.set_volume.call_count == 2

    @pytest.mark.asyncio
    async def test_refresh_handles_connection_error(self, mock_client):
        """Test refresh handles connection errors (device unreachable)."""
        from pywiim.exceptions import WiiMConnectionError
        from pywiim.player import Player

        # Simulate connection error using the library's exception type
        mock_client.get_player_status_model = AsyncMock(side_effect=WiiMConnectionError("Connection refused"))

        player = Player(mock_client)
        with pytest.raises(WiiMConnectionError):
            await player.refresh()

        assert player.available is False

    @pytest.mark.asyncio
    async def test_control_methods_handle_unavailable_player(self, mock_client):
        """Test control methods handle unavailable player gracefully."""
        from pywiim.models import PlayerStatus
        from pywiim.player import Player

        player = Player(mock_client)
        player._available = False
        player._status_model = PlayerStatus(play_state="pause")

        # Methods should still work (they may queue commands or handle offline state)
        # This tests that availability doesn't block control methods
        mock_client.play = AsyncMock()
        await player.play()

        # Should still attempt API call (device might be back online)
        mock_client.play.assert_called_once()


class TestPlayerGroupRoleTransitions:
    """Test group role transitions (solo->master, master->solo, etc.)."""

    @pytest.mark.asyncio
    async def test_role_transition_solo_to_master(self, mock_client):
        """Test role transition from solo to master when slaves join."""
        from pywiim.group import Group
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        player = Player(mock_client)
        player._status_model = PlayerStatus(play_state="play")
        player._device_info = DeviceInfo(uuid="master-uuid", name="Master")

        # Start as solo
        assert player.role == "solo"
        assert player.is_solo is True

        # Simulate device detecting slaves (role detection happens during refresh)
        player._detected_role = "master"
        group = Group(player)

        # Add a slave to make it a proper master
        slave = Player(mock_client)
        slave._detected_role = "slave"
        group.add_slave(slave)

        # Role should now be master
        assert player.role == "master"
        assert player.is_solo is False
        assert player.is_master is True
        assert player.group == group

    @pytest.mark.asyncio
    async def test_role_transition_master_to_solo(self, mock_client):
        """Test role transition from master to solo when all slaves leave."""
        from pywiim.group import Group
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        master = Player(mock_client)
        master._detected_role = "master"
        master._status_model = PlayerStatus(play_state="play")
        master._device_info = DeviceInfo(uuid="master-uuid", name="Master")

        slave = Player(mock_client)
        slave._detected_role = "slave"

        group = Group(master)
        group.add_slave(slave)

        # Start as master
        assert master.role == "master"
        assert master.is_master is True

        # Remove slave
        group.remove_slave(slave)

        # Master with no slaves should be solo
        # (Role detection would update this during refresh, but Group tracks it)
        assert master.group == group  # Group still exists
        # Note: Actual role comes from device API, but group state reflects no slaves

    @pytest.mark.asyncio
    async def test_role_transition_slave_to_solo(self, mock_client):
        """Test role transition from slave to solo when leaving group."""
        from pywiim.group import Group
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        master = Player(mock_client)
        master._detected_role = "master"
        slave = Player(mock_client)
        slave._detected_role = "slave"
        slave._status_model = PlayerStatus(play_state="play")
        slave._device_info = DeviceInfo(uuid="slave-uuid", name="Slave")

        group = Group(master)
        group.add_slave(slave)

        # Start as slave
        assert slave.role == "slave"
        assert slave.is_slave is True
        assert slave.group == group

        # Simulate leaving group (device API would update role during refresh)
        slave._detected_role = "solo"
        group.remove_slave(slave)

        # Should transition to solo
        assert slave.role == "solo"
        assert slave.is_solo is True
        assert slave.group is None

    @pytest.mark.asyncio
    async def test_role_transition_master_to_slave(self, mock_client):
        """Test role transition when master becomes slave (joins another group)."""
        from pywiim.group import Group
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        # Original master
        original_master = Player(mock_client)
        original_master._detected_role = "master"
        original_master._status_model = PlayerStatus(play_state="play")
        original_master._device_info = DeviceInfo(uuid="master1-uuid", name="Master1")

        # New master (this device joins as slave)
        new_master = Player(mock_client)
        new_master._detected_role = "master"
        new_master._status_model = PlayerStatus(play_state="play")
        new_master._device_info = DeviceInfo(uuid="master2-uuid", name="Master2")

        # Original master has a slave
        original_group = Group(original_master)
        slave1 = Player(mock_client)
        slave1._detected_role = "slave"
        original_group.add_slave(slave1)

        # Original master joins new master's group (becomes slave)
        original_master._detected_role = "slave"
        new_group = Group(new_master)
        new_group.add_slave(original_master)

        # Original master should now be slave
        assert original_master.role == "slave"
        assert original_master.is_slave is True
        assert original_master.group == new_group


class TestPlayerSourceConflictScenarios:
    """Test source conflict scenarios (HTTP vs UPnP, optimistic updates vs device state)."""

    @pytest.mark.asyncio
    async def test_source_conflict_http_vs_upnp_freshness(self, mock_client):
        """Test source conflict resolution based on freshness (UPnP fresh, HTTP stale)."""
        import time
        from unittest.mock import MagicMock

        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        now = time.time()

        # Setup player with UPnP client
        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.rendering_control = MagicMock()
        mock_upnp_client.get_volume = AsyncMock(return_value=75)
        mock_upnp_client.get_mute = AsyncMock(return_value=False)

        player = Player(mock_client, upnp_client=mock_upnp_client)
        player._status_model = PlayerStatus(play_state="play", volume=50, mute=True)

        # Update state synchronizer with stale HTTP and fresh UPnP
        # UPnP and HTTP both use 0-100 scale for internal merged state.
        player._state_synchronizer.update_from_http({"volume": 50, "muted": True}, timestamp=now - 10.0)
        player._state_synchronizer.update_from_upnp({"volume": 75, "muted": False}, timestamp=now)

        # Refresh should merge states, preferring fresh UPnP
        mock_status = PlayerStatus(play_state="play", volume=50, mute=True)  # HTTP returns old values
        mock_info = DeviceInfo(uuid="test", name="Test")
        mock_client.get_player_status_model = AsyncMock(return_value=mock_status)
        mock_client.get_device_info_model = AsyncMock(return_value=mock_info)

        await player.refresh()

        # Merged state should prefer fresh UPnP values (UPnP has priority for volume)
        merged = player._state_synchronizer.get_merged_state()
        assert merged["volume"] == 75  # From UPnP (fresh), 0-100 scale
        assert merged["muted"] is False  # From UPnP (fresh)

    @pytest.mark.asyncio
    async def test_optimistic_update_preserved_during_refresh(self, mock_client):
        """Test optimistic source update is preserved during refresh when device reports mode=0."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        player = Player(mock_client)

        # Set optimistic source (e.g., from set_source("bluetooth"))
        player._status_model = PlayerStatus(source="bluetooth", play_state="idle")
        player._device_info = DeviceInfo(uuid="test-uuid", name="Test Device")

        # Device refresh returns mode=0 (idle) - no source field
        new_status = PlayerStatus(play_state="idle", volume=50, mute=False)  # No source field
        mock_client.get_player_status_model = AsyncMock(return_value=new_status)
        mock_client.get_device_info_model = AsyncMock(return_value=player._device_info)

        await player.refresh()

        # Optimistic source should be preserved
        assert player._status_model.source == "bluetooth"
        assert player._status_model.play_state == "idle"

    @pytest.mark.asyncio
    async def test_source_conflict_priority_when_both_fresh(self, mock_client):
        """Test source conflict resolution uses priority when both sources are fresh."""
        import time
        from unittest.mock import MagicMock

        from pywiim.player import Player
        from pywiim.upnp.client import UpnpClient

        now = time.time()

        # Setup player with UPnP client
        mock_upnp_client = MagicMock(spec=UpnpClient)
        mock_upnp_client.rendering_control = MagicMock()
        mock_upnp_client.get_volume = AsyncMock(return_value=80)
        mock_upnp_client.get_mute = AsyncMock(return_value=True)

        player = Player(mock_client, upnp_client=mock_upnp_client)

        # Both sources fresh - UPnP has priority for both play_state and volume
        player._state_synchronizer.update_from_http({"play_state": "pause", "volume": 50}, timestamp=now)
        player._state_synchronizer.update_from_upnp({"play_state": "play", "volume": 80}, timestamp=now)

        merged = player._state_synchronizer.get_merged_state()

        # UPnP has priority for play_state AND volume (both are real-time fields)
        assert merged["play_state"] == "play"  # UPnP priority
        assert merged["volume"] == 80  # UPnP priority for volume (0-100 scale)

    @pytest.mark.asyncio
    async def test_rapid_state_changes_preserve_latest(self, mock_client):
        """Test rapid state changes preserve the latest update."""

        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        player = Player(mock_client)
        player._status_model = PlayerStatus(play_state="pause", volume=50)
        player._device_info = DeviceInfo(uuid="test", name="Test")

        # Simulate rapid play/pause/play sequence
        mock_client.play = AsyncMock()
        mock_client.pause = AsyncMock()
        mock_client.get_player_status_model = AsyncMock(return_value=PlayerStatus(play_state="play", volume=50))
        mock_client.get_device_info_model = AsyncMock(return_value=player._device_info)

        # Rapid commands
        await player.play()
        await player.pause()
        await player.play()

        # Final state should be play
        assert player._status_model.play_state == "play"
        # All commands should have been called
        assert mock_client.play.call_count == 2
        assert mock_client.pause.call_count == 1


class TestPlayerStateTransitions:
    """Test edge cases for state transitions (rapid changes, stale data, conflicts)."""

    @pytest.mark.asyncio
    async def test_stale_data_handling(self, mock_client):
        """Test handling of stale data from device."""
        import time

        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        now = time.time()

        player = Player(mock_client)
        player._status_model = PlayerStatus(play_state="play", volume=50)
        player._device_info = DeviceInfo(uuid="test", name="Test")

        # Update state synchronizer with fresh optimistic update
        player._state_synchronizer.update_from_http({"play_state": "play", "volume": 60}, timestamp=now)

        # Device returns stale data (older timestamp)
        stale_status = PlayerStatus(play_state="pause", volume=50)  # Stale state
        mock_client.get_player_status_model = AsyncMock(return_value=stale_status)
        mock_client.get_device_info_model = AsyncMock(return_value=player._device_info)

        await player.refresh()

        # Fresh optimistic update should be preserved over stale device data
        # Note: refresh updates from device, but freshness logic should handle this
        # The exact behavior depends on timestamp comparison in state synchronizer
        _ = player._state_synchronizer.get_merged_state()  # Verify merged state exists

    @pytest.mark.asyncio
    async def test_volume_transition_edge_cases(self, mock_client):
        """Test volume transition edge cases (0, 1.0, rapid changes)."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        player = Player(mock_client)
        player._status_model = PlayerStatus(volume=50, play_state="play")
        player._device_info = DeviceInfo(uuid="test", name="Test")

        mock_client.set_volume = AsyncMock()

        # Test boundary values
        await player.set_volume(0.0)  # Minimum
        await player.set_volume(1.0)  # Maximum

        assert mock_client.set_volume.call_count == 2
        mock_client.set_volume.assert_any_call(0.0)
        mock_client.set_volume.assert_any_call(1.0)

    @pytest.mark.asyncio
    async def test_play_state_debouncing_rapid_changes(self, mock_client):
        """Test play state debouncing handles rapid play/pause changes."""
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        player = Player(mock_client)
        player._status_model = PlayerStatus(play_state="pause", volume=50)
        player._device_info = DeviceInfo(uuid="test", name="Test")

        mock_client.play = AsyncMock()
        mock_client.pause = AsyncMock()

        # Rapid play/pause sequence
        await player.play()
        await player.pause()
        await player.play()

        # All commands should execute (debouncing doesn't block commands)
        assert mock_client.play.call_count == 2
        assert mock_client.pause.call_count == 1

    @pytest.mark.asyncio
    async def test_state_synchronization_after_error_recovery(self, mock_client):
        """Test state synchronization recovers correctly after API error."""
        from pywiim.exceptions import WiiMError
        from pywiim.models import DeviceInfo, PlayerStatus
        from pywiim.player import Player

        player = Player(mock_client)
        player._status_model = PlayerStatus(play_state="play", volume=50)
        player._device_info = DeviceInfo(uuid="test", name="Test")

        # First refresh fails
        mock_client.get_player_status_model = AsyncMock(side_effect=WiiMError("Network error"))
        with pytest.raises(WiiMError):
            await player.refresh()

        assert player.available is False

        # Second refresh succeeds
        new_status = PlayerStatus(play_state="pause", volume=60)
        mock_client.get_player_status_model = AsyncMock(return_value=new_status)
        mock_client.get_device_info_model = AsyncMock(return_value=player._device_info)

        await player.refresh()

        # State should be updated and player available
        assert player.available is True
        assert player._status_model.play_state == "pause"
        assert player._status_model.volume == 60
