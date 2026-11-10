"""YouTube Music client against a scripted ytmusicapi double; nothing touches the network."""

from types import SimpleNamespace
from typing import Any

import pytest

from integrations.ytmusic import (
    Album,
    Artist,
    ArtistRef,
    Lyrics,
    ReleaseRef,
    SongHit,
    Track,
    YTMusicClient,
    YTMusicError,
    parse_channel_id,
)
from integrations.ytmusic.client import parse_count

CHANNEL = "UCmMUZbaYdNH0bEd1PAlAqsA"
OTHER = "UC0000000000000000000000"


class FakeApi:
    """Returns canned responses by method name and records every call."""

    def __init__(self, **responses: Any) -> None:
        self.responses = responses
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:
        def call(*args: Any, **kwargs: Any) -> Any:
            self.calls.append((name, args, kwargs))
            response = self.responses[name]
            if isinstance(response, Exception):
                raise response
            return response

        return call


def thumbs(*widths: int) -> list[dict[str, Any]]:
    return [{"url": f"https://img.test/a=w{w}-h{w}-l90-rj", "width": w} for w in widths]


def artist_page(**overrides: Any) -> dict[str, Any]:
    page: dict[str, Any] = {
        "name": "Los Cometas",
        "channelId": CHANNEL,
        "description": "A band.",
        "subscribers": "1.2M",
        "monthlyListeners": "12.4M monthly audience",
        "thumbnails": thumbs(120, 540),
        "albums": {
            "results": [
                {"title": "Atlas", "browseId": "MPREb_atlas", "year": "2020", "type": "Album"}
            ]
        },
        "singles": {"results": [{"title": "Faro", "browseId": "MPREb_faro", "year": "2021"}]},
        "related": {
            "results": [
                {"title": "Nova Brisa", "browseId": OTHER, "subscribers": "8.1M"},
                {"title": "No channel"},
            ]
        },
    }
    return page | overrides


def test_artist_keeps_the_id_it_was_asked_for() -> None:
    # The page's own "channelId" is the artist's video channel, a different id from the one
    # search results, track credits and related artists use to refer to the artist.
    api = FakeApi(get_artist={**artist_page(), "channelId": "UCvideo-channel-000000000"})
    assert YTMusicClient(api).get_artist(CHANNEL).artist.id == CHANNEL
    assert YTMusicClient(api).get_artist_profile(CHANNEL).id == CHANNEL


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (CHANNEL, CHANNEL),
        (f"https://music.youtube.com/channel/{CHANNEL}?si=abc", CHANNEL),
        (f"https://music.youtube.com/browse/{CHANNEL}", CHANNEL),
        (f"  https://www.youtube.com/channel/{CHANNEL}/featured ", CHANNEL),
        ("Los Cometas", None),
        ("UCtooshort", None),
        ("", None),
    ],
)
def test_parse_channel_id(text: str, expected: str | None) -> None:
    assert parse_channel_id(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("12.4M monthly audience", 12_400_000),
        ("1.2M", 1_200_000),
        ("412K subscribers", 412_000),
        ("3B", 3_000_000_000),
        ("1,234,567 views", 1_234_567),
        ("96", 96),
        ("850 monthly audience", 850),
        ("7 B-sides", 7),
        ("1,5 M", 1_500_000),
        (2500, 2500),
        ("no figures here", None),
        (None, None),
    ],
)
def test_parse_count(text: object, expected: int | None) -> None:
    assert parse_count(text) == expected


def test_get_artist_returns_profile_with_largest_image_at_cover_size() -> None:
    page = YTMusicClient(FakeApi(get_artist=artist_page())).get_artist(CHANNEL)
    assert page.artist == Artist(
        id=CHANNEL,
        name="Los Cometas",
        image_url="https://img.test/a=w1200-h1200-l90-rj",
        description="A band.",
        monthly_listeners=12_400_000,
        subscribers=1_200_000,
    )


def test_audience_prefers_monthly_listeners_then_subscribers() -> None:
    assert Artist("x", "X", monthly_listeners=5, subscribers=9).audience == 5
    assert Artist("x", "X", subscribers=9).audience == 9
    assert Artist("x", "X").audience == 0


def test_get_artist_tolerates_a_sparse_page() -> None:
    api = FakeApi(get_artist={"name": "Solo", "thumbnails": None})
    page = YTMusicClient(api).get_artist(CHANNEL)
    assert page.artist == Artist(id=CHANNEL, name="Solo")
    assert page.releases == ()
    assert page.related == ()


def test_get_artist_lists_albums_then_singles_with_their_kind() -> None:
    page = YTMusicClient(FakeApi(get_artist=artist_page())).get_artist(CHANNEL)
    assert page.releases == (
        ReleaseRef("MPREb_atlas", "Atlas", "album", 2020),
        ReleaseRef("MPREb_faro", "Faro", "single", 2021),
    )


def test_get_artist_follows_the_shelf_link_to_the_full_discography() -> None:
    albums = {"browseId": "MPADUC1", "params": "p", "results": [{"title": "x", "browseId": "x"}]}
    full = [
        {"title": "Atlas", "browseId": "MPREb_atlas", "year": "2020"},
        {"title": "Atlas II", "browseId": "MPREb_atlas2", "type": "EP"},
        {"title": "Atlas", "browseId": "MPREb_atlas"},
        {"title": "No id"},
    ]
    api = FakeApi(get_artist=artist_page(albums=albums, singles=None), get_artist_albums=full)
    page = YTMusicClient(api).get_artist(CHANNEL)
    assert [(r.id, r.kind) for r in page.releases] == [
        ("MPREb_atlas", "album"),
        ("MPREb_atlas2", "ep"),
    ]
    assert ("get_artist_albums", ("MPADUC1", "p"), {"limit": None}) in api.calls


def test_get_artist_profile_costs_a_single_request() -> None:
    albums = {"browseId": "MPADUC1", "params": "p", "results": []}
    api = FakeApi(get_artist=artist_page(albums=albums))
    assert YTMusicClient(api).get_artist_profile(CHANNEL).name == "Los Cometas"
    assert [name for name, *_ in api.calls] == ["get_artist"]


def test_get_artist_returns_related_artists_that_have_a_channel() -> None:
    page = YTMusicClient(FakeApi(get_artist=artist_page())).get_artist(CHANNEL)
    assert page.related == (ArtistRef("Nova Brisa", OTHER),)


def test_get_artist_without_a_name_is_an_error() -> None:
    with pytest.raises(YTMusicError, match=CHANNEL):
        YTMusicClient(FakeApi(get_artist={"description": "?"})).get_artist(CHANNEL)


def test_any_ytmusicapi_failure_becomes_ytmusic_error() -> None:
    client = YTMusicClient(FakeApi(get_artist=KeyError("musicImmersiveHeaderRenderer")))
    with pytest.raises(YTMusicError, match="get_artist failed") as raised:
        client.get_artist(CHANNEL)
    assert isinstance(raised.value.__cause__, KeyError)


def test_search_artists_skips_results_without_a_channel() -> None:
    results = [
        {"artist": "Los Cometas", "browseId": CHANNEL, "subscribers": "1.2M", "thumbnails": []},
        {"artist": "Ghost"},
    ]
    api = FakeApi(search=results)
    assert YTMusicClient(api).search_artists("cometas", limit=5) == (
        Artist(id=CHANNEL, name="Los Cometas", subscribers=1_200_000),
    )
    assert api.calls == [("search", ("cometas",), {"filter": "artists", "limit": 5})]


def test_search_songs_returns_what_is_needed_to_match_a_file() -> None:
    results = [
        {
            "title": "Uno",
            "videoId": "aaaaaaaaaaa",
            "artists": [{"name": "Los Cometas", "id": CHANNEL}],
            "album": {"name": "Atlas", "id": "MPREb_atlas"},
            "duration_seconds": 201,
        },
        {"title": "Loose", "videoId": "bbbbbbbbbbb", "artists": None, "album": None},
        {"title": "No video"},
    ]
    api = FakeApi(search=results)
    assert YTMusicClient(api).search_songs("los cometas uno") == (
        SongHit(
            "aaaaaaaaaaa", "Uno", (ArtistRef("Los Cometas", CHANNEL),), "MPREb_atlas", "Atlas", 201
        ),
        SongHit("bbbbbbbbbbb", "Loose", ()),
    )
    assert api.calls == [("search", ("los cometas uno",), {"filter": "songs", "limit": 10})]


def album_page(**overrides: Any) -> dict[str, Any]:
    page: dict[str, Any] = {
        "title": "Atlas",
        "type": "Album",
        "year": "2020",
        "isExplicit": True,
        "artists": [{"name": "Los Cometas", "id": CHANNEL}],
        "thumbnails": thumbs(60, 544),
        "tracks": [
            {
                "title": "Uno (feat. Nova Brisa)",
                "videoId": "aaaaaaaaaaa",
                "artists": [{"name": "Los Cometas", "id": CHANNEL}],
                "trackNumber": 1,
                "duration_seconds": 201,
                "isExplicit": True,
            },
            {"title": "Dos", "videoId": None, "artists": None, "trackNumber": 2},
        ],
    }
    return page | overrides


def test_get_album_returns_release_and_tracks() -> None:
    album = YTMusicClient(FakeApi(get_album=album_page())).get_album("MPREb_atlas")
    band = ArtistRef("Los Cometas", CHANNEL)
    assert album == Album(
        id="MPREb_atlas",
        title="Atlas",
        artists=(band,),
        kind="album",
        year=2020,
        cover_url="https://img.test/a=w1200-h1200-l90-rj",
        explicit=True,
        tracks=(
            Track(
                title="Uno",
                artists=(band, ArtistRef("Nova Brisa")),
                video_id="aaaaaaaaaaa",
                position=1,
                duration=201,
                explicit=True,
            ),
            Track(title="Dos", artists=(band,), position=2),
        ),
    )


def test_get_album_reads_kind_and_tolerates_missing_year_and_tracks() -> None:
    page = album_page(type="Single", year=None, tracks=None)
    album = YTMusicClient(FakeApi(get_album=page)).get_album("MPREb_faro")
    assert (album.kind, album.year, album.tracks) == ("single", None, ())


def test_get_album_without_a_title_is_an_error() -> None:
    with pytest.raises(YTMusicError, match="MPREb_x"):
        YTMusicClient(FakeApi(get_album={"tracks": []})).get_album("MPREb_x")


def test_get_lyrics_formats_timed_lines_as_lrc() -> None:
    lines = [
        SimpleNamespace(text="First line", start_time=9_200),
        SimpleNamespace(text="Second line", start_time=65_430),
    ]
    api = FakeApi(
        get_watch_playlist={"lyrics": "MPLYt_1"},
        get_lyrics={"lyrics": lines, "hasTimestamps": True, "source": "Source: Musixmatch"},
    )
    assert YTMusicClient(api).get_lyrics("aaaaaaaaaaa") == Lyrics(
        "[00:09.20]First line\n[01:05.43]Second line", True, "Source: Musixmatch"
    )
    assert api.calls[-1] == ("get_lyrics", ("MPLYt_1",), {"timestamps": True})


def test_get_lyrics_returns_plain_text_when_untimed() -> None:
    api = FakeApi(
        get_watch_playlist={"lyrics": "MPLYt_1"},
        get_lyrics={"lyrics": "First\nSecond", "hasTimestamps": False, "source": None},
    )
    assert YTMusicClient(api).get_lyrics("aaaaaaaaaaa") == Lyrics("First\nSecond")


@pytest.mark.parametrize("response", [None, {}, {"lyrics": None}, {"lyrics": ""}])
def test_get_lyrics_is_none_when_the_track_has_none(response: Any) -> None:
    api = FakeApi(get_watch_playlist={"lyrics": "MPLYt_1"}, get_lyrics=response)
    assert YTMusicClient(api).get_lyrics("aaaaaaaaaaa") is None


def test_get_lyrics_skips_the_second_request_without_a_lyrics_tab() -> None:
    api = FakeApi(get_watch_playlist={"lyrics": None})
    assert YTMusicClient(api).get_lyrics("aaaaaaaaaaa") is None
    assert [name for name, *_ in api.calls] == ["get_watch_playlist"]
