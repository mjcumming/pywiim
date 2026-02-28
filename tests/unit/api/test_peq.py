"""Unit tests for PEQAPI mixin and PEQ helper functions.

Tests parametric EQ band parsing, settings parsing, enable/disable,
band read/write, and all validation helpers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pywiim.api.constants import (
    PEQ_CHANNEL_MODE_LR,
    PEQ_CHANNEL_MODE_STEREO,
    PEQ_MODE_HIGH_SHELF,
    PEQ_MODE_LOW_SHELF,
    PEQ_MODE_OFF,
    PEQ_MODE_PEAK,
)
from pywiim.api.peq import (
    PEQBand,
    PEQSettings,
    _parse_eq_band_array,
    _parse_peq_settings,
    _validate_channel_mode,
    _validate_frequency,
    _validate_gain,
    _validate_mode,
    _validate_q,
)

# ---------------------------------------------------------------------------
# _parse_eq_band_array
# ---------------------------------------------------------------------------


class TestParseEqBandArray:
    """Tests for _parse_eq_band_array helper."""

    def test_normal_input(self):
        """Parse a standard band array with all 10 bands."""
        band_array = []
        for letter in "abcdefghij":
            band_array.extend(
                [
                    {"param_name": f"{letter}_mode", "value": 1},
                    {"param_name": f"{letter}_freq", "value": 1000.0},
                    {"param_name": f"{letter}_q", "value": 1.0},
                    {"param_name": f"{letter}_gain", "value": 3.0},
                ]
            )
        bands = _parse_eq_band_array(band_array)
        assert len(bands) == 10
        assert bands[0].letter == "a"
        assert bands[0].mode == 1
        assert bands[0].frequency == 1000.0
        assert bands[0].q == 1.0
        assert bands[0].gain == 3.0

    def test_empty_input(self):
        """Empty band array returns 10 default bands."""
        from pywiim.api.constants import PEQ_DEFAULT_GAIN, PEQ_DEFAULT_MODE

        bands = _parse_eq_band_array([])
        assert len(bands) == 10
        for band in bands:
            assert band.mode == PEQ_DEFAULT_MODE
            assert band.gain == PEQ_DEFAULT_GAIN

    def test_malformed_non_numeric_value(self):
        """Non-numeric values are skipped gracefully (no exception)."""
        band_array = [
            {"param_name": "a_mode", "value": "N/A"},
            {"param_name": "a_freq", "value": "--"},
            {"param_name": "a_gain", "value": 3.0},  # valid
        ]
        bands = _parse_eq_band_array(band_array)
        assert len(bands) == 10
        # The valid gain entry is used; mode/freq fall back to defaults
        assert bands[0].gain == 3.0

    def test_malformed_none_value(self):
        """Entries with value=None are skipped."""
        band_array = [{"param_name": "a_mode", "value": None}]
        bands = _parse_eq_band_array(band_array)
        assert len(bands) == 10

    def test_malformed_missing_param_name(self):
        """Entries without param_name are skipped."""
        band_array = [{"value": 1.0}]
        bands = _parse_eq_band_array(band_array)
        assert len(bands) == 10

    def test_partial_bands(self):
        """Array with only some bands parsed; others get defaults."""
        band_array = [
            {"param_name": "a_mode", "value": 2},
            {"param_name": "a_gain", "value": -6.0},
        ]
        bands = _parse_eq_band_array(band_array)
        assert bands[0].mode == 2
        assert bands[0].gain == -6.0
        # Band b has all defaults
        from pywiim.api.constants import PEQ_DEFAULT_GAIN, PEQ_DEFAULT_MODE

        assert bands[1].mode == PEQ_DEFAULT_MODE
        assert bands[1].gain == PEQ_DEFAULT_GAIN


# ---------------------------------------------------------------------------
# _parse_peq_settings
# ---------------------------------------------------------------------------


class TestParsePeqSettings:
    """Tests for _parse_peq_settings helper."""

    def _make_stereo_raw(self, enabled: bool = True) -> dict:
        bands = []
        for letter in "abcdefghij":
            bands.extend(
                [
                    {"param_name": f"{letter}_mode", "value": 1},
                    {"param_name": f"{letter}_freq", "value": 500.0},
                    {"param_name": f"{letter}_q", "value": 1.5},
                    {"param_name": f"{letter}_gain", "value": 2.0},
                ]
            )
        return {
            "EQStat": "On" if enabled else "Off",
            "channelMode": PEQ_CHANNEL_MODE_STEREO,
            "source_name": "wifi",
            "Name": "MyPreset",
            "EQBand": bands,
        }

    def _make_lr_raw(self) -> dict:
        bands = []
        for letter in "abcdefghij":
            bands.extend(
                [
                    {"param_name": f"{letter}_mode", "value": 0},
                    {"param_name": f"{letter}_freq", "value": 200.0},
                    {"param_name": f"{letter}_q", "value": 0.7},
                    {"param_name": f"{letter}_gain", "value": -3.0},
                ]
            )
        return {
            "EQStat": "On",
            "channelMode": PEQ_CHANNEL_MODE_LR,
            "source_name": "line-in",
            "Name": "",
            "EQBandL": bands,
            "EQBandR": bands,
        }

    def test_stereo_mode_enabled(self):
        """Stereo mode returns bands list with enabled=True."""
        raw = self._make_stereo_raw(enabled=True)
        settings = _parse_peq_settings(raw)
        assert isinstance(settings, PEQSettings)
        assert settings.enabled is True
        assert settings.channel_mode == PEQ_CHANNEL_MODE_STEREO
        assert settings.source_name == "wifi"
        assert settings.name == "MyPreset"
        assert len(settings.bands) == 10
        assert settings.bands_l == []
        assert settings.bands_r == []

    def test_stereo_mode_disabled(self):
        """EQStat=Off returns enabled=False."""
        raw = self._make_stereo_raw(enabled=False)
        settings = _parse_peq_settings(raw)
        assert settings.enabled is False

    def test_lr_mode(self):
        """L/R mode returns bands_l and bands_r populated."""
        raw = self._make_lr_raw()
        settings = _parse_peq_settings(raw)
        assert settings.channel_mode == PEQ_CHANNEL_MODE_LR
        assert settings.source_name == "line-in"
        assert len(settings.bands_l) == 10
        assert len(settings.bands_r) == 10
        assert settings.bands == []

    def test_defaults_on_empty_raw(self):
        """Empty raw dict returns sensible defaults."""
        settings = _parse_peq_settings({})
        assert settings.enabled is False
        assert settings.channel_mode == PEQ_CHANNEL_MODE_STEREO
        assert settings.source_name == ""
        assert settings.name == ""
        assert len(settings.bands) == 10


# ---------------------------------------------------------------------------
# PEQAPI public methods (via mock_client)
# ---------------------------------------------------------------------------


class TestGetPeqBands:
    """Tests for PEQAPI.get_peq_bands."""

    @pytest.mark.asyncio
    async def test_get_peq_bands_no_source(self, mock_client):
        """get_peq_bands without source calls EQGetLV2BandEx endpoint."""
        raw = {
            "EQStat": "On",
            "channelMode": PEQ_CHANNEL_MODE_STEREO,
            "EQBand": [],
        }
        mock_client._request = AsyncMock(return_value=raw)
        result = await mock_client.get_peq_bands()
        assert isinstance(result, PEQSettings)
        call_args = mock_client._request.call_args[0][0]
        assert "EQGetLV2BandEx" in call_args

    @pytest.mark.asyncio
    async def test_get_peq_bands_with_source(self, mock_client):
        """get_peq_bands with source calls EQGetLV2SourceBandEx endpoint."""
        raw = {
            "EQStat": "On",
            "channelMode": PEQ_CHANNEL_MODE_STEREO,
            "EQBand": [],
        }
        mock_client._request = AsyncMock(return_value=raw)
        result = await mock_client.get_peq_bands(source_name="wifi")
        assert isinstance(result, PEQSettings)
        call_args = mock_client._request.call_args[0][0]
        assert "EQGetLV2SourceBandEx" in call_args
        assert "wifi" in call_args

    @pytest.mark.asyncio
    async def test_get_peq_bands_capability_check(self, mock_client):
        """get_peq_bands raises WiiMError when supports_peq=False."""
        from pywiim.exceptions import WiiMError

        mock_client._capabilities = {"supports_peq": False}
        with pytest.raises(WiiMError, match="supports_peq"):
            await mock_client.get_peq_bands()


class TestSetPeqBands:
    """Tests for PEQAPI.set_peq_bands."""

    @pytest.mark.asyncio
    async def test_set_peq_bands_stereo_no_source(self, mock_client):
        """set_peq_bands in stereo mode calls EQSetLV2Band endpoint."""
        mock_client._request = AsyncMock(return_value={"status": "OK"})
        bands = [PEQBand(letter=letter) for letter in "abcdefghij"]
        await mock_client.set_peq_bands(bands)
        call_args = mock_client._request.call_args[0][0]
        assert "EQSetLV2Band" in call_args

    @pytest.mark.asyncio
    async def test_set_peq_bands_with_source(self, mock_client):
        """set_peq_bands with source calls EQSetLV2SourceBand endpoint."""
        mock_client._request = AsyncMock(return_value={"status": "OK"})
        bands = [PEQBand(letter=letter) for letter in "abcdefghij"]
        await mock_client.set_peq_bands(bands, source_name="bluetooth")
        call_args = mock_client._request.call_args[0][0]
        assert "EQSetLV2SourceBand" in call_args
        assert "bluetooth" in call_args

    @pytest.mark.asyncio
    async def test_set_peq_bands_invalid_channel_mode(self, mock_client):
        """set_peq_bands raises ValueError for invalid channel_mode."""
        bands = [PEQBand(letter=letter) for letter in "abcdefghij"]
        with pytest.raises(ValueError, match="channel_mode"):
            await mock_client.set_peq_bands(bands, channel_mode="Mono")


class TestSetPeqEnabled:
    """Tests for PEQAPI.set_peq_enabled."""

    @pytest.mark.asyncio
    async def test_enable_no_source(self, mock_client):
        """Enabling PEQ without source calls EQChangeFX."""
        mock_client._request = AsyncMock(return_value={"status": "OK"})
        await mock_client.set_peq_enabled(True)
        call_args = mock_client._request.call_args[0][0]
        assert "EQChangeFX" in call_args

    @pytest.mark.asyncio
    async def test_enable_with_source(self, mock_client):
        """Enabling PEQ with source calls EQChangeSourceFX."""
        mock_client._request = AsyncMock(return_value={"status": "OK"})
        await mock_client.set_peq_enabled(True, source_name="wifi")
        call_args = mock_client._request.call_args[0][0]
        assert "EQChangeSourceFX" in call_args
        assert "wifi" in call_args

    @pytest.mark.asyncio
    async def test_disable_with_source(self, mock_client):
        """Disabling PEQ with source calls EQSourceOff."""
        mock_client._request = AsyncMock(return_value={"status": "OK"})
        await mock_client.set_peq_enabled(False, source_name="line-in")
        call_args = mock_client._request.call_args[0][0]
        assert "EQSourceOff" in call_args
        assert "line-in" in call_args

    @pytest.mark.asyncio
    async def test_disable_no_source_uses_eqoff(self, mock_client):
        """Disabling PEQ without source falls back to legacy EQOff."""
        mock_client._request = AsyncMock(return_value={"status": "OK"})
        await mock_client.set_peq_enabled(False)
        call_args = mock_client._request.call_args[0][0]
        assert "EQOff" in call_args


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


class TestValidationHelpers:
    """Tests for _validate_* helpers."""

    def test_validate_channel_mode_valid(self):
        _validate_channel_mode(PEQ_CHANNEL_MODE_STEREO)
        _validate_channel_mode(PEQ_CHANNEL_MODE_LR)

    def test_validate_channel_mode_invalid(self):
        with pytest.raises(ValueError, match="channel_mode"):
            _validate_channel_mode("Mono")

    def test_validate_mode_valid(self):
        for mode in (PEQ_MODE_OFF, PEQ_MODE_LOW_SHELF, PEQ_MODE_PEAK, PEQ_MODE_HIGH_SHELF):
            _validate_mode(mode)

    def test_validate_mode_invalid(self):
        with pytest.raises(ValueError, match="Invalid PEQ mode"):
            _validate_mode(99)

    def test_validate_frequency_valid(self):
        _validate_frequency(10.0)
        _validate_frequency(1000.0)
        _validate_frequency(22000.0)

    def test_validate_frequency_too_low(self):
        with pytest.raises(ValueError, match="Frequency"):
            _validate_frequency(5.0)

    def test_validate_frequency_too_high(self):
        with pytest.raises(ValueError, match="Frequency"):
            _validate_frequency(25000.0)

    def test_validate_q_valid(self):
        _validate_q(0.01)
        _validate_q(1.0)
        _validate_q(24.0)

    def test_validate_q_out_of_range(self):
        with pytest.raises(ValueError, match="Q value"):
            _validate_q(0.001)
        with pytest.raises(ValueError, match="Q value"):
            _validate_q(25.0)

    def test_validate_gain_valid(self):
        _validate_gain(-12.0)
        _validate_gain(0.0)
        _validate_gain(12.0)

    def test_validate_gain_out_of_range(self):
        with pytest.raises(ValueError, match="Gain"):
            _validate_gain(-15.0)
        with pytest.raises(ValueError, match="Gain"):
            _validate_gain(13.0)


# ---------------------------------------------------------------------------
# PEQBand dataclass
# ---------------------------------------------------------------------------


class TestPeqBand:
    """Tests for PEQBand dataclass."""

    def test_default_frequency_from_letter(self):
        """Frequency defaults to the per-letter default when 0.0 is given."""
        band = PEQBand(letter="a")
        assert band.frequency > 0.0

    def test_to_api_params(self):
        """to_api_params returns the four expected dicts."""
        band = PEQBand(letter="a", mode=1, frequency=1000.0, q=1.0, gain=3.0)
        params = band.to_api_params()
        assert len(params) == 4
        names = {p["param_name"] for p in params}
        assert names == {"a_mode", "a_freq", "a_q", "a_gain"}

    def test_from_api_params(self):
        """from_api_params constructs a PEQBand correctly."""
        param_dict = {"a_mode": 2.0, "a_freq": 500.0, "a_q": 0.7, "a_gain": -6.0}
        band = PEQBand.from_api_params("a", param_dict)
        assert band.letter == "a"
        assert band.mode == 2
        assert band.frequency == 500.0
        assert band.q == 0.7
        assert band.gain == -6.0
