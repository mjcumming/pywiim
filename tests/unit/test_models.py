"""Unit tests for Pydantic models.

Tests field validation, aliases, defaults, serialization, and forward compatibility.
"""

from __future__ import annotations

import pytest

from pywiim.models import (
    AcousticCapability,
    AudioInputEnable,
    DeviceGroupInfo,
    DeviceInfo,
    EQInfo,
    GroupDeviceState,
    GroupState,
    MultiroomInfo,
    PlayerStatus,
    PollingMetrics,
    RoutineList,
    SlaveInfo,
    SoundCardModeSupport,
    TrackMetadata,
)


class TestDeviceInfo:
    """Test DeviceInfo model."""

    def test_device_info_minimal(self):
        """Test DeviceInfo with minimal required fields."""
        info = DeviceInfo(uuid="test-uuid")
        assert info.uuid == "test-uuid"
        assert info.name is None
        assert info.model is None

    def test_device_info_field_aliases(self):
        """Test DeviceInfo field aliases match API keys."""
        info = DeviceInfo(
            DeviceName="Test Device",
            project="WiiM Pro",
            MAC="AA:BB:CC:DD:EE:FF",
            Release="2024-01-01",
            VersionUpdate="5.0.2",
            NewVer="5.0.3",
        )
        assert info.name == "Test Device"
        assert info.model == "WiiM Pro"
        assert info.mac == "AA:BB:CC:DD:EE:FF"
        assert info.release_date == "2024-01-01"
        assert info.version_update == "5.0.2"
        assert info.latest_version == "5.0.3"

    def test_device_info_field_names(self):
        """Test DeviceInfo with Python field names."""
        info = DeviceInfo(
            name="Test Device",
            model="WiiM Pro",
            mac="AA:BB:CC:DD:EE:FF",
            firmware="5.0.1",
        )
        assert info.name == "Test Device"
        assert info.model == "WiiM Pro"
        assert info.mac == "AA:BB:CC:DD:EE:FF"
        assert info.firmware == "5.0.1"

    def test_device_info_extra_fields(self):
        """Test DeviceInfo allows extra fields for forward compatibility."""
        info = DeviceInfo(
            uuid="test",
            name="Test",
            unknown_field="value",  # Should not raise error
            another_unknown=123,
        )
        assert hasattr(info, "unknown_field")
        assert info.unknown_field == "value"
        assert hasattr(info, "another_unknown")
        assert info.another_unknown == 123

    def test_device_info_input_list_list(self):
        """Test input_list normalization with list input."""
        info = DeviceInfo(InputList=["wifi", "bluetooth", "line_in"])
        assert info.input_list == ["wifi", "bluetooth", "line_in"]

    def test_device_info_input_list_string(self):
        """Test input_list normalization with comma-separated string."""
        info = DeviceInfo(InputList="wifi,bluetooth,line_in")
        assert info.input_list == ["wifi", "bluetooth", "line_in"]

    def test_device_info_input_list_string_with_spaces(self):
        """Test input_list normalization with spaces."""
        info = DeviceInfo(InputList="wifi, bluetooth , line_in")
        assert info.input_list == ["wifi", "bluetooth", "line_in"]

    def test_device_info_input_list_empty_string(self):
        """Test input_list normalization with empty string."""
        info = DeviceInfo(InputList="")
        assert info.input_list is None

    def test_device_info_input_list_none(self):
        """Test input_list normalization with None."""
        info = DeviceInfo(InputList=None)
        assert info.input_list is None

    def test_device_info_input_list_variations(self):
        """Test input_list with various field name variations."""
        # Test InputList (canonical)
        info1 = DeviceInfo(InputList=["wifi", "bluetooth"])
        assert info1.input_list == ["wifi", "bluetooth"]

        # Test inputList (camelCase)
        info2 = DeviceInfo.model_validate({"inputList": ["wifi", "bluetooth"]})
        assert info2.input_list == ["wifi", "bluetooth"]

        # Test input_list (snake_case)
        info3 = DeviceInfo.model_validate({"input_list": ["wifi", "bluetooth"]})
        assert info3.input_list == ["wifi", "bluetooth"]

        # Test inputlist (lowercase)
        info4 = DeviceInfo.model_validate({"inputlist": ["wifi", "bluetooth"]})
        assert info4.input_list == ["wifi", "bluetooth"]


class TestPlayerStatus:
    """Test PlayerStatus model."""

    def test_player_status_minimal(self):
        """Test PlayerStatus with minimal fields."""
        status = PlayerStatus()
        assert status.play_state is None
        assert status.volume is None

    def test_player_status_field_aliases(self):
        """Test PlayerStatus field aliases match API keys."""
        status = PlayerStatus(
            play_status="play",
            vol=50,
            Title="Test Song",
            Artist="Test Artist",
            Album="Test Album",
            eq="rock",
            RSSI=-60,
            WifiChannel=6,
        )
        assert status.play_state == "play"
        assert status.volume == 50
        assert status.title == "Test Song"
        assert status.artist == "Test Artist"
        assert status.album == "Test Album"
        assert status.eq_preset == "rock"
        assert status.wifi_rssi == -60
        assert status.wifi_channel == 6

    def test_player_status_volume_validation(self):
        """Test PlayerStatus volume validation (0-100)."""
        # Valid volumes
        status1 = PlayerStatus(vol=0)
        assert status1.volume == 0

        status2 = PlayerStatus(vol=50)
        assert status2.volume == 50

        status3 = PlayerStatus(vol=100)
        assert status3.volume == 100

        # Invalid volumes should be caught by Pydantic
        from pydantic import ValidationError

        with pytest.raises(ValidationError):  # Pydantic validation error
            PlayerStatus(vol=-1)

        with pytest.raises(ValidationError):  # Pydantic validation error
            PlayerStatus(vol=101)

    def test_player_status_source_normalization(self):
        """Test PlayerStatus source casing preservation for UI display."""
        status1 = PlayerStatus(source="SPOTIFY")
        assert status1.source == "SPOTIFY"  # Preserves original casing

        status2 = PlayerStatus(source="Bluetooth")
        assert status2.source == "Bluetooth"  # Preserves original casing

        status3 = PlayerStatus(source="AirPlay")
        assert status3.source == "AirPlay"  # Preserves original casing

        status4 = PlayerStatus(source=None)
        assert status4.source is None

    def test_player_status_play_state_normalization(self):
        """Test PlayerStatus play_state normalization."""
        # Test lowercase conversion
        status1 = PlayerStatus(play_status="PLAY")
        assert status1.play_state == "play"

        # Test 'none' -> 'idle' conversion
        status2 = PlayerStatus(play_status="none")
        assert status2.play_state == "idle"

        status3 = PlayerStatus(play_status="NONE")
        assert status3.play_state == "idle"

        # Test other states
        status4 = PlayerStatus(play_status="pause")
        assert status4.play_state == "pause"

        status5 = PlayerStatus(play_status="stop")
        assert status5.play_state == "pause"  # Modern UX: stop normalizes to pause

    def test_player_status_duration_normalization(self):
        """Test PlayerStatus duration normalization (0 -> None)."""
        # Duration of 0 should become None (streaming services)
        status1 = PlayerStatus(duration=0)
        assert status1.duration is None

        # Non-zero duration should remain
        status2 = PlayerStatus(duration=240)
        assert status2.duration == 240

        # None should remain None
        status3 = PlayerStatus(duration=None)
        assert status3.duration is None

    def test_player_status_eq_preset_normalization(self):
        """Test PlayerStatus eq_preset normalization."""
        # String preset should remain
        status1 = PlayerStatus(eq="rock")
        assert status1.eq_preset == "rock"

        # Dict should become None
        status2 = PlayerStatus(eq={"eq_enabled": False})
        assert status2.eq_preset is None

        # None should remain None
        status3 = PlayerStatus(eq=None)
        assert status3.eq_preset is None

    def test_player_status_extra_fields(self):
        """Test PlayerStatus allows extra fields."""
        status = PlayerStatus(
            play_state="play",
            unknown_field="value",
        )
        assert hasattr(status, "unknown_field")
        assert status.unknown_field == "value"


class TestWiiMDiscoveryModels:
    """Test read-only WiiM discovery models."""

    def test_audio_input_enable_model(self):
        """Audio input enable payload preserves modes and normalizes flags."""
        payload = AudioInputEnable.model_validate(
            {
                "ver": "1.0",
                "audioInput": [
                    {"mode": "wifi", "enable": 1},
                    {"mode": "phono", "enable": "0"},
                ],
            }
        )

        assert payload.version == "1.0"
        assert payload.audio_input[0].mode == "wifi"
        assert payload.audio_input[0].enable is True
        assert payload.audio_input[1].enable is False

    def test_acoustic_capability_model(self):
        """Acoustic capability keeps feature blocks available for inspection."""
        payload = AcousticCapability.model_validate(
            {
                "Version": "1.0",
                "GEQ": {"Version": "1.0"},
                "PEQ": {"Filters": ["OFF", "PK"]},
                "OutputDelay": {"MinDelayUs": -1000000, "StepDelayUs": 100},
            }
        )

        assert payload.version == "1.0"
        assert payload.geq == {"Version": "1.0"}
        assert payload.peq == {"Filters": ["OFF", "PK"]}
        assert payload.output_delay["MinDelayUs"] == -1000000

    def test_routine_list_model(self):
        """Routine list maps date aliases and step payloads."""
        payload = RoutineList.model_validate(
            {
                "routines": [
                    {
                        "id": "routine-id",
                        "name": "PC",
                        "index": 3,
                        "createDate": "2026-06-23T06:08:26Z",
                        "updateDate": "2026-06-23T06:08:56Z",
                        "steps": [{"type": "audioInput", "payload": {"input": "optical"}}],
                    }
                ]
            }
        )

        routine = payload.routines[0]
        assert routine.id == "routine-id"
        assert routine.create_date == "2026-06-23T06:08:26Z"
        assert routine.update_date == "2026-06-23T06:08:56Z"
        assert routine.steps[0].type == "audioInput"
        assert routine.steps[0].payload == {"input": "optical"}

    def test_sound_card_mode_support_model(self):
        """Sound-card support uses mode as stable identity and keeps card details."""
        payload = SoundCardModeSupport.model_validate(
            {
                "index": 5,
                "mode": "AUDIO_OUTPUT_UAC_CARD_MODE",
                "soundCard": {
                    "cardName": "SABRE-D70 Pro SABRE",
                    "devName": "Topping D70 Pro SABRE",
                    "cardId": "hw:1,0",
                    "supportVrmsChange": "1",
                    "sampleRateSupportList": [44100, 48000, 192000],
                },
            }
        )

        assert payload.index == 5
        assert payload.mode == "AUDIO_OUTPUT_UAC_CARD_MODE"
        assert payload.sound_card is not None
        assert payload.sound_card.card_name == "SABRE-D70 Pro SABRE"
        assert payload.sound_card.dev_name == "Topping D70 Pro SABRE"
        assert payload.sound_card.support_vrms_change is True


class TestSlaveInfo:
    """Test SlaveInfo model."""

    def test_slave_info_required_fields(self):
        """Test SlaveInfo with required fields."""
        slave = SlaveInfo(ip="192.168.1.100", name="Test Slave")
        assert slave.ip == "192.168.1.100"
        assert slave.name == "Test Slave"
        assert slave.uuid is None

    def test_slave_info_with_uuid(self):
        """Test SlaveInfo with optional UUID."""
        slave = SlaveInfo(
            uuid="slave-uuid",
            ip="192.168.1.101",
            name="Test Slave 2",
        )
        assert slave.uuid == "slave-uuid"
        assert slave.ip == "192.168.1.101"
        assert slave.name == "Test Slave 2"


class TestMultiroomInfo:
    """Test MultiroomInfo model."""

    def test_multiroom_info_master(self):
        """Test MultiroomInfo with master role."""
        multiroom = MultiroomInfo(
            role="master",
            slave_list=[
                SlaveInfo(ip="192.168.1.100", name="Slave 1"),
                SlaveInfo(ip="192.168.1.101", name="Slave 2"),
            ],
        )
        assert multiroom.role == "master"
        assert len(multiroom.slave_list) == 2
        assert multiroom.slave_list[0].name == "Slave 1"

    def test_multiroom_info_slave(self):
        """Test MultiroomInfo with slave role."""
        multiroom = MultiroomInfo(role="slave", slave_list=[])
        assert multiroom.role == "slave"
        assert len(multiroom.slave_list) == 0

    def test_multiroom_info_solo(self):
        """Test MultiroomInfo with solo role."""
        multiroom = MultiroomInfo(role="solo")
        assert multiroom.role == "solo"


class TestTrackMetadata:
    """Test TrackMetadata model."""

    def test_track_metadata_minimal(self):
        """Test TrackMetadata with minimal fields."""
        metadata = TrackMetadata(title="Test Song")
        assert metadata.title == "Test Song"
        assert metadata.artist is None
        assert metadata.album is None

    def test_track_metadata_complete(self):
        """Test TrackMetadata with all fields."""
        metadata = TrackMetadata(
            title="Test Song",
            artist="Test Artist",
            album="Test Album",
            entity_picture="http://example.com/artwork.jpg",
            cover_url="http://example.com/cover.jpg",
            sample_rate=44100,
            bit_depth=16,
            bit_rate=320,
        )
        assert metadata.title == "Test Song"
        assert metadata.artist == "Test Artist"
        assert metadata.album == "Test Album"
        assert metadata.entity_picture == "http://example.com/artwork.jpg"
        assert metadata.cover_url == "http://example.com/cover.jpg"
        assert metadata.sample_rate == 44100
        assert metadata.bit_depth == 16
        assert metadata.bit_rate == 320

    def test_track_metadata_extra_fields(self):
        """Test TrackMetadata allows extra fields."""
        metadata = TrackMetadata(
            title="Test",
            unknown_field="value",
        )
        assert hasattr(metadata, "unknown_field")


class TestEQInfo:
    """Test EQInfo model."""

    def test_eq_info_minimal(self):
        """Test EQInfo with minimal fields."""
        eq = EQInfo()
        assert eq.eq_enabled is None
        assert eq.eq_preset is None

    def test_eq_info_complete(self):
        """Test EQInfo with all fields."""
        eq = EQInfo(eq_enabled=True, eq_preset="rock")
        assert eq.eq_enabled is True
        assert eq.eq_preset == "rock"


class TestPollingMetrics:
    """Test PollingMetrics model."""

    def test_polling_metrics_required_fields(self):
        """Test PollingMetrics with required fields."""
        metrics = PollingMetrics(
            interval=5.0,
            is_playing=True,
            api_capabilities={"supports_eq": True, "supports_presets": False},
        )
        assert metrics.interval == 5.0
        assert metrics.is_playing is True
        assert metrics.api_capabilities == {"supports_eq": True, "supports_presets": False}


class TestGroupDeviceState:
    """Test GroupDeviceState model."""

    def test_group_device_state_master(self):
        """Test GroupDeviceState with master role."""
        state = GroupDeviceState(
            host="192.168.1.100",
            role="master",
            volume=0.5,
            mute=False,
            play_state="play",
        )
        assert state.host == "192.168.1.100"
        assert state.role == "master"
        assert state.volume == 0.5
        assert state.mute is False
        assert state.play_state == "play"

    def test_group_device_state_slave(self):
        """Test GroupDeviceState with slave role."""
        state = GroupDeviceState(
            host="192.168.1.101",
            role="slave",
            volume=0.3,
            mute=True,
            play_state="pause",
        )
        assert state.host == "192.168.1.101"
        assert state.role == "slave"
        assert state.volume == 0.3
        assert state.mute is True
        assert state.play_state == "pause"


class TestGroupState:
    """Test GroupState model."""

    def test_group_state_minimal(self):
        """Test GroupState with minimal fields."""
        master_state = GroupDeviceState(host="192.168.1.100", role="master")
        group = GroupState(
            master_host="192.168.1.100",
            master_state=master_state,
        )
        assert group.master_host == "192.168.1.100"
        assert group.master_state.host == "192.168.1.100"
        assert len(group.slave_hosts) == 0
        assert len(group.slave_states) == 0

    def test_group_state_with_slaves(self):
        """Test GroupState with slaves."""
        master_state = GroupDeviceState(host="192.168.1.100", role="master")
        slave1_state = GroupDeviceState(host="192.168.1.101", role="slave")
        slave2_state = GroupDeviceState(host="192.168.1.102", role="slave")

        group = GroupState(
            master_host="192.168.1.100",
            slave_hosts=["192.168.1.101", "192.168.1.102"],
            master_state=master_state,
            slave_states=[slave1_state, slave2_state],
            play_state="play",
            volume_level=0.5,
            is_muted=False,
        )
        assert group.master_host == "192.168.1.100"
        assert len(group.slave_hosts) == 2
        assert len(group.slave_states) == 2
        assert group.play_state == "play"
        assert group.volume_level == 0.5
        assert group.is_muted is False


class TestDeviceGroupInfo:
    """Test DeviceGroupInfo model."""

    def test_device_group_info_solo(self):
        """Test DeviceGroupInfo with solo role."""
        info = DeviceGroupInfo(role="solo")
        assert info.role == "solo"
        assert info.master_host is None
        assert info.master_uuid is None
        assert len(info.slave_hosts) == 0
        assert info.slave_count == 0

    def test_device_group_info_master(self):
        """Test DeviceGroupInfo with master role."""
        info = DeviceGroupInfo(
            role="master",
            master_host="192.168.1.100",
            master_uuid="master-uuid",
            slave_hosts=["192.168.1.101", "192.168.1.102"],
            slave_count=2,
        )
        assert info.role == "master"
        assert info.master_host == "192.168.1.100"
        assert info.master_uuid == "master-uuid"
        assert len(info.slave_hosts) == 2
        assert info.slave_count == 2

    def test_device_group_info_slave(self):
        """Test DeviceGroupInfo with slave role."""
        info = DeviceGroupInfo(
            role="slave",
            master_host="192.168.1.100",
            master_uuid="master-uuid",
        )
        assert info.role == "slave"
        assert info.master_host == "192.168.1.100"
        assert info.master_uuid == "master-uuid"
        assert len(info.slave_hosts) == 0
        assert info.slave_count == 0
