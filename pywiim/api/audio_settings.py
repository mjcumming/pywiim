"""Audio settings helpers for WiiM HTTP client.

This mixin handles audio-related configuration including SPDIF settings,
channel balance, and other audio parameters. These endpoints are unofficial
and may not be available on all firmware versions.

It assumes the base client provides the `_request` coroutine. No state is stored –
all results come from the device each call.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ..exceptions import WiiMError, WiiMResponseError
from ..models import SoundCardModeSupport, parse_output_channel
from .constants import (
    API_ENDPOINT_GET_CHANNEL_BALANCE,
    API_ENDPOINT_GET_SOUND_CARD_MODE_SUPPORT_LIST,
    API_ENDPOINT_GET_SPDIF_SAMPLE_RATE,
    API_ENDPOINT_SET_CHANNEL_BALANCE,
    API_ENDPOINT_SET_OUTPUT_CHANNEL,
    API_ENDPOINT_SET_SPDIF_SWITCH_DELAY,
    OUTPUT_CHANNEL_MAP,
)


def output_channel_value(channel: str) -> int:
    """Return the wire value (0, 1, 2) for ``stereo`` / ``left`` / ``right``.

    Matching ignores case and surrounding spaces.

    Raises:
        ValueError: If ``channel`` is not one of the three names.
    """
    wanted = channel.strip().lower() if isinstance(channel, str) else ""
    for value, name in OUTPUT_CHANNEL_MAP.items():
        if name == wanted:
            return value
    raise ValueError(f"Output channel must be one of {list(OUTPUT_CHANNEL_MAP.values())}, got {channel!r}")


class AudioSettingsAPI:
    """Audio settings helpers (SPDIF, balance, etc.).

    This mixin provides methods for configuring advanced audio settings
    including SPDIF sample rates and channel balance.
    """

    # ------------------------------------------------------------------
    # Audio output support discovery
    # ------------------------------------------------------------------

    async def get_sound_card_mode_support_list(self) -> list[SoundCardModeSupport]:
        """Return WiiM sound-card/output mode support entries.

        This read-only endpoint can enumerate real output hardware (including
        attached USB DACs). It is expected to be WiiM/firmware-specific; devices
        that do not support it return an empty list.
        """
        try:
            response = await self._request(API_ENDPOINT_GET_SOUND_CARD_MODE_SUPPORT_LIST)  # type: ignore[attr-defined]
            if isinstance(response.parsed, list):
                supported: list[SoundCardModeSupport] = []
                for item in response.parsed:
                    if not isinstance(item, dict) or not item.get("mode"):
                        continue
                    try:
                        supported.append(SoundCardModeSupport.model_validate(item))
                    except ValidationError:
                        continue
                return supported
        except WiiMError:
            return []
        return []

    # ------------------------------------------------------------------
    # SPDIF sample rate configuration
    # ------------------------------------------------------------------

    async def get_spdif_sample_rate(self) -> str:
        """Get current SPDIF output sample rate.

        Returns:
            Sample rate in Hz as string (e.g., "48000", "96000", "192000")
            Empty string if SPDIF output is not active or endpoint not supported
        """
        try:
            response = await self._request(API_ENDPOINT_GET_SPDIF_SAMPLE_RATE)  # type: ignore[attr-defined]
            if response.parsed is not None:
                return str(response.parsed)
            return response.raw or ""
        except WiiMError:
            return ""

    async def set_spdif_switch_delay(self, delay_ms: int) -> None:
        """Set SPDIF sample rate switch latency.

        Args:
            delay_ms: Delay in milliseconds (0-3000ms)

        Raises:
            ValueError: If delay is outside valid range
            WiiMRequestError: If the request fails
        """
        if not 0 <= delay_ms <= 3000:
            raise ValueError("SPDIF switch delay must be between 0 and 3000 milliseconds")

        await self._request(f"{API_ENDPOINT_SET_SPDIF_SWITCH_DELAY}{delay_ms}")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Channel balance control
    # ------------------------------------------------------------------

    async def get_channel_balance(self) -> float:
        """Get current left/right channel balance.

        Returns:
            Balance value from -1.0 (fully left) to 1.0 (fully right)
            Returns 0.0 if unable to retrieve
        """
        try:
            response = await self._request(API_ENDPOINT_GET_CHANNEL_BALANCE)  # type: ignore[attr-defined]
            val = response.parsed if response.parsed is not None else response.raw
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                return float(val)
            return 0.0
        except WiiMError:
            return 0.0

    async def set_channel_balance(self, balance: float) -> None:
        """Set left/right channel balance.

        Args:
            balance: Balance value from -1.0 (left) to 1.0 (right)
                    0.0 = center, -1.0 = full left, 1.0 = full right

        Raises:
            ValueError: If balance is outside valid range
            WiiMRequestError: If the request fails
        """
        if not -1.0 <= balance <= 1.0:
            raise ValueError("Channel balance must be between -1.0 and 1.0")

        # Format as string, removing unnecessary decimal places
        balance_str = f"{balance:g}"
        await self._request(f"{API_ENDPOINT_SET_CHANNEL_BALANCE}{balance_str}")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Output channel (stereo / left / right)
    # ------------------------------------------------------------------

    async def get_output_channel(self) -> str | None:
        """Read the output channel from the ``ch`` field of the player status.

        There is no dedicated getter command; ``ch`` comes with every
        ``getPlayerStatus`` / ``getPlayerStatusEx`` response.

        Returns:
            ``"stereo"``, ``"left"`` or ``"right"``, or None if the status has no usable ``ch``.

        Raises:
            WiiMRequestError: If the status request fails.
        """
        status = await self.get_player_status()  # type: ignore[attr-defined]
        return parse_output_channel(status.get("ch"))

    async def set_output_channel(self, channel: str) -> None:
        """Set the output channel with ``setPlayerCmd:slave_channel:N``.

        Works on a standalone player and on a group member addressed directly.
        A group master can also set a member's channel with ``set_slave_channel()``.

        Args:
            channel: ``"stereo"`` (0), ``"left"`` (1) or ``"right"`` (2), any case.

        Raises:
            ValueError: If ``channel`` is not one of the three names.
            WiiMRequestError: If the request fails.
            WiiMResponseError: If the device does not acknowledge the command.
        """
        value = output_channel_value(channel)
        endpoint = f"{API_ENDPOINT_SET_OUTPUT_CHANNEL}{value}"
        response = await self._request(endpoint)  # type: ignore[attr-defined]
        if (response.raw or "").strip().upper() != "OK" and response.parsed != "OK":
            raise WiiMResponseError(
                f"Failed to set output channel: {response.raw or response.parsed!r}", endpoint=endpoint
            )

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    async def center_channel_balance(self) -> None:
        """Center the channel balance (set to 0.0).

        Raises:
            WiiMRequestError: If the request fails
        """
        await self.set_channel_balance(0.0)

    async def get_spdif_sample_rate_int(self) -> int:
        """Get SPDIF sample rate as integer.

        Returns:
            Sample rate in Hz as integer, or 0 if unable to retrieve
        """
        try:
            rate_str = await self.get_spdif_sample_rate()
            return int(rate_str) if rate_str.isdigit() else 0
        except (ValueError, AttributeError):
            return 0

    async def is_spdif_output_active(self) -> bool:
        """Check if SPDIF output appears to be active.

        Returns:
            True if SPDIF sample rate is available and > 0
        """
        rate = await self.get_spdif_sample_rate_int()
        return rate > 0

    async def get_audio_settings_status(self) -> dict[str, Any]:
        """Get comprehensive audio settings status.

        Returns:
            Dict containing current audio settings:
            - spdif_sample_rate: Current SPDIF sample rate
            - channel_balance: Current balance setting
            - spdif_active: Whether SPDIF output appears active
        """
        try:
            return {
                "spdif_sample_rate": await self.get_spdif_sample_rate(),
                "channel_balance": await self.get_channel_balance(),
                "spdif_active": await self.is_spdif_output_active(),
            }
        except WiiMError:
            return {
                "spdif_sample_rate": "",
                "channel_balance": 0.0,
                "spdif_active": False,
            }
