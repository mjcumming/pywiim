"""Unit tests for API response parser.

Tests response parsing, field mapping, time unit conversion, and normalization.
"""

from __future__ import annotations

from pywiim.api.constants import PLAY_MODE_REPEAT_ONE, PLAY_MODE_SHUFFLE
from pywiim.api.parser import _decode_text, _hex_to_str, _normalize_time_value, parse_player_status


class TestNormalizeTimeValue:
    """Test time value normalization (milliseconds vs microseconds)."""

    def test_normalize_milliseconds(self):
        """Test normalization of millisecond values."""
        # 120 seconds = 120,000 milliseconds
        result = _normalize_time_value(120000, "position", "wifi")
        assert result == 120

        # 5 minutes = 300,000 milliseconds
        result = _normalize_time_value(300000, "duration", "spotify")
        assert result == 300

    def test_normalize_microseconds(self):
        """Test normalization of microsecond values (> 10 hours threshold)."""
        # 120 seconds = 120,000,000 microseconds
        result = _normalize_time_value(120000000, "position", "spotify")
        assert result == 120

        # 5 minutes = 300,000,000 microseconds
        result = _normalize_time_value(300000000, "duration", "qobuz")
        assert result == 300

    def test_normalize_threshold_boundary(self):
        """Test threshold boundary (10 hours = 36,000,000 ms)."""
        # Just below threshold (should be treated as ms)
        result = _normalize_time_value(36000000 - 1, "position", "wifi")
        assert result == 36000 - 1  # milliseconds

        # Just above threshold (should be treated as μs)
        result = _normalize_time_value(36000000 + 1, "position", "spotify")
        assert result == 36  # microseconds

    def test_normalize_long_local_network_values_as_milliseconds(self):
        """Long local/network files can exceed 10 hours and still report milliseconds."""
        result = _normalize_time_value(41000000, "duration", "10")
        assert result == 41000

    def test_normalize_udisk_values_as_milliseconds(self):
        """USB/UDisk playback reports long curpos/totlen values in milliseconds."""
        result = _normalize_time_value(89784000, "duration", "10", "UDiskLocal")
        assert result == 89784


class TestHexDecoding:
    """Test hex-encoded string decoding."""

    def test_hex_to_str_valid(self):
        """Test decoding valid hex-encoded strings."""
        # "Hello" in hex: 48656c6c6f
        result = _hex_to_str("48656c6c6f")
        assert result == "Hello"

        # "Test" in hex: 54657374
        result = _hex_to_str("54657374")
        assert result == "Test"

    def test_hex_to_str_invalid(self):
        """Test decoding invalid hex strings returns original."""
        # Invalid hex should return original
        result = _hex_to_str("not hex")
        assert result == "not hex"

        # Empty string returns None (as per implementation)
        result = _hex_to_str("")
        assert result is None

    def test_hex_to_str_none(self):
        """Test decoding None returns None."""
        result = _hex_to_str(None)
        assert result is None

    def test_decode_text_hex(self):
        """Test _decode_text with hex-encoded strings."""
        # Hex-encoded "Hello World"
        result = _decode_text("48656c6c6f20576f726c64")
        assert result == "Hello World"

    def test_decode_text_html_entities(self):
        """Test _decode_text with HTML entities."""
        # Hex-encoded string with HTML entities
        # "Test &amp; More" in hex: 546573742026616d703b204d6f7265
        result = _decode_text("546573742026616d703b204d6f7265")
        assert result == "Test & More"

    def test_decode_text_plain(self):
        """Test _decode_text with plain strings."""
        result = _decode_text("Plain Text")
        assert result == "Plain Text"

    def test_decode_text_none(self):
        """Test _decode_text with None."""
        result = _decode_text(None)
        assert result is None


class TestParsePlayerStatus:
    """Test parse_player_status function."""

    def test_parse_minimal_response(self):
        """Test parsing minimal API response."""
        raw = {"state": "play", "vol": 50}
        parsed, last_track = parse_player_status(raw)

        assert parsed["play_status"] == "play"
        assert parsed["volume"] == 50
        assert parsed["volume_level"] == 0.5
        assert last_track is None

    def test_parse_play_state_variations(self):
        """Test parsing different play state field names."""
        # Test "state" field
        raw1 = {"state": "play"}
        parsed1, _ = parse_player_status(raw1)
        assert parsed1["play_status"] == "play"

        # Test "player_state" field
        raw2 = {"player_state": "pause"}
        parsed2, _ = parse_player_status(raw2)
        assert parsed2["play_status"] == "pause"

        # Test "status" field
        raw3 = {"status": "stop"}
        parsed3, _ = parse_player_status(raw3)
        assert parsed3["play_status"] == "stop"

    def test_parse_volume_conversion(self):
        """Test volume conversion (percentage to 0-1 float)."""
        raw = {"vol": 75}
        parsed, _ = parse_player_status(raw)

        assert parsed["volume"] == 75
        assert parsed["volume_level"] == 0.75

    def test_parse_position_milliseconds(self):
        """Test position parsing from milliseconds."""
        raw = {"curpos": 120000, "mode": "wifi"}  # 120 seconds in ms
        parsed, _ = parse_player_status(raw)

        assert parsed["position"] == 120
        assert "position_updated_at" in parsed

    def test_parse_position_microseconds(self):
        """Test position parsing from microseconds."""
        raw = {"curpos": 120000000, "mode": "spotify"}  # 120 seconds in μs
        parsed, _ = parse_player_status(raw)

        assert parsed["position"] == 120

    def test_parse_duration_milliseconds(self):
        """Test duration parsing from milliseconds."""
        raw = {"totlen": 240000, "mode": "wifi"}  # 240 seconds in ms
        parsed, _ = parse_player_status(raw)

        assert parsed["duration"] == 240

    def test_parse_duration_microseconds(self):
        """Test duration parsing from microseconds."""
        raw = {"totlen": 240000000, "mode": "spotify"}  # 240 seconds in μs
        parsed, _ = parse_player_status(raw)

        assert parsed["duration"] == 240

    def test_parse_long_mode_10_duration_milliseconds(self):
        """Mode 10 local/network playback can report >10h durations in milliseconds."""
        raw = {"status": "play", "mode": "10", "curpos": 230000, "totlen": 41000000}
        parsed, _ = parse_player_status(raw)

        assert parsed["position"] == 230
        assert parsed["duration"] == 41000

    def test_parse_long_udisk_duration_milliseconds(self):
        """UDisk playback can report very long durations in milliseconds."""
        raw = {
            "status": "play",
            "mode": "10",
            "vendor": "UDiskLocal",
            "curpos": 5732000,
            "totlen": 89784000,
        }
        parsed, _ = parse_player_status(raw)

        assert parsed["position"] == 5732
        assert parsed["duration"] == 89784
        assert parsed["source"] == "usb"
        assert parsed["vendor"] == "UDiskLocal"

    def test_parse_udisk_vendor_uses_usb_source(self):
        """WiiM Ultra USB playback reports mode 10 plus UDisk vendor."""
        raw = {
            "type": "0",
            "ch": "0",
            "mode": "10",
            "loop": "4",
            "eq": "0",
            "vendor": "UDiskLocal",
            "status": "play",
            "curpos": "5732",
            "offset_pts": "5739",
            "totlen": "89784",
            "Title": "547261636B2030322047756974617273205370616E6973682044616E636573204578636572707473",
            "Artist": "566172696F75732041727469737473",
            "Album": "5068696C6861726D6F6E696320417564696F20323032332044656D6F204344",
            "alarmflag": "0",
            "plicount": "0",
            "plicurr": "0",
            "vol": "12",
            "mute": "0",
        }
        parsed, _ = parse_player_status(raw)

        assert parsed["source"] == "usb"
        assert parsed["vendor"] == "UDiskLocal"
        assert parsed["title"] == "Track 02 Guitars Spanish Dances Excerpts"

    def test_parse_dlna_mode_without_vendor_uses_dlna_source(self):
        """DLNA playback may report mode 2 without a vendor field."""
        raw = {"status": "play", "mode": "2"}
        parsed, _ = parse_player_status(raw)

        assert parsed["source"] == "dlna"

    def test_parse_duration_zero(self):
        """Test duration of 0 (streaming services)."""
        raw = {"totlen": 0}
        parsed, _ = parse_player_status(raw)

        # Duration of 0 should not be set (None)
        assert "duration" not in parsed or parsed.get("duration") is None

    def test_parse_hex_encoded_metadata(self):
        """Test parsing hex-encoded metadata fields."""
        # "Test Song" in hex: 5465737420536f6e67
        # "Test Artist" in hex: 5465737420417274697374
        raw = {
            "Title": "5465737420536f6e67",
            "Artist": "5465737420417274697374",
            "Album": "5465737420416c62756d",
        }
        parsed, _ = parse_player_status(raw)

        assert parsed["title"] == "Test Song"
        assert parsed["artist"] == "Test Artist"
        assert parsed["album"] == "Test Album"

    def test_parse_mute_conversion(self):
        """Test mute field conversion to boolean."""
        raw1 = {"mute": "1"}
        parsed1, _ = parse_player_status(raw1)
        assert parsed1["mute"] is True

        raw2 = {"mute": "0"}
        parsed2, _ = parse_player_status(raw2)
        assert parsed2["mute"] is False

        raw3 = {"mute": 1}
        parsed3, _ = parse_player_status(raw3)
        assert parsed3["mute"] is True

        raw4 = {"mute": 0}
        parsed4, _ = parse_player_status(raw4)
        assert parsed4["mute"] is False

    def test_parse_play_mode_from_loop_mode(self):
        """Test play mode extraction from loop_mode using vendor-specific mappings (WiiM)."""
        # WiiM loop mode mapping:
        # 0 = repeat_all, 1 = repeat_one, 2 = shuffle_repeat_all, 3 = shuffle, 4 = normal
        # loop_mode = 1 (repeat_one)
        raw1 = {"loop_mode": 1}
        parsed1, _ = parse_player_status(raw1, vendor="wiim")
        assert parsed1["play_mode"] == "repeat_one"

        # loop_mode = 0 (repeat_all for WiiM)
        raw2 = {"loop_mode": 0}
        parsed2, _ = parse_player_status(raw2, vendor="wiim")
        assert parsed2["play_mode"] == "repeat_all"

        # loop_mode = 3 (shuffle for WiiM)
        raw3 = {"loop_mode": 3}
        parsed3, _ = parse_player_status(raw3, vendor="wiim")
        assert parsed3["play_mode"] == "shuffle"

        # loop_mode = 2 (shuffle + repeat_all for WiiM)
        raw4 = {"loop_mode": 2}
        parsed4, _ = parse_player_status(raw4, vendor="wiim")
        assert parsed4["play_mode"] == "shuffle_repeat_all"

    def test_parse_loop_mode_arylic_scheme_value_5(self):
        """loop_mode 5 is shuffle+repeat_one under Arylic scheme (WiiM Ultra 5.2+ pywiim#17)."""
        raw = {"loop_mode": 5}
        parsed, _ = parse_player_status(raw, vendor="wiim", loop_mode_scheme="arylic")
        assert parsed["play_mode"] == PLAY_MODE_SHUFFLE

    def test_parse_loop_mode_wiim_spotify_value_5(self):
        """Spotify loop_mode 5 is source-specific repeat one on WiiM-scheme devices."""
        raw = {"mode": "31", "loop_mode": 5}
        parsed, _ = parse_player_status(raw, vendor="wiim", loop_mode_scheme="wiim")

        assert parsed["source"] == "spotify"
        assert parsed["play_mode"] == PLAY_MODE_REPEAT_ONE

    def test_parse_source_from_mode(self):
        """Test source mapping from mode field."""
        # Mode 0 maps to "idle" in MODE_MAP but should NOT be set as source
        # "idle" is a play STATE, not a SOURCE (Issue #122)
        raw1 = {"mode": "0"}
        parsed1, _ = parse_player_status(raw1)
        # source should not be set to "idle" - either None or not present
        assert parsed1.get("source") != "idle"

        # Mode 1 = airplay
        raw2 = {"mode": "1"}
        parsed2, _ = parse_player_status(raw2)
        assert parsed2["source"] == "airplay"

        # Mode 5 = bluetooth
        raw3 = {"mode": "5"}
        parsed3, _ = parse_player_status(raw3)
        assert parsed3["source"] == "bluetooth"

        # Mode 34 = lyrion (Lyrion Music Server / LMS - Issue mjcumming/wiim#188)
        raw_mode34 = {"mode": "34"}
        parsed_mode34, _ = parse_player_status(raw_mode34)
        assert parsed_mode34["source"] == "lyrion"

        # Mode 60 = line_in (Audio Pro A10 MkII WiiM Edition)
        raw_mode60 = {"mode": "60"}
        parsed_mode60, _ = parse_player_status(raw_mode60)
        assert parsed_mode60["source"] == "line_in"

        # Mode 99 = multiroom (special handling)
        raw4 = {"mode": "99"}
        parsed4, _ = parse_player_status(raw4)
        assert parsed4["source"] == "multiroom"
        assert parsed4.get("_multiroom_mode") is True

    def test_parse_mode_0_preserves_existing_source(self):
        """Test that mode=0 doesn't overwrite existing source (Issue #122 - Spotify idle bug)."""
        # Simulate Spotify playing but device reports mode=0
        # This was causing source="spotify" to be overwritten with source="idle"
        raw = {
            "mode": "0",  # Device incorrectly reports mode=0 when playing Spotify
            "state": "play",  # But device IS playing
            "vendor": "Spotify",  # Spotify app
        }
        parsed, _ = parse_player_status(raw, vendor="spotify")

        # source should be set from vendor, NOT from mode=0
        # Mode 0 maps to "idle" but that should be ignored (it's a play state, not a source)
        assert parsed.get("source") == "spotify"  # From vendor field
        assert parsed.get("play_status") == "play"  # Play state is separate (mapped to play_status)

    def test_parse_artwork_url(self):
        """Test artwork URL parsing and cache-busting."""
        raw = {
            "cover": "http://example.com/artwork.jpg",
            "Title": "Test Song",
            "Artist": "Test Artist",
        }
        parsed, _ = parse_player_status(raw)

        assert "entity_picture" in parsed
        assert "cache=" in parsed["entity_picture"]

    def test_parse_artwork_invalid_values(self):
        """Test artwork URL filtering of invalid values - should use WiiM logo as fallback."""
        invalid_values = ["unknow", "unknown", "un_known", "", "none"]

        for invalid in invalid_values:
            raw = {"cover": invalid}
            parsed, _ = parse_player_status(raw)
            # When invalid cover art is provided, should return None (fallback handled by Player property)
            assert parsed.get("entity_picture") is None

    def test_parse_artwork_no_cover(self):
        """Test that entity_picture is None when no cover art field is present."""
        raw = {"Title": "Test Song", "Artist": "Test Artist"}
        parsed, _ = parse_player_status(raw)
        # When no cover art is provided, should return None (fallback handled by Player property)
        assert parsed.get("entity_picture") is None

    def test_parse_eq_numeric_mapping(self):
        """Test EQ preset numeric to text mapping."""
        # EQ preset 0 = flat
        raw1 = {"eq": "0"}
        parsed1, _ = parse_player_status(raw1)
        assert parsed1["eq_preset"] == "flat"

        # EQ preset 1 = pop
        raw2 = {"eq": "1"}
        parsed2, _ = parse_player_status(raw2)
        assert parsed2["eq_preset"] == "pop"

        # EQ preset 2 = rock
        raw3 = {"eq": "2"}
        parsed3, _ = parse_player_status(raw3)
        assert parsed3["eq_preset"] == "rock"

    def test_parse_track_change_detection(self):
        """Test track change detection for logging."""
        raw1 = {"Title": "5465737420536f6e67", "Artist": "5465737420417274697374"}
        parsed1, last_track1 = parse_player_status(raw1)

        # First track should be detected
        assert last_track1 is not None
        assert "Test Song" in last_track1

        # Same track should not change
        raw2 = {"Title": "5465737420536f6e67", "Artist": "5465737420417274697374"}
        parsed2, last_track2 = parse_player_status(raw2, last_track1)
        assert last_track2 == last_track1

        # Different track should be detected
        raw3 = {"Title": "4e657720536f6e67", "Artist": "4e657720417274697374"}
        parsed3, last_track3 = parse_player_status(raw3, last_track2)
        assert last_track3 != last_track2
        assert "New Song" in last_track3

    def test_parse_power_default(self):
        """Test power field defaults to True."""
        raw = {}
        parsed, _ = parse_player_status(raw)

        assert parsed["power"] is True

    def test_parse_position_duration_validation(self):
        """Test position vs duration validation."""
        # Valid: position < duration
        raw1 = {"curpos": 60000, "totlen": 240000}  # 60s < 240s
        parsed1, _ = parse_player_status(raw1)
        assert parsed1["position"] == 60
        assert parsed1["duration"] == 240

        # Invalid: position > duration (Issue mjcumming/wiim#188 - prefer hide duration)
        raw2 = {"curpos": 300000, "totlen": 120000}  # 300s > 120s
        parsed2, _ = parse_player_status(raw2)
        # Hide duration, keep position (never reset to 0)
        assert parsed2["position"] == 300
        assert parsed2.get("duration") is None

        # Tolerance: position exceeds duration by <=2 seconds (clock drift) - no correction
        raw_tol = {"curpos": 242000, "totlen": 241000}  # 242s vs 241s
        parsed_tol, _ = parse_player_status(raw_tol)
        assert parsed_tol["position"] == 242
        assert parsed_tol["duration"] == 241

        # Invalid: position > duration (but duration seems too short)
        raw3 = {"curpos": 60000, "totlen": 30000}  # 60s > 30s, but duration < 2min
        parsed3, _ = parse_player_status(raw3)
        # Duration should be hidden
        assert parsed3["position"] == 60
        assert parsed3.get("duration") is None

    def test_parse_vendor_override(self):
        """Test vendor field override for source."""
        # Vendor override only works if source is missing/unknown/wifi
        # Mode 0 maps to "idle", but vendor should override if source is in override list
        raw = {"vendor": "amazon music"}
        parsed, _ = parse_player_status(raw)

        # Vendor override should set source to "amazon" when source is missing/unknown/wifi
        assert parsed["source"] == "amazon"
        assert parsed["vendor"] == "amazon music"

    def test_parse_chromecast_vendor_overrides_mode_5_bluetooth(self):
        """Test Chromecast vendor fixes incorrect mode=5 bluetooth mapping (Issue #6)."""
        raw = {
            "mode": "5",  # Often reported during Chromecast sessions
            "vendor": "Google Cast",
            "state": "play",
        }
        parsed, _ = parse_player_status(raw)

        assert parsed["source"] == "wifi"
        assert parsed["vendor"] == "Google Cast"

    def test_parse_bbc_sounds_vendor_overrides_mode_5_bluetooth(self):
        """Test BBC Sounds (Chromecast app) vendor overrides mode=5 bluetooth to wifi (Issue #6)."""
        raw = {
            "mode": "5",
            "vendor": "BBC Sounds",
            "state": "play",
        }
        parsed, _ = parse_player_status(raw)

        assert parsed["source"] == "wifi"
        assert parsed["vendor"] == "BBC Sounds"

    def test_parse_cast_vendor_overrides_mode_5_bluetooth(self):
        """Test WiiM Amp vendor=CAST overrides mode=5 bluetooth to wifi (pywiim #19)."""
        raw = {
            "mode": "5",
            "vendor": "CAST",
            "status": "play",
        }
        parsed, _ = parse_player_status(raw)

        assert parsed["source"] == "wifi"
        assert parsed["vendor"] == "CAST"

    def test_parse_chromecast_artwork_fallback_when_vendor_missing(self):
        """Test artwork URL fallback overrides bluetooth to wifi when vendor not reported (Issue #6)."""
        raw = {
            "mode": "5",
            "state": "play",
            "cover": "https://ichef.bbci.co.uk/images/ic/1280x720/p0lxyycc.jpg",
        }
        parsed, _ = parse_player_status(raw)

        assert parsed["source"] == "wifi"

    def test_parse_qobuz_connect_state_quirks(self):
        """Test Qobuz Connect state detection quirks."""
        # Qobuz with stopped status but rich metadata should be corrected to play
        raw = {
            "state": "stop",
            "source": "qobuz",
            "Title": "5465737420536f6e67",
            "Artist": "5465737420417274697374",
            "curpos": 60000,
            "totlen": 240000,
            "cover": "http://example.com/artwork.jpg",
        }
        parsed, _ = parse_player_status(raw)

        # Should be corrected to "play" due to rich metadata
        assert parsed["play_status"] == "play"

    def test_parse_qobuz_connect_status_none_issue_222(self):
        """HTTP ``status: none`` with Qobuz stream fields should map to play (mjcumming/wiim#222)."""
        raw = {
            "status": "none",
            "mode": "36",
            "vendor": "Qobuz",
            "Title": "5465737420536f6e67",  # "Test Song"
            "Artist": "5465737420417274697374",  # "Test Artist"
            "curpos": 0,
            "totlen": 240000,
            "cover": "http://example.com/artwork.jpg",
        }
        parsed, _ = parse_player_status(raw)
        assert parsed["play_status"] == "play"
        assert parsed["source"] == "qobuz"

    def test_parse_qobuz_connect_state_no_correction(self):
        """Test Qobuz Connect state not corrected without enough indicators."""
        # Qobuz with stopped status and minimal metadata should not be corrected
        raw = {
            "state": "stop",
            "source": "qobuz",
            "Title": "Unknown",
        }
        parsed, _ = parse_player_status(raw)

        # Should remain "stop" (not enough indicators)
        assert parsed["play_status"] == "stop"
