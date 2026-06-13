"""Loop mode mappings for different device vendors.

WiiM and Arylic devices use different ``loop_mode`` integer schemes. Prefer
:func:`resolve_loop_mode_mapping` with ``loop_mode_scheme`` from
:class:`pywiim.profiles.DeviceProfile` — some WiiM firmware (e.g. Ultra 5.2+)
uses LinkPlay/Arylic numbering while ``vendor`` remains ``wiim``.
See https://github.com/mjcumming/pywiim/issues/17
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Literal, NamedTuple

__all__ = [
    "LoopModeMapping",
    "LoopModeState",
    "decode_loop_mode",
    "decode_loop_mode_for_player",
    "get_loop_mode_mapping",
    "get_loop_mode_mapping_for_scheme",
    "resolve_loop_mode_mapping",
    "resolve_loop_mode_mapping_for_player",
    "WIIM_LOOP_MODE",
    "ARYLIC_LOOP_MODE",
]

_LOGGER = logging.getLogger(__name__)

LoopModeAuthority = Literal["device", "source", "unknown"]

_UNKNOWN_LOOP_MODE_WARNING_LAST: dict[tuple[int, str, str | None], float] = {}
_UNKNOWN_LOOP_MODE_WARNING_INTERVAL = 60.0


class LoopModeMapping(NamedTuple):
    """Loop mode value mapping for a specific vendor."""

    # Map: (shuffle, repeat_one, repeat_all) -> loop_mode_value
    normal: int  # No shuffle, no repeat
    repeat_one: int  # No shuffle, repeat one
    repeat_all: int  # No shuffle, repeat all
    shuffle: int  # Shuffle, no repeat
    shuffle_repeat_one: int  # Shuffle + repeat one
    shuffle_repeat_all: int  # Shuffle + repeat all

    def to_loop_mode(self, shuffle: bool, repeat_one: bool, repeat_all: bool) -> int:
        """Convert shuffle/repeat flags to loop_mode value for this vendor.

        Args:
            shuffle: Whether shuffle is enabled
            repeat_one: Whether repeat one is enabled
            repeat_all: Whether repeat all is enabled

        Returns:
            The loop_mode value to send to the device
        """
        if shuffle and repeat_all:
            return self.shuffle_repeat_all
        if shuffle and repeat_one:
            return self.shuffle_repeat_one
        if shuffle:
            return self.shuffle
        if repeat_one:
            return self.repeat_one
        if repeat_all:
            return self.repeat_all
        return self.normal

    def from_loop_mode(self, loop_mode: int) -> tuple[bool, bool, bool]:
        """Convert loop_mode value to shuffle/repeat flags for this vendor.

        Args:
            loop_mode: The loop_mode value from the device

        Returns:
            Tuple of (shuffle, repeat_one, repeat_all) flags
        """
        if loop_mode == self.shuffle_repeat_all:
            return (True, False, True)
        if loop_mode == self.shuffle_repeat_one:
            return (True, True, False)
        if loop_mode == self.shuffle:
            return (True, False, False)
        if loop_mode == self.repeat_one:
            return (False, True, False)
        if loop_mode == self.repeat_all:
            return (False, False, True)
        if loop_mode == self.normal:
            return (False, False, False)

        return (False, False, False)

    def contains_loop_mode(self, loop_mode: int) -> bool:
        """Return whether the value is part of this documented mapping."""
        return loop_mode in {
            self.normal,
            self.repeat_one,
            self.repeat_all,
            self.shuffle,
            self.shuffle_repeat_one,
            self.shuffle_repeat_all,
        }


@dataclass(frozen=True)
class LoopModeState:
    """Decoded loop mode state, including context for source-specific values."""

    raw_value: int
    shuffle: bool | None
    repeat_one: bool | None
    repeat_all: bool | None
    authority: LoopModeAuthority
    known: bool


# WiiM Loop Mode Mapping
# Based on WiiM HTTP API documentation
# 0: loop all
# 1: single loop
# 2: shuffle loop
# 3: shuffle, no loop
# 4: no shuffle, no loop
WIIM_LOOP_MODE = LoopModeMapping(
    normal=4,  # no shuffle, no loop
    repeat_one=1,  # single loop
    repeat_all=0,  # loop all
    shuffle=3,  # shuffle, no loop
    shuffle_repeat_one=2,  # shuffle loop (WiiM doesn't differentiate shuffle+repeat_one from shuffle+repeat_all)
    shuffle_repeat_all=2,  # shuffle loop
)


# Arylic Loop Mode Mapping
# Based on Arylic HTTP API documentation
# 0: SHUFFLE disabled, REPEAT enabled (loop)
# 1: SHUFFLE disabled, REPEAT enabled (loop once)
# 2: SHUFFLE enabled, REPEAT enabled (loop)
# 3: SHUFFLE enabled, REPEAT disabled
# 4: SHUFFLE disabled, REPEAT disabled
# 5: SHUFFLE enabled, REPEAT enabled (loop once)
ARYLIC_LOOP_MODE = LoopModeMapping(
    normal=4,  # SHUFFLE disabled, REPEAT disabled
    repeat_one=1,  # SHUFFLE disabled, REPEAT enabled (loop once)
    repeat_all=0,  # SHUFFLE disabled, REPEAT enabled (loop)
    shuffle=3,  # SHUFFLE enabled, REPEAT disabled
    shuffle_repeat_one=5,  # SHUFFLE enabled, REPEAT enabled (loop once)
    shuffle_repeat_all=2,  # SHUFFLE enabled, REPEAT enabled (loop)
)


# Legacy bitfield mapping (used before vendor-specific mappings were implemented)
# This is kept for backwards compatibility with devices that might use this scheme
# Values: 0=normal, 1=repeat_one, 2=repeat_all, 4=shuffle, 5=shuffle+repeat_one, 6=shuffle+repeat_all
# Note: Value 3 (repeat_one + repeat_all) is invalid in this scheme
LEGACY_BITFIELD_LOOP_MODE = LoopModeMapping(
    normal=0,
    repeat_one=1,
    repeat_all=2,
    shuffle=4,
    shuffle_repeat_one=5,
    shuffle_repeat_all=6,
)


def decode_loop_mode(
    loop_mode: int,
    *,
    loop_mode_scheme: str | None = None,
    vendor: str | None = None,
    source: str | None = None,
) -> LoopModeState:
    """Decode a raw ``loop_mode`` value with device and source context.

    ``LoopModeMapping`` stays limited to documented scheme tables. This helper
    adds source-specific protocol behavior, such as Spotify reporting
    ``loop_mode=5`` on WiiM-scheme devices for single-track repeat.
    """
    mapping = resolve_loop_mode_mapping(loop_mode_scheme=loop_mode_scheme, vendor=vendor)
    source_key = _normalize_context_value(source)

    if mapping.contains_loop_mode(loop_mode):
        shuffle, repeat_one, repeat_all = mapping.from_loop_mode(loop_mode)
        return LoopModeState(
            raw_value=loop_mode,
            shuffle=shuffle,
            repeat_one=repeat_one,
            repeat_all=repeat_all,
            authority="device",
            known=True,
        )

    if mapping is WIIM_LOOP_MODE and source_key == "spotify" and loop_mode == 5:
        return LoopModeState(
            raw_value=loop_mode,
            shuffle=False,
            repeat_one=True,
            repeat_all=False,
            authority="source",
            known=True,
        )

    _log_unknown_loop_mode(loop_mode, mapping, source_key)
    return LoopModeState(
        raw_value=loop_mode,
        shuffle=False,
        repeat_one=False,
        repeat_all=False,
        authority="unknown",
        known=False,
    )


def decode_loop_mode_for_player(loop_mode: int, player: Any, source: str | None = None) -> LoopModeState:
    """Decode a raw ``loop_mode`` value using player profile and source context."""
    scheme: str | None = None
    prof = getattr(player, "profile", None)
    if prof is not None:
        scheme = getattr(prof, "loop_mode_scheme", None)
    if scheme is None:
        scheme = player.client._capabilities.get("loop_mode_scheme")
    vendor = player.client._capabilities.get("vendor")

    if source is None:
        status_model = getattr(player, "_status_model", None)
        source = getattr(status_model, "source", None)

    return decode_loop_mode(loop_mode, loop_mode_scheme=scheme, vendor=vendor, source=source)


def _normalize_context_value(value: str | None) -> str | None:
    """Normalize a source/vendor-like context value for comparisons."""
    if value is None:
        return None

    normalized = str(value).strip().lower().replace(" ", "_")
    if not normalized:
        return None
    if normalized.startswith("spotify"):
        return "spotify"
    return normalized


def _loop_mode_mapping_name(mapping: LoopModeMapping) -> str:
    """Return a stable name for warning keys and log context."""
    if mapping is WIIM_LOOP_MODE:
        return "wiim"
    if mapping is ARYLIC_LOOP_MODE:
        return "arylic"
    if mapping is LEGACY_BITFIELD_LOOP_MODE:
        return "legacy"
    return "unknown"


def _log_unknown_loop_mode(loop_mode: int, mapping: LoopModeMapping, source: str | None) -> None:
    """Warn about unknown values without multiplying logs on every property read."""
    scheme = _loop_mode_mapping_name(mapping)
    warning_key = (loop_mode, scheme, source)
    now = time.time()
    last_warning = _UNKNOWN_LOOP_MODE_WARNING_LAST.get(warning_key, 0)
    if (now - last_warning) < _UNKNOWN_LOOP_MODE_WARNING_INTERVAL:
        return

    _UNKNOWN_LOOP_MODE_WARNING_LAST[warning_key] = now
    if len(_UNKNOWN_LOOP_MODE_WARNING_LAST) > 50:
        cutoff = now - _UNKNOWN_LOOP_MODE_WARNING_INTERVAL * 2
        for key in list(_UNKNOWN_LOOP_MODE_WARNING_LAST):
            if _UNKNOWN_LOOP_MODE_WARNING_LAST[key] < cutoff:
                del _UNKNOWN_LOOP_MODE_WARNING_LAST[key]

    _LOGGER.warning(
        "Unknown loop_mode value: %d. Defaulting to normal playback. (scheme=%s, source=%s)",
        loop_mode,
        scheme,
        source or "unknown",
    )


def get_loop_mode_mapping_for_scheme(scheme: str) -> LoopModeMapping:
    """Return the mapping table for a profile ``loop_mode_scheme`` value.

    Args:
        scheme: ``"wiim"``, ``"arylic"``, or ``"legacy"`` (case-insensitive).

    Returns:
        The corresponding :class:`LoopModeMapping`.
    """
    key = (scheme or "wiim").strip().lower()
    if key == "arylic":
        return ARYLIC_LOOP_MODE
    if key == "legacy":
        return LEGACY_BITFIELD_LOOP_MODE
    return WIIM_LOOP_MODE


def resolve_loop_mode_mapping(
    *,
    loop_mode_scheme: str | None = None,
    vendor: str | None = None,
) -> LoopModeMapping:
    """Pick the correct mapping: prefer explicit scheme, then infer from vendor.

    Use this (with ``loop_mode_scheme`` from :func:`pywiim.profiles.get_device_profile`)
    anywhere shuffle/repeat is translated to or from ``loop_mode`` integers.
    """
    if loop_mode_scheme is not None and str(loop_mode_scheme).strip() != "":
        return get_loop_mode_mapping_for_scheme(loop_mode_scheme)
    return get_loop_mode_mapping(vendor)


def resolve_loop_mode_mapping_for_player(player: Any) -> LoopModeMapping:
    """Resolve mapping from a :class:`pywiim.player.Player` (profile + client capabilities)."""
    scheme: str | None = None
    prof = getattr(player, "profile", None)
    if prof is not None:
        scheme = getattr(prof, "loop_mode_scheme", None)
    if scheme is None:
        scheme = player.client._capabilities.get("loop_mode_scheme")
    vendor = player.client._capabilities.get("vendor")
    return resolve_loop_mode_mapping(loop_mode_scheme=scheme, vendor=vendor)


def get_loop_mode_mapping(vendor: str | None) -> LoopModeMapping:
    """Infer loop mode mapping from vendor string only (legacy helper).

    Prefer :func:`resolve_loop_mode_mapping` with ``loop_mode_scheme`` from the
    device profile when model/firmware uses a non-default scheme for this vendor.

    Args:
        vendor: Device vendor ("wiim", "arylic", "audio_pro", "linkplay_generic", or None)

    Returns:
        LoopModeMapping for the vendor

    Note:
        - WiiM devices use sequential values (0,1,2,3,4) in the *documented* WiiM scheme
        - Arylic devices use a different sequential scheme (0,1,2,3,4,5)
        - Audio Pro and generic LinkPlay devices default to Arylic mapping
        - Unknown/None vendors default to WiiM mapping (most common)
    """
    if not vendor:
        return WIIM_LOOP_MODE

    vendor_lower = vendor.lower()

    if vendor_lower == "wiim":
        return WIIM_LOOP_MODE
    elif vendor_lower in ("arylic", "audio_pro", "linkplay_generic"):
        return ARYLIC_LOOP_MODE
    else:
        # Unknown vendor - default to WiiM (most common)
        return WIIM_LOOP_MODE
