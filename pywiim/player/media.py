"""Media playback control."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from html import unescape
from typing import TYPE_CHECKING, Any, Literal
from xml.etree import ElementTree as ET

from ..exceptions import WiiMError
from .source_capabilities import SOURCE_CAPABILITIES, source_supports_native_notification_prompt

if TYPE_CHECKING:
    from . import Player

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class NotificationPlaybackResult:
    """Outcome details for play_notification source-aware execution."""

    method_used: Literal["prompt", "play_url"]
    source_before: str | None
    likely_interrupted: bool
    reason: str | None = None


class MediaControl:
    """Manages media playback operations."""

    def __init__(self, player: Player) -> None:
        """Initialize media control.

        Args:
            player: Parent Player instance.
        """
        self.player = player

    async def _route_slave_command(self, group_method) -> bool:
        """Route slave playback commands through group to master.

        Args:
            group_method: Async callable that routes to master (e.g., group.play() or group.master.resume()).

        Returns:
            True if command was routed (slave with group), False otherwise.

        Raises:
            WiiMError: If slave has no group object.
        """
        if self.player.is_slave and self.player.group:
            await group_method()
            return True

        if self.player.is_slave:
            _LOGGER.debug("Slave %s has no group object, cannot route playback command", self.player.host)
            raise WiiMError("Slave player not linked to group")

        return False

    async def play(self) -> None:
        """Start playback (raw API call).

        Note: On streaming sources when paused, this may restart the track from the
        beginning. Consider using resume() or media_play_pause() instead to continue
        from the current position.

        Raises:
            WiiMError: If the request fails.
        """
        # Route slave commands through group to master
        if self.player.group is not None:
            if await self._route_slave_command(lambda: self.player.group.play()):
                return
        elif self.player.is_slave:
            raise WiiMError("Slave player not linked to group")

        # Call API (raises on failure)
        await self.player.client.play()

        # Update cached state immediately (optimistic)
        if self.player._status_model:
            self.player._status_model.play_state = "play"

        # Update state synchronizer (for immediate property reads)
        self.player._state_synchronizer.update_from_http({"play_state": "play"})

        # Call callback to notify state change
        if self.player._on_state_changed:
            self.player._on_state_changed()

    async def pause(self) -> None:
        """Pause playback (raw API call).

        Raises:
            WiiMError: If the request fails.
        """
        # Route slave commands through group to master
        if self.player.group is not None:
            if await self._route_slave_command(lambda: self.player.group.pause()):
                return
        elif self.player.is_slave:
            raise WiiMError("Slave player not linked to group")

        # Call API (raises on failure)
        await self.player.client.pause()

        # Update cached state immediately (optimistic)
        if self.player._status_model:
            self.player._status_model.play_state = "pause"

        # Update state synchronizer (for immediate property reads)
        self.player._state_synchronizer.update_from_http({"play_state": "pause"})

        # Call callback to notify state change
        if self.player._on_state_changed:
            self.player._on_state_changed()

    async def resume(self) -> None:
        """Resume playback from paused state (raw API call).

        This command continues playback from the current position without restarting
        the track. Use this instead of play() when resuming paused content on streaming
        sources to avoid restarting from the beginning.

        Raises:
            WiiMError: If the request fails.
        """

        # Route slave commands through group to master
        # Note: Group doesn't have resume() method, so route directly to master
        if self.player.group is not None:
            group = self.player.group

            async def _resume_master() -> None:
                await group.master.resume()

            if await self._route_slave_command(_resume_master):
                return
        elif self.player.is_slave:
            raise WiiMError("Slave player not linked to group")

        # Call API (raises on failure)
        await self.player.client.resume()

        # Update cached state immediately (optimistic)
        if self.player._status_model:
            self.player._status_model.play_state = "play"

        # Update state synchronizer (for immediate property reads)
        self.player._state_synchronizer.update_from_http({"play_state": "play"})

        # Call callback to notify state change
        if self.player._on_state_changed:
            self.player._on_state_changed()

    async def stop(self) -> None:
        """Stop playback (raw API call).

        Note: WiFi/Webradio sources may not stay stopped and may return to playing state.
        For web radio streams, consider using pause() instead if stop() doesn't work reliably.

        Raises:
            WiiMError: If the request fails.
        """
        # Route slave commands through group to master
        if self.player.group is not None:
            if await self._route_slave_command(lambda: self.player.group.stop()):
                return
        elif self.player.is_slave:
            raise WiiMError("Slave player not linked to group")

        # Call API (raises on failure)
        await self.player.client.stop()

        # Update cached state immediately (optimistic)
        if self.player._status_model:
            self.player._status_model.play_state = "stop"

        # Update state synchronizer (for immediate property reads)
        self.player._state_synchronizer.update_from_http({"play_state": "stop"})

        # Call callback to notify state change
        if self.player._on_state_changed:
            self.player._on_state_changed()

    async def media_play_pause(self) -> None:
        """Toggle play/pause state intelligently (Home Assistant compatible).

        This method follows Home Assistant media_player conventions and handles the
        play/pause/resume semantics correctly across different sources:

        - When paused: Uses resume() to continue from current position (avoiding
          the issue where play() restarts streaming tracks from the beginning)
        - When playing: Uses pause() to pause playback
        - When stopped/idle: Uses play() to start playback

        This is the recommended method for implementing Home Assistant's media_play_pause
        service, as it avoids the track restart issue on streaming sources (Issue #102).

        Raises:
            WiiMError: If the request fails.

        Example:
            ```python
            # In Home Assistant media player entity
            async def async_media_play_pause(self) -> None:
                await self.coordinator.player.media_play_pause()
            ```
        """
        current_state = self.player.play_state

        if current_state in ("pause", "paused"):
            # Resume from current position (don't restart)
            await self.resume()
        elif current_state in ("play", "playing"):
            # Pause playback
            await self.pause()
        else:
            # Start playback (stopped/idle/unknown)
            await self.play()

    async def next_track(self) -> None:
        """Skip to next track."""
        # Route slave commands through group to master
        if self.player.group is not None:
            if await self._route_slave_command(lambda: self.player.group.next_track()):
                return
        elif self.player.is_slave:
            raise WiiMError("Slave player not linked to group")

        # Call API (raises on failure)
        await self.player.client.next_track()

        # Call callback to notify state change (track will change)
        if self.player._on_state_changed:
            self.player._on_state_changed()

    async def previous_track(self) -> None:
        """Skip to previous track."""
        # Route slave commands through group to master
        if self.player.group is not None:
            if await self._route_slave_command(lambda: self.player.group.previous_track()):
                return
        elif self.player.is_slave:
            raise WiiMError("Slave player not linked to group")

        # Call API (raises on failure)
        await self.player.client.previous_track()

        # Call callback to notify state change (track will change)
        if self.player._on_state_changed:
            self.player._on_state_changed()

    async def seek(self, position: int) -> None:
        """Seek to position in current track.

        Args:
            position: Position in seconds to seek to.
        """
        # Call API (raises on failure)
        await self.player.client.seek(position)

        # Update cached state immediately (optimistic)
        if self.player._status_model:
            self.player._status_model.position = position

        # Update state synchronizer (for immediate property reads)
        self.player._state_synchronizer.update_from_http({"position": position})

        # Call callback to notify state change
        if self.player._on_state_changed:
            self.player._on_state_changed()

    async def play_url(self, url: str, enqueue: Literal["add", "next", "replace", "play"] = "replace") -> None:
        """Play a URL directly with optional enqueue support.

        **Note: Fire-and-Forget API**

        The LinkPlay API accepts URLs without validation. This method returns
        successfully even if the URL is invalid, unreachable, or not an audio file.
        The device will attempt to play asynchronously and may end up in 'pause'
        or 'idle' state if playback fails.

        To verify playback actually started, wait a few seconds after calling
        this method, then check `player.play_state`. If it's 'pause' or 'idle'
        instead of 'play', the URL likely failed.

        Args:
            url: URL to play. Supports http/https URLs to audio files or streams.
            enqueue: How to enqueue the media:
                - "replace" (default): Replace current playback with URL
                - "play": Same as replace
                - "add": Add to end of queue (requires UPnP client)
                - "next": Insert after current track (requires UPnP client)

        Raises:
            WiiMError: If enqueue='add' or 'next' and UPnP client is not available.
                Note: Does NOT raise for invalid/unreachable URLs.
        """
        # Call API (raises on failure)
        if enqueue == "add" or enqueue == "next":
            if not self.player._upnp_client:
                raise WiiMError(f"Queue management (enqueue='{enqueue}') requires UPnP client.")
            # Explicit branches so mypy narrows enqueue (no type: ignore; CI uses warn_unused_ignores).
            if enqueue == "add":
                await self._enqueue_via_upnp(url, "add")
            else:
                await self._enqueue_via_upnp(url, "next")
        else:
            await self.player.client.play_url(url)
            # Track URL for media_title fallback (only for replace/play modes)
            self.player._last_played_url = url

        # Call callback to notify state change
        if self.player._on_state_changed:
            self.player._on_state_changed()

    async def play_playlist(self, playlist_url: str) -> None:
        """Play a playlist (M3U) URL.

        Args:
            playlist_url: URL to M3U playlist file.
        """
        # Call API (raises on failure)
        await self.player.client.play_playlist(playlist_url)

        # Call callback to notify state change
        if self.player._on_state_changed:
            self.player._on_state_changed()

    async def play_notification(self, url: str, *, force_interrupt: bool = False) -> NotificationPlaybackResult:
        """Play a notification sound from URL.

        For sources with native prompt support, this uses playPromptUrl so the
        firmware can duck and restore audio. For unsupported (or unknown)
        sources, it falls back to play_url so the notification remains audible.

        Note: fallback playback may interrupt the current source.

        Args:
            url: URL to notification audio file.
            force_interrupt: If True, always use play_url (interrupt playback)
                so the notification is guaranteed audible. Use for TTS when
                playPromptUrl returns OK but produces no sound (e.g. some
                firmware/source combinations or when the device cannot fetch
                the URL).

        Returns:
            NotificationPlaybackResult describing which playback path was used.
        """
        source_before: str | None = None
        if self.player._status_model and self.player._status_model.source:
            source_before = self.player._status_model.source.lower()

        if force_interrupt:
            await self.player.client.play_url(url)
            self.player._last_played_url = url
            result = NotificationPlaybackResult(
                method_used="play_url",
                source_before=source_before,
                likely_interrupted=True,
                reason="force_interrupt",
            )
        elif source_supports_native_notification_prompt(source_before):
            await self.player.client.play_notification(url)
            result = NotificationPlaybackResult(
                method_used="prompt",
                source_before=source_before,
                likely_interrupted=False,
            )
        else:
            await self.player.client.play_url(url)
            # Mirror play_url behavior: keep last URL for media_content_id fallback.
            self.player._last_played_url = url
            reason = "unsupported_source"
            if source_before is None:
                reason = "unknown_source_default_fallback"
            elif source_before not in SOURCE_CAPABILITIES:
                reason = "unknown_source_default_fallback"
            result = NotificationPlaybackResult(
                method_used="play_url",
                source_before=source_before,
                likely_interrupted=True,
                reason=reason,
            )

        # Call callback to notify state change
        if self.player._on_state_changed:
            self.player._on_state_changed()

        return result

    async def add_to_queue(self, url: str, metadata: str = "") -> None:
        """Add URL to end of queue (requires UPnP client).

        Args:
            url: URL to add to queue.
            metadata: Optional DIDL-Lite metadata.
        """
        if not self.player._upnp_client:
            raise WiiMError("Queue management requires UPnP client.")

        await self.player._upnp_client.async_call_action(
            "AVTransport",
            "AddURIToQueue",
            {
                "InstanceID": 0,
                "EnqueuedURI": url,
                "EnqueuedURIMetaData": metadata,
                "DesiredFirstTrackNumberEnqueued": 0,
                "EnqueueAsNext": False,
            },
        )

    async def insert_next(self, url: str, metadata: str = "") -> None:
        """Insert URL after current track (requires UPnP client).

        Args:
            url: URL to insert.
            metadata: Optional DIDL-Lite metadata.
        """
        if not self.player._upnp_client:
            raise WiiMError("Queue management requires UPnP client.")

        await self.player._upnp_client.async_call_action(
            "AVTransport",
            "InsertURIToQueue",
            {
                "InstanceID": 0,
                "EnqueuedURI": url,
                "EnqueuedURIMetaData": metadata,
                "DesiredTrackNumber": 0,
            },
        )

    async def _enqueue_via_upnp(self, url: str, enqueue: Literal["add", "next"]) -> None:
        """Internal helper for UPnP queue operations."""
        if enqueue == "add":
            await self.add_to_queue(url)
        elif enqueue == "next":
            await self.insert_next(url)

    async def play_preset(self, preset: int, index: int | None = None) -> None:
        """Play a preset by number, optionally starting at a track index.

        Args:
            preset: Preset number (1-based).
            index: Optional 1-based track index to start from (e.g. 1 = from beginning).
                When None, device resumes from last position.
        """
        # Call API (raises on failure)
        await self.player.client.play_preset(preset, index=index)

        # Call callback to notify state change
        if self.player._on_state_changed:
            self.player._on_state_changed()

    async def clear_playlist(self) -> None:
        """Clear the current playlist.

        Uses UPnP PlayQueue DeleteQueue action if available, otherwise falls back to HTTP API.
        The UPnP method is more reliable on some devices (e.g., Audio Pro C5MkII).

        Raises:
            WiiMError: If both UPnP and HTTP API methods fail
        """
        # Try UPnP PlayQueue DeleteQueue first (more reliable on some devices)
        if self.player._upnp_client and self.player._upnp_client.play_queue is not None:
            try:
                await self.player._upnp_client.async_call_action(
                    "play_queue",
                    "DeleteQueue",
                    {
                        "QueueName": "CurrentQueue",
                    },
                )
                _LOGGER.debug("Cleared playlist via UPnP PlayQueue on %s", self.player.host)

                # Call callback to notify state change
                if self.player._on_state_changed:
                    self.player._on_state_changed()
                return
            except Exception as err:
                _LOGGER.debug(
                    "UPnP PlayQueue DeleteQueue failed for %s, falling back to HTTP API: %s",
                    self.player.host,
                    err,
                )

        # Fall back to HTTP API
        await self.player.client.clear_playlist()

        # Call callback to notify state change
        if self.player._on_state_changed:
            self.player._on_state_changed()

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        """Check if string is a valid HTTP/HTTPS URL.

        Args:
            url: URL string to validate

        Returns:
            True if valid URL, False otherwise
        """
        if not url or not isinstance(url, str):
            return False
        url_lower = url.lower().strip()
        return url_lower.startswith(("http://", "https://"))

    def _parse_queue_items(self, didl_xml: str, starting_index: int = 0) -> list[dict[str, Any]]:
        """Parse DIDL-Lite XML to extract queue items.

        Follows SoCo pattern: Parses multiple items from queue Browse response.

        Args:
            didl_xml: DIDL-Lite XML string containing queue items
            starting_index: Starting index for position calculation

        Returns:
            List of queue item dictionaries with:
            - media_content_id: Media URI (HA standard field name)
            - title: Track title (if available)
            - artist: Artist name (if available)
            - album: Album name (if available)
            - duration: Duration in seconds (if available)
            - position: Position in queue (0-based index)
            - image_url: Album art URL (if available)
        """
        items: list[dict[str, Any]] = []

        if not didl_xml or didl_xml.strip() == "":
            return items

        try:
            # Unescape HTML entities (e.g., &lt; becomes <)
            didl_xml = unescape(didl_xml)

            # Parse XML
            root = ET.fromstring(didl_xml)

            # Define namespaces (both standard and LinkPlay-specific)
            namespaces = {
                "dc": "http://purl.org/dc/elements/1.1/",
                "upnp": "urn:schemas-upnp-org:metadata-1-0/upnp/",
                "song": "www.linkplay.com/song/",
                "": "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/",
            }

            # Find all item elements
            item_elements = root.findall(".//item", namespaces)
            if not item_elements:
                # Try without namespace
                item_elements = root.findall(".//item")

            for idx, item in enumerate(item_elements):
                queue_item: dict[str, Any] = {
                    "position": starting_index + idx,  # 0-based position in queue
                }

                # Extract URI from res element (res contains the media URL)
                res_elem = item.find(".//{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}res")
                if res_elem is None:
                    # Try without namespace
                    res_elem = item.find(".//res")

                if res_elem is not None and res_elem.text:
                    queue_item["media_content_id"] = res_elem.text.strip()

                    # Extract duration from res element's duration attribute
                    # Format is typically "H:MM:SS" or "H:MM:SS.mmm"
                    duration_str = res_elem.get("duration")
                    if duration_str:
                        duration_seconds = self._parse_duration(duration_str)
                        if duration_seconds is not None:
                            queue_item["duration"] = duration_seconds
                else:
                    # Fallback: check for res attribute on item
                    res_attr = item.get("res")
                    if res_attr:
                        queue_item["media_content_id"] = res_attr.strip()

                # Extract title (dc:title)
                title_elem = item.find("dc:title", namespaces)
                if title_elem is None:
                    title_elem = item.find(".//{http://purl.org/dc/elements/1.1/}title")
                if title_elem is not None and title_elem.text:
                    queue_item["title"] = title_elem.text.strip()

                # Extract artist (upnp:artist or dc:creator)
                artist_elem = item.find("upnp:artist", namespaces)
                if artist_elem is None:
                    artist_elem = item.find(".//{urn:schemas-upnp-org:metadata-1-0/upnp/}artist")
                if artist_elem is None:
                    artist_elem = item.find("dc:creator", namespaces)
                if artist_elem is None:
                    artist_elem = item.find(".//{http://purl.org/dc/elements/1.1/}creator")
                if artist_elem is not None and artist_elem.text:
                    queue_item["artist"] = artist_elem.text.strip()

                # Extract album (upnp:album)
                album_elem = item.find("upnp:album", namespaces)
                if album_elem is None:
                    album_elem = item.find(".//{urn:schemas-upnp-org:metadata-1-0/upnp/}album")
                if album_elem is not None and album_elem.text:
                    queue_item["album"] = album_elem.text.strip()

                # Extract album art URI (upnp:albumArtURI)
                art_elem = item.find("upnp:albumArtURI", namespaces)
                if art_elem is None:
                    art_elem = item.find(".//{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI")
                if art_elem is not None and art_elem.text:
                    image_url = art_elem.text.strip()
                    # Validate URL: must be valid http/https and not placeholder values
                    if image_url and image_url != "un_known" and self._is_valid_url(image_url):
                        queue_item["image_url"] = image_url

                # Only add item if it has at least a media_content_id
                if queue_item.get("media_content_id"):
                    items.append(queue_item)

        except ET.ParseError as err:
            _LOGGER.warning("Failed to parse queue DIDL-Lite XML: %s", err)
        except Exception as err:
            _LOGGER.warning("Error parsing queue items: %s", err)

        return items

    def _parse_duration(self, duration_str: str) -> int | None:
        """Parse UPnP duration string to seconds.

        Args:
            duration_str: Duration in format "H:MM:SS" or "H:MM:SS.mmm"

        Returns:
            Duration in seconds, or None if parsing fails
        """
        if not duration_str:
            return None

        try:
            # Remove milliseconds if present
            if "." in duration_str:
                duration_str = duration_str.split(".")[0]

            parts = duration_str.split(":")
            if len(parts) == 3:
                hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
                return hours * 3600 + minutes * 60 + seconds
            elif len(parts) == 2:
                minutes, seconds = int(parts[0]), int(parts[1])
                return minutes * 60 + seconds
            elif len(parts) == 1:
                return int(parts[0])
        except (ValueError, TypeError):
            pass

        return None

    async def get_queue(
        self,
        object_id: str = "Q:0",
        starting_index: int = 0,
        requested_count: int = 0,
    ) -> list[dict[str, Any]]:
        """Get current queue contents (requires UPnP client with ContentDirectory service).

        Follows SoCo pattern: Uses ContentDirectory Browse action to retrieve queue.

        **Note on Queue Information:**
        - **Queue count and position**: Available via HTTP API (`plicount`, `plicurr` in getPlayerStatus)
        - **Full queue contents**: Requires UPnP ContentDirectory service (see availability below)

        **ContentDirectory Availability:**
        ContentDirectory service is only available on:
        - WiiM Amp (when USB drive is connected)
        - WiiM Ultra (when USB drive is connected)

        Other WiiM devices (Mini, Pro, Pro Plus) do not expose ContentDirectory service
        as they function only as UPnP renderers, not media servers.

        Args:
            object_id: Queue object ID (default "Q:0" for standard queue)
            starting_index: Starting index for pagination (0 = first item)
            requested_count: Number of items to retrieve (0 = all available)

        Returns:
            List of queue item dictionaries, each containing:
            - media_content_id: Media URI (HA standard field name)
            - title: Track title (if available)
            - artist: Artist name (if available)
            - album: Album name (if available)
            - duration: Duration in seconds (if available)
            - position: Position in queue (0-based index)
            - image_url: Album art URL (if available)

        Raises:
            WiiMError: If UPnP client is not available, ContentDirectory service is not
                available, or queue retrieval fails
        """
        if not self.player._upnp_client:
            raise WiiMError("Queue retrieval requires UPnP client.")

        try:
            # Browse queue using ContentDirectory service
            result = await self.player._upnp_client.browse_queue(
                object_id=object_id,
                starting_index=starting_index,
                requested_count=requested_count,
            )

            # Parse DIDL-Lite XML response
            didl_xml = result.get("Result", "")
            items = self._parse_queue_items(didl_xml, starting_index)

            _LOGGER.debug(
                "Retrieved %d queue items from %s (total: %d)",
                len(items),
                self.player.host,
                result.get("TotalMatches", len(items)),
            )

            return items

        except Exception as err:
            _LOGGER.warning("Failed to get queue from %s: %s", self.player.host, err)
            raise WiiMError(f"Failed to get queue: {err}") from err

    async def play_queue(self, queue_position: int = 0) -> None:
        """Start playing from the queue at a specific position.

        Uses UPnP AVTransport Seek action with TRACK_NR unit to jump to queue position.

        Args:
            queue_position: 0-based index in queue to start playing (default: 0)

        Raises:
            WiiMError: If UPnP client is not available, queue position is invalid,
                or the seek action fails
        """
        if not self.player._upnp_client:
            raise WiiMError("Queue playback requires UPnP client.")

        if queue_position < 0:
            raise WiiMError(f"Invalid queue position: {queue_position} (must be >= 0)")

        try:
            # Use Seek with TRACK_NR unit to jump to queue position
            # UPnP uses 1-based track numbers, so add 1 to 0-based position
            await self.player._upnp_client.async_call_action(
                "av_transport",
                "Seek",
                {
                    "InstanceID": 0,
                    "Unit": "TRACK_NR",
                    "Target": str(queue_position + 1),  # UPnP uses 1-based index
                },
            )

            _LOGGER.debug(
                "Started playback from queue position %d on %s",
                queue_position,
                self.player.host,
            )

        except Exception as err:
            _LOGGER.warning(
                "Failed to play queue position %d on %s: %s",
                queue_position,
                self.player.host,
                err,
            )
            raise WiiMError(f"Failed to play queue position {queue_position}: {err}") from err

    async def remove_from_queue(self, queue_position: int = 0) -> None:
        """Remove an item from the queue at a specific position.

        Uses UPnP AVTransport RemoveTrackFromQueue action.

        Args:
            queue_position: 0-based index in queue to remove (default: 0)

        Raises:
            WiiMError: If UPnP client is not available, queue position is invalid,
                or the remove action fails
        """
        if not self.player._upnp_client:
            raise WiiMError("Queue management requires UPnP client.")

        if queue_position < 0:
            raise WiiMError(f"Invalid queue position: {queue_position} (must be >= 0)")

        try:
            # RemoveTrackFromQueue uses ObjectID which is typically "Q:0/position"
            # UPnP uses 1-based track numbers
            object_id = f"Q:0/{queue_position + 1}"

            await self.player._upnp_client.async_call_action(
                "av_transport",
                "RemoveTrackFromQueue",
                {
                    "InstanceID": 0,
                    "ObjectID": object_id,
                    "UpdateID": 0,
                },
            )

            _LOGGER.debug(
                "Removed item at queue position %d from %s",
                queue_position,
                self.player.host,
            )

        except Exception as err:
            _LOGGER.warning(
                "Failed to remove queue position %d from %s: %s",
                queue_position,
                self.player.host,
                err,
            )
            raise WiiMError(f"Failed to remove queue position {queue_position}: {err}") from err

    async def clear_queue(self) -> None:
        """Clear all items from the queue.

        Uses UPnP AVTransport RemoveAllTracksFromQueue action.

        Raises:
            WiiMError: If UPnP client is not available or the action fails
        """
        if not self.player._upnp_client:
            raise WiiMError("Queue management requires UPnP client.")

        try:
            await self.player._upnp_client.async_call_action(
                "av_transport",
                "RemoveAllTracksFromQueue",
                {
                    "InstanceID": 0,
                },
            )

            _LOGGER.debug("Cleared queue on %s", self.player.host)

        except Exception as err:
            _LOGGER.warning("Failed to clear queue on %s: %s", self.player.host, err)
            raise WiiMError(f"Failed to clear queue: {err}") from err
