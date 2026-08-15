"""Tests for PlayQueue XML helpers."""

from pywiim.upnp.playqueue import (
    build_empty_playlist,
    build_track_playlist,
    parse_queue_context,
    playqueue_supports_enqueue,
    service_has_action,
    title_from_url,
)


class TestServiceHasAction:
    def test_none_service(self) -> None:
        assert service_has_action(None, "CreateQueue") is False

    def test_actions_not_dict(self) -> None:
        class Svc:
            actions = object()

        assert service_has_action(Svc(), "CreateQueue") is False

    def test_missing_action(self) -> None:
        class Svc:
            actions = {"BrowseQueue": object()}

        assert playqueue_supports_enqueue(Svc()) is False

    def test_enqueue_actions_present(self) -> None:
        class Svc:
            actions = {
                "CreateQueue": object(),
                "AppendTracksInQueueEx": object(),
                "PlayQueueWithIndex": object(),
            }

        assert playqueue_supports_enqueue(Svc()) is True


class TestPlaylistXml:
    def test_title_from_url(self) -> None:
        assert title_from_url("https://example.com/music/Song%201.mp3") == "Song 1.mp3"

    def test_empty_playlist_has_no_tracks(self) -> None:
        xml = build_empty_playlist()
        assert "<ListName>CurrentQueue</ListName>" in xml
        assert "<Tracks></Tracks>" in xml
        assert "<TotalNumber>0</TotalNumber>" in xml

    def test_track_playlist_includes_url_and_didl(self) -> None:
        xml = build_track_playlist("https://example.com/a.mp3")
        assert "<URL>https://example.com/a.mp3</URL>" in xml
        assert "<Track1>" in xml
        assert "DIDL-Lite" in xml
        assert "a.mp3" in xml

    def test_track_playlist_escapes_ampersand(self) -> None:
        xml = build_track_playlist("https://example.com/a.mp3?x=1&y=2")
        assert "x=1&amp;y=2" in xml

    def test_parse_queue_context_tracks(self) -> None:
        didl = (
            "&lt;DIDL-Lite xmlns:dc=&quot;http://purl.org/dc/elements/1.1/&quot; "
            "xmlns=&quot;urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/&quot;&gt;"
            "&lt;dc:title&gt;Song 1&lt;/dc:title&gt;&lt;/DIDL-Lite&gt;"
        )
        ctx = f"""<?xml version="1.0"?>
<PlayList>
<ListName>CurrentQueue</ListName>
<Tracks>
<Track1>
<URL>https://example.com/one.mp3</URL>
<Metadata>{didl}</Metadata>
</Track1>
<Track2>
<URL>https://example.com/two.mp3</URL>
<Metadata></Metadata>
</Track2>
</Tracks>
</PlayList>
"""
        items = parse_queue_context(ctx)
        assert len(items) == 2
        assert items[0]["media_content_id"] == "https://example.com/one.mp3"
        assert items[0]["title"] == "Song 1"
        assert items[0]["position"] == 0
        assert items[1]["media_content_id"] == "https://example.com/two.mp3"
        assert items[1]["position"] == 1

    def test_parse_empty_or_invalid(self) -> None:
        assert parse_queue_context("") == []
        assert parse_queue_context("<not-xml") == []
        assert parse_queue_context("<PlayList><Tracks></Tracks></PlayList>") == []
