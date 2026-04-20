"""Unit tests for AudioConfiguration.

Tests audio configuration operations including EQ, output modes, and settings.
"""

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from pywiim.api.base import ApiResponse
from pywiim.models import PlayerStatus


class TestAudioConfiguration:
    """Test AudioConfiguration class."""

    @pytest.fixture
    def mock_player(self, mock_client):
        """Create a mock Player instance."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._status_model = PlayerStatus()
        player._audio_output_status = None
        player._on_state_changed = None
        player._properties = MagicMock()
        player._properties.bluetooth_output_devices = []
        # Mock is_bluetooth_output_active property
        type(player).is_bluetooth_output_active = PropertyMock(return_value=False)

        # Mock audio_output_mode property to read from _audio_output_status
        def audio_output_mode_getter():
            if player._audio_output_status is None:
                return None
            hardware_mode = player._audio_output_status.get("hardware")
            if hardware_mode is None:
                return None
            # Simple mapping for test
            mode_int = int(hardware_mode) if isinstance(hardware_mode, str) else hardware_mode
            mode_map = {0: "Line Out", 1: "Optical Out", 2: "Coax Out", 3: "Headphone Out", 4: "Bluetooth Out"}
            return mode_map.get(mode_int)

        type(player).audio_output_mode = PropertyMock(side_effect=audio_output_mode_getter)
        # Also set on properties mock
        player._properties.audio_output_mode = PropertyMock(side_effect=audio_output_mode_getter)

        # Mock source property to match Player's current semantics:
        # - player.source -> stable id (matches source_catalog ids)
        # - computed from state synchronizer / status_model
        def source_id_getter():
            from pywiim.player.properties import PlayerProperties

            return PlayerProperties(player).source

        type(player).source = PropertyMock(side_effect=source_id_getter)
        player._properties.source = PropertyMock(side_effect=source_id_getter)
        return player

    @pytest.fixture
    def audio_config(self, mock_player):
        """Create an AudioConfiguration instance."""
        from pywiim.player.audio import AudioConfiguration

        return AudioConfiguration(mock_player)

    @pytest.mark.asyncio
    async def test_set_source(self, audio_config, mock_player):
        """Test setting audio source."""
        mock_player.client.set_source = AsyncMock()
        mock_player._on_state_changed = MagicMock()
        mock_player._status_model = PlayerStatus()

        await audio_config.set_source("wifi")

        mock_player.client.set_source.assert_called_once_with("wifi")
        assert mock_player._status_model.source == "wifi"
        mock_player._on_state_changed.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_source_updates_status_model(self, audio_config, mock_player):
        """Test that set_source() updates _status_model.source immediately."""
        mock_player.client.set_source = AsyncMock()
        mock_player._status_model = PlayerStatus(source="bluetooth")

        # Before: source is "bluetooth"
        assert mock_player._status_model.source == "bluetooth"

        # Call set_source
        await audio_config.set_source("wifi")

        # After: _status_model.source should be updated immediately (optimistic update)
        assert mock_player._status_model.source == "wifi"
        mock_player.client.set_source.assert_called_once_with("wifi")

    @pytest.mark.asyncio
    async def test_set_source_property_reflects_change(self, audio_config, mock_player):
        """Test that source property reflects the change after set_source."""
        from pywiim.models import PlayerStatus

        mock_player.client.set_source = AsyncMock()
        mock_player._status_model = PlayerStatus(source="bluetooth")
        # Mock state synchronizer to return None (so it falls back to _status_model)
        mock_player._state_synchronizer = MagicMock()
        mock_player._state_synchronizer.get_merged_state = MagicMock(return_value={})

        # Before: source should be "bluetooth"
        assert mock_player.source == "bluetooth"

        # Call set_source
        await audio_config.set_source("wifi")

        # After: source property should reflect the change (reads from _status_model as fallback)
        assert mock_player._status_model.source == "wifi"
        # `source` is stable id; wifi maps to network
        assert mock_player.source == "network"

    @pytest.mark.asyncio
    async def test_set_source_refresh_updates_state_synchronizer(self, audio_config, mock_player):
        """Test that refresh after set_source() updates state synchronizer with device state."""
        from pywiim.models import PlayerStatus

        mock_player.client.set_source = AsyncMock()
        mock_player._status_model = PlayerStatus(source="bluetooth")
        mock_player._state_synchronizer = MagicMock()
        mock_player._state_synchronizer.get_merged_state = MagicMock(return_value={})
        mock_player._state_synchronizer.update_from_http = MagicMock()

        # Mock refresh to simulate what it does - updates state synchronizer
        async def mock_refresh(full=False):
            # Simulate refresh getting status from device
            status = PlayerStatus(source="wifi")  # Device confirms the change
            mock_player._status_model = status
            # Refresh updates state synchronizer
            mock_player._state_synchronizer.update_from_http({"source": "wifi"})
            # Update merged state to include the new source
            mock_player._state_synchronizer.get_merged_state = MagicMock(return_value={"source": "wifi"})

        mock_player.refresh = AsyncMock(side_effect=mock_refresh)

        # Call set_source (optimistic update)
        await audio_config.set_source("wifi")
        assert mock_player._status_model.source == "wifi"

        # Call refresh to sync with device
        await mock_player.refresh(full=False)

        # Verify state synchronizer was updated
        mock_player._state_synchronizer.update_from_http.assert_called()
        # Verify source property now reads from state synchronizer
        assert mock_player.source == "network"

    @pytest.mark.asyncio
    async def test_set_source_propagates_api_errors(self, audio_config, mock_player):
        """Test that errors from the API are properly propagated (not silently swallowed)."""
        from pywiim.exceptions import WiiMRequestError

        # Setup: API call raises an error
        api_error = WiiMRequestError("API call failed")
        mock_player.client.set_source = AsyncMock(side_effect=api_error)
        mock_player._status_model = PlayerStatus(source="bluetooth")

        # Call set_source - should raise the error
        with pytest.raises(WiiMRequestError) as exc_info:
            await audio_config.set_source("wifi")

        # Verify the error was propagated
        assert exc_info.value == api_error
        # Verify _status_model was NOT updated (since API call failed)
        assert mock_player._status_model.source == "bluetooth"
        # Verify callback was NOT called
        assert (
            not hasattr(mock_player, "_on_state_changed")
            or mock_player._on_state_changed is None
            or not hasattr(mock_player._on_state_changed, "call_count")
            or mock_player._on_state_changed.call_count == 0
        )

    @pytest.mark.asyncio
    async def test_set_audio_output_mode_string(self, audio_config, mock_player):
        """Test setting audio output mode by string."""
        mock_player.client.set_audio_output_mode = AsyncMock()
        mock_player.refresh = AsyncMock()
        mock_player._on_state_changed = MagicMock()

        await audio_config.set_audio_output_mode("Line Out")

        mock_player.client.set_audio_output_mode.assert_called_once_with("Line Out")
        mock_player.refresh.assert_called_once_with(full=True)
        mock_player._on_state_changed.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_audio_output_mode_int(self, audio_config, mock_player):
        """Test setting audio output mode by integer."""
        mock_player.client.set_audio_output_mode = AsyncMock()
        mock_player.refresh = AsyncMock()

        await audio_config.set_audio_output_mode(2)

        mock_player.client.set_audio_output_mode.assert_called_once_with(2)

    @pytest.mark.asyncio
    async def test_select_output_hardware(self, audio_config, mock_player):
        """Test selecting hardware output."""
        mock_player.is_bluetooth_output_active = False
        mock_player.client.set_audio_output_mode = AsyncMock()
        mock_player.refresh = AsyncMock()
        mock_player._on_state_changed = MagicMock()

        await audio_config.select_output("Optical Out")

        mock_player.client.set_audio_output_mode.assert_called_once_with("Optical Out")

    @pytest.mark.asyncio
    async def test_select_output_bluetooth_device(self, audio_config, mock_player):
        """Test selecting specific Bluetooth device."""
        mock_player._properties.bluetooth_output_devices = [
            {"name": "Sony Speaker", "mac": "AA:BB:CC:DD:EE:01", "connected": False},
        ]
        mock_player.connect_bluetooth_device = AsyncMock()
        mock_player.refresh = AsyncMock()

        await audio_config.select_output("BT: Sony Speaker")

        mock_player.connect_bluetooth_device.assert_called_once_with("AA:BB:CC:DD:EE:01")

    @pytest.mark.asyncio
    async def test_select_output_bluetooth_device_not_found(self, audio_config, mock_player):
        """Test selecting non-existent Bluetooth device."""
        mock_player._properties.bluetooth_output_devices = [
            {"name": "Other Device", "mac": "AA:BB:CC:DD:EE:01"},
        ]

        with pytest.raises(ValueError, match="not found"):
            await audio_config.select_output("BT: Sony Speaker")

    @pytest.mark.asyncio
    async def test_select_output_bluetooth_generic(self, audio_config, mock_player):
        """Test selecting generic Bluetooth output."""
        mock_player._properties.bluetooth_output_devices = [
            {"name": "Device 1", "mac": "AA:BB:CC:DD:EE:01", "connected": True},
            {"name": "Device 2", "mac": "AA:BB:CC:DD:EE:02", "connected": False},
        ]
        mock_player.connect_bluetooth_device = AsyncMock()

        await audio_config.select_output("Bluetooth Out")

        # Should connect to the connected device
        mock_player.connect_bluetooth_device.assert_called_once_with("AA:BB:CC:DD:EE:01")

    @pytest.mark.asyncio
    async def test_select_output_bluetooth_generic_no_devices(self, audio_config, mock_player):
        """Test selecting generic Bluetooth when no devices paired."""
        mock_player._properties.bluetooth_output_devices = []

        with pytest.raises(ValueError, match="No paired Bluetooth devices"):
            await audio_config.select_output("Bluetooth Out")

    @pytest.mark.asyncio
    async def test_select_output_hardware_with_bt_active(self, audio_config, mock_player):
        """Test selecting hardware output when Bluetooth is active."""
        type(mock_player).is_bluetooth_output_active = PropertyMock(return_value=True)
        mock_player.disconnect_bluetooth_device = AsyncMock()
        mock_player.client.set_audio_output_mode = AsyncMock()
        mock_player.refresh = AsyncMock()

        await audio_config.select_output("Line Out")

        mock_player.disconnect_bluetooth_device.assert_called_once()
        mock_player.client.set_audio_output_mode.assert_called_once_with("Line Out")

    @pytest.mark.asyncio
    async def test_select_output_hardware_bt_disconnect_fails(self, audio_config, mock_player):
        """Test selecting hardware output when BT disconnect fails."""
        type(mock_player).is_bluetooth_output_active = PropertyMock(return_value=True)
        mock_player.disconnect_bluetooth_device = AsyncMock(side_effect=Exception("Disconnect error"))
        mock_player.client.set_audio_output_mode = AsyncMock()
        mock_player.refresh = AsyncMock()

        # Should continue even if disconnect fails
        await audio_config.select_output("Line Out")

        mock_player.disconnect_bluetooth_device.assert_called_once()
        mock_player.client.set_audio_output_mode.assert_called_once_with("Line Out")

    @pytest.mark.asyncio
    async def test_set_led(self, audio_config, mock_player):
        """Test setting LED state."""
        mock_player.client.set_led = AsyncMock()

        await audio_config.set_led(True)

        mock_player.client.set_led.assert_called_once_with(True)

    @pytest.mark.asyncio
    async def test_set_led_brightness(self, audio_config, mock_player):
        """Test setting LED brightness."""
        mock_player.client.set_led_brightness = AsyncMock()

        await audio_config.set_led_brightness(50)

        mock_player.client.set_led_brightness.assert_called_once_with(50)

    @pytest.mark.asyncio
    async def test_set_led_brightness_invalid(self, audio_config, mock_player):
        """Test setting invalid LED brightness."""
        with pytest.raises(ValueError, match="between 0 and 100"):
            await audio_config.set_led_brightness(150)

    @pytest.mark.asyncio
    async def test_set_channel_balance(self, audio_config, mock_player):
        """Test setting channel balance."""
        mock_player.client.set_channel_balance = AsyncMock()
        mock_player._on_state_changed = MagicMock()

        await audio_config.set_channel_balance(0.5)

        mock_player.client.set_channel_balance.assert_called_once_with(0.5)
        assert mock_player._channel_balance == 0.5
        mock_player._on_state_changed.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_channel_balance_not_supported(self, audio_config, mock_player):
        """When capability is false, get_channel_balance does not HTTP."""
        mock_player.client._capabilities = {"supports_channel_balance": False}
        mock_player.client._request = AsyncMock()

        result = await audio_config.get_channel_balance()

        assert result is None
        mock_player.client._request.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_channel_balance_success(self, audio_config, mock_player):
        """Read balance parses numeric JSON from getChannelBalance."""
        mock_player.client._capabilities = {"supports_channel_balance": True}
        mock_player.client._request = AsyncMock(return_value=ApiResponse(parsed=-0.25, raw=None))

        result = await audio_config.get_channel_balance()

        assert result == -0.25
        mock_player.client._request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_channel_balance_unknown_command(self, audio_config, mock_player):
        """Non-numeric body returns None."""
        mock_player.client._capabilities = {"supports_channel_balance": True}
        mock_player.client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="unknown command"))

        result = await audio_config.get_channel_balance()

        assert result is None

    @pytest.mark.asyncio
    async def test_set_channel_balance_invalid(self, audio_config, mock_player):
        """Test setting invalid channel balance."""
        with pytest.raises(ValueError, match="between -1.0 and 1.0"):
            await audio_config.set_channel_balance(1.5)

    @pytest.mark.asyncio
    async def test_set_eq_preset(self, audio_config, mock_player):
        """Test setting EQ preset."""
        mock_player.client.set_eq_preset = AsyncMock()
        mock_player._on_state_changed = MagicMock()
        mock_player._eq_presets = ["Flat", "Rock"]

        await audio_config.set_eq_preset("rock")

        mock_player.client.set_eq_preset.assert_called_once_with("rock", available_presets=["Flat", "Rock"])
        assert mock_player._status_model.eq_preset == "rock"
        mock_player._on_state_changed.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_eq_preset_dynamic_device_label(self, audio_config, mock_player):
        """Test setting device-reported presets outside the built-in map."""
        mock_player.client.set_eq_preset = AsyncMock()
        mock_player._on_state_changed = MagicMock()
        mock_player._eq_presets = ["Flat", "Vocal Booster", "My Movie Night"]

        await audio_config.set_eq_preset("vocal booster")

        mock_player.client.set_eq_preset.assert_called_once_with(
            "vocal booster",
            available_presets=["Flat", "Vocal Booster", "My Movie Night"],
        )
        assert mock_player._status_model.eq_preset == "Vocal Booster"

    @pytest.mark.asyncio
    async def test_set_eq_custom(self, audio_config, mock_player):
        """Test setting custom EQ values."""
        mock_player.client.set_eq_custom = AsyncMock()
        mock_player._on_state_changed = MagicMock()

        eq_values = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
        await audio_config.set_eq_custom(eq_values)

        mock_player.client.set_eq_custom.assert_called_once_with(eq_values)
        mock_player._on_state_changed.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_eq_enabled(self, audio_config, mock_player):
        """Test enabling/disabling EQ."""
        mock_player.client.set_eq_enabled = AsyncMock()
        mock_player._on_state_changed = MagicMock()

        await audio_config.set_eq_enabled(True)

        mock_player.client.set_eq_enabled.assert_called_once_with(True)
        mock_player._on_state_changed.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_eq(self, audio_config, mock_player):
        """Test getting EQ values."""
        expected_eq = {"band1": 0, "band2": 1}
        mock_player.client.get_eq = AsyncMock(return_value=expected_eq)

        result = await audio_config.get_eq()

        assert result == expected_eq
        mock_player.client.get_eq.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_eq_presets(self, audio_config, mock_player):
        """Test getting EQ presets."""
        expected_presets = ["rock", "jazz", "pop"]
        mock_player.client.get_eq_presets = AsyncMock(return_value=expected_presets)

        result = await audio_config.get_eq_presets()

        assert result == expected_presets
        mock_player.client.get_eq_presets.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_eq_status(self, audio_config, mock_player):
        """Test getting EQ status."""
        mock_player.client.get_eq_status = AsyncMock(return_value=True)

        result = await audio_config.get_eq_status()

        assert result is True
        mock_player.client.get_eq_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_multiroom_status(self, audio_config, mock_player):
        """Test getting multiroom status."""
        expected_status = {"group": "test-group"}
        mock_player.client.get_multiroom_status = AsyncMock(return_value=expected_status)

        result = await audio_config.get_multiroom_status()

        assert result == expected_status
        mock_player.client.get_multiroom_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_audio_output_status(self, audio_config, mock_player):
        """Test getting audio output status."""
        expected_status = {"mode": "hardware", "source": "line"}
        mock_player.client.get_audio_output_status = AsyncMock(return_value=expected_status)

        result = await audio_config.get_audio_output_status()

        assert result == expected_status
        assert mock_player._audio_output_status == expected_status
        mock_player.client.get_audio_output_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_meta_info(self, audio_config, mock_player):
        """Test getting meta info."""
        # get_meta_info may not exist in all API versions, skip if not available
        if not hasattr(mock_player.client, "get_meta_info"):
            pytest.skip("get_meta_info not available in this API version")

        expected_info = {"title": "Test", "artist": "Artist"}
        mock_player.client.get_meta_info = AsyncMock(return_value=expected_info)

        result = await audio_config.get_meta_info()

        assert result == expected_info
        mock_player.client.get_meta_info.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_audio_output_mode_updates_cache_after_refresh(self, audio_config, mock_player):
        """Test that set_audio_output_mode() refresh actually updates _audio_output_status."""
        # Setup: initial state has no audio output status
        mock_player._audio_output_status = None
        mock_player.client.set_audio_output_mode = AsyncMock()
        type(mock_player.client).capabilities = PropertyMock(return_value={"supports_audio_output": True})

        # New audio output status that should be set after refresh
        new_audio_output_status = {"hardware": 0, "source": 0}
        mock_player.client.get_audio_output_status = AsyncMock(return_value=new_audio_output_status)

        # Mock the refresh method to actually call get_audio_output_status
        async def mock_refresh(full=False):
            # Simulate what refresh does - it calls get_audio_output_status
            audio_output_status = await mock_player.get_audio_output_status()
            mock_player._audio_output_status = audio_output_status

        mock_player.refresh = AsyncMock(side_effect=mock_refresh)

        # Call set_audio_output_mode
        await audio_config.set_audio_output_mode("Line Out")

        # Verify API was called
        mock_player.client.set_audio_output_mode.assert_called_once_with("Line Out")
        # Verify refresh was called
        mock_player.refresh.assert_called_once_with(full=True)
        # Verify _audio_output_status was updated
        assert mock_player._audio_output_status == new_audio_output_status
        # Verify get_audio_output_status was called during refresh
        mock_player.client.get_audio_output_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_audio_output_mode_property_reflects_change(self, audio_config, mock_player):
        """Test that audio_output_mode property reflects the change after refresh."""
        # Setup: initial state
        mock_player._audio_output_status = None
        mock_player.client.set_audio_output_mode = AsyncMock()
        type(mock_player.client).capabilities = PropertyMock(return_value={"supports_audio_output": True})
        mock_player.client.audio_output_mode_to_name = MagicMock(return_value="Line Out")

        # New audio output status after refresh
        new_audio_output_status = {"hardware": 0, "source": 0}
        mock_player.client.get_audio_output_status = AsyncMock(return_value=new_audio_output_status)

        # Mock refresh to update _audio_output_status
        async def mock_refresh(full=False):
            audio_output_status = await mock_player.get_audio_output_status()
            mock_player._audio_output_status = audio_output_status

        mock_player.refresh = AsyncMock(side_effect=mock_refresh)

        # Before: audio_output_mode should be None
        assert mock_player.audio_output_mode is None

        # Call set_audio_output_mode
        await audio_config.set_audio_output_mode("Line Out")

        # After: _audio_output_status should be updated
        assert mock_player._audio_output_status == new_audio_output_status
        # Verify the property reflects the change
        # The property reads from _audio_output_status via _properties
        assert mock_player.audio_output_mode == "Line Out"

    @pytest.mark.asyncio
    async def test_set_audio_output_mode_propagates_api_errors(self, audio_config, mock_player):
        """Test that errors from the API are properly propagated (not silently swallowed)."""
        from pywiim.exceptions import WiiMRequestError

        # Setup: API call raises an error
        api_error = WiiMRequestError("API call failed")
        mock_player.client.set_audio_output_mode = AsyncMock(side_effect=api_error)

        # Call set_audio_output_mode - should raise the error
        with pytest.raises(WiiMRequestError) as exc_info:
            await audio_config.set_audio_output_mode("Line Out")

        # Verify the error was propagated
        assert exc_info.value == api_error
        # Verify refresh was NOT called (since API call failed)
        assert (
            not hasattr(mock_player, "refresh")
            or not hasattr(mock_player.refresh, "call_count")
            or mock_player.refresh.call_count == 0
        )

    @pytest.mark.asyncio
    async def test_set_audio_output_mode_propagates_refresh_errors(self, audio_config, mock_player):
        """Test that errors from refresh are properly propagated."""
        from pywiim.exceptions import WiiMConnectionError

        # Setup: API call succeeds but refresh fails
        mock_player.client.set_audio_output_mode = AsyncMock()
        refresh_error = WiiMConnectionError("Refresh failed")
        mock_player.refresh = AsyncMock(side_effect=refresh_error)

        # Call set_audio_output_mode - should raise the refresh error
        with pytest.raises(WiiMConnectionError) as exc_info:
            await audio_config.set_audio_output_mode("Line Out")

        # Verify the error was propagated
        assert exc_info.value == refresh_error
        # Verify API was called
        mock_player.client.set_audio_output_mode.assert_called_once_with("Line Out")
        # Verify refresh was attempted
        mock_player.refresh.assert_called_once_with(full=True)


class TestSourceNormalization:
    """Test source name normalization for API calls.

    The WiiM/LinkPlay API's switchmode command expects specific formats:
    - Multi-word sources use hyphens: "line-in" (NOT "line_in")
    - Single-word sources are lowercase: "wifi", "bluetooth", "optical"

    These tests ensure the normalization converts various user inputs to
    the correct API format. See GitHub issue #153.
    """

    @pytest.fixture
    def audio_config(self, mock_client):
        """Create an AudioConfiguration instance."""
        from pywiim.player import Player
        from pywiim.player.audio import AudioConfiguration

        player = Player(mock_client)
        return AudioConfiguration(player)

    # Line In variations - all should become "line-in"
    @pytest.mark.parametrize(
        "input_source,expected",
        [
            ("Line In", "line-in"),  # Title case with space (from available_sources)
            ("line in", "line-in"),  # Lowercase with space
            ("line_in", "line-in"),  # Underscore (common API format)
            ("line-in", "line-in"),  # Hyphenated (correct API format)
            ("linein", "line-in"),  # No separator
            ("LINE IN", "line-in"),  # Uppercase
            ("Line_In", "line-in"),  # Mixed case with underscore
            ("Line-In", "line-in"),  # Mixed case with hyphen
        ],
    )
    def test_normalize_source_line_in(self, audio_config, input_source, expected):
        """Test Line In normalization to API format (line-in)."""
        result = audio_config._normalize_source_for_api(input_source)
        assert result == expected

    # Line In 2 variations
    @pytest.mark.parametrize(
        "input_source,expected",
        [
            ("Line In 2", "line-in-2"),
            ("line_in_2", "line-in-2"),
            ("line-in-2", "line-in-2"),
            ("linein_2", "line-in-2"),
        ],
    )
    def test_normalize_source_line_in_2(self, audio_config, input_source, expected):
        """Test Line In 2 normalization."""
        result = audio_config._normalize_source_for_api(input_source)
        assert result == expected

    # Coaxial variations
    @pytest.mark.parametrize(
        "input_source,expected",
        [
            ("Coaxial", "coaxial"),
            ("coaxial", "coaxial"),
            ("coax", "coaxial"),
            ("Coax", "coaxial"),
            ("CoaxIal", "coaxial"),  # Bug report: device returns wrong capitalization
        ],
    )
    def test_normalize_source_coaxial(self, audio_config, input_source, expected):
        """Test Coaxial normalization."""
        result = audio_config._normalize_source_for_api(input_source)
        assert result == expected

    # WiFi variations
    @pytest.mark.parametrize(
        "input_source,expected",
        [
            ("WiFi", "wifi"),
            ("wifi", "wifi"),
            ("Wi-Fi", "wifi"),
            ("wi-fi", "wifi"),
            ("wi_fi", "wifi"),
            ("Ethernet", "wifi"),  # Ethernet maps to WiFi mode
            ("ethernet", "wifi"),
        ],
    )
    def test_normalize_source_wifi(self, audio_config, input_source, expected):
        """Test WiFi/Ethernet normalization."""
        result = audio_config._normalize_source_for_api(input_source)
        assert result == expected

    # Single-word sources (no change needed except lowercase)
    @pytest.mark.parametrize(
        "input_source,expected",
        [
            ("Bluetooth", "bluetooth"),
            ("bluetooth", "bluetooth"),
            ("BLUETOOTH", "bluetooth"),
            ("Optical", "optical"),
            ("optical", "optical"),
            ("USB", "usb"),
            ("usb", "usb"),
            ("HDMI", "hdmi"),
            ("hdmi", "hdmi"),
            ("HDMI In", "hdmi"),  # Resilience
            ("HDMI ARC", "hdmi"),
            ("Phono", "phono"),
            ("phono", "phono"),
            ("Phono In", "phono"),  # Resilience
            ("Optical In", "optical"),  # UI standardization (stable since 2.1.58)
            ("Coaxial In", "coaxial"),  # Resilience
            ("Aux", "line-in"),
            ("Aux In", "line-in"),
        ],
    )
    def test_normalize_source_single_word(self, audio_config, input_source, expected):
        """Test single-word source normalization."""
        result = audio_config._normalize_source_for_api(input_source)
        assert result == expected

    def test_normalize_source_device_specific(self, audio_config):
        """Test normalization respecting device-reported input names (smart fallback)."""
        # Mock device info with custom names in InputList
        from pywiim.models import DeviceInfo

        audio_config.player._device_info = DeviceInfo(project="test", DeviceName="Test")
        audio_config.player._device_info.input_list = ["custom_in", "SuperSource", "bluetooth"]

        # Should match custom sources from input_list
        assert audio_config._normalize_source_for_api("Custom In") == "custom_in"
        assert audio_config._normalize_source_for_api("Super Source") == "SuperSource"
        assert audio_config._normalize_source_for_api("super-source") == "SuperSource"

    # Streaming services (pass through as-is, lowercase)
    @pytest.mark.parametrize(
        "input_source,expected",
        [
            ("AirPlay", "airplay"),
            ("airplay", "airplay"),
            ("Spotify", "spotify"),
            ("DLNA", "dlna"),
            ("Amazon", "amazon"),
            ("Tidal", "tidal"),
        ],
    )
    def test_normalize_source_streaming(self, audio_config, input_source, expected):
        """Test streaming service normalization."""
        result = audio_config._normalize_source_for_api(input_source)
        assert result == expected

    # RCA variations (Audio Pro specific)
    @pytest.mark.parametrize(
        "input_source,expected",
        [
            ("RCA", "RCA"),
            ("rca", "RCA"),
            ("Rca", "RCA"),
            ("RCA In", "RCA"),
            ("rca-in", "RCA"),
        ],
    )
    def test_normalize_source_rca(self, audio_config, input_source, expected):
        """Test RCA normalization to uppercase RCA."""
        result = audio_config._normalize_source_for_api(input_source)
        assert result == expected

    # Edge cases
    def test_normalize_source_empty(self, audio_config):
        """Test empty source returns as-is."""
        assert audio_config._normalize_source_for_api("") == ""

    def test_normalize_source_none(self, audio_config):
        """Test None source returns None."""
        assert audio_config._normalize_source_for_api(None) is None

    def test_normalize_source_whitespace(self, audio_config):
        """Test whitespace handling."""
        result = audio_config._normalize_source_for_api("  line in  ")
        assert result == "line-in"

    @pytest.mark.asyncio
    async def test_set_source_uses_normalized_format(self, audio_config, mock_client):
        """Test that set_source uses the normalized API format."""
        mock_client.set_source = AsyncMock()
        audio_config.player._status_model = MagicMock()
        audio_config.player._on_state_changed = None

        # User selects "Line In" from UI (Title Case from available_sources)
        await audio_config.set_source("Line In")

        # API should receive "line-in" (hyphenated format)
        mock_client.set_source.assert_called_once_with("line-in")


class TestEQOffBehavior:
    """Test EQ Off behavior (GitHub issue #165).

    When EQ is disabled, sound_mode should show "Off" instead of the last preset.
    Selecting "Off" should disable EQ, selecting any other preset should enable EQ.
    """

    @pytest.fixture
    def mock_player(self, mock_client):
        """Create a mock Player instance for EQ Off tests."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._status_model = PlayerStatus()
        player._eq_enabled = None  # Not yet fetched
        player._eq_presets = None
        player._on_state_changed = None
        return player

    @pytest.fixture
    def audio_config(self, mock_player):
        """Create an AudioConfiguration instance."""
        from pywiim.player.audio import AudioConfiguration

        return AudioConfiguration(mock_player)

    @pytest.mark.asyncio
    async def test_set_eq_preset_off_disables_eq(self, audio_config, mock_player):
        """Test that setting preset to 'Off' disables EQ instead of setting a preset."""
        mock_player.client.set_eq_enabled = AsyncMock()
        mock_player._on_state_changed = MagicMock()

        await audio_config.set_eq_preset("Off")

        # Should call set_eq_enabled(False), not set_eq_preset
        mock_player.client.set_eq_enabled.assert_called_once_with(False)
        # _eq_enabled should be updated
        assert mock_player._eq_enabled is False

    @pytest.mark.asyncio
    async def test_set_eq_preset_off_case_insensitive(self, audio_config, mock_player):
        """Test that 'off', 'OFF', 'Off' all disable EQ."""
        mock_player.client.set_eq_enabled = AsyncMock()
        mock_player._on_state_changed = MagicMock()

        for off_value in ["off", "OFF", "Off", "oFf"]:
            mock_player.client.set_eq_enabled.reset_mock()
            await audio_config.set_eq_preset(off_value)
            mock_player.client.set_eq_enabled.assert_called_once_with(False)

    @pytest.mark.asyncio
    async def test_set_eq_preset_enables_eq_when_off(self, audio_config, mock_player):
        """Test that setting a preset when EQ is off enables EQ first."""
        mock_player.client.set_eq_enabled = AsyncMock()
        mock_player.client.set_eq_preset = AsyncMock()
        mock_player.client.get_eq = AsyncMock(return_value={"Name": "rock"})
        mock_player._eq_enabled = False  # EQ is currently off
        mock_player._on_state_changed = MagicMock()

        await audio_config.set_eq_preset("rock")

        # Should enable EQ first, then set preset
        mock_player.client.set_eq_enabled.assert_called_once_with(True)
        mock_player.client.set_eq_preset.assert_called_once_with("rock", available_presets=None)
        assert mock_player._eq_enabled is True

    @pytest.mark.asyncio
    async def test_set_eq_preset_does_not_enable_when_already_on(self, audio_config, mock_player):
        """Test that setting a preset when EQ is on doesn't re-enable EQ."""
        mock_player.client.set_eq_enabled = AsyncMock()
        mock_player.client.set_eq_preset = AsyncMock()
        mock_player.client.get_eq = AsyncMock(return_value={"Name": "rock"})
        mock_player._eq_enabled = True  # EQ is already on
        mock_player._on_state_changed = MagicMock()

        await audio_config.set_eq_preset("rock")

        # Should NOT call set_eq_enabled since EQ is already on
        mock_player.client.set_eq_enabled.assert_not_called()
        mock_player.client.set_eq_preset.assert_called_once_with("rock", available_presets=None)

    @pytest.mark.asyncio
    async def test_set_eq_enabled_updates_cached_state(self, audio_config, mock_player):
        """Test that set_eq_enabled updates _eq_enabled immediately."""
        mock_player.client.set_eq_enabled = AsyncMock()
        mock_player._on_state_changed = MagicMock()

        # Enable EQ
        await audio_config.set_eq_enabled(True)
        assert mock_player._eq_enabled is True

        # Disable EQ
        await audio_config.set_eq_enabled(False)
        assert mock_player._eq_enabled is False

    def test_eq_preset_property_returns_off_when_eq_disabled(self, mock_player):
        """Test that eq_preset property returns 'Off' when EQ is disabled."""
        mock_player._eq_enabled = False
        mock_player._status_model = PlayerStatus(eq_preset="flat")

        # Even though there's a preset in status, should return "Off"
        assert mock_player.eq_preset == "Off"

    def test_eq_preset_property_returns_preset_when_eq_enabled(self, mock_player):
        """Test that eq_preset property returns the preset when EQ is enabled."""
        mock_player._eq_enabled = True
        mock_player._status_model = PlayerStatus(eq_preset="rock")

        assert mock_player.eq_preset == "Rock"  # Title Case

    def test_eq_preset_property_returns_preset_when_eq_status_unknown(self, mock_player):
        """Test that eq_preset returns preset when EQ status hasn't been fetched yet."""
        mock_player._eq_enabled = None  # Not yet fetched
        mock_player._status_model = PlayerStatus(eq_preset="jazz")

        # Should return the preset (not "Off") when EQ status is unknown
        assert mock_player.eq_preset == "Jazz"

    def test_eq_presets_includes_off_option(self, mock_player):
        """Test that eq_presets list includes 'Off' as first option."""
        mock_player._eq_presets = ["Flat", "Rock", "Jazz"]

        presets = mock_player.eq_presets

        assert presets[0] == "Off"
        assert "Flat" in presets
        assert "Rock" in presets
        assert "Jazz" in presets

    def test_eq_presets_empty_when_no_presets(self, mock_player):
        """Test that eq_presets returns empty list when no presets available."""
        mock_player._eq_presets = None

        assert mock_player.eq_presets == []

    def test_eq_presets_empty_when_empty_list(self, mock_player):
        """Test that eq_presets returns empty list when presets list is empty."""
        mock_player._eq_presets = []

        # Empty list means no EQ support, so no "Off" option either
        assert mock_player.eq_presets == []
