"""LinkPlay PlayQueue helpers for URL enqueue on WiiM firmware.

WiiM Pro / Pro Plus advertise AVTransport but do not implement Sonos
``AddURIToQueue``. Incremental HTTP enqueue is a no-op. The working path is
the vendor PlayQueue service with DIDL metadata inside each ``TrackN``.
"""

from __future__ import annotations

from html import escape, unescape
from typing import Any
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree as ET

CURRENT_QUEUE = "CurrentQueue"
PLAYQUEUE_ENQUEUE_ACTIONS = (
    "CreateQueue",
    "AppendTracksInQueueEx",
    "PlayQueueWithIndex",
)


def service_has_action(service: Any, action: str) -> bool:
    """Return True when a UPnP service advertises ``action``."""
    if service is None:
        return False
    actions = getattr(service, "actions", None)
    return isinstance(actions, dict) and action in actions


def playqueue_supports_enqueue(play_queue: Any) -> bool:
    """Return True when PlayQueue can create, append, and play-at-index."""
    return all(service_has_action(play_queue, name) for name in PLAYQUEUE_ENQUEUE_ACTIONS)


def title_from_url(url: str) -> str:
    """Best-effort title from a media URL path."""
    path = unquote(urlparse(url).path)
    name = path.rsplit("/", 1)[-1].strip()
    return name or url


def build_didl_metadata(url: str, title: str) -> str:
    """Build escaped DIDL-Lite for a PlayQueue ``<Metadata>`` element."""
    safe_url = escape(url, quote=True)
    safe_title = escape(title, quote=True)
    raw = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/" '
        'xmlns:song="www.wiimu.com/song/" '
        'xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/">'
        "<upnp:class>object.item.audioItem.musicTrack</upnp:class>"
        '<item id="0">'
        f'<res protocolInfo="http-get:*:audio/mpeg:DLNA.ORG_PN=MP3;DLNA.ORG_OP=01;" '
        f'duration="00:00:00.000">{safe_url}</res>'
        f"<dc:title>{safe_title}</dc:title>"
        "<upnp:artist>unknown</upnp:artist>"
        "<upnp:album>unknown</upnp:album>"
        "</item>"
        "</DIDL-Lite>"
    )
    return escape(raw)


def build_empty_playlist(queue_name: str = CURRENT_QUEUE) -> str:
    """QueueContext that creates an empty PlayQueue without autoplay."""
    return (
        '<?xml version="1.0"?>'
        "<PlayList>"
        f"<ListName>{escape(queue_name)}</ListName>"
        "<ListInfo>"
        "<QueueVersion>2.0</QueueVersion>"
        "<SourceName></SourceName>"
        "<PicUrl></PicUrl>"
        "<TotalNumber>0</TotalNumber>"
        "<TrackNumber>0</TrackNumber>"
        "<LastPlayIndex>1</LastPlayIndex>"
        "</ListInfo>"
        "<Tracks></Tracks>"
        "</PlayList>"
    )


def build_track_playlist(
    url: str,
    metadata: str = "",
    title: str | None = None,
    queue_name: str = CURRENT_QUEUE,
) -> str:
    """QueueContext with a single DIDL-backed track for append/create."""
    track_title = title or title_from_url(url)
    didl = metadata.strip() if metadata and metadata.strip() else build_didl_metadata(url, track_title)
    if metadata and metadata.strip() and not didl.startswith("&lt;") and "<" in didl:
        didl = escape(didl)
    return (
        '<?xml version="1.0"?>'
        "<PlayList>"
        f"<ListName>{escape(queue_name)}</ListName>"
        "<ListInfo>"
        "<QueueVersion>2.0</QueueVersion>"
        "<Radio>0</Radio>"
        "<SourceName>Local</SourceName>"
        "<PicUrl></PicUrl>"
        "<TotalNumber>1</TotalNumber>"
        "<TrackNumber>1</TrackNumber>"
        "<LastPlayIndex>1</LastPlayIndex>"
        "</ListInfo>"
        "<Tracks>"
        "<Track1>"
        f"<URL>{escape(url, quote=True)}</URL>"
        f"<Metadata>{didl}</Metadata>"
        "<Source>OnlineMusic</Source>"
        "<Id>1</Id>"
        "</Track1>"
        "</Tracks>"
        "</PlayList>"
    )


def parse_queue_context(queue_context: str) -> list[dict[str, Any]]:
    """Parse BrowseQueue QueueContext XML into HA-style queue items."""
    items: list[dict[str, Any]] = []
    if not queue_context or not queue_context.strip():
        return items
    try:
        root = ET.fromstring(queue_context)
    except ET.ParseError:
        return items

    tracks = root.find("Tracks")
    if tracks is None:
        return items

    for child in list(tracks):
        tag = child.tag.rsplit("}", 1)[-1]
        if not tag.startswith("Track") or not tag[5:].isdigit():
            continue
        url_el = child.find("URL")
        url = (url_el.text or "").strip() if url_el is not None else ""
        if not url:
            continue
        item: dict[str, Any] = {
            "media_content_id": url,
            "position": len(items),
        }
        title = _title_from_metadata(child.find("Metadata"))
        if title:
            item["title"] = title
        items.append(item)
    return items


def _title_from_metadata(meta_el: ET.Element | None) -> str | None:
    if meta_el is None or not meta_el.text:
        return None
    raw = unescape(meta_el.text)
    try:
        meta_root = ET.fromstring(raw)
    except ET.ParseError:
        return None
    for elem in meta_root.iter():
        if elem.tag.rsplit("}", 1)[-1] == "title" and elem.text:
            return elem.text.strip()
    return None
