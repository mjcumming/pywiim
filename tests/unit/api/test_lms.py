"""Unit tests for LMS API."""

from unittest.mock import AsyncMock

import pytest

from pywiim.api.base import ApiResponse
from pywiim.exceptions import WiiMError


class TestLMSAPI:
    """Test LMSAPI mixin."""

    @pytest.mark.asyncio
    async def test_get_squeezelite_state(self, mock_client):
        """Test getting Squeezelite state."""
        from pywiim.api.lms import LMSAPI

        expected_state = {
            "default_server": "192.168.1.4:3483",
            "state": "connected",
            "discover_list": ["192.168.1.4:3483"],
            "connected_server": "192.168.1.4:3483",
            "auto_connect": "1",
        }
        mock_client._request = AsyncMock(return_value=ApiResponse(parsed=expected_state, raw=None))

        class TestClient(LMSAPI):
            async def _request(self, endpoint):
                return ApiResponse(parsed=expected_state, raw=None)

        client = TestClient()
        state = await client.get_squeezelite_state()

        assert state == expected_state

    @pytest.mark.asyncio
    async def test_discover_lms_servers(self, mock_client):
        """Test discovering LMS servers."""
        from pywiim.api.lms import LMSAPI

        class TestClient(LMSAPI):
            async def _request(self, endpoint):
                return ApiResponse(parsed={"status": "ok"}, raw=None)

        client = TestClient()
        await client.discover_lms_servers()

    @pytest.mark.asyncio
    async def test_set_auto_connect_enabled(self, mock_client):
        """Test setting auto-connect enabled."""
        from pywiim.api.lms import LMSAPI

        class TestClient(LMSAPI):
            async def _request(self, endpoint):
                return ApiResponse(parsed={"status": "ok"}, raw=None)

        client = TestClient()
        await client.set_auto_connect_enabled(True)
        await client.set_auto_connect_enabled(False)

    @pytest.mark.asyncio
    async def test_connect_to_lms_server(self, mock_client):
        """Test connecting to LMS server."""
        from pywiim.api.lms import LMSAPI

        class TestClient(LMSAPI):
            async def _request(self, endpoint):
                return ApiResponse(parsed={"status": "ok"}, raw=None)

        client = TestClient()
        await client.connect_to_lms_server("192.168.1.4:3483")

    @pytest.mark.asyncio
    async def test_is_auto_connect_enabled(self, mock_client):
        """Test checking if auto-connect is enabled."""
        from pywiim.api.lms import LMSAPI

        class TestClient(LMSAPI):
            async def get_squeezelite_state(self):
                return {"auto_connect": "1"}

        client = TestClient()
        result = await client.is_auto_connect_enabled()

        assert result is True

    @pytest.mark.asyncio
    async def test_is_auto_connect_enabled_false(self, mock_client):
        """Test checking if auto-connect is disabled."""
        from pywiim.api.lms import LMSAPI

        class TestClient(LMSAPI):
            async def get_squeezelite_state(self):
                return {"auto_connect": "0"}

        client = TestClient()
        result = await client.is_auto_connect_enabled()

        assert result is False

    @pytest.mark.asyncio
    async def test_is_auto_connect_enabled_error(self, mock_client):
        """Test checking auto-connect when request fails."""
        from pywiim.api.lms import LMSAPI

        class TestClient(LMSAPI):
            async def get_squeezelite_state(self):
                raise WiiMError("Failed")

        client = TestClient()
        result = await client.is_auto_connect_enabled()

        assert result is False

    @pytest.mark.asyncio
    async def test_get_connected_server(self, mock_client):
        """Test getting connected server."""
        from pywiim.api.lms import LMSAPI

        class TestClient(LMSAPI):
            async def get_squeezelite_state(self):
                return {"connected_server": "192.168.1.4:3483"}

        client = TestClient()
        result = await client.get_connected_server()

        assert result == "192.168.1.4:3483"

    @pytest.mark.asyncio
    async def test_get_default_server(self, mock_client):
        """Test getting default server."""
        from pywiim.api.lms import LMSAPI

        class TestClient(LMSAPI):
            async def get_squeezelite_state(self):
                return {"default_server": "192.168.1.4:3483"}

        client = TestClient()
        result = await client.get_default_server()

        assert result == "192.168.1.4:3483"

    @pytest.mark.asyncio
    async def test_get_discovered_servers(self, mock_client):
        """Test getting discovered servers."""
        from pywiim.api.lms import LMSAPI

        class TestClient(LMSAPI):
            async def get_squeezelite_state(self):
                return {"discover_list": ["192.168.1.4:3483", "192.168.1.5:3483"]}

        client = TestClient()
        result = await client.get_discovered_servers()

        assert result == ["192.168.1.4:3483", "192.168.1.5:3483"]

    @pytest.mark.asyncio
    async def test_get_connection_state(self, mock_client):
        """Test getting connection state."""
        from pywiim.api.lms import LMSAPI

        class TestClient(LMSAPI):
            async def get_squeezelite_state(self):
                return {"state": "connected"}

        client = TestClient()
        result = await client.get_connection_state()

        assert result == "Connected"

    @pytest.mark.asyncio
    async def test_is_connected_to_lms(self, mock_client):
        """Test checking if connected to LMS."""
        from pywiim.api.lms import LMSAPI

        class TestClient(LMSAPI):
            async def get_squeezelite_state(self):
                return {"state": "connected"}

        client = TestClient()
        result = await client.is_connected_to_lms()

        assert result is True

    @pytest.mark.asyncio
    async def test_setup_lms_connection(self, mock_client):
        """Test setting up LMS connection."""
        from pywiim.api.lms import LMSAPI

        class TestClient(LMSAPI):
            async def set_auto_connect_enabled(self, enabled):
                pass

            async def connect_to_lms_server(self, server_address):
                pass

        client = TestClient()
        await client.setup_lms_connection("192.168.1.4:3483", auto_connect=True)

    @pytest.mark.asyncio
    async def test_get_lms_status(self, mock_client):
        """Test getting LMS status."""
        from pywiim.api.lms import LMSAPI

        class TestClient(LMSAPI):
            async def get_squeezelite_state(self):
                return {
                    "state": "connected",
                    "connected_server": "192.168.1.4:3483",
                    "default_server": "192.168.1.4:3483",
                    "auto_connect": "1",
                    "discover_list": ["192.168.1.4:3483"],
                }

            async def get_connection_state(self):
                return "Connected"

            async def is_auto_connect_enabled(self):
                return True

            async def get_discovered_servers(self):
                return ["192.168.1.4:3483"]

            async def is_connected_to_lms(self):
                return True

        client = TestClient()
        status = await client.get_lms_status()

        assert status["connection_state"] == "Connected"
        assert status["is_connected"] is True
        assert status["auto_connect_enabled"] is True
