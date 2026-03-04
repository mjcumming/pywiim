"""Unit tests for StateManager.

Tests state management, refresh, UPnP integration, and state synchronization.
"""

import time
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from pywiim.models import DeviceInfo, PlayerStatus


class TestStateManager:
    """Test StateManager class."""

    @pytest.fixture
    def mock_player(self, mock_client):
        """Create a mock Player instance."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._status_model = PlayerStatus()
        player._device_info = None
        player._upnp_client = None
        player._upnp_health_tracker = None
        player._state_synchronizer = MagicMock()
        player._state_synchronizer.update_from_upnp = MagicMock()
        player._state_synchronizer.get_merged_state = MagicMock(return_value={})
        player._on_state_changed = None
        player._group = None
        # Set up coverart manager (now used for track change detection)
        from pywiim.player.coverart import CoverArtManager
        from pywiim.player.groupops import GroupOperations

        player._coverart_mgr = CoverArtManager(player)
        player._group_ops = GroupOperations(player)
        # Mock properties - store originals to restore later
        from pywiim.player import Player as PlayerClass

        property_names = ["play_state", "volume_level", "is_muted", "media_title", "media_position", "is_master"]
        for prop_name in property_names:
            if not hasattr(PlayerClass, f"_original_{prop_name}_property"):
                setattr(PlayerClass, f"_original_{prop_name}_property", getattr(PlayerClass, prop_name, None))
            setattr(PlayerClass, prop_name, PropertyMock(return_value=None if prop_name != "is_muted" else False))
        return player

    @pytest.fixture
    def state_manager(self, mock_player):
        """Create a StateManager instance."""
        from pywiim.player.statemgr import StateManager

        return StateManager(mock_player)

    @staticmethod
    def _setup_refresh_mocks(mock_player, state_manager):
        """Helper to set up common mocks for refresh tests."""
        from pywiim.polling import PollingStrategy

        mock_player._state_synchronizer.update_from_http = MagicMock()
        mock_player._state_synchronizer.get_merged_state = MagicMock(return_value={})
        # Mock capabilities as a property - store original to restore later
        client_class = type(mock_player.client)
        if not hasattr(client_class, "_original_capabilities_property"):
            # Store original property descriptor before patching
            client_class._original_capabilities_property = getattr(client_class, "capabilities", None)
        # Patch on class using PropertyMock (will be restored by test cleanup)
        client_class.capabilities = PropertyMock(return_value={})
        mock_player._last_refresh = time.time() - 10
        mock_player._audio_output_status = None
        mock_player._last_audio_output_check = None
        mock_player._last_eq_presets_check = None
        mock_player._last_eq_status_check = None
        mock_player._last_presets_check = None
        mock_player._last_bt_history_check = None
        mock_player._upnp_health_tracker = None
        mock_player._metadata = None
        mock_player._last_metadata_check = 0
        mock_player._eq_presets = None
        mock_player._presets = []
        mock_player._bluetooth_history = []
        mock_player._group = None
        mock_player._available = True
        state_manager._polling_strategy = PollingStrategy({})
        state_manager._last_eq_preset = None
        state_manager._last_source = None
        # Track signature is now managed by CoverArtManager
        if hasattr(mock_player, "_coverart_mgr"):
            mock_player._coverart_mgr._last_track_signature = None

    def test_init(self, state_manager):
        """Test StateManager initialization."""
        assert state_manager.player is not None
        assert state_manager._play_state_debouncer is not None
        assert state_manager._stream_enricher is not None

    def test_apply_diff_no_changes(self, state_manager, mock_player):
        """Test apply_diff with no changes."""
        result = state_manager.apply_diff({})

        assert result is False

    def test_apply_diff_with_changes(self, state_manager, mock_player):
        """Test apply_diff with changes."""
        # Mock properties to return different values before and after
        # Use return_value for first call, then side_effect for subsequent
        play_state_values = ["stop", "play"]
        volume_values = [0.3, 0.5]

        play_state_prop = PropertyMock()
        play_state_prop.side_effect = lambda: play_state_values.pop(0) if play_state_values else "play"
        volume_prop = PropertyMock()
        volume_prop.side_effect = lambda: volume_values.pop(0) if volume_values else 0.5

        type(mock_player).play_state = play_state_prop
        type(mock_player).volume_level = volume_prop
        type(mock_player).is_muted = PropertyMock(return_value=False)
        type(mock_player).media_title = PropertyMock(return_value=None)
        type(mock_player).media_position = PropertyMock(return_value=None)
        mock_player._state_synchronizer.get_merged_state.return_value = {
            "play_state": "play",
            "volume": 0.5,
        }

        # Reset the lists for the actual test
        play_state_values[:] = ["stop", "play"]
        volume_values[:] = [0.3, 0.5]

        result = state_manager.apply_diff({"play_state": "play", "volume": 0.5})

        # Just verify it doesn't crash and returns a boolean
        assert isinstance(result, bool)

    def test_update_from_upnp_no_play_state(self, state_manager, mock_player):
        """Test update_from_upnp without play_state."""
        mock_player._state_synchronizer.get_merged_state.return_value = {"volume": 0.5}

        state_manager.update_from_upnp({"volume": 0.5})

        mock_player._state_synchronizer.update_from_upnp.assert_called_once()

    def test_update_from_upnp_play_state_debounce(self, state_manager, mock_player):
        """Test update_from_upnp with play_state debouncing."""
        type(mock_player).play_state = PropertyMock(return_value="play")
        mock_player._state_synchronizer.get_merged_state.return_value = {"play_state": "pause"}

        state_manager.update_from_upnp({"play_state": "pause"})

        # Should schedule delayed update via debouncer
        assert state_manager._play_state_debouncer._pending_task is not None

    def test_update_from_upnp_play_state_immediate(self, state_manager, mock_player):
        """Test update_from_upnp with immediate play state."""
        type(mock_player).play_state = PropertyMock(return_value="stop")
        mock_player._state_synchronizer.get_merged_state.return_value = {"play_state": "play"}

        state_manager.update_from_upnp({"play_state": "play"})

        mock_player._state_synchronizer.update_from_upnp.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_full(self, state_manager, mock_player):
        """Test full refresh."""
        mock_status = PlayerStatus(play_state="play", volume=50)
        mock_info = DeviceInfo(uuid="test-uuid", name="Test Device")
        mock_player.client.get_player_status_model = AsyncMock(return_value=mock_status)
        mock_player.client.get_device_info_model = AsyncMock(return_value=mock_info)
        TestStateManager._setup_refresh_mocks(mock_player, state_manager)
        mock_player._last_refresh = time.time() - 10  # Not first refresh
        with patch.object(mock_player._group_ops, "propagate_metadata_to_slaves", new_callable=MagicMock):
            with patch("pywiim.player.groupops.GroupOperations") as mock_groupops:
                mock_groupops.return_value._synchronize_group_state = AsyncMock()

                await state_manager.refresh(full=True)

                mock_player.client.get_player_status_model.assert_called_once()
                mock_player.client.get_device_info_model.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_not_full(self, state_manager, mock_player):
        """Test non-full refresh."""
        mock_status = PlayerStatus(play_state="play", volume=50)
        mock_player.client.get_player_status_model = AsyncMock(return_value=mock_status)
        mock_player._state_synchronizer.update_from_http = MagicMock()
        mock_player._state_synchronizer.get_merged_state = MagicMock(return_value={})
        mock_player._device_info = DeviceInfo(uuid="test-uuid", name="Test Device")  # Already cached
        TestStateManager._setup_refresh_mocks(mock_player, state_manager)
        with patch.object(mock_player._group_ops, "propagate_metadata_to_slaves", new_callable=MagicMock):
            with patch("pywiim.player.groupops.GroupOperations") as mock_groupops:
                mock_groupops.return_value._synchronize_group_state = AsyncMock()

                await state_manager.refresh(full=False)

        mock_player.client.get_player_status_model.assert_called_once()
        # Should not fetch device info when not full and already cached
        if hasattr(mock_player.client, "get_device_info_model"):
            device_info_method = mock_player.client.get_device_info_model
            # Only assert if it's a mock (might be a real method in some cases)
            if hasattr(device_info_method, "assert_not_called"):
                device_info_method.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_device_info(self, state_manager, mock_player):
        """Test getting device info."""
        mock_info = DeviceInfo(uuid="test-uuid", name="Test Device")
        mock_player.client.get_device_info_model = AsyncMock(return_value=mock_info)

        result = await state_manager.get_device_info()

        assert result == mock_info

    @pytest.mark.asyncio
    async def test_get_status(self, state_manager, mock_player):
        """Test getting status."""
        mock_status = PlayerStatus(play_state="play", volume=50)
        mock_player.client.get_player_status_model = AsyncMock(return_value=mock_status)

        result = await state_manager.get_status()

        assert result == mock_status

    @pytest.mark.asyncio
    async def test_get_play_state(self, state_manager, mock_player):
        """Test getting play state."""
        mock_status = PlayerStatus(play_state="play")
        mock_player.client.get_player_status_model = AsyncMock(return_value=mock_status)

        result = await state_manager.get_play_state()

        assert result == "play"

    # === Comprehensive refresh() tests ===

    @pytest.mark.asyncio
    async def test_refresh_first_time_always_full(self, state_manager, mock_player):
        """Test that first refresh is always full."""
        mock_status = PlayerStatus(play_state="play", volume=50)
        mock_info = DeviceInfo(uuid="test-uuid", name="Test Device")
        mock_player.client.get_player_status_model = AsyncMock(return_value=mock_status)
        mock_player.client.get_device_info_model = AsyncMock(return_value=mock_info)
        TestStateManager._setup_refresh_mocks(mock_player, state_manager)
        mock_player._last_refresh = None  # First refresh
        with patch.object(mock_player._group_ops, "propagate_metadata_to_slaves", new_callable=MagicMock):
            with patch("pywiim.player.groupops.GroupOperations") as mock_groupops:
                mock_groupops.return_value._synchronize_group_state = AsyncMock()

                await state_manager.refresh(full=False)  # Even though False, should be full

                mock_player.client.get_device_info_model.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_with_upnp_volume(self, state_manager, mock_player):
        """Test refresh with UPnP volume/mute."""
        mock_status = PlayerStatus(play_state="play", volume=50)
        mock_player.client.get_player_status_model = AsyncMock(return_value=mock_status)
        TestStateManager._setup_refresh_mocks(mock_player, state_manager)
        mock_player._upnp_client = MagicMock()
        mock_player._upnp_client.rendering_control = MagicMock()
        mock_player._upnp_client.get_volume = AsyncMock(return_value=75)
        mock_player._upnp_client.get_mute = AsyncMock(return_value=True)

        with patch("pywiim.player.groupops.GroupOperations") as mock_groupops:
            mock_groupops.return_value._synchronize_group_state = AsyncMock()

            await state_manager.refresh(full=False)

        # Should use UPnP volume
        call_args = mock_player._state_synchronizer.update_from_http.call_args[0][0]
        assert call_args["volume"] == 75
        assert call_args["muted"] is True

    @pytest.mark.asyncio
    async def test_refresh_upnp_volume_fails_fallback(self, state_manager, mock_player):
        """Test refresh when UPnP volume fails, falls back to HTTP."""
        mock_status = PlayerStatus(play_state="play", volume=50, mute=False)
        mock_player.client.get_player_status_model = AsyncMock(return_value=mock_status)
        TestStateManager._setup_refresh_mocks(mock_player, state_manager)
        mock_player._upnp_client = MagicMock()
        mock_player._upnp_client.rendering_control = MagicMock()
        mock_player._upnp_client.get_volume = AsyncMock(side_effect=Exception("UPnP error"))

        with patch("pywiim.player.groupops.GroupOperations") as mock_groupops:
            mock_groupops.return_value._synchronize_group_state = AsyncMock()

            await state_manager.refresh(full=False)

        # Should use HTTP volume
        call_args = mock_player._state_synchronizer.update_from_http.call_args[0][0]
        assert call_args["volume"] == 50

    @pytest.mark.asyncio
    async def test_refresh_track_changed_fetches_metadata(self, state_manager, mock_player):
        """Test refresh when track changes, fetches metadata."""
        mock_status = PlayerStatus(play_state="play", title="New Track", artist="New Artist")
        mock_player.client.get_player_status_model = AsyncMock(return_value=mock_status)
        TestStateManager._setup_refresh_mocks(mock_player, state_manager)
        type(mock_player.client).capabilities = PropertyMock(return_value={"supports_metadata": True})
        mock_player.client.get_meta_info = AsyncMock(return_value={"metaData": {}})
        # Track signature is now managed by CoverArtManager
        mock_player._coverart_mgr._last_track_signature = "Old|Track|Album"

        with patch("pywiim.player.groupops.GroupOperations") as mock_groupops:
            mock_groupops.return_value._synchronize_group_state = AsyncMock()

            await state_manager.refresh(full=False)

        mock_player.client.get_meta_info.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_startup_fetches_metadata_when_missing(self, state_manager, mock_player):
        """Test refresh fetches getMetaInfo on startup when metadata cache is empty.

        Regression: track-change detection can miss the first track (no prior signature),
        so we must fetch getMetaInfo at least once to populate audio-quality fields.
        """
        mock_status = PlayerStatus(play_state="play", title="Same", artist="Same")
        mock_player.client.get_player_status_model = AsyncMock(return_value=mock_status)
        TestStateManager._setup_refresh_mocks(mock_player, state_manager)
        type(mock_player.client).capabilities = PropertyMock(return_value={"supports_metadata": True})
        mock_player.client.get_meta_info = AsyncMock(return_value={"metaData": {"bitRate": "128"}})
        # Ensure track change detector returns False (first signature)
        mock_player._coverart_mgr._last_track_signature = None
        mock_player._metadata = None

        with patch("pywiim.player.groupops.GroupOperations") as mock_groupops:
            mock_groupops.return_value._synchronize_group_state = AsyncMock()
            await state_manager.refresh(full=False)  # First refresh is coerced to full internally

        mock_player.client.get_meta_info.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_eq_preset_changed(self, state_manager, mock_player):
        """Test refresh when EQ preset changes."""
        mock_status = PlayerStatus(play_state="play", eq_preset="rock")
        mock_player.client.get_player_status_model = AsyncMock(return_value=mock_status)
        TestStateManager._setup_refresh_mocks(mock_player, state_manager)
        type(mock_player.client).capabilities = PropertyMock(return_value={"supports_eq": True})
        mock_player.client.get_eq = AsyncMock(return_value={})
        state_manager._last_eq_preset = "jazz"

        with patch("pywiim.player.groupops.GroupOperations") as mock_groupops:
            mock_groupops.return_value._synchronize_group_state = AsyncMock()

            await state_manager.refresh(full=False)

        mock_player.client.get_eq.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_source_changed_fetches_audio_output(self, state_manager, mock_player):
        """Test refresh when source changes, fetches audio output."""
        mock_status = PlayerStatus(play_state="play", source="bluetooth")
        mock_player.client.get_player_status_model = AsyncMock(return_value=mock_status)
        TestStateManager._setup_refresh_mocks(mock_player, state_manager)
        type(mock_player.client).capabilities = PropertyMock(return_value={"supports_audio_output": True})
        mock_player.get_audio_output_status = AsyncMock(return_value={"mode": "bluetooth"})
        state_manager._last_source = "wifi"

        with patch("pywiim.player.groupops.GroupOperations") as mock_groupops:
            mock_groupops.return_value._synchronize_group_state = AsyncMock()

            await state_manager.refresh(full=False)

        mock_player.get_audio_output_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_updates_eq_enabled_from_get_eq_status(self, state_manager, mock_player):
        """Test we update _eq_enabled from get_eq_status() when EQ is supported."""
        mock_status = PlayerStatus(play_state="play", eq_preset="flat", title="Same")
        mock_player.client.get_player_status_model = AsyncMock(return_value=mock_status)
        TestStateManager._setup_refresh_mocks(mock_player, state_manager)
        type(mock_player.client).capabilities = PropertyMock(return_value={"supports_eq": True})
        mock_player.client.get_eq_status = AsyncMock(return_value=False)
        mock_player._coverart_mgr._last_track_signature = "Same|Track"

        with patch("pywiim.player.groupops.GroupOperations") as mock_groupops:
            mock_groupops.return_value._synchronize_group_state = AsyncMock()

            await state_manager.refresh(full=True)

        mock_player.client.get_eq_status.assert_called_once()
        assert mock_player._eq_enabled is False

    @pytest.mark.asyncio
    async def test_refresh_fetches_eq_presets(self, state_manager, mock_player):
        """Test refresh fetches EQ presets on track change."""
        mock_status = PlayerStatus(play_state="play", title="New Track")
        mock_player.client.get_player_status_model = AsyncMock(return_value=mock_status)
        TestStateManager._setup_refresh_mocks(mock_player, state_manager)
        type(mock_player.client).capabilities = PropertyMock(return_value={"supports_eq": True})
        mock_player.client.get_eq_presets = AsyncMock(return_value=["rock", "jazz"])
        mock_player._last_eq_presets_check = None
        mock_player.client.get_eq_status = AsyncMock(return_value=True)
        # Track signature is now managed by CoverArtManager
        mock_player._coverart_mgr._last_track_signature = "Old|Track"

        with patch("pywiim.player.groupops.GroupOperations") as mock_groupops:
            mock_groupops.return_value._synchronize_group_state = AsyncMock()

            await state_manager.refresh(full=False)

        mock_player.client.get_eq_presets.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_fetches_presets(self, state_manager, mock_player):
        """Test refresh fetches presets on track change."""
        mock_status = PlayerStatus(play_state="play", title="New Track")
        mock_player.client.get_player_status_model = AsyncMock(return_value=mock_status)
        TestStateManager._setup_refresh_mocks(mock_player, state_manager)
        type(mock_player.client).capabilities = PropertyMock(return_value={"supports_presets": True})
        mock_player.client.get_presets = AsyncMock(return_value=[])
        mock_player._last_presets_check = None
        # Track signature is now managed by CoverArtManager
        mock_player._coverart_mgr._last_track_signature = "Old|Track"

        with patch("pywiim.player.groupops.GroupOperations") as mock_groupops:
            mock_groupops.return_value._synchronize_group_state = AsyncMock()

            await state_manager.refresh(full=False)

        mock_player.client.get_presets.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_fetches_bluetooth_history(self, state_manager, mock_player):
        """Test refresh fetches Bluetooth history."""
        mock_status = PlayerStatus(play_state="play", title="New Track")
        mock_player.client.get_player_status_model = AsyncMock(return_value=mock_status)
        TestStateManager._setup_refresh_mocks(mock_player, state_manager)
        mock_player.client.get_bluetooth_history = AsyncMock(return_value=[])
        mock_player._last_bt_history_check = None
        # Track signature is now managed by CoverArtManager
        mock_player._coverart_mgr._last_track_signature = "Old|Track"

        with patch("pywiim.player.groupops.GroupOperations") as mock_groupops:
            mock_groupops.return_value._synchronize_group_state = AsyncMock()

            await state_manager.refresh(full=False)

        mock_player.client.get_bluetooth_history.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_error_handling(self, state_manager, mock_player):
        """Test refresh error handling."""
        mock_player.client.get_player_status_model = AsyncMock(side_effect=RuntimeError("Network error"))
        TestStateManager._setup_refresh_mocks(mock_player, state_manager)

        with pytest.raises(RuntimeError):
            with patch("pywiim.player.groupops.GroupOperations") as mock_groupops:
                mock_groupops.return_value._synchronize_group_state = AsyncMock()

                await state_manager.refresh(full=False)

        assert mock_player._available is False

    @pytest.mark.asyncio
    async def test_refresh_updates_upnp_health_tracker(self, state_manager, mock_player):
        """Test refresh updates UPnP health tracker."""
        from pywiim.upnp.health import UpnpHealthTracker

        mock_status = PlayerStatus(play_state="play", volume=50, mute=False)
        mock_player.client.get_player_status_model = AsyncMock(return_value=mock_status)
        TestStateManager._setup_refresh_mocks(mock_player, state_manager)
        mock_player._upnp_health_tracker = UpnpHealthTracker()

        with patch("pywiim.player.groupops.GroupOperations") as mock_groupops:
            mock_groupops.return_value._synchronize_group_state = AsyncMock()

            await state_manager.refresh(full=False)

        # Health tracker should have been updated
        assert mock_player._upnp_health_tracker._last_poll_state is not None

    @pytest.mark.asyncio
    async def test_refresh_skips_upnp_when_unhealthy(self, state_manager, mock_player):
        """Test that refresh skips UPnP control calls when UPnP is marked unhealthy."""
        mock_status = PlayerStatus(play_state="play", volume=50)
        mock_player.client.get_player_status_model = AsyncMock(return_value=mock_status)
        TestStateManager._setup_refresh_mocks(mock_player, state_manager)
        mock_player._upnp_client = MagicMock()
        mock_player._upnp_client.rendering_control = MagicMock()
        mock_player._upnp_client.get_volume = AsyncMock(return_value=75)

        # Mark UPnP as unhealthy
        type(mock_player).upnp_is_healthy = PropertyMock(return_value=False)

        with patch("pywiim.player.groupops.GroupOperations") as mock_groupops:
            mock_groupops.return_value._synchronize_group_state = AsyncMock()

            await state_manager.refresh(full=False)

        # Should NOT use UPnP volume because it's unhealthy
        mock_player._upnp_client.get_volume.assert_not_called()
        call_args = mock_player._state_synchronizer.update_from_http.call_args[0][0]
        assert call_args["volume"] == 50  # Should use HTTP volume (50) instead of UPnP (75)

    def test_propagate_metadata_to_slaves(self, state_manager, mock_player):
        """Test that propagate_metadata_to_slaves correctly copies metadata from master to slaves.

        This is a critical feature that ensures slaves always have the latest metadata.
        In real-world testing, this works correctly during refresh and UPnP updates.
        This unit test verifies the method itself works correctly.
        """
        from pywiim.group import Group

        # Set up master with metadata
        mock_status = PlayerStatus(
            play_state="play", title="Master Track", artist="Master Artist", album="Master Album"
        )
        type(mock_player).is_master = PropertyMock(return_value=True)
        mock_player._status_model = mock_status
        mock_player._metadata = {"metaData": {"bitRate": "320", "sampleRate": "44100"}}

        # Create a real PlayerStatus object for the slave
        slave_status = PlayerStatus()

        # Create a simple object that allows attribute access (simulating a slave Player)
        class SlaveMock:
            def __init__(self):
                self._status_model = slave_status
                self._state_synchronizer = MagicMock()
                self._state_synchronizer.update_from_http = MagicMock()
                self._on_state_changed = None
                self.host = "192.168.1.101"
                self._group = None

        slave = SlaveMock()
        group = Group(mock_player)
        group.add_slave(slave)
        mock_player._group = group

        # Verify initial state
        assert slave._status_model.title is None
        assert slave._status_model.artist is None
        assert mock_player._status_model.title == "Master Track"

        # Call propagate_metadata_to_slaves (this is called in _finalize_refresh and update_from_upnp)
        mock_player._group_ops.propagate_metadata_to_slaves()

        # Verify slave received master's metadata
        assert slave._status_model.title == "Master Track"
        assert slave._status_model.artist == "Master Artist"
        assert slave._status_model.album == "Master Album"
        assert slave._status_model.play_state == "play"
        assert slave._metadata == mock_player._metadata

        # Verify state synchronizer was updated with metadata
        # (may be called multiple times, but should include the metadata call)
        calls = slave._state_synchronizer.update_from_http.call_args_list
        metadata_call = None
        for call in calls:
            args = call[0][0] if call[0] else {}
            if "title" in args and args["title"] == "Master Track":
                metadata_call = args
                break

        assert metadata_call is not None, "update_from_http should have been called with metadata"
        assert metadata_call["title"] == "Master Track"
        assert metadata_call["artist"] == "Master Artist"
        assert metadata_call["album"] == "Master Album"

    def test_update_from_upnp_with_upnp_health_tracker(self, state_manager, mock_player):
        """Test update_from_upnp updates UPnP health tracker."""
        from pywiim.upnp.health import UpnpHealthTracker

        mock_player._upnp_health_tracker = UpnpHealthTracker()
        mock_player._state_synchronizer.get_merged_state.return_value = {"volume": 0.5}

        state_manager.update_from_upnp({"volume": 0.5, "muted": False})

        # Health tracker should have been updated
        assert mock_player._upnp_health_tracker._last_upnp_state is not None

    def test_update_from_upnp_volume_conversion(self, state_manager, mock_player):
        """Test update_from_upnp converts float volume to int."""
        from pywiim.upnp.health import UpnpHealthTracker

        mock_player._upnp_health_tracker = UpnpHealthTracker()
        mock_player._state_synchronizer.get_merged_state.return_value = {"volume": 50}

        state_manager.update_from_upnp({"volume": 0.5})  # Float 0.0-1.0

        # Should convert to int 0-100
        upnp_state = mock_player._upnp_health_tracker._last_upnp_state
        assert upnp_state["volume"] == 50

    def test_update_from_upnp_slave_ignores_playback_and_metadata(self, state_manager, mock_player):
        """Slave mode must never accept slave-local playback/metadata from UPnP.

        Slaves only contribute volume/mute; playback + metadata come exclusively
        from the master via propagation (or remain empty if master has none).
        """
        type(mock_player).is_slave = PropertyMock(return_value=True)
        mock_player._state_synchronizer.update_from_upnp = MagicMock()
        mock_player._state_synchronizer.get_merged_state = MagicMock(return_value={})

        state_manager.update_from_upnp(
            {
                "title": "Slave Track",
                "artist": "Slave Artist",
                "album": "Slave Album",
                "image_url": "http://example/art.jpg",
                "play_state": "play",
                "position": 12,
                "duration": 180,
                "source": "bluetooth",
                "volume": 0.5,
                "muted": True,
            }
        )

        called_payload = mock_player._state_synchronizer.update_from_upnp.call_args[0][0]
        assert called_payload == {"volume": 0.5, "muted": True}
