"""Playback control - shuffle, repeat, loop modes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..exceptions import WiiMError

if TYPE_CHECKING:
    from . import Player


class PlaybackControl:
    """Manages playback mode operations."""

    def __init__(self, player: Player) -> None:
        """Initialize playback control.

        Args:
            player: Parent Player instance.
        """
        self.player = player

    async def set_shuffle(self, enabled: bool) -> None:
        """Set shuffle mode on or off, preserving current repeat state.

        Args:
            enabled: True to enable shuffle, False to disable.

        Raises:
            WiiMError: If shuffle cannot be controlled on current source.
        """
        import time

        from ..api.loop_mode import resolve_loop_mode_mapping_for_player
        from .properties import PlayerProperties

        props = PlayerProperties(self.player)

        # Check if shuffle is supported for current source
        if not props.shuffle_supported:
            source = props.source or "unknown"
            raise WiiMError(
                f"Shuffle cannot be controlled when playing from '{source}'. "
                f"Shuffle is controlled by the source device/app, not the WiiM device. "
                f"Supported sources: USB, Line In, Optical, Coaxial, Playlist, Preset."
            )

        mapping = resolve_loop_mode_mapping_for_player(self.player)

        # Get current repeat state
        repeat_mode = props.repeat_mode
        is_repeat_one = repeat_mode == "one"
        is_repeat_all = repeat_mode == "all"

        # Calculate new loop_mode using vendor mapping
        loop_mode = mapping.to_loop_mode(shuffle=enabled, repeat_one=is_repeat_one, repeat_all=is_repeat_all)

        # Call API (raises on failure)
        await self.player.client.set_loop_mode(loop_mode)

        # Update cached state immediately (optimistic)
        if self.player._status_model:
            self.player._status_model.loop_mode = loop_mode

        # Track when loop_mode was set for preserving optimistic update during refresh
        self.player._last_loop_mode_set_time = time.time()

        # Call callback to notify state change
        if self.player._on_state_changed:
            self.player._on_state_changed()

    async def set_repeat(self, mode: str) -> None:
        """Set repeat mode, preserving current shuffle state.

        Args:
            mode: Repeat mode - "off", "one", or "all".

        Raises:
            ValueError: If mode is not valid.
            WiiMError: If repeat cannot be controlled on current source.
        """
        import time

        mode_lower = mode.lower().strip()
        if mode_lower not in ("off", "one", "all"):
            raise ValueError(f"Invalid repeat mode: {mode}. Valid values: 'off', 'one', 'all'")

        from ..api.loop_mode import resolve_loop_mode_mapping_for_player
        from .properties import PlayerProperties

        props = PlayerProperties(self.player)

        # Check if repeat is supported for current source
        if not props.repeat_supported:
            source = props.source or "unknown"
            raise WiiMError(
                f"Repeat cannot be controlled when playing from '{source}'. "
                f"Repeat is controlled by the source device/app, not the WiiM device. "
                f"Supported sources: USB, Line In, Optical, Coaxial, Playlist, Preset."
            )

        mapping = resolve_loop_mode_mapping_for_player(self.player)

        # Get current shuffle state
        shuffle_enabled = props.shuffle_state or False

        # Calculate new loop_mode using vendor mapping
        is_repeat_one = mode_lower == "one"
        is_repeat_all = mode_lower == "all"
        loop_mode = mapping.to_loop_mode(shuffle=shuffle_enabled, repeat_one=is_repeat_one, repeat_all=is_repeat_all)

        # Call API (raises on failure)
        await self.player.client.set_loop_mode(loop_mode)

        # Update cached state immediately (optimistic)
        if self.player._status_model:
            self.player._status_model.loop_mode = loop_mode

        # Track when loop_mode was set for preserving optimistic update during refresh
        self.player._last_loop_mode_set_time = time.time()

        # Call callback to notify state change
        if self.player._on_state_changed:
            self.player._on_state_changed()
