"""Core integration tests for Player with real devices.

These tests require a real WiiM device to be available on the network.
Set the WIIM_TEST_DEVICE environment variable to enable these tests.

These are fast, safe core tests that validate basic Player functionality.
For comprehensive testing, see test_prerelease.py or use the `wiim-verify` CLI tool.

Example:
    WIIM_TEST_DEVICE=192.168.1.100 pytest -m integration tests/integration/test_real_device.py -v

For HTTPS devices (typical WiiM):
    WIIM_TEST_DEVICE=192.168.1.100 WIIM_TEST_HTTPS=true pytest -m integration tests/integration/test_real_device.py -v

``pytest.ini`` / ``pyproject.toml`` may exclude ``integration`` by default; pass ``-m integration`` to run these tests.
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.integration
@pytest.mark.smoke
@pytest.mark.core  # Alias for backwards compatibility
@pytest.mark.asyncio
class TestRealDeviceCore:
    """Core integration tests with real WiiM devices - fast and safe."""

    async def test_device_connection(self, real_device_client, integration_test_marker):
        """Test basic device connection."""
        device_info = await real_device_client.get_device_info_model()

        assert device_info is not None
        assert device_info.uuid is not None
        assert device_info.model is not None
        assert device_info.firmware is not None

    async def test_capability_detection(self, real_device_client, integration_test_marker):
        """Test automatic capability detection."""
        # Reset capabilities to trigger detection
        real_device_client._capabilities_detected = False
        real_device_client._capabilities = {}

        # Trigger capability detection
        await real_device_client._detect_capabilities()

        assert real_device_client._capabilities_detected is True
        assert "vendor" in real_device_client._capabilities
        assert (
            "is_wiim_device" in real_device_client._capabilities
            or "is_legacy_device" in real_device_client._capabilities
        )
        assert "supports_channel_balance" in real_device_client._capabilities
        assert "supports_subwoofer" in real_device_client._capabilities
        assert "loop_mode_scheme" in real_device_client._capabilities
        caps = real_device_client._capabilities
        if caps.get("is_wiim_device"):
            assert caps["supports_channel_balance"] in (True, False)
            assert caps["supports_subwoofer"] in (True, False, None)
        else:
            assert caps["supports_channel_balance"] is False
            assert caps["supports_subwoofer"] is False

        print("\nCapabilities:")
        print(f"  Vendor: {real_device_client._capabilities.get('vendor')}")
        print(f"  loop_mode_scheme: {real_device_client._capabilities.get('loop_mode_scheme')}")
        print(f"  Is WiiM: {real_device_client._capabilities.get('is_wiim_device')}")
        print(f"  Is Legacy: {real_device_client._capabilities.get('is_legacy_device')}")
        print(f"  Channel balance: {real_device_client._capabilities.get('supports_channel_balance')}")
        print(f"  Subwoofer (getSubLPF): {real_device_client._capabilities.get('supports_subwoofer')}")

    async def test_subwoofer_capability_detection(self, real_device_client, integration_test_marker):
        """getSubLPF probe sets supports_subwoofer; refresh_capabilities re-runs probe.

        Devices without a subwoofer output path typically get supports_subwoofer False;
        status raw read stays None. WiiM-only inconclusive probe may leave None.
        """
        client = real_device_client
        client._capabilities_detected = False
        client._capabilities = {}
        await client._detect_capabilities()

        caps = client.capabilities
        assert "supports_subwoofer" in caps
        sw = caps.get("supports_subwoofer")
        raw = await client.get_subwoofer_status_raw()

        is_wiim = bool(caps.get("is_wiim_device"))
        if is_wiim:
            assert sw in (True, False, None)
            if sw is False:
                assert raw is None
            elif sw is True:
                assert isinstance(raw, dict)
        else:
            assert sw is False
            assert raw is None

        await client.refresh_capabilities(force=True)
        sw2 = client.capabilities.get("supports_subwoofer")
        raw2 = await client.get_subwoofer_status_raw()
        assert sw2 in (True, False, None)
        if is_wiim:
            if sw2 is False:
                assert raw2 is None
            elif sw2 is True:
                assert isinstance(raw2, dict)
        else:
            assert sw2 is False
            assert raw2 is None

        print("\nSubwoofer capability (getSubLPF):")
        print(f"  supports_subwoofer after detect: {sw!r}")
        print(f"  supports_subwoofer after refresh_capabilities: {sw2!r}")

    async def test_player_initialization(self, real_device_player, integration_test_marker):
        """Test Player initialization and basic properties."""
        player = real_device_player

        # Test that player is initialized
        assert player is not None
        assert player.client is not None
        assert player.host is not None

        # Test device info access
        device_info = await player.get_device_info()
        assert device_info is not None
        assert device_info.uuid is not None
        assert device_info.name is not None
        assert device_info.model is not None
        assert device_info.firmware is not None

        print("\nPlayer Info:")
        print(f"  Host: {player.host}")
        print(f"  Name: {device_info.name}")
        print(f"  Model: {device_info.model}")
        print(f"  Firmware: {device_info.firmware}")

    async def test_player_refresh(self, real_device_player, integration_test_marker):
        """Test Player refresh functionality."""
        player = real_device_player

        # Initial refresh
        await player.refresh()

        # Verify state is populated
        assert player._status_model is not None or player._device_info is not None

        # Test full refresh
        await player.refresh(full=True)

        # Verify device info is populated after full refresh
        assert player._device_info is not None
        assert player._device_info.uuid is not None

    async def test_player_properties_access(self, real_device_player, integration_test_marker):
        """Test accessing Player properties."""
        player = real_device_player
        await player.refresh()

        # Test basic properties (may be None if device is off/idle)
        # These should not raise errors even if None
        _ = player.volume_level  # May be None
        _ = player.is_muted  # May be None
        _ = player.play_state  # May be None
        _ = player.source  # May be None
        _ = player.role  # Should always be available (defaults to "solo")

        # Role should always be available
        assert player.role in ("solo", "master", "slave")

        # Test device info properties
        assert player.name is not None
        assert player.model is not None
        assert player.firmware is not None

    async def test_player_status_read(self, real_device_player, integration_test_marker):
        """Test reading player status."""
        player = real_device_player

        # Get status (always queries device)
        status = await player.get_status()

        assert status is not None
        # Status should have at least some fields
        assert hasattr(status, "volume") or hasattr(status, "play_state") or hasattr(status, "source")

        print("\nPlayer Status:")
        print(f"  Volume: {getattr(status, 'volume', None)}")
        print(f"  Play State: {getattr(status, 'play_state', None)}")
        print(f"  Source: {getattr(status, 'source', None)}")

    async def test_player_volume_read(self, real_device_player, integration_test_marker):
        """Test reading volume state."""
        player = real_device_player
        await player.refresh()

        # Test volume getter (may be None)
        volume = await player.get_volume()
        # Volume should be in valid range if not None
        if volume is not None:
            assert 0.0 <= volume <= 1.0

        # Test mute getter (may be None)
        muted = await player.get_muted()
        # Muted should be bool if not None
        if muted is not None:
            assert isinstance(muted, bool)

    async def test_player_volume_controls_safe(self, real_device_player, integration_test_marker):
        """Test volume controls with safe limits and state restoration."""
        player = real_device_player
        await player.refresh()

        # Save initial state
        initial_volume = await player.get_volume()
        initial_mute = await player.get_muted()

        # Skip if we can't read initial state
        if initial_volume is None:
            pytest.skip("Device does not report volume level")

        try:
            # Test volume read
            volume = await player.get_volume()
            assert volume is not None
            assert 0.0 <= volume <= 1.0

            # Test safe volume change (max 10%)
            safe_volume = min(0.10, volume + 0.05) if volume < 0.10 else 0.10
            await player.set_volume(safe_volume)
            await asyncio.sleep(0.5)

            new_volume = await player.get_volume()
            assert new_volume is not None
            assert abs(new_volume - safe_volume) < 0.05

            # Test mute toggle
            await player.set_mute(True)
            await asyncio.sleep(0.5)
            muted = await player.get_muted()
            if muted is not None:
                assert muted is True

            await player.set_mute(False)
            await asyncio.sleep(0.5)
            unmuted = await player.get_muted()
            if unmuted is not None:
                assert unmuted is False

        finally:
            # Restore initial state
            if initial_volume is not None:
                await player.set_volume(initial_volume)
            if initial_mute is not None:
                await player.set_mute(initial_mute)
            await asyncio.sleep(0.5)

    async def test_player_source_list(self, real_device_player, integration_test_marker):
        """Test reading available sources."""
        player = real_device_player
        await player.refresh(full=True)  # Need full refresh to get device info

        # Get available sources (property, not method)
        sources = player.available_sources
        assert sources is not None
        assert isinstance(sources, list)
        assert len(sources) > 0

        print("\nAvailable Sources:")
        for source in sources:
            print(f"  - {source}")

    async def test_player_audio_output_modes(self, real_device_player, integration_test_marker):
        """Test reading audio output modes."""
        player = real_device_player
        # Do full refresh to ensure device info and capabilities are populated
        await player.refresh(full=True)

        # Check capabilities first
        if not player.supports_audio_output:
            pytest.skip("Audio output control not supported on this device (capability check)")

        # Get audio output status
        try:
            status = await player.audio.get_audio_output_status()
            if status is None:
                pytest.skip("Audio output status not available (device may not support this feature)")

            # Verify status has expected fields
            assert "mode" in status or "output" in status or "hardware" in status

            # Test that available_output_modes property works
            available_modes = player.available_output_modes
            assert isinstance(available_modes, list)
            # Most devices should have at least one output mode
            if len(available_modes) > 0:
                print(f"\nAvailable Audio Output Modes: {available_modes}")
                print(f"Current Mode: {player.audio_output_mode}")

        except Exception as e:
            # If we get here, there's an actual error (not just unsupported)
            pytest.fail(f"Error testing audio output modes: {e}")

    async def test_player_state_caching(self, real_device_player, integration_test_marker):
        """Test that Player state caching works correctly."""
        player = real_device_player

        # Initial refresh
        await player.refresh()

        # Get a property (uses cache)
        volume1 = player.volume_level
        device_name1 = player.name

        # Refresh again
        await player.refresh()

        # Properties should still be accessible (may have changed, but shouldn't error)
        volume2 = player.volume_level
        device_name2 = player.name

        # Device name should be consistent (doesn't change)
        assert device_name1 == device_name2

        # Volume might have changed, but should still be valid if not None
        if volume1 is not None and volume2 is not None:
            assert 0.0 <= volume1 <= 1.0
            assert 0.0 <= volume2 <= 1.0

    async def test_player_eq_read(self, real_device_player, integration_test_marker):
        """Test reading EQ status and presets."""
        player = real_device_player
        # Do full refresh to ensure capabilities are detected
        await player.refresh(full=True)

        # Check capabilities first
        if not player.supports_eq:
            pytest.skip("EQ not supported on this device (capability check)")

        try:
            # Get EQ status (enabled/disabled)
            eq_enabled = await player.audio.get_eq_status()
            assert isinstance(eq_enabled, bool)

            # Get current EQ preset
            current_preset = player.eq_preset
            # May be None if EQ is disabled or not set

            # Get EQ presets list
            eq_presets = await player.audio.get_eq_presets()
            if eq_presets is not None:
                assert isinstance(eq_presets, list)
                if len(eq_presets) > 0:
                    print(f"\nAvailable EQ Presets: {eq_presets}")
                    print(f"Current EQ Preset: {current_preset}")
                    print(f"EQ Enabled: {eq_enabled}")

            # Get EQ band values (may fail if EQ not enabled)
            try:
                eq_bands = await player.audio.get_eq()
                if eq_bands is not None:
                    assert isinstance(eq_bands, dict)
            except Exception:
                # EQ bands may not be available if EQ is disabled
                pass

        except Exception as e:
            # If we get here, there's an actual error (not just unsupported)
            pytest.fail(f"Error testing EQ: {e}")

    async def test_player_presets_read(self, real_device_player, integration_test_marker):
        """Test reading playback presets."""
        player = real_device_player
        # Do full refresh to ensure presets are fetched
        await player.refresh(full=True)

        # Check capabilities first
        if not player.supports_presets:
            pytest.skip("Presets not supported on this device (capability check)")

        try:
            # Verify presets_full_data capability
            if player.presets_full_data:
                # WiiM device: Should be able to read preset names
                print("\nDevice supports full preset data (WiiM)")
                presets = player.presets
                if presets:
                    assert isinstance(presets, list)
                    for preset in presets:
                        assert "number" in preset
                        # Should have name if presets_full_data is True
                        if preset.get("name"):
                            print(f"  Preset {preset['number']}: {preset['name']}")
                    print(f"Available Presets: {len(presets)} preset(s)")
                else:
                    print("\nNo presets configured on this device")
            else:
                # LinkPlay device: Only count available
                print("\nDevice supports presets but only count available (LinkPlay)")
                max_slots = await player.client.get_max_preset_slots()
                assert max_slots > 0
                print(f"  Max preset slots: {max_slots}")
                # player.presets should be None or empty
                assert player.presets is None or player.presets == []

        except Exception as e:
            # If we get here, there's an actual error (not just unsupported)
            pytest.fail(f"Error testing presets: {e}")

    async def test_player_subwoofer_read(self, real_device_player, integration_test_marker):
        """Subwoofer: player.supports_subwoofer matches API; read fields when supported."""
        player = real_device_player
        # Do full refresh to ensure capabilities are detected and optional status cache updated
        await player.refresh(full=True)

        # Try to get subwoofer status
        try:
            cap_flag = player.client.capabilities.get("supports_subwoofer")
            status = await player.get_subwoofer_status()

            if not player.supports_subwoofer:
                assert status is None
                assert cap_flag is not True
                print(
                    "\nSubwoofer: not supported or inconclusive for integrations "
                    f"(capabilities supports_subwoofer={cap_flag!r}); status API returned None — OK."
                )
                return

            assert cap_flag is True
            assert status is not None

            # Validate status fields
            assert hasattr(status, "enabled")
            assert hasattr(status, "crossover")
            assert hasattr(status, "phase")
            assert hasattr(status, "level")
            assert hasattr(status, "sub_delay")

            # Validate value ranges
            assert isinstance(status.enabled, bool)
            assert 30 <= status.crossover <= 250
            assert status.phase in (0, 180)
            assert -15 <= status.level <= 15
            assert -200 <= status.sub_delay <= 200

            print("\nSubwoofer Status:")
            print(f"  Enabled: {status.enabled}")
            print(f"  Crossover: {status.crossover} Hz")
            print(f"  Phase: {status.phase}°")
            print(f"  Level: {status.level} dB")
            print(f"  Delay: {status.sub_delay} ms")
            # Note: main_filter_enabled=True means bass is NOT sent to main speakers
            # sub_filter_enabled=True means filtering is active (not bypassed)
            print(f"  Bass to Mains: {not status.main_filter_enabled}")
            print(f"  Filter Bypassed: {not status.sub_filter_enabled}")

            # Test player-level properties
            assert player.supports_subwoofer is True
            assert player.subwoofer_enabled == status.enabled
            assert player.subwoofer_level == status.level
            assert player.subwoofer_crossover == status.crossover

        except Exception as e:
            error_str = str(e).lower()
            if "unknown command" in error_str:
                pytest.skip("Subwoofer not supported (WiiM devices only)")
            pytest.fail(f"Error testing subwoofer: {e}")

    async def test_player_subwoofer_controls_safe(self, real_device_player, integration_test_marker):
        """Test subwoofer controls with safe limits and state restoration."""
        player = real_device_player
        await player.refresh(full=True)

        if not player.supports_subwoofer:
            pytest.skip("Subwoofer not supported on this device (capability probe)")

        # Try to get initial subwoofer status
        try:
            initial_status = await player.get_subwoofer_status()

            if initial_status is None:
                pytest.skip("Subwoofer API returned no status despite capability True")

            # Save initial values
            initial_crossover = initial_status.crossover
            initial_level = initial_status.level

            try:
                # Test setting crossover (safe - just change and restore)
                test_crossover = 85 if initial_crossover != 85 else 90
                await player.set_subwoofer_crossover(test_crossover)
                await asyncio.sleep(0.5)

                # Verify change
                verify_status = await player.get_subwoofer_status()
                assert verify_status is not None
                assert verify_status.crossover == test_crossover
                print(f"\n✓ set_subwoofer_crossover({test_crossover}) - verified")

                # Test setting level (safe - just change and restore)
                test_level = 2 if initial_level != 2 else 0
                await player.set_subwoofer_level(test_level)
                await asyncio.sleep(0.5)

                # Verify change
                verify_status = await player.get_subwoofer_status()
                assert verify_status is not None
                assert verify_status.level == test_level
                print(f"✓ set_subwoofer_level({test_level}) - verified")

            finally:
                # Restore initial state
                await player.set_subwoofer_crossover(initial_crossover)
                await player.set_subwoofer_level(initial_level)
                await asyncio.sleep(0.5)
                print(f"✓ Restored crossover to {initial_crossover}Hz, level to {initial_level}dB")

        except Exception as e:
            error_str = str(e).lower()
            if "unknown command" in error_str:
                pytest.skip("Subwoofer not supported (WiiM devices only)")
            pytest.fail(f"Error testing subwoofer controls: {e}")
