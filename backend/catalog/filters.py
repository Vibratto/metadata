"""Filters of the catalogue API."""

from typing import Any

from django.apps import apps
from django.db.models import Exists, F, Min, OuterRef, Q, QuerySet
from django.utils.translation import gettext as _
from django_filters import (  # type: ignore[import-untyped]
    BaseInFilter,
    BooleanFilter,
    CharFilter,
    ChoiceFilter,
    FilterSet,
    NumberFilter,
)
from rest_framework.exceptions import ValidationError

from .models import Album, Artist, Track


class NumberInFilter(BaseInFilter, NumberFilter):
    """One or several comma-separated ids, matching any of them."""


class RecordTypeFilter(CharFilter):
    """Comma-separated release types; an unknown one is a 400, not an empty list."""

    def filter(self, qs: QuerySet[Any], value: str) -> QuerySet[Any]:  # noqa: A003
        kinds = [v.strip() for v in (value or "").split(",") if v.strip()]
        if not kinds:
            return qs
        unknown = sorted(set(kinds) - set(Album.RecordType.values))
        if unknown:
            raise ValidationError({"record_type": [_("Unknown type: %s.") % unknown[0]]})
        return qs.filter(**{f"{self.field_name}__in": kinds})


class ArtistFilter(FilterSet):
    # ``track_count`` and ``pending_count`` are annotated by the view.
    has_downloads = BooleanFilter(method="filter_has_downloads")
    has_pending = BooleanFilter(method="filter_has_pending")
    watched = BooleanFilter(method="filter_watched")
    profile_only = BooleanFilter(method="filter_profile_only")
    related_to = NumberFilter(field_name="related_from")

    class Meta:
        model = Artist
        fields = {"name": ["icontains"], "ytmusic_id": ["exact"]}

    def filter_has_downloads(
        self, qs: QuerySet[Artist], name: str, value: bool
    ) -> QuerySet[Artist]:
        has = Q(track_count__gt=F("pending_count"))
        return qs.filter(has if value else ~has)

    def filter_has_pending(self, qs: QuerySet[Artist], name: str, value: bool) -> QuerySet[Artist]:
        has = Q(pending_count__gt=0)
        return qs.filter(has if value else ~has)

    def filter_watched(self, qs: QuerySet[Artist], name: str, value: bool) -> QuerySet[Artist]:
        entries = apps.get_model("watches", "WatchArtist").objects.filter(artist=OuterRef("pk"))
        return qs.filter(Exists(entries) if value else ~Exists(entries))

    def filter_profile_only(self, qs: Any, name: str, value: bool) -> Any:
        """``true``: related artists saved without music. ``false``: artists with music."""
        return qs.profiles_only() if value else qs.with_music()


class AlbumFilter(FilterSet):
    artist = NumberInFilter(field_name="credits__artist_id", distinct=True)
    record_type = RecordTypeFilter(field_name="record_type")
    year_from = NumberFilter(field_name="year", lookup_expr="gte")
    year_to = NumberFilter(field_name="year", lookup_expr="lte")
    download_status = ChoiceFilter(
        choices=[("complete", "complete"), ("partial", "partial"), ("none", "none")],
        method="filter_download_status",
    )

    class Meta:
        model = Album
        fields = {"title": ["icontains"], "ytmusic_id": ["exact"], "year": ["exact"]}

    # ``qs`` is ``Any`` because the counters are annotations the type checker cannot see.
    def filter_download_status(self, qs: Any, name: str, value: str) -> Any:
        """All, some or none of the tracks downloaded; an empty album counts as none."""
        if value == "complete":
            return qs.filter(track_count__gt=0, pending_count=0)
        if value == "none":
            return qs.filter(Q(track_count=0) | Q(pending_count=F("track_count")))
        return qs.filter(track_count__gt=0, pending_count__gt=0, pending_count__lt=F("track_count"))


class TrackFilter(FilterSet):
    album = NumberInFilter(field_name="album_id")
    artist = NumberInFilter(field_name="recording__credits__artist_id", distinct=True)
    video_id = CharFilter(field_name="recording__video_id")
    has_video = BooleanFilter(field_name="recording__video_id", lookup_expr="isnull", exclude=True)
    downloaded = BooleanFilter(field_name="downloaded")
    explicit = BooleanFilter(field_name="recording__explicit")
    record_type = RecordTypeFilter(field_name="album__record_type")
    year = NumberFilter(field_name="album__year")
    year_from = NumberFilter(field_name="album__year", lookup_expr="gte")
    year_to = NumberFilter(field_name="album__year", lookup_expr="lte")
    duration_min = NumberFilter(field_name="recording__duration", lookup_expr="gte")
    duration_max = NumberFilter(field_name="recording__duration", lookup_expr="lte")
    one_per_recording = BooleanFilter(method="filter_one_per_recording")

    class Meta:
        model = Track
        fields = {"title": ["icontains"]}

    def filter_one_per_recording(
        self, qs: QuerySet[Track], name: str, value: bool
    ) -> QuerySet[Track]:
        """With ``true``, only the first track of each recording: one row per song."""
        if not value:
            return qs
        first = Track.objects.values("recording").annotate(first=Min("pk")).values("first")
        return qs.filter(pk__in=first)
