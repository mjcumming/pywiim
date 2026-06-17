"""Cover art fetching and caching.

# pragma: allow-long-file coverart-cohesive
# This file exceeds the 400 LOC soft limit (417 lines) but is kept as a single
# cohesive unit because:
# 1. Single responsibility: Cover art fetching, caching, and track change detection
# 2. Well-organized: Clear sections for fetching, caching, and change detection
# 3. Tight coupling: All methods work together for cover art management
# 4. Maintainable: Clear structure, follows cover art design pattern
# 5. Natural unit: Represents one concept (cover art management)
# Splitting would add complexity without clear benefit.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import aiohttp

if TYPE_CHECKING:
    from . import Player

_LOGGER = logging.getLogger(__name__)


class CoverArtManager:
    """Manages cover art fetching and caching."""

    def __init__(self, player: Player) -> None:
        """Initialize cover art manager.

        Args:
            player: Parent Player instance.
        """
        self.player = player
        # Track last track signature to detect track changes for immediate artwork fetching
        self._last_track_signature: str | None = None
        # Track if we're already fetching artwork to avoid duplicate requests
        self._artwork_fetch_task: asyncio.Task | None = None

    def _get_url_hash(self, url: str) -> str:
        """Generate a hash for a URL to use as cache key."""
        return hashlib.md5(url.encode()).hexdigest()

    def _cleanup_cover_art_cache(self) -> None:
        """Remove expired entries from cover art cache."""
        now = time.time()
        expired_keys = [
            key
            for key, (_, _, timestamp) in self.player._cover_art_cache.items()
            if now - timestamp > self.player._cover_art_cache_ttl
        ]
        for key in expired_keys:
            del self.player._cover_art_cache[key]

        # If still over max size, remove oldest entries
        if len(self.player._cover_art_cache) > self.player._cover_art_cache_max_size:
            sorted_entries = sorted(
                self.player._cover_art_cache.items(),
                key=lambda x: x[1][2],
            )
            for key, _ in sorted_entries[: len(self.player._cover_art_cache) - self.player._cover_art_cache_max_size]:
                del self.player._cover_art_cache[key]

    async def fetch_cover_art(self, url: str | None = None) -> tuple[bytes, str] | None:
        """Fetch cover art image from URL or return embedded fallback logo.

        Args:
            url: Cover art URL to fetch. If None, uses current track's cover art URL.
                If no valid URL is found, returns the embedded PyWiim logo (no HTTP call).

        Returns:
            Tuple of (image_bytes, content_type) if successful, None otherwise.
        """
        import base64

        from .properties import PlayerProperties

        if url is None:
            url = PlayerProperties(self.player).media_image_url

        # If no URL provided OR sentinel value, return embedded PyWiim logo directly (no HTTP call needed)
        from ..api.constants import DEFAULT_WIIM_LOGO_URL, EMBEDDED_LOGO_BASE64

        if not url or url == DEFAULT_WIIM_LOGO_URL:
            try:
                # Decode the embedded base64 PNG logo (join tuple of strings first)
                base64_string = "".join(EMBEDDED_LOGO_BASE64)
                logo_bytes = base64.b64decode(base64_string)
                _LOGGER.debug("Returning embedded PyWiim fallback logo (%d bytes)", len(logo_bytes))
                return (logo_bytes, "image/png")
            except Exception as e:
                _LOGGER.error("Failed to decode embedded logo: %s", e)
                return None

        # Clean up expired cache entries
        self._cleanup_cover_art_cache()

        # Check cache first
        url_hash = self._get_url_hash(url)
        if url_hash in self.player._cover_art_cache:
            cached_bytes, content_type, timestamp = self.player._cover_art_cache[url_hash]
            if time.time() - timestamp < self.player._cover_art_cache_ttl:
                _LOGGER.debug("Returning cover art from cache for URL: %s", url)
                return (cached_bytes, content_type)

        # Fetch from URL
        try:
            session = self.player.client._session
            should_close_session = False

            if session is None:
                session = aiohttp.ClientSession()
                should_close_session = True

            try:
                # Get SSL context from client if URL is HTTPS
                timeout = aiohttp.ClientTimeout(total=10)
                if url.startswith("https://"):
                    # Use the client's SSL context for HTTPS URLs
                    # This ensures we can fetch artwork from device URLs with self-signed certs
                    ssl_ctx = await self.player.client._get_ssl_context()
                    async with session.get(url, timeout=timeout, ssl=ssl_ctx) as response:
                        if response.status == 200:
                            image_bytes = await response.read()
                            content_type = response.headers.get("Content-Type", "image/jpeg")
                            if "image" not in content_type.lower():
                                content_type = "image/jpeg"

                            # Cache the result
                            self.player._cover_art_cache[url_hash] = (
                                image_bytes,
                                content_type,
                                time.time(),
                            )
                            _LOGGER.debug("Fetched and cached cover art from URL: %s", url)

                            # Clean up cache if needed
                            self._cleanup_cover_art_cache()

                            return (image_bytes, content_type)
                        else:
                            _LOGGER.debug(
                                "Failed to fetch cover art: HTTP %d from %s",
                                response.status,
                                url,
                            )
                            return None
                else:
                    # For HTTP URLs, use default SSL handling
                    async with session.get(url, timeout=timeout) as response:
                        if response.status == 200:
                            image_bytes = await response.read()
                            content_type = response.headers.get("Content-Type", "image/jpeg")
                            if "image" not in content_type.lower():
                                content_type = "image/jpeg"

                            # Cache the result
                            self.player._cover_art_cache[url_hash] = (
                                image_bytes,
                                content_type,
                                time.time(),
                            )
                            _LOGGER.debug("Fetched and cached cover art from URL: %s", url)

                            # Clean up cache if needed
                            self._cleanup_cover_art_cache()

                            return (image_bytes, content_type)
                        else:
                            _LOGGER.debug(
                                "Failed to fetch cover art: HTTP %d from %s",
                                response.status,
                                url,
                            )
                            return None
            finally:
                if should_close_session:
                    await session.close()
        except Exception as e:
            _LOGGER.debug("Error fetching cover art from %s: %s", url, e)
            return None

    def check_track_changed(self, merged_state: dict[str, Any]) -> bool:
        """Check if track changed based on title/artist/album signature.

        Args:
            merged_state: Merged state dictionary from StateSynchronizer.

        Returns:
            True if track changed, False otherwise.
        """
        # Build current track signature
        title = merged_state.get("title") or ""
        artist = merged_state.get("artist") or ""
        album = merged_state.get("album") or ""
        current_signature = f"{title}|{artist}|{album}"

        # Check if track changed
        track_changed = bool(
            current_signature and self._last_track_signature and current_signature != self._last_track_signature
        )

        if track_changed:
            self._last_track_signature = current_signature

        if not self._last_track_signature and current_signature:
            # First track detected
            self._last_track_signature = current_signature

        return track_changed

    async def enrich_metadata_on_track_change(
        self,
        merged_state: dict[str, Any],
        *,
        track_changed: bool | None = None,
    ) -> None:
        """Fetch metadata from getMetaInfo when artwork missing or metadata is Unknown.

        This runs as a background task when:
        1. Track changed, OR
        2. Metadata (title/artist) is "Unknown" (Bluetooth AVRCP case), OR
        3. Artwork is missing but track metadata exists

        Args:
            merged_state: Merged state dictionary from StateSynchronizer.
            track_changed: Whether the track changed this refresh cycle. Callers on
                the polling/UPnP paths compute this once via :meth:`check_track_changed`
                and pass it here, because ``_last_track_signature`` is a single-shot
                latch that other trigger logic (EQ/source/getMetaInfo) consumes earlier
                in the same cycle. When ``None`` (legacy callers / isolated tests), the
                edge is derived from the latch as a best-effort fallback.
        """

        # Helper to check if metadata value is invalid/unknown
        def is_invalid_metadata(val: str | None) -> bool:
            if not val:
                return True
            val_lower = str(val).strip().lower()
            return val_lower in ("unknow", "unknown", "un_known", "", "none")

        # Build current track signature
        title = merged_state.get("title") or ""
        artist = merged_state.get("artist") or ""
        album = merged_state.get("album") or ""
        current_signature = f"{title}|{artist}|{album}"

        # Determine the track-change edge. The caller owns the latch when it passes an
        # explicit value (it already called check_track_changed for this cycle), so we
        # must not re-read or re-write _last_track_signature in that case — doing so is
        # exactly the bug that made the stale-artwork refresh a silent no-op on the
        # polling path. Only the legacy (track_changed is None) fallback touches the latch.
        owns_latch = track_changed is None
        if owns_latch:
            track_changed = bool(
                current_signature and self._last_track_signature and current_signature != self._last_track_signature
            )
            if track_changed:
                self._last_track_signature = current_signature

        # Check if metadata needs enrichment (title/artist/album are present but Unknown)
        # This is common with Bluetooth AVRCP where getPlayerStatusEx returns "Unknown"
        # but getMetaInfo has the actual track info
        needs_metadata_enrichment = (
            ("title" in merged_state and is_invalid_metadata(title))
            or ("artist" in merged_state and is_invalid_metadata(artist))
            or ("album" in merged_state and is_invalid_metadata(album))
        )

        # Check if artwork is missing or is default logo
        image_url = merged_state.get("image_url")
        from ..api.constants import DEFAULT_WIIM_LOGO_URL

        has_valid_artwork = (
            image_url
            and str(image_url).strip()
            and str(image_url).strip().lower() not in ("unknow", "unknown", "un_known", "none", "")
            and str(image_url).strip() != DEFAULT_WIIM_LOGO_URL
        )

        # Fetch metadata when:
        # 1. Track changed, OR
        # 2. Metadata (title/artist) is "Unknown" (Bluetooth AVRCP case), OR
        # 3. Artwork is missing but we have track metadata (Arylic/LinkPlay GetInfoEx case)
        # A valid URL can still be stale artwork from the previous track, so track
        # changes refresh enrichment even when image_url is syntactically valid.
        has_track_metadata = bool(title or artist or album)
        needs_artwork_enrichment = not has_valid_artwork and has_track_metadata
        should_fetch_metadata = track_changed or needs_metadata_enrichment or needs_artwork_enrichment

        if should_fetch_metadata:
            # Cancel any existing fetch task
            current_task = asyncio.current_task()
            if (
                self._artwork_fetch_task
                and not self._artwork_fetch_task.done()
                and self._artwork_fetch_task is not current_task
            ):
                self._artwork_fetch_task.cancel()

            if current_task:
                self._artwork_fetch_task = current_task

            if needs_metadata_enrichment:
                _LOGGER.debug("Metadata is Unknown, fetching enrichment sources")
            elif needs_artwork_enrichment:
                _LOGGER.debug("Artwork missing with track metadata, fetching enrichment sources")
            else:
                _LOGGER.debug("Track changed, fetching enrichment sources")

            await self._fetch_artwork_from_metainfo(
                merged_state,
                force_getinfoex=bool(track_changed),
            )

        if owns_latch and not self._last_track_signature and current_signature:
            # First track detected (legacy fallback only; the caller owns the latch
            # via check_track_changed on the polling/UPnP paths).
            self._last_track_signature = current_signature

    @staticmethod
    def _is_invalid_metadata(val: str | None) -> bool:
        """Return True when metadata value is empty or a known placeholder."""
        if not val:
            return True
        val_lower = str(val).strip().lower()
        return val_lower in ("unknow", "unknown", "un_known", "", "none")

    def _build_metadata_update(
        self,
        merged_state: dict[str, Any],
        source: dict[str, Any],
        *,
        source_name: str,
    ) -> dict[str, Any]:
        """Build a state synchronizer update from enrichment source metadata."""
        update: dict[str, Any] = {}

        for field, alias in (("title", "Title"), ("artist", "Artist"), ("album", "Album")):
            source_value = source.get(field)
            if source_value and not self._is_invalid_metadata(source_value):
                current_value = merged_state.get(field)
                if self._is_invalid_metadata(current_value) or str(source_value) != str(current_value):
                    update[field] = source_value
                    update[alias] = source_value

        artwork_url = (
            source.get("image_url")
            or source.get("cover")
            or source.get("cover_url")
            or source.get("albumart")
            or source.get("albumArtURI")
            or source.get("albumArtUri")
            or source.get("albumarturi")
            or source.get("art_url")
            or source.get("artwork_url")
            or source.get("pic_url")
        )

        if artwork_url and not self._is_invalid_metadata(artwork_url):
            if "http" in str(artwork_url).lower() or str(artwork_url).startswith("/"):
                title = update.get("title") or merged_state.get("title") or ""
                artist = update.get("artist") or merged_state.get("artist") or ""
                album = update.get("album") or merged_state.get("album") or ""
                cache_key = f"{title}-{artist}-{album}"
                if cache_key:
                    encoded = quote(cache_key)
                    sep = "&" if "?" in str(artwork_url) else "?"
                    artwork_url = f"{artwork_url}{sep}cache={encoded}"
                update["image_url"] = artwork_url
                update["entity_picture"] = artwork_url

        if update:
            _LOGGER.debug("Built metadata update from %s: %s", source_name, update)
        return update

    def _apply_metadata_update(
        self,
        update: dict[str, Any],
        *,
        source_name: str,
        state_source: str = "http",
    ) -> None:
        """Apply enrichment metadata to synchronizer, status model, and callbacks."""
        if not update:
            return

        timestamp = time.time()
        if state_source == "upnp":
            self.player._state_synchronizer.update_from_upnp(
                update,
                timestamp=timestamp,
                force_metadata_update=True,
            )
        else:
            self.player._state_synchronizer.update_from_http(
                update,
                timestamp=timestamp,
                force_metadata_update=True,
            )
        merged = self.player._state_synchronizer.get_merged_state()
        if self.player._status_model:
            if "title" in update:
                self.player._status_model.title = merged.get("title")
            if "artist" in update:
                self.player._status_model.artist = merged.get("artist")
            if "album" in update:
                self.player._status_model.album = merged.get("album")
            if "image_url" in update or "entity_picture" in update:
                image_url = merged.get("image_url")
                self.player._status_model.entity_picture = image_url
                self.player._status_model.cover_url = image_url

        if self.player._on_state_changed:
            try:
                self.player._on_state_changed()
            except Exception as err:
                _LOGGER.debug("Error in callback after %s metadata update: %s", source_name, err)

    async def _fetch_artwork_from_getinfoex(self, merged_state: dict[str, Any]) -> dict[str, Any] | None:
        """Fetch artwork/metadata from LinkPlay GetInfoEx when HTTP metadata lacks artwork."""
        if getattr(self.player, "_getinfoex_supported", None) is False:
            return None

        if not await self.player._ensure_upnp_client():
            return None

        upnp_client = self.player._upnp_client
        if upnp_client is None or upnp_client.av_transport is None:
            return None

        try:
            info = await upnp_client.get_info_ex()
        except Exception as err:
            self.player._getinfoex_supported = False
            _LOGGER.debug("GetInfoEx unavailable for %s: %s", self.player.host, err)
            return None

        self.player._getinfoex_supported = True
        update = self._build_metadata_update(merged_state, info, source_name="GetInfoEx")
        if update:
            self._apply_metadata_update(update, source_name="GetInfoEx", state_source="upnp")
        return update

    async def _fetch_artwork_from_metainfo(
        self,
        merged_state: dict[str, Any],
        *,
        force_getinfoex: bool = False,
    ) -> None:
        """Fetch metadata/artwork from getMetaInfo, then GetInfoEx as fallback.

        This runs as a background task when track changes and artwork is missing.
        Also updates title/artist/album from getMetaInfo when the status endpoint
        returns "Unknown" values (common with Bluetooth AVRCP sources).
        On track changes, GetInfoEx is also probed after getMetaInfo because
        some LinkPlay/Arylic devices keep returning the first artwork URL from
        getMetaInfo while GetInfoEx already has the current track art.

        Args:
            merged_state: Current merged state dictionary from StateSynchronizer.
            force_getinfoex: Whether to probe GetInfoEx even when getMetaInfo
                returned artwork.
        """
        try:
            update: dict[str, Any] = {}

            # Skip getMetaInfo on devices that don't implement it (issue #248); the
            # GetInfoEx fallback below still runs and can supply artwork.
            if self.player.supports_metadata and hasattr(self.player.client, "get_meta_info"):
                meta_info = await self.player.client.get_meta_info()
                if meta_info and "metaData" in meta_info:
                    update = self._build_metadata_update(
                        merged_state,
                        meta_info["metaData"],
                        source_name="getMetaInfo",
                    )
                    if update:
                        self._apply_metadata_update(update, source_name="getMetaInfo")

            if force_getinfoex or not (update.get("image_url") or update.get("entity_picture")):
                await self._fetch_artwork_from_getinfoex(merged_state)
        except asyncio.CancelledError:
            # Task was cancelled (new track change detected)
            pass
        except Exception as e:
            _LOGGER.debug("Error fetching metadata enrichment on track change: %s", e)

    async def get_cover_art_bytes(self, url: str | None = None) -> bytes | None:
        """Get cover art image bytes (convenience method).

        Args:
            url: Cover art URL to fetch. If None, uses current track's cover art URL.

        Returns:
            Image bytes if successful, None otherwise.
        """
        result = await self.fetch_cover_art(url)
        if result:
            return result[0]
        return None
