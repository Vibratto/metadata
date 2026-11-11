"""Import of YouTube Music artists into the catalogue.

Safe to repeat: every row is looked up by its YouTube Music id before it is created, and
rows that exist are not overwritten, so manual edits survive and a second run only adds
what is new. Each release is saved in its own transaction, so a stopped or failed run
never leaves half an album behind.
"""

from collections import Counter
from typing import Any

import requests
from django.db import transaction
from django.db.models import Max
from django.utils.translation import gettext as _

from catalog.models import (
    Album,
    AlbumArtist,
    Artist,
    BlockedItem,
    Recording,
    RecordingArtist,
    Track,
)
from catalog.services.problems import report
from integrations import ytmusic as ytm
from integrations.ytmusic import YTMusicClient, YTMusicError
from jobs import runner
from jobs.models import JobRun
from proxies.routing import proxied_session

#: What a failed YouTube Music request can raise.
FETCH_ERRORS = (YTMusicError, requests.RequestException)


def ytmusic_client() -> YTMusicClient:
    """Client whose requests go out through the configured proxies."""
    return YTMusicClient(session=proxied_session())


class Importer:
    """Imports artists, their releases and their tracks inside a job run.

    Args:
        run: Receives progress and log lines.
        client: Source of YouTube Music data.
    """

    def __init__(self, run: JobRun, client: YTMusicClient) -> None:
        self.run = run
        self._client = client
        self._done = 0
        self._total = 0
        self.counts: Counter[str] = Counter()

    def import_artists(self, channel_ids: list[str]) -> bool:
        """Import several artists; one failing does not stop the others.

        Returns:
            ``False`` if a stop request cut the run short.
        """
        for channel_id in channel_ids:
            if runner.should_stop(self.run):
                return False
            try:
                if not self.import_artist(channel_id):
                    return False
            except FETCH_ERRORS as error:
                self.counts["failed_artists"] += 1
                report(self.run, _("Artist %(id)s") % {"id": channel_id}, error)
        return True

    def import_artist(self, channel_id: str) -> bool:
        """Import an artist's whole discography and save its related artists as profiles.

        Returns:
            ``False`` if a stop request arrived between releases.
        """
        if BlockedItem.blocks(BlockedItem.Kind.ARTIST, channel_id):
            self.counts["blocked"] += 1
            return True
        page = self._client.get_artist(channel_id)
        artist, created = Artist.objects.get_or_create(
            ytmusic_id=page.artist.id, defaults={"name": page.artist.name}
        )
        if created:
            self.counts["artists"] += 1
        update_profile(artist, page.artist)
        self._save_related(artist, page.related)

        self._total += len(page.releases)
        for release in page.releases:
            if runner.should_stop(self.run):
                return False
            self._done += 1
            runner.progress(self.run, self._done, self._total, release.title)
            self.try_import_release(release)
        return True

    def _save_related(self, artist: Artist, related: tuple[ytm.ArtistRef, ...]) -> None:
        """Save related artists as profiles only; their music is never imported here."""
        for ref in related:
            if BlockedItem.blocks(BlockedItem.Kind.ARTIST, ref.id):
                continue
            profile, created = Artist.objects.get_or_create(
                ytmusic_id=ref.id, defaults={"name": ref.name}
            )
            if created:
                self.counts["related_artists"] += 1
                self._complete(profile)
            artist.related.add(profile)

    def try_import_release(self, release: ytm.ReleaseRef) -> list[Track]:
        """Like :meth:`import_release`, but a fetch failure is logged instead of raised.

        One broken release must not cost the rest of the run. Nothing of it is saved,
        because the fetch happens before its transaction starts.
        """
        try:
            return self.import_release(release)
        except FETCH_ERRORS as error:
            self.counts["failed_albums"] += 1
            report(self.run, release.title, error)
            return []

    def import_release(self, release: ytm.ReleaseRef) -> list[Track]:
        """Import a release and its tracks unless it is blocked or already stored.

        Returns:
            The tracks created; empty when the release was skipped.
        """
        if BlockedItem.blocks(BlockedItem.Kind.ALBUM, release.id):
            self.counts["blocked"] += 1
            return []
        if Album.objects.filter(ytmusic_id=release.id).exists():
            self.counts["skipped_albums"] += 1
            return []
        remote = self._client.get_album(release.id)
        with transaction.atomic():
            album = Album.objects.create(
                ytmusic_id=remote.id,
                title=remote.title,
                year=remote.year or release.year,
                cover_url=remote.cover_url or release.cover_url or "",
                record_type=remote.kind,
            )
            self._credit(AlbumArtist, "album", album, remote.artists)
            created = self._create_tracks(album, remote.tracks)
        self.counts["albums"] += 1
        return created

    def complete_album(self, album: Album) -> list[Track]:
        """Create the tracks YouTube Music lists for a stored album and the catalogue lacks.

        Returns:
            The tracks created.
        """
        if not album.ytmusic_id:
            return []
        remote = self._client.get_album(album.ytmusic_id)
        stored = set(album.tracks.values_list("recording__video_id", flat=True))
        missing = tuple(t for t in remote.tracks if t.video_id and t.video_id not in stored)
        with transaction.atomic():
            return self._create_tracks(album, missing)

    def _create_tracks(self, album: Album, tracks: tuple[ytm.Track, ...]) -> list[Track]:
        return [
            self._create_track(album, track, index)
            for index, track in enumerate(tracks, start=1)
            if not BlockedItem.blocks(BlockedItem.Kind.TRACK, track.video_id)
        ]

    def _create_track(self, album: Album, remote: ytm.Track, index: int) -> Track:
        """Create the track, reusing the recording that already has its video id.

        The same song on a single and on its album is one recording with two tracks.
        """
        number = self._free_number(album, remote, index)
        recording = (
            Recording.objects.filter(video_id=remote.video_id).first() if remote.video_id else None
        )
        if recording is None:
            recording = Recording.objects.create(
                video_id=remote.video_id,
                title=remote.title,
                duration=remote.duration,
                explicit=remote.explicit,
            )
            self._credit(RecordingArtist, "recording", recording, remote.artists)
        else:
            self.counts["reused_recordings"] += 1
        self.counts["tracks"] += 1
        return Track.objects.create(
            album=album, recording=recording, title=remote.title, track_number=number
        )

    def _free_number(self, album: Album, remote: ytm.Track, index: int) -> int:
        """The track's position, or the next free one when that position is taken.

        YouTube Music repeats or omits numbers on some releases, and a position holds a
        single track.
        """
        wanted = remote.position or index
        on_disc = Track.objects.filter(album=album, disc_number=1)
        if not on_disc.filter(track_number=wanted).exists():
            return wanted
        number = (on_disc.aggregate(last=Max("track_number"))["last"] or 0) + 1
        return number

    def _credit(
        self,
        model: type[AlbumArtist] | type[RecordingArtist],
        field: str,
        owner: Any,
        refs: tuple[ytm.ArtistRef, ...],
    ) -> None:
        """Create the credits in order, leaving blocked artists out."""
        position = 0
        for ref in refs:
            artist = self._artist_for(ref)
            if artist is not None:
                model.objects.get_or_create(
                    **{field: owner, "artist": artist}, defaults={"position": position}
                )
                position += 1

    def _artist_for(self, ref: ytm.ArtistRef) -> Artist | None:
        """Find or create a credited artist; ``None`` when it is blocked.

        A guest named only in a title has no channel id and is matched by name.
        """
        if ref.id is None:
            artist = Artist.objects.filter(name__iexact=ref.name).first()
            return artist or Artist.objects.create(name=ref.name)
        if BlockedItem.blocks(BlockedItem.Kind.ARTIST, ref.id):
            return None
        artist, created = Artist.objects.get_or_create(
            ytmusic_id=ref.id, defaults={"name": ref.name}
        )
        if created:
            self._complete(artist)
        return artist

    def _complete(self, artist: Artist) -> None:
        """Fetch a new artist's profile; a failure only warns.

        The "complete artists" maintenance operation retries it later.
        """
        try:
            self.complete_artist(artist)
        except FETCH_ERRORS as error:
            report(self.run, artist.name, error)

    def complete_artist(self, artist: Artist) -> None:
        """Fill in an artist's profile from YouTube Music; never imports its music.

        An artist without a channel id is left alone: looking it up by name could attach
        a namesake's picture.
        """
        if artist.ytmusic_id:
            update_profile(artist, self._client.get_artist_profile(artist.ytmusic_id))


def update_profile(artist: Artist, remote: ytm.Artist) -> None:
    """Refresh audience figures and fill in the image and description if they are empty.

    Figures follow YouTube Music whenever it reports them. Image and description are only
    filled in, never replaced, because they may have been edited by hand. Nothing is
    saved when nothing changed, so repeated imports add no history entries.
    """
    values = {
        "monthly_listeners": remote.monthly_listeners or artist.monthly_listeners,
        "subscribers": remote.subscribers or artist.subscribers,
        "image_url": artist.image_url or remote.image_url or "",
        "description": artist.description or remote.description or "",
    }
    changed = [name for name, value in values.items() if getattr(artist, name) != value]
    for name in changed:
        setattr(artist, name, values[name])
    if changed:
        artist.save(update_fields=changed)
