"""Tests for UPnP metadata parsing helpers."""

from __future__ import annotations

from pywiim.upnp.metadata import is_valid_image_url, parse_didl_metadata, parse_getinfoex_response

DIDL_ESCAPED = (
    "&lt;?xml version=&quot;1.0&quot; encoding=&quot;UTF-8&quot;?&gt;"
    "&lt;DIDL-Lite xmlns:dc=&quot;http://purl.org/dc/elements/1.1/&quot; "
    "xmlns:upnp=&quot;urn:schemas-upnp-org:metadata-1-0/upnp/&quot; "
    "xmlns=&quot;urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/&quot;&gt;"
    "&lt;item id=&quot;0&quot;&gt;"
    "&lt;dc:title&gt;Herz an Herz&lt;/dc:title&gt;"
    "&lt;upnp:artist&gt;Betontod&lt;/upnp:artist&gt;"
    "&lt;upnp:album&gt;Revolution&lt;/upnp:album&gt;"
    "&lt;upnp:albumArtURI&gt;https://i.scdn.co/image/ab67616d0000b27356d04017e7964e8b231a5677&lt;/upnp:albumArtURI&gt;"
    "&lt;/item&gt;&lt;/DIDL-Lite&gt;"
)

SOAP_RESPONSE = f"""<?xml version=\"1.0\" encoding=\"utf-8\"?>
<s:Envelope xmlns:s=\"http://schemas.xmlsoap.org/soap/envelope/\">
  <s:Body>
    <u:GetInfoExResponse xmlns:u=\"urn:schemas-upnp-org:service:AVTransport:1\">
      <CurrentTransportState>PLAYING</CurrentTransportState>
      <TrackMetaData>{DIDL_ESCAPED}</TrackMetaData>
      <PlayMedium>SPOTIFY</PlayMedium>
    </u:GetInfoExResponse>
  </s:Body>
</s:Envelope>"""


class TestUpnpMetadataHelpers:
    def test_is_valid_image_url(self):
        assert is_valid_image_url("https://example.com/art.jpg") is True
        assert is_valid_image_url("un_known") is False
        assert is_valid_image_url(None) is False

    def test_parse_didl_metadata_extracts_artwork(self):
        result = parse_didl_metadata(DIDL_ESCAPED)
        assert result["title"] == "Herz an Herz"
        assert result["artist"] == "Betontod"
        assert result["album"] == "Revolution"
        assert result["image_url"].startswith("https://i.scdn.co/image/")

    def test_parse_didl_metadata_invalid_artwork(self):
        didl = (
            "<DIDL-Lite xmlns:upnp=\"urn:schemas-upnp-org:metadata-1-0/upnp/\">"
            "<item><upnp:albumArtURI>un_known</upnp:albumArtURI></item></DIDL-Lite>"
        )
        result = parse_didl_metadata(didl)
        assert "image_url" not in result

    def test_parse_getinfoex_response(self):
        result = parse_getinfoex_response(SOAP_RESPONSE)
        assert result["CurrentTransportState"] == "PLAYING"
        assert result["PlayMedium"] == "SPOTIFY"
        assert result["title"] == "Herz an Herz"
        assert result["image_url"].startswith("https://i.scdn.co/image/")
