"""Filters of the catalogue lists."""

from typing import Any

import pytest
from rest_framework.test import APIClient

from catalog.factories import (
    AlbumArtistFactory,
    AlbumFactory,
    ArtistFactory,
    DownloadFactory,
    TrackArtistFactory,
    TrackFactory,
)
from catalog.models import Album, Track
from watches.models import Watch, WatchArtist

pytestmark = pytest.mark.django_db

BASE = "/api/v1/catalog"


def _ids(api: APIClient, path: str, **query: Any) -> set[int]:
    response = api.get(f"{BASE}/{path}/", query)
    assert response.status_code == 200, response.content
    return {row["id"] for row in response.json()["results"]}


def _album(**fields: Any) -> Album:
    return AlbumFactory(**fields)


def _artist_with(downloaded: int, pending: int) -> int:
    artist = ArtistFactory()
    for index in range(downloaded + pending):
        track = TrackFactory(credit=None)
        TrackArtistFactory(track=track, artist=artist)
        if index < downloaded:
            DownloadFactory(track=track)
    return artist.pk


# --- Artists ---


def test_artists_by_name_and_external_id(api: APIClient) -> None:
    cometas = ArtistFactory(name="Los Cometas", ytmusic_id="UCcometas")
    ArtistFactory(name="Other")
    assert _ids(api, "artists", name__icontains="comet") == {cometas.pk}
    assert _ids(api, "artists", ytmusic_id="UCcometas") == {cometas.pk}


def test_artists_by_download_state(api: APIClient) -> None:
    complete = _artist_with(downloaded=2, pending=0)
    partial = _artist_with(downloaded=1, pending=1)
    untouched = _artist_with(downloaded=0, pending=2)
    mine = {complete, partial, untouched}
    assert _ids(api, "artists", has_downloads="true") & mine == {complete, partial}
    assert _ids(api, "artists", has_downloads="false") & mine == {untouched}
    assert _ids(api, "artists", has_pending="true") & mine == {partial, untouched}
    assert _ids(api, "artists", has_pending="false") & mine == {complete}


def test_artists_by_watch(api: APIClient) -> None:
    watched, free = ArtistFactory(), ArtistFactory()
    WatchArtist.objects.create(watch=Watch.objects.create(name="w"), artist=watched)
    assert _ids(api, "artists", watched="true") == {watched.pk}
    assert _ids(api, "artists", watched="false") == {free.pk}


# --- Albums ---


def test_albums_by_artist_accept_several_ids_without_repeating_rows(api: APIClient) -> None:
    first, second = ArtistFactory(), ArtistFactory()
    shared = AlbumFactory(credit=None)
    AlbumArtistFactory(album=shared, artist=first, position=0)
    AlbumArtistFactory(album=shared, artist=second, position=1)
    other = AlbumFactory()
    response = api.get(f"{BASE}/albums/", {"artist": f"{first.pk},{second.pk}"})
    assert [row["id"] for row in response.json()["results"]] == [shared.pk]
    assert other.pk not in _ids(api, "albums", artist=first.pk)


def test_albums_by_type(api: APIClient) -> None:
    album, single, ep = _album(), _album(record_type="single"), _album(record_type="ep")
    assert _ids(api, "albums", record_type="album") == {album.pk}
    assert _ids(api, "albums", record_type="single,ep") == {single.pk, ep.pk}
    assert _ids(api, "albums", record_type="") == {album.pk, single.pk, ep.pk}


def test_unknown_type_is_a_400_not_an_empty_list(api: APIClient) -> None:
    response = api.get(f"{BASE}/albums/", {"record_type": "album,mixtape"})
    assert response.status_code == 400
    assert response.json()["record_type"] == ["Unknown type: mixtape."]


def test_albums_by_year(api: APIClient) -> None:
    old, mid, new, unknown = _album(year=1999), _album(year=2010), _album(year=2022), _album()
    assert _ids(api, "albums", year=2010) == {mid.pk}
    assert _ids(api, "albums", year_from=2010) == {mid.pk, new.pk}
    assert _ids(api, "albums", year_to=2010) == {old.pk, mid.pk}
    assert _ids(api, "albums", year_from=2000, year_to=2015) == {mid.pk}
    assert unknown.pk not in _ids(api, "albums", year_from=0)


def test_albums_by_download_status(api: APIClient) -> None:
    complete, partial, none, empty = _album(), _album(), _album(), _album()
    DownloadFactory(track=TrackFactory(album=complete))
    DownloadFactory(track=TrackFactory(album=partial))
    TrackFactory(album=partial)
    TrackFactory(album=none)
    assert _ids(api, "albums", download_status="complete") == {complete.pk}
    assert _ids(api, "albums", download_status="partial") == {partial.pk}
    # An album without tracks has nothing downloaded either.
    assert _ids(api, "albums", download_status="none") == {none.pk, empty.pk}
    assert api.get(f"{BASE}/albums/", {"download_status": "half"}).status_code == 400


# --- Tracks ---


def test_tracks_by_album_artist_and_video(api: APIClient) -> None:
    track, other = TrackFactory(video_id="vid-1"), TrackFactory()
    artist = track.credits.get().artist
    assert _ids(api, "tracks", album=track.album_id) == {track.pk}
    assert _ids(api, "tracks", album=f"{track.album_id},{other.album_id}") == {track.pk, other.pk}
    assert _ids(api, "tracks", artist=artist.pk) == {track.pk}
    assert _ids(api, "tracks", video_id="vid-1") == {track.pk}


def test_tracks_with_and_without_a_video(api: APIClient) -> None:
    playable, unplayable = TrackFactory(), TrackFactory(video_id=None)
    assert _ids(api, "tracks", has_video="true") == {playable.pk}
    assert _ids(api, "tracks", has_video="false") == {unplayable.pk}


def test_tracks_by_state_and_recording_data(api: APIClient) -> None:
    downloaded = TrackFactory(explicit=True, duration=100)
    pending = TrackFactory(explicit=False, duration=300)
    DownloadFactory(track=downloaded)
    assert _ids(api, "tracks", downloaded="true") == {downloaded.pk}
    assert _ids(api, "tracks", downloaded="false") == {pending.pk}
    assert _ids(api, "tracks", explicit="true") == {downloaded.pk}
    assert _ids(api, "tracks", duration_min=200) == {pending.pk}
    assert _ids(api, "tracks", duration_max=200) == {downloaded.pk}


def test_tracks_by_album_type_and_year(api: APIClient) -> None:
    on_single = TrackFactory(album=_album(record_type="single", year=2020))
    on_album = TrackFactory(album=_album(year=2022))
    assert _ids(api, "tracks", record_type="single") == {on_single.pk}
    assert _ids(api, "tracks", year=2022) == {on_album.pk}
    assert _ids(api, "tracks", year_from=2021) == {on_album.pk}
    assert _ids(api, "tracks", year_to=2021) == {on_single.pk}


def test_one_row_per_recording(api: APIClient) -> None:
    single = TrackFactory()
    on_album = TrackFactory(recording=single.recording, credit=None)
    alone = TrackFactory()
    assert _ids(api, "tracks", one_per_recording="true") == {single.pk, alone.pk}
    assert _ids(api, "tracks", one_per_recording="false") == {single.pk, on_album.pk, alone.pk}
    assert Track.objects.count() == 3
