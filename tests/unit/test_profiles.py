"""Unit tests for device profiles module.

Tests profile detection, configuration, and device-specific behaviors.
"""

from __future__ import annotations

import pytest

from pywiim.models import DeviceInfo
from pywiim.profiles import (
    PROFILES,
    get_device_profile,
    get_profile_for_vendor,
)


class TestProfileRegistry:
    """Test the profile registry."""

    def test_all_expected_profiles_exist(self):
        """Verify all expected profiles are in the registry."""
        expected = [
            "wiim",
            "arylic",
            "audio_pro_mkii",
            "audio_pro_w_generation",
            "audio_pro_original",
            "linkplay_generic",
        ]
        for profile_key in expected:
            assert profile_key in PROFILES, f"Missing profile: {profile_key}"

    def test_profiles_are_frozen_dataclasses(self):
        """Verify profiles are immutable."""
        from dataclasses import FrozenInstanceError

        profile = PROFILES["wiim"]
        with pytest.raises(FrozenInstanceError):
            profile.vendor = "modified"  # type: ignore

    def test_all_profiles_have_required_fields(self):
        """Verify all profiles have required configuration sections."""
        for name, profile in PROFILES.items():
            assert profile.vendor, f"{name} missing vendor"
            assert profile.state_sources is not None, f"{name} missing state_sources"
            assert profile.connection is not None, f"{name} missing connection"
            assert profile.endpoints is not None, f"{name} missing endpoints"
            assert profile.grouping is not None, f"{name} missing grouping"


class TestVendorDetection:
    """Test vendor detection from DeviceInfo."""

    def test_wiim_by_model(self):
        """WiiM devices detected by model name."""
        device_info = DeviceInfo(uuid="test", name="Living Room", model="WiiM Pro")
        profile = get_device_profile(device_info)
        assert profile.vendor == "wiim"

    def test_wiim_by_model_variant(self):
        """WiiM variants detected correctly."""
        for model in ["WiiM Mini", "WiiM Amp", "WiiM Ultra", "WiiM_Pro_with_gc4a", "Muzo_Mini"]:
            device_info = DeviceInfo(uuid="test", name="Test", model=model)
            profile = get_device_profile(device_info)
            assert profile.vendor == "wiim", f"Failed for model: {model}"

    def test_wiim_by_name_fallback(self):
        """WiiM detected from name when model is generic."""
        device_info = DeviceInfo(uuid="test", name="WiiM Living Room", model="smart_audio")
        profile = get_device_profile(device_info)
        assert profile.vendor == "wiim"

    def test_arylic_by_model(self):
        """Arylic devices detected by model name."""
        device_info = DeviceInfo(uuid="test", name="Kitchen", model="Arylic Up2Stream")
        profile = get_device_profile(device_info)
        assert profile.vendor == "arylic"

    def test_arylic_variants(self):
        """Arylic variants detected correctly."""
        for model in ["Up2Stream", "S10+", "Arylic Amp"]:
            device_info = DeviceInfo(uuid="test", name="Test", model=model)
            profile = get_device_profile(device_info)
            assert profile.vendor == "arylic", f"Failed for model: {model}"

    def test_audio_pro_by_model(self):
        """Audio Pro devices detected by model name."""
        device_info = DeviceInfo(uuid="test", name="Office", model="Audio Pro Addon C10")
        profile = get_device_profile(device_info)
        assert profile.vendor == "audio_pro"

    def test_audio_pro_variants(self):
        """Audio Pro variants detected correctly."""
        for model in ["Addon C10", "A10", "A15", "A28", "Audio Pro", "C5 MKII", "C5MkII"]:
            device_info = DeviceInfo(uuid="test", name="Test", model=model)
            profile = get_device_profile(device_info)
            assert profile.vendor == "audio_pro", f"Failed for model: {model}"

    def test_audio_pro_c5_mkii_model(self):
        """C5 MkII model string is Audio Pro MkII (issue #266)."""
        device_info = DeviceInfo(uuid="test", name="AudioPro C5MkII Bad WC OG", model="C5MkII")
        profile = get_device_profile(device_info)
        assert profile.vendor == "audio_pro"
        assert profile.generation == "mkii"

    def test_audio_pro_compact_name_without_space(self):
        """AudioPro (no space) in the device name is still Audio Pro."""
        device_info = DeviceInfo(uuid="test", name="AudioPro Living Room", model="smart_audio")
        profile = get_device_profile(device_info)
        assert profile.vendor == "audio_pro"

    def test_linkplay_generic_fallback(self):
        """Unknown devices default to linkplay_generic."""
        device_info = DeviceInfo(uuid="test", name="Speaker", model="Unknown Brand XYZ")
        profile = get_device_profile(device_info)
        assert profile.vendor == "linkplay_generic"


class TestAudioProGenerationDetection:
    """Test Audio Pro generation detection."""

    def test_mkii_detected(self):
        """MkII generation detected from model name."""
        for model in ["Audio Pro A10 MkII", "Addon C10 MK2", "A15 Mk II", "A28 Mark II"]:
            device_info = DeviceInfo(uuid="test", name="Test", model=model)
            profile = get_device_profile(device_info)
            assert profile.vendor == "audio_pro"
            assert profile.generation == "mkii", f"Failed for model: {model}"

    def test_w_generation_detected(self):
        """W-Generation detected from model name."""
        for model in ["Audio Pro W-Series", "A10 W Generation", "Addon W-Gen"]:
            device_info = DeviceInfo(uuid="test", name="Test", model=model)
            profile = get_device_profile(device_info)
            assert profile.vendor == "audio_pro"
            assert profile.generation == "w_generation", f"Failed for model: {model}"

    def test_original_generation_fallback(self):
        """Old Audio Pro models default to original."""
        device_info = DeviceInfo(uuid="test", name="Test", model="Addon C5")
        profile = get_device_profile(device_info)
        assert profile.vendor == "audio_pro"
        # Addon C5 without version info defaults to original
        assert profile.generation in ("original", "mkii")  # May be detected either way


class TestMkIIProfile:
    """Test Audio Pro MkII specific profile settings."""

    def test_mkii_requires_client_cert(self):
        """MkII requires client certificate."""
        profile = PROFILES["audio_pro_mkii"]
        assert profile.connection.requires_client_cert is True

    def test_mkii_preferred_ports(self):
        """MkII prefers port 4443."""
        profile = PROFILES["audio_pro_mkii"]
        assert 4443 in profile.connection.preferred_ports
        assert profile.connection.preferred_ports[0] == 4443

    def test_mkii_https_only(self):
        """MkII uses HTTPS only."""
        profile = PROFILES["audio_pro_mkii"]
        assert profile.connection.protocol_priority == ("https",)

    def test_mkii_state_sources_use_upnp(self):
        """MkII uses UPnP for play_state and volume."""
        profile = PROFILES["audio_pro_mkii"]
        assert profile.state_sources.play_state == "upnp"
        assert profile.state_sources.volume == "upnp"
        assert profile.state_sources.mute == "upnp"

    def test_mkii_metadata_uses_http(self):
        """MkII uses HTTP for metadata."""
        profile = PROFILES["audio_pro_mkii"]
        assert profile.state_sources.title == "http"
        assert profile.state_sources.artist == "http"
        assert profile.state_sources.album == "http"

    def test_mkii_limited_endpoints(self):
        """MkII has limited endpoint support."""
        profile = PROFILES["audio_pro_mkii"]
        assert profile.endpoints.supports_getPlayerStatusEx is False
        assert profile.endpoints.supports_getMetaInfo is False
        assert profile.endpoints.supports_getPresetInfo is False
        assert profile.endpoints.supports_eq is False

    def test_mkii_uses_getStatusEx(self):
        """MkII uses getStatusEx endpoint."""
        profile = PROFILES["audio_pro_mkii"]
        assert "getStatusEx" in profile.endpoints.status_endpoint


class TestWiiMProfile:
    """Test WiiM specific profile settings."""

    def test_wiim_uses_upnp_for_realtime_audio_state(self):
        """WiiM uses UPnP for realtime play_state/volume/mute."""
        profile = PROFILES["wiim"]
        assert profile.state_sources.play_state == "upnp"
        assert profile.state_sources.volume == "upnp"
        assert profile.state_sources.mute == "upnp"
        assert profile.state_sources.title == "http"

    def test_wiim_supports_alarms(self):
        """WiiM supports alarms and sleep timer."""
        profile = PROFILES["wiim"]
        assert profile.endpoints.supports_alarms is True
        assert profile.endpoints.supports_sleep_timer is True

    def test_wiim_loop_mode_scheme(self):
        """WiiM uses wiim loop mode scheme."""
        profile = PROFILES["wiim"]
        assert profile.loop_mode_scheme == "wiim"

    def test_wiim_ultra_fw_52_gets_arylic_loop_mode_scheme(self):
        """WiiM Ultra 5.2+ uses LinkPlay/Arylic loop_mode numbering (pywiim#17)."""
        device_info = DeviceInfo(uuid="t", model="wiim_ultra", firmware="5.2.813259")
        profile = get_device_profile(device_info)
        assert profile.loop_mode_scheme == "arylic"

    def test_wiim_ultra_fw_51_keeps_wiim_loop_mode_scheme(self):
        device_info = DeviceInfo(uuid="t", model="wiim_ultra", firmware="5.1.999999")
        profile = get_device_profile(device_info)
        assert profile.loop_mode_scheme == "wiim"

    def test_wiim_pro_fw_52_keeps_wiim_loop_mode_scheme(self):
        device_info = DeviceInfo(uuid="t", model="wiim_pro", firmware="5.2.813259")
        profile = get_device_profile(device_info)
        assert profile.loop_mode_scheme == "wiim"


class TestArylicProfile:
    """Test Arylic specific profile settings."""

    def test_arylic_loop_mode_scheme(self):
        """Arylic uses arylic loop mode scheme."""
        profile = PROFILES["arylic"]
        assert profile.loop_mode_scheme == "arylic"

    def test_arylic_eq_read_only(self):
        """Arylic may not support EQ set."""
        profile = PROFILES["arylic"]
        assert profile.endpoints.supports_eq is True
        assert profile.endpoints.supports_eq_set is False


class TestGen1Detection:
    """Test Gen1/WiFi Direct detection."""

    def test_gen1_by_wmrm_version(self):
        """Gen1 detected by wmrm_version 2.0."""
        device_info = DeviceInfo(
            uuid="test",
            name="Old Speaker",
            model="Audio Pro A10",
            wmrm_version="2.0",
        )
        profile = get_device_profile(device_info)
        assert profile.grouping.uses_wifi_direct is True

    def test_gen2_by_wmrm_version(self):
        """Gen2+ detected by wmrm_version 4.2."""
        device_info = DeviceInfo(
            uuid="test",
            name="New Speaker",
            model="WiiM Pro",
            wmrm_version="4.2",
        )
        profile = get_device_profile(device_info)
        assert profile.grouping.uses_wifi_direct is False

    def test_gen1_by_firmware(self):
        """Gen1 detected by old firmware version."""
        device_info = DeviceInfo(
            uuid="test",
            name="Old Speaker",
            model="Arylic Up2Stream",
            firmware="4.2.7000",
        )
        profile = get_device_profile(device_info)
        assert profile.grouping.uses_wifi_direct is True

    def test_gen2_by_firmware(self):
        """Gen2+ detected by new firmware version."""
        device_info = DeviceInfo(
            uuid="test",
            name="New Speaker",
            model="Arylic Up2Stream",
            firmware="4.2.9000",
        )
        profile = get_device_profile(device_info)
        assert profile.grouping.uses_wifi_direct is False


class TestProfileForVendor:
    """Test get_profile_for_vendor helper."""

    def test_get_wiim_profile(self):
        """Get WiiM profile by vendor string."""
        profile = get_profile_for_vendor("wiim")
        assert profile.vendor == "wiim"

    def test_get_arylic_profile(self):
        """Get Arylic profile by vendor string."""
        profile = get_profile_for_vendor("arylic")
        assert profile.vendor == "arylic"

    def test_get_audio_pro_mkii_profile(self):
        """Get Audio Pro MkII profile by vendor and generation."""
        profile = get_profile_for_vendor("audio_pro", "mkii")
        assert profile.vendor == "audio_pro"
        assert profile.generation == "mkii"

    def test_unknown_vendor_returns_generic(self):
        """Unknown vendor returns generic profile."""
        profile = get_profile_for_vendor("unknown_brand")
        assert profile.vendor == "linkplay_generic"


class TestRebootCommand:
    """Test reboot command configuration in profiles.

    Audio Pro devices use StartRebootTime:0 instead of the standard 'reboot' command.
    See: https://github.com/mjcumming/wiim/issues/177
    """

    def test_wiim_uses_standard_reboot_command(self):
        """WiiM devices use standard 'reboot' command."""
        profile = PROFILES["wiim"]
        assert profile.endpoints.reboot_command == "reboot"

    def test_arylic_uses_standard_reboot_command(self):
        """Arylic devices use standard 'reboot' command."""
        profile = PROFILES["arylic"]
        assert profile.endpoints.reboot_command == "reboot"

    def test_linkplay_generic_uses_standard_reboot_command(self):
        """Generic LinkPlay devices use standard 'reboot' command."""
        profile = PROFILES["linkplay_generic"]
        assert profile.endpoints.reboot_command == "reboot"

    def test_audio_pro_mkii_uses_start_reboot_time(self):
        """Audio Pro MkII uses StartRebootTime:0 command."""
        profile = PROFILES["audio_pro_mkii"]
        assert profile.endpoints.reboot_command == "StartRebootTime:0"

    def test_audio_pro_w_generation_uses_start_reboot_time(self):
        """Audio Pro W-Generation uses StartRebootTime:0 command."""
        profile = PROFILES["audio_pro_w_generation"]
        assert profile.endpoints.reboot_command == "StartRebootTime:0"

    def test_audio_pro_original_uses_start_reboot_time(self):
        """Audio Pro Original uses StartRebootTime:0 command."""
        profile = PROFILES["audio_pro_original"]
        assert profile.endpoints.reboot_command == "StartRebootTime:0"

    def test_all_audio_pro_profiles_use_start_reboot_time(self):
        """All Audio Pro profiles use StartRebootTime:0 command."""
        audio_pro_profiles = [
            "audio_pro_mkii",
            "audio_pro_w_generation",
            "audio_pro_original",
        ]
        for profile_name in audio_pro_profiles:
            profile = PROFILES[profile_name]
            assert (
                profile.endpoints.reboot_command == "StartRebootTime:0"
            ), f"{profile_name} should use StartRebootTime:0"


class TestProfileIntegration:
    """Integration tests for profile usage patterns."""

    def test_profile_can_be_used_for_state_source_lookup(self):
        """Profiles can be used to determine state source for a field."""
        mkii_profile = PROFILES["audio_pro_mkii"]
        wiim_profile = PROFILES["wiim"]

        # MkII needs UPnP for play_state
        assert mkii_profile.state_sources.play_state == "upnp"
        # WiiM also uses UPnP for play_state
        assert wiim_profile.state_sources.play_state == "upnp"

    def test_profile_can_be_used_for_connection_config(self):
        """Profiles can be used to configure connections."""
        mkii_profile = PROFILES["audio_pro_mkii"]

        # Can use profile to configure connection
        assert mkii_profile.connection.requires_client_cert is True
        assert mkii_profile.connection.response_timeout == 6.0
        assert mkii_profile.connection.retry_count == 3

    def test_profile_can_be_used_for_endpoint_check(self):
        """Profiles can be used to check endpoint availability."""
        mkii_profile = PROFILES["audio_pro_mkii"]
        wiim_profile = PROFILES["wiim"]

        # MkII doesn't support getMetaInfo
        assert mkii_profile.endpoints.supports_getMetaInfo is False
        # WiiM does
        assert wiim_profile.endpoints.supports_getMetaInfo is True


class TestLink2FirmwareFallback:
    """Test that Link 2 with non-standard model string gets the correct MkII profile."""

    def test_link2_gets_mkii_profile(self):
        """Link 2 model + audiopro firmware → audio_pro vendor, mkii generation."""
        device_info = DeviceInfo(
            uuid="FF98F08F07C5B3572C4FB7E1",
            name="Turntable",
            model="LINK 2 Wireless multiroom HiFi player",
            firmware="audiopro_link2-user 1.56",
        )
        profile = get_device_profile(device_info)
        assert profile.vendor == "audio_pro"
        assert profile.generation == "mkii"

    def test_mkii_profile_source_is_upnp(self):
        """MkII profile must prefer UPnP for source (HTTP returns mode=0 when idle)."""
        profile = PROFILES["audio_pro_mkii"]
        assert profile.state_sources.source == "upnp"
