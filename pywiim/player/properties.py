"""Property getters for player state and metadata."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..device_capabilities import filter_plm_inputs, get_device_inputs
from ..metadata import is_valid_image_url, is_valid_metadata_value
from .source_capabilities import SourceCapability, get_source_capabilities

if TYPE_CHECKING:
    from . import Player

_LOGGER = logging.getLogger(__name__)

_KNOWN_SERVICE_SOURCES: tuple[tuple[str, str], ...] = (
    ("airplay", "AirPlay"),
    ("lyrion", "Lyrion"),
    ("spotify", "Spotify"),
    ("amazon", "Amazon Music"),
    ("tidal", "Tidal"),
    ("qobuz", "Qobuz"),
    ("deezer", "Deezer"),
    ("pandora", "Pandora"),
    ("tunein", "TuneIn"),
    ("iheartradio", "iHeartRadio"),
    ("dlna", "DLNA"),
)

_HARDWARE_SOURCE_KEYS: set[str] = {
    "network",
    "wifi",
    "bluetooth",
    "line_in",
    "line_in_2",
    "aux",
    "optical",
    "coaxial",
    "usb",
    "hdmi",
    "phono",
    "rca",
}


class PlayerProperties:
    """Provides property access to player state and metadata."""

    def __init__(self, player: Player) -> None:
        """Initialize properties.

        Args:
            player: Parent Player instance.
        """
        self.player = player

    # === Device Info ===

    @property
    def device_name(self) -> str | None:
        """Device name from cached device info."""
        if self.player._device_info is None:
            return None
        return self.player._device_info.name

    @property
    def firmware_update_available(self) -> bool:
        """Whether a firmware update is available and ready to install.

        Returns True if version_update="1" (update downloaded and ready),
        False otherwise (no update or not ready).

        Note: Updates cannot be installed via API. If an update is available
        and downloaded, rebooting the device will install it. Use player.reboot()
        to trigger installation.
        """
        if self.player._device_info is None:
            return False
        version_update = self.player._device_info.version_update
        if version_update is None:
            return False
        return str(version_update).strip() == "1"

    @property
    def latest_firmware_version(self) -> str | None:
        """Latest available firmware version from device info.

        Returns the version string from NewVer field in getStatusEx,
        or None if not available.
        """
        if self.player._device_info is None:
            return None
        latest = self.player._device_info.latest_version
        if latest and str(latest).strip() not in ("0", "-", ""):
            return str(latest).strip()
        return None

    # === Volume and Mute ===

    @property
    def volume_level(self) -> float | None:
        """Current volume level (0.0-1.0) from merged HTTP/UPnP state."""
        # Always read from state synchronizer (merges HTTP polling + UPnP events)
        merged = self.player._state_synchronizer.get_merged_state()
        volume = merged.get("volume")
        if volume is not None:
            return max(0.0, min(float(volume), 100.0)) / 100.0

        # Fallback to cached status if synchronizer has no data yet
        if self.player._status_model is None or self.player._status_model.volume is None:
            return None
        return max(0.0, min(float(self.player._status_model.volume), 100.0)) / 100.0

    @property
    def is_muted(self) -> bool | None:
        """Current mute state from merged HTTP/UPnP state."""
        # Always read from state synchronizer (merges HTTP polling + UPnP events)
        merged = self.player._state_synchronizer.get_merged_state()
        mute_val = merged.get("muted")

        # If not in merged state, fall back to cached status
        if mute_val is None and self.player._status_model is not None:
            mute_val = self.player._status_model.mute

        if mute_val is None:
            return None

        if isinstance(mute_val, (bool, int)):
            return bool(int(mute_val))

        mute_str = str(mute_val).strip().lower()
        if mute_str in ("1", "true", "yes", "on"):
            return True
        if mute_str in ("0", "false", "no", "off"):
            return False
        return None

    @property
    def channel_balance(self) -> float | None:
        """Stereo channel balance from player cache (HTTP API; not from UPnP)."""
        return self.player._channel_balance

    # === Playback State ===

    @property
    def play_state(self) -> str | None:
        """Current playback state from merged HTTP/UPnP state."""
        # Always read from state synchronizer (merges HTTP polling + UPnP events)
        merged = self.player._state_synchronizer.get_merged_state()
        play_state: str | None = merged.get("play_state")
        if play_state is not None:
            return play_state

        # Fallback to cached status if synchronizer has no data yet
        if self.player._status_model is None:
            return None
        return self.player._status_model.play_state

    @property
    def is_playing(self) -> bool:
        """Whether device is currently playing (including buffering/loading).

        Returns True for any active playback state: play, playing, buffering,
        loading, transitioning, load. This indicates the device is actively
        outputting or preparing to output audio.

        Use this property instead of checking play_state manually:
            # Good:
            if player.is_playing:
                ...
            # Avoid:
            if player.play_state in ("play", "playing", "buffering", ...):
                ...
        """
        state = self.play_state
        if not state:
            return False
        # Import here to avoid circular dependency
        from ..state import PLAYING_STATES

        return state.lower() in PLAYING_STATES

    @property
    def is_paused(self) -> bool:
        """Whether device is paused.

        Returns True only when playback is paused. Media is loaded but not
        playing. Resuming playback will continue from current position.
        """
        return self.play_state == "pause"

    @property
    def is_idle(self) -> bool:
        """Whether device is idle (no media loaded).

        Returns True when device has no active media. This indicates the device
        is not playing and has no media to resume.

        Note: "stop" states are normalized to "pause" (modern UX), so stopped
        devices are considered paused, not idle. Use is_paused to check for
        both paused and stopped states.
        """
        state = self.play_state
        return state is None or state in ("idle", "none")

    @property
    def is_buffering(self) -> bool:
        """Whether device is buffering or loading media.

        Returns True during loading, buffering, or transitioning states.
        Useful for showing loading indicators in UI.
        """
        state = self.play_state
        if not state:
            return False
        return state.lower() in ("buffering", "loading", "transitioning", "load")

    @property
    def state(self) -> str:
        """Normalized playback state: 'playing', 'paused', 'idle', or 'buffering'.

        This property provides a clean, consistent state string that maps
        directly to Home Assistant's MediaPlayerState values:
        - 'playing' → MediaPlayerState.PLAYING
        - 'paused' → MediaPlayerState.PAUSED
        - 'idle' → MediaPlayerState.IDLE
        - 'buffering' → MediaPlayerState.BUFFERING

        Example:
            ```python
            # Clean state mapping
            from homeassistant.components.media_player import MediaPlayerState

            STATE_MAP = {
                "playing": MediaPlayerState.PLAYING,
                "paused": MediaPlayerState.PAUSED,
                "idle": MediaPlayerState.IDLE,
                "buffering": MediaPlayerState.BUFFERING,
            }
            return STATE_MAP[player.state]
            ```
        """
        if self.is_buffering:
            return "buffering"
        if self.is_playing:
            return "playing"
        if self.is_paused:
            return "paused"
        return "idle"

    # === Media Metadata ===

    def _status_field(self, *names: str) -> str | None:
        """Return the first non-empty attribute from merged state or cached status."""
        # First try merged state (combines HTTP + UPnP)
        merged = self.player._state_synchronizer.get_merged_state()
        for n in names:
            val = merged.get(n)
            if val is not None:
                # Field-aware filtering: artwork fields must be valid URLs,
                # other metadata must be non-placeholder values.
                if n in {"image_url", "entity_picture", "cover_url"}:
                    if not is_valid_image_url(val):
                        continue
                else:
                    if not is_valid_metadata_value(val):
                        continue
                # (Keep the explicit placeholder set for backwards-compat readability.)
                if isinstance(val, str) and val.strip().lower() in {
                    "unknown",
                    "unknow",
                    "un_known",
                    "none",
                    "null",
                    "(null)",
                    "n/a",
                    "na",
                    "-",
                    "--",
                }:
                    continue
                if val not in (None, ""):
                    return str(val) if val is not None else None

        # Fallback to cached status if synchronizer has no data yet
        if self.player._status_model is None:
            return None

        for n in names:
            if hasattr(self.player._status_model, n):
                val = getattr(self.player._status_model, n)
                if n in {"image_url", "entity_picture", "cover_url"}:
                    if not is_valid_image_url(val):
                        continue
                else:
                    if not is_valid_metadata_value(val):
                        continue
                if isinstance(val, str) and val.strip().lower() in {
                    "unknown",
                    "unknow",
                    "un_known",
                    "none",
                    "null",
                    "(null)",
                    "n/a",
                    "na",
                    "-",
                    "--",
                }:
                    continue
                if val not in (None, ""):
                    return str(val) if val is not None else None
        return None

    @property
    def media_title(self) -> str | None:
        """Current track title from cached status.

        Falls back to extracting filename from last played URL if device
        doesn't report a title (common with direct URL playback).
        """
        title = self._status_field("title")
        if title:
            return title

        # Fallback: extract filename from last played URL
        url = self.player._last_played_url
        if url:
            from urllib.parse import unquote, urlparse

            try:
                parsed = urlparse(url)
                path = parsed.path
                if path:
                    # Get the last path segment
                    filename = path.rsplit("/", 1)[-1]
                    if filename:
                        # Decode URL-encoded characters
                        filename = unquote(filename)
                        # Remove query parameters if they snuck in
                        if "?" in filename:
                            filename = filename.split("?", 1)[0]
                        if filename:
                            return filename
            except Exception:
                pass  # Don't let URL parsing errors break title retrieval

        return None

    @property
    def media_artist(self) -> str | None:
        """Current track artist from cached status."""
        return self._status_field("artist")

    @property
    def media_album(self) -> str | None:
        """Current track album from cached status."""
        return self._status_field("album", "album_name")

    @property
    def media_content_id(self) -> str | None:
        """Current media content identifier (URL if playing from URL).

        Returns the URL that was passed to play_url() when playing URL-based media.
        This is useful for Home Assistant integration to expose the current media source.

        Note: Only populated for URL-based playback initiated via play_url().
        Other sources (Spotify, Bluetooth, etc.) will return None.
        """
        return self.player._last_played_url

    @property
    def media_duration(self) -> int | None:
        """Current track duration in seconds from cached status."""
        duration = self._status_field("duration")
        try:
            if duration is not None:
                result = int(float(duration))
                if result == 0:
                    return None
                return result
            return None
        except (TypeError, ValueError):
            return None

    @property
    def media_position(self) -> int | None:
        """Current playback position in seconds with hybrid estimation.

        Position estimation is handled by StateSynchronizer, which combines
        HTTP polling data and UPnP events, then estimates position between
        updates when playing.
        """
        # StateSynchronizer already does position estimation - just read it
        merged = self.player._state_synchronizer.get_merged_state()
        position = merged.get("position")

        if position is not None:
            try:
                pos_value = int(float(position))
                if pos_value < 0:
                    return None

                # Clamp to duration if available
                duration_value = self.media_duration
                if duration_value is not None and duration_value > 0:
                    if pos_value > duration_value:
                        pos_value = duration_value

                return pos_value
            except (TypeError, ValueError):
                return None

        # Fallback to cached status if synchronizer has no data yet
        if self.player._status_model is None:
            return None
        status_position = getattr(self.player._status_model, "position", None)
        if status_position is not None:
            try:
                pos_value = int(float(status_position))
                if pos_value < 0:
                    return None
                # Clamp to duration if available
                duration_value = self.media_duration
                if duration_value is not None and duration_value > 0:
                    if pos_value > duration_value:
                        pos_value = duration_value
                return pos_value
            except (TypeError, ValueError):
                return None

        return None

    @property
    def media_image_url(self) -> str | None:
        """Media image URL from cached status.

        Returns the first available artwork URL from:
        1. Merged state (image_url) - from HTTP or UPnP
        2. Cached status model (entity_picture or cover_url)
        3. Fallback to WiiM logo if no other artwork available
        """
        # First check merged state and status model for any valid artwork
        url = self._status_field("image_url", "entity_picture", "cover_url")
        if url:
            return url

        # Fallback to WiiM logo sentinel if no artwork found
        from ..api.constants import DEFAULT_WIIM_LOGO_URL

        return DEFAULT_WIIM_LOGO_URL

    @property
    def queue_count(self) -> int | None:
        """Total number of tracks in queue (from HTTP API plicount field)."""
        if self.player._status_model is None:
            return None
        count = getattr(self.player._status_model, "queue_count", None)
        if count is not None:
            try:
                return int(count)
            except (TypeError, ValueError):
                return None
        return None

    @property
    def queue_position(self) -> int | None:
        """Current track position in queue (from HTTP API plicurr field)."""
        if self.player._status_model is None:
            return None
        position = getattr(self.player._status_model, "queue_position", None)
        if position is not None:
            try:
                return int(position)
            except (TypeError, ValueError):
                return None
        return None

    @property
    def media_sample_rate(self) -> int | None:
        """Audio sample rate in Hz from metadata."""
        if self.player._metadata is None:
            return None
        meta_data = self.player._metadata.get("metaData", {})
        # API uses camelCase (sampleRate), but support both formats
        sample_rate = meta_data.get("sampleRate") or meta_data.get("sample_rate")
        if sample_rate is None:
            return None
        try:
            return int(sample_rate)
        except (TypeError, ValueError):
            return None

    @property
    def media_bit_depth(self) -> int | None:
        """Audio bit depth in bits from metadata."""
        if self.player._metadata is None:
            return None
        meta_data = self.player._metadata.get("metaData", {})
        # API uses camelCase (bitDepth), but support both formats
        bit_depth = meta_data.get("bitDepth") or meta_data.get("bit_depth")
        if bit_depth is None:
            return None
        try:
            return int(bit_depth)
        except (TypeError, ValueError):
            return None

    @property
    def media_bit_rate(self) -> int | None:
        """Audio bit rate in kbps from metadata."""
        if self.player._metadata is None:
            return None
        meta_data = self.player._metadata.get("metaData", {})
        # API uses camelCase (bitRate), but support both formats
        bit_rate = meta_data.get("bitRate") or meta_data.get("bit_rate")
        if bit_rate is None:
            return None
        try:
            return int(bit_rate)
        except (TypeError, ValueError):
            return None

    @property
    def media_codec(self) -> str | None:
        """Audio codec from status (e.g., 'flac', 'mp3', 'aac')."""
        if self.player._status_model is None:
            return None
        return getattr(self.player._status_model, "codec", None)

    # === Source-Based Capabilities ===
    # These capabilities depend on the current playback source.
    # See source_capabilities.py for the centralized capability definitions.

    def _get_source_capabilities(self) -> SourceCapability:
        """Get capabilities for current source.

        Uses the centralized SOURCE_CAPABILITIES mapping from source_capabilities.py.
        Includes special handling for Spotify podcasts (no shuffle/repeat).

        Returns:
            SourceCapability flags for the current source.
        """
        # Get raw source from status model (before normalization) for capability lookup
        # Capabilities are keyed by lowercase source names
        if self.player._status_model is None:
            return SourceCapability.NONE

        raw_source = self.player._status_model.source
        if not raw_source:
            return SourceCapability.NONE

        source_lower = raw_source.lower()

        # Special handling for Spotify - check content type via vendor URI
        # Podcasts and audiobooks don't support shuffle/repeat
        if source_lower == "spotify":
            vendor_uri = getattr(self.player._status_model, "vendor", None)
            if vendor_uri and isinstance(vendor_uri, str):
                if vendor_uri.startswith("spotify:show:") or vendor_uri.startswith("spotify:episode:"):
                    # Podcast/audiobook - track control only, no shuffle/repeat
                    return SourceCapability.TRACK_CONTROL

        return get_source_capabilities(raw_source)

    @property
    def shuffle_supported(self) -> bool:
        """Whether shuffle can be controlled by the device in current state.

        Returns False for:
        - External casting sources (AirPlay, Bluetooth, DLNA) where source app controls shuffle
        - Live radio (no queue to shuffle)
        - Physical inputs (passthrough audio)
        - Spotify podcasts/audiobooks (episodic content)

        Example:
            ```python
            if player.shuffle_supported:
                await player.set_shuffle(True)
            else:
                print("Shuffle controlled by source app")
            ```
        """
        return SourceCapability.SHUFFLE in self._get_source_capabilities()

    @property
    def repeat_supported(self) -> bool:
        """Whether repeat mode can be controlled by the device in current state.

        Returns False for:
        - External casting sources (AirPlay, Bluetooth, DLNA) where source app controls repeat
        - Live radio (no queue to repeat)
        - Physical inputs (passthrough audio)
        - Spotify podcasts/audiobooks (episodic content)

        Example:
            ```python
            if player.repeat_supported:
                await player.set_repeat("all")
            else:
                print("Repeat controlled by source app")
            ```
        """
        return SourceCapability.REPEAT in self._get_source_capabilities()

    @property
    def supports_next_track(self) -> bool:
        """Whether skip to next track is supported in current state.

        IMPORTANT: Returns True even when queue_count is 0.
        Streaming services (Spotify, Amazon, etc.) manage their own queues
        and don't report via plicount, but next/previous commands work.

        Home Assistant integrations should use this (or next_track_supported alias)
        to determine NEXT_TRACK support, NOT queue_count.

        Returns True for:
        - Streaming services: Spotify, Amazon, Tidal, Qobuz, Deezer, Pandora
        - Local playback: USB, Network (wifi), HTTP, playlist, preset
        - External casting: AirPlay, Bluetooth, DLNA (commands forwarded to app)
        - Multiroom slaves: Commands route through Group to master

        Returns False for:
        - Live radio: TuneIn, iHeartRadio (no "next" concept)
        - Physical inputs: Line-in, Optical, Coaxial, HDMI (passthrough audio)
        """
        return SourceCapability.NEXT_TRACK in self._get_source_capabilities()

    @property
    def supports_previous_track(self) -> bool:
        """Whether skip to previous track is supported in current state.

        Same logic as supports_next_track - see that property for details.

        Home Assistant integrations should use this (or previous_track_supported alias)
        to determine PREVIOUS_TRACK support, NOT queue_count.
        """
        return SourceCapability.PREVIOUS_TRACK in self._get_source_capabilities()

    @property
    def supports_seek(self) -> bool:
        """Whether seeking within track is supported in current state.

        Returns False for live radio and physical inputs where seeking doesn't apply.
        """
        return SourceCapability.SEEK in self._get_source_capabilities()

    # Aliases for WiiM HA integration compatibility (uses *_supported naming)
    @property
    def next_track_supported(self) -> bool:
        """Alias for supports_next_track (WiiM HA integration compatibility)."""
        return self.supports_next_track

    @property
    def previous_track_supported(self) -> bool:
        """Alias for supports_previous_track (WiiM HA integration compatibility)."""
        return self.supports_previous_track

    @property
    def seek_supported(self) -> bool:
        """Alias for supports_seek (WiiM HA integration compatibility)."""
        return self.supports_seek

    # === Shuffle and Repeat State ===

    @property
    def shuffle_state(self) -> bool | None:
        """Shuffle state, or None if not controlled by device.

        Returns None for external sources (AirPlay, Bluetooth, etc.) where
        the WiiM device doesn't control shuffle. Check shuffle_supported first.
        """
        if not self.shuffle_supported:
            return None

        if self.player._status_model is None:
            return None

        shuffle_val = getattr(self.player._status_model, "shuffle", None)
        if shuffle_val is not None:
            if isinstance(shuffle_val, (bool, int)):
                return bool(int(shuffle_val))
            shuffle_str = str(shuffle_val).strip().lower()
            return shuffle_str in {"1", "true", "shuffle"}

        loop_mode = getattr(self.player._status_model, "loop_mode", None)
        if loop_mode is not None:
            try:
                from ..api.loop_mode import decode_loop_mode_for_player

                loop_val = int(loop_mode)
                loop_state = decode_loop_mode_for_player(loop_val, self.player, source=self.source)
                return loop_state.shuffle
            except (TypeError, ValueError):
                pass

        play_mode = getattr(self.player._status_model, "play_mode", None)
        if play_mode is not None:
            mode_str = str(play_mode).strip().lower()
            return "shuffle" in mode_str

        return None

    @property
    def repeat_mode(self) -> str | None:
        """Repeat mode ('one', 'all', 'off'), or None if not controlled by device.

        Returns None for external sources (AirPlay, Bluetooth, etc.) where
        the WiiM device doesn't control repeat. Check repeat_supported first.
        """
        if not self.repeat_supported:
            return None

        if self.player._status_model is None:
            return None

        repeat_val = getattr(self.player._status_model, "repeat", None)
        if repeat_val is not None:
            repeat_str = str(repeat_val).strip().lower()
            if repeat_str in {"one", "single", "repeat_one", "repeatone", "1"}:
                return "one"
            elif repeat_str in {"all", "repeat_all", "repeatall", "2"}:
                return "all"
            else:
                return "off"

        loop_mode = getattr(self.player._status_model, "loop_mode", None)
        if loop_mode is not None:
            try:
                from ..api.loop_mode import decode_loop_mode_for_player

                loop_val = int(loop_mode)
                loop_state = decode_loop_mode_for_player(loop_val, self.player, source=self.source)

                if loop_state.repeat_one:
                    return "one"
                elif loop_state.repeat_all:
                    return "all"
                else:
                    return "off"
            except (TypeError, ValueError):
                pass

        play_mode = getattr(self.player._status_model, "play_mode", None)
        if play_mode is not None:
            mode_str = str(play_mode).strip().lower()
            if "repeat_one" in mode_str or mode_str in {"one", "single"}:
                return "one"
            elif "repeat_all" in mode_str or mode_str in {"all"}:
                return "all"
            elif "repeat" in mode_str and "shuffle" not in mode_str:
                return "all"

        return "off"

    @property
    def source(self) -> str | None:
        """Current source as a stable identifier.

        This returns a canonical source key that matches the `id` field in
        `player.source_catalog` entries. Use this for stable comparisons and
        storing state in integrations.

        For the UI-ready display name, use `player.source_name`.
        """
        merged = self.player._state_synchronizer.get_merged_state()
        source = merged.get("source")
        if source is None and self.player._status_model is not None:
            source = self.player._status_model.source
        if not source:
            return None
        return self._catalog_source_key(str(source))

    @property
    def source_id(self) -> str | None:
        """Alias for `source` (stable catalog id)."""
        return self.source

    @property
    def source_name(self) -> str | None:
        """Current source display name from cached status (UI-ready)."""
        merged = self.player._state_synchronizer.get_merged_state()
        source = merged.get("source")
        if source is None and self.player._status_model is not None:
            source = self.player._status_model.source
        if not source:
            return None
        return self._normalize_source_name(str(source))

    def _normalize_source_name(self, source: str) -> str:
        """Normalize source name to Title Case, handling acronyms correctly.

        Args:
            source: Source name (e.g., "airplay", "line_in", "line-in", "bluetooth")

        Returns:
            Formatted source name (e.g., "AirPlay", "Line In", "Bluetooth")
        """
        # Special handling for specific sources with non-standard capitalization
        source_lower = source.lower()
        if source_lower == "airplay":
            return "AirPlay"
        elif source_lower in ("wifi", "ethernet", "wi-fi", "network"):
            return "Network"  # Standardize on "Network" for streaming mode
        elif source_lower == "custompushurl":
            return "URL Stream"  # Device reports this when playing via play_url() API
        elif source_lower == "tunein":
            return "TuneIn"  # TuneIn (capital T, capital I)
        elif source_lower == "iheartradio":
            return "iHeartRadio"  # iHeartRadio (lowercase i, capital H, capital R)
        elif source_lower == "aux":
            return "Aux In"  # Aux In is more descriptive for UI

        # Known acronyms that should be all uppercase
        acronyms = {"dlna", "usb", "hdmi", "rssi", "spdif", "rca"}

        # Replace underscores AND hyphens with spaces for consistent word splitting
        # This handles both "line_in" and "line-in" variations
        formatted = source.replace("_", " ").replace("-", " ")

        # Split into words
        words = formatted.split()

        # Format each word
        formatted_words = []
        for word in words:
            word_lower = word.lower()
            if word_lower in acronyms:
                # Acronyms should be all uppercase
                formatted_words.append(word_lower.upper())
            elif (
                word_lower == "in"
                and formatted_words
                and formatted_words[-1].lower() in ("line", "optical", "coaxial", "aux")
            ):
                # "In" suffix for inputs should be capitalized (Title Case)
                formatted_words.append("In")
            else:
                # Regular words: capitalize first letter, lowercase rest
                # This ensures "CoaxIal" becomes "Coaxial"
                formatted_words.append(word.capitalize())

        # Ensure "In" suffix for specific physical inputs if missing
        if len(formatted_words) == 1:
            if formatted_words[0] == "Line":
                formatted_words.append("In")
            elif formatted_words[0] == "Optical":
                formatted_words.append("In")
            elif formatted_words[0] == "Aux":
                formatted_words.append("In")

        return " ".join(formatted_words)

    @property
    def eq_preset(self) -> str | None:
        """Current EQ preset from cached status, or "Off" if EQ is disabled.

        Returns:
            - "Off" if EQ is disabled (bypassed)
            - The preset name (Title Case) if EQ is enabled
            - None if status is not available

        Normalized to Title Case to match the format returned by get_eq_presets().
        The device may return lowercase in status but capitalized in preset list,
        so we normalize for consistency.
        """
        # Check if EQ is disabled - return "Off" if so
        # Note: _eq_enabled is None if we haven't fetched status yet, so default to showing preset
        if self.player._eq_enabled is False:
            return "Off"

        if self.player._status_model is None:
            return None
        preset = self.player._status_model.eq_preset
        if not preset:
            return None
        # Normalize to Title Case to match get_eq_presets() format
        # Handle special cases like "Hip-Hop" and "R&B"
        preset_lower = preset.lower()
        if "hip" in preset_lower and "hop" in preset_lower:
            return "Hip-Hop"
        elif preset_lower == "r&b" or preset_lower == "r and b":
            return "R&B"
        else:
            # Capitalize first letter of each word
            return " ".join(word.capitalize() for word in str(preset).split())

    @property
    def shuffle(self) -> bool | None:
        """Shuffle state from cached status (alias for shuffle_state)."""
        return self.shuffle_state

    @property
    def repeat(self) -> str | None:
        """Repeat mode from cached status (alias for repeat_mode)."""
        return self.repeat_mode

    @property
    def wifi_rssi(self) -> int | None:
        """Wi-Fi signal strength (RSSI) from cached status."""
        if self.player._status_model is None:
            return None
        return self.player._status_model.wifi_rssi

    # === Available Sources and Outputs ===

    @property
    def available_sources(self) -> list[str]:
        """Available input sources from cached device info.

        Returns user-selectable physical inputs plus the current source (if active):

        - Always included: Physical/hardware inputs (Line In, USB, Bluetooth,
          Optical, Coaxial, HDMI, etc.) - these can be manually selected by the user
        - Conditionally included: Current source (when active) - includes streaming
          services (AirPlay, Spotify, Amazon, etc.) and multi-room follower sources
          (e.g., "Master Bedroom"). These are NOT user-selectable but are included
          for correct UI state display
        - NOT included: Inactive streaming services - these can't be manually selected
          and aren't currently playing

        plm_support is the source of truth for physical inputs. input_list is
        used to augment with additional sources when available.

        Returns:
            List of available source names, or empty list if device info unavailable.
        """
        if self.player._device_info is None:
            return []

        # Streaming services and protocols that are externally activated
        streaming_services = {
            "amazon",
            "spotify",
            "tidal",
            "qobuz",
            "deezer",
            "pandora",
            "iheartradio",
            "tunein",
            "airplay",
            "dlna",
        }

        # Get current source to potentially include if it's a streaming service
        current_source = None
        if self.player._status_model is not None:
            current_source = self.player._status_model.source

        # Start with physical_inputs from plm_support (source of truth)
        physical_inputs = []

        # Parse plm_support bitmask - this is the source of truth for physical inputs
        if self.player._device_info.plm_support is not None:
            try:
                if isinstance(self.player._device_info.plm_support, str):
                    plm_value = (
                        int(self.player._device_info.plm_support.replace("0x", "").replace("0X", ""), 16)
                        if "x" in self.player._device_info.plm_support.lower()
                        else int(self.player._device_info.plm_support)
                    )
                else:
                    plm_value = int(self.player._device_info.plm_support)

                # Parse bitmask to get physical inputs (plm_support is source of truth)
                # Bit mappings per Arylic/LinkPlay documentation (1-based in docs, 0-based in code):
                # bit1 (bit 0): LineIn (Aux support)
                # bit2 (bit 1): Bluetooth support
                # bit3 (bit 2): USB support
                # bit4 (bit 3): Optical support
                # bit6 (bit 5): Coaxial support
                # bit8 (bit 7): LineIn 2 support
                # bit15 (bit 14): USBDAC support (not a selectable source, informational only)
                # Note: Newer devices (e.g., WiiM Ultra) may use additional bits for new inputs (e.g., phono, HDMI)
                if plm_value & (1 << 0):  # bit1: LineIn
                    physical_inputs.append("line_in")
                if plm_value & (1 << 1):  # bit2: Bluetooth
                    physical_inputs.append("bluetooth")
                if plm_value & (1 << 2):  # bit3: USB
                    physical_inputs.append("usb")
                if plm_value & (1 << 3):  # bit4: Optical
                    physical_inputs.append("optical")
                if plm_value & (1 << 5):  # bit6: Coaxial
                    physical_inputs.append("coaxial")
                if plm_value & (1 << 7):  # bit8: LineIn 2
                    physical_inputs.append("line_in_2")
                # Note: bit15 (USBDAC) is not a selectable source, so we don't add it to the list

                # Check for additional bits that might be set (for newer devices like WiiM Ultra)
                # Log all set bits for debugging to identify new bit mappings
                all_set_bits = []
                for bit_pos in range(16):  # Check bits 0-15
                    if plm_value & (1 << bit_pos):
                        all_set_bits.append(f"bit{bit_pos + 1} (bit {bit_pos})")

                if len(all_set_bits) > len(physical_inputs) + 1:  # +1 for USBDAC which we don't add
                    unknown_bits = [
                        b
                        for b in all_set_bits
                        if b
                        not in [
                            "bit1 (bit 0)",
                            "bit2 (bit 1)",
                            "bit3 (bit 2)",
                            "bit4 (bit 3)",
                            "bit6 (bit 5)",
                            "bit8 (bit 7)",
                            "bit15 (bit 14)",
                        ]
                    ]
                    if unknown_bits:
                        _LOGGER.debug(
                            "plm_support has unknown set bits (may indicate new inputs like phono/HDMI): %s",
                            ", ".join(unknown_bits),
                        )

                _LOGGER.debug(
                    "Parsed plm_support: value=%s (0x%x), detected inputs (before filtering): %s, all set bits: %s",
                    self.player._device_info.plm_support,
                    plm_value,
                    physical_inputs,
                    ", ".join(all_set_bits),
                )

                # Filter out spurious inputs based on device model (some devices report incorrect bits)
                # E.g., WiiM Pro reports USB bit but has no USB audio input (USB-C is power only)
                physical_inputs = filter_plm_inputs(physical_inputs, plm_value, self.player._device_info.model)
                if len(physical_inputs) < len(all_set_bits) - 1:  # Some bits were filtered
                    _LOGGER.debug("After device-specific filtering: %s", physical_inputs)
            except (ValueError, TypeError) as e:
                _LOGGER.warning(
                    "Failed to parse plm_support value '%s' for device %s: %s",
                    self.player._device_info.plm_support,
                    self.player.host,
                    e,
                )

        # Augment with input_list for:
        # 1. Current streaming service (if active)
        # 2. Physical inputs missing from plm_support (plm_support may be incomplete in some firmware)
        # plm_support is source of truth, but input_list can fill gaps when plm_support is incomplete
        if self.player._device_info.input_list is not None:
            # Normalize physical_inputs to lowercase set for quick lookup
            physical_inputs_lower = {s.lower() for s in physical_inputs}

            for source in self.player._device_info.input_list:
                if not source:
                    continue

                source_lower = source.lower()

                # Include WiFi/Ethernet as selectable source (user can switch to network mode)
                # Note: WiFi is the network connection mode, not a physical input, but users can select it
                if source_lower in ("wifi", "ethernet", "wi-fi"):
                    # Normalize to "wifi" for consistency
                    if "wifi" not in physical_inputs_lower:
                        physical_inputs.append("wifi")
                        physical_inputs_lower.add("wifi")
                    continue

                # Include current source even if it's a streaming service (for state display)
                if current_source and source_lower == current_source.lower():
                    physical_inputs.append(source)
                    continue

                # Skip streaming services and protocols (externally activated)
                # Only include if it's the current source (already handled above)
                if any(svc in source_lower for svc in streaming_services):
                    continue

                # Known physical input names (to identify physical inputs vs streaming services)
                # Includes all physical inputs that may appear in input_list but not in plm_support
                # Note: Some inputs are device-specific (e.g., "phono" is WiiM Ultra only),
                # but it's safe to include them here since they'll only be added if actually
                # present in the device's input_list
                known_physical_input_names = {
                    "line_in",
                    "linein",
                    "aux",
                    "optical",
                    "coaxial",
                    "coax",
                    "usb",
                    "bluetooth",
                    "hdmi",
                    "line_in_2",
                    "linein_2",
                    "phono",  # Phono input (WiiM Ultra specific, but safe to include for all devices)
                    "rca",  # RCA input (Audio Pro C10 MkII specific)
                }

                # If it's a known physical input and not already in our list, add it
                # This handles cases where plm_support is incomplete but input_list has the inputs
                if source_lower in known_physical_input_names and source_lower not in physical_inputs_lower:
                    physical_inputs.append(source)
                    physical_inputs_lower.add(source_lower)
                    _LOGGER.debug(
                        "Added physical input '%s' from input_list (not in plm_support) for device %s",
                        source,
                        self.player.host,
                    )

        # Augment with device capability database when input_list is not available or empty after filtering
        # plm_support is incomplete/unreliable for both WiiM AND Arylic devices
        # (e.g., Arylic UP2STREAM_AMP_V4 doesn't set line_in bit but has line_in hardware)
        # Also trigger fallback if only WiFi is present (need physical inputs)
        only_wifi = len(physical_inputs) == 1 and physical_inputs[0].lower() in ("wifi", "ethernet", "wi-fi")
        if self.player._device_info.input_list is None or not physical_inputs or only_wifi:
            vendor = self.player.client.capabilities.get("vendor", "").lower() if self.player.client else None
            device_inputs = get_device_inputs(self.player._device_info.model, vendor)

            if device_inputs and device_inputs.inputs:
                _LOGGER.debug(
                    "input_list not available or empty after filtering, "
                    "augmenting with device capability database for %s (vendor: %s)",
                    self.player._device_info.model,
                    vendor,
                )
                # Add model-specific inputs from database (removes duplicates later)
                physical_inputs.extend(device_inputs.inputs)
            elif not physical_inputs or only_wifi:
                # Last resort: no plm_support, no input_list (or all filtered out), no model match
                # Also use fallback if only WiFi is present (need physical inputs)
                _LOGGER.debug("No plm_support, input_list, or model match - using default fallback")
                physical_inputs.extend(["bluetooth", "line_in", "optical"])

        # If current source exists and isn't already in our list, add it
        # This handles:
        # - Streaming services when active (AirPlay, Spotify, Amazon, etc.)
        # - Multi-room sources (e.g., device following "Master Bedroom")
        # - Any other non-enumerated sources that are currently playing
        # We include these so the UI can display the current source correctly
        if current_source:
            current_source_lower = current_source.lower()
            physical_inputs_lower_set = {s.lower() for s in physical_inputs}
            if current_source_lower not in physical_inputs_lower_set:
                # Add current source (preserves original casing)
                physical_inputs.append(current_source)
                _LOGGER.debug(
                    "Added current source '%s' to available_sources (not in physical inputs, currently active) for %s",
                    current_source,
                    self.player.host,
                )

        # Remove duplicates while preserving order
        all_sources = list(dict.fromkeys(physical_inputs))

        # Final filtering against device capability database if available
        # This ensures that even if firmware reports incorrect inputs in plm_support
        # or input_list, we only show what the hardware actually supports.
        vendor = self.player.client.capabilities.get("vendor", "").lower() if self.player.client else None
        device_info = get_device_inputs(self.player._device_info.model, vendor)
        if device_info and device_info.inputs:
            # Build authoritative set of allowed inputs from database
            allowed_inputs = {s.lower() for s in device_info.inputs}

            # Always allow the "Network" mode (internal name "wifi") and current source
            # Every WiiM/LinkPlay device supports network streaming
            allowed_inputs.update({"wifi", "network"})

            if current_source:
                allowed_inputs.add(current_source.lower())

            # Streaming services are always allowed (they are added later or already present)
            allowed_inputs.update(streaming_services)

            filtered_sources = []
            for s in all_sources:
                s_lower = s.lower()
                # Normalize transport variations for the filtering check
                # e.g., "ethernet" or "wi-fi" should be checked as "wifi" if not explicitly allowed
                if s_lower in ("ethernet", "wi-fi"):
                    check_val = "wifi"
                else:
                    check_val = s_lower

                if s_lower in allowed_inputs or check_val in allowed_inputs:
                    filtered_sources.append(s)
                elif any(svc in s_lower for svc in streaming_services):
                    filtered_sources.append(s)

            all_sources = filtered_sources

        # Always include WiFi/Ethernet as it's always available (network connection)
        # Users can select it to switch to network mode
        all_sources_lower = {s.lower() for s in all_sources}
        if "wifi" not in all_sources_lower and "ethernet" not in all_sources_lower:
            all_sources.append("wifi")

        # Normalize source names to Title Case format to match source property
        # This ensures Home Assistant validation works correctly (current source matches available_sources)
        normalized_sources = []
        for source in all_sources:
            normalized_sources.append(self._normalize_source_name(source))

        return normalized_sources

    def _catalog_source_key(self, source_name: str) -> str:
        """Normalize a source display name to canonical key."""
        source_lower = source_name.strip().lower()
        if not source_lower:
            return ""

        # Direct mappings for UI display names
        direct_map = {
            "network": "network",
            "wifi": "network",
            "wi-fi": "network",
            "ethernet": "network",
            "line in": "line_in",
            "line in 2": "line_in_2",
            "aux in": "aux",
            "optical in": "optical",
            "coaxial": "coaxial",
            "usb": "usb",
            "hdmi": "hdmi",
            "phono": "phono",
            "rca": "rca",
            "airplay": "airplay",
            "spotify": "spotify",
            "amazon music": "amazon",
            "amazon": "amazon",
            "tidal": "tidal",
            "qobuz": "qobuz",
            "deezer": "deezer",
            "pandora": "pandora",
            "tunein": "tunein",
            "iheartradio": "iheartradio",
            "dlna": "dlna",
            "bluetooth": "bluetooth",
        }
        if source_lower in direct_map:
            return direct_map[source_lower]

        # Fallback: alphanumeric simplification for resilient matching
        simple = "".join(ch for ch in source_lower if ch.isalnum())
        simple_map = {
            "linein": "line_in",
            "linein2": "line_in_2",
            "auxin": "aux",
            "opticalin": "optical",
            "coaxialin": "coaxial",
            "amazonmusic": "amazon",
            "iheartradio": "iheartradio",
            "airplay": "airplay",
        }
        if simple in simple_map:
            return simple_map[simple]

        return source_lower.replace(" ", "_").replace("-", "_")

    def _catalog_source_kind(self, source_key: str) -> str:
        """Return catalog kind for a canonical source key."""
        if source_key in _HARDWARE_SOURCE_KEYS:
            return "hardware_input"
        if any(source_key == known_key for known_key, _ in _KNOWN_SERVICE_SOURCES):
            return "service"
        return "virtual"

    def _catalog_entry(self, source_id: str, name: str, is_current: bool) -> dict[str, Any]:
        """Build source catalog entry with capability flags."""
        kind = self._catalog_source_kind(source_id)
        selectable = kind == "hardware_input"

        # Apply capability-driven selectability overrides for known device quirks.
        blocked_ids: set[str] = set()
        if self.player.client:
            raw_blocked = self.player.client.capabilities.get("non_selectable_source_ids", [])
            if isinstance(raw_blocked, list):
                blocked_ids = {str(item).lower() for item in raw_blocked}
        if source_id.lower() in blocked_ids:
            selectable = False

        # Keep unknown/virtual source capabilities conservative in the catalog.
        capabilities = get_source_capabilities(source_id) if kind != "virtual" else SourceCapability.NONE

        return {
            "id": source_id,
            "name": name,
            "kind": kind,
            "selectable": selectable,
            "is_current": is_current,
            "supports_pause": capabilities != SourceCapability.NONE,
            "supports_seek": SourceCapability.SEEK in capabilities,
            "supports_next_track": SourceCapability.NEXT_TRACK in capabilities,
            "supports_previous_track": SourceCapability.PREVIOUS_TRACK in capabilities,
            "supports_shuffle": SourceCapability.SHUFFLE in capabilities,
            "supports_repeat": SourceCapability.REPEAT in capabilities,
        }

    @property
    def source_catalog(self) -> list[dict[str, Any]]:
        """Structured source catalog for integrations.

        Returns a normalized list of source entries with:
        - Stable `id` and display `name`
        - `kind` classification (hardware_input, service, virtual)
        - `selectable` flag for direct source switching
        - Source capability flags (pause/seek/next/previous/shuffle/repeat)
        - `is_current` marker for the active source
        """
        if self.player._device_info is None:
            return []

        catalog: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        current_id = self.source
        current_key = current_id if current_id else None

        # Start with device-available sources (hardware + active source).
        for source_name in self.available_sources:
            source_id = self._catalog_source_key(source_name)
            if not source_id or source_id in seen_ids:
                continue
            entry = self._catalog_entry(
                source_id=source_id,
                name=source_name,
                is_current=current_key == source_id,
            )
            catalog.append(entry)
            seen_ids.add(source_id)

        # Append known service/protocol sources for integrations like Music Assistant.
        for source_id, source_name in _KNOWN_SERVICE_SOURCES:
            if source_id in seen_ids:
                continue
            entry = self._catalog_entry(
                source_id=source_id,
                name=source_name,
                is_current=current_key == source_id,
            )
            # Service/protocol sources are not directly selectable by this source list.
            entry["selectable"] = False
            catalog.append(entry)
            seen_ids.add(source_id)

        return catalog

    @property
    def audio_output_mode(self) -> str | None:
        """Current audio output mode as friendly name."""
        if self.player._audio_output_status is None:
            return None

        hardware_mode = self.player._audio_output_status.get("hardware")
        if hardware_mode is None:
            return None

        source = self.player._audio_output_status.get("source")

        # Special handling for mode 4 on WiiM Ultra (Issue #86)
        # For Ultra: hardware=4 with source=0 = Headphone Out, source=1 = Bluetooth Out
        try:
            mode_int = int(hardware_mode) if isinstance(hardware_mode, str) else hardware_mode

            # Bluetooth Out via source field (takes precedence over hardware mode)
            if source == 1 or source == "1":
                return "Bluetooth Out"

            # Special handling for mode 4 on WiiM Ultra (headphone output is ONLY on Ultra)
            if mode_int == 4:
                # Check if device is Ultra - headphone output is only available on Ultra
                # Use lenient check: "ultra" in model name (matches available_output_modes logic)
                model = None
                if self.player._device_info:
                    model = self.player._device_info.model

                # Check if it's an Ultra device (lenient check - just "ultra" in model name)
                is_ultra = False
                if model:
                    model_lower = model.lower()
                    is_ultra = "ultra" in model_lower

                if is_ultra:
                    # On Ultra: hardware=4 with source=0 = Headphone Out
                    if source == 0 or source == "0":
                        return "Headphone Out"
                    # If source != 0, fall through to default "Bluetooth Out"
                # If not Ultra, mode 4 is just Bluetooth Out (fall through to mapping)

            # Map hardware mode to friendly name
            mode_name = self.player.client.audio_output_mode_to_name(mode_int)
            if mode_name is not None:
                return mode_name

            # If mode is not in map, log warning and return None
            model = self.player._device_info.model if self.player._device_info else None
            _LOGGER.warning(
                "Unknown audio output mode %s (hardware=%s, source=%s) for device %s (model=%s)",
                mode_int,
                hardware_mode,
                source,
                self.player.host,
                model or "unknown",
            )
            return None
        except (ValueError, TypeError) as e:
            _LOGGER.warning(
                "Failed to parse audio output mode (hardware=%s, source=%s) for device %s: %s",
                hardware_mode,
                source,
                self.player.host,
                e,
            )
            return None

    @property
    def audio_output_mode_int(self) -> int | None:
        """Current audio output mode as integer."""
        if self.player._audio_output_status is None:
            return None

        source = self.player._audio_output_status.get("source")
        if source == 1 or source == "1":
            return 4

        hardware_mode = self.player._audio_output_status.get("hardware")
        if hardware_mode is None:
            return None

        try:
            return int(hardware_mode) if isinstance(hardware_mode, str) else hardware_mode
        except (ValueError, TypeError):
            return None

    @property
    def available_output_modes(self) -> list[str]:
        """Available audio output modes for this device.

        Note: This returns hardware output modes only. Bluetooth output is handled
        separately via specific BT devices from history - "Bluetooth Out" is never
        included as it's not a hardware mode the device provides.
        """
        if not self.player.client.capabilities.get("supports_audio_output", False):
            return []

        model = None
        if self.player._device_info:
            model = self.player._device_info.model

        if not model:
            return ["Line Out", "Optical Out", "Coax Out"]

        model_lower = model.lower()

        # Check for specific models (order matters - check more specific first)
        # IMPORTANT: Check "amp ultra"/"amp pro" BEFORE "amp" to avoid false matches
        if "amp ultra" in model_lower or ("ultra" in model_lower and "amp" in model_lower):
            # WiiM Amp Ultra: Has USB Out, HDMI Out (ARC), but no Headphone Out
            return ["Line Out", "USB Out", "HDMI Out"]
        elif "ultra" in model_lower:
            # WiiM Ultra (non-Amp): Has USB Out, Headphone Out, multiple digital outputs
            # Note: HDMI on WiiM Ultra is INPUT only (not output) - confirmed via Issue #160
            return ["Line Out", "Optical Out", "Coax Out", "USB Out", "Headphone Out"]
        elif "amp pro" in model_lower or ("pro" in model_lower and "amp" in model_lower):
            # WiiM Amp Pro: Has USB Out
            return ["Line Out", "USB Out"]
        elif "wiim amp" in model_lower or ("amp" in model_lower and "wiim" in model_lower):
            # WiiM Amp (standard): Has USB Out
            return ["Line Out", "USB Out"]
        elif "wiim mini" in model_lower or ("mini" in model_lower and "wiim" in model_lower):
            return ["Line Out", "Optical Out"]
        elif "wiim pro" in model_lower or ("pro" in model_lower and "wiim" in model_lower):
            return ["Line Out", "Optical Out", "Coax Out"]
        elif "wiim" in model_lower:
            # Generic WiiM device (fallback)
            return ["Line Out", "Optical Out", "Coax Out"]
        else:
            return ["Line Out", "Optical Out", "Coax Out"]

    @property
    def is_bluetooth_output_active(self) -> bool:
        """Check if Bluetooth output is currently active."""
        if self.player._audio_output_status is None:
            return False

        source = self.player._audio_output_status.get("source")
        return source == 1

    @property
    def bluetooth_output_devices(self) -> list[dict[str, str]]:
        """Get paired Bluetooth output devices (Audio Sinks only).

        Returns:
            List of dicts with keys:
            - name: Device name
            - mac: MAC address (normalized from 'ad' field)
            - connected: Boolean indicating if currently connected

        Example:
            [
                {"name": "Sony SRS-XB43", "mac": "AA:BB:CC:DD:EE:FF", "connected": True},
                {"name": "JBL Tune 750", "mac": "11:22:33:44:55:66", "connected": False}
            ]
        """
        if not self.player._bluetooth_history:
            return []

        output_devices = []
        for device in self.player._bluetooth_history:
            # Only include Audio Sink devices (output devices, not input sources)
            role = device.get("role", "")
            if "Audio Sink" not in role:
                continue

            output_devices.append(
                {
                    "name": device.get("name", "Unknown Device"),
                    "mac": device.get("ad", ""),  # API uses 'ad' not 'mac'
                    "connected": device.get("ct") == 1,
                }
            )

        return output_devices

    @property
    def available_outputs(self) -> list[str]:
        """Get all available outputs including hardware modes and paired BT devices.

        This combines hardware output modes (Line Out, Optical, etc.) with
        already paired Bluetooth output devices for a unified selection list.

        The generic "Bluetooth Out" option is never shown - only specific
        paired Bluetooth devices from history are included.

        Returns:
            List of output names. Bluetooth devices are prefixed with "BT: "

        Example:
            [
                "Line Out",
                "Optical Out",
                "Coax Out",
                "BT: Sony SRS-XB43",
                "BT: JBL Tune 750"
            ]
        """
        outputs = []

        # Get hardware output modes (doesn't include "Bluetooth Out" - only specific BT devices shown)
        hardware_modes = self.available_output_modes.copy()

        # Get paired Bluetooth output devices
        bt_devices = self.bluetooth_output_devices

        # Add hardware output modes
        outputs.extend(hardware_modes)

        # Add paired Bluetooth output devices
        for device in bt_devices:
            outputs.append(f"BT: {device['name']}")

        return outputs

    # === UPnP Health ===

    @property
    def upnp_health_status(self) -> dict[str, Any] | None:
        """UPnP event health statistics.

        Returns health tracking information if UPnP is enabled, None otherwise.

        Returns:
            Dictionary with health statistics:
            - is_healthy: bool - Whether UPnP events are working properly
            - miss_rate: float - Fraction of changes missed (0.0-1.0)
            - detected_changes: int - Total changes detected by polling
            - missed_changes: int - Changes polling saw but UPnP didn't
            - has_enough_samples: bool - Whether enough data for reliable health assessment

            None if UPnP is not enabled or health tracker not available.
        """
        if not self.player._upnp_health_tracker:
            return None
        return self.player._upnp_health_tracker.statistics

    @property
    def upnp_is_healthy(self) -> bool | None:
        """Whether UPnP events are working properly.

        Returns:
            True if UPnP is healthy, False if degraded/failed, None if UPnP not enabled.
        """
        if not self.player._upnp_health_tracker:
            return None
        return self.player._upnp_health_tracker.is_healthy

    @property
    def upnp_miss_rate(self) -> float | None:
        """UPnP event miss rate (0.0 = perfect, 1.0 = all missed).

        Returns:
            Fraction of changes missed by UPnP (0.0 to 1.0), or None if UPnP not enabled.
        """
        if not self.player._upnp_health_tracker:
            return None
        return self.player._upnp_health_tracker.miss_rate

    # === Device Capabilities ===
    # These properties expose device capabilities for integrations (e.g., Home Assistant)
    # to check feature support before calling methods. Follows SoCo pattern.

    @property
    def supports_eq(self) -> bool:
        """Whether EQ control is supported."""
        if not self.player.client:
            return False
        return bool(self.player.client.capabilities.get("supports_eq", False))

    @property
    def supports_channel_balance(self) -> bool:
        """Whether stereo channel balance (getChannelBalance / setChannelBalance) is supported.

        Detected at connect time for WiiM devices only (read-only HTTP probe).
        """
        if not self.player.client:
            return False
        return bool(self.player.client.capabilities.get("supports_channel_balance", False))

    @property
    def supports_presets(self) -> bool:
        """Whether preset/favorites are supported."""
        if not self.player.client:
            return False
        return bool(self.player.client.capabilities.get("supports_presets", False))

    @property
    def presets_full_data(self) -> bool:
        """Whether preset names/URLs are available (WiiM devices) or only count (LinkPlay devices).

        Returns:
            True if getPresetInfo works (WiiM devices) - can read preset names, URLs, etc.
            False if only preset_key available (LinkPlay devices) - only count available via get_max_preset_slots().
        """
        if not self.player.client:
            return False
        return bool(self.player.client.capabilities.get("presets_full_data", False))

    @property
    def supports_audio_output(self) -> bool:
        """Whether audio output mode control is supported."""
        if not self.player.client:
            return False
        return bool(self.player.client.capabilities.get("supports_audio_output", False))

    @property
    def supports_metadata(self) -> bool:
        """Whether metadata retrieval (getMetaInfo) is supported."""
        if not self.player.client:
            return False
        return bool(self.player.client.capabilities.get("supports_metadata", False))

    @property
    def supports_alarms(self) -> bool:
        """Whether alarm clock feature is supported."""
        if not self.player.client:
            return False
        return bool(self.player.client.capabilities.get("supports_alarms", False))

    @property
    def supports_sleep_timer(self) -> bool:
        """Whether sleep timer feature is supported."""
        if not self.player.client:
            return False
        return bool(self.player.client.capabilities.get("supports_sleep_timer", False))

    @property
    def supports_firmware_install(self) -> bool:
        """Whether firmware update installation via API is supported (WiiM devices only)."""
        if not self.player.client:
            return False
        return bool(self.player.client.capabilities.get("supports_firmware_install", False))

    @property
    def supports_led_control(self) -> bool:
        """Whether LED control is supported (primary setLED/setLEDBrightness API)."""
        if not self.player.client:
            return False
        return bool(self.player.client.capabilities.get("supports_led_control", False))

    @property
    def supports_led_switch(self) -> bool:
        """Whether Status Light (LED_SWITCH_SET) is supported.

        Use when primary LED control does not work; e.g. for app 'Status Light' toggle.
        """
        if not self.player.client:
            return False
        return bool(self.player.client.capabilities.get("supports_led_switch", False))

    @property
    def supports_led_indicator(self) -> bool:
        """Whether LED indicator on/off is supported (ADR 005; Arylic + WiiM via probe)."""
        if not self.player.client:
            return False
        return bool(self.player.client.capabilities.get("supports_led_switch", False))

    @property
    def supports_display_config(self) -> bool:
        """Whether display/LCD on-off and brightness is supported (WiiM Ultra only)."""
        if not self.player.client:
            return False
        return bool(self.player.client.capabilities.get("supports_display_config", False))

    # === UPnP Capabilities ===
    # These are determined at runtime based on UPnP client initialization

    @property
    def supports_upnp(self) -> bool:
        """Whether UPnP client is available for events and transport control."""
        return self.player._upnp_client is not None

    @property
    def supports_queue_browse(self) -> bool:
        """Whether full queue retrieval is available (UPnP ContentDirectory).

        Only available on WiiM Amp and Ultra when a USB drive is connected.
        Most WiiM devices (Mini, Pro, Pro Plus) do not support this.
        """
        if not self.player._upnp_client:
            return False
        return self.player._upnp_client.content_directory is not None

    @property
    def supports_queue_add(self) -> bool:
        """Whether adding items to queue is supported (UPnP AVTransport).

        Available on most devices with UPnP support.
        """
        if not self.player._upnp_client:
            return False
        return self.player._upnp_client.av_transport is not None

    @property
    def supports_queue_count(self) -> bool:
        """Whether queue count/position is available (HTTP API).

        Always True - available via plicount/plicurr in getPlayerStatus.
        """
        return True
