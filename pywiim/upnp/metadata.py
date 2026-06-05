"""UPnP metadata parsing helpers."""

from __future__ import annotations

import logging
import re
from html import unescape
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

_LOGGER = logging.getLogger(__name__)

_BARE_AMPERSAND_RE = re.compile(r"&(?!#\d+;|#x[0-9a-fA-F]+;|[A-Za-z][A-Za-z0-9]+;)")


def is_valid_image_url(url: str | None) -> bool:
    """Return True when value is a usable HTTP/HTTPS artwork URL."""
    if not url or not isinstance(url, str):
        return False

    value = url.strip()
    if not value or value.lower() in ("unknow", "unknown", "un_known", "none"):
        return False

    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def parse_didl_metadata(didl_xml: str, *, allow_clear: bool = False) -> dict[str, Any]:
    """Parse DIDL-Lite XML and extract track metadata.

    Args:
        didl_xml: DIDL-Lite XML string (may be HTML-encoded).
        allow_clear: When True, empty elements clear existing metadata fields.

    Returns:
        Dict with optional title, artist, album, and image_url keys.
    """
    changes: dict[str, Any] = {}
    if not didl_xml or not didl_xml.strip():
        return changes

    try:
        didl_xml = _BARE_AMPERSAND_RE.sub("&amp;", unescape(didl_xml))
        root = ET.fromstring(didl_xml)

        namespaces = {
            "dc": "http://purl.org/dc/elements/1.1/",
            "upnp": "urn:schemas-upnp-org:metadata-1-0/upnp/",
            "song": "www.linkplay.com/song/",
            "": "urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/",
        }

        item = root.find(".//item", namespaces)
        if item is None:
            item = root.find(".//{*}item")

        if item is None:
            return changes

        title_elem = item.find("dc:title", namespaces)
        if title_elem is None:
            title_elem = item.find(".//{http://purl.org/dc/elements/1.1/}title")
        if title_elem is not None and title_elem.text and title_elem.text.strip():
            changes["title"] = title_elem.text.strip()
        elif title_elem is not None and allow_clear:
            changes["title"] = None

        artist_elem = item.find("upnp:artist", namespaces)
        if artist_elem is None:
            artist_elem = item.find(".//{urn:schemas-upnp-org:metadata-1-0/upnp/}artist")
        if artist_elem is None:
            artist_elem = item.find("dc:creator", namespaces)
        if artist_elem is None:
            artist_elem = item.find(".//{http://purl.org/dc/elements/1.1/}creator")
        if artist_elem is not None and artist_elem.text and artist_elem.text.strip():
            changes["artist"] = artist_elem.text.strip()
        elif artist_elem is not None and allow_clear:
            changes["artist"] = None

        album_elem = item.find("upnp:album", namespaces)
        if album_elem is None:
            album_elem = item.find(".//{urn:schemas-upnp-org:metadata-1-0/upnp/}album")
        if album_elem is not None and album_elem.text and album_elem.text.strip():
            changes["album"] = album_elem.text.strip()
        elif album_elem is not None and allow_clear:
            changes["album"] = None

        art_elem = item.find("upnp:albumArtURI", namespaces)
        if art_elem is None:
            art_elem = item.find(".//{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI")
        if art_elem is not None and art_elem.text:
            image_url = art_elem.text.strip()
            if is_valid_image_url(image_url):
                changes["image_url"] = image_url
            elif allow_clear:
                changes["image_url"] = None

    except ET.ParseError as err:
        _LOGGER.debug("Failed to parse DIDL-Lite metadata: %s", err)
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Error extracting metadata from DIDL-Lite: %s", err)

    return changes


def _find_first_text_by_local_name(root: ET.Element, local_name: str) -> str | None:
    """Return text for the first element matching a local tag name."""
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == local_name and element.text and element.text.strip():
            return element.text.strip()
    return None


def parse_getinfoex_response(soap_xml: str) -> dict[str, Any]:
    """Parse a GetInfoEx SOAP response into normalized metadata fields."""
    if not soap_xml or not soap_xml.strip():
        return {}

    try:
        root = ET.fromstring(soap_xml)
    except ET.ParseError as err:
        _LOGGER.debug("Failed to parse GetInfoEx SOAP response: %s", err)
        return {}

    result: dict[str, Any] = {}

    for field in (
        "CurrentTransportState",
        "TrackURI",
        "RelTime",
        "TrackDuration",
        "PlayMedium",
        "TrackSource",
    ):
        value = _find_first_text_by_local_name(root, field)
        if value is not None:
            result[field] = value

    track_metadata = _find_first_text_by_local_name(root, "TrackMetaData")
    if track_metadata:
        result["TrackMetaData"] = track_metadata
        result.update(parse_didl_metadata(track_metadata))

    return result
