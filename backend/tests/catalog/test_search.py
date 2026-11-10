"""Global catalogue search."""

from typing import Any

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from catalog.factories import AlbumFactory, ArtistFactory, TrackFactory

pytestmark = pytest.mark.django_db

URL = "/api/v1/catalog/search/"


def _names(group: dict[str, Any]) -> list[str]:
    return [r.get("name") or r["title"] for r in group["results"]]


def test_requires_a_session(anonymous: APIClient) -> None:
    assert anonymous.get(URL, {"q": "ab"}).status_code == 403


@pytest.mark.parametrize("params", [{}, {"q": ""}, {"q": "a"}, {"q": "abc", "type": "records"}])
def test_bad_query_is_400(api: APIClient, params: dict[str, str]) -> None:
    assert api.get(URL, params).status_code == 400


def test_groups_by_type_with_totals(api: APIClient) -> None:
    artist = ArtistFactory(name="Michael Thriller")
    album = AlbumFactory(title="Thriller")
    TrackFactory(album=album, title="Thriller (live)")
    TrackFactory(title="Another")
    body = api.get(URL, {"q": "thriller"}).data
    assert set(body) == {"artists", "albums", "tracks"}
    assert (body["artists"]["count"], _names(body["artists"])) == (1, [artist.name])
    assert (body["albums"]["count"], _names(body["albums"])) == (1, ["Thriller"])
    assert (body["tracks"]["count"], _names(body["tracks"])) == (1, ["Thriller (live)"])
    track = body["tracks"]["results"][0]
    assert {"id", "title", "image", "subtitle"} <= set(track)
    assert track["subtitle"]


def test_type_limits_to_one_group(api: APIClient) -> None:
    AlbumFactory(title="Zeta")
    TrackFactory(title="Zeta song")
    for kind in ("artists", "albums", "tracks"):
        assert set(api.get(URL, {"q": "zeta", "type": kind}).data) == {kind}
    assert set(api.get(URL, {"q": "zeta", "type": "all"}).data) == {
        "artists",
        "albums",
        "tracks",
    }


def test_limit_and_its_maximum(api: APIClient) -> None:
    for _n in range(30):
        ArtistFactory(name="Zebra")
    body = api.get(URL, {"q": "zebra", "type": "artists"}).data
    assert (body["artists"]["count"], len(body["artists"]["results"])) == (30, 5)
    assert (
        len(api.get(URL, {"q": "zebra", "type": "artists", "limit": 2}).data["artists"]["results"])
        == 2
    )
    assert (
        len(api.get(URL, {"q": "zebra", "type": "artists", "limit": 99}).data["artists"]["results"])
        == 20
    )
    assert api.get(URL, {"q": "zebra", "limit": "x"}).status_code == 400


def test_matches_by_artist_name_without_duplicates(api: APIClient) -> None:
    a, b = ArtistFactory(name="Dúo Uno"), ArtistFactory(name="Dúo Dos")
    track = TrackFactory(title="Canción")
    track.credits.all().delete()
    track.credits.create(artist=a)
    track.credits.create(artist=b)
    album = AlbumFactory(title="Disco")
    album.credits.all().delete()
    album.credits.create(artist=a)
    album.credits.create(artist=b)
    body = api.get(URL, {"q": "dúo"}).data
    assert (body["tracks"]["count"], _names(body["tracks"])) == (1, ["Canción"])
    assert (body["albums"]["count"], _names(body["albums"])) == (1, ["Disco"])


def test_query_count_is_constant(api: APIClient) -> None:
    def count() -> int:
        with CaptureQueriesContext(connection) as ctx:
            assert api.get(URL, {"q": "mix"}).status_code == 200
        return len(ctx)

    TrackFactory(title="mix 0", album__title="mix 0")
    ArtistFactory(name="mix 0")
    before = count()
    for n in range(1, 10):
        TrackFactory(title=f"mix {n}", album__title=f"mix {n}")
        ArtistFactory(name=f"mix {n}")
    assert count() == before
