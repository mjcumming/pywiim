"""Unit tests for loop mode vendor mappings.

Tests LoopModeMapping class and vendor-specific mappings.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from pywiim.api.loop_mode import (
    ARYLIC_LOOP_MODE,
    LEGACY_BITFIELD_LOOP_MODE,
    WIIM_LOOP_MODE,
    get_loop_mode_mapping,
    get_loop_mode_mapping_for_scheme,
    resolve_loop_mode_mapping,
    resolve_loop_mode_mapping_for_player,
)


class TestLoopModeMapping:
    """Test LoopModeMapping NamedTuple."""

    def test_to_loop_mode_normal(self):
        """Test to_loop_mode with normal (no shuffle, no repeat)."""
        mapping = WIIM_LOOP_MODE
        result = mapping.to_loop_mode(shuffle=False, repeat_one=False, repeat_all=False)
        assert result == mapping.normal

    def test_to_loop_mode_repeat_one(self):
        """Test to_loop_mode with repeat one."""
        mapping = WIIM_LOOP_MODE
        result = mapping.to_loop_mode(shuffle=False, repeat_one=True, repeat_all=False)
        assert result == mapping.repeat_one

    def test_to_loop_mode_repeat_all(self):
        """Test to_loop_mode with repeat all."""
        mapping = WIIM_LOOP_MODE
        result = mapping.to_loop_mode(shuffle=False, repeat_one=False, repeat_all=True)
        assert result == mapping.repeat_all

    def test_to_loop_mode_shuffle(self):
        """Test to_loop_mode with shuffle only."""
        mapping = WIIM_LOOP_MODE
        result = mapping.to_loop_mode(shuffle=True, repeat_one=False, repeat_all=False)
        assert result == mapping.shuffle

    def test_to_loop_mode_shuffle_repeat_one(self):
        """Test to_loop_mode with shuffle and repeat one."""
        mapping = WIIM_LOOP_MODE
        result = mapping.to_loop_mode(shuffle=True, repeat_one=True, repeat_all=False)
        assert result == mapping.shuffle_repeat_one

    def test_to_loop_mode_shuffle_repeat_all(self):
        """Test to_loop_mode with shuffle and repeat all."""
        mapping = WIIM_LOOP_MODE
        result = mapping.to_loop_mode(shuffle=True, repeat_one=False, repeat_all=True)
        assert result == mapping.shuffle_repeat_all

    def test_to_loop_mode_priority_order(self):
        """Test to_loop_mode priority order (shuffle+repeat_all takes precedence)."""
        mapping = WIIM_LOOP_MODE
        # Even if repeat_one is True, shuffle+repeat_all should win
        result = mapping.to_loop_mode(shuffle=True, repeat_one=True, repeat_all=True)
        assert result == mapping.shuffle_repeat_all

    def test_from_loop_mode_normal(self):
        """Test from_loop_mode with normal value."""
        mapping = WIIM_LOOP_MODE
        shuffle, repeat_one, repeat_all = mapping.from_loop_mode(mapping.normal)
        assert shuffle is False
        assert repeat_one is False
        assert repeat_all is False

    def test_from_loop_mode_repeat_one(self):
        """Test from_loop_mode with repeat one value."""
        mapping = WIIM_LOOP_MODE
        shuffle, repeat_one, repeat_all = mapping.from_loop_mode(mapping.repeat_one)
        assert shuffle is False
        assert repeat_one is True
        assert repeat_all is False

    def test_from_loop_mode_repeat_all(self):
        """Test from_loop_mode with repeat all value."""
        mapping = WIIM_LOOP_MODE
        shuffle, repeat_one, repeat_all = mapping.from_loop_mode(mapping.repeat_all)
        assert shuffle is False
        assert repeat_one is False
        assert repeat_all is True

    def test_from_loop_mode_shuffle(self):
        """Test from_loop_mode with shuffle value."""
        mapping = WIIM_LOOP_MODE
        shuffle, repeat_one, repeat_all = mapping.from_loop_mode(mapping.shuffle)
        assert shuffle is True
        assert repeat_one is False
        assert repeat_all is False

    def test_from_loop_mode_shuffle_repeat_one(self):
        """Test from_loop_mode with shuffle repeat one value."""
        mapping = WIIM_LOOP_MODE
        # WiiM doesn't differentiate shuffle+repeat_one from shuffle+repeat_all
        # Both map to 2, and from_loop_mode(2) returns shuffle_repeat_all
        shuffle, repeat_one, repeat_all = mapping.from_loop_mode(mapping.shuffle_repeat_one)
        assert shuffle is True
        assert repeat_all is True  # WiiM returns shuffle_repeat_all for value 2
        assert repeat_one is False

    def test_from_loop_mode_shuffle_repeat_all(self):
        """Test from_loop_mode with shuffle repeat all value."""
        mapping = WIIM_LOOP_MODE
        shuffle, repeat_one, repeat_all = mapping.from_loop_mode(mapping.shuffle_repeat_all)
        assert shuffle is True
        assert repeat_one is False
        assert repeat_all is True

    def test_from_loop_mode_value_5_invalid_for_wiim_scheme(self):
        """loop_mode 5 is not in the documented WiiM table — treated as unknown."""
        mapping = WIIM_LOOP_MODE
        shuffle, repeat_one, repeat_all = mapping.from_loop_mode(5)
        assert shuffle is False
        assert repeat_one is False
        assert repeat_all is False

    def test_from_loop_mode_unknown_value(self):
        """Test from_loop_mode with unknown value returns safe default."""
        mapping = WIIM_LOOP_MODE
        shuffle, repeat_one, repeat_all = mapping.from_loop_mode(999)
        assert shuffle is False
        assert repeat_one is False
        assert repeat_all is False


class TestWiiMLoopMode:
    """Test WiiM loop mode mapping values."""

    def test_wiim_values(self):
        """Test WiiM loop mode values match documentation."""
        assert WIIM_LOOP_MODE.normal == 4
        assert WIIM_LOOP_MODE.repeat_one == 1
        assert WIIM_LOOP_MODE.repeat_all == 0
        assert WIIM_LOOP_MODE.shuffle == 3
        assert WIIM_LOOP_MODE.shuffle_repeat_one == 2
        assert WIIM_LOOP_MODE.shuffle_repeat_all == 2

    def test_wiim_round_trip(self):
        """Test WiiM mapping round trip."""
        # Test specific combinations that should work
        test_cases = [
            (False, False, False, 4),  # normal
            (False, True, False, 1),  # repeat_one
            (False, False, True, 0),  # repeat_all
            (True, False, False, 3),  # shuffle
        ]
        for shuffle, repeat_one, repeat_all, expected_mode in test_cases:
            loop_mode = WIIM_LOOP_MODE.to_loop_mode(shuffle, repeat_one, repeat_all)
            assert loop_mode == expected_mode
            result_shuffle, result_repeat_one, result_repeat_all = WIIM_LOOP_MODE.from_loop_mode(loop_mode)
            assert result_shuffle == shuffle
            assert result_repeat_one == repeat_one
            assert result_repeat_all == repeat_all

        # Test shuffle combinations (both map to 2)
        for shuffle, repeat_one, repeat_all in [(True, True, False), (True, False, True)]:
            loop_mode = WIIM_LOOP_MODE.to_loop_mode(shuffle, repeat_one, repeat_all)
            assert loop_mode == 2  # Both map to 2
            result_shuffle, result_repeat_one, result_repeat_all = WIIM_LOOP_MODE.from_loop_mode(loop_mode)
            # from_loop_mode(2) returns shuffle_repeat_all
            assert result_shuffle is True
            assert result_repeat_all is True
            assert result_repeat_one is False


class TestArylicLoopMode:
    """Test Arylic loop mode mapping values."""

    def test_arylic_values(self):
        """Test Arylic loop mode values match documentation."""
        assert ARYLIC_LOOP_MODE.normal == 4
        assert ARYLIC_LOOP_MODE.repeat_one == 1
        assert ARYLIC_LOOP_MODE.repeat_all == 0
        assert ARYLIC_LOOP_MODE.shuffle == 3
        assert ARYLIC_LOOP_MODE.shuffle_repeat_one == 5
        assert ARYLIC_LOOP_MODE.shuffle_repeat_all == 2

    def test_arylic_round_trip(self):
        """Test Arylic mapping round trip."""
        # Test key combinations that should round-trip perfectly
        test_cases = [
            (False, False, False),  # normal
            (False, True, False),  # repeat_one
            (False, False, True),  # repeat_all
            (True, False, False),  # shuffle
            (True, True, False),  # shuffle_repeat_one
            (True, False, True),  # shuffle_repeat_all
        ]
        for shuffle, repeat_one, repeat_all in test_cases:
            loop_mode = ARYLIC_LOOP_MODE.to_loop_mode(shuffle, repeat_one, repeat_all)
            result_shuffle, result_repeat_one, result_repeat_all = ARYLIC_LOOP_MODE.from_loop_mode(loop_mode)
            # Arylic has distinct values for all combinations
            assert result_shuffle == shuffle
            assert result_repeat_one == repeat_one
            assert result_repeat_all == repeat_all


class TestLegacyBitfieldLoopMode:
    """Test legacy bitfield loop mode mapping."""

    def test_legacy_values(self):
        """Test legacy bitfield loop mode values."""
        assert LEGACY_BITFIELD_LOOP_MODE.normal == 0
        assert LEGACY_BITFIELD_LOOP_MODE.repeat_one == 1
        assert LEGACY_BITFIELD_LOOP_MODE.repeat_all == 2
        assert LEGACY_BITFIELD_LOOP_MODE.shuffle == 4
        assert LEGACY_BITFIELD_LOOP_MODE.shuffle_repeat_one == 5
        assert LEGACY_BITFIELD_LOOP_MODE.shuffle_repeat_all == 6


class TestGetLoopModeMappingForScheme:
    """Test scheme-based mapping selection."""

    def test_scheme_wiim(self):
        assert get_loop_mode_mapping_for_scheme("wiim") is WIIM_LOOP_MODE

    def test_scheme_arylic(self):
        assert get_loop_mode_mapping_for_scheme("arylic") is ARYLIC_LOOP_MODE

    def test_scheme_legacy(self):
        assert get_loop_mode_mapping_for_scheme("legacy") is LEGACY_BITFIELD_LOOP_MODE

    def test_resolve_prefers_scheme(self):
        assert resolve_loop_mode_mapping(loop_mode_scheme="arylic", vendor="wiim") is ARYLIC_LOOP_MODE

    def test_resolve_loop_mode_mapping_for_player_uses_capabilities_scheme(self):
        player = MagicMock()
        player.profile = None
        player.client._capabilities = {"vendor": "wiim", "loop_mode_scheme": "arylic"}
        assert resolve_loop_mode_mapping_for_player(player) is ARYLIC_LOOP_MODE

    def test_resolve_loop_mode_mapping_for_player_profile_overrides_caps(self):
        player = MagicMock()
        player.profile = MagicMock(loop_mode_scheme="arylic")
        player.client._capabilities = {"vendor": "wiim", "loop_mode_scheme": "wiim"}
        assert resolve_loop_mode_mapping_for_player(player) is ARYLIC_LOOP_MODE


class TestGetLoopModeMapping:
    """Test get_loop_mode_mapping function."""

    def test_none_vendor(self):
        """Test None vendor returns WiiM mapping."""
        result = get_loop_mode_mapping(None)
        assert result == WIIM_LOOP_MODE

    def test_wiim_vendor(self):
        """Test wiim vendor returns WiiM mapping."""
        result = get_loop_mode_mapping("wiim")
        assert result == WIIM_LOOP_MODE

    def test_wiim_vendor_case_insensitive(self):
        """Test wiim vendor is case insensitive."""
        assert get_loop_mode_mapping("WIIM") == WIIM_LOOP_MODE
        assert get_loop_mode_mapping("WiiM") == WIIM_LOOP_MODE
        assert get_loop_mode_mapping("WiIm") == WIIM_LOOP_MODE

    def test_arylic_vendor(self):
        """Test arylic vendor returns Arylic mapping."""
        result = get_loop_mode_mapping("arylic")
        assert result == ARYLIC_LOOP_MODE

    def test_audio_pro_vendor(self):
        """Test audio_pro vendor returns Arylic mapping."""
        result = get_loop_mode_mapping("audio_pro")
        assert result == ARYLIC_LOOP_MODE

    def test_linkplay_generic_vendor(self):
        """Test linkplay_generic vendor returns Arylic mapping."""
        result = get_loop_mode_mapping("linkplay_generic")
        assert result == ARYLIC_LOOP_MODE

    def test_unknown_vendor(self):
        """Test unknown vendor defaults to WiiM mapping."""
        result = get_loop_mode_mapping("unknown_vendor")
        assert result == WIIM_LOOP_MODE

    def test_empty_string_vendor(self):
        """Test empty string vendor defaults to WiiM mapping."""
        result = get_loop_mode_mapping("")
        assert result == WIIM_LOOP_MODE
