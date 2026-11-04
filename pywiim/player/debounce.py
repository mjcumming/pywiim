"""Play state debouncing to smooth track changes."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import Player

_LOGGER = logging.getLogger(__name__)


class PlayStateDebouncer:
    """Debounces play state transitions to smooth track changes.

    During track changes, devices often report STOPPED/PAUSED briefly between tracks.
    This debouncer delays applying these interruption states, allowing play transitions
    to cancel them if playback resumes quickly (indicating a track change, not a pause).
    """

    def __init__(self, player: Player, delay: float = 0.5) -> None:
        """Initialize play state debouncer.

        Args:
            player: Parent Player instance.
            delay: Delay in seconds before applying interrupted states (default: 0.5).
        """
        self.player = player
        self.delay = delay
        self._pending_task: asyncio.Task | None = None

    def schedule_state_change(self, new_state: str) -> None:
        """Schedule a delayed update to play state (pause/stop/buffering).

        This debounces the 'stop' or 'buffering' events that occur during track changes.
        If playback resumes before the delay expires, the pending state change is cancelled.

        Args:
            new_state: The play state to apply after delay (pause, stop, idle, or buffering).
        """
        # Cancel any existing pending task
        if self._pending_task and not self._pending_task.done():
            self._pending_task.cancel()

        try:
            loop = asyncio.get_event_loop()
            pending = self._apply_delayed_state(new_state)
            try:
                self._pending_task = loop.create_task(pending)
            except RuntimeError:
                pending.close()
                raise
        except RuntimeError:
            # No event loop (sync context) - apply immediately
            _LOGGER.debug("No event loop available, applying state immediately: %s", new_state)
            self.player._state_synchronizer.update_from_upnp({"play_state": new_state})

    def cancel_pending(self) -> bool:
        """Cancel pending state change (called when play resumes).

        Returns:
            True if a pending task was cancelled, False otherwise.
        """
        if self._pending_task and not self._pending_task.done():
            self._pending_task.cancel()
            self._pending_task = None
            _LOGGER.debug("Cancelled pending state update (play resumed)")
            return True
        return False

    async def _apply_delayed_state(self, new_state: str) -> None:
        """Apply play state after delay."""
        try:
            # Wait for delay - typical track change stop is < 100ms, but buffering can take longer
            await asyncio.sleep(self.delay)

            # If we get here, the timer expired without being cancelled by a "Play" event
            _LOGGER.debug("Debounce timer expired, applying delayed state: %s", new_state)

            self.player._state_synchronizer.update_from_upnp({"play_state": new_state})

            # Force update of cached model
            merged = self.player._state_synchronizer.get_merged_state()
            if self.player._status_model and "play_state" in merged:
                self.player._status_model.play_state = merged["play_state"]

            # Trigger callback
            if self.player._on_state_changed:
                try:
                    self.player._on_state_changed()
                except Exception as err:
                    _LOGGER.debug("Error in callback after delayed state update: %s", err)

        except asyncio.CancelledError:
            # Task cancelled - track change confirmed (Play -> Interruption -> Play)
            pass
        except Exception as e:
            _LOGGER.error("Error in delayed state task: %s", e)
        finally:
            self._pending_task = None
