"""Tests for source_capabilities module."""

from pywiim.player.source_capabilities import (
    DEFAULT_CAPABILITIES,
    NATIVE_NOTIFICATION_PROMPT_SOURCES,
    SOURCE_CAPABILITIES,
    SourceCapability,
    get_source_capabilities,
    source_supports_native_notification_prompt,
)


class TestSourceCapability:
    """Test SourceCapability enum and flags."""

    def test_none_has_no_capabilities(self):
        """Test NONE has no capabilities."""
        assert SourceCapability.SHUFFLE not in SourceCapability.NONE
        assert SourceCapability.REPEAT not in SourceCapability.NONE
        assert SourceCapability.NEXT_TRACK not in SourceCapability.NONE
        assert SourceCapability.PREVIOUS_TRACK not in SourceCapability.NONE
        assert SourceCapability.SEEK not in SourceCapability.NONE

    def test_full_control_has_all_capabilities(self):
        """Test FULL_CONTROL has all capabilities."""
        assert SourceCapability.SHUFFLE in SourceCapability.FULL_CONTROL
        assert SourceCapability.REPEAT in SourceCapability.FULL_CONTROL
        assert SourceCapability.NEXT_TRACK in SourceCapability.FULL_CONTROL
        assert SourceCapability.PREVIOUS_TRACK in SourceCapability.FULL_CONTROL
        assert SourceCapability.SEEK in SourceCapability.FULL_CONTROL

    def test_track_control_has_track_capabilities_only(self):
        """Test TRACK_CONTROL has next/prev/seek but not shuffle/repeat."""
        assert SourceCapability.SHUFFLE not in SourceCapability.TRACK_CONTROL
        assert SourceCapability.REPEAT not in SourceCapability.TRACK_CONTROL
        assert SourceCapability.NEXT_TRACK in SourceCapability.TRACK_CONTROL
        assert SourceCapability.PREVIOUS_TRACK in SourceCapability.TRACK_CONTROL
        assert SourceCapability.SEEK in SourceCapability.TRACK_CONTROL


class TestSourceCapabilitiesMapping:
    """Test SOURCE_CAPABILITIES mapping."""

    def test_streaming_services_have_full_control(self):
        """Test streaming services have full control."""
        streaming = ["spotify", "amazon", "tidal", "qobuz", "deezer", "pandora"]
        for source in streaming:
            caps = SOURCE_CAPABILITIES[source]
            assert caps == SourceCapability.FULL_CONTROL, f"{source} should have FULL_CONTROL"

    def test_local_playback_has_full_control(self):
        """Test local playback sources have full control."""
        local = ["usb", "wifi", "network", "http", "playlist", "preset"]
        for source in local:
            caps = SOURCE_CAPABILITIES[source]
            assert caps == SourceCapability.FULL_CONTROL, f"{source} should have FULL_CONTROL"

    def test_external_casting_has_track_control(self):
        """Test external casting sources have track control only."""
        external = ["airplay", "bluetooth", "dlna", "multiroom"]
        for source in external:
            caps = SOURCE_CAPABILITIES[source]
            assert caps == SourceCapability.TRACK_CONTROL, f"{source} should have TRACK_CONTROL"

    def test_live_radio_has_no_control(self):
        """Test live radio sources have no control."""
        radio = ["tunein", "iheartradio", "radio", "internetradio", "webradio"]
        for source in radio:
            caps = SOURCE_CAPABILITIES[source]
            assert caps == SourceCapability.NONE, f"{source} should have NONE"

    def test_physical_inputs_have_no_control(self):
        """Test physical inputs have no control."""
        physical = ["line_in", "linein", "optical", "coaxial", "coax", "aux", "hdmi", "phono", "rca"]
        for source in physical:
            caps = SOURCE_CAPABILITIES[source]
            assert caps == SourceCapability.NONE, f"{source} should have NONE"


class TestGetSourceCapabilities:
    """Test get_source_capabilities function."""

    def test_none_source_returns_none(self):
        """Test None source returns NONE capabilities."""
        assert get_source_capabilities(None) == SourceCapability.NONE

    def test_empty_source_returns_none(self):
        """Test empty source returns NONE capabilities."""
        assert get_source_capabilities("") == SourceCapability.NONE

    def test_case_insensitive(self):
        """Test source lookup is case-insensitive."""
        assert get_source_capabilities("SPOTIFY") == SourceCapability.FULL_CONTROL
        assert get_source_capabilities("Spotify") == SourceCapability.FULL_CONTROL
        assert get_source_capabilities("spotify") == SourceCapability.FULL_CONTROL

    def test_unknown_source_returns_default(self):
        """Test unknown source returns default (permissive) capabilities."""
        assert get_source_capabilities("unknown_source") == DEFAULT_CAPABILITIES
        assert get_source_capabilities("new_streaming_service") == DEFAULT_CAPABILITIES

    def test_default_is_full_control(self):
        """Test default capabilities is FULL_CONTROL (permissive approach)."""
        assert DEFAULT_CAPABILITIES == SourceCapability.FULL_CONTROL

    def test_spotify_capabilities(self):
        """Test Spotify has all capabilities."""
        caps = get_source_capabilities("spotify")
        assert SourceCapability.SHUFFLE in caps
        assert SourceCapability.REPEAT in caps
        assert SourceCapability.NEXT_TRACK in caps
        assert SourceCapability.PREVIOUS_TRACK in caps
        assert SourceCapability.SEEK in caps

    def test_tunein_capabilities(self):
        """Test TuneIn has no capabilities (live radio)."""
        caps = get_source_capabilities("tunein")
        assert SourceCapability.SHUFFLE not in caps
        assert SourceCapability.REPEAT not in caps
        assert SourceCapability.NEXT_TRACK not in caps
        assert SourceCapability.PREVIOUS_TRACK not in caps
        assert SourceCapability.SEEK not in caps

    def test_airplay_capabilities(self):
        """Test AirPlay has track control but no shuffle/repeat."""
        caps = get_source_capabilities("airplay")
        assert SourceCapability.SHUFFLE not in caps
        assert SourceCapability.REPEAT not in caps
        assert SourceCapability.NEXT_TRACK in caps
        assert SourceCapability.PREVIOUS_TRACK in caps
        assert SourceCapability.SEEK in caps

    def test_line_in_capabilities(self):
        """Test line_in has no capabilities (passthrough)."""
        caps = get_source_capabilities("line_in")
        assert caps == SourceCapability.NONE


class TestNotificationPromptSupport:
    """Test native playPromptUrl source support helper."""

    def test_native_notification_sources_supported(self):
        """Known native prompt sources return True."""
        for source in NATIVE_NOTIFICATION_PROMPT_SOURCES:
            assert source_supports_native_notification_prompt(source) is True
            assert source_supports_native_notification_prompt(source.upper()) is True

    def test_non_native_notification_sources_not_supported(self):
        """Known non-native and unknown sources return False."""
        for source in (
            "spotify",
            "airplay",
            "bluetooth",
            "line_in",
            "dlna",
            "linkplay_radio",  # WiiM Home built-in radio; use play_url for TTS
            "unknown_service",
        ):
            assert source_supports_native_notification_prompt(source) is False

    def test_none_or_empty_not_supported(self):
        """None/empty source returns False."""
        assert source_supports_native_notification_prompt(None) is False
        assert source_supports_native_notification_prompt("") is False
