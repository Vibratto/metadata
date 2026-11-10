"""Music catalogue models.

Nothing is stored twice: an album or artist name lives in its own row and tracks reach it
through relations. Whether a track is downloaded is derived from ``Download`` rows, never
kept as a flag.
"""

from typing import Any, ClassVar

from django.db import models
from django.db.models import Exists, OuterRef
from django.db.models.functions import Coalesce
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from core.models import AppendOnlyModel


class ImmutableFieldError(Exception):
    """An external identifier that was already assigned was changed."""


class ExternalIdModel(models.Model):
    """Base for models that carry an identifier assigned by YouTube Music.

    The identifier can be set once: ``None`` to a value is fine (a guest known only by
    name is later matched to a channel), but changing or clearing it is not, because
    imports find existing rows by it.
    """

    #: Fields ``save()`` refuses to change once they hold a value.
    immutable_fields: ClassVar[tuple[str, ...]] = ()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Save, raising ``ImmutableFieldError`` if an assigned identifier changes."""
        if not self._state.adding and self.immutable_fields:
            stored = (
                type(self)
                ._default_manager.filter(pk=self.pk)
                .values_list(*self.immutable_fields)
                .first()
            )
            for name, old in zip(self.immutable_fields, stored or (), strict=True):
                if old is not None and old != getattr(self, name):
                    raise ImmutableFieldError(
                        _("The field %(field)s cannot be changed.") % {"field": name}
                    )
        super().save(*args, **kwargs)


def _count(queryset: models.QuerySet[Any], key: str) -> Coalesce:
    """Count as a subquery, so it never multiplies rows through other joins."""
    counted = queryset.order_by().values(key).annotate(n=models.Count("pk")).values("n")
    return Coalesce(models.Subquery(counted, output_field=models.IntegerField()), 0)


class ArtistQuerySet(models.QuerySet["Artist"]):
    def with_counts(self) -> "ArtistQuerySet":
        """Annotate ``album_count``, ``track_count`` and ``pending_count``."""
        tracks = Track.objects.filter(recording__credits__artist=OuterRef("pk"))
        pending = tracks.filter(~Exists(Download.objects.filter(track=OuterRef("pk"))))
        return self.annotate(
            album_count=_count(AlbumArtist.objects.filter(artist=OuterRef("pk")), "artist"),
            track_count=_count(tracks, "recording__credits__artist"),
            pending_count=_count(pending, "recording__credits__artist"),
        )

    def with_music(self) -> "ArtistQuerySet":
        """Artists credited on at least one album or recording."""
        return self.filter(self._has_music())

    def profiles_only(self) -> "ArtistQuerySet":
        """Artists saved as a profile, with no album or recording to their name."""
        return self.exclude(self._has_music())

    @staticmethod
    def _has_music() -> models.Q:
        return models.Q(Exists(AlbumArtist.objects.filter(artist=OuterRef("pk")))) | models.Q(
            Exists(RecordingArtist.objects.filter(artist=OuterRef("pk")))
        )


class Artist(ExternalIdModel):
    """An artist.

    Related artists are saved as profiles: a row here with no credits. Importing their
    discography later turns them into regular library artists.
    """

    immutable_fields = ("ytmusic_id",)

    ytmusic_id = models.CharField(
        max_length=64, null=True, blank=True, unique=True, help_text=_("Channel id.")
    )
    name = models.CharField(max_length=255, db_index=True)
    image_url = models.URLField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    monthly_listeners = models.PositiveBigIntegerField(null=True, blank=True)
    subscribers = models.PositiveBigIntegerField(null=True, blank=True)
    related = models.ManyToManyField(
        "self", symmetrical=False, related_name="related_from", blank=True
    )
    history = HistoricalRecords()

    objects = ArtistQuerySet.as_manager()

    def __str__(self) -> str:
        return self.name

    @property
    def audience(self) -> int:
        """Size estimate used to suggest a discography import."""
        return self.monthly_listeners or self.subscribers or 0


class AlbumQuerySet(models.QuerySet["Album"]):
    def with_counts(self) -> "AlbumQuerySet":
        """Annotate ``track_count`` and ``pending_count``."""
        tracks = Track.objects.filter(album=OuterRef("pk"))
        pending = tracks.filter(~Exists(Download.objects.filter(track=OuterRef("pk"))))
        return self.annotate(
            track_count=_count(tracks, "album"), pending_count=_count(pending, "album")
        )


class Album(ExternalIdModel):
    """A release: album, single or EP. Its artists are ``AlbumArtist`` rows."""

    class RecordType(models.TextChoices):
        ALBUM = "album", _("Album")
        SINGLE = "single", _("Single")
        EP = "ep", _("EP")

    immutable_fields = ("ytmusic_id",)

    ytmusic_id = models.CharField(
        max_length=64, null=True, blank=True, unique=True, help_text=_("Browse id.")
    )
    title = models.CharField(max_length=255, db_index=True)
    # YouTube Music only publishes the release year.
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    cover_url = models.URLField(max_length=500, blank=True)
    record_type = models.CharField(
        max_length=20, choices=RecordType.choices, default=RecordType.ALBUM
    )
    artists = models.ManyToManyField(Artist, through="AlbumArtist", related_name="albums")
    history = HistoricalRecords()

    objects = AlbumQuerySet.as_manager()

    def __str__(self) -> str:
        return self.title


class AlbumArtist(models.Model):
    """An album credit and its position."""

    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name="credits")
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name="album_credits")
    position = models.PositiveSmallIntegerField(default=0)
    history = HistoricalRecords()

    class Meta:
        ordering = ["album", "position"]
        constraints = [
            models.UniqueConstraint(fields=["album", "artist"], name="unique_album_artist")
        ]

    def __str__(self) -> str:
        return f"{self.album} / {self.artist}"


class Recording(ExternalIdModel):
    """What plays, whichever release it appears on.

    The YouTube Music video id identifies it: a single and the album that includes it
    usually share the video, and then they share the recording and its audio file.
    ``video_id`` is ``None`` for tracks YouTube Music lists but cannot play, and for
    files imported from a folder that matched nothing.
    """

    immutable_fields = ("video_id",)

    video_id = models.CharField(max_length=11, null=True, blank=True, unique=True)
    title = models.CharField(max_length=255, db_index=True)
    duration = models.PositiveIntegerField(null=True, blank=True, help_text=_("Seconds."))
    explicit = models.BooleanField(default=False)
    artists = models.ManyToManyField(Artist, through="RecordingArtist", related_name="recordings")
    history = HistoricalRecords()

    def __str__(self) -> str:
        return self.title


class RecordingArtist(models.Model):
    """A recording credit and its position: main artist first, then guests."""

    recording = models.ForeignKey(Recording, on_delete=models.CASCADE, related_name="credits")
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name="recording_credits")
    position = models.PositiveSmallIntegerField(default=0)
    history = HistoricalRecords()

    class Meta:
        ordering = ["recording", "position"]
        constraints = [
            models.UniqueConstraint(fields=["recording", "artist"], name="unique_recording_artist")
        ]

    def __str__(self) -> str:
        return f"{self.recording} / {self.artist}"


class TrackQuerySet(models.QuerySet["Track"]):
    def with_downloaded(self) -> "TrackQuerySet":
        """Annotate ``downloaded`` from the ``Download`` rows."""
        return self.annotate(downloaded=Exists(Download.objects.filter(track=OuterRef("pk"))))

    def with_copyable(self) -> "TrackQuerySet":
        """Annotate ``copyable``: another track of the same recording is downloaded.

        Downloading a copyable track copies that file instead of fetching the audio again.
        """
        sibling = (
            Track.objects.filter(recording=OuterRef("recording"), download__isnull=False)
            .exclude(pk=OuterRef("pk"))
            .order_by()
        )
        return self.annotate(copyable=Exists(sibling))

    def with_also_on(self) -> "TrackQuerySet":
        """Annotate ``also_on``: how many other releases hold the same recording."""
        others = Track.objects.filter(recording=OuterRef("recording")).exclude(pk=OuterRef("pk"))
        return self.annotate(also_on=_count(others, "recording"))


class Track(models.Model):
    """The appearance of a recording on a release."""

    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name="tracks")
    recording = models.ForeignKey(Recording, on_delete=models.PROTECT, related_name="tracks")
    title = models.CharField(max_length=255, db_index=True)
    track_number = models.PositiveSmallIntegerField(default=1)
    disc_number = models.PositiveSmallIntegerField(default=1)
    history = HistoricalRecords()

    objects = TrackQuerySet.as_manager()

    class Meta:
        ordering = ["album", "disc_number", "track_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["album", "disc_number", "track_number"], name="unique_track_position"
            )
        ]

    def __str__(self) -> str:
        return self.title

    @property
    def video_id(self) -> str | None:
        return self.recording.video_id

    @property
    def duration(self) -> int | None:
        return self.recording.duration

    @property
    def explicit(self) -> bool:
        return self.recording.explicit

    @property
    def credits(self) -> Any:
        return self.recording.credits

    @property
    def artists(self) -> Any:
        return self.recording.artists

    @property
    def is_downloaded(self) -> bool:
        return Download.objects.filter(track=self).exists()


@receiver(post_delete, sender=Track)
def _drop_orphan_recording(sender: type[Track], instance: Track, **kwargs: Any) -> None:
    """Delete a recording once its last track is gone."""
    Recording.objects.filter(pk=instance.recording_id, tracks__isnull=True).delete()


class BlockedItem(models.Model):
    """A YouTube Music item that must never be imported.

    It stores the external id rather than a foreign key, so an item can be blocked before
    it was ever imported and stays blocked after its row is deleted.
    """

    class Kind(models.TextChoices):
        ARTIST = "artist", _("Artist")
        ALBUM = "album", _("Album")
        TRACK = "track", _("Track")

    kind = models.CharField(max_length=10, choices=Kind.choices)
    external_id = models.CharField(
        max_length=64, help_text=_("Channel id, browse id or video id, depending on the kind.")
    )
    name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kind", "external_id"], name="unique_blocked_item")
        ]

    def __str__(self) -> str:
        return f"{self.kind}:{self.external_id}"

    @classmethod
    def blocks(cls, kind: str, external_id: str | None) -> bool:
        """Whether the item with this external id is blocked."""
        return bool(external_id) and cls.objects.filter(kind=kind, external_id=external_id).exists()


class Download(AppendOnlyModel):
    """A completed download of a track.

    Append-only. ``PROTECT`` keeps a downloaded track from being deleted, which would
    orphan the file on disk.
    """

    track = models.ForeignKey(Track, on_delete=models.PROTECT)
    file_path = models.CharField(max_length=1000)
    audio_format = models.CharField(max_length=10)
    source_url = models.URLField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.file_path


class Loudness(models.Model):
    """A loudness measurement, kept so ReplayGain tags can be rewritten without measuring."""

    lufs = models.FloatField(help_text=_("Integrated loudness (LUFS)."))
    peak = models.FloatField(help_text=_("True peak; 1 is full scale."))

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return f"{self.pk}: {self.lufs} LUFS"


class DownloadLoudness(Loudness):
    """Loudness of a downloaded file.

    Separate from ``Download`` because that table is append-only and a file can be
    measured again.
    """

    download = models.OneToOneField(
        Download, on_delete=models.CASCADE, primary_key=True, related_name="loudness"
    )


class AlbumLoudness(Loudness):
    """Loudness of an album: its downloaded tracks played back to back."""

    album = models.OneToOneField(
        Album, on_delete=models.CASCADE, primary_key=True, related_name="loudness"
    )
