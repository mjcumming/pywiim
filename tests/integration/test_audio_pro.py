"""Integration tests for Audio Pro device support.

Tests vendor/generation detection, UPnP GetControlDeviceInfo, and source detection
for Audio Pro devices with non-standard model strings (e.g. Link 2).

Audio Pro devices use mTLS on port 4443 by default. The library auto-negotiates this.

Run with:
    WIIM_TEST_DEVICE=<ip> WIIM_TEST_PORT=4443 pytest tests/integration/test_audio_pro.py -v -m integration -s
"""

from __future__ import annotations

import os

import pytest

AUDIO_PRO_IP = os.getenv("WIIM_TEST_DEVICE", "")
AUDIO_PRO_PORT = int(os.getenv("WIIM_TEST_PORT", "4443"))

if not AUDIO_PRO_IP:
    pytest.skip("Set WIIM_TEST_DEVICE to an Audio Pro device IP to run these tests", allow_module_level=True)


@pytest.fixture
async def audio_pro_client():
    """WiiMClient connected to the Audio Pro device."""
    from pywiim.client import WiiMClient

    client = WiiMClient(AUDIO_PRO_IP, port=AUDIO_PRO_PORT)
    yield client
    await client.close()


@pytest.fixture
async def audio_pro_player(audio_pro_client):
    """Player instance connected to the Audio Pro device."""
    from pywiim.player import Player

    player = Player(audio_pro_client)
    await player.refresh(full=True)
    yield player


@pytest.mark.integration
@pytest.mark.asyncio
class TestAudioProCapabilityDetection:
    """Verify vendor/generation detection for non-standard Audio Pro model strings."""

    async def test_vendor_detected_as_audio_pro(self, audio_pro_client):
        """Device must be detected as audio_pro, not linkplay_generic."""
        from pywiim.capabilities import detect_vendor

        device_info = await audio_pro_client.get_device_info_model()
        print(f"\n  model={device_info.model!r}  firmware={device_info.firmware!r}")

        vendor = detect_vendor(device_info)
        assert vendor == "audio_pro", (
            f"Expected audio_pro but got {vendor!r}. " f"model={device_info.model!r}, firmware={device_info.firmware!r}"
        )

    async def test_generation_detected_as_mkii(self, audio_pro_client):
        """MkII firmware must map to mkii generation."""
        from pywiim.capabilities import detect_audio_pro_generation

        device_info = await audio_pro_client.get_device_info_model()
        generation = detect_audio_pro_generation(device_info)
        print(f"\n  generation={generation!r}")

        assert generation == "mkii", f"Expected mkii but got {generation!r}. " f"firmware={device_info.firmware!r}"

    async def test_profile_is_audio_pro_mkii(self, audio_pro_player):
        """Player profile must be audio_pro_mkii after initialization."""
        player = audio_pro_player
        profile = player._profile
        assert profile is not None, "Player has no profile set"
        assert profile.vendor == "audio_pro", f"Profile vendor: {profile.vendor!r}"
        assert profile.generation == "mkii", f"Profile generation: {profile.generation!r}"
        print(f"\n  profile.vendor={profile.vendor!r}  profile.generation={profile.generation!r}")

    async def test_profile_source_is_upnp(self, audio_pro_player):
        """MkII profile must prefer UPnP for source (HTTP returns mode=0 when idle)."""
        player = audio_pro_player
        assert player._profile is not None
        assert (
            player._profile.state_sources.source == "upnp"
        ), f"Expected source='upnp', got {player._profile.state_sources.source!r}"


@pytest.mark.integration
@pytest.mark.asyncio
class TestAudioProUPnPGetControlDeviceInfo:
    """Verify GetControlDeviceInfo returns valid PlayMode for source detection."""

    async def test_get_control_device_info_returns_play_mode(self, audio_pro_client):
        """GetControlDeviceInfo must return a PlayMode field."""
        from pywiim.upnp.client import UpnpClient

        description_url = f"http://{AUDIO_PRO_IP}:49152/description.xml"
        upnp_client = await UpnpClient.create(AUDIO_PRO_IP, description_url)
        try:
            result = await upnp_client.get_control_device_info()
            print(f"\n  GetControlDeviceInfo result: {result}")
            assert "PlayMode" in result, f"PlayMode not in result: {result}"
        finally:
            await upnp_client.close()

    async def test_get_control_device_info_play_mode_maps_to_source(self, audio_pro_client):
        """PlayMode returned by GetControlDeviceInfo must map to a known source string."""
        from pywiim.api.constants import MODE_MAP
        from pywiim.upnp.client import UpnpClient

        description_url = f"http://{AUDIO_PRO_IP}:49152/description.xml"
        upnp_client = await UpnpClient.create(AUDIO_PRO_IP, description_url)
        try:
            result = await upnp_client.get_control_device_info()
            play_mode = str(result.get("PlayMode", ""))
            print(f"\n  PlayMode={play_mode!r}")
            if play_mode:
                mapped = MODE_MAP.get(play_mode)
                print(f"  mapped source={mapped!r}")
                assert mapped is not None, (
                    f"PlayMode {play_mode!r} not in MODE_MAP. " f"Need to add it to pywiim/api/constants.py"
                )
        finally:
            await upnp_client.close()


@pytest.mark.integration
@pytest.mark.asyncio
class TestAudioProSourceDetection:
    """Verify source is correctly reported after refresh."""

    async def test_source_is_not_unknown_after_refresh(self, audio_pro_player):
        """After a refresh, source must not be unknown.

        Requires the device to have an active input selected (not in standby).
        """
        player = audio_pro_player
        source = player.source
        print(f"\n  source={source!r}")
        if source is None:
            pytest.skip("Device is in standby (source=None); switch to an input and retry")
        assert source != "unknown", f"source='unknown' means mode mapping failed: {source!r}"

    async def test_rca_source_detected_via_get_control_device_info(self, audio_pro_player):
        """When device is set to RCA input, refresh must report source='rca'.

        Prerequisite: switch the device to RCA input before running this test.
        """
        player = audio_pro_player
        await player.refresh()
        source = player.source
        print(f"\n  source after refresh={source!r}")
        if source is None:
            pytest.skip("Device is in standby; switch to RCA input and retry")
        assert source == "rca", (
            f"Expected source='rca' (RCA input), got {source!r}. " "Make sure the device is set to RCA input."
        )
