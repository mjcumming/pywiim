"""WiiM Voice Remote responses captured from a WiiM Pro Plus (firmware Linkplay.4.8.833841).

Values are the real responses; the BLE MAC is replaced by a locally administered fake.
"""

from __future__ import annotations

import json
from typing import Any

FAKE_REMOTE_MAC = "02:00:00:00:00:01"

# getStatusEx keys while the remote is connected.
STATUS_EX_REMOTE_CONNECTED: dict[str, str] = {
    "BleRemoteControl": "1",
    "BleRemoteConnected": "1",
    "BleRemoteException": "0",
    "BleRemoteVersion": "0054",
    "BleRemoteBatterylevel": "100",
    "BleRemoteRSSI": "-61",
    "BleRemote_dev_state": "normal",
    "BleRemote_power_status": "0",
    "BleRemote_has_new": "0",
    "BleRemoteNewVersion": "",
    "BleRemote_update_checked_counter": "11",
}

# getStatusEx keys while the remote is not connected (batteries out or not paired).
STATUS_EX_REMOTE_NOT_CONNECTED: dict[str, str] = {
    "BleRemoteControl": "1",
    "BleRemoteConnected": "0",
}

# Unrelated getStatusEx keys, so tests can build a DeviceInfo.
STATUS_EX_BASE: dict[str, Any] = {
    "uuid": "TEST-UUID-0001",
    "DeviceName": "Test Pro Plus",
    "project": "WiiM_Pro_with_gc4a",
    "firmware": "Linkplay.4.8.833841",
}

# getblehidstatus bodies as sent by the device (note the space before "doubleclickdisable").
HID_CONNECTED_RAW = (
    '{"status":"connected","error":0,"name":"WiiM Voice Remote","mac":"' + FAKE_REMOTE_MAC + '",'
    '"battery":100,"ver":"0054","rssi":-61,"powerstatus":0, "doubleclickdisable":0}'
)
# After a battery change `battery` still lagged (0) while getStatusEx already said 100.
HID_CONNECTED_LAGGING_BATTERY_RAW = HID_CONNECTED_RAW.replace('"battery":100', '"battery":0')
HID_NOT_CONNECTED_RAW = (
    '{"status":"notconnect","error":0,"name":"WiiM Voice Remote","mac":"' + FAKE_REMOTE_MAC + '",'
    '"battery":0,"ver":"0054","rssi":-61,"powerstatus":0, "doubleclickdisable":0}'
)
HID_SCANNING_RAW = (
    '{"status":"scanning","error":0,"name":"","mac":"00:00:00:00:00:00",'
    '"battery":0,"ver":"","rssi":0,"powerstatus":0, "doubleclickdisable":0}'
)

HID_CONNECTED = json.loads(HID_CONNECTED_RAW)
HID_CONNECTED_LAGGING_BATTERY = json.loads(HID_CONNECTED_LAGGING_BATTERY_RAW)
HID_NOT_CONNECTED = json.loads(HID_NOT_CONNECTED_RAW)
HID_SCANNING = json.loads(HID_SCANNING_RAW)

VOLUME_STEP_GET_RESPONSE = {"status": "OK", "remote_volume_step": 1}
VOLUME_STEP_SET_RESPONSE = {"status": "OK"}

# Commands that pair, remove, or update the remote. Nothing may send them.
FORBIDDEN_REMOTE_COMMANDS = (
    "blehidremoveall",
    "startblescan",
    "blehidpair",
    "getMvRemoteUpdateStart",
    "getMvRemoteUpdateStartCheck",
)
