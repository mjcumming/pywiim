"""WiiM API response parser.

This module provides functions to parse and normalize API responses from WiiM devices.
Handles field mapping, time unit conversion, text decoding, and device-specific quirks.
"""

from __future__ import annotations

import asyncio
import html
import logging
import time
from typing import Any
from urllib.parse import quote

from .constants import (
    EQ_NUMERIC_MAP,
    MODE_MAP,
    PLAY_MODE_NORMAL,
    PLAY_MODE_REPEAT_ALL,
    PLAY_MODE_REPEAT_ONE,
    PLAY_MODE_SHUFFLE,
    PLAY_MODE_SHUFFLE_REPEAT_ALL,
    STATUS_MAP,
)

_LOGGER = logging.getLogger(__name__)

# Rate-limit position>duration warnings (Issue mjcumming/wiim#188)
_POSITION_DURATION_WARNING_LAST: dict[str, float] = {}
_POSITION_DURATION_WARNING_INTERVAL = 60.0  # seconds
_POSITION_DURATION_TOLERANCE = 2  # seconds - ignore small clock drift

_MS_THRESHOLD = 36_000_000  # 10 hours * 3600 seconds * 1000 ms
_MILLISECOND_TIME_SOURCES = {
    "1",  # AirPlay
    "2",  # DLNA
    "10",  # Network/local URL playback
    "11",  # USB on some firmwares
    "51",  # USB on newer firmwares
    "airplay",
    "dlna",
    "network",
    "udisk",
    "udisklocal",
    "usb",
    "wifi",
}


def _time_source_key(value: str | None) -> str:
    """Return a normalized source key for time-unit heuristics."""
    return str(value or "").strip().lower().replace(" ", "").replace("_", "")


def _uses_milliseconds_for_large_values(source: str | None, vendor: str | None = None) -> bool:
    """Return True when a source is known to report curpos/totlen in milliseconds.

    Some local/network file playback modes legitimately exceed the old 10-hour
    threshold, so they must not be reclassified as microseconds.
    """
    source_key = _time_source_key(source)
    vendor_key = _time_source_key(vendor)
    return source_key in _MILLISECOND_TIME_SOURCES or vendor_key.startswith("udisk")


def _normalize_time_value(
    value: int,
    field_name: str,
    source: str | None = None,
    vendor: str | None = None,
) -> int:
    """Normalize time values that may be in milliseconds or microseconds.

    The LinkPlay API returns time in different units depending on the streaming source:
    - Most sources: milliseconds (1,000 ms = 1 second)
    - Streaming services (Spotify, etc.): microseconds (1,000,000 μs = 1 second)

    Known local/network file sources are always treated as milliseconds. Other
    sources use a fallback sanity check: if a value would represent > 10 hours
    when interpreted as milliseconds, it's likely in microseconds instead.

    Args:
        value: Raw time value from API
        field_name: Name of field for logging ("position" or "duration")
        source: Optional source name for enhanced logging
        vendor: Optional vendor/app name for source-specific time-unit handling

    Returns:
        Time in seconds

    See: https://github.com/mjcumming/wiim/issues/75
    """
    if _uses_milliseconds_for_large_values(source, vendor):
        result = value // 1_000
        _LOGGER.debug(
            "🎵 %s value %d treated as milliseconds for local/network source, "
            "converting to seconds: %d seconds (source: %s, vendor: %s)",
            field_name.capitalize(),
            value,
            result,
            source or "unknown",
            vendor or "unknown",
        )
        return result

    if value > _MS_THRESHOLD:
        # Value appears to be in microseconds
        result = value // 1_000_000
        _LOGGER.debug(
            "🎵 %s value %d appears to be in microseconds (> 10 hours if ms), "
            "converting from μs to seconds: %d seconds (source: %s)",
            field_name.capitalize(),
            value,
            result,
            source or "unknown",
        )
        return result
    else:
        # Standard millisecond conversion
        result = value // 1_000
        _LOGGER.debug(
            "🎵 %s value %d appears to be in milliseconds, converting to seconds: %d seconds (source: %s)",
            field_name.capitalize(),
            value,
            result,
            source or "unknown",
        )
        return result


def parse_player_status(
    raw: dict[str, Any],
    last_track: str | None = None,
    vendor: str | None = None,
    loop_mode_scheme: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Normalise *getPlayerStatusEx* / *getStatusEx* responses.

    Parses raw API response and normalizes field names, values, and formats.
    Handles time unit conversion, text decoding, and device-specific quirks.

    Args:
        raw: Raw API response dictionary
        last_track: Previous track identifier for change detection
        vendor: Device vendor (fallback when ``loop_mode_scheme`` is not set)
        loop_mode_scheme: Profile scheme ``wiim`` / ``arylic`` / ``legacy`` for ``loop_mode``
            decode (preferred over vendor alone; see ``get_device_profile``).

    Returns:
        Tuple of (parsed_data, new_last_track)
    """
    data: dict[str, Any] = {}

    play_state_val = raw.get("state") or raw.get("player_state") or raw.get("status")
    if play_state_val is not None:
        data["play_status"] = play_state_val

    # Generic key mapping first.
    for k, v in raw.items():
        if k in ("status", "state", "player_state"):
            continue
        data[STATUS_MAP.get(k, k)] = v

    # Hex-encoded strings → UTF-8 (per LinkPlay API standard)
    # Get raw values from original dict (before STATUS_MAP mapping)
    # STATUS_MAP maps Title/Artist/Album to title_hex/artist_hex/album_hex,
    # but we need the original hex values to decode them
    raw_title = raw.get("Title") or raw.get("title") or data.get("title_hex")
    raw_artist = raw.get("Artist") or raw.get("artist") or data.get("artist_hex")
    raw_album = raw.get("Album") or raw.get("album") or data.get("album_hex")

    decoded_title = _decode_text(raw_title)
    decoded_artist = _decode_text(raw_artist)
    decoded_album = _decode_text(raw_album)

    # Set both lowercase (for StateSynchronizer) and capitalized (for model alias)
    # Override any hex values with decoded values
    data["title"] = decoded_title
    data["Title"] = decoded_title  # For Pydantic model alias
    data["artist"] = decoded_artist
    data["Artist"] = decoded_artist  # For Pydantic model alias
    data["album"] = decoded_album
    data["Album"] = decoded_album  # For Pydantic model alias

    # Metadata parsing debug logging removed to reduce noise on every poll.
    # Track changes are logged below when they actually change.

    # Track change detection for debug logging.
    new_last_track = last_track
    if data.get("title") and data["title"] != "Unknown":
        cur = f"{data.get('artist', 'Unknown')} - {data['title']}"
        if last_track != cur:
            _LOGGER.debug("🎵 Track changed: %s", cur)
            new_last_track = cur

    # Power state defaults to *True* when missing.
    data.setdefault("power", True)

    # Volume (int percentage) → float 0-1.
    if (vol := raw.get("vol")) is not None:
        try:
            vol_i = int(vol)
            data["volume_level"] = vol_i / 100
            data["volume"] = vol_i
        except ValueError:
            _LOGGER.debug("Invalid volume value: %s", vol)

    # Playback position & duration (auto-detect ms vs μs).
    # The API returns time in milliseconds for most sources but microseconds for streaming services.
    # Use intelligent normalization to handle both cases.
    # See: https://github.com/mjcumming/wiim/issues/75
    source_hint = raw.get("mode") or raw.get("source")  # Will be used for enhanced logging
    vendor_hint = raw.get("vendor") or raw.get("Vendor") or raw.get("app") or vendor

    # AirPlay debug logging removed to reduce noise on every poll.
    # Raw API response still available for debugging if needed.

    # Check both original field names and mapped field names (since generic mapping happens first)
    if (pos := raw.get("curpos") or raw.get("offset_pts") or data.get("position_ms")) is not None:
        try:
            pos_int = int(pos)
            normalized_position = _normalize_time_value(pos_int, "position", source_hint, vendor_hint)
            data["position"] = normalized_position
            _LOGGER.debug("🎵 API PARSER: Setting data['position'] = %s", normalized_position)

            # Enhanced logging for position parsing
            source_type = "AirPlay" if source_hint and "airplay" in source_hint.lower() else source_hint or "unknown"
            _LOGGER.debug(
                "🎵 Position from API: %d seconds (source: %s, raw_value: %d)",
                normalized_position,
                source_type,
                pos_int,
            )

            # Try to use event loop time if available (async context), otherwise use time.time()
            try:
                data["position_updated_at"] = asyncio.get_running_loop().time()
            except RuntimeError:
                data["position_updated_at"] = time.time()
        except (ValueError, TypeError):
            _LOGGER.debug("Invalid position value: %s", pos)

    if (duration_val := raw.get("totlen") or data.get("duration_ms")) is not None:
        try:
            duration_int = int(duration_val)
            if duration_int > 0:  # Only set duration if it's actually provided
                normalized_duration = _normalize_time_value(duration_int, "duration", source_hint, vendor_hint)

                # For AirPlay and other streaming sources, totlen is the actual total duration
                # The previous logic incorrectly interpreted it as remaining time
                # AirPlay provides both position (elapsed) and totlen (total duration) correctly
                data["duration"] = normalized_duration

                # Enhanced logging to help identify AirPlay and other sources
                source_type = (
                    "AirPlay" if source_hint and "airplay" in source_hint.lower() else source_hint or "unknown"
                )
        except (ValueError, TypeError):
            _LOGGER.debug("Invalid duration value: %s", duration_val)

    # Validate position vs duration - detect impossible scenarios (Issue mjcumming/wiim#188)
    # Never reset position to 0 - prefer hiding unreliable duration. Add tolerance for
    # small clock drift (e.g. Lyrion mode=34). Rate-limit warnings to avoid log spam.
    if data.get("position") is not None and data.get("duration") is not None:
        position = data["position"]
        duration = data["duration"]
        if duration > 0 and position > duration + _POSITION_DURATION_TOLERANCE:
            # Duration unreliable (firmware/source quirk) - hide it, keep position
            data["duration"] = None

            # Rate-limited warning: once per (mode, track) per interval
            device_name = raw.get("device_name", "unknown")
            source = source_hint or "unknown"
            track_key = f"{source}:{data.get('title', '')}:{data.get('artist', '')}"
            now = time.time()
            last_log = _POSITION_DURATION_WARNING_LAST.get(track_key, 0)
            use_warning = (now - last_log) >= _POSITION_DURATION_WARNING_INTERVAL
            if use_warning:
                _POSITION_DURATION_WARNING_LAST[track_key] = now
                # Prune old entries (keep dict bounded)
                if len(_POSITION_DURATION_WARNING_LAST) > 50:
                    cutoff = now - _POSITION_DURATION_WARNING_INTERVAL * 2
                    for k in list(_POSITION_DURATION_WARNING_LAST.keys()):
                        if _POSITION_DURATION_WARNING_LAST[k] < cutoff:
                            del _POSITION_DURATION_WARNING_LAST[k]

            msg = (
                f"Position {position} > duration {duration} (device: {device_name}, source: {source}). "
                "Hiding duration; keeping position."
            )
            # Lyrion (mode 34) has known firmware quirk - log at DEBUG to avoid spam (Issue mjcumming/wiim#188)
            is_lyrion = str(source_hint) == "34" if source_hint is not None else False
            if is_lyrion:
                _LOGGER.debug("Position/duration mismatch (Lyrion): %s", msg)
            elif use_warning:
                _LOGGER.warning("🚨 Impossible media position detected: %s", msg)
            else:
                _LOGGER.debug("Position/duration mismatch: %s", msg)

    # Mute → bool.
    if "mute" in data:
        try:
            data["mute"] = bool(int(data["mute"]))
        except (TypeError, ValueError):  # noqa: PERF203 – clarity > micro perf.
            data["mute"] = bool(data["mute"])

    # Artwork – attempt cache-busting when metadata changes.
    cover = (
        raw.get("cover")
        or raw.get("cover_url")
        or raw.get("albumart")
        or raw.get("albumArtURI")
        or raw.get("albumArtUri")
        or raw.get("albumarturi")
        or raw.get("art_url")
        or raw.get("artwork_url")
        or raw.get("pic_url")
    )

    # Validate artwork URL - filter out invalid values like "unknow", "unknown", etc.
    if cover and str(cover).strip() not in (
        "unknow",
        "unknown",
        "un_known",
        "",
        "none",
    ):
        try:
            # Basic URL validation - must contain http or start with /
            if "http" in str(cover).lower() or str(cover).startswith("/"):
                cache_key = f"{data.get('title', '')}-{data.get('artist', '')}-{data.get('album', '')}"
                if cache_key:
                    encoded = quote(cache_key)
                    sep = "&" if "?" in cover else "?"
                    cover = f"{cover}{sep}cache={encoded}"
                data["entity_picture"] = cover
            else:
                _LOGGER.debug("Invalid artwork URL format: %s", cover)
        except Exception as e:
            _LOGGER.debug("Error processing artwork URL %s: %s", cover, e)

    # If artwork is invalid (sentinel values from API), clear it.
    # Note: Fallback to WiiM logo is handled at the property level (Player.media_image_url)
    # to allow StateSynchronizer to prefer real artwork from other sources (UPnP).
    entity_picture = data.get("entity_picture")
    if entity_picture and str(entity_picture).strip() in (
        "unknow",
        "unknown",
        "un_known",
        "",
        "none",
    ):
        data["entity_picture"] = None

    # Source mapping from *mode* field.
    # Always derive source from mode if source is missing, None, empty, or invalid.
    # This handles cases where the API returns mode but not source (e.g., DLNA mode="2").
    # See: https://github.com/mjcumming/wiim/issues/104
    if (mode_val := raw.get("mode")) is not None:
        current_source = data.get("source")
        # Only override if source is missing, None, empty, or invalid
        if not current_source or current_source in ("unknown", "wifi", ""):
            if str(mode_val) == "99":
                # Set multiroom source when mode=99, but check if we explicitly cleared it
                # If source was explicitly set to "unknown" (by remove_slave), don't override
                # Otherwise, trust mode=99 as indicating multiroom mode
                group_field = raw.get("group") or data.get("group")
                master_uuid = raw.get("master_uuid") or data.get("master_uuid")
                master_ip = raw.get("master_ip") or data.get("master_ip")

                # Check if device is explicitly NOT in a group (group="0" and no master info)
                # This indicates the device has left the group
                explicitly_not_in_group = group_field == "0" and not master_uuid and not master_ip

                # Only skip setting source if explicitly not in group AND source is None or "unknown"
                # (which indicates we just cleared it in remove_slave)
                if explicitly_not_in_group and (current_source is None or current_source == "unknown"):
                    # Device just left group - don't set source
                    _LOGGER.debug(
                        "Mode=99 detected but device explicitly not in group (group=%s) and source=%s, "
                        "not setting source",
                        group_field,
                        current_source or "None",
                    )
                else:
                    # Set source - use "multiroom" as fallback
                    # Note: If source is already set to master's name (by add_slave), this won't override
                    # because the condition checks for missing/unknown/multiroom sources.
                    # The actual master name will be set by add_slave() when device joins.
                    data["source"] = "multiroom"
                    data["_multiroom_mode"] = True
            else:
                mapped_source = MODE_MAP.get(str(mode_val), "unknown")
                # Only set if we have a valid mapping (not "unknown" or "idle")
                # "idle" is a play STATE, not a SOURCE - don't overwrite existing source
                # Defensive fix for Issues #122, #103: Prevent mode=0 from setting source="idle"
                # - Modern WiiM devices: Report correct mode values (e.g., mode=31 for Spotify)
                # - Legacy Audio Pro devices: May report mode=0 for DLNA/Spotify (Issue #103)
                # Without this check, source from vendor field could be overwritten with "idle"
                if mapped_source not in ("unknown", "idle"):
                    data["source"] = mapped_source
                    _LOGGER.debug(
                        "Mapped mode %s to source '%s' (previous source: %s)",
                        mode_val,
                        mapped_source,
                        current_source or "missing",
                    )
                else:
                    _LOGGER.debug(
                        "Mode %s maps to '%s' (not a valid source), keeping source '%s'",
                        mode_val,
                        mapped_source,
                        current_source or "missing",
                    )
        else:
            # Source already set to something other than unknown/wifi/empty
            # Log why mapping was skipped (following HA pattern: log both success and skip cases)
            _LOGGER.debug(
                "Skipping mode-to-source mapping: mode=%s, source already set to '%s'",
                mode_val,
                current_source,
            )

    # Vendor override (e.g. Amazon Music).
    vendor_val = raw.get("vendor") or raw.get("Vendor") or raw.get("app")
    if vendor_val:
        vendor_clean = str(vendor_val).strip()
        _VENDOR_MAP = {
            "amazon music": "amazon",
            "amazonmusic": "amazon",
            "prime": "amazon",
            "qobuz": "qobuz",
            "tidal": "tidal",
            "deezer": "deezer",
            # Chromecast sessions can report mode=5 (bluetooth) even when source is network (Issue #6).
            "chromecast": "wifi",
            "google cast": "wifi",
            "googlecast": "wifi",
            "chromecast built-in": "wifi",
            "cast": "wifi",  # WiiM Amp reports vendor="CAST" during Cast sessions (pywiim #19)
            # Apps that cast via Chromecast may report app name instead of "Chromecast".
            "bbc sounds": "wifi",
            "bbc iplayer": "wifi",
            "bbc": "wifi",
        }
        vendor_key = vendor_clean.lower()
        if vendor_key.startswith("udisk"):
            # WiiM Ultra USB playback can report mode=10 (network/local playback)
            # with vendor=UDiskLocal. Treat the vendor as the stronger signal
            # and expose the canonical source id from the source catalog.
            vendor_source = "usb"
        else:
            vendor_source = _VENDOR_MAP.get(vendor_key, vendor_key.replace(" ", "_"))
        current_source = data.get("source")
        should_override = current_source in {None, "wifi", "unknown"}
        # Issue #6: allow known network apps to override incorrect bluetooth mode mapping.
        if vendor_source == "wifi" and current_source == "bluetooth":
            should_override = True
        if should_override:
            data["source"] = vendor_source
        data["vendor"] = vendor_clean

    # Issue #6: Chromecast fallback when vendor is missing - use artwork URL to detect network streaming.
    # BBC Sounds and other cast apps sometimes don't report vendor; artwork domain is a reliable signal.
    if data.get("source") == "bluetooth":
        _chromecast_artwork_domains = ("bbci.co.uk", "bbc.co.uk")
        artwork_url = raw.get("cover") or raw.get("albumArtURI") or data.get("entity_picture") or data.get("cover")
        if isinstance(artwork_url, str) and any(d in artwork_url.lower() for d in _chromecast_artwork_domains):
            data["source"] = "wifi"
            _LOGGER.debug("Issue #6: source bluetooth overridden to wifi (artwork URL suggests Chromecast/network)")

    # Play-mode mapping from loop_mode values.
    # Decode after source mapping so source-specific protocol values (for example
    # Spotify loop_mode=5 on WiiM-scheme devices) have enough context.
    if "loop_mode" in data:
        try:
            # Convert loop_mode to int (API returns it as string)
            loop_val = int(data["loop_mode"])
            # Update data dict with int value for PlayerStatus model
            data["loop_mode"] = loop_val
        except (TypeError, ValueError):
            loop_val = 0
            data["loop_mode"] = 0

        # Only process play_mode if not already set
        if "play_mode" not in data:
            from .loop_mode import decode_loop_mode

            loop_state = decode_loop_mode(
                loop_val,
                loop_mode_scheme=loop_mode_scheme,
                vendor=vendor,
                source=data.get("source"),
            )

            # Map to play modes
            if loop_state.shuffle and loop_state.repeat_all:
                data["play_mode"] = PLAY_MODE_SHUFFLE_REPEAT_ALL
            elif loop_state.shuffle and loop_state.repeat_one:
                data["play_mode"] = PLAY_MODE_SHUFFLE  # Some devices don't differentiate shuffle+repeat_one
            elif loop_state.shuffle:
                data["play_mode"] = PLAY_MODE_SHUFFLE
            elif loop_state.repeat_one:
                data["play_mode"] = PLAY_MODE_REPEAT_ONE
            elif loop_state.repeat_all:
                data["play_mode"] = PLAY_MODE_REPEAT_ALL
            else:
                data["play_mode"] = PLAY_MODE_NORMAL

    # EQ numeric → textual preset.
    eq_raw = data.get("eq_preset")
    if isinstance(eq_raw, int | str) and str(eq_raw).isdigit():
        data["eq_preset"] = EQ_NUMERIC_MAP.get(str(eq_raw), eq_raw)

    # Enhanced Qobuz Connect state detection (addresses GitHub issue #35)
    # Qobuz Connect has complex state reporting issues that require sophisticated detection
    if data.get("source") == "qobuz" or (vendor_val and "qobuz" in str(vendor_val).lower()):
        _handle_qobuz_connect_state_quirks(data, raw)

    return data, new_last_track


def _hex_to_str(val: str | None) -> str | None:
    """Decode hex-encoded UTF-8 strings as used by LinkPlay."""
    if not val:
        return None
    try:
        return bytes.fromhex(val).decode("utf-8", errors="replace")
    except ValueError:
        return val


def _handle_qobuz_connect_state_quirks(data: dict[str, Any], raw: dict[str, Any]) -> None:
    """Handle Qobuz Connect state detection quirks.

    Addresses GitHub issue #35: Qobuz Connect shows playing briefly then switches to idle.
    Also handles HTTP ``status: "none"`` with live timeline/metadata (mjcumming/wiim#222).

    Args:
        data: Parsed data dictionary (modified in place)
        raw: Raw API response for additional context
    """
    current_status = data.get("play_status", "").lower()

    # Only skip when the device already reports a normal transport state we should not override.
    # Qobuz Connect often reports ``status: "none"`` while ``curpos`` / ``totlen`` and metadata
    # still reflect an active stream (see mjcumming/wiim#222); ``none`` must not bypass this path.
    if current_status in {
        "play",
        "playing",
        "pause",
        "paused",
        "paused playback",
        "load",
        "loading",
        "buffering",
        "transitioning",
    }:
        return

    # Enhanced detection: Look for multiple indicators that suggest active playback
    # This mimics the improved logic from python-linkplay v0.2.9

    title = data.get("title")
    has_track_info = bool(title and isinstance(title, str) and title.strip() and title != "Unknown")
    has_position_info = (
        data.get("position") is not None or raw.get("curpos") is not None or raw.get("offset_pts") is not None
    )
    has_duration_info = bool(data.get("duration") or raw.get("totlen"))
    has_artwork = bool(data.get("entity_picture") or raw.get("cover") or raw.get("albumArtURI"))

    # Additional context indicators
    artist = data.get("artist")
    has_artist = bool(artist and isinstance(artist, str) and artist.strip() and artist != "Unknown")
    album = data.get("album")
    has_album = bool(album and isinstance(album, str) and album.strip() and album != "Unknown")

    # Count the number of positive indicators
    playback_indicators = sum(
        [
            has_track_info,
            has_position_info,
            has_duration_info,
            has_artwork,
            has_artist,
            has_album,
        ]
    )

    # Qobuz Connect specific: If we have rich metadata but status is stopped,
    # it's likely incorrectly reported. But be conservative to avoid false positives.
    if playback_indicators >= 3:  # Need multiple indicators to be confident
        _LOGGER.debug(
            "🎵 Qobuz Connect state correction: status='%s' but %d indicators suggest active playback. "
            "Correcting to 'play' (track: %s)",
            current_status,
            playback_indicators,
            data.get("title", "Unknown"),
        )
        data["play_status"] = "play"
    else:
        # Not enough indicators - probably genuinely stopped/idle
        _LOGGER.debug(
            "🎵 Qobuz Connect: status='%s' with %d indicators - leaving unchanged",
            current_status,
            playback_indicators,
        )


def _decode_text(val: str | None) -> str | None:
    """Decode hex-encoded UTF-8 strings, then clean up HTML entities."""
    if not val:
        return None

    # First: Standard hex decoding as per API specification
    decoded = _hex_to_str(val)
    if decoded:
        # Second: Clean up HTML entities that may appear in hex-decoded text
        return html.unescape(decoded)

    return val


__all__ = ["parse_player_status"]
