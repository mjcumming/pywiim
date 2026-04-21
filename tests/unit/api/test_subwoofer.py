"""Unit tests for SubwooferAPI mixin.

Tests subwoofer control functionality including status retrieval,
crossover, phase, level, and delay settings.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pywiim.api.base import ApiResponse
from pywiim.api.subwoofer import SubwooferStatus
from pywiim.exceptions import WiiMError


class TestSubwooferStatus:
    """Test SubwooferStatus dataclass."""

    def test_from_dict_full_response(self):
        """Test parsing complete API response."""
        data = {
            "status": 1,
            "delay_main_sub": "1.0",
            "plugged": 1,
            "output_mode": 1,
            "cross": 85,
            "phase": 0,
            "level": 0,
            "mix_sub": 1,
            "main_filter": 1,
            "sub_filter": 1,
            "sub_delay": -5,
            "linein_delay": 0.00,
        }

        status = SubwooferStatus.from_dict(data)

        assert status.enabled is True
        assert status.plugged is True
        assert status.crossover == 85
        assert status.phase == 0
        assert status.level == 0
        # main_filter=1 means disabled, so main_filter_enabled=False
        assert status.main_filter_enabled is False
        # sub_filter=1 means disabled, so sub_filter_enabled=False
        assert status.sub_filter_enabled is False
        assert status.sub_delay == -5
        assert status.output_mode == 1
        assert status.mix_sub == 1
        assert status.linein_delay == 0.0
        assert status.delay_main_sub == "1.0"

    def test_from_dict_minimal_response(self):
        """Test parsing minimal API response with defaults."""
        data = {}

        status = SubwooferStatus.from_dict(data)

        assert status.enabled is False
        assert status.plugged is False
        assert status.crossover == 80  # default
        assert status.phase == 0
        assert status.level == 0
        assert status.main_filter_enabled is False  # default is 1 which means disabled
        assert status.sub_filter_enabled is False
        assert status.sub_delay == 0
        assert status.output_mode == 0
        assert status.mix_sub == 0
        assert status.linein_delay == 0.0
        assert status.delay_main_sub == ""

    def test_from_dict_inverted_filter_logic(self):
        """Test that filter settings correctly invert API logic.

        API uses: 1=disabled, 0=enabled
        We expose: enabled=True means active
        """
        # main_filter=0 means bass IS sent to mains (enabled)
        # sub_filter=0 means filtering IS active (enabled)
        data = {"main_filter": 0, "sub_filter": 0}
        status = SubwooferStatus.from_dict(data)
        assert status.main_filter_enabled is True
        assert status.sub_filter_enabled is True

        # main_filter=1 means bass is NOT sent to mains (disabled)
        # sub_filter=1 means filtering is NOT active (bypass)
        data = {"main_filter": 1, "sub_filter": 1}
        status = SubwooferStatus.from_dict(data)
        assert status.main_filter_enabled is False
        assert status.sub_filter_enabled is False

    def test_to_dict(self):
        """Test serialization to dictionary."""
        status = SubwooferStatus(
            enabled=True,
            plugged=True,
            crossover=80,
            phase=180,
            level=5,
            main_filter_enabled=True,
            sub_filter_enabled=False,
            sub_delay=10,
            output_mode=1,
            mix_sub=1,
            linein_delay=0.5,
            delay_main_sub="2.0",
        )

        result = status.to_dict()

        assert result["enabled"] is True
        assert result["plugged"] is True
        assert result["crossover"] == 80
        assert result["phase"] == 180
        assert result["level"] == 5
        assert result["main_filter_enabled"] is True
        assert result["sub_filter_enabled"] is False
        assert result["sub_delay"] == 10


class TestSubwooferAPIStatus:
    """Test SubwooferAPI status retrieval methods."""

    @pytest.mark.asyncio
    async def test_get_subwoofer_status_success(self, mock_client):
        """Test successful subwoofer status retrieval."""
        mock_client._request = AsyncMock(
            return_value=ApiResponse(
                parsed={
                    "status": 1,
                    "plugged": 1,
                    "cross": 85,
                    "phase": 0,
                    "level": -3,
                    "main_filter": 0,
                    "sub_filter": 1,
                    "sub_delay": 10,
                },
                raw=None,
            )
        )

        status = await mock_client.get_subwoofer_status()

        assert status is not None
        assert status.enabled is True
        assert status.plugged is True
        assert status.crossover == 85
        assert status.level == -3
        mock_client._request.assert_called_once()
        assert "getSubLPF" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_get_subwoofer_status_not_supported(self, mock_client):
        """Test status retrieval when endpoint not supported."""
        mock_client._request = AsyncMock(side_effect=WiiMError("Unknown command"))

        status = await mock_client.get_subwoofer_status()

        assert status is None

    @pytest.mark.asyncio
    async def test_get_subwoofer_status_error_json_returns_none(self, mock_client):
        """Some devices return 200 + JSON error object instead of raising."""
        mock_client._request = AsyncMock(
            return_value=ApiResponse(
                parsed={"error": "unsupported_command", "raw": "unknown command"},
                raw=None,
            )
        )

        status = await mock_client.get_subwoofer_status()
        assert status is None

    @pytest.mark.asyncio
    async def test_get_subwoofer_status_raw_error_json_returns_none(self, mock_client):
        """Raw helper must not return API error wrappers as status dicts."""
        mock_client._request = AsyncMock(
            return_value=ApiResponse(
                parsed={"error": "unsupported_command", "raw": "unknown command"},
                raw=None,
            )
        )

        result = await mock_client.get_subwoofer_status_raw()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_subwoofer_status_raw(self, mock_client):
        """Test raw status retrieval returns dict directly."""
        raw_response = {"status": 1, "cross": 80, "custom_field": "value"}
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=raw_response, raw=None))

        result = await mock_client.get_subwoofer_status_raw()

        assert result == raw_response

    @pytest.mark.asyncio
    async def test_is_subwoofer_supported_yes(self, mock_client):
        """Test subwoofer support detection when available."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed={"status": 0, "cross": 80}, raw=None))

        supported = await mock_client.is_subwoofer_supported()

        assert supported is True

    @pytest.mark.asyncio
    async def test_is_subwoofer_supported_no(self, mock_client):
        """Test subwoofer support detection when not available."""
        mock_client._request = AsyncMock(side_effect=WiiMError("Unknown command"))

        supported = await mock_client.is_subwoofer_supported()

        assert supported is False

    @pytest.mark.asyncio
    async def test_is_subwoofer_connected(self, mock_client):
        """Test subwoofer connection detection."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed={"status": 1, "plugged": 1}, raw=None))

        connected = await mock_client.is_subwoofer_connected()

        assert connected is True


class TestSubwooferAPIEnable:
    """Test SubwooferAPI enable/disable methods."""

    @pytest.mark.asyncio
    async def test_set_subwoofer_enabled_true(self, mock_client):
        """Test enabling subwoofer."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_subwoofer_enabled(True)

        mock_client._request.assert_called_once()
        assert "setSubLPF:status:1" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_subwoofer_enabled_false(self, mock_client):
        """Test disabling subwoofer."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_subwoofer_enabled(False)

        mock_client._request.assert_called_once()
        assert "setSubLPF:status:0" in mock_client._request.call_args[0][0]


class TestSubwooferAPICrossover:
    """Test SubwooferAPI crossover frequency methods."""

    @pytest.mark.asyncio
    async def test_set_crossover_valid(self, mock_client):
        """Test setting valid crossover frequency."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_subwoofer_crossover(80)

        mock_client._request.assert_called_once()
        assert "setSubLPF:cross:80" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_crossover_min_boundary(self, mock_client):
        """Test setting minimum crossover frequency."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_subwoofer_crossover(30)

        assert "setSubLPF:cross:30" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_crossover_max_boundary(self, mock_client):
        """Test setting maximum crossover frequency."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_subwoofer_crossover(250)

        assert "setSubLPF:cross:250" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_crossover_below_min_raises(self, mock_client):
        """Test setting crossover below minimum raises ValueError."""
        with pytest.raises(ValueError, match="between 30 and 250"):
            await mock_client.set_subwoofer_crossover(29)

    @pytest.mark.asyncio
    async def test_set_crossover_above_max_raises(self, mock_client):
        """Test setting crossover above maximum raises ValueError."""
        with pytest.raises(ValueError, match="between 30 and 250"):
            await mock_client.set_subwoofer_crossover(251)


class TestSubwooferAPIPhase:
    """Test SubwooferAPI phase methods."""

    @pytest.mark.asyncio
    async def test_set_phase_0(self, mock_client):
        """Test setting phase to 0 degrees."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_subwoofer_phase(0)

        mock_client._request.assert_called_once()
        assert "setSubLPF:phase:0" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_phase_180(self, mock_client):
        """Test setting phase to 180 degrees."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_subwoofer_phase(180)

        mock_client._request.assert_called_once()
        assert "setSubLPF:phase:180" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_phase_invalid_raises(self, mock_client):
        """Test setting invalid phase raises ValueError."""
        with pytest.raises(ValueError, match="must be 0 or 180"):
            await mock_client.set_subwoofer_phase(90)


class TestSubwooferAPILevel:
    """Test SubwooferAPI level methods."""

    @pytest.mark.asyncio
    async def test_set_level_valid(self, mock_client):
        """Test setting valid level."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_subwoofer_level(5)

        mock_client._request.assert_called_once()
        assert "setSubLPF:level:5" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_level_negative(self, mock_client):
        """Test setting negative level."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_subwoofer_level(-10)

        assert "setSubLPF:level:-10" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_level_min_boundary(self, mock_client):
        """Test setting minimum level."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_subwoofer_level(-15)

        assert "setSubLPF:level:-15" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_level_max_boundary(self, mock_client):
        """Test setting maximum level."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_subwoofer_level(15)

        assert "setSubLPF:level:15" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_level_below_min_raises(self, mock_client):
        """Test setting level below minimum raises ValueError."""
        with pytest.raises(ValueError, match="between -15 and 15"):
            await mock_client.set_subwoofer_level(-16)

    @pytest.mark.asyncio
    async def test_set_level_above_max_raises(self, mock_client):
        """Test setting level above maximum raises ValueError."""
        with pytest.raises(ValueError, match="between -15 and 15"):
            await mock_client.set_subwoofer_level(16)


class TestSubwooferAPIFilters:
    """Test SubwooferAPI filter methods."""

    @pytest.mark.asyncio
    async def test_set_main_speaker_bass_enabled(self, mock_client):
        """Test enabling bass to main speakers."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_main_speaker_bass(True)

        mock_client._request.assert_called_once()
        # enabled=True means send bass to mains, API value=0
        assert "setSubLPF:main_filter:0" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_main_speaker_bass_disabled(self, mock_client):
        """Test disabling bass to main speakers."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_main_speaker_bass(False)

        mock_client._request.assert_called_once()
        # enabled=False means filter bass from mains, API value=1
        assert "setSubLPF:main_filter:1" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_subwoofer_filter_enabled(self, mock_client):
        """Test enabling subwoofer low-pass filter."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_subwoofer_filter(True)

        mock_client._request.assert_called_once()
        # enabled=True means filtering active, API value=0
        assert "setSubLPF:sub_filter:0" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_subwoofer_filter_disabled(self, mock_client):
        """Test disabling subwoofer filter (bypass mode)."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_subwoofer_filter(False)

        mock_client._request.assert_called_once()
        # enabled=False means bypass mode, API value=1
        assert "setSubLPF:sub_filter:1" in mock_client._request.call_args[0][0]


class TestSubwooferAPIDelay:
    """Test SubwooferAPI delay methods."""

    @pytest.mark.asyncio
    async def test_set_delay_positive(self, mock_client):
        """Test setting positive delay (subwoofer closer)."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_subwoofer_delay(50)

        mock_client._request.assert_called_once()
        assert "setSubLPF:sub_delay:50" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_delay_negative(self, mock_client):
        """Test setting negative delay (subwoofer further)."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_subwoofer_delay(-50)

        assert "setSubLPF:sub_delay:-50" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_delay_min_boundary(self, mock_client):
        """Test setting minimum delay."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_subwoofer_delay(-200)

        assert "setSubLPF:sub_delay:-200" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_delay_max_boundary(self, mock_client):
        """Test setting maximum delay."""
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=None, raw="OK"))

        await mock_client.set_subwoofer_delay(200)

        assert "setSubLPF:sub_delay:200" in mock_client._request.call_args[0][0]

    @pytest.mark.asyncio
    async def test_set_delay_below_min_raises(self, mock_client):
        """Test setting delay below minimum raises ValueError."""
        with pytest.raises(ValueError, match="between -200 and 200"):
            await mock_client.set_subwoofer_delay(-201)

    @pytest.mark.asyncio
    async def test_set_delay_above_max_raises(self, mock_client):
        """Test setting delay above maximum raises ValueError."""
        with pytest.raises(ValueError, match="between -200 and 200"):
            await mock_client.set_subwoofer_delay(201)
