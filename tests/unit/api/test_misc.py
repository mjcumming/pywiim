"""Unit tests for Misc API."""

import json
from urllib.parse import unquote

import pytest

from pywiim.api.base import ApiResponse
from pywiim.exceptions import WiiMError


class TestMiscAPI:
    """Test MiscAPI mixin."""

    @pytest.mark.asyncio
    async def test_get_audio_input_enable(self):
        """Test getAudioInputEnable model parsing."""
        from pywiim.api.constants import API_ENDPOINT_GET_AUDIO_INPUT_ENABLE
        from pywiim.api.misc import MiscAPI

        requests = []

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                requests.append(endpoint)
                return ApiResponse(
                    parsed={
                        "ver": "1.0",
                        "audioInput": [
                            {"mode": "wifi", "enable": 1},
                            {"mode": "phono", "enable": "0"},
                        ],
                    },
                    raw=None,
                )

        result = await TestClient().get_audio_input_enable()

        assert requests == [API_ENDPOINT_GET_AUDIO_INPUT_ENABLE]
        assert result is not None
        assert result.version == "1.0"
        assert result.audio_input[0].mode == "wifi"
        assert result.audio_input[0].enable is True
        assert result.audio_input[1].enable is False

    @pytest.mark.asyncio
    async def test_get_audio_input_enable_unsupported(self):
        """Unsupported getAudioInputEnable returns None."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                raise WiiMError("unknown command")

        assert await TestClient().get_audio_input_enable() is None

    @pytest.mark.asyncio
    async def test_get_audio_input_enable_unsupported_error_payload(self):
        """Unsupported getAudioInputEnable error dictionaries return None."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                return ApiResponse(parsed={"error": "unsupported_command", "raw": "unknown command"}, raw=None)

        assert await TestClient().get_audio_input_enable() is None

    @pytest.mark.asyncio
    async def test_get_mode_rename(self):
        """Test getModeRename dynamic map parsing."""
        from pywiim.api.constants import API_ENDPOINT_GET_MODE_RENAME
        from pywiim.api.misc import MiscAPI

        requests = []

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                requests.append(endpoint)
                return ApiResponse(parsed={"SPDIF-In": "Phono", "optical": "TV"}, raw=None)

        result = await TestClient().get_mode_rename()

        assert requests == [API_ENDPOINT_GET_MODE_RENAME]
        assert result == {"SPDIF-In": "Phono", "optical": "TV"}

    @pytest.mark.asyncio
    async def test_get_mode_rename_failed_returns_none(self):
        """Firmware returns plain Failed when no modes are renamed."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                return ApiResponse(parsed=None, raw="Failed")

        assert await TestClient().get_mode_rename() is None

    @pytest.mark.asyncio
    async def test_get_mode_rename_unsupported_error_payload(self):
        """Unsupported getModeRename error dictionaries return None."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                return ApiResponse(parsed={"error": "unsupported_command", "raw": "unknown command"}, raw=None)

        assert await TestClient().get_mode_rename() is None

    @pytest.mark.asyncio
    async def test_get_acoustic_capability(self):
        """Test GetAcousticCapability parsing."""
        from pywiim.api.constants import API_ENDPOINT_GET_ACOUSTIC_CAPABILITY
        from pywiim.api.misc import MiscAPI

        requests = []

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                requests.append(endpoint)
                return ApiResponse(
                    parsed={
                        "Version": "1.0",
                        "PEQ": {"Version": "1.0", "Filters": ["OFF", "PK"]},
                        "OutputDelay": {"EnableMicroDelay": True, "StepDelayUs": 100},
                    },
                    raw=None,
                )

        result = await TestClient().get_acoustic_capability()

        assert requests == [API_ENDPOINT_GET_ACOUSTIC_CAPABILITY]
        assert result is not None
        assert result.version == "1.0"
        assert result.peq == {"Version": "1.0", "Filters": ["OFF", "PK"]}
        assert result.output_delay["StepDelayUs"] == 100

    @pytest.mark.asyncio
    async def test_get_acoustic_capability_unsupported_error_payload(self):
        """Unsupported GetAcousticCapability error dictionaries return None."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                return ApiResponse(parsed={"error": "unsupported_command", "raw": "unknown command"}, raw=None)

        assert await TestClient().get_acoustic_capability() is None

    @pytest.mark.asyncio
    async def test_get_all_routines(self):
        """Test getAllRoutines parsing."""
        from pywiim.api.constants import API_ENDPOINT_GET_ALL_ROUTINES
        from pywiim.api.misc import MiscAPI

        requests = []

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                requests.append(endpoint)
                return ApiResponse(
                    parsed={
                        "routines": [
                            {
                                "id": "0000000067570795",
                                "name": "PC",
                                "index": 3,
                                "createDate": "2026-06-23T06:08:26Z",
                                "steps": [{"type": "audioInput", "payload": {"input": "optical"}}],
                            }
                        ]
                    },
                    raw=None,
                )

        result = await TestClient().get_all_routines()

        assert requests == [API_ENDPOINT_GET_ALL_ROUTINES]
        assert result is not None
        assert len(result.routines) == 1
        assert result.routines[0].name == "PC"
        assert result.routines[0].create_date == "2026-06-23T06:08:26Z"
        assert result.routines[0].steps[0].payload == {"input": "optical"}

    @pytest.mark.asyncio
    async def test_get_all_routines_failed_error_payload(self):
        """Unsupported getAllRoutines failed dictionaries return None."""
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                return ApiResponse(parsed={"state": -1, "error": "Fail"}, raw=None)

        assert await TestClient().get_all_routines() is None

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

    def test_parse_led_switch_get_response_from_raw(self):
        from pywiim.api.misc import MiscAPI

        assert MiscAPI._parse_led_switch_get_response("1", None) is True
        assert MiscAPI._parse_led_switch_get_response("0", None) is False
        assert MiscAPI._parse_led_switch_get_response(" 1 ", None) is True
        assert MiscAPI._parse_led_switch_get_response(None, 0) is False
        assert MiscAPI._parse_led_switch_get_response(None, None) is None

    @pytest.mark.asyncio
    async def test_get_led_indicator_from_led_switch_get_on(self, mock_client):
        """LED_SWITCH_GET returning 1 maps to True."""
        from pywiim.api.constants import API_ENDPOINT_GET_LED_SWITCH
        from pywiim.api.misc import MiscAPI

        class TestClient(MiscAPI):
            async def get_device_info(self):
                return {}

            async def _request(self, endpoint):
                if endpoint == API_ENDPOINT_GET_LED_SWITCH:
                    return ApiResponse(parsed=None, raw="1")
                return ApiResponse(parsed=None, raw="")

        client = TestClient()
        client._capabilities = {"supports_led_switch": True}
        assert await client.get_led_indicator() is True

    @pytest.mark.asyncio
    async def test_get_led_indicator_from_led_switch_get(self, mock_client):
        """Test get_led_indicator uses LED_SWITCH_GET on WiiM (plain 0/1)."""
        from pywiim.api.constants import API_ENDPOINT_GET_LED_SWITCH
        from pywiim.api.misc import MiscAPI

        requests: list[str] = []

        class TestClient(MiscAPI):
            async def get_device_info(self):
                return {}

            async def _request(self, endpoint):
                requests.append(endpoint)
                if endpoint == API_ENDPOINT_GET_LED_SWITCH:
                    return ApiResponse(parsed=None, raw="0")
                return ApiResponse(parsed=None, raw="")

        client = TestClient()
        client._capabilities = {"supports_led_switch": True, "is_wiim_device": True}
        result = await client.get_led_indicator()
        assert result is False
        assert API_ENDPOINT_GET_LED_SWITCH in requests

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
        """Test set_display_enabled sends full JSON; on uses max default brightness."""
        from pywiim.api.constants import (
            API_ENDPOINT_DISPLAY_CONFIG,
            DISPLAY_DEFAULT_BRIGHTNESS,
        )
        from pywiim.api.misc import MiscAPI

        requests = []

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                requests.append(endpoint)
                return ApiResponse(parsed="OK", raw=None)

        client = TestClient()
        await client.set_display_enabled(True)
        await client.set_display_enabled(False)
        assert len(requests) == 2
        on_payload = json.loads(unquote(requests[0][len(API_ENDPOINT_DISPLAY_CONFIG) :]))
        off_payload = json.loads(unquote(requests[1][len(API_ENDPOINT_DISPLAY_CONFIG) :]))
        # Turning on enables adaptive brightness (auto_sense_enable=1) so the
        # panel relights on WiiM Ultra firmware (mjcumming/wiim#250).
        assert on_payload == {
            "auto_sense_enable": 1,
            "default_bright": DISPLAY_DEFAULT_BRIGHTNESS,
            "disable": 0,
        }
        assert off_payload == {
            "auto_sense_enable": 0,
            "default_bright": DISPLAY_DEFAULT_BRIGHTNESS,
            "disable": 1,
        }

    @pytest.mark.asyncio
    async def test_set_display_enabled_custom_brightness(self, mock_client):
        """Test set_display_enabled(True, default_bright=...) overrides default."""
        from pywiim.api.constants import API_ENDPOINT_DISPLAY_CONFIG
        from pywiim.api.misc import MiscAPI

        requests = []

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                requests.append(endpoint)
                return ApiResponse(parsed="OK", raw=None)

        client = TestClient()
        await client.set_display_enabled(True, default_bright=42)
        payload = json.loads(unquote(requests[0][len(API_ENDPOINT_DISPLAY_CONFIG) :]))
        assert payload["default_bright"] == 42
        assert payload["disable"] == 0

    @pytest.mark.asyncio
    async def test_set_display_enabled_auto_sense_override(self, mock_client):
        """Test set_display_enabled(True, auto_sense_enable=0) keeps adaptive brightness off."""
        from pywiim.api.constants import API_ENDPOINT_DISPLAY_CONFIG
        from pywiim.api.misc import MiscAPI

        requests = []

        class TestClient(MiscAPI):
            async def _request(self, endpoint):
                requests.append(endpoint)
                return ApiResponse(parsed="OK", raw=None)

        client = TestClient()
        await client.set_display_enabled(True, auto_sense_enable=0)
        payload = json.loads(unquote(requests[0][len(API_ENDPOINT_DISPLAY_CONFIG) :]))
        assert payload["auto_sense_enable"] == 0
        assert payload["disable"] == 0

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
