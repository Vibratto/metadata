"""factory_boy factories for tests."""

from typing import Any

from factory.declarations import RelatedFactory, Sequence, SubFactory
from factory.django import DjangoModelFactory

from .models import Album, AlbumArtist, Artist, Download, Recording, RecordingArtist, Track


class ArtistFactory(DjangoModelFactory[Artist]):
    class Meta:
        model = Artist

    name = Sequence(lambda n: f"Artist {n}")
    ytmusic_id = Sequence(lambda n: f"UC{n:022d}")


class AlbumFactory(DjangoModelFactory[Album]):
    """Album with one main artist."""

    class Meta:
        model = Album
        skip_postgeneration_save = True

    title = Sequence(lambda n: f"Album {n}")
    ytmusic_id = Sequence(lambda n: f"MPREb_{n}")
    credit = RelatedFactory("catalog.factories.AlbumArtistFactory", factory_related_name="album")


class AlbumArtistFactory(DjangoModelFactory[AlbumArtist]):
    class Meta:
        model = AlbumArtist

    album = SubFactory(AlbumFactory, credit=None)
    artist = SubFactory(ArtistFactory)


class RecordingFactory(DjangoModelFactory[Recording]):
    """Recording with a video id and one main artist."""

    class Meta:
        model = Recording
        skip_postgeneration_save = True

    title = Sequence(lambda n: f"Track {n}")
    video_id = Sequence(lambda n: f"v{n:010d}")
    credit = RelatedFactory(
        "catalog.factories.RecordingArtistFactory", factory_related_name="recording"
    )


class RecordingArtistFactory(DjangoModelFactory[RecordingArtist]):
    class Meta:
        model = RecordingArtist

    recording = SubFactory(RecordingFactory, credit=None)
    artist = SubFactory(ArtistFactory)


class TrackFactory(DjangoModelFactory[Track]):
    """Track with its own recording and one main artist.

    ``video_id``, ``duration`` and ``explicit`` go to the new recording. To put a track on
    an existing recording pass ``recording=...`` and ``credit=None``.
    """

    class Meta:
        model = Track
        skip_postgeneration_save = True

    album = SubFactory(AlbumFactory)
    title = Sequence(lambda n: f"Track {n}")
    track_number = Sequence(lambda n: n + 1)
    video_id = Sequence(lambda n: f"t{n:010d}")
    duration = None
    explicit = False
    credit = RelatedFactory("catalog.factories.TrackArtistFactory", factory_related_name="track")

    @classmethod
    def _create(cls, model_class: type[Track], *args: Any, **kwargs: Any) -> Track:
        recording_fields = {k: kwargs.pop(k) for k in ("video_id", "duration", "explicit")}
        if "recording" not in kwargs:
            kwargs["recording"] = RecordingFactory(
                credit=None, title=kwargs["title"], **recording_fields
            )
        return model_class.objects.create(*args, **kwargs)


class TrackArtistFactory(RecordingArtistFactory):
    """Credit on a track's recording."""

    recording = None  # type: ignore[assignment]
    track = SubFactory(TrackFactory, credit=None)

    @classmethod
    def _create(cls, model_class: type[RecordingArtist], *args: Any, **kwargs: Any) -> Any:
        kwargs["recording"] = kwargs.pop("track").recording
        return super()._create(model_class, *args, **kwargs)


class DownloadFactory(DjangoModelFactory[Download]):
    class Meta:
        model = Download

    track = SubFactory(TrackFactory)
    file_path = Sequence(lambda n: f"Artist/{n}.mp3")
    audio_format = "mp3"
