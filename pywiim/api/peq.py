"""LV2 parametric and graphic equalizer helpers for the WiiM HTTP client.

This mixin implements the official WiiM LV2 PEQ API for 10-band parametric
equalization. Each band has four adjustable parameters:
  - mode:      -1=Off, 0=Low-Shelf, 1=Peak, 2=High-Shelf
  - frequency: 10–22000 Hz
  - Q:         0.01–24
  - gain:      -12–12 dB

The PEQ is identified by pluginURI ``http://moddevices.com/plugins/caps/EqNp``.
The same HTTP command family can target other LV2 plugins on the device (for
example the 10-band graphic plugin ``http://moddevices.com/plugins/caps/Eq10HP``);
this module supports both ``EqNp`` and the stereo ``Eq10HP`` band API.
See ``docs/integration/API_REFERENCE.md`` for usage and verification limits.

All commands operate on a per-source basis (wifi, bluetooth, line-in, etc.).

It assumes the base client provides the ``_request`` coroutine.  No state is
stored – all results come from the device on each call.

.. note::
    PEQ requires the ``supports_peq`` capability. Graphic band operations
    require an actual Eq10HP response; PEQ capability alone does not establish
    graphic support on another model or firmware.

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
import math
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from ..exceptions import WiiMError, WiiMResponseError
from ..normalize import canonical_source_key
from .base import ApiResponse
from .constants import (
    API_ENDPOINT_EQ_OFF,
    API_ENDPOINT_PEQ_CHANGE_FX,
    API_ENDPOINT_PEQ_CHANGE_SOURCE_FX,
    API_ENDPOINT_PEQ_DELETE,
    API_ENDPOINT_PEQ_GET_BAND,
    API_ENDPOINT_PEQ_GET_LIST,
    API_ENDPOINT_PEQ_GET_NEW_LIST,
    API_ENDPOINT_PEQ_GET_SOURCE_BAND,
    API_ENDPOINT_PEQ_RENAME,
    API_ENDPOINT_PEQ_SET_CHANNEL_MODE,
    API_ENDPOINT_PEQ_SET_SOURCE_BAND,
    API_ENDPOINT_PEQ_SOURCE_LOAD,
    API_ENDPOINT_PEQ_SOURCE_OFF,
    API_ENDPOINT_PEQ_SOURCE_SAVE,
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
    ROOM_CORRECTION_EQ_LEVEL,
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
    """RoomFit state from ``EQGetLV2SourceBandEx`` at EQLevel 2."""

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
    """Parse complete, unambiguous PEQ bands reported by the device.

    The device returns bands indexed 0–47 (4 params × 12 bands).
    We only surface bands a–j (indices 0–39); incomplete bands are omitted
    instead of filling missing parameters with defaults.
    """
    if not isinstance(band_array, list):
        return []
    param_map: dict[str, float] = {}
    seen: set[str] = set()
    invalid: set[str] = set()
    for entry in band_array:
        if not isinstance(entry, dict):
            continue
        pname = entry.get("param_name")
        val = entry.get("value")
        if not isinstance(pname, str) or not pname:
            continue
        if pname in seen:
            invalid.add(pname)
            continue
        seen.add(pname)
        try:
            if val is None or isinstance(val, bool):
                raise ValueError("missing or boolean EQ parameter")
            parsed = float(val)
            if not math.isfinite(parsed):
                raise ValueError("non-finite EQ parameter")
            param_map[pname] = parsed
        except (ValueError, TypeError):
            invalid.add(pname)
            _LOGGER.debug("PEQ: skipping unreadable param %r = %r", pname, val)

    bands: list[PEQBand] = []
    for letter in PEQ_BAND_LETTERS:
        keys = {f"{letter}_{suffix}" for suffix in ("mode", "freq", "q", "gain")}
        if not keys.issubset(param_map) or keys & invalid:
            continue
        if not param_map[f"{letter}_mode"].is_integer() or param_map[f"{letter}_freq"] <= 0:
            continue
        bands.append(PEQBand.from_api_params(letter, param_map))
    return bands


def _parse_graphic_eq_band_array(band_array: list[dict[str, Any]]) -> list[GraphicEQBand]:
    """Parse reported Eq10HP bands without inventing missing gains."""
    gains: dict[str, float] = {}
    for entry in band_array:
        if not isinstance(entry, dict):
            continue
        pname = entry.get("param_name")
        val = entry.get("value")
        if pname and val is not None:
            try:
                gain = float(val)
                if math.isfinite(gain):
                    gains[str(pname)] = gain
            except (ValueError, TypeError):
                _LOGGER.debug("GEQ: skipping unreadable param %r = %r", pname, val)

    return [GraphicEQBand(name=name, gain=gains[name]) for name in GEQ_BAND_NAMES if name in gains]


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
    """Convert a RoomFit band response into :class:`RoomCorrectionSettings`."""
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


def parse_room_correction_profiles(raw: Any) -> list[str]:
    """Return saved RoomFit names from an ``EQv2GetNewList`` payload.

    Entries with a ``Type`` other than ``RC`` are skipped. A missing type is
    kept. Order follows ``custom`` then ``preset``.
    """
    if not isinstance(raw, dict):
        return []
    names: list[str] = []
    for key in ("custom", "preset"):
        entries = raw.get(key, [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, str):
                name = entry.strip()
            elif isinstance(entry, dict):
                if str(entry.get("Type", "RC")) != "RC":
                    continue
                name = str(entry.get("Name", "")).strip()
            else:
                continue
            if name and name not in names:
                names.append(name)
    return names


def _room_correction_payload(**extra: Any) -> dict[str, Any]:
    """EqNp payload at the RoomFit EQ level."""
    return {"EQLevel": ROOM_CORRECTION_EQ_LEVEL, "pluginURI": PEQ_PLUGIN_URI, **extra}


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


def _require_write_ack(response: ApiResponse, endpoint: str) -> None:
    """Reject explicit errors and unknown acknowledgments before readback."""
    if isinstance(response.parsed, dict):
        if not response.parsed.get("error") and str(response.parsed.get("status", "")).lower() == "ok":
            return
    elif response.parsed is None and isinstance(response.raw, str) and response.raw.strip().lower() == "ok":
        return
    raise WiiMResponseError("EQ command was rejected or returned an invalid acknowledgment", endpoint=endpoint)


def _confirm_band_values(actual: Any, expected: list[dict[str, Any]], endpoint: str) -> None:
    """Require real, finite readback for each requested parameter."""
    if not isinstance(actual, list):
        raise WiiMResponseError("EQ band readback is missing", endpoint=endpoint)
    values: dict[str, float] = {}
    for entry in actual:
        if not isinstance(entry, dict) or not isinstance(entry.get("param_name"), str):
            continue
        name = entry["param_name"]
        try:
            value = float(entry["value"])
        except (KeyError, TypeError, ValueError):
            continue
        if name in values or not math.isfinite(value):
            raise WiiMResponseError("EQ band readback is ambiguous or invalid", endpoint=endpoint)
        values[name] = value
    for entry in expected:
        name = entry["param_name"]
        tolerance = 0.001 if name.endswith("_mode") else 0.0051 if name.endswith("_q") else 0.051
        if name not in values or not math.isclose(values[name], float(entry["value"]), rel_tol=0.0, abs_tol=tolerance):
            raise WiiMResponseError(f"EQ band {name!r} was not confirmed by the device", endpoint=endpoint)


def _full_peq_parameters(data: dict[str, Any], endpoint: str) -> dict[str, list[dict[str, Any]]]:
    """Collect all reported PEQ parameters only when the ten bands are complete."""
    keys = ("EQBandL", "EQBandR") if data["channelMode"] == PEQ_CHANNEL_MODE_LR else ("EQBand",)
    required = {f"{letter}_{suffix}" for letter in PEQ_BAND_LETTERS for suffix in ("mode", "freq", "q", "gain")}
    result: dict[str, list[dict[str, Any]]] = {}
    for key in keys:
        entries = data.get(key)
        if not isinstance(entries, list):
            raise WiiMResponseError("PEQ bands are incomplete", endpoint=endpoint)
        params: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("param_name"), str):
                raise WiiMResponseError("Invalid PEQ bands", endpoint=endpoint)
            name = entry["param_name"]
            if not name or name in seen:
                raise WiiMResponseError("Ambiguous PEQ bands", endpoint=endpoint)
            seen.add(name)
            raw_value = entry.get("value")
            if raw_value is None:
                raise WiiMResponseError("Invalid PEQ bands", endpoint=endpoint)
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                raise WiiMResponseError("Invalid PEQ bands", endpoint=endpoint) from None
            if not math.isfinite(value):
                raise WiiMResponseError("Invalid PEQ bands", endpoint=endpoint)
            params.append({"param_name": name, "value": value})
        if not required.issubset(seen):
            raise WiiMResponseError("PEQ bands are incomplete", endpoint=endpoint)
        result[key] = params
    return result


def _validate_peq_bands(bands: list[PEQBand]) -> None:
    if not bands:
        raise ValueError("At least one PEQ band is required")
    letters: set[str] = set()
    for band in bands:
        if band.letter not in PEQ_BAND_LETTERS or band.letter in letters:
            raise ValueError(f"Invalid or duplicate PEQ band: {band.letter!r}")
        letters.add(band.letter)
        _validate_mode(band.mode)
        _validate_frequency(band.frequency)
        _validate_q(band.q)
        _validate_gain(band.gain)


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

    async def _read_lv2_state(self, plugin_uri: str, source_name: str | None) -> tuple[dict[str, Any], str]:
        """Read and validate the requested plugin and source without manufacturing state."""
        if source_name is None:
            endpoint = API_ENDPOINT_PEQ_GET_BAND + quote(plugin_uri, safe="")
        else:
            payload = {"source_name": source_name, "pluginURI": plugin_uri}
            endpoint = API_ENDPOINT_PEQ_GET_SOURCE_BAND + _encode_json_param(payload)
        response = await self._request(endpoint)  # type: ignore[attr-defined]
        data = response.parsed
        if (
            not isinstance(data, dict)
            or str(data.get("status", "")).lower() != "ok"
            or data.get("pluginURI") != plugin_uri
            or not isinstance(data.get("source_name"), str)
            or not data["source_name"].strip()
            or str(data.get("EQStat", "")).lower() not in ("on", "off")
            or data.get("channelMode") not in (PEQ_CHANNEL_MODE_STEREO, PEQ_CHANNEL_MODE_LR)
        ):
            raise WiiMResponseError("Invalid or unsupported LV2 EQ state response", endpoint=endpoint)
        if source_name is not None and canonical_source_key(data["source_name"]) != canonical_source_key(source_name):
            raise WiiMResponseError("EQ state belongs to a different source", endpoint=endpoint)
        return data, endpoint

    async def _write_lv2_bands(
        self,
        plugin_uri: str,
        source_name: str | None,
        channel_mode: str,
        band_arrays: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        """Write to the resolved source and verify each parameter independently."""
        before, _ = await self._read_lv2_state(plugin_uri, source_name)
        if plugin_uri == GEQ_PLUGIN_URI and before["channelMode"] != PEQ_CHANNEL_MODE_STEREO:
            raise WiiMResponseError("Graphic EQ L/R mode is not supported by this writer")
        target_source = before["source_name"]
        payload: dict[str, Any] = {
            "source_name": target_source,
            "pluginURI": plugin_uri,
            "channelMode": channel_mode,
            **band_arrays,
        }
        endpoint = API_ENDPOINT_PEQ_SET_SOURCE_BAND + _encode_json_param(payload)
        response = await self._request(endpoint)  # type: ignore[attr-defined]
        _require_write_ack(response, endpoint)
        after, read_endpoint = await self._read_lv2_state(plugin_uri, target_source)
        if str(after["EQStat"]).lower() != "on" or after["channelMode"] != channel_mode:
            raise WiiMResponseError("EQ write was not activated", endpoint=read_endpoint)
        for key, expected in band_arrays.items():
            _confirm_band_values(after.get(key), expected, read_endpoint)
        if source_name is None:
            current, current_endpoint = await self._read_lv2_state(plugin_uri, None)
            if canonical_source_key(current["source_name"]) != canonical_source_key(target_source):
                raise WiiMResponseError("Active source changed during the EQ write", endpoint=current_endpoint)
        return after

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
        if (
            not isinstance(raw.parsed, dict)
            or str(raw.parsed.get("status", "ok")).lower() != "ok"
            or str(raw.parsed.get("EQStat", "")).lower() not in ("on", "off")
        ):
            raise WiiMResponseError("Invalid PEQ state response", endpoint=endpoint)
        return _parse_peq_settings(raw.parsed)

    async def get_graphic_eq_bands(self, source_name: str | None = None) -> GraphicEQSettings:
        """Get WiiM LV2 graphic 10-band EQ settings.

        This targets the ``Eq10HP`` LV2 plugin. A valid plugin response is
        required; PEQ capability alone does not establish graphic support.
        """
        _LOGGER.debug("get_graphic_eq_bands source=%s", source_name)
        raw, endpoint = await self._read_lv2_state(GEQ_PLUGIN_URI, source_name)
        if raw["channelMode"] != PEQ_CHANNEL_MODE_STEREO or not isinstance(raw.get("EQBand"), list):
            raise WiiMResponseError("Graphic EQ bands are unavailable", endpoint=endpoint)
        settings = _parse_graphic_eq_settings(raw)
        if not settings.bands:
            raise WiiMResponseError("Graphic EQ bands are unavailable", endpoint=endpoint)
        return settings

    async def set_graphic_eq_bands(
        self, bands: list[GraphicEQBand], *, source_name: str | None = None
    ) -> GraphicEQSettings:
        """Apply graphic bands in dB and verify them on the requested source.

        The device must identify the Eq10HP plugin. This activates graphic EQ;
        omitted bands are left unchanged. Gain limits are -12 to +12 dB.
        """
        if not bands:
            raise ValueError("At least one graphic EQ band is required")
        names: set[str] = set()
        for band in bands:
            if band.name not in GEQ_BAND_NAMES or band.name in names:
                raise ValueError(f"Invalid or duplicate graphic EQ band: {band.name!r}")
            names.add(band.name)
            _validate_gain(band.gain)
        parameters = [{"param_name": band.name, "value": float(band.gain)} for band in bands]
        raw = await self._write_lv2_bands(GEQ_PLUGIN_URI, source_name, PEQ_CHANNEL_MODE_STEREO, {"EQBand": parameters})
        return _parse_graphic_eq_settings(raw)

    async def get_graphic_eq_preset_list(self) -> dict[str, list[str]]:
        """Get custom and preset names for a device's Eq10HP graphic plugin."""
        endpoint = API_ENDPOINT_PEQ_GET_LIST + quote(GEQ_PLUGIN_URI, safe="")
        raw = await self._request(endpoint)  # type: ignore[attr-defined]
        data = raw.parsed
        if (
            not isinstance(data, dict)
            or data.get("error")
            or str(data.get("status", "ok")).lower() != "ok"
            or not all(isinstance(data.get(key), list) for key in ("custom", "preset"))
            or not all(isinstance(name, str) for key in ("custom", "preset") for name in data[key])
        ):
            raise WiiMResponseError("Invalid graphic EQ preset list response", endpoint=endpoint)
        return {
            "custom": list(data["custom"]),
            "preset": list(data["preset"]),
        }

    async def get_room_correction(self) -> RoomCorrectionSettings:
        """Get RoomFit state.

        ``RoomCorrGet`` leaves ``EQStat`` off while RoomFit is on. The WiiM Home
        app reads ``EQGetLV2SourceBandEx`` at EQLevel 2. ``Name`` is the active
        profile.
        """
        self._require_peq()
        payload = _room_correction_payload(source_name="")
        endpoint = API_ENDPOINT_PEQ_GET_SOURCE_BAND + _encode_json_param(payload)
        raw = await self._request(endpoint)  # type: ignore[attr-defined]
        return _parse_room_correction_settings(raw.parsed if isinstance(raw.parsed, dict) else {})

    async def get_room_correction_profiles(self) -> list[str]:
        """Return saved RoomFit profile names.

        An empty list means the device did not return profiles. Callers should
        treat that as unsupported.
        """
        self._require_peq()
        endpoint = API_ENDPOINT_PEQ_GET_NEW_LIST + _encode_json_param(_room_correction_payload())
        raw = await self._request(endpoint)  # type: ignore[attr-defined]
        return parse_room_correction_profiles(raw.parsed)

    async def set_room_correction(self, name: str) -> None:
        """Load a RoomFit profile, or turn RoomFit off.

        ``Off`` (any case) sends ``EQSourceOff``. Any other name sends
        ``EQv2SourceLoad`` for that profile. This does not create profiles.
        """
        self._require_peq()
        cleaned = name.strip()
        if not cleaned:
            raise WiiMError("Room correction profile name is empty")
        if cleaned.lower() == "off":
            payload = _room_correction_payload(source_name="")
            endpoint = API_ENDPOINT_PEQ_SOURCE_OFF + _encode_json_param(payload)
        else:
            payload = _room_correction_payload(Name=cleaned)
            endpoint = API_ENDPOINT_PEQ_SOURCE_LOAD + _encode_json_param(payload)
        await self._request(endpoint)  # type: ignore[attr-defined]

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
            channel_mode: ``"Stereo"``. For independent channels use
                          :meth:`set_peq_bands_lr`.
            source_name:  Optional source to target.  If *None*, the device's
                          current source is used.

        Raises:
            ValueError:  If *channel_mode* is invalid.
            WiiMError:   If the write or its device readback fails.
        """
        self._require_peq()
        _validate_channel_mode(channel_mode)
        if channel_mode != PEQ_CHANNEL_MODE_STEREO:
            raise ValueError("Use set_peq_bands_lr for independent L/R bands")
        _validate_peq_bands(bands)
        await self._write_lv2_bands(PEQ_PLUGIN_URI, source_name, channel_mode, {"EQBand": _bands_to_api_list(bands)})

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
        _validate_peq_bands(bands_l)
        _validate_peq_bands(bands_r)
        await self._write_lv2_bands(
            PEQ_PLUGIN_URI,
            source_name,
            PEQ_CHANNEL_MODE_LR,
            {"EQBandL": _bands_to_api_list(bands_l), "EQBandR": _bands_to_api_list(bands_r)},
        )

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
        if channel_mode != PEQ_CHANNEL_MODE_STEREO:
            raise ValueError("Use set_peq_bands_lr for independent L/R bands")
        await self._write_lv2_bands(PEQ_PLUGIN_URI, source_name, channel_mode, {"EQBand": params})

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
        data = raw.parsed
        if (
            not isinstance(data, dict)
            or str(data.get("status", "ok")).lower() != "ok"
            or not all(isinstance(data.get(k), list) for k in ("custom", "preset"))
        ):
            raise WiiMResponseError("Invalid PEQ preset list response", endpoint=endpoint)
        if not all(isinstance(name, str) for key in ("custom", "preset") for name in data[key]):
            raise WiiMResponseError("Invalid PEQ preset name", endpoint=endpoint)
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
        *,
        overwrite: bool = False,
    ) -> None:
        """Save the current PEQ settings as a custom preset.

        Args:
            name:        Custom preset name to save.
            source_name: Optional source to save settings from.  If *None*,
                         saves the current source's settings.
            overwrite:   Explicitly allow replacing an existing custom profile.

        Saving loads the resulting profile to verify its stored bands. If that
        verification fails, the library attempts to restore the previous bands;
        the operation is not atomic and a failed restoration is reported.

        Raises:
            WiiMError: If the request fails.
        """
        self._require_peq()
        if not isinstance(name, str) or not name.strip():
            raise ValueError("PEQ preset name must not be empty")
        existing = await self.get_peq_preset_list()
        if any(item.casefold() == name.casefold() for item in existing["preset"]):
            raise ValueError(f"PEQ preset {name!r} already exists as a factory preset")
        matching = [item for item in existing["custom"] if item.casefold() == name.casefold()]
        if matching and (not overwrite or matching != [name]):
            raise ValueError(f"PEQ preset {name!r} already exists; use its exact name and overwrite=True")

        before, read_endpoint = await self._read_lv2_state(PEQ_PLUGIN_URI, source_name)
        if str(before["EQStat"]).lower() != "on":
            raise WiiMResponseError("Cannot save an inactive PEQ", endpoint=read_endpoint)
        channel_mode = before["channelMode"]
        expected = _full_peq_parameters(before, read_endpoint)
        target_source = before["source_name"]
        payload = {"source_name": target_source, "pluginURI": PEQ_PLUGIN_URI, "Name": name}
        endpoint = API_ENDPOINT_PEQ_SOURCE_SAVE + _encode_json_param(payload)
        response = await self._request(endpoint)  # type: ignore[attr-defined]
        _require_write_ack(response, endpoint)
        saved = await self.get_peq_preset_list()
        if name not in saved["custom"]:
            raise WiiMResponseError(f"PEQ preset {name!r} was not saved", endpoint=endpoint)
        after, read_endpoint = await self._read_lv2_state(PEQ_PLUGIN_URI, target_source)
        if after.get("Name") != name or str(after["EQStat"]).lower() != "on" or after["channelMode"] != channel_mode:
            raise WiiMResponseError(f"PEQ preset {name!r} was not confirmed", endpoint=read_endpoint)
        for key, params in expected.items():
            _confirm_band_values(after.get(key), params, read_endpoint)
        if source_name is None:
            current, current_endpoint = await self._read_lv2_state(PEQ_PLUGIN_URI, None)
            if canonical_source_key(current["source_name"]) != canonical_source_key(target_source):
                raise WiiMResponseError("Active source changed during the PEQ save", endpoint=current_endpoint)

        # A profile already appearing in the list does not prove an overwrite.
        # Reload the stored data and compare it with the pre-save curve.
        try:
            after_load, read_endpoint = await self._load_peq_on_source(name, target_source)
            if (
                after_load.get("Name") != name
                or str(after_load["EQStat"]).lower() != "on"
                or after_load["channelMode"] != channel_mode
            ):
                raise WiiMResponseError(f"Saved PEQ preset {name!r} was not loaded", endpoint=read_endpoint)
            for key, params in expected.items():
                _confirm_band_values(after_load.get(key), params, read_endpoint)
            if source_name is None:
                current, current_endpoint = await self._read_lv2_state(PEQ_PLUGIN_URI, None)
                if canonical_source_key(current["source_name"]) != canonical_source_key(target_source):
                    raise WiiMResponseError("Active source changed during the PEQ save", endpoint=current_endpoint)
        except WiiMError as exc:
            try:
                await self._write_lv2_bands(PEQ_PLUGIN_URI, target_source, channel_mode, expected)
            except WiiMError as restore_exc:
                raise WiiMResponseError(
                    f"PEQ save could not be verified and restoring the previous bands failed: {restore_exc}"
                ) from exc
            raise WiiMResponseError("PEQ save could not be verified; the previous bands were restored") from exc

    async def _load_peq_on_source(self, name: str, target_source: str) -> tuple[dict[str, Any], str]:
        """Load a profile onto a previously identified source and read it back."""
        payload = {"source_name": target_source, "pluginURI": PEQ_PLUGIN_URI, "Name": name}
        endpoint = API_ENDPOINT_PEQ_SOURCE_LOAD + _encode_json_param(payload)
        raw = await self._request(endpoint)  # type: ignore[attr-defined]
        if (
            not isinstance(raw.parsed, dict)
            or str(raw.parsed.get("status", "")).lower() != "ok"
            or str(raw.parsed.get("EQStat", "")).lower() != "on"
            or raw.parsed.get("Name") != name
        ):
            raise WiiMResponseError(f"Failed to load PEQ preset {name!r}", endpoint=endpoint)
        after, read_endpoint = await self._read_lv2_state(PEQ_PLUGIN_URI, target_source)
        if after.get("Name") != name or str(after["EQStat"]).lower() != "on":
            raise WiiMResponseError(f"PEQ preset {name!r} was not confirmed", endpoint=read_endpoint)
        _full_peq_parameters(after, read_endpoint)
        return after, read_endpoint

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
        if not isinstance(name, str) or not name.strip():
            raise ValueError("PEQ preset name must not be empty")
        before, _ = await self._read_lv2_state(PEQ_PLUGIN_URI, source_name)
        target_source = before["source_name"]
        after, _ = await self._load_peq_on_source(name, target_source)
        if source_name is None:
            current, current_endpoint = await self._read_lv2_state(PEQ_PLUGIN_URI, None)
            if canonical_source_key(current["source_name"]) != canonical_source_key(target_source):
                raise WiiMResponseError("Active source changed during the PEQ load", endpoint=current_endpoint)
        return _parse_peq_settings(after)

    async def delete_peq(self, name: str) -> None:
        """Delete a custom PEQ preset by name.

        Args:
            name: Custom preset name to delete.

        Raises:
            WiiMError: If the request fails.
        """
        self._require_peq()
        if not isinstance(name, str) or not name.strip():
            raise ValueError("PEQ preset name must not be empty")
        existing = await self.get_peq_preset_list()
        if name not in existing["custom"]:
            raise ValueError(f"Custom PEQ preset {name!r} does not exist")
        payload = {"pluginURI": PEQ_PLUGIN_URI, "Name": name}
        endpoint = API_ENDPOINT_PEQ_DELETE + _encode_json_param(payload)
        response = await self._request(endpoint)  # type: ignore[attr-defined]
        _require_write_ack(response, endpoint)
        if name in (await self.get_peq_preset_list())["custom"]:
            raise WiiMResponseError(f"PEQ preset {name!r} was not deleted", endpoint=endpoint)

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
        if not isinstance(name, str) or not name.strip() or not isinstance(new_name, str) or not new_name.strip():
            raise ValueError("PEQ preset names must not be empty")
        if name == new_name:
            raise ValueError(f"name and new_name must differ (both are {name!r}).")
        existing = await self.get_peq_preset_list()
        if name not in existing["custom"]:
            raise ValueError(f"Custom PEQ preset {name!r} does not exist")
        if any(item.casefold() == new_name.casefold() for group in existing.values() for item in group):
            raise ValueError(f"PEQ preset {new_name!r} already exists")
        payload = {"pluginURI": PEQ_PLUGIN_URI, "Name": name, "newName": new_name}
        endpoint = API_ENDPOINT_PEQ_RENAME + _encode_json_param(payload)
        response = await self._request(endpoint)  # type: ignore[attr-defined]
        _require_write_ack(response, endpoint)
        saved = (await self.get_peq_preset_list())["custom"]
        if name in saved or new_name not in saved:
            raise WiiMResponseError(f"PEQ preset {name!r} was not renamed", endpoint=endpoint)


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
