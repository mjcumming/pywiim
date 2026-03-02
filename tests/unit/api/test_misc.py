"""Unit tests for Misc API."""

import pytest

from pywiim.exceptions import WiiMError


class TestMiscAPI:
    """Test MiscAPI mixin."""

    @pytest.mark.asyncio
    async def test_set_buttons_enabled(self, mock_client):
        """Test setting buttons enabled."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                return {"status": "ok"}

        client = TestClient()
        await client.set_buttons_enabled(True)
        await client.set_buttons_enabled(False)

    @pytest.mark.asyncio
    async def test_enable_touch_buttons(self, mock_client):
        """Test enabling touch buttons."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def set_buttons_enabled(self, enabled):
                pass

        client = TestClient()
        await client.enable_touch_buttons()

    @pytest.mark.asyncio
    async def test_disable_touch_buttons(self, mock_client):
        """Test disabling touch buttons."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def set_buttons_enabled(self, enabled):
                pass

        client = TestClient()
        await client.disable_touch_buttons()

    @pytest.mark.asyncio
    async def test_set_led_switch(self, mock_client):
        """Test setting LED switch."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                return {"status": "ok"}

        client = TestClient()
        await client.set_led_switch(True)
        await client.set_led_switch(False)

    @pytest.mark.asyncio
    async def test_get_device_capabilities(self, mock_client):
        """Test getting device capabilities."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def set_buttons_enabled(self, enabled):
                pass

            async def set_led_switch(self, enabled):
                pass

        client = TestClient()
        capabilities = await client.get_device_capabilities()

        assert isinstance(capabilities, dict)
        assert "touch_buttons" in capabilities
        assert "alternative_led" in capabilities

    @pytest.mark.asyncio
    async def test_get_device_capabilities_with_errors(self, mock_client):
        """Test getting device capabilities when some fail."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def set_buttons_enabled(self, enabled):
                raise WiiMError("Not supported")

            async def set_led_switch(self, enabled):
                pass

        client = TestClient()
        capabilities = await client.get_device_capabilities()

        assert capabilities["touch_buttons"] is False
        assert capabilities["alternative_led"] is True

    @pytest.mark.asyncio
    async def test_are_touch_buttons_enabled(self, mock_client):
        """Test checking if touch buttons are enabled."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def enable_touch_buttons(self):
                pass

        client = TestClient()
        result = await client.are_touch_buttons_enabled()

        assert result is True

    @pytest.mark.asyncio
    async def test_are_touch_buttons_enabled_error(self, mock_client):
        """Test checking touch buttons when request fails."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def enable_touch_buttons(self):
                raise WiiMError("Not supported")

        client = TestClient()
        result = await client.are_touch_buttons_enabled()

        assert result is False

    @pytest.mark.asyncio
    async def test_test_misc_functionality(self, mock_client):
        """Test testing misc functionality."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def set_buttons_enabled(self, enabled):
                pass

            async def set_led_switch(self, enabled):
                pass

        client = TestClient()
        results = await client.test_misc_functionality()

        assert results["touch_buttons"] is True
        assert results["alternative_led"] is True

    # --- 12V trigger (WiiM Ultra / Pro / Pro Plus) ---

    @pytest.mark.asyncio
    async def test_get_trigger_out_status_on(self, mock_client):
        """Test get 12V trigger status returns True when on."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                if "getTriggeroutStatus" in endpoint:
                    return {"status": 1}
                return {"status": "ok"}

        client = TestClient()
        result = await client.get_trigger_out_status()
        assert result is True

    @pytest.mark.asyncio
    async def test_get_trigger_out_status_off(self, mock_client):
        """Test get 12V trigger status returns False when off."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                if "getTriggeroutStatus" in endpoint:
                    return {"status": 0}
                return {"status": "ok"}

        client = TestClient()
        result = await client.get_trigger_out_status()
        assert result is False

    @pytest.mark.asyncio
    async def test_get_trigger_out_status_not_supported(self, mock_client):
        """Test get 12V trigger status returns None when device does not support it."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                if "getTriggeroutStatus" in endpoint:
                    raise WiiMError("unknown command")
                return {"status": "ok"}

        client = TestClient()
        result = await client.get_trigger_out_status()
        assert result is None

    @pytest.mark.asyncio
    async def test_set_trigger_out(self, mock_client):
        """Test set 12V trigger on and off sends correct command."""
        from pywiim.api.constants import API_ENDPOINT_TRIGGER_OUT_SET
        from pywiim.api.misc import MiscAPI

        requests = []

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                requests.append(endpoint)
                return {"status": "OK"}

        client = TestClient()
        await client.set_trigger_out(True)
        await client.set_trigger_out(False)
        assert requests == [f"{API_ENDPOINT_TRIGGER_OUT_SET}1", f"{API_ENDPOINT_TRIGGER_OUT_SET}0"]

    @pytest.mark.asyncio
    async def test_set_trigger_out_on_off(self, mock_client):
        """Test set_trigger_out_on and set_trigger_out_off convenience methods."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def set_trigger_out(self, on):
                self._last_trigger = on

        client = TestClient()
        await client.set_trigger_out_on()
        assert client._last_trigger is True
        await client.set_trigger_out_off()
        assert client._last_trigger is False
