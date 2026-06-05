"""Unit tests for device discovery.

Tests SSDP discovery, device validation, and discovery orchestration.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pywiim.discovery import (
    DiscoveredDevice,
    discover_devices,
    discover_via_ssdp,
    is_known_linkplay,
    is_likely_non_linkplay,
    is_linkplay_device,
    validate_device,
    validate_device_strict,
)
from pywiim.exceptions import WiiMConnectionError, WiiMError
from pywiim.models import DeviceInfo


class TestDiscoveredDevice:
    """Test DiscoveredDevice dataclass."""

    def test_discovered_device_creation(self):
        """Test creating DiscoveredDevice."""
        device = DiscoveredDevice(
            ip="192.168.1.100",
            name="Test Device",
            model="WiiM Pro",
            firmware="5.0.1",
            mac="AA:BB:CC:DD:EE:FF",
            uuid="test-uuid",
            port=80,
            protocol="http",
            vendor="wiim",
            discovery_method="ssdp",
            validated=True,
        )

        assert device.ip == "192.168.1.100"
        assert device.name == "Test Device"
        assert device.validated is True

    def test_discovered_device_to_dict(self):
        """Test converting DiscoveredDevice to dict."""
        device = DiscoveredDevice(ip="192.168.1.100", name="Test Device")
        device_dict = device.to_dict()

        assert device_dict["ip"] == "192.168.1.100"
        assert device_dict["name"] == "Test Device"
        assert "validated" in device_dict

    def test_discovered_device_str(self):
        """Test DiscoveredDevice string representation."""
        device = DiscoveredDevice(ip="192.168.1.100", name="Test Device", model="WiiM Pro")
        device_str = str(device)

        assert "Test Device" in device_str
        assert "WiiM Pro" in device_str
        assert "192.168.1.100" in device_str


class TestDiscoverViaSSDP:
    """Test SSDP discovery."""

    @pytest.mark.asyncio
    async def test_discover_via_ssdp_no_async_upnp_client(self):
        """Test SSDP discovery when async-upnp-client is not available."""
        # Mock the module-level async_search to be None
        with patch("pywiim.discovery.async_search", None):
            devices = await discover_via_ssdp(timeout=5)
            assert devices == []

    @pytest.mark.asyncio
    async def test_discover_via_ssdp_success(self):
        """Test successful SSDP discovery."""
        captured_target = None
        mock_response = {
            "location": "http://192.168.1.100:49152/description.xml",
            "usn": "uuid:test-uuid::upnp:rootdevice",
        }

        async def mock_async_search(async_callback, timeout, search_target):
            nonlocal captured_target
            captured_target = search_target
            await async_callback(mock_response)

        with patch("pywiim.discovery.async_search", mock_async_search):
            devices = await discover_via_ssdp(timeout=5)

            assert len(devices) == 1
            assert devices[0].ip == "192.168.1.100"
            assert devices[0].uuid == "test-uuid"
            assert devices[0].port == 80  # API port, not UPnP port
            assert devices[0].discovery_method == "ssdp"
            assert captured_target == "urn:schemas-upnp-org:device:MediaRenderer:1"

    @pytest.mark.asyncio
    async def test_discover_via_ssdp_no_location(self):
        """Test SSDP discovery with response missing location."""
        mock_response = {"usn": "uuid:test-uuid"}

        async def mock_async_search(async_callback, timeout, search_target):
            await async_callback(mock_response)

        with patch("pywiim.discovery.async_search", mock_async_search):
            devices = await discover_via_ssdp(timeout=5)

            assert len(devices) == 0

    @pytest.mark.asyncio
    async def test_discover_via_ssdp_duplicate_ip(self):
        """Test SSDP discovery filtering duplicate IPs."""
        mock_response = {
            "location": "http://192.168.1.100:49152/description.xml",
            "usn": "uuid:test-uuid::upnp:rootdevice",
        }

        async def mock_async_search(async_callback, timeout, search_target):
            await async_callback(mock_response)
            await async_callback(mock_response)  # Duplicate

        with patch("pywiim.discovery.async_search", mock_async_search):
            devices = await discover_via_ssdp(timeout=5)

            assert len(devices) == 1  # Should filter duplicates

    @pytest.mark.asyncio
    async def test_discover_via_ssdp_https(self):
        """Test SSDP discovery with HTTPS location."""
        mock_response = {
            "location": "https://192.168.1.100:49152/description.xml",
            "usn": "uuid:test-uuid",
        }

        async def mock_async_search(async_callback, timeout, search_target):
            await async_callback(mock_response)

        with patch("pywiim.discovery.async_search", mock_async_search):
            devices = await discover_via_ssdp(timeout=5)

            assert devices[0].protocol == "https"

    @pytest.mark.asyncio
    async def test_discover_via_ssdp_exception_handling(self):
        """Test SSDP discovery exception handling."""

        async def mock_async_search(async_callback, timeout, search_target):
            raise Exception("Network error")

        with patch("pywiim.discovery.async_search", mock_async_search):
            devices = await discover_via_ssdp(timeout=5)

            assert devices == []


class TestValidateDevice:
    """Test device validation."""

    @pytest.mark.asyncio
    async def test_validate_device_success(self):
        """Test successful device validation."""
        device = DiscoveredDevice(ip="192.168.1.100", port=80, protocol="http")
        mock_device_info = DeviceInfo(
            uuid="test-uuid",
            name="Test Device",
            model="WiiM Pro",
            firmware="5.0.1",
            mac="AA:BB:CC:DD:EE:FF",
        )

        mock_client = MagicMock()
        mock_client.host = "192.168.1.100"
        mock_client.port = 80
        mock_client.capabilities = {"vendor": "wiim"}
        mock_client._detect_capabilities = AsyncMock()
        mock_client.get_device_info_model = AsyncMock(return_value=mock_device_info)
        mock_client.get_player_status = AsyncMock()
        mock_client.close = AsyncMock()

        # Mock is_linkplay_device to return True (device responds to LinkPlay API)
        with patch("pywiim.discovery.is_linkplay_device", return_value=True):
            with patch("pywiim.discovery.WiiMClient", return_value=mock_client):
                validated = await validate_device(device)

                assert validated.validated is True
                assert validated.name == "Test Device"
                assert validated.model == "WiiM Pro"
                assert validated.vendor == "wiim"
                assert validated.protocol == "http"
                mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_device_updates_protocol_from_validated_port(self):
        """Test protocol is updated to match validated API transport."""
        device = DiscoveredDevice(ip="192.168.1.100", port=80, protocol="http")
        mock_device_info = DeviceInfo(
            uuid="test-uuid",
            name="Test Device",
            model="WiiM Pro",
            firmware="5.0.1",
            mac="AA:BB:CC:DD:EE:FF",
        )

        mock_client = MagicMock()
        mock_client.host = "192.168.1.100"
        mock_client.port = 443
        mock_client.capabilities = {"vendor": "wiim"}
        mock_client._detect_capabilities = AsyncMock()
        mock_client.get_device_info_model = AsyncMock(return_value=mock_device_info)
        mock_client.get_player_status = AsyncMock()
        mock_client.close = AsyncMock()

        with patch("pywiim.discovery.is_linkplay_device", return_value=True):
            with patch("pywiim.discovery.WiiMClient", return_value=mock_client):
                validated = await validate_device(device)

                assert validated.validated is True
                assert validated.port == 443
                assert validated.protocol == "https"

    @pytest.mark.asyncio
    async def test_validate_device_already_validated(self):
        """Test validating already validated device."""
        device = DiscoveredDevice(ip="192.168.1.100", validated=True)

        validated = await validate_device(device)

        assert validated.validated is True

    @pytest.mark.asyncio
    async def test_validate_device_validation_failure(self):
        """Test device validation failure during full validation phase."""
        device = DiscoveredDevice(ip="192.168.1.100", port=80, protocol="http")

        mock_client = MagicMock()
        mock_client.host = "192.168.1.100"
        mock_client._detect_capabilities = AsyncMock(side_effect=WiiMError("Connection failed"))
        mock_client.close = AsyncMock()

        # Device passes LinkPlay probe but fails full validation
        with patch("pywiim.discovery.is_linkplay_device", return_value=True):
            with patch("pywiim.discovery.WiiMClient", return_value=mock_client):
                validated = await validate_device(device)

                assert validated.validated is False
                mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_device_not_linkplay(self):
        """Test validation skips non-LinkPlay devices (e.g., Samsung TV, Sonos)."""
        device = DiscoveredDevice(ip="192.168.1.100", port=80, protocol="http")

        # Device does NOT respond to LinkPlay API (e.g., Samsung TV)
        with patch("pywiim.discovery.is_linkplay_device", return_value=False):
            validated = await validate_device(device)

            # Should return immediately without attempting full validation
            assert validated.validated is False

    @pytest.mark.asyncio
    async def test_validate_device_strict_success(self):
        """Test strict validation returns validated devices."""
        device = DiscoveredDevice(ip="192.168.1.100", validated=True)

        with patch("pywiim.discovery.validate_device", return_value=device):
            validated = await validate_device_strict(device)

        assert validated is device
        assert validated.validated is True

    @pytest.mark.asyncio
    async def test_validate_device_strict_raises_for_unvalidated_device(self):
        """Test strict validation rejects soft validation failures."""
        device = DiscoveredDevice(ip="192.168.1.100", validated=False)

        with patch("pywiim.discovery.validate_device", return_value=device):
            with pytest.raises(WiiMConnectionError, match="did not validate"):
                await validate_device_strict(device)

    @pytest.mark.asyncio
    async def test_validate_device_http_probe_always_called(self):
        """Test validation always uses HTTP probe (no fast path, probe every device)."""
        # Device with WiiM in SSDP SERVER header - still gets probed
        device = DiscoveredDevice(
            ip="192.168.1.100",
            port=80,
            protocol="http",
            ssdp_response={"SERVER": "Linux UPnP/1.0 WiiM/4.8.5"},
        )
        mock_device_info = DeviceInfo(
            uuid="test-uuid",
            name="WiiM Device",
            model="WiiM Mini",
            firmware="4.8.5",
            mac="AA:BB:CC:DD:EE:FF",
        )

        mock_client = MagicMock()
        mock_client.host = "192.168.1.100"
        mock_client.port = 80
        mock_client.capabilities = {"vendor": "wiim"}
        mock_client._detect_capabilities = AsyncMock()
        mock_client.get_device_info_model = AsyncMock(return_value=mock_device_info)
        mock_client.get_player_status = AsyncMock()
        mock_client.close = AsyncMock()

        # HTTP probe is always called (definitive check)
        with patch("pywiim.discovery.is_linkplay_device", return_value=True) as mock_probe:
            with patch("pywiim.discovery.WiiMClient", return_value=mock_client):
                validated = await validate_device(device)

                assert validated.validated is True
                assert validated.name == "WiiM Device"
                # HTTP probe should always be called (no fast path)
                mock_probe.assert_called_once_with("192.168.1.100", 80, timeout=3.0)

    @pytest.mark.asyncio
    async def test_validate_device_client_creation_failure(self):
        """Test device validation when client creation fails."""
        device = DiscoveredDevice(ip="192.168.1.100", port=80, protocol="http")

        # Device passes LinkPlay probe but client creation fails
        with patch("pywiim.discovery.is_linkplay_device", return_value=True):
            with patch("pywiim.discovery.WiiMClient", side_effect=Exception("Failed")):
                validated = await validate_device(device)

                assert validated.validated is False


class TestDiscoverDevices:
    """Test discover_devices orchestration."""

    @pytest.mark.asyncio
    async def test_discover_devices_ssdp_only(self):
        """Test discovering devices via SSDP only."""
        mock_device = DiscoveredDevice(ip="192.168.1.100", name="Test Device", discovery_method="ssdp", validated=True)

        async def mock_validate(device):
            device.validated = True
            return device

        with patch("pywiim.discovery.discover_via_ssdp", return_value=[mock_device]):
            with patch("pywiim.discovery.validate_device", side_effect=mock_validate):
                devices = await discover_devices(methods=["ssdp"], validate=True)

                assert len(devices) == 1
                assert devices[0].ip == "192.168.1.100"

    @pytest.mark.asyncio
    async def test_discover_devices_no_validation(self):
        """Test discovering devices without validation."""
        mock_device = DiscoveredDevice(ip="192.168.1.100", name="Test Device", validated=False)

        with patch("pywiim.discovery.discover_via_ssdp", return_value=[mock_device]):
            devices = await discover_devices(methods=["ssdp"], validate=False)

            assert len(devices) == 1
            assert devices[0].validated is False

    @pytest.mark.asyncio
    async def test_discover_devices_filter_invalid(self):
        """Test filtering out invalid devices."""
        valid_device = DiscoveredDevice(ip="192.168.1.100", name="Valid", validated=True)
        invalid_device = DiscoveredDevice(ip="192.168.1.101", name="Invalid", validated=False)

        async def mock_validate(device):
            return device  # Return as-is

        with patch("pywiim.discovery.discover_via_ssdp", return_value=[valid_device, invalid_device]):
            with patch("pywiim.discovery.validate_device", side_effect=mock_validate):
                devices = await discover_devices(methods=["ssdp"], validate=True)

                # Should only include validated devices
                assert len(devices) == 1
                assert devices[0].validated is True

    @pytest.mark.asyncio
    async def test_discover_devices_remove_duplicates(self):
        """Test removing duplicate devices by IP."""
        device1 = DiscoveredDevice(ip="192.168.1.100", name="Device 1")
        device2 = DiscoveredDevice(ip="192.168.1.100", name="Device 2")  # Same IP

        with patch("pywiim.discovery.discover_via_ssdp", return_value=[device1, device2]):
            with patch("pywiim.discovery.validate_device", side_effect=lambda d: d):
                devices = await discover_devices(methods=["ssdp"], validate=False)

                assert len(devices) == 1  # Should remove duplicate

    @pytest.mark.asyncio
    async def test_discover_devices_default_methods(self):
        """Test discovering devices with default methods."""
        mock_device = DiscoveredDevice(ip="192.168.1.100", name="Test Device", validated=True)

        async def mock_validate(device):
            device.validated = True
            return device

        with patch("pywiim.discovery.discover_via_ssdp", return_value=[mock_device]):
            with patch("pywiim.discovery.validate_device", side_effect=mock_validate):
                devices = await discover_devices()

                assert len(devices) == 1

    @pytest.mark.asyncio
    async def test_discover_devices_filter_sonos(self):
        """Test filtering out Sonos devices via HTTP probe."""
        sonos_device = DiscoveredDevice(
            ip="192.168.1.100",
            name="Sonos Device",
            discovery_method="ssdp",
            ssdp_response={
                "SERVER": "Linux UPnP/1.0 Sonos/70.1-82030",
                "st": "urn:schemas-upnp-org:device:ZonePlayer:1",
            },
        )
        wiim_device = DiscoveredDevice(
            ip="192.168.1.101",
            name="WiiM Device",
            discovery_method="ssdp",
            ssdp_response={"SERVER": "Linux/5.15.0", "st": "upnp:rootdevice"},
        )

        # Mock HTTP probe: Sonos returns False, WiiM returns True
        async def mock_is_linkplay(host, port, timeout):
            return host == "192.168.1.101"

        mock_device_info = DeviceInfo(
            name="WiiM Device",
            model="WiiM Mini",
            firmware="4.8.123456",
            mac="AA:BB:CC:DD:EE:FF",
            uuid="12345678-1234-1234-1234-123456789abc",
        )
        mock_client = MagicMock()
        mock_client.host = "192.168.1.101"
        mock_client.port = 80
        mock_client.capabilities = {"vendor": "wiim"}
        mock_client._detect_capabilities = AsyncMock()
        mock_client.get_device_info_model = AsyncMock(return_value=mock_device_info)
        mock_client.get_player_status = AsyncMock()
        mock_client.close = AsyncMock()

        with patch("pywiim.discovery.discover_via_ssdp", return_value=[sonos_device, wiim_device]):
            with patch("pywiim.discovery.is_linkplay_device", side_effect=mock_is_linkplay):
                with patch("pywiim.discovery.WiiMClient", return_value=mock_client):
                    devices = await discover_devices(methods=["ssdp"], validate=True)

                    # Should only include WiiM device, Sonos should be filtered by HTTP probe
                    assert len(devices) == 1
                    assert devices[0].ip == "192.168.1.101"

    @pytest.mark.asyncio
    async def test_discover_devices_skips_known_non_linkplay_before_validation(self):
        """Known non-LinkPlay SSDP matches should be skipped before validation."""
        sonos_device = DiscoveredDevice(
            ip="192.168.1.100",
            discovery_method="ssdp",
            ssdp_response={
                "SERVER": "Linux UPnP/1.0 Sonos/70.1-82030",
                "st": "urn:schemas-upnp-org:device:ZonePlayer:1",
            },
        )
        candidate = DiscoveredDevice(
            ip="192.168.1.101",
            discovery_method="ssdp",
            ssdp_response={"SERVER": "Linux", "st": "upnp:rootdevice"},
        )

        async def mock_validate(device):
            device.validated = True
            return device

        with patch("pywiim.discovery.discover_via_ssdp", return_value=[sonos_device, candidate]):
            with patch("pywiim.discovery.validate_device", side_effect=mock_validate) as mock_validate_fn:
                devices = await discover_devices(methods=["ssdp"], validate=True)

                assert len(devices) == 1
                assert devices[0].ip == "192.168.1.101"
                assert mock_validate_fn.await_count == 1


class TestIsLikelyNonLinkplay:
    """Test is_likely_non_linkplay filtering function."""

    def test_sonos_server_header(self):
        """Test Sonos device identified by SERVER header."""
        ssdp_response = {"SERVER": "Linux UPnP/1.0 Sonos/70.1-82030"}
        assert is_likely_non_linkplay(ssdp_response) is True

    def test_sonos_st_header(self):
        """Test Sonos device identified by ST header."""
        ssdp_response = {"st": "urn:schemas-upnp-org:device:ZonePlayer:1"}
        assert is_likely_non_linkplay(ssdp_response) is True

    def test_chromecast_server_header(self):
        """Test Chromecast device identified by SERVER header."""
        ssdp_response = {"SERVER": "Linux/4.19.260, UPnP/1.0, Chromecast/1.6.18"}
        assert is_likely_non_linkplay(ssdp_response) is True

    def test_chromecast_dial_st_header(self):
        """Test Chromecast device identified by DIAL ST header."""
        ssdp_response = {"st": "urn:dial-multiscreen-org:device:dial:1"}
        assert is_likely_non_linkplay(ssdp_response) is True

    def test_roku_st_header(self):
        """Test Roku device identified by ST header."""
        ssdp_response = {"st": "urn:roku-com:device:player:1-0"}
        assert is_likely_non_linkplay(ssdp_response) is True

    def test_denon_heos_server_header(self):
        """Test Denon Heos device identified by SERVER header."""
        ssdp_response = {"SERVER": "LINUX UPnP/1.0 Denon-Heos/1.2.3"}
        assert is_likely_non_linkplay(ssdp_response) is True

    def test_sony_server_header(self):
        """Test Sony device identified by SERVER header."""
        ssdp_response = {"SERVER": "FedoraCore/2 UPnP/1.0 MINT-X/1.8.1"}
        assert is_likely_non_linkplay(ssdp_response) is True

    def test_kodi_server_header(self):
        """Test Kodi device identified by SERVER header."""
        ssdp_response = {"SERVER": "KnOS/3.2 UPnP/1.0 DMP/3.5"}
        assert is_likely_non_linkplay(ssdp_response) is True

    def test_generic_linux_not_filtered(self):
        """Test generic Linux device is not filtered (might be LinkPlay)."""
        ssdp_response = {"SERVER": "Linux/5.15.0 UPnP/1.0"}
        assert is_likely_non_linkplay(ssdp_response) is False

    def test_wiim_device_not_filtered(self):
        """Test WiiM device is not filtered."""
        ssdp_response = {"SERVER": "Linux UPnP/1.0 WiiM/4.8.5", "st": "upnp:rootdevice"}
        assert is_likely_non_linkplay(ssdp_response) is False

    def test_audio_pro_device_not_filtered(self):
        """Test Audio Pro device is not filtered (uses generic Linux header)."""
        ssdp_response = {"SERVER": "Linux", "st": "upnp:rootdevice"}
        assert is_likely_non_linkplay(ssdp_response) is False

    def test_empty_headers_not_filtered(self):
        """Test device with no SERVER or ST headers is not filtered."""
        ssdp_response = {}
        assert is_likely_non_linkplay(ssdp_response) is False

    def test_case_insensitive_matching(self):
        """Test pattern matching is case insensitive."""
        ssdp_response = {"SERVER": "linux upnp/1.0 sonos/70.1"}
        assert is_likely_non_linkplay(ssdp_response) is True

    def test_st_and_server_both_checked(self):
        """Test both ST and SERVER headers are checked."""
        # Sonos in SERVER
        assert is_likely_non_linkplay({"SERVER": "Sonos/70.1"}) is True
        # Sonos in ST
        assert is_likely_non_linkplay({"st": "urn:schemas-upnp-org:device:ZonePlayer:1"}) is True
        # Neither
        assert is_likely_non_linkplay({"SERVER": "Linux", "st": "upnp:rootdevice"}) is False

    def test_samsung_server_header(self):
        """Test Samsung device identified by SERVER header."""
        ssdp_response = {"SERVER": "Samsung/1.0 UPnP/1.0"}
        assert is_likely_non_linkplay(ssdp_response) is True

    def test_samsung_sec_hhp_header(self):
        """Test Samsung device identified by SEC_HHP pattern."""
        ssdp_response = {"SERVER": "SEC_HHP_[TV] Samsung Q60 Series"}
        assert is_likely_non_linkplay(ssdp_response) is True

    def test_samsung_st_header(self):
        """Test Samsung device identified by ST header."""
        ssdp_response = {"st": "urn:samsung.com:device:RemoteControlReceiver:1"}
        assert is_likely_non_linkplay(ssdp_response) is True

    def test_smartthings_server_header(self):
        """Test SmartThings device identified by SERVER header."""
        ssdp_response = {"SERVER": "SmartThings/1.0 UPnP/1.0"}
        assert is_likely_non_linkplay(ssdp_response) is True


class TestIsKnownLinkplay:
    """Test is_known_linkplay fast-path function."""

    def test_wiim_server_header(self):
        """Test WiiM device identified by SERVER header."""
        ssdp_response = {"SERVER": "Linux UPnP/1.0 WiiM/4.8.5"}
        assert is_known_linkplay(ssdp_response) is True

    def test_linkplay_server_header(self):
        """Test LinkPlay device identified by SERVER header."""
        ssdp_response = {"SERVER": "Linux/5.10.0 Linkplay/2.0"}
        assert is_known_linkplay(ssdp_response) is True

    def test_arylic_server_header(self):
        """Test Arylic device identified by SERVER header (if exposed).

        Note: Many Arylic devices use generic 'Linux' headers, so this pattern
        may not match in practice. They'll still work via the API probe.
        """
        ssdp_response = {"SERVER": "Linux UPnP/1.0 Arylic/3.2.1"}
        assert is_known_linkplay(ssdp_response) is True

    def test_audio_pro_server_header(self):
        """Test Audio Pro device identified by SERVER header."""
        ssdp_response = {"SERVER": "Linux UPnP/1.0 Audio Pro/1.5"}
        assert is_known_linkplay(ssdp_response) is True

    def test_ieast_server_header(self):
        """Test iEAST device identified by SERVER header."""
        ssdp_response = {"SERVER": "Linux UPnP/1.0 iEAST/2.0"}
        assert is_known_linkplay(ssdp_response) is True

    def test_generic_linux_not_known(self):
        """Test generic Linux device is NOT identified as known LinkPlay."""
        ssdp_response = {"SERVER": "Linux/5.15.0 UPnP/1.0"}
        assert is_known_linkplay(ssdp_response) is False

    def test_empty_response_not_known(self):
        """Test empty response is not identified as known LinkPlay."""
        assert is_known_linkplay({}) is False
        assert is_known_linkplay(None) is False  # type: ignore[arg-type]

    def test_case_insensitive_matching(self):
        """Test pattern matching is case insensitive."""
        assert is_known_linkplay({"SERVER": "linux upnp/1.0 wiim/4.8.5"}) is True
        assert is_known_linkplay({"SERVER": "LINUX UPNP/1.0 WIIM/4.8.5"}) is True

    def test_sonos_not_known_linkplay(self):
        """Test Sonos device is NOT identified as known LinkPlay."""
        ssdp_response = {"SERVER": "Linux UPnP/1.0 Sonos/70.1"}
        assert is_known_linkplay(ssdp_response) is False

    def test_samsung_not_known_linkplay(self):
        """Test Samsung device is NOT identified as known LinkPlay."""
        ssdp_response = {"SERVER": "Samsung/1.0 UPnP/1.0"}
        assert is_known_linkplay(ssdp_response) is False


class TestIsLinkplayDevice:
    """Test is_linkplay_device probe function."""

    @pytest.mark.asyncio
    async def test_linkplay_device_responds(self):
        """Test device that responds to getStatusEx is identified as LinkPlay."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"project": "WiiM_Mini", "uuid": "123"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await is_linkplay_device("192.168.1.100")
            assert result is True

    @pytest.mark.asyncio
    async def test_non_linkplay_device_no_response(self):
        """Test device that doesn't respond is not identified as LinkPlay."""
        import aiohttp

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=aiohttp.ClientError("Connection refused"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await is_linkplay_device("192.168.1.100")
            assert result is False

    @pytest.mark.asyncio
    async def test_non_linkplay_device_non_json_response(self):
        """Test device that returns non-JSON is not identified as LinkPlay."""
        import json

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(side_effect=json.JSONDecodeError("", "", 0))
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await is_linkplay_device("192.168.1.100")
            assert result is False

    @pytest.mark.asyncio
    async def test_device_returns_empty_dict(self):
        """Test device that returns empty dict is not identified as LinkPlay."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={})  # Empty dict
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await is_linkplay_device("192.168.1.100")
            assert result is False

    @pytest.mark.asyncio
    async def test_device_timeout(self):
        """Test device that times out is not identified as LinkPlay."""
        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=TimeoutError())
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await is_linkplay_device("192.168.1.100")
            assert result is False

    @pytest.mark.asyncio
    async def test_linkplay_device_responds_on_443_fallback(self):
        """Test fallback probe to 443 when discovery-provided port 80 fails."""
        import aiohttp

        mock_ok_response = MagicMock()
        mock_ok_response.status = 200
        mock_ok_response.json = AsyncMock(return_value={"project": "WiiM_Amp", "uuid": "123"})
        mock_ok_response.__aenter__ = AsyncMock(return_value=mock_ok_response)
        mock_ok_response.__aexit__ = AsyncMock(return_value=None)

        def mock_get(url, *args, **kwargs):
            if "https://192.168.1.100:443/httpapi.asp?command=getStatusEx" in url:
                return mock_ok_response
            raise aiohttp.ClientError("Connection refused")

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=mock_get)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await is_linkplay_device("192.168.1.100", port=80)
            assert result is True

    @pytest.mark.asyncio
    async def test_linkplay_device_responds_on_4443_fallback(self):
        """Test fallback probe to 4443 when 80 and 443 fail."""
        import aiohttp

        mock_ok_response = MagicMock()
        mock_ok_response.status = 200
        mock_ok_response.json = AsyncMock(return_value={"project": "AudioPro", "uuid": "123"})
        mock_ok_response.__aenter__ = AsyncMock(return_value=mock_ok_response)
        mock_ok_response.__aexit__ = AsyncMock(return_value=None)

        def mock_get(url, *args, **kwargs):
            if "https://192.168.1.100:4443/httpapi.asp?command=getPlayerStatusEx" in url:
                return mock_ok_response
            raise aiohttp.ClientError("Connection refused")

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=mock_get)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await is_linkplay_device("192.168.1.100", port=80)
            assert result is True

    @pytest.mark.asyncio
    async def test_linkplay_device_responds_to_player_status_ex_only(self):
        """Test device validation when only getPlayerStatusEx is supported."""
        import aiohttp

        mock_ok_response = MagicMock()
        mock_ok_response.status = 200
        mock_ok_response.json = AsyncMock(return_value={"mode": "1", "volume": "50"})
        mock_ok_response.__aenter__ = AsyncMock(return_value=mock_ok_response)
        mock_ok_response.__aexit__ = AsyncMock(return_value=None)

        def mock_get(url, *args, **kwargs):
            if "getPlayerStatusEx" in url:
                return mock_ok_response
            raise aiohttp.ClientError("Endpoint not supported")

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=mock_get)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await is_linkplay_device("192.168.1.100", port=443)
            assert result is True

    @pytest.mark.asyncio
    async def test_linkplay_device_client_fallback_when_probe_inconclusive(self):
        """Test WiiMClient fallback when lightweight endpoint probe fails."""
        import aiohttp

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=aiohttp.ClientError("Probe path failed"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_client = MagicMock()
        mock_client.get_player_status = AsyncMock(return_value={"mode": "1", "volume": "25"})
        mock_client.base_url = "https://192.168.1.100:443"
        mock_client.close = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with patch("pywiim.discovery.WiiMClient", return_value=mock_client):
                result = await is_linkplay_device("192.168.1.100", port=80)
                assert result is True
                mock_client.get_player_status.assert_awaited_once()
                mock_client.close.assert_awaited_once()
