"""Merging two recordings and splitting a track off a shared one."""

import pytest

from catalog.factories import AlbumFactory, ArtistFactory, TrackArtistFactory, TrackFactory
from catalog.models import Recording
from catalog.services.recordings import RecordingError, merge_recordings, split_track

pytestmark = pytest.mark.django_db


def test_merge_moves_the_tracks_and_deletes_the_absorbed_recording() -> None:
    single, on_album = TrackFactory(), TrackFactory()
    keep, absorbed = single.recording, on_album.recording

    merge_recordings(keep, absorbed)

    on_album.refresh_from_db()
    assert on_album.recording == keep
    assert not Recording.objects.filter(pk=absorbed.pk).exists()


def test_merge_fills_in_what_the_kept_recording_lacks() -> None:
    keep = TrackFactory(video_id=None, duration=None, explicit=False).recording
    absorbed = TrackFactory(video_id="vid-b", duration=180, explicit=True).recording
    merge_recordings(keep, absorbed)
    keep.refresh_from_db()
    assert (keep.video_id, keep.duration, keep.explicit) == ("vid-b", 180, True)


def test_merge_keeps_what_the_kept_recording_already_has() -> None:
    keep = TrackFactory(video_id="vid-a", duration=200).recording
    absorbed = TrackFactory(video_id="vid-b", duration=180).recording
    merge_recordings(keep, absorbed)
    keep.refresh_from_db()
    assert (keep.video_id, keep.duration) == ("vid-a", 200)


def test_merge_with_itself_is_refused() -> None:
    recording = TrackFactory().recording
    with pytest.raises(RecordingError, match="itself"):
        merge_recordings(recording, recording)


def test_merge_is_refused_when_both_are_on_the_same_album() -> None:
    album = AlbumFactory()
    first, second = TrackFactory(album=album), TrackFactory(album=album)
    with pytest.raises(RecordingError, match="same album"):
        merge_recordings(first.recording, second.recording)
    assert Recording.objects.count() == 2


def test_split_copies_the_recording_but_not_its_video() -> None:
    single = TrackFactory(video_id="vid", duration=200, explicit=True, credit=None)
    main, guest = ArtistFactory(), ArtistFactory()
    TrackArtistFactory(track=single, artist=main, position=0)
    TrackArtistFactory(track=single, artist=guest, position=1)
    on_album = TrackFactory(recording=single.recording, credit=None)

    copy = split_track(on_album)

    on_album.refresh_from_db()
    assert on_album.recording == copy != single.recording
    assert (copy.title, copy.duration, copy.explicit) == (single.recording.title, 200, True)
    # The video id is unique and stays with the original.
    assert copy.video_id is None
    assert list(copy.credits.values_list("artist", "position")) == [(main.pk, 0), (guest.pk, 1)]
    assert single.recording.credits.count() == 2


def test_split_is_refused_for_a_recording_with_one_track() -> None:
    track = TrackFactory()
    with pytest.raises(RecordingError, match="only track"):
        split_track(track)
    assert Recording.objects.count() == 1
