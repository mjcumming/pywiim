"""WiiM Voice Remote (Bluetooth LE) API.

Read-only status plus the remote's volume step setting. Verified on a WiiM Pro Plus
(firmware Linkplay.4.8.833841); other models and firmware are not tested.

Sources (see ADR 025):
- ``getStatusEx`` ``BleRemoteControl`` is ``"1"`` whenever the speaker supports a remote, paired or
  not. That flag is read from the device info already fetched at connect. The regular poll does
  not call ``getStatusEx`` again for the remote (ADR 024).
- ``getblehidstatus`` is the remote read: connected, battery, RSSI, name, MAC, and firmware.
  Battery can lag after a battery change. While the remote is not connected, battery and RSSI
  are reported as None.
- ``get_remote_volume_step`` / ``set_remote_volume_step:N`` (N = 1-5) read and write the setting.

This module never builds the commands that pair, remove or update the remote. The BLE MAC is
kept out of ``repr`` and masked in diagnostics.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from ..exceptions import WiiMError
from .constants import (
    API_ENDPOINT_BLE_REMOTE_STATUS,
    API_ENDPOINT_REMOTE_VOLUME_STEP_GET,
    API_ENDPOINT_REMOTE_VOLUME_STEP_SET,
)

_LOGGER = logging.getLogger(__name__)

REMOTE_VOLUME_STEP_MIN = 1
REMOTE_VOLUME_STEP_MAX = 5
REMOTE_VOLUME_STEP_DEFAULT = 1

# Labels as shown in the WiiM Home app (English). Integrations may translate them.
REMOTE_VOLUME_STEPS: Mapping[int, str] = MappingProxyType(
    {
        1: "Fine Adjustment",
        2: "Small Step",
        3: "Medium Step",
        4: "Large Step",
        5: "Quick Adjustment",
    }
)

_UNPAIRED_MAC = "00:00:00:00:00:00"


def mask_mac(mac: str | None) -> str | None:
    """Return *mac* with every octet masked, or None when there is no MAC."""
    if not mac:
        return None
    return ":".join("XX" for _ in mac.split(":"))


@dataclass(frozen=True)
class BleRemoteIdentity:
    """What ``getblehidstatus`` says about the remote (slow-changing).

    Attributes:
        status: Raw status string (``connected``, ``notconnect``, ``scanning``; others pass through).
        paired: True when a remote is stored (non-empty name and a non-zero MAC).
        name: Remote name, or None when not paired.
        mac: Remote BLE MAC, or None when not paired. Hidden from ``repr``.
        firmware: Remote firmware string such as ``"0054"``, or None.
        battery: Battery percent from this response. It can lag after a battery change.
        rssi: Signal strength in dBm from this response, including a stale value while disconnected.
    """

    status: str
    paired: bool
    name: str | None
    mac: str | None = field(repr=False)
    firmware: str | None
    battery: int | None
    rssi: int | None


@dataclass(frozen=True)
class BleRemoteState:
    """Typed state of the WiiM Voice Remote.

    Attributes:
        paired: True/False from ``getblehidstatus``; None until that has been read.
        connected: Whether the remote is currently connected.
        name: Remote name, None when not paired or not read yet.
        mac: Remote BLE MAC, None when not paired or not read yet. Hidden from ``repr``;
            masked by :meth:`diagnostics_dict`.
        firmware: Remote firmware string (for example ``"0054"``), None when unknown.
        battery: Battery level in percent from ``getblehidstatus``; None while not connected.
            The value can lag after a battery change.
        rssi: Signal strength in dBm from ``getblehidstatus``; None while not connected.
    """

    paired: bool | None
    connected: bool
    name: str | None
    mac: str | None = field(repr=False)
    firmware: str | None
    battery: int | None
    rssi: int | None

    def diagnostics_dict(self) -> dict[str, Any]:
        """Dictionary safe for diagnostics: the BLE MAC is masked."""
        return {
            "paired": self.paired,
            "connected": self.connected,
            "name": self.name,
            "mac": mask_mac(self.mac),
            "firmware": self.firmware,
            "battery": self.battery,
            "rssi": self.rssi,
        }


def parse_ble_remote_identity(parsed: Any) -> BleRemoteIdentity | None:
    """Parse a ``getblehidstatus`` body; None when it is not a valid status object.

    The real response includes ``"error":0``, so only a non-zero ``error`` marks an error wrapper.
    """
    if not isinstance(parsed, dict):
        return None
    status = parsed.get("status")
    if not isinstance(status, str) or "name" not in parsed or "mac" not in parsed:
        return None
    error = parsed.get("error", 0)
    if error not in (0, "0", None):
        return None
    name = parsed.get("name")
    mac = parsed.get("mac")
    name = name.strip() if isinstance(name, str) else ""
    mac = mac.strip() if isinstance(mac, str) else ""
    paired = bool(name) and bool(mac) and mac != _UNPAIRED_MAC
    firmware = parsed.get("ver")
    firmware = firmware.strip() if isinstance(firmware, str) else ""
    return BleRemoteIdentity(
        status=status,
        paired=paired,
        name=name or None if paired else None,
        mac=mac if paired else None,
        firmware=firmware or None if paired else None,
        battery=_int_or_none(parsed.get("battery"), 0, 100),
        rssi=_int_or_none(parsed.get("rssi")),
    )


def _int_or_none(value: Any, low: int | None = None, high: int | None = None) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = int(str(value).strip())
    except ValueError:
        return None
    if (low is not None and number < low) or (high is not None and number > high):
        return None
    return number


def build_ble_remote_state(identity: BleRemoteIdentity | None) -> BleRemoteState | None:
    """Build remote state from one ``getblehidstatus`` read.

    Battery and RSSI are None unless ``status`` is ``connected``. The battery value can lag after
    a battery change. Returns None when the identity has not been read.
    """
    if identity is None:
        return None
    connected = identity.status == "connected"
    return BleRemoteState(
        paired=identity.paired,
        connected=connected,
        name=identity.name,
        mac=identity.mac,
        firmware=identity.firmware,
        battery=identity.battery if connected else None,
        rssi=identity.rssi if connected else None,
    )


class BleRemoteAPI:
    """WiiM Voice Remote mixin for the client. Read-only except the volume step."""

    async def get_ble_remote_identity(self) -> BleRemoteIdentity | None:
        """Read ``getblehidstatus``.

        Returns:
            The parsed identity, or None when the command is unsupported, the body is not a valid
            status object, or the request failed.
        """
        try:
            response = await self._request(API_ENDPOINT_BLE_REMOTE_STATUS)  # type: ignore[attr-defined]
        except WiiMError as err:
            _LOGGER.debug("getblehidstatus failed: %s", err)
            return None
        return parse_ble_remote_identity(response.parsed)

    async def get_remote_volume_step(self) -> int | None:
        """Read the remote's volume step (1-5), or None when unreadable."""
        try:
            response = await self._request(API_ENDPOINT_REMOTE_VOLUME_STEP_GET)  # type: ignore[attr-defined]
        except WiiMError as err:
            _LOGGER.debug("get_remote_volume_step failed: %s", err)
            return None
        if not isinstance(response.parsed, dict):
            return None
        return _int_or_none(response.parsed.get("remote_volume_step"), REMOTE_VOLUME_STEP_MIN, REMOTE_VOLUME_STEP_MAX)

    async def set_remote_volume_step(self, step: int) -> int:
        """Set the remote's volume step and verify it by reading it back.

        Args:
            step: 1 (Fine Adjustment) to 5 (Quick Adjustment); see ``REMOTE_VOLUME_STEPS``.

        Returns:
            The value the device reports after the write (equal to ``step``).

        Raises:
            ValueError: If ``step`` is not an int from 1 to 5 (nothing is sent).
            WiiMError: If the device rejects the write, or the read-back is missing or differs.
        """
        if (
            isinstance(step, bool)
            or not isinstance(step, int)
            or not (REMOTE_VOLUME_STEP_MIN <= step <= REMOTE_VOLUME_STEP_MAX)
        ):
            raise ValueError(
                f"Remote volume step must be an integer between {REMOTE_VOLUME_STEP_MIN} "
                f"and {REMOTE_VOLUME_STEP_MAX}, got {step!r}"
            )
        response = await self._request(f"{API_ENDPOINT_REMOTE_VOLUME_STEP_SET}{step}")  # type: ignore[attr-defined]
        parsed = response.parsed
        if isinstance(parsed, dict) and str(parsed.get("status", "OK")).strip().upper() != "OK":
            raise WiiMError(f"Device rejected remote volume step {step}: {parsed.get('status')!r}")
        actual = await self.get_remote_volume_step()
        if actual is None:
            raise WiiMError(f"Remote volume step {step} was sent but could not be read back")
        if actual != step:
            raise WiiMError(f"Remote volume step set to {step} but the device reports {actual}")
        return actual
