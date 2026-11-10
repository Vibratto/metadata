"""Recordings API: the albums a recording is on, merging and splitting."""

import pytest
from rest_framework.test import APIClient

from activity.models import ActivityLog
from catalog.factories import AlbumFactory, DownloadFactory, RecordingFactory, TrackFactory
from catalog.models import Recording, Track

pytestmark = pytest.mark.django_db

BASE = "/api/v1/catalog"


def _on_two_albums() -> Recording:
    """One recording that is a single and also a track of an album."""
    single = TrackFactory(title="Song", duration=200, video_id="vid-song", album__title="Single")
    TrackFactory(
        title="Song", recording=single.recording, credit=None, album=AlbumFactory(title="Album")
    )
    return single.recording


def test_a_session_is_required(anonymous: APIClient) -> None:
    recording = _on_two_albums()
    assert anonymous.get(f"{BASE}/recordings/").status_code == 403
    body = {"recording": recording.pk}
    assert anonymous.post(f"{BASE}/recordings/{recording.pk}/merge/", body).status_code == 403


def test_list_shows_each_recording_with_its_albums(api: APIClient) -> None:
    recording = _on_two_albums()
    TrackFactory()

    body = api.get(f"{BASE}/recordings/").json()

    assert body["count"] == 2
    item = next(r for r in body["results"] if r["id"] == recording.pk)
    assert (item["title"], item["duration"], item["video_id"]) == ("Song", 200, "vid-song")
    assert (item["track_count"], item["downloaded"]) == (2, False)
    assert sorted(t["album_title"] for t in item["tracks"]) == ["Album", "Single"]
    assert item["artists"][0]["name"]


def test_recording_is_downloaded_when_any_of_its_tracks_is(api: APIClient) -> None:
    recording = _on_two_albums()
    DownloadFactory(track=recording.tracks.first())
    TrackFactory(title="Other")

    body = api.get(f"{BASE}/recordings/", {"search": "Song"}).json()

    assert [r["id"] for r in body["results"]] == [recording.pk]
    assert body["results"][0]["downloaded"] is True
    assert sorted(t["downloaded"] for t in body["results"][0]["tracks"]) == [False, True]


def test_search_finds_a_recording_by_its_video_id(api: APIClient) -> None:
    recording = _on_two_albums()
    TrackFactory()
    body = api.get(f"{BASE}/recordings/", {"search": "vid-song"}).json()
    assert [r["id"] for r in body["results"]] == [recording.pk]


def test_detail(api: APIClient) -> None:
    recording = _on_two_albums()
    assert api.get(f"{BASE}/recordings/{recording.pk}/").json()["id"] == recording.pk


def test_recordings_cannot_be_edited_or_deleted(api: APIClient) -> None:
    recording = _on_two_albums()
    assert api.patch(f"{BASE}/recordings/{recording.pk}/", {"title": "x"}).status_code == 405
    assert api.delete(f"{BASE}/recordings/{recording.pk}/").status_code == 405


def test_merge_moves_the_tracks_and_drops_the_absorbed_recording(api: APIClient) -> None:
    keep = RecordingFactory(title="Song", duration=None)
    gone = RecordingFactory(title="Song", duration=180)
    kept_track = TrackFactory(recording=keep, credit=None)
    moved_track = TrackFactory(recording=gone, credit=None)

    response = api.post(f"{BASE}/recordings/{keep.pk}/merge/", {"recording": gone.pk})

    assert response.status_code == 200
    assert response.json()["track_count"] == 2
    assert not Recording.objects.filter(pk=gone.pk).exists()
    assert set(Track.objects.filter(recording=keep)) == {kept_track, moved_track}
    keep.refresh_from_db()
    assert keep.duration == 180
    entry = ActivityLog.objects.get(action="catalog.recording.merged")
    assert entry.detail == {"absorbed": gone.pk, "title": "Song"}


def test_merge_refuses_two_tracks_on_the_same_album(api: APIClient) -> None:
    album = AlbumFactory()
    keep, gone = RecordingFactory(), RecordingFactory()
    TrackFactory(album=album, recording=keep, credit=None)
    TrackFactory(album=album, recording=gone, credit=None)

    response = api.post(f"{BASE}/recordings/{keep.pk}/merge/", {"recording": gone.pk})

    assert response.status_code == 400
    assert response.json()["detail"] == "Both recordings have a track on the same album."
    assert Recording.objects.filter(pk=gone.pk).exists()


@pytest.mark.parametrize("other", ["self", 999_999, None])
def test_merge_needs_another_existing_recording(api: APIClient, other: object) -> None:
    keep = TrackFactory().recording
    body = {} if other is None else {"recording": keep.pk if other == "self" else other}
    assert api.post(f"{BASE}/recordings/{keep.pk}/merge/", body).status_code == 400
    assert Recording.objects.count() == 1


def test_split_gives_the_track_its_own_recording(api: APIClient) -> None:
    recording = _on_two_albums()
    on_album = recording.tracks.get(album__title="Album")

    response = api.post(f"{BASE}/tracks/{on_album.pk}/split/")

    assert response.status_code == 200
    assert response.json()["recording"] != recording.pk
    assert response.json()["also_on"] == 0
    assert Recording.objects.count() == 2
    assert ActivityLog.objects.filter(action="catalog.track.split").count() == 1


def test_split_of_an_only_track_is_a_400(api: APIClient) -> None:
    track = TrackFactory()
    response = api.post(f"{BASE}/tracks/{track.pk}/split/")
    assert response.status_code == 400
    assert Recording.objects.count() == 1


def test_tracks_show_how_many_other_albums_share_their_recording(api: APIClient) -> None:
    recording = _on_two_albums()
    alone = TrackFactory()
    rows = {t["id"]: t for t in api.get(f"{BASE}/tracks/").json()["results"]}
    assert {rows[t.pk]["also_on"] for t in recording.tracks.all()} == {1}
    assert rows[alone.pk]["also_on"] == 0


def test_a_track_whose_recording_is_already_downloaded_is_copyable(api: APIClient) -> None:
    recording = _on_two_albums()
    single = recording.tracks.get(album__title="Single")
    on_album = recording.tracks.get(album__title="Album")
    DownloadFactory(track=single)
    rows = {t["id"]: t for t in api.get(f"{BASE}/tracks/").json()["results"]}
    assert (rows[on_album.pk]["copyable"], rows[single.pk]["copyable"]) == (True, False)
