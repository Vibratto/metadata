"""Serializers of the catalogue API.

External ids and audience figures come from YouTube Music and are read-only; only what
the user may correct is editable.
"""

from typing import Any, cast

from django.utils.translation import gettext as _
from rest_framework import serializers

from preferences.models import get_value

from .models import Album, Artist, BlockedItem, Recording, Track


class ArtistSerializer(serializers.ModelSerializer[Artist]):
    # Annotated by the list view; 0 when the object does not carry them.
    album_count = serializers.IntegerField(read_only=True, default=0)
    track_count = serializers.IntegerField(read_only=True, default=0)
    pending_count = serializers.IntegerField(read_only=True, default=0)
    suggest_import = serializers.SerializerMethodField(
        help_text="A profile without music whose audience reaches the suggestion threshold."
    )

    class Meta:
        model = Artist
        fields = [
            "id",
            "name",
            "image_url",
            "description",
            "ytmusic_id",
            "monthly_listeners",
            "subscribers",
            "album_count",
            "track_count",
            "pending_count",
            "suggest_import",
        ]
        read_only_fields = [f for f in fields if f not in ("name", "image_url", "description")]

    def get_suggest_import(self, artist: Artist) -> bool:
        has_music = getattr(artist, "album_count", 0) or getattr(artist, "track_count", 0)
        return (
            not has_music
            and bool(artist.ytmusic_id)
            and artist.audience >= get_value("import.suggestion_threshold")
        )


class CreditSerializer(serializers.Serializer[Any]):
    """One credited artist, in credit order."""

    id = serializers.IntegerField(source="artist_id")
    name = serializers.CharField(source="artist.name")
    position = serializers.IntegerField()


class AlbumSerializer(serializers.ModelSerializer[Album]):
    artists = CreditSerializer(source="credits", many=True, read_only=True)
    track_count = serializers.IntegerField(read_only=True, default=0)
    pending_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Album
        fields = [
            "id",
            "title",
            "year",
            "cover_url",
            "record_type",
            "artists",
            "ytmusic_id",
            "track_count",
            "pending_count",
        ]
        read_only_fields = [f for f in fields if f not in ("title", "year", "cover_url")]


class TrackSerializer(serializers.ModelSerializer[Track]):
    artists = CreditSerializer(source="credits", many=True, read_only=True)
    downloaded = serializers.BooleanField(read_only=True)
    also_on = serializers.IntegerField(
        read_only=True, default=0, help_text="Other albums holding the same recording."
    )
    copyable = serializers.BooleanField(
        read_only=True,
        default=False,
        help_text="Downloading it copies the audio already stored for another album.",
    )
    recording = serializers.IntegerField(source="recording_id", read_only=True)
    duration = serializers.IntegerField(read_only=True, allow_null=True, help_text="Seconds.")
    explicit = serializers.BooleanField(read_only=True)
    video_id = serializers.CharField(read_only=True, allow_null=True)
    cover_url = serializers.CharField(source="album.cover_url", read_only=True)

    class Meta:
        model = Track
        fields = [
            "id",
            "album",
            "recording",
            "title",
            "track_number",
            "disc_number",
            "duration",
            "explicit",
            "video_id",
            "artists",
            "downloaded",
            "also_on",
            "copyable",
            "cover_url",
        ]
        read_only_fields = [f for f in fields if f not in ("title", "track_number", "disc_number")]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Reject a position another track of the album already holds."""
        track = cast(Track, self.instance)  # tracks are edited through the API, never created
        disc = attrs.get("disc_number", track.disc_number)
        number = attrs.get("track_number", track.track_number)
        taken = Track.objects.filter(album=track.album, disc_number=disc, track_number=number)
        if taken.exclude(pk=track.pk).exists():
            raise serializers.ValidationError(
                {"track_number": _("Another track of the album already has that position.")}
            )
        return attrs


class RecordingTrackSerializer(serializers.ModelSerializer[Track]):
    """One appearance of a recording on an album."""

    album_title = serializers.CharField(source="album.title", read_only=True)
    downloaded = serializers.BooleanField(read_only=True)

    class Meta:
        model = Track
        fields = [
            "id",
            "album",
            "album_title",
            "title",
            "disc_number",
            "track_number",
            "downloaded",
        ]
        read_only_fields = fields


class RecordingSerializer(serializers.ModelSerializer[Recording]):
    artists = CreditSerializer(source="credits", many=True, read_only=True)
    tracks = RecordingTrackSerializer(many=True, read_only=True)
    track_count = serializers.IntegerField(read_only=True)
    downloaded = serializers.BooleanField(read_only=True)

    class Meta:
        model = Recording
        fields = [
            "id",
            "title",
            "duration",
            "explicit",
            "video_id",
            "artists",
            "track_count",
            "downloaded",
            "tracks",
        ]
        read_only_fields = fields


class RecordingMergeSerializer(serializers.Serializer[Any]):
    recording = serializers.PrimaryKeyRelatedField(
        queryset=Recording.objects.all(), help_text="Id of the recording to absorb."
    )


class ArtistIdsSerializer(serializers.Serializer[Any]):
    """Ordered list of artists; the first one is the main artist."""

    artists = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)

    def validate_artists(self, ids: list[int]) -> list[Artist]:
        if len(set(ids)) != len(ids):
            raise serializers.ValidationError(_("An artist is listed twice."))
        found = Artist.objects.in_bulk(ids)
        if len(found) != len(ids):
            raise serializers.ValidationError(_("One of the artists does not exist."))
        return [found[i] for i in ids]


class HistoryEntrySerializer(serializers.Serializer[Any]):
    """A past version of an item."""

    history_id = serializers.IntegerField()
    history_date = serializers.DateTimeField()
    history_type = serializers.CharField(help_text="+ created, ~ changed, - deleted.")
    history_user = serializers.CharField(allow_null=True)
    changes = serializers.DictField(help_text="Values of the editable fields.")


class RevertSerializer(serializers.Serializer[Any]):
    history_id = serializers.IntegerField()


class BlockedItemSerializer(serializers.ModelSerializer[BlockedItem]):
    class Meta:
        model = BlockedItem
        fields = ["id", "kind", "external_id", "name", "created_at"]
        read_only_fields = ["id", "created_at"]


class ArtistLookupQuerySerializer(serializers.Serializer[Any]):
    q = serializers.CharField(
        max_length=300, help_text="Artist name, channel id or YouTube Music artist link."
    )


class ArtistLookupResultSerializer(serializers.Serializer[Any]):
    """An artist found on YouTube Music."""

    ytmusic_id = serializers.CharField()
    name = serializers.CharField()
    image_url = serializers.CharField(allow_null=True)
    monthly_listeners = serializers.IntegerField(allow_null=True)
    subscribers = serializers.IntegerField(allow_null=True)
    album_count = serializers.IntegerField(
        allow_null=True, help_text="Only known when looking up a link or channel id."
    )
    single_count = serializers.IntegerField(allow_null=True)
    in_library = serializers.BooleanField(help_text="Already has music in the library.")
    blocked = serializers.BooleanField()


class ArtistLookupSerializer(serializers.Serializer[Any]):
    results = ArtistLookupResultSerializer(many=True)


class LibrarySummarySerializer(serializers.Serializer[Any]):
    artists = serializers.IntegerField(help_text="Artists with music.")
    related_artists = serializers.IntegerField(help_text="Profiles saved without music.")
    albums = serializers.IntegerField()
    recordings = serializers.IntegerField()
    tracks = serializers.IntegerField()
    downloaded = serializers.IntegerField(help_text="Tracks with at least one download.")
