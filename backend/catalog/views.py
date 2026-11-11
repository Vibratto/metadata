"""Views of the catalogue API.

Every change is written to the activity log and, through django-simple-history, to the
item's own history.
"""

import logging
from typing import Any, ClassVar, cast

from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models import Count, Exists, OuterRef, Prefetch
from django.utils.translation import gettext as _
from django_filters.rest_framework import DjangoFilterBackend  # type: ignore[import-untyped]
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView
from simple_history.utils import bulk_create_with_history

from activity.services import log_activity
from core.serializers import DetailSerializer
from integrations import ytmusic as ytm

from .filters import AlbumFilter, ArtistFilter, TrackFilter
from .models import Album, Artist, BlockedItem, Download, Recording, Track
from .serializers import (
    AlbumSerializer,
    ArtistIdsSerializer,
    ArtistLookupQuerySerializer,
    ArtistLookupSerializer,
    ArtistSerializer,
    BlockedItemSerializer,
    HistoryEntrySerializer,
    LibrarySummarySerializer,
    RecordingMergeSerializer,
    RecordingSerializer,
    RevertSerializer,
    TrackSerializer,
)
from .services.importing import FETCH_ERRORS, ytmusic_client
from .services.library import absolute
from .services.recordings import RecordingError, merge_recordings, split_track

logger = logging.getLogger(__name__)


class CatalogPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


def _user(request: Request) -> User:
    return cast(User, request.user)


class TrackOrdering(OrderingFilter):
    """Lets ``?ordering=duration`` work although duration lives on the recording."""

    def get_ordering(
        self, request: Request, queryset: models.QuerySet[Any], view: Any
    ) -> list[str]:
        ordering = super().get_ordering(request, queryset, view) or []
        return [term.replace("duration", "recording__duration") for term in ordering]


class _CatalogViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet[Any],
):
    """List, detail, edit, history and revert, shared by artists, albums and tracks."""

    permission_classes = [IsAuthenticated]
    pagination_class = CatalogPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]

    #: Name used in activity actions: ``catalog.<kind>.updated``.
    kind: ClassVar[str]
    #: Fields the user may edit, which are also the ones a revert restores.
    editable_fields: ClassVar[tuple[str, ...]]

    def perform_update(self, serializer: BaseSerializer[Any]) -> None:
        # simple_history reads this attribute to fill ``history_user``.
        serializer.instance._history_user = _user(self.request)  # type: ignore[union-attr]
        serializer.save()
        log_activity(
            _user(self.request),
            f"catalog.{self.kind}.updated",
            serializer.instance,
            {"fields": sorted(serializer.validated_data)},
        )

    @extend_schema(responses=HistoryEntrySerializer(many=True), tags=["catalog"])
    @action(detail=True, methods=["get"])
    def history(self, request: Request, pk: str | None = None) -> Response:
        """Versions of the item, newest first."""
        entries = [
            {
                "history_id": record.history_id,
                "history_date": record.history_date,
                "history_type": record.history_type,
                "history_user": record.history_user.get_username() if record.history_user else None,
                "changes": {name: getattr(record, name) for name in self.editable_fields},
            }
            for record in self.get_object().history.all()
        ]
        return Response(HistoryEntrySerializer(entries, many=True).data)

    @extend_schema(request=RevertSerializer, tags=["catalog"])
    @action(detail=True, methods=["post"])
    def revert(self, request: Request, pk: str | None = None) -> Response:
        """Set the editable fields back to the values of a past version."""
        body = RevertSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        item = self.get_object()
        record = item.history.filter(history_id=body.validated_data["history_id"]).first()
        if record is None:
            raise NotFound(_("That version does not exist."))
        for name in self.editable_fields:
            setattr(item, name, getattr(record, name))
        item._history_user = _user(request)
        item.save()
        log_activity(
            _user(request),
            f"catalog.{self.kind}.reverted",
            item,
            {"history_id": record.history_id},
        )
        return Response(self.get_serializer(self.get_queryset().get(pk=item.pk)).data)


class _CreditsMixin:
    """Adds ``PUT <item>/artists/`` to replace the artists of an album or track."""

    kind: ClassVar[str]

    @extend_schema(request=ArtistIdsSerializer, tags=["catalog"])
    @action(detail=True, methods=["put"], url_path="artists")
    def set_artists(self, request: Request, pk: str | None = None) -> Response:
        """Replace the artists, in the order received."""
        viewset = cast(_CatalogViewSet, self)
        body = ArtistIdsSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        item = viewset.get_object()
        user = _user(request)
        with transaction.atomic():
            # Deleted one by one and created with history: bulk operations would not
            # record who made the change.
            for old in item.credits.all():
                old._history_user = user
                old.delete()
            credit = item.credits.model
            # A track's credits belong to its recording.
            owner = getattr(item, "recording", item)
            bulk_create_with_history(
                [
                    credit(**{item.credits.field.name: owner}, artist=artist, position=position)
                    for position, artist in enumerate(body.validated_data["artists"])
                ],
                credit,
                default_user=user,
            )
        log_activity(
            user,
            f"catalog.{self.kind}.artists_changed",
            item,
            {"artists": [a.pk for a in body.validated_data["artists"]]},
        )
        return Response(viewset.get_serializer(viewset.get_queryset().get(pk=item.pk)).data)


class _DeletableMixin(mixins.DestroyModelMixin):
    """Deletes albums and tracks, optionally blocking them with ``?block=true``.

    Blocking keeps a later import from bringing the item back. The audio files are
    removed from disk together with their ``Download`` rows, since a row without its file
    would only mislead the maintenance checks. What was deleted stays in the activity
    log. Deleting an album deletes its tracks.
    """

    kind: ClassVar[str]

    @extend_schema(
        parameters=[OpenApiParameter("block", bool, description="Also block the item.")],
        tags=["catalog"],
    )
    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return super().destroy(request, *args, **kwargs)

    def perform_destroy(self, instance: Album | Track) -> None:
        request = cast(viewsets.GenericViewSet[Any], self).request
        block = request.query_params.get("block", "").lower() in {"1", "true"}
        is_album = isinstance(instance, Album)
        external_id = instance.ytmusic_id if isinstance(instance, Album) else instance.video_id
        if block and not external_id:
            raise ValidationError(
                {"block": _("This item did not come from YouTube Music, so it cannot be blocked.")}
            )
        tracks = (
            instance.tracks.all()
            if isinstance(instance, Album)
            else Track.objects.filter(pk=instance.pk)
        )
        downloads = Download.objects.filter(track__in=tracks)
        paths = sorted({d.file_path for d in cast(list[Download], list(downloads))})
        detail: dict[str, Any] = {
            "title": instance.title,
            "external_id": external_id,
            "files": paths,
            "blocked": block,
        }
        if is_album:
            detail["tracks"] = tracks.count()
        with transaction.atomic():
            log_activity(_user(request), f"catalog.{self.kind}.deleted", instance, detail)
            if block:
                BlockedItem.objects.get_or_create(
                    kind=self.kind, external_id=external_id, defaults={"name": instance.title}
                )
            # ``Download`` is append-only; this is the one place allowed to bypass that.
            models.QuerySet.delete(downloads)
            instance.delete()
        for path in paths:
            try:
                absolute(path).unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not delete the file %s", path, exc_info=True)


class ArtistViewSet(_CatalogViewSet):
    queryset = Artist.objects.with_counts()
    serializer_class = ArtistSerializer
    filterset_class = ArtistFilter
    search_fields = ["name"]
    ordering_fields = [
        "name",
        "id",
        "track_count",
        "pending_count",
        "album_count",
        "monthly_listeners",
        "subscribers",
    ]
    ordering = ["name", "id"]
    kind = "artist"
    editable_fields = ("name", "image_url", "description")


class AlbumViewSet(_DeletableMixin, _CreditsMixin, _CatalogViewSet):
    queryset = Album.objects.with_counts().prefetch_related("credits__artist")
    serializer_class = AlbumSerializer
    filterset_class = AlbumFilter
    search_fields = ["title", "credits__artist__name"]
    ordering_fields = ["title", "year", "id", "track_count", "pending_count"]
    ordering = ["title", "id"]
    kind = "album"
    editable_fields = ("title", "year", "cover_url")


class TrackViewSet(_DeletableMixin, _CreditsMixin, _CatalogViewSet):
    queryset = (
        Track.objects.with_downloaded()
        .with_also_on()
        .with_copyable()
        .select_related("album", "recording")
        .prefetch_related("recording__credits__artist")
    )
    serializer_class = TrackSerializer
    filterset_class = TrackFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, TrackOrdering]
    search_fields = ["title", "recording__credits__artist__name"]
    ordering_fields = [
        "title",
        "track_number",
        "disc_number",
        "duration",
        "album__title",
        "album__year",
        "id",
    ]
    ordering = ["album", "disc_number", "track_number", "id"]
    kind = "track"
    editable_fields = ("title", "track_number", "disc_number")

    @extend_schema(request=None, responses=TrackSerializer, tags=["catalog"])
    @action(detail=True, methods=["post"])
    def split(self, request: Request, pk: str | None = None) -> Response:
        """Give the track a recording of its own."""
        track = cast(Track, self.get_object())
        try:
            split_track(track)
        except RecordingError as error:
            raise ValidationError({"detail": str(error)}) from error
        log_activity(
            _user(request), "catalog.track.split", track, {"recording": track.recording_id}
        )
        return Response(self.get_serializer(self.get_object()).data)


class RecordingViewSet(viewsets.ReadOnlyModelViewSet[Recording]):
    """Recordings with the albums they appear on. Read-only, except for merging."""

    permission_classes = [IsAuthenticated]
    pagination_class = CatalogPagination
    filter_backends = [SearchFilter, OrderingFilter]
    serializer_class = RecordingSerializer
    queryset = Recording.objects.annotate(
        track_count=Count("tracks", distinct=True),
        downloaded=Exists(Track.objects.filter(recording=OuterRef("pk"), download__isnull=False)),
    ).prefetch_related(
        "credits__artist",
        Prefetch("tracks", queryset=Track.objects.with_downloaded().select_related("album")),
    )
    search_fields = ["title", "credits__artist__name", "video_id"]
    ordering_fields = ["title", "duration", "track_count", "id"]
    ordering = ["title", "id"]

    @extend_schema(
        request=RecordingMergeSerializer, responses=RecordingSerializer, tags=["catalog"]
    )
    @action(detail=True, methods=["post"])
    def merge(self, request: Request, pk: str | None = None) -> Response:
        """Absorb another recording into this one."""
        keep = self.get_object()
        body = RecordingMergeSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        absorbed = body.validated_data["recording"]
        detail = {"absorbed": absorbed.pk, "title": absorbed.title}
        try:
            merge_recordings(keep, absorbed)
        except RecordingError as error:
            raise ValidationError({"detail": str(error)}) from error
        log_activity(_user(request), "catalog.recording.merged", keep, detail)
        return Response(self.get_serializer(self.get_object()).data)


class BlockedItemViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet[BlockedItem],
):
    """The block list: blocking creates an entry, unblocking deletes it."""

    queryset = BlockedItem.objects.order_by("-created_at", "-id")
    serializer_class = BlockedItemSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CatalogPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["kind", "external_id"]
    search_fields = ["name"]

    def perform_create(self, serializer: BaseSerializer[BlockedItem]) -> None:
        item = serializer.save()
        log_activity(
            _user(self.request),
            "catalog.blocked.added",
            item,
            {"kind": item.kind, "external_id": item.external_id},
        )

    def perform_destroy(self, instance: BlockedItem) -> None:
        # Logged before deleting: afterwards the object has no primary key to refer to.
        log_activity(
            _user(self.request),
            "catalog.blocked.removed",
            instance,
            {"kind": instance.kind, "external_id": instance.external_id},
        )
        instance.delete()


class ArtistLookupView(APIView):
    """Finds artists on YouTube Music so they can be imported.

    A link or channel id returns that one artist with the size of its discography; any
    other text is searched as a name.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[ArtistLookupQuerySerializer],
        responses={200: ArtistLookupSerializer, 502: DetailSerializer},
        tags=["catalog"],
    )
    def get(self, request: Request) -> Response:
        query = ArtistLookupQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        text = query.validated_data["q"]
        try:
            found = _lookup(text)
        except FETCH_ERRORS:
            logger.warning("YouTube Music lookup failed for %r", text, exc_info=True)
            return Response(
                {"detail": _("YouTube Music is not responding.")},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        ids = [result["ytmusic_id"] for result in found]
        in_library = set(
            Artist.objects.with_music()
            .filter(ytmusic_id__in=ids)
            .values_list("ytmusic_id", flat=True)
        )
        blocked = set(
            BlockedItem.objects.filter(
                kind=BlockedItem.Kind.ARTIST, external_id__in=ids
            ).values_list("external_id", flat=True)
        )
        for result in found:
            result["in_library"] = result["ytmusic_id"] in in_library
            result["blocked"] = result["ytmusic_id"] in blocked
        return Response({"results": found})


def _lookup(text: str) -> list[dict[str, Any]]:
    client = ytmusic_client()
    channel_id = ytm.parse_channel_id(text)
    if channel_id is None:
        # A handle link ("…/@name") carries no id: its name is searched like any other.
        name = ytm.parse_handle(text) or text
        return [_lookup_result(artist) for artist in client.search_artists(name)]
    page = client.get_artist(channel_id)
    albums = sum(1 for release in page.releases if release.kind == ytm.models.ALBUM)
    return [_lookup_result(page.artist, albums, len(page.releases) - albums)]


def _lookup_result(
    artist: ytm.Artist, album_count: int | None = None, single_count: int | None = None
) -> dict[str, Any]:
    return {
        "ytmusic_id": artist.id,
        "name": artist.name,
        "image_url": artist.image_url,
        "monthly_listeners": artist.monthly_listeners,
        "subscribers": artist.subscribers,
        "album_count": album_count,
        "single_count": single_count,
    }


class LibrarySummaryView(APIView):
    """Counts shown on the dashboard."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=LibrarySummarySerializer, tags=["catalog"])
    def get(self, request: Request) -> Response:
        return Response(
            {
                "artists": Artist.objects.with_music().count(),
                "related_artists": Artist.objects.profiles_only().count(),
                "albums": Album.objects.count(),
                "recordings": Recording.objects.count(),
                "tracks": Track.objects.count(),
                # Tracks, not downloads: a track can be downloaded more than once.
                "downloaded": Download.objects.values("track").distinct().count(),
            }
        )
