"""Catalogue models: identifiers, counters, orphan recordings and the block list."""

import pytest
from django.db import IntegrityError
from django.db.models import ProtectedError

from catalog.factories import (
    AlbumArtistFactory,
    AlbumFactory,
    ArtistFactory,
    DownloadFactory,
    RecordingFactory,
    TrackArtistFactory,
    TrackFactory,
)
from catalog.models import (
    Album,
    Artist,
    BlockedItem,
    Download,
    ImmutableFieldError,
    Recording,
    Track,
)
from core.models import AppendOnlyError

pytestmark = pytest.mark.django_db


def test_text_of_each_model() -> None:
    track = TrackFactory(title="Song", album__title="Album")
    credit = track.album.credits.get()
    assert (str(track), str(track.album), str(track.recording)) == ("Song", "Album", "Song")
    assert str(credit) == f"Album / {credit.artist.name}"
    assert str(track.recording.credits.get()).startswith("Song / ")
    assert str(BlockedItem(kind="album", external_id="MPREb_1")) == "album:MPREb_1"
    assert str(DownloadFactory(file_path="a/b.mp3")) == "a/b.mp3"


@pytest.mark.parametrize(
    ("factory", "field"),
    [(ArtistFactory, "ytmusic_id"), (AlbumFactory, "ytmusic_id"), (RecordingFactory, "video_id")],
)
def test_assigned_external_id_cannot_change_or_be_cleared(factory: type, field: str) -> None:
    item = factory()
    original = getattr(item, field)
    for value in ("other", None):
        setattr(item, field, value)
        with pytest.raises(ImmutableFieldError):
            item.save()
    item.refresh_from_db()
    assert getattr(item, field) == original


def test_missing_external_id_can_be_assigned_once() -> None:
    artist = Artist.objects.create(name="Guest named in a title")
    artist.ytmusic_id = "UCguest"
    artist.save()
    artist.refresh_from_db()
    assert artist.ytmusic_id == "UCguest"


def test_other_fields_stay_editable() -> None:
    artist = ArtistFactory(name="Before")
    artist.name = "After"
    artist.save()
    assert Artist.objects.get(pk=artist.pk).name == "After"


@pytest.mark.parametrize(
    ("factory", "field"),
    [(ArtistFactory, "ytmusic_id"), (AlbumFactory, "ytmusic_id"), (RecordingFactory, "video_id")],
)
def test_external_ids_are_unique_but_may_be_missing(factory: type, field: str) -> None:
    factory(**{field: None})
    factory(**{field: None})
    factory(**{field: "same"})
    with pytest.raises(IntegrityError):
        factory(**{field: "same"})


def test_audience_prefers_monthly_listeners() -> None:
    assert Artist(monthly_listeners=5, subscribers=9).audience == 5
    assert Artist(subscribers=9).audience == 9
    assert Artist().audience == 0


def test_artist_counters_do_not_multiply_each_other() -> None:
    artist = ArtistFactory()
    for _ in range(2):
        AlbumArtistFactory(artist=artist)
    downloaded = TrackFactory(credit=None)
    pending = [TrackFactory(credit=None) for _ in range(2)]
    for track in (downloaded, *pending):
        TrackArtistFactory(track=track, artist=artist)
    DownloadFactory(track=downloaded)
    DownloadFactory(track=downloaded)  # a second file of the same track counts once

    counted = Artist.objects.with_counts().get(pk=artist.pk)

    assert (counted.album_count, counted.track_count, counted.pending_count) == (2, 3, 2)


def test_artist_with_nothing_counts_zero() -> None:
    counted = Artist.objects.with_counts().get(pk=ArtistFactory().pk)
    assert (counted.album_count, counted.track_count, counted.pending_count) == (0, 0, 0)


def test_profiles_are_artists_without_any_credit() -> None:
    profile = ArtistFactory(name="Profile")
    on_album = AlbumFactory().credits.get().artist
    on_track = TrackFactory().credits.get().artist
    assert list(Artist.objects.profiles_only()) == [profile]
    assert set(Artist.objects.with_music()) >= {on_album, on_track}
    assert profile not in Artist.objects.with_music()


def test_related_artists_point_one_way() -> None:
    main, related = ArtistFactory(), ArtistFactory()
    main.related.add(related)
    assert list(main.related.all()) == [related]
    assert list(related.related.all()) == []
    assert list(related.related_from.all()) == [main]


def test_album_counters() -> None:
    album = AlbumFactory()
    done, _pending = TrackFactory(album=album), TrackFactory(album=album)
    DownloadFactory(track=done)
    counted = Album.objects.with_counts().get(pk=album.pk)
    assert (counted.track_count, counted.pending_count) == (2, 1)


def test_track_reads_through_to_its_recording() -> None:
    track = TrackFactory(video_id="vid", duration=200, explicit=True)
    assert (track.video_id, track.duration, track.explicit) == ("vid", 200, True)
    assert list(track.artists.all()) == list(track.recording.artists.all())
    assert not track.is_downloaded
    DownloadFactory(track=track)
    assert track.is_downloaded


def test_track_annotations() -> None:
    single = TrackFactory()
    on_album = TrackFactory(recording=single.recording, credit=None)
    DownloadFactory(track=single)
    rows = {t.pk: t for t in Track.objects.with_downloaded().with_copyable().with_also_on()}
    assert (rows[single.pk].downloaded, rows[single.pk].copyable) == (True, False)
    assert (rows[on_album.pk].downloaded, rows[on_album.pk].copyable) == (False, True)
    assert rows[single.pk].also_on == rows[on_album.pk].also_on == 1


def test_position_on_an_album_holds_one_track() -> None:
    track = TrackFactory(track_number=1)
    with pytest.raises(IntegrityError):
        TrackFactory(album=track.album, track_number=1)


def test_recording_goes_with_its_last_track() -> None:
    single = TrackFactory()
    on_album = TrackFactory(recording=single.recording, credit=None)
    single.delete()
    assert Recording.objects.filter(pk=on_album.recording_id).exists()
    on_album.delete()
    assert not Recording.objects.exists()


def test_recording_with_tracks_cannot_be_deleted() -> None:
    with pytest.raises(ProtectedError):
        TrackFactory().recording.delete()


def test_downloaded_track_cannot_be_deleted() -> None:
    download = DownloadFactory()
    with pytest.raises(ProtectedError):
        download.track.delete()


def test_download_is_append_only() -> None:
    download = DownloadFactory()
    download.file_path = "elsewhere.mp3"
    with pytest.raises(AppendOnlyError):
        download.save()
    with pytest.raises(AppendOnlyError):
        Download.objects.all().delete()


def test_block_list_matches_kind_and_id() -> None:
    BlockedItem.objects.create(kind="album", external_id="MPREb_1")
    assert BlockedItem.blocks("album", "MPREb_1")
    assert not BlockedItem.blocks("artist", "MPREb_1")
    assert not BlockedItem.blocks("album", "MPREb_2")
    assert not BlockedItem.blocks("album", None)
    with pytest.raises(IntegrityError):
        BlockedItem.objects.create(kind="album", external_id="MPREb_1")


def test_changes_are_kept_in_history() -> None:
    artist = ArtistFactory(name="Before")
    artist.name = "After"
    artist.save()
    assert list(artist.history.values_list("name", flat=True)) == ["After", "Before"]
