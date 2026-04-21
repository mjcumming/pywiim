"""Subwoofer control API for WiiM devices.

This mixin handles subwoofer configuration including crossover frequency,
phase, level, and delay settings. These endpoints are undocumented and
were discovered through reverse engineering.

Confirmed working on:
- WiiM Ultra (firmware 5.2.804553) - Original discovery
- WiiM Pro (firmware 4.8+) - Tested working
- NOT supported on Arylic devices (returns "unknown command")

It assumes the base client provides the `_request` coroutine. No state is stored –
all results come from the device each call.

API Reference (from GitHub Issue #2):
- getSubLPF: Get subwoofer status
- setSubLPF:status:value - Enable/disable (1 or 0)
- setSubLPF:cross:value - Crossover frequency (30 to 250 Hz)
- setSubLPF:phase:value - Phase (0 or 180 degrees)
- setSubLPF:level:value - Level (-15 to 15 dB)
- setSubLPF:main_filter:value - Main speakers output bass (1=disabled, 0=enabled)
- setSubLPF:sub_filter:value - Subwoofer bypass mode (1=disabled, 0=enabled)
- setSubLPF:sub_delay:value - Manual delay adjustment (-200 to 200 ms)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..exceptions import WiiMError
from .constants import (
    API_ENDPOINT_SUBWOOFER_SET,
    API_ENDPOINT_SUBWOOFER_STATUS,
    SUBWOOFER_CROSSOVER_MAX,
    SUBWOOFER_CROSSOVER_MIN,
    SUBWOOFER_DELAY_MAX,
    SUBWOOFER_DELAY_MIN,
    SUBWOOFER_LEVEL_MAX,
    SUBWOOFER_LEVEL_MIN,
    SUBWOOFER_PHASE_0,
    SUBWOOFER_PHASE_180,
)

_SUBWOOFER_LPF_KNOWN_KEYS = frozenset(
    {"cross", "plugged", "sub_delay", "main_filter", "sub_filter", "mix_sub", "output_mode"}
)


def is_valid_subwoofer_lpf_dict(parsed: Any) -> bool:
    """True when *parsed* is a real getSubLPF status object (not an API error wrapper).

    Some vendors return HTTP 200 with JSON like ``{\"error\": \"unsupported_command\"}``;
    those must not be treated as subwoofer support or coerced into :class:`SubwooferStatus`.
    """
    if not isinstance(parsed, dict):
        return False
    if "error" in parsed:
        return False
    keys = parsed.keys()
    if keys & _SUBWOOFER_LPF_KNOWN_KEYS:
        return True
    st = parsed.get("status")
    return isinstance(st, int) and ("level" in parsed or "phase" in parsed)


@dataclass
class SubwooferStatus:
    """Subwoofer status information.

    Attributes:
        enabled: Whether subwoofer output is enabled.
        plugged: Whether a subwoofer is physically connected.
        crossover: Crossover frequency in Hz (30-250).
        phase: Phase setting (0 or 180 degrees).
        level: Level adjustment in dB (-15 to 15).
        main_filter_enabled: Whether bass is sent to main speakers (False = bass to mains).
        sub_filter_enabled: Whether subwoofer filtering is active (False = bypass mode).
        sub_delay: Subwoofer delay adjustment in ms (-200 to 200).
        output_mode: Output mode setting.
        mix_sub: Mix subwoofer setting.
        linein_delay: Line-in delay setting.
        delay_main_sub: Delay between main and sub.
    """

    enabled: bool
    plugged: bool
    crossover: int
    phase: int
    level: int
    main_filter_enabled: bool
    sub_filter_enabled: bool
    sub_delay: int
    output_mode: int = 0
    mix_sub: int = 0
    linein_delay: float = 0.0
    delay_main_sub: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SubwooferStatus:
        """Create SubwooferStatus from API response dictionary.

        Args:
            data: Dictionary from getSubLPF API response.

        Returns:
            SubwooferStatus instance.
        """
        return cls(
            enabled=data.get("status", 0) == 1,
            plugged=data.get("plugged", 0) == 1,
            crossover=int(data.get("cross", 80)),
            phase=int(data.get("phase", 0)),
            level=int(data.get("level", 0)),
            # Note: API uses inverted logic (1=disabled, 0=enabled)
            main_filter_enabled=data.get("main_filter", 1) == 0,
            sub_filter_enabled=data.get("sub_filter", 1) == 0,
            sub_delay=int(data.get("sub_delay", 0)),
            output_mode=int(data.get("output_mode", 0)),
            mix_sub=int(data.get("mix_sub", 0)),
            linein_delay=float(data.get("linein_delay", 0.0)),
            delay_main_sub=str(data.get("delay_main_sub", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Returns:
            Dictionary representation of subwoofer status.
        """
        return {
            "enabled": self.enabled,
            "plugged": self.plugged,
            "crossover": self.crossover,
            "phase": self.phase,
            "level": self.level,
            "main_filter_enabled": self.main_filter_enabled,
            "sub_filter_enabled": self.sub_filter_enabled,
            "sub_delay": self.sub_delay,
            "output_mode": self.output_mode,
            "mix_sub": self.mix_sub,
            "linein_delay": self.linein_delay,
            "delay_main_sub": self.delay_main_sub,
        }


class SubwooferAPI:
    """Subwoofer control API mixin for WiiM devices.

    This mixin provides methods for configuring subwoofer settings including
    crossover frequency, phase, level, and delay. These are undocumented
    endpoints discovered through reverse engineering.

    Confirmed working on: WiiM Ultra (firmware 5.2.804553)
    """

    # ------------------------------------------------------------------
    # Status retrieval
    # ------------------------------------------------------------------

    async def get_subwoofer_status(self) -> SubwooferStatus | None:
        """Get current subwoofer configuration.

        Returns:
            SubwooferStatus object with current settings, or None if not supported.

        Example response from device:
            {
                "status": 1,
                "delay_main_sub": "1.0",
                "plugged": 1,
                "output_mode": 1,
                "cross": 85,
                "phase": 0,
                "level": 0,
                "mix_sub": 1,
                "main_filter": 1,
                "sub_filter": 1,
                "sub_delay": -5,
                "linein_delay": 0.00
            }
        """
        try:
            response = await self._request(API_ENDPOINT_SUBWOOFER_STATUS)  # type: ignore[attr-defined]
            if isinstance(response.parsed, dict) and is_valid_subwoofer_lpf_dict(response.parsed):
                return SubwooferStatus.from_dict(response.parsed)
            return None
        except WiiMError:
            return None

    async def get_subwoofer_status_raw(self) -> dict[str, Any] | None:
        """Get raw subwoofer status response from device.

        Returns:
            Raw dictionary from API, or None if not supported.
        """
        try:
            response = await self._request(API_ENDPOINT_SUBWOOFER_STATUS)  # type: ignore[attr-defined]
            if isinstance(response.parsed, dict) and is_valid_subwoofer_lpf_dict(response.parsed):
                return response.parsed
            return None
        except WiiMError:
            return None

    # ------------------------------------------------------------------
    # Enable/disable
    # ------------------------------------------------------------------

    async def set_subwoofer_enabled(self, enabled: bool) -> None:
        """Enable or disable subwoofer output.

        Args:
            enabled: True to enable subwoofer, False to disable.

        Raises:
            WiiMError: If the request fails.
        """
        value = 1 if enabled else 0
        await self._request(f"{API_ENDPOINT_SUBWOOFER_SET}status:{value}")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Crossover frequency
    # ------------------------------------------------------------------

    async def set_subwoofer_crossover(self, frequency: int) -> None:
        """Set subwoofer crossover frequency.

        The crossover frequency determines the cutoff point where audio
        is split between the main speakers and subwoofer.

        Args:
            frequency: Crossover frequency in Hz (30-250).

        Raises:
            ValueError: If frequency is outside valid range.
            WiiMError: If the request fails.
        """
        if not SUBWOOFER_CROSSOVER_MIN <= frequency <= SUBWOOFER_CROSSOVER_MAX:
            raise ValueError(
                f"Crossover frequency must be between {SUBWOOFER_CROSSOVER_MIN} "
                f"and {SUBWOOFER_CROSSOVER_MAX} Hz, got {frequency}"
            )
        await self._request(f"{API_ENDPOINT_SUBWOOFER_SET}cross:{frequency}")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Phase
    # ------------------------------------------------------------------

    async def set_subwoofer_phase(self, phase: int) -> None:
        """Set subwoofer phase.

        Phase adjustment can help align the subwoofer output with the
        main speakers to prevent cancellation at the crossover frequency.

        Args:
            phase: Phase in degrees (0 or 180).

        Raises:
            ValueError: If phase is not 0 or 180.
            WiiMError: If the request fails.
        """
        if phase not in (SUBWOOFER_PHASE_0, SUBWOOFER_PHASE_180):
            raise ValueError(f"Phase must be {SUBWOOFER_PHASE_0} or {SUBWOOFER_PHASE_180} degrees, got {phase}")
        await self._request(f"{API_ENDPOINT_SUBWOOFER_SET}phase:{phase}")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Level
    # ------------------------------------------------------------------

    async def set_subwoofer_level(self, level: int) -> None:
        """Set subwoofer level adjustment.

        Args:
            level: Level adjustment in dB (-15 to 15).
                   Negative values reduce subwoofer output,
                   positive values boost it.

        Raises:
            ValueError: If level is outside valid range.
            WiiMError: If the request fails.
        """
        if not SUBWOOFER_LEVEL_MIN <= level <= SUBWOOFER_LEVEL_MAX:
            raise ValueError(
                f"Level must be between {SUBWOOFER_LEVEL_MIN} " f"and {SUBWOOFER_LEVEL_MAX} dB, got {level}"
            )
        await self._request(f"{API_ENDPOINT_SUBWOOFER_SET}level:{level}")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Main speaker bass filter
    # ------------------------------------------------------------------

    async def set_main_speaker_bass(self, enabled: bool) -> None:
        """Enable or disable bass output to main speakers.

        When disabled, bass frequencies below the crossover are only
        sent to the subwoofer. When enabled, bass is sent to both
        main speakers and subwoofer.

        Args:
            enabled: True to send bass to main speakers, False to filter it out.

        Raises:
            WiiMError: If the request fails.

        Note:
            The API uses inverted logic: main_filter=1 means disabled,
            main_filter=0 means enabled. This method abstracts that.
        """
        # API uses inverted logic: 1=disabled, 0=enabled
        value = 0 if enabled else 1
        await self._request(f"{API_ENDPOINT_SUBWOOFER_SET}main_filter:{value}")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Subwoofer filter (bypass mode)
    # ------------------------------------------------------------------

    async def set_subwoofer_filter(self, enabled: bool) -> None:
        """Enable or disable subwoofer low-pass filter.

        When disabled (bypass mode), the full frequency range is sent
        to the subwoofer without filtering. When enabled, only frequencies
        below the crossover are sent to the subwoofer.

        Args:
            enabled: True to enable filtering, False for bypass mode.

        Raises:
            WiiMError: If the request fails.

        Note:
            The API uses inverted logic: sub_filter=1 means disabled,
            sub_filter=0 means enabled. This method abstracts that.
        """
        # API uses inverted logic: 1=disabled, 0=enabled
        value = 0 if enabled else 1
        await self._request(f"{API_ENDPOINT_SUBWOOFER_SET}sub_filter:{value}")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Delay adjustment
    # ------------------------------------------------------------------

    async def set_subwoofer_delay(self, delay_ms: int) -> None:
        """Set manual delay adjustment for subwoofer timing.

        Positive values add delay to the subwoofer output (use when
        subwoofer is closer to listening position than main speakers).
        Negative values add delay to main speaker output (use when
        subwoofer is further from listening position).

        Args:
            delay_ms: Delay adjustment in milliseconds (-200 to 200).

        Raises:
            ValueError: If delay is outside valid range.
            WiiMError: If the request fails.
        """
        if not SUBWOOFER_DELAY_MIN <= delay_ms <= SUBWOOFER_DELAY_MAX:
            raise ValueError(
                f"Delay must be between {SUBWOOFER_DELAY_MIN} " f"and {SUBWOOFER_DELAY_MAX} ms, got {delay_ms}"
            )
        await self._request(f"{API_ENDPOINT_SUBWOOFER_SET}sub_delay:{delay_ms}")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Convenience methods
    # ------------------------------------------------------------------

    async def is_subwoofer_supported(self) -> bool:
        """Check if subwoofer control is supported by this device.

        Returns:
            True if getSubLPF endpoint is available and responds.
        """
        status = await self.get_subwoofer_status()
        return status is not None

    async def is_subwoofer_connected(self) -> bool:
        """Check if a subwoofer is physically connected.

        Returns:
            True if subwoofer is plugged in, False otherwise.
        """
        status = await self.get_subwoofer_status()
        return status.plugged if status else False
