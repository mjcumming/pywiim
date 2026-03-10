"""Unit tests for Misc API."""

import json
from urllib.parse import unquote

import pytest

from pywiim.api.base import ApiResponse
from pywiim.exceptions import WiiMError


class TestMiscAPI:
    """Test MiscAPI mixin."""

    @pytest.mark.asyncio
    async def test_set_buttons_enabled(self, mock_client):
        """Test setting buttons enabled."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                return ApiResponse(parsed={"status": "ok"}, raw=None)

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
                return ApiResponse(parsed={"status": "ok"}, raw=None)

        client = TestClient()
        await client.set_led_switch(True)
        await client.set_led_switch(False)

    @pytest.mark.asyncio
    async def test_get_led_indicator_from_status_returns_false_when_led_0(self, mock_client):
        """Test get_led_indicator returns False when getStatusEx has led=0."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def get_device_info(self):
                return {"led": 0}

        client = TestClient()
        client._capabilities = {}
        result = await client.get_led_indicator()
        assert result is False

    @pytest.mark.asyncio
    async def test_get_led_indicator_from_status_returns_true_when_led_1(self, mock_client):
        """Test get_led_indicator returns True when getStatusEx has led=1."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def get_device_info(self):
                return {"LED": 1}

        client = TestClient()
        client._capabilities = {}
        result = await client.get_led_indicator()
        assert result is True

    @pytest.mark.asyncio
    async def test_get_led_indicator_assumes_on_when_no_read_api(self, mock_client):
        """Test get_led_indicator returns True (assume on) when no led in status."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def get_device_info(self):
                return {"vol": 50}

        client = TestClient()
        client._capabilities = {}
        result = await client.get_led_indicator()
        assert result is True

    @pytest.mark.asyncio
    async def test_get_led_indicator_arylic_parses_mcu_response(self, mock_client):
        """Test get_led_indicator for Arylic parses getMCUASCIICmd:LED response."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def get_device_info(self):
                return {}

            async def _request(self, endpoint):
                return ApiResponse(parsed=None, raw="LED:0")

        client = TestClient()
        client._capabilities = {"vendor": "arylic"}
        result = await client.get_led_indicator()
        assert result is False

    @pytest.mark.asyncio
    async def test_set_led_switch_arylic_does_not_raise(self, mock_client):
        """Test set_led_switch for Arylic does not raise on failure (try-and-ignore)."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                raise WiiMError("unknown command")

        client = TestClient()
        client._capabilities = {"vendor": "arylic"}
        await client.set_led_switch(True)
        await client.set_led_switch(False)

    @pytest.mark.asyncio
    async def test_set_display_config(self, mock_client):
        """Test set_display_config sends correct setLightOperationBrightConfig command."""
        from pywiim.api.constants import API_ENDPOINT_DISPLAY_CONFIG
        from pywiim.api.misc import MiscAPI

        requests = []

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                requests.append(endpoint)
                return ApiResponse(parsed="OK", raw=None)

        client = TestClient()
        await client.set_display_config(auto_sense_enable=0, default_bright=1, disable=1)
        assert len(requests) == 1
        assert requests[0].startswith(API_ENDPOINT_DISPLAY_CONFIG)
        # Payload after base: URL-encoded JSON
        payload_str = unquote(requests[0][len(API_ENDPOINT_DISPLAY_CONFIG) :])
        payload = json.loads(payload_str)
        assert payload == {"auto_sense_enable": 0, "default_bright": 1, "disable": 1}

    @pytest.mark.asyncio
    async def test_set_display_enabled(self, mock_client):
        """Test set_display_enabled calls set_display_config with correct disable value."""
        from pywiim.api.misc import MiscAPI

        calls = []

        class TestClient(MiscAPI):
            async def set_display_config(self, *, auto_sense_enable=0, default_bright=1, disable=0):
                calls.append({"disable": disable})

        client = TestClient()
        await client.set_display_enabled(True)
        await client.set_display_enabled(False)
        assert calls == [{"disable": 0}, {"disable": 1}]

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
                    return ApiResponse(parsed={"status": 1}, raw=None)
                return ApiResponse(parsed={"status": "ok"}, raw=None)

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
                    return ApiResponse(parsed={"status": 0}, raw=None)
                return ApiResponse(parsed={"status": "ok"}, raw=None)

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
                return ApiResponse(parsed={"status": "ok"}, raw=None)

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
                return ApiResponse(parsed={"status": "OK"}, raw=None)

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
