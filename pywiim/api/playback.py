"""Playback and volume helpers for WiiM HTTP client.

All networking (`_request`) and logging are supplied by the base client.
This mix-in must therefore be inherited **before** the base client in the final MRO.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import quote

from .constants import (
    API_ENDPOINT_AUDIO_OUTPUT_SET,
    API_ENDPOINT_AUDIO_OUTPUT_STATUS,
    API_ENDPOINT_CLEAR_PLAYLIST,
    API_ENDPOINT_LOOPMODE,
    API_ENDPOINT_MUTE,
    API_ENDPOINT_NEXT,
    API_ENDPOINT_PAUSE,
    API_ENDPOINT_PLAY,
    API_ENDPOINT_PLAY_M3U,
    API_ENDPOINT_PLAY_PROMPT_URL,
    API_ENDPOINT_PLAY_URL,
    API_ENDPOINT_PREV,
    API_ENDPOINT_RESUME,
    API_ENDPOINT_SEEK,
    API_ENDPOINT_SOURCE,
    API_ENDPOINT_STOP,
    API_ENDPOINT_VOLUME,
    AUDIO_OUTPUT_MODE_MAP,
    AUDIO_OUTPUT_MODE_NAME_TO_INT,
)

_LOGGER = logging.getLogger(__name__)


class PlaybackAPI:
    """Transport-level playback controls (play, volume, seek, …).

    This mixin provides methods for controlling playback, volume, mute,
    source selection, and playlist management.
    """

    # ------------------------------------------------------------------
    # Core transport helpers
    # ------------------------------------------------------------------

    async def play(self) -> None:
        """Start playback.

        Raises:
            WiiMError: If the request fails.
        """
        await self._request(API_ENDPOINT_PLAY)  # type: ignore[attr-defined]

    async def pause(self) -> None:
        """Pause playback.

        Raises:
            WiiMError: If the request fails.
        """
        await self._request(API_ENDPOINT_PAUSE)  # type: ignore[attr-defined]

    async def resume(self) -> None:
        """Resume playback from paused state.

        Raises:
            WiiMError: If the request fails.
        """
        await self._request(API_ENDPOINT_RESUME)  # type: ignore[attr-defined]

    async def stop(self) -> None:
        """Stop playback.

        Raises:
            WiiMError: If the request fails.
        """
        await self._request(API_ENDPOINT_STOP)  # type: ignore[attr-defined]

    async def next_track(self) -> None:
        """Skip to next track.

        Raises:
            WiiMError: If the request fails.
        """
        await self._request(API_ENDPOINT_NEXT)  # type: ignore[attr-defined]

    async def previous_track(self) -> None:
        """Skip to previous track.

        Raises:
            WiiMError: If the request fails.
        """
        await self._request(API_ENDPOINT_PREV)  # type: ignore[attr-defined]

    async def seek(self, position: int) -> None:
        """Seek to *position* (seconds).

        Args:
            position: Position in seconds to seek to.

        Raises:
            WiiMError: If the request fails.
        """
        await self._request(f"{API_ENDPOINT_SEEK}{position}")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Volume / mute
    # ------------------------------------------------------------------

    async def set_volume(self, volume: float) -> None:
        """Set absolute volume (0.0 – 1.0).

        Args:
            volume: Volume level from 0.0 (muted) to 1.0 (maximum).

        Raises:
            WiiMError: If the request fails.
        """
        vol_pct = int(max(0.0, min(volume, 1.0)) * 100)
        endpoint = f"{API_ENDPOINT_VOLUME}{vol_pct}"
        _LOGGER.info("Sending volume API request: %s to %s (%.0f%%)", endpoint, self._host, vol_pct)  # type: ignore[attr-defined]
        try:
            result = await self._request(endpoint)  # type: ignore[attr-defined]
            _LOGGER.debug("Volume API request successful: %s", result.parsed or result.raw)
        except Exception as err:
            _LOGGER.error(
                "Volume API request failed: %s to %s: %s (type: %s)",
                endpoint,
                self._host,  # type: ignore[attr-defined]
                err,
                type(err).__name__,
                exc_info=True,
            )
            raise

    async def set_mute(self, mute: bool) -> None:
        """Set mute state.

        Args:
            mute: True to mute, False to unmute.

        Raises:
            WiiMError: If the request fails.
        """
        await self._request(f"{API_ENDPOINT_MUTE}{1 if mute else 0}")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Loop mode (shuffle/repeat combined)
    # ------------------------------------------------------------------

    async def set_loop_mode(self, mode: int) -> None:
        """Set loop mode using device's loopmode command.

        Loop mode values are vendor-specific:
        - WiiM: 0=loop_all, 1=repeat_one, 2=shuffle_loop, 3=shuffle_no_loop, 4=normal
        - Arylic: 0=repeat_all, 1=repeat_one, 2=shuffle_repeat_all, 3=shuffle, 4=normal, 5=shuffle_repeat_one

        Use pywiim.api.loop_mode.get_loop_mode_mapping() for vendor-specific mappings.

        Args:
            mode: Loop mode value (vendor-specific, typically 0-6).

        Raises:
            ValueError: If mode is negative or unreasonably large.
            WiiMError: If the request fails.
        """
        # Accept all reasonable loop mode values (vendor-specific)
        # WiiM uses 0-4, Arylic uses 0-5, legacy bitfield uses 0,1,2,4,5,6
        if mode < 0 or mode > 10:
            raise ValueError(f"Invalid loop mode: {mode}. Valid range: 0-10")
        await self._request(f"{API_ENDPOINT_LOOPMODE}{mode}")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Source selection
    # ------------------------------------------------------------------

    async def set_source(self, source: str) -> None:
        """Set audio source using WiiM's switchmode command.

        Args:
            source: Source to switch to (e.g., "wifi", "bluetooth", "line_in", "optical").

        Raises:
            WiiMError: If the request fails.
        """
        await self._request(f"{API_ENDPOINT_SOURCE}{source}")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Audio Output Control
    # ------------------------------------------------------------------

    async def get_audio_output_status(self) -> dict[str, Any] | None:
        """Get current audio output status including Bluetooth output mode.

        Returns:
            dict with keys: hardware, source, audiocast if supported, None if not supported
            - hardware: Hardware output mode (0=Line Out, 1=Optical Out, 2=Line Out, 3=Coax Out, 4=Bluetooth Out)
            - source: Bluetooth output mode (0=disabled, 1=active)
            - audiocast: Audio cast mode (0=disabled, 1=active)

        Note:
            Returns None if the endpoint is not supported or fails.
        """
        try:
            result = await self._request(API_ENDPOINT_AUDIO_OUTPUT_STATUS)  # type: ignore[attr-defined]
            return result.parsed if isinstance(result.parsed, dict) else None
        except Exception as e:
            # Log with more details for first few failures
            if not hasattr(self, "_audio_output_error_count"):
                self._audio_output_error_count = 0
            self._audio_output_error_count += 1

            # Log first 5 failures with full details, then throttle
            if self._audio_output_error_count <= 5:
                _LOGGER.warning(
                    "%s: Audio output API call failed (attempt %d), error type: %s, error: %s",
                    self.host,  # type: ignore[attr-defined]
                    self._audio_output_error_count,
                    type(e).__name__,
                    str(e),
                )
            elif self._audio_output_error_count % 10 == 1:
                _LOGGER.debug(
                    "%s: Audio output API still failing (%d consecutive failures)",
                    self.host,  # type: ignore[attr-defined]
                    self._audio_output_error_count,
                )
            return None

    async def set_audio_output_hardware_mode(self, mode: int) -> None:
        """Set hardware audio output mode.

        Args:
            mode: Hardware output mode integer (0=Line Out, 1=Optical Out, 2=Line Out, 3=Coax Out, 4=Bluetooth Out).

        Raises:
            WiiMError: If the request fails.
        """
        await self._request(f"{API_ENDPOINT_AUDIO_OUTPUT_SET}{mode}")  # type: ignore[attr-defined]

    def audio_output_mode_to_name(self, mode: int | None) -> str | None:
        """Convert audio output mode integer to friendly name.

        Args:
            mode: Hardware output mode integer (0-4) or None.

        Returns:
            Friendly name string (e.g., "Line Out", "Optical Out") or None if mode is None or invalid.
        """
        if mode is None:
            return None
        return AUDIO_OUTPUT_MODE_MAP.get(mode)

    def audio_output_name_to_mode(self, name: str) -> int | None:
        """Convert friendly name to audio output mode integer.

        Args:
            name: Friendly name string (e.g., "Line Out", "Optical Out", "Bluetooth Out").
                Case-insensitive, accepts variations like "coax", "coaxial", "optical", etc.

        Returns:
            Mode integer (0-4) or None if name is not recognized.
        """
        if not name:
            return None
        name_lower = name.lower().strip()
        return AUDIO_OUTPUT_MODE_NAME_TO_INT.get(name_lower)

    async def set_audio_output_mode(self, mode: str | int) -> None:
        """Set audio output mode by friendly name or integer.

        This is a convenience method that accepts either a friendly name string
        (e.g., "Line Out", "Optical Out") or a mode integer (0-4).

        Args:
            mode: Either a friendly name string or mode integer (0-4).

        Raises:
            ValueError: If mode string is not recognized.
            WiiMError: If the request fails.

        Example:
            ```python
            # Using friendly name
            await client.set_audio_output_mode("Line Out")
            await client.set_audio_output_mode("Optical Out")
            await client.set_audio_output_mode("Bluetooth Out")

            # Using integer
            await client.set_audio_output_mode(0)  # Line Out
            await client.set_audio_output_mode(1)  # Optical Out
            ```
        """
        if isinstance(mode, str):
            mode_int = self.audio_output_name_to_mode(mode)
            if mode_int is None:
                raise ValueError(
                    f"Unknown audio output mode: {mode!r}. "
                    f"Valid names: {', '.join(sorted(set(AUDIO_OUTPUT_MODE_MAP.values())))}"
                )
            await self.set_audio_output_hardware_mode(mode_int)
        elif isinstance(mode, int):
            if mode not in AUDIO_OUTPUT_MODE_MAP:
                raise ValueError(
                    f"Invalid audio output mode: {mode}. Valid modes: {list(AUDIO_OUTPUT_MODE_MAP.keys())}"
                )
            await self.set_audio_output_hardware_mode(mode)
        else:
            raise TypeError(f"Mode must be str or int, got {type(mode).__name__}")

    # ------------------------------------------------------------------
    # Playlist helpers
    # ------------------------------------------------------------------

    async def clear_playlist(self) -> None:
        """Clear the current playlist.

        Raises:
            WiiMError: If the request fails.
        """
        await self._request(API_ENDPOINT_CLEAR_PLAYLIST)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # URL playback helpers – preserved for automation convenience
    # ------------------------------------------------------------------

    async def play_url(self, url: str) -> None:
        """Play a URL directly.

        Note: This is a fire-and-forget API. The device accepts URLs without
        validation - invalid, unreachable, or non-audio URLs won't cause errors.
        The device attempts playback asynchronously and may end up in 'pause'
        or 'idle' state if playback fails.

        Args:
            url: URL to play (http/https to audio file or stream).

        Raises:
            WiiMError: If the HTTP request to the device fails (network error).
                Does NOT raise for invalid/unreachable media URLs.
        """
        encoded = quote(url, safe="")
        await self._request(f"{API_ENDPOINT_PLAY_URL}{encoded}")  # type: ignore[attr-defined]

    async def play_playlist(self, playlist_url: str) -> None:
        """Play a playlist (M3U) URL.

        Args:
            playlist_url: URL to M3U playlist file.

        Raises:
            WiiMError: If the request fails.
        """
        encoded = quote(playlist_url, safe="")
        await self._request(f"{API_ENDPOINT_PLAY_M3U}{encoded}")  # type: ignore[attr-defined]

    async def play_notification(self, url: str) -> None:
        """Play a notification sound from URL.

        This uses the device's playPromptUrl command which automatically
        lowers the current playback volume, plays the notification,
        and restores volume afterwards.

        Note: Only works in NETWORK or USB playback mode.

        Args:
            url: URL to notification audio file.

        Raises:
            WiiMError: If the request fails.
        """
        encoded = quote(url, safe="")
        await self._request(f"{API_ENDPOINT_PLAY_PROMPT_URL}{encoded}")  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Metadata helper (used by media-image caching)
    # ------------------------------------------------------------------

    async def get_meta_info(self) -> dict[str, Any]:
        """Retrieve current track metadata.

        Not all firmware supports this call – returns an empty dict when the
        endpoint is missing or replies with the old plain-text "unknown
        command" response.

        Returns:
            Dictionary containing metadata, or empty dict if not supported.
        """
        try:
            resp = await self._request("/httpapi.asp?command=getMetaInfo")  # type: ignore[attr-defined]
            if resp.raw and str(resp.raw).lower().startswith("unknown command"):
                return {}
            if isinstance(resp.parsed, dict) and "metaData" in resp.parsed:
                return {"metaData": resp.parsed["metaData"]}
            return {}
        except Exception:  # noqa: BLE001 – older firmware returns plain text
            return {}

    # ------------------------------------------------------------------
    # Convenience: repeat/shuffle status check (non-blocking)
    # ------------------------------------------------------------------

    async def _verify_play_mode(self) -> None:
        """Verify play mode by checking player status (non-blocking best-effort)."""
        try:
            await asyncio.sleep(0.5)
            await self.get_player_status()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 – best-effort only
            pass
