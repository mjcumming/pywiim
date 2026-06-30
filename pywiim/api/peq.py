"""Parametric Equalizer (PEQ) helpers for WiiM HTTP client.

This mixin implements the official WiiM LV2 PEQ API for 10-band parametric
equalization. Each band has four adjustable parameters:
  - mode:      -1=Off, 0=Low-Shelf, 1=Peak, 2=High-Shelf
  - frequency: 10–22000 Hz
  - Q:         0.01–24
  - gain:      -12–12 dB

The PEQ is identified by pluginURI ``http://moddevices.com/plugins/caps/EqNp``.
The same HTTP command family can target other LV2 plugins on the device (for
example the 10-band graphic plugin ``http://moddevices.com/plugins/caps/Eq10HP``);
this module implements **only** ``EqNp``.  See ``docs/integration/API_REFERENCE.md``
(PEQ section) for integrators who need ``Eq10HP``.

All commands operate on a per-source basis (wifi, bluetooth, line-in, etc.).

It assumes the base client provides the ``_request`` coroutine.  No state is
stored – all results come from the device on each call.

.. note::
    This API targets the WiiM LV2 PEQ system (``EQGetLV2BandEx``,
    ``EQSetLV2Band``, etc.) and is **not** available on Audio Pro, Arylic, or
    generic LinkPlay devices.  The client detects support via the
    ``supports_peq`` capability flag populated at connect time.

# pragma: allow-long-file peq-cohesive
# This file exceeds the 600 LOC hard limit but is kept as a cohesive unit
# because the data-models (PEQBand, PEQSettings, PEQPresetInfo), private
# helpers, and the PEQAPI mixin are all tightly coupled and small in
# isolation.  Splitting into peq_models.py would add an extra import layer
# for no practical maintainability gain.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from ..exceptions import WiiMError
from .constants import (
    API_ENDPOINT_EQ_OFF,
    API_ENDPOINT_PEQ_CHANGE_FX,
    API_ENDPOINT_PEQ_CHANGE_SOURCE_FX,
    API_ENDPOINT_PEQ_DELETE,
    API_ENDPOINT_PEQ_GET_BAND,
    API_ENDPOINT_PEQ_GET_LIST,
    API_ENDPOINT_PEQ_GET_NEW_LIST,
    API_ENDPOINT_PEQ_GET_SOURCE_BAND,
    API_ENDPOINT_PEQ_LOAD,
    API_ENDPOINT_PEQ_RENAME,
    API_ENDPOINT_PEQ_SAVE,
    API_ENDPOINT_PEQ_SET_BAND,
    API_ENDPOINT_PEQ_SET_CHANNEL_MODE,
    API_ENDPOINT_PEQ_SET_SOURCE_BAND,
    API_ENDPOINT_PEQ_SOURCE_LOAD,
    API_ENDPOINT_PEQ_SOURCE_OFF,
    API_ENDPOINT_PEQ_SOURCE_SAVE,
    API_ENDPOINT_ROOM_CORRECTION_GET,
    GEQ_PLUGIN_URI,
    PEQ_BAND_LETTERS,
    PEQ_CHANNEL_MODE_LR,
    PEQ_CHANNEL_MODE_STEREO,
    PEQ_DEFAULT_FREQUENCIES,
    PEQ_DEFAULT_GAIN,
    PEQ_DEFAULT_MODE,
    PEQ_DEFAULT_Q,
    PEQ_FREQ_MAX,
    PEQ_FREQ_MIN,
    PEQ_GAIN_MAX,
    PEQ_GAIN_MIN,
    PEQ_MODE_HIGH_SHELF,
    PEQ_MODE_LOW_SHELF,
    PEQ_MODE_OFF,
    PEQ_MODE_PEAK,
    PEQ_PLUGIN_URI,
    PEQ_Q_MAX,
    PEQ_Q_MIN,
)

_LOGGER = logging.getLogger(__name__)

# Re-export mode constants for convenient access by callers
__all__ = [
    "PEQAPI",
    "PEQBand",
    "PEQSettings",
    "PEQPresetInfo",
    "GraphicEQBand",
    "GraphicEQSettings",
    "RoomCorrectionSettings",
    "PEQ_MODE_OFF",
    "PEQ_MODE_LOW_SHELF",
    "PEQ_MODE_PEAK",
    "PEQ_MODE_HIGH_SHELF",
    "PEQ_CHANNEL_MODE_STEREO",
    "PEQ_CHANNEL_MODE_LR",
]

GEQ_BAND_NAMES = (
    "band31hz",
    "band63hz",
    "band125hz",
    "band250hz",
    "band500hz",
    "band1khz",
    "band2khz",
    "band4khz",
    "band8khz",
    "band16khz",
)


@dataclass
class PEQBand:
    """Represents a single parametric EQ band.

    Attributes:
        letter:    Band identifier letter (a–j).
        mode:      Filter type: -1=Off, 0=Low-Shelf, 1=Peak, 2=High-Shelf.
        frequency: Centre/corner frequency in Hz (10–22000).
        q:         Quality factor (0.01–24).
        gain:      Band gain in dB (-12–12).
    """

    letter: str
    mode: int = PEQ_DEFAULT_MODE
    frequency: float = field(default=0.0)
    q: float = PEQ_DEFAULT_Q
    gain: float = PEQ_DEFAULT_GAIN

    def __post_init__(self) -> None:
        if self.frequency == 0.0:
            self.frequency = PEQ_DEFAULT_FREQUENCIES.get(self.letter, 1000.0)

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_api_params(self) -> list[dict[str, Any]]:
        """Return the four band parameters as a list of API dicts."""
        p = self.letter
        return [
            {"param_name": f"{p}_mode", "value": float(self.mode)},
            {"param_name": f"{p}_freq", "value": float(self.frequency)},
            {"param_name": f"{p}_q", "value": float(self.q)},
            {"param_name": f"{p}_gain", "value": float(self.gain)},
        ]

    @classmethod
    def from_api_params(cls, letter: str, params: dict[str, float]) -> PEQBand:
        """Construct a PEQBand from the flat ``param_name → value`` dict.

        Args:
            letter: Band letter (a–j).
            params: Mapping of ``{letter}_mode``, ``{letter}_freq``,
                    ``{letter}_q``, ``{letter}_gain`` to their values.
        """
        p = letter
        return cls(
            letter=letter,
            mode=int(params.get(f"{p}_mode", PEQ_DEFAULT_MODE)),
            frequency=float(params.get(f"{p}_freq", PEQ_DEFAULT_FREQUENCIES.get(letter, 1000.0))),
            q=float(params.get(f"{p}_q", PEQ_DEFAULT_Q)),
            gain=float(params.get(f"{p}_gain", PEQ_DEFAULT_GAIN)),
        )


@dataclass
class PEQSettings:
    """Complete PEQ settings for one source.

    Attributes:
        source_name:  Device input source (e.g. ``"wifi"``, ``"line-in"``).
        enabled:      Whether PEQ is active (EQStat == "On").
        channel_mode: ``"Stereo"`` (shared L+R) or ``"L/R"`` (independent channels).
        name:         Loaded preset/custom name, empty string if none.
        bands:        10 bands for Stereo mode (or when channel_mode is "Stereo").
        bands_l:      Left-channel bands when channel_mode is ``"L/R"``.
        bands_r:      Right-channel bands when channel_mode is ``"L/R"``.
    """

    source_name: str = ""
    enabled: bool = False
    channel_mode: str = PEQ_CHANNEL_MODE_STEREO
    name: str = ""
    bands: list[PEQBand] = field(default_factory=list)
    bands_l: list[PEQBand] = field(default_factory=list)
    bands_r: list[PEQBand] = field(default_factory=list)


@dataclass
class PEQPresetInfo:
    """Metadata for a single PEQ custom or preset entry.

    Attributes:
        name:         Preset/custom name string.
        channel_mode: ``"Stereo"`` or ``"L/R"``.
        preset_type:  ``"Custom"`` for user-saved, ``"RC"`` for remote-control
                      auto-saved, or ``"Preset"`` for factory presets.
    """

    name: str
    channel_mode: str = PEQ_CHANNEL_MODE_STEREO
    preset_type: str = "Custom"


@dataclass
class GraphicEQBand:
    """One band from WiiM's LV2 10-band graphic EQ plugin."""

    name: str
    gain: float = 0.0


@dataclass
class GraphicEQSettings:
    """Settings for WiiM's LV2 10-band graphic EQ plugin (Eq10HP)."""

    source_name: str = ""
    enabled: bool = False
    channel_mode: str = PEQ_CHANNEL_MODE_STEREO
    name: str = ""
    eq_level: int | None = None
    bands: list[GraphicEQBand] = field(default_factory=list)


@dataclass
class RoomCorrectionSettings:
    """Read-only room-correction settings from ``RoomCorrGet``."""

    source_name: str = ""
    enabled: bool = False
    channel_mode: str = PEQ_CHANNEL_MODE_STEREO
    name: str = ""
    eq_level: int | None = None
    plugin_uri: str = PEQ_PLUGIN_URI
    bands: list[PEQBand] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_eq_band_array(band_array: list[dict[str, Any]]) -> list[PEQBand]:
    """Parse a raw EQBand/EQBandL/EQBandR array into a list of PEQBand objects.

    The device returns bands indexed 0–47 (4 params × 12 bands).
    We only surface bands a–j (indices 0–39).
    """
    # Build a flat param_name → value mapping
    param_map: dict[str, float] = {}
    for entry in band_array:
        pname = entry.get("param_name")
        val = entry.get("value")
        if pname and val is not None:
            try:
                param_map[str(pname)] = float(val)
            except (ValueError, TypeError):
                _LOGGER.debug("PEQ: skipping unreadable param %r = %r", pname, val)

    bands: list[PEQBand] = []
    for letter in PEQ_BAND_LETTERS:
        band = PEQBand.from_api_params(letter, param_map)
        bands.append(band)
    return bands


def _parse_graphic_eq_band_array(band_array: list[dict[str, Any]]) -> list[GraphicEQBand]:
    """Parse Eq10HP band array into stable 10-band graphic EQ objects."""
    gains: dict[str, float] = {}
    for entry in band_array:
        pname = entry.get("param_name")
        val = entry.get("value")
        if pname and val is not None:
            try:
                gains[str(pname)] = float(val)
            except (ValueError, TypeError):
                _LOGGER.debug("GEQ: skipping unreadable param %r = %r", pname, val)

    return [GraphicEQBand(name=name, gain=gains.get(name, 0.0)) for name in GEQ_BAND_NAMES]


def _parse_graphic_eq_settings(raw: dict[str, Any]) -> GraphicEQSettings:
    """Convert a raw Eq10HP API response into :class:`GraphicEQSettings`."""
    eq_level = raw.get("EQLevel")
    try:
        parsed_eq_level = int(eq_level) if eq_level is not None else None
    except (TypeError, ValueError):
        parsed_eq_level = None

    return GraphicEQSettings(
        source_name=str(raw.get("source_name", "")),
        enabled=str(raw.get("EQStat", "Off")).strip().lower() == "on",
        channel_mode=str(raw.get("channelMode", PEQ_CHANNEL_MODE_STEREO)),
        name=str(raw.get("Name", "")),
        eq_level=parsed_eq_level,
        bands=_parse_graphic_eq_band_array(raw.get("EQBand", [])),
    )


def _parse_room_correction_settings(raw: dict[str, Any]) -> RoomCorrectionSettings:
    """Convert a raw RoomCorrGet response into :class:`RoomCorrectionSettings`."""
    eq_level = raw.get("EQLevel")
    try:
        parsed_eq_level = int(eq_level) if eq_level is not None else None
    except (TypeError, ValueError):
        parsed_eq_level = None

    return RoomCorrectionSettings(
        source_name=str(raw.get("source_name", "")),
        enabled=str(raw.get("EQStat", "Off")).strip().lower() == "on",
        channel_mode=str(raw.get("channelMode", PEQ_CHANNEL_MODE_STEREO)),
        name=str(raw.get("Name", "")),
        eq_level=parsed_eq_level,
        plugin_uri=str(raw.get("pluginURI", PEQ_PLUGIN_URI)),
        bands=_parse_eq_band_array(raw.get("EQBand", [])),
    )


def _encode_json_param(payload: dict[str, Any]) -> str:
    """Serialize *payload* to a compact JSON string and URL-encode it.

    The WiiM HTTP API embeds JSON directly in the command query parameter,
    requiring URL encoding of ``{``, ``}``, ``"``, ``:``, etc.
    """
    return quote(json.dumps(payload, separators=(",", ":")), safe="")


def _bands_to_api_list(bands: list[PEQBand]) -> list[dict[str, Any]]:
    """Flatten a list of PEQBands into the API EQBand array format."""
    result: list[dict[str, Any]] = []
    for band in bands:
        result.extend(band.to_api_params())
    return result


# ---------------------------------------------------------------------------
# PEQAPI mixin
# ---------------------------------------------------------------------------


class PEQAPI:
    """Parametric Equalizer (PEQ) helpers – official WiiM LV2 PEQ API.

    This mixin provides full PEQ management including:
    - Reading and writing 10-band parametric EQ parameters
    - Per-source configuration (wifi, bluetooth, line-in, etc.)
    - Stereo and independent L/R channel modes
    - Saving, loading, deleting, and renaming custom presets
    """

    def _require_peq(self) -> None:
        """Raise WiiMError if the device does not support PEQ (supports_peq=False)."""
        if hasattr(self, "_capabilities") and self._capabilities:
            if not self._capabilities.get("supports_peq", False):
                raise WiiMError("Device does not support the WiiM LV2 PEQ API (supports_peq=False)")

    # ------------------------------------------------------------------
    # Display (get)
    # ------------------------------------------------------------------

    async def get_peq_bands(self, source_name: str | None = None) -> PEQSettings:
        """Get the PEQ settings for the current (or specified) source.

        .. note::
            Requires a WiiM device.  Check ``capabilities["supports_peq"]``
            before calling on unknown hardware.

        Args:
            source_name: Optional input source (e.g. ``"wifi"``, ``"line-in"``).
                         If *None*, uses the device's current active source.

        Returns:
            :class:`PEQSettings` with all band parameters, channel mode, and
            enabled status populated.

        Raises:
            WiiMError: If the request fails or the device does not support PEQ.
        """
        self._require_peq()
        _LOGGER.debug("get_peq_bands source=%s", source_name)
        if source_name is not None:
            payload = {"source_name": source_name, "pluginURI": PEQ_PLUGIN_URI}
            endpoint = API_ENDPOINT_PEQ_GET_SOURCE_BAND + _encode_json_param(payload)
        else:
            endpoint = API_ENDPOINT_PEQ_GET_BAND + quote(PEQ_PLUGIN_URI, safe="")

        raw = await self._request(endpoint)  # type: ignore[attr-defined]
        return _parse_peq_settings(raw.parsed if isinstance(raw.parsed, dict) else {})

    async def get_graphic_eq_bands(self, source_name: str | None = None) -> GraphicEQSettings:
        """Get WiiM LV2 graphic 10-band EQ settings.

        This targets the ``Eq10HP`` LV2 plugin used by WiiM's graphic EQ. It is
        read-only for now; use the WiiM app for setup until write behavior is
        tested across more firmware versions.
        """
        self._require_peq()
        _LOGGER.debug("get_graphic_eq_bands source=%s", source_name)
        if source_name is not None:
            payload = {"source_name": source_name, "pluginURI": GEQ_PLUGIN_URI}
            endpoint = API_ENDPOINT_PEQ_GET_SOURCE_BAND + _encode_json_param(payload)
        else:
            endpoint = API_ENDPOINT_PEQ_GET_BAND + quote(GEQ_PLUGIN_URI, safe="")

        raw = await self._request(endpoint)  # type: ignore[attr-defined]
        return _parse_graphic_eq_settings(raw.parsed if isinstance(raw.parsed, dict) else {})

    async def get_graphic_eq_preset_list(self) -> dict[str, list[str]]:
        """Get all custom and preset names for the WiiM graphic EQ plugin."""
        self._require_peq()
        endpoint = API_ENDPOINT_PEQ_GET_LIST + quote(GEQ_PLUGIN_URI, safe="")
        raw = await self._request(endpoint)  # type: ignore[attr-defined]
        data = raw.parsed if isinstance(raw.parsed, dict) else {}
        return {
            "custom": list(data.get("custom", [])),
            "preset": list(data.get("preset", [])),
        }

    async def get_room_correction(self) -> RoomCorrectionSettings:
        """Get WiiM room-correction settings.

        The payload is PEQ-shaped but belongs to the device's room-correction
        block, not the user PEQ preset. This helper is intentionally read-only.
        """
        self._require_peq()
        raw = await self._request(API_ENDPOINT_ROOM_CORRECTION_GET)  # type: ignore[attr-defined]
        return _parse_room_correction_settings(raw.parsed if isinstance(raw.parsed, dict) else {})

    # ------------------------------------------------------------------
    # Tune (set)
    # ------------------------------------------------------------------

    async def set_peq_bands(
        self,
        bands: list[PEQBand],
        *,
        channel_mode: str = PEQ_CHANNEL_MODE_STEREO,
        source_name: str | None = None,
    ) -> None:
        """Set PEQ band parameters for the current (or specified) source.

        This call also enables PEQ for the source and switches the source to
        the PEQ plugin type.

        Args:
            bands:        List of :class:`PEQBand` objects.  You may pass a
                          subset of the 10 bands – only those supplied are
                          updated on the device.
            channel_mode: ``"Stereo"`` (default) or ``"L/R"``.  For
                          ``"Stereo"`` pass all bands via *bands*.  For
                          ``"L/R"`` see :meth:`set_peq_bands_lr`.
            source_name:  Optional source to target.  If *None*, the device's
                          current source is used.

        Raises:
            ValueError:  If *channel_mode* is invalid.
            WiiMError:   If the request fails.
        """
        self._require_peq()
        _validate_channel_mode(channel_mode)
        payload: dict[str, Any] = {
            "pluginURI": PEQ_PLUGIN_URI,
            "channelMode": channel_mode,
            "EQBand": _bands_to_api_list(bands),
        }
        if source_name is not None:
            payload["source_name"] = source_name
            endpoint = API_ENDPOINT_PEQ_SET_SOURCE_BAND + _encode_json_param(payload)
        else:
            endpoint = API_ENDPOINT_PEQ_SET_BAND + _encode_json_param(payload)
        await self._request(endpoint)  # type: ignore[attr-defined]

    async def set_peq_bands_lr(
        self,
        bands_l: list[PEQBand],
        bands_r: list[PEQBand],
        *,
        source_name: str | None = None,
    ) -> None:
        """Set PEQ band parameters in independent L/R channel mode.

        Args:
            bands_l:     Left-channel bands.
            bands_r:     Right-channel bands.
            source_name: Optional source to target.

        Raises:
            WiiMError: If the request fails.
        """
        self._require_peq()
        payload: dict[str, Any] = {
            "pluginURI": PEQ_PLUGIN_URI,
            "channelMode": PEQ_CHANNEL_MODE_LR,
            "EQBandL": _bands_to_api_list(bands_l),
            "EQBandR": _bands_to_api_list(bands_r),
        }
        if source_name is not None:
            payload["source_name"] = source_name
            endpoint = API_ENDPOINT_PEQ_SET_SOURCE_BAND + _encode_json_param(payload)
        else:
            endpoint = API_ENDPOINT_PEQ_SET_BAND + _encode_json_param(payload)
        await self._request(endpoint)  # type: ignore[attr-defined]

    async def set_peq_band(
        self,
        letter: str,
        *,
        mode: int | None = None,
        frequency: float | None = None,
        q: float | None = None,
        gain: float | None = None,
        channel_mode: str = PEQ_CHANNEL_MODE_STEREO,
        source_name: str | None = None,
    ) -> None:
        """Update individual parameters of a single PEQ band.

        Only the supplied keyword arguments are sent to the device.

        Args:
            letter:       Band letter ``"a"``–``"j"``.
            mode:         Filter type (-1, 0, 1, or 2).
            frequency:    Centre/corner frequency in Hz.
            q:            Quality factor.
            gain:         Gain in dB.
            channel_mode: Channel mode (``"Stereo"`` or ``"L/R"``).
            source_name:  Optional source to target.

        Raises:
            ValueError: If *letter* is invalid or no parameter is specified.
            WiiMError:  If the request fails.
        """
        self._require_peq()
        letter = letter.lower()
        if letter not in PEQ_BAND_LETTERS:
            raise ValueError(f"Invalid PEQ band letter: {letter!r}. Must be one of {PEQ_BAND_LETTERS}.")

        params: list[dict[str, Any]] = []
        if mode is not None:
            _validate_mode(mode)
            params.append({"param_name": f"{letter}_mode", "value": float(mode)})
        if frequency is not None:
            _validate_frequency(frequency)
            params.append({"param_name": f"{letter}_freq", "value": float(frequency)})
        if q is not None:
            _validate_q(q)
            params.append({"param_name": f"{letter}_q", "value": float(q)})
        if gain is not None:
            _validate_gain(gain)
            params.append({"param_name": f"{letter}_gain", "value": float(gain)})

        if not params:
            raise ValueError("At least one of mode, frequency, q, or gain must be provided.")

        _validate_channel_mode(channel_mode)
        payload: dict[str, Any] = {
            "pluginURI": PEQ_PLUGIN_URI,
            "channelMode": channel_mode,
            "EQBand": params,
        }
        if source_name is not None:
            payload["source_name"] = source_name
            endpoint = API_ENDPOINT_PEQ_SET_SOURCE_BAND + _encode_json_param(payload)
        else:
            endpoint = API_ENDPOINT_PEQ_SET_BAND + _encode_json_param(payload)
        await self._request(endpoint)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Enable / disable
    # ------------------------------------------------------------------

    async def set_peq_enabled(
        self,
        enabled: bool,
        source_name: str | None = None,
    ) -> None:
        """Enable or disable PEQ for the current (or specified) source.

        Enabling switches the source to the PEQ plugin type.
        Disabling turns off EQ for the source.

        Args:
            enabled:     ``True`` to enable PEQ, ``False`` to disable.
            source_name: Optional source to target.

        Raises:
            WiiMError: If the request fails.
        """
        self._require_peq()
        _LOGGER.debug("set_peq_enabled enabled=%s source=%s", enabled, source_name)
        if enabled:
            if source_name is not None:
                payload = {"source_name": source_name, "pluginURI": PEQ_PLUGIN_URI}
                endpoint = API_ENDPOINT_PEQ_CHANGE_SOURCE_FX + _encode_json_param(payload)
            else:
                endpoint = API_ENDPOINT_PEQ_CHANGE_FX + quote(PEQ_PLUGIN_URI, safe="")
        else:
            if source_name is not None:
                payload = {"source_name": source_name, "pluginURI": PEQ_PLUGIN_URI}
                endpoint = API_ENDPOINT_PEQ_SOURCE_OFF + _encode_json_param(payload)
            else:
                # No source_name supplied: fall back to the legacy EQOff command,
                # which turns off EQ for the device's currently-active source.
                # Note: this sends the generic EQOff rather than the LV2-specific
                # EQSourceOff because we do not know the current source name without
                # an extra round-trip.  On all tested WiiM firmware versions EQOff
                # reliably disables the active PEQ plugin.  If you need to disable
                # PEQ for a specific source, pass source_name explicitly.
                _LOGGER.debug("PEQ disable via legacy EQOff (no source_name given)")
                endpoint = API_ENDPOINT_EQ_OFF
        await self._request(endpoint)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Channel mode
    # ------------------------------------------------------------------

    async def set_peq_channel_mode(
        self,
        channel_mode: str,
        source_name: str,
    ) -> None:
        """Set the channel mode (Stereo or L/R) for the given source.

        Args:
            channel_mode: ``"Stereo"`` or ``"L/R"``.
            source_name:  Target input source (required).

        Raises:
            ValueError: If *channel_mode* is invalid.
            WiiMError:  If the request fails.
        """
        self._require_peq()
        _validate_channel_mode(channel_mode)
        payload: dict[str, Any] = {
            "source_name": source_name,
            "pluginURI": PEQ_PLUGIN_URI,
            "channelMode": channel_mode,
        }
        endpoint = API_ENDPOINT_PEQ_SET_CHANNEL_MODE + _encode_json_param(payload)
        await self._request(endpoint)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Save / Load
    # ------------------------------------------------------------------

    async def get_peq_preset_list(self) -> dict[str, list[str]]:
        """Get all custom and preset names for the PEQ plugin.

        Returns:
            Dictionary with ``"custom"`` and ``"preset"`` keys, each mapping
            to a list of name strings.

        Raises:
            WiiMError: If the request fails.
        """
        self._require_peq()
        endpoint = API_ENDPOINT_PEQ_GET_LIST + quote(PEQ_PLUGIN_URI, safe="")
        raw = await self._request(endpoint)  # type: ignore[attr-defined]
        data = raw.parsed if isinstance(raw.parsed, dict) else {}
        return {
            "custom": list(data.get("custom", [])),
            "preset": list(data.get("preset", [])),
        }

    async def get_peq_preset_list_detailed(self) -> dict[str, list[PEQPresetInfo]]:
        """Get all custom and preset names with channel mode information.

        Returns:
            Dictionary with ``"custom"`` and ``"preset"`` keys, each mapping
            to a list of :class:`PEQPresetInfo` objects.

        Raises:
            WiiMError: If the request fails.
        """
        self._require_peq()
        payload = {"pluginURI": PEQ_PLUGIN_URI}
        endpoint = API_ENDPOINT_PEQ_GET_NEW_LIST + _encode_json_param(payload)
        raw = await self._request(endpoint)  # type: ignore[attr-defined]
        data = raw.parsed if isinstance(raw.parsed, dict) else {}

        def _parse_entries(entries: list[Any]) -> list[PEQPresetInfo]:
            result = []
            for entry in entries:
                if isinstance(entry, dict):
                    result.append(
                        PEQPresetInfo(
                            name=str(entry.get("Name", "")),
                            channel_mode=str(entry.get("channelMode", PEQ_CHANNEL_MODE_STEREO)),
                            preset_type=str(entry.get("Type", "Custom")),
                        )
                    )
                elif isinstance(entry, str):
                    result.append(PEQPresetInfo(name=entry))
            return result

        return {
            "custom": _parse_entries(data.get("custom", [])),
            "preset": _parse_entries(data.get("preset", [])),
        }

    async def save_peq(
        self,
        name: str,
        source_name: str | None = None,
    ) -> None:
        """Save the current PEQ settings as a custom preset.

        Args:
            name:        Custom preset name to save.
            source_name: Optional source to save settings from.  If *None*,
                         saves the current source's settings.

        Raises:
            WiiMError: If the request fails.
        """
        self._require_peq()
        if source_name is not None:
            payload: dict[str, Any] = {
                "source_name": source_name,
                "pluginURI": PEQ_PLUGIN_URI,
                "Name": name,
            }
            endpoint = API_ENDPOINT_PEQ_SOURCE_SAVE + _encode_json_param(payload)
        else:
            endpoint = API_ENDPOINT_PEQ_SAVE + quote(name, safe="")
        await self._request(endpoint)  # type: ignore[attr-defined]

    async def load_peq(
        self,
        name: str,
        source_name: str | None = None,
    ) -> PEQSettings:
        """Load a custom or preset PEQ configuration by name.

        The current source (or the specified source) will switch to and enable
        the PEQ plugin type.

        Args:
            name:        Preset/custom name to load.
            source_name: Optional source to load settings onto.

        Returns:
            :class:`PEQSettings` with the loaded parameters.

        Raises:
            WiiMError: If the request fails.
        """
        self._require_peq()
        if source_name is not None:
            payload: dict[str, Any] = {
                "source_name": source_name,
                "pluginURI": PEQ_PLUGIN_URI,
                "Name": name,
            }
            endpoint = API_ENDPOINT_PEQ_SOURCE_LOAD + _encode_json_param(payload)
        else:
            payload = {"pluginURI": PEQ_PLUGIN_URI, "Name": name}
            endpoint = API_ENDPOINT_PEQ_LOAD + _encode_json_param(payload)
        raw = await self._request(endpoint)  # type: ignore[attr-defined]
        return _parse_peq_settings(raw.parsed if isinstance(raw.parsed, dict) else {})

    async def delete_peq(self, name: str) -> None:
        """Delete a custom PEQ preset by name.

        Args:
            name: Custom preset name to delete.

        Raises:
            WiiMError: If the request fails.
        """
        self._require_peq()
        payload = {"pluginURI": PEQ_PLUGIN_URI, "Name": name}
        endpoint = API_ENDPOINT_PEQ_DELETE + _encode_json_param(payload)
        await self._request(endpoint)  # type: ignore[attr-defined]

    async def rename_peq(self, name: str, new_name: str) -> None:
        """Rename a custom PEQ preset.

        Both the original and new name must differ and the original must exist.

        Args:
            name:     Existing custom preset name.
            new_name: New name for the preset.

        Raises:
            ValueError: If *name* and *new_name* are the same.
            WiiMError:  If the request fails.
        """
        self._require_peq()
        if name == new_name:
            raise ValueError(f"name and new_name must differ (both are {name!r}).")
        payload = {"pluginURI": PEQ_PLUGIN_URI, "Name": name, "newName": new_name}
        endpoint = API_ENDPOINT_PEQ_RENAME + _encode_json_param(payload)
        await self._request(endpoint)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Private parsing / validation helpers
# ---------------------------------------------------------------------------


def _parse_peq_settings(raw: dict[str, Any]) -> PEQSettings:
    """Convert a raw API response dict into a :class:`PEQSettings` object."""
    enabled = str(raw.get("EQStat", "Off")).strip().lower() == "on"
    channel_mode = str(raw.get("channelMode", PEQ_CHANNEL_MODE_STEREO))
    source_name = str(raw.get("source_name", ""))
    name = str(raw.get("Name", ""))

    if channel_mode == PEQ_CHANNEL_MODE_LR:
        bands_l = _parse_eq_band_array(raw.get("EQBandL", []))
        bands_r = _parse_eq_band_array(raw.get("EQBandR", []))
        return PEQSettings(
            source_name=source_name,
            enabled=enabled,
            channel_mode=channel_mode,
            name=name,
            bands_l=bands_l,
            bands_r=bands_r,
        )
    else:
        bands = _parse_eq_band_array(raw.get("EQBand", []))
        return PEQSettings(
            source_name=source_name,
            enabled=enabled,
            channel_mode=channel_mode,
            name=name,
            bands=bands,
        )


def _validate_channel_mode(channel_mode: str) -> None:
    valid = {PEQ_CHANNEL_MODE_STEREO, PEQ_CHANNEL_MODE_LR}
    if channel_mode not in valid:
        raise ValueError(f"Invalid channel_mode {channel_mode!r}. Must be one of {sorted(valid)}.")


def _validate_mode(mode: int) -> None:
    valid = {PEQ_MODE_OFF, PEQ_MODE_LOW_SHELF, PEQ_MODE_PEAK, PEQ_MODE_HIGH_SHELF}
    if mode not in valid:
        raise ValueError(
            f"Invalid PEQ mode {mode}. Must be one of "
            f"{PEQ_MODE_OFF} (Off), {PEQ_MODE_LOW_SHELF} (Low-Shelf), "
            f"{PEQ_MODE_PEAK} (Peak), {PEQ_MODE_HIGH_SHELF} (High-Shelf)."
        )


def _validate_frequency(frequency: float) -> None:
    if not (PEQ_FREQ_MIN <= frequency <= PEQ_FREQ_MAX):
        raise ValueError(f"Frequency {frequency} Hz out of range [{PEQ_FREQ_MIN}, {PEQ_FREQ_MAX}].")


def _validate_q(q: float) -> None:
    if not (PEQ_Q_MIN <= q <= PEQ_Q_MAX):
        raise ValueError(f"Q value {q} out of range [{PEQ_Q_MIN}, {PEQ_Q_MAX}].")


def _validate_gain(gain: float) -> None:
    if not (PEQ_GAIN_MIN <= gain <= PEQ_GAIN_MAX):
        raise ValueError(f"Gain {gain} dB out of range [{PEQ_GAIN_MIN}, {PEQ_GAIN_MAX}].")
