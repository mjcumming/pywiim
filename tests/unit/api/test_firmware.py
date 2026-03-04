"""Unit tests for firmware API."""

from unittest.mock import AsyncMock

import pytest

from pywiim.api.base import ApiResponse
from pywiim.api.firmware import FirmwareAPI, compare_firmware_versions, parse_firmware_version


class TestParseFirmwareVersion:
    """Test parse_firmware_version function."""

    def test_parse_major_minor_build(self):
        """Test parsing major.minor.build format."""
        result = parse_firmware_version("5.0.123456")

        assert result is not None
        assert result["major"] == 5
        assert result["minor"] == 0
        assert result["build"] == 123456
        assert result["raw"] == "5.0.123456"

    def test_parse_major_minor(self):
        """Test parsing major.minor format."""
        result = parse_firmware_version("5.0")

        assert result is not None
        assert result["major"] == 5
        assert result["minor"] == 0
        assert result["build"] is None

    def test_parse_major_minor_patch(self):
        """Test parsing major.minor.patch format."""
        result = parse_firmware_version("2.0.1")

        assert result is not None
        assert result["major"] == 2
        assert result["minor"] == 0
        # Note: The first regex matches major.minor.build, so "2.0.1" is parsed as build=1
        assert result["build"] == 1

    def test_parse_legacy_format(self):
        """Test parsing legacy format."""
        result = parse_firmware_version("1.56")

        assert result is not None
        assert result["major"] == 1
        assert result["minor"] == 56

    def test_parse_none(self):
        """Test parsing None."""
        result = parse_firmware_version(None)

        assert result is None

    def test_parse_empty(self):
        """Test parsing empty string."""
        result = parse_firmware_version("")

        assert result is None

    def test_parse_invalid(self):
        """Test parsing invalid format."""
        result = parse_firmware_version("invalid")

        assert result is not None
        assert result["major"] is None
        assert result["raw"] == "invalid"

    def test_parse_zero(self):
        """Test parsing zero."""
        result = parse_firmware_version("0")

        assert result is None

    def test_parse_unknown(self):
        """Test parsing unknown."""
        result = parse_firmware_version("unknown")

        assert result is None


class TestCompareFirmwareVersions:
    """Test compare_firmware_versions function."""

    def test_compare_equal(self):
        """Test comparing equal versions."""
        assert compare_firmware_versions("5.0.123456", "5.0.123456") == 0

    def test_compare_current_older(self):
        """Test comparing when current is older."""
        assert compare_firmware_versions("5.0.123456", "5.0.123457") == -1
        assert compare_firmware_versions("5.0", "5.1") == -1

    def test_compare_current_newer(self):
        """Test comparing when current is newer."""
        assert compare_firmware_versions("5.0.123457", "5.0.123456") == 1
        assert compare_firmware_versions("5.1", "5.0") == 1

    def test_compare_major_versions(self):
        """Test comparing major versions."""
        assert compare_firmware_versions("4.0", "5.0") == -1
        assert compare_firmware_versions("5.0", "4.0") == 1

    def test_compare_unparseable(self):
        """Test comparing unparseable versions."""
        # Falls back to string comparison
        result = compare_firmware_versions("invalid", "invalid")
        assert result == 0

        # When unparseable, both return None, so comparison returns 0
        result = compare_firmware_versions("a", "b")
        # Both unparseable, so returns 0 (can't compare)
        assert result == 0


class TestFirmwareAPI:
    """Test FirmwareAPI mixin."""

    @pytest.mark.asyncio
    async def test_get_firmware_info(self, mock_client):
        """Test getting firmware info."""
        from pywiim.models import DeviceInfo

        device_info = DeviceInfo(
            uuid="test",
            firmware="5.0.123456",
            latest_version="5.0.123457",
            version_update="1",
        )
        mock_client.get_device_info_model = AsyncMock(return_value=device_info)

        # Create a class that mixes in FirmwareAPI
        class TestClient(FirmwareAPI):
            async def get_device_info_model(self):
                return device_info

        client = TestClient()
        info = await client.get_firmware_info()

        assert info["current_version"] == "5.0.123456"
        assert info["latest_version"] == "5.0.123457"
        assert info["update_available"] is True
        assert info["parsed_version"] is not None

    @pytest.mark.asyncio
    async def test_check_for_updates(self, mock_client):
        """Test checking for updates."""
        from pywiim.models import DeviceInfo

        device_info = DeviceInfo(uuid="test", firmware="5.0.123456", version_update="1")
        mock_client.get_device_info_model = AsyncMock(return_value=device_info)

        class TestClient(FirmwareAPI):
            async def get_device_info_model(self):
                return device_info

        client = TestClient()
        has_update = await client.check_for_updates()

        assert has_update is True

    @pytest.mark.asyncio
    async def test_get_update_status(self, mock_client):
        """Test getting update status."""
        from pywiim.models import DeviceInfo

        device_info = DeviceInfo(uuid="test", firmware="5.0.123456", version_update="1")
        mock_client.get_device_info_model = AsyncMock(return_value=device_info)

        class TestClient(FirmwareAPI):
            async def get_device_info_model(self):
                return device_info

        client = TestClient()
        status = await client.get_update_status()

        assert status["update_available"] is True
        assert status["update_ready"] is True
        assert status["can_install"] is True

    @pytest.mark.asyncio
    async def test_is_firmware_version_at_least(self, mock_client):
        """Test checking if firmware version meets requirement."""
        from pywiim.models import DeviceInfo

        device_info = DeviceInfo(uuid="test", firmware="5.0.123456")
        mock_client.get_device_info_model = AsyncMock(return_value=device_info)

        class TestClient(FirmwareAPI):
            async def get_device_info_model(self):
                return device_info

        client = TestClient()
        result = await client.is_firmware_version_at_least("5.0")

        assert result is True

        result = await client.is_firmware_version_at_least("6.0")
        assert result is False

    @pytest.mark.asyncio
    async def test_ensure_wiim_device_with_capabilities(self, mock_client):
        """Test _ensure_wiim_device with capabilities set."""
        from pywiim.models import DeviceInfo

        device_info = DeviceInfo(uuid="test", model="WiiM Pro", firmware="5.0.1")
        mock_client.get_device_info_model = AsyncMock(return_value=device_info)
        mock_client._request = AsyncMock()

        class TestClient(FirmwareAPI):
            def __init__(self):
                self._capabilities = {"supports_firmware_install": True}

            async def get_device_info_model(self):
                return device_info

            async def _request(self, endpoint):
                return ApiResponse(parsed={}, raw=None)

        client = TestClient()
        # Should not raise (capabilities indicate support)
        await client._ensure_wiim_device()

    @pytest.mark.asyncio
    async def test_ensure_wiim_device_not_supported(self, mock_client):
        """Test _ensure_wiim_device raises error for non-WiiM device."""
        from pywiim.exceptions import WiiMError
        from pywiim.models import DeviceInfo

        device_info = DeviceInfo(uuid="test", model="Arylic H50", firmware="4.6.1")
        mock_client.get_device_info_model = AsyncMock(return_value=device_info)

        class TestClient(FirmwareAPI):
            def __init__(self):
                self._capabilities = {"supports_firmware_install": False}

            async def get_device_info_model(self):
                return device_info

            async def _request(self, endpoint):
                return ApiResponse(parsed={}, raw=None)

        client = TestClient()

        with pytest.raises(WiiMError, match="Firmware update installation is only available"):
            await client._ensure_wiim_device()

    @pytest.mark.asyncio
    async def test_check_for_updates_wiim(self, mock_client):
        """Test check_for_updates_wiim on WiiM device."""
        from pywiim.models import DeviceInfo

        device_info = DeviceInfo(uuid="test", model="WiiM Pro", firmware="5.0.1")
        mock_client.get_device_info_model = AsyncMock(return_value=device_info)
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed={"status": "ok"}, raw=None))

        class TestClient(FirmwareAPI):
            def __init__(self):
                self._capabilities = {"supports_firmware_install": True}

            async def get_device_info_model(self):
                return device_info

            async def _request(self, endpoint):
                return ApiResponse(parsed={"status": "ok", "update_available": True}, raw=None)

        client = TestClient()
        result = await client.check_for_updates_wiim()

        assert isinstance(result, dict)
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_install_firmware_update(self, mock_client):
        """Test install_firmware_update on WiiM device."""
        from pywiim.models import DeviceInfo

        device_info = DeviceInfo(uuid="test", model="WiiM Pro", firmware="5.0.1")
        request_mock = AsyncMock(return_value="OK")

        class TestClient(FirmwareAPI):
            def __init__(self):
                self._capabilities = {"supports_firmware_install": True}
                self._request_called = False

            async def get_device_info_model(self):
                return device_info

            async def _request(self, endpoint):
                self._request_called = True
                return ApiResponse(parsed=None, raw=await request_mock(endpoint))

        client = TestClient()
        await client.install_firmware_update()

        # Verify request was made
        assert client._request_called
        assert request_mock.called

    @pytest.mark.asyncio
    async def test_get_update_download_status(self, mock_client):
        """Test get_update_download_status on WiiM device."""
        from pywiim.models import DeviceInfo

        device_info = DeviceInfo(uuid="test", model="WiiM Pro", firmware="5.0.1")
        mock_client.get_device_info_model = AsyncMock(return_value=device_info)
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed={"status": "27", "progress": "100"}, raw=None))

        class TestClient(FirmwareAPI):
            def __init__(self):
                self._capabilities = {"supports_firmware_install": True}

            async def get_device_info_model(self):
                return device_info

            async def _request(self, endpoint):
                return ApiResponse(parsed={"status": "27", "progress": "100"}, raw=None)

        client = TestClient()
        result = await client.get_update_download_status()

        assert isinstance(result, dict)
        assert result["status"] == "27"

    @pytest.mark.asyncio
    async def test_get_update_install_status(self, mock_client):
        """Test get_update_install_status on WiiM device."""
        from pywiim.models import DeviceInfo

        device_info = DeviceInfo(uuid="test", model="WiiM Pro", firmware="5.0.1")
        mock_client.get_device_info_model = AsyncMock(return_value=device_info)
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed={"status": "0", "progress": "50"}, raw=None))

        class TestClient(FirmwareAPI):
            def __init__(self):
                self._capabilities = {"supports_firmware_install": True}

            async def get_device_info_model(self):
                return device_info

            async def _request(self, endpoint):
                return ApiResponse(parsed={"status": "0", "progress": "50"}, raw=None)

        client = TestClient()
        result = await client.get_update_install_status()

        assert isinstance(result, dict)
        assert result["status"] == "0"
        assert result["progress"] == "50"
