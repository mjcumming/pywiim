"""Unit tests for PlayStateDebouncer.

Tests play state debouncing to smooth track changes.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestPlayStateDebouncer:
    """Test PlayStateDebouncer class."""

    @pytest.fixture
    def mock_player(self, mock_client):
        """Create a mock Player instance."""
        from pywiim.player import Player

        player = Player(mock_client)
        player._state_synchronizer = MagicMock()
        player._state_synchronizer.update_from_upnp = MagicMock()
        player._state_synchronizer.get_merged_state = MagicMock(return_value={"play_state": "pause"})
        player._status_model = MagicMock()
        player._on_state_changed = None
        return player

    @pytest.fixture
    def debouncer(self, mock_player):
        """Create a PlayStateDebouncer instance."""
        from pywiim.player.debounce import PlayStateDebouncer

        return PlayStateDebouncer(mock_player)

    def test_init(self, debouncer, mock_player):
        """Test PlayStateDebouncer initialization."""
        assert debouncer.player == mock_player
        assert debouncer.delay == 0.5
        assert debouncer._pending_task is None

    def test_init_custom_delay(self, mock_player):
        """Test PlayStateDebouncer initialization with custom delay."""
        from pywiim.player.debounce import PlayStateDebouncer

        debouncer = PlayStateDebouncer(mock_player, delay=1.0)
        assert debouncer.delay == 1.0

    @pytest.mark.asyncio
    async def test_schedule_state_change(self, debouncer, mock_player):
        """Test scheduling delayed update."""
        debouncer.delay = 0
        debouncer.schedule_state_change("pause")

        task = debouncer._pending_task
        assert isinstance(task, asyncio.Task)
        await task
        mock_player._state_synchronizer.update_from_upnp.assert_called_once_with({"play_state": "pause"})

    @pytest.mark.asyncio
    async def test_schedule_state_change_cancels_existing(self, debouncer, mock_player):
        """Test scheduling cancels existing pending task."""
        existing_task = MagicMock()
        existing_task.done.return_value = False
        debouncer._pending_task = existing_task

        debouncer.delay = 0
        debouncer.schedule_state_change("pause")

        existing_task.cancel.assert_called_once()
        task = debouncer._pending_task
        assert isinstance(task, asyncio.Task)
        await task
        mock_player._state_synchronizer.update_from_upnp.assert_called_once_with({"play_state": "pause"})

    def test_schedule_state_change_no_event_loop(self, debouncer, mock_player):
        """Test scheduling when no event loop."""
        with patch("asyncio.get_event_loop", side_effect=RuntimeError("No event loop")):
            debouncer.schedule_state_change("pause")

            # Should apply immediately
            mock_player._state_synchronizer.update_from_upnp.assert_called_once_with({"play_state": "pause"})

    def test_schedule_state_change_closed_event_loop(self, debouncer, mock_player):
        """Apply immediately without leaking the coroutine when the loop is closed."""
        loop = asyncio.new_event_loop()
        loop.close()
        with patch("asyncio.get_event_loop", return_value=loop):
            debouncer.schedule_state_change("pause")

        mock_player._state_synchronizer.update_from_upnp.assert_called_once_with({"play_state": "pause"})

    def test_cancel_pending(self, debouncer):
        """Test cancelling pending state change."""
        mock_task = MagicMock()
        mock_task.done.return_value = False
        debouncer._pending_task = mock_task

        result = debouncer.cancel_pending()

        assert result is True
        mock_task.cancel.assert_called_once()
        assert debouncer._pending_task is None

    def test_cancel_pending_no_task(self, debouncer):
        """Test cancelling when no pending task."""
        result = debouncer.cancel_pending()

        assert result is False

    def test_cancel_pending_task_done(self, debouncer):
        """Test cancelling when task already done."""
        mock_task = MagicMock()
        mock_task.done.return_value = True
        debouncer._pending_task = mock_task

        result = debouncer.cancel_pending()

        assert result is False
        mock_task.cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_delayed_state(self, debouncer, mock_player):
        """Test applying delayed state."""
        mock_player._state_synchronizer.get_merged_state.return_value = {"play_state": "pause"}

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await debouncer._apply_delayed_state("pause")

        mock_player._state_synchronizer.update_from_upnp.assert_called_once_with({"play_state": "pause"})
        assert debouncer._pending_task is None

    @pytest.mark.asyncio
    async def test_apply_delayed_state_updates_model(self, debouncer, mock_player):
        """Test applying delayed state updates cached model."""
        mock_player._state_synchronizer.get_merged_state.return_value = {"play_state": "pause"}

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await debouncer._apply_delayed_state("pause")

        assert mock_player._status_model.play_state == "pause"

    @pytest.mark.asyncio
    async def test_apply_delayed_state_triggers_callback(self, debouncer, mock_player):
        """Test applying delayed state triggers callback."""
        mock_player._state_synchronizer.get_merged_state.return_value = {"play_state": "pause"}
        mock_player._on_state_changed = MagicMock()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await debouncer._apply_delayed_state("pause")

        mock_player._on_state_changed.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_delayed_state_callback_error(self, debouncer, mock_player):
        """Test applying delayed state when callback raises error."""
        mock_player._state_synchronizer.get_merged_state.return_value = {"play_state": "pause"}
        mock_player._on_state_changed = MagicMock(side_effect=Exception("Callback error"))

        # Should not raise
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await debouncer._apply_delayed_state("pause")

    @pytest.mark.asyncio
    async def test_apply_delayed_state_cancelled(self, debouncer, mock_player):
        """Test applying delayed state when cancelled."""
        with patch("asyncio.sleep", side_effect=asyncio.CancelledError()):
            # Should not raise
            await debouncer._apply_delayed_state("pause")

        # Should not update state synchronizer
        mock_player._state_synchronizer.update_from_upnp.assert_not_called()
        assert debouncer._pending_task is None

    @pytest.mark.asyncio
    async def test_apply_delayed_state_error(self, debouncer, mock_player):
        """Test applying delayed state when error occurs."""
        mock_player._state_synchronizer.update_from_upnp.side_effect = Exception("Update error")

        # Should not raise
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await debouncer._apply_delayed_state("pause")

        assert debouncer._pending_task is None
