"""A track's tags, built from the catalogue.

Downloading, uploading and retagging all go through here, so the three always write the
same tags. ``integrations.audio`` only ever receives the finished ``Tags``.
"""

from django.db.models import Max

from catalog.models import Album, AlbumLoudness, Download, DownloadLoudness, Track
from integrations.audio import Loudness, ReplayGain, Tags, replaygain
from preferences.models import get_value

# YouTube Music credits compilations to this name, with no channel behind it.
VARIOUS_ARTISTS = "various artists"


def _replaygain(track: Track, loudness: Loudness | None) -> ReplayGain | None:
    """ReplayGain for ``track``; ``None`` when turned off or not measured yet.

    Without a measurement passed in, only the latest download's counts: one taken from
    an older file is stale.
    """
    if not get_value("replaygain.enabled"):
        return None
    if loudness is None:
        latest = Download.objects.filter(track=track).order_by("-pk").values("pk")[:1]
        stored = DownloadLoudness.objects.filter(download__in=latest).first()
        if stored is None:
            return None
        loudness = Loudness(lufs=stored.lufs, peak=stored.peak)
    album = AlbumLoudness.objects.filter(album_id=track.album_id).first()
    return replaygain(loudness, Loudness(lufs=album.lufs, peak=album.peak) if album else None)


def _artist_ids(album: Album) -> list[int]:
    return list(album.credits.order_by("position").values_list("artist", flat=True))


def _album_version(album: Album) -> str | None:
    """Version that tells ``album`` apart from one a player would merge it with.

    Navidrome groups albums by album artists, title and release date. Two albums that
    share all three need distinct versions: "Explicit" or "Clean" when that alone
    separates them, otherwise the album's own id. ``None`` when there is no such twin,
    so most albums keep a clean title.
    """
    artists = _artist_ids(album)
    candidates = Album.objects.filter(year=album.year).exclude(pk=album.pk)
    if artists:
        candidates = candidates.filter(credits__artist=artists[0], credits__position=0)
    # Compared in Python because SQLite only folds ASCII case.
    title = album.title.casefold()
    twins = [
        twin
        for twin in candidates
        if twin.title.casefold() == title and _artist_ids(twin) == artists
    ]
    if not twins:
        return None
    explicit = album.tracks.filter(recording__explicit=True).exists()
    if all(twin.tracks.filter(recording__explicit=True).exists() != explicit for twin in twins):
        return "Explicit" if explicit else "Clean"
    # Albums imported from a folder have no YouTube Music id; the primary key is unique too.
    return album.ytmusic_id or f"Vibratto {album.pk}"


def tags_for(track: Track, *, cover: bytes | None = None, loudness: Loudness | None = None) -> Tags:
    """Build every tag of ``track``.

    Args:
        track: Catalogue track.
        cover: Cover image to embed, if any.
        loudness: Measurement of the file about to be stored; defaults to the stored one.
    """
    album = track.album
    artists = tuple(track.credits.order_by("position").values_list("artist__name", flat=True))
    album_artists = tuple(album.credits.order_by("position").values_list("artist__name", flat=True))
    return Tags(
        title=track.title,
        artists=artists,
        album=album.title,
        album_artists=album_artists,
        track_number=track.track_number,
        track_total=album.tracks.filter(disc_number=track.disc_number).count(),
        disc_number=track.disc_number,
        disc_total=album.tracks.aggregate(last=Max("disc_number"))["last"],
        year=album.year,
        release_type=album.record_type or None,
        explicit=track.explicit,
        compilation=any(name.casefold() == VARIOUS_ARTISTS for name in album_artists),
        album_version=_album_version(album),
        replaygain=_replaygain(track, loudness),
        cover=cover,
        joiner=get_value("tags.artist_separators")[0],
    )
