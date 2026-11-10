"""Tags built from the catalogue."""

from typing import Any

import pytest

from catalog.factories import AlbumFactory, ArtistFactory, DownloadFactory, TrackFactory
from catalog.models import AlbumLoudness, DownloadLoudness, Track
from catalog.services.tagging import tags_for
from integrations.audio import Loudness
from preferences.models import Preference

pytestmark = pytest.mark.django_db


def _credit(owner: Any, names: tuple[str, ...]) -> None:
    # Created in reverse, so credit order cannot be mistaken for creation order.
    for position, name in reversed(list(enumerate(names))):
        owner.credits.create(artist=ArtistFactory(name=name), position=position)


def _album(*artists: str, **fields: Any) -> Any:
    album = AlbumFactory(credit=None, **fields)
    _credit(album, artists)
    return album


def _track(album: Any, *artists: str, **fields: Any) -> Track:
    track = TrackFactory(album=album, credit=None, **fields)
    _credit(track, artists)
    return Track.objects.get(pk=track.pk)


def test_every_field_comes_from_the_catalogue_in_credit_order() -> None:
    album = _album("Rosalía", "The Weeknd", title="Motomami", year=2022, record_type="album")
    track = _track(album, "Rosalía", "The Weeknd", title="La Fama", track_number=2, explicit=True)

    tags = tags_for(track)

    assert (tags.title, tags.album) == ("La Fama", "Motomami")
    assert tags.artists == ("Rosalía", "The Weeknd")
    assert tags.album_artists == ("Rosalía", "The Weeknd")
    assert (tags.track_number, tags.disc_number) == (2, 1)
    assert (tags.year, tags.date_text) == (2022, "2022")
    assert (tags.release_type, tags.explicit, tags.compilation) == ("album", True, False)
    assert tags.album_version is None
    assert tags.cover is None


def test_album_without_a_year_has_no_date() -> None:
    tags = tags_for(_track(_album("A", year=None), "A"))
    assert (tags.year, tags.date_text) == (None, None)


def test_totals_count_the_tracks_of_the_disc_and_the_last_disc() -> None:
    album = AlbumFactory()
    for disc, number in ((1, 1), (1, 2), (1, 3), (2, 1), (2, 2)):
        TrackFactory(album=album, disc_number=disc, track_number=number)
    first_disc = Track.objects.get(album=album, disc_number=1, track_number=3)
    second_disc = Track.objects.get(album=album, disc_number=2, track_number=1)
    assert (tags_for(first_disc).track_total, tags_for(first_disc).disc_total) == (3, 2)
    assert (tags_for(second_disc).track_total, tags_for(second_disc).disc_total) == (2, 2)


@pytest.mark.parametrize(
    ("album_artist", "compilation"),
    [("Various Artists", True), ("VARIOUS ARTISTS", True), ("Various", False)],
)
def test_album_by_various_artists_is_a_compilation(album_artist: str, compilation: bool) -> None:
    track = _track(_album(album_artist), "Someone")
    assert tags_for(track).compilation is compilation


def test_cover_is_passed_through() -> None:
    assert tags_for(TrackFactory(), cover=b"jpeg").cover == b"jpeg"


def test_first_separator_joins_the_artists() -> None:
    track = _track(_album("Rosalía"), "Rosalía", "The Weeknd")
    assert tags_for(track).joined(tags_for(track).artists) == "Rosalía / The Weeknd"
    Preference.objects.create(key="tags.artist_separators", value=["; ", " / "])
    assert tags_for(track).joined(tags_for(track).artists) == "Rosalía; The Weeknd"
    assert tags_for(track).artists == ("Rosalía", "The Weeknd")


# --- Album version: tells apart albums a player would merge ---


def _twins(*, explicit: tuple[bool, bool]) -> tuple[Track, Track]:
    """One track on each of two albums with the same artist, title and year."""
    artist = ArtistFactory(name="Twin")
    tracks = []
    for flag in explicit:
        album = AlbumFactory(credit=None, title="Same", year=2020)
        album.credits.create(artist=artist, position=0)
        tracks.append(TrackFactory(album=album, explicit=flag))
    return tracks[0], tracks[1]


def test_album_without_a_twin_has_no_version() -> None:
    assert tags_for(TrackFactory()).album_version is None


def test_explicit_and_clean_twins_are_named_after_that() -> None:
    explicit, clean = _twins(explicit=(True, False))
    assert tags_for(explicit).album_version == "Explicit"
    assert tags_for(clean).album_version == "Clean"


def test_twins_that_explicitness_cannot_separate_use_their_id() -> None:
    first, second = _twins(explicit=(False, False))
    assert tags_for(first).album_version == first.album.ytmusic_id
    assert tags_for(second).album_version == second.album.ytmusic_id
    assert first.album.ytmusic_id != second.album.ytmusic_id


def test_twin_without_a_youtube_music_id_uses_its_own_key() -> None:
    first, second = _twins(explicit=(False, False))
    type(first.album).objects.filter(pk=first.album.pk).update(ytmusic_id=None)
    first.album.refresh_from_db()
    assert tags_for(first).album_version == f"Vibratto {first.album.pk}"


@pytest.mark.parametrize("difference", [{"title": "Other"}, {"year": 2021}], ids=["title", "year"])
def test_albums_that_differ_in_title_or_year_are_not_twins(difference: dict[str, Any]) -> None:
    first, second = _twins(explicit=(False, False))
    type(second.album).objects.filter(pk=second.album.pk).update(**difference)
    assert tags_for(first).album_version is None


def test_title_case_does_not_separate_twins() -> None:
    first, second = _twins(explicit=(True, False))
    type(second.album).objects.filter(pk=second.album.pk).update(title="SAME")
    assert tags_for(first).album_version == "Explicit"


def test_albums_with_different_artists_are_not_twins() -> None:
    first, second = _twins(explicit=(False, False))
    second.album.credits.create(artist=ArtistFactory(), position=1)
    assert tags_for(first).album_version is None


# --- ReplayGain ---


def test_no_replaygain_until_the_file_is_measured() -> None:
    assert tags_for(TrackFactory()).replaygain is None


def test_replaygain_from_the_measurement_passed_in() -> None:
    gain = tags_for(TrackFactory(), loudness=Loudness(lufs=-14.0, peak=0.5)).replaygain
    assert gain is not None
    assert (gain.track_gain_db, gain.track_peak) == (-4.0, 0.5)
    assert gain.album_gain_db is None


def test_replaygain_from_the_latest_download_and_the_album() -> None:
    track = TrackFactory()
    old, new = DownloadFactory(track=track), DownloadFactory(track=track)
    DownloadLoudness.objects.create(download=old, lufs=-30.0, peak=0.1)
    DownloadLoudness.objects.create(download=new, lufs=-16.0, peak=0.8)
    AlbumLoudness.objects.create(album=track.album, lufs=-20.0, peak=0.9)

    gain = tags_for(track).replaygain

    assert gain is not None
    assert (gain.track_gain_db, gain.track_peak) == (-2.0, 0.8)
    assert (gain.album_gain_db, gain.album_peak) == (2.0, 0.9)


def test_measurement_of_an_older_file_is_not_used() -> None:
    track = TrackFactory()
    old = DownloadFactory(track=track)
    DownloadFactory(track=track)
    DownloadLoudness.objects.create(download=old, lufs=-30.0, peak=0.1)
    assert tags_for(track).replaygain is None


def test_no_replaygain_when_turned_off() -> None:
    Preference.objects.create(key="replaygain.enabled", value=False)
    assert tags_for(TrackFactory(), loudness=Loudness(lufs=-14.0, peak=0.5)).replaygain is None
