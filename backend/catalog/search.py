"""Global catalogue search.

Same fields as the lists (``name``; ``title`` and credited artists), so what shows up
here is what the full list shows afterwards.
"""

from typing import Any

from django.db.models import Q, QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Album, Artist, Track

DEFAULT_LIMIT = 5
MAX_LIMIT = 20
GROUPS = ("artists", "albums", "tracks")


class SearchQuerySerializer(serializers.Serializer[Any]):
    """Search parameters."""

    q = serializers.CharField(min_length=2, trim_whitespace=True)
    type = serializers.ChoiceField(choices=["all", *GROUPS], default="all")
    limit = serializers.IntegerField(min_value=1, default=DEFAULT_LIMIT)


class SearchResultSerializer(serializers.Serializer[Any]):
    """One result."""

    id = serializers.IntegerField()
    name = serializers.CharField(required=False)
    title = serializers.CharField(required=False)
    image = serializers.CharField(allow_blank=True)
    subtitle = serializers.CharField(allow_blank=True)


class SearchGroupSerializer(serializers.Serializer[Any]):
    """A result group with its total."""

    count = serializers.IntegerField()
    results = SearchResultSerializer(many=True)


class SearchSerializer(serializers.Serializer[Any]):
    """Results grouped by type."""

    artists = SearchGroupSerializer(required=False)
    albums = SearchGroupSerializer(required=False)
    tracks = SearchGroupSerializer(required=False)


def _artists_line(item: Album | Track) -> str:
    return ", ".join(c.artist.name for c in item.credits.all())


class CatalogSearchView(APIView):
    """Searches all three at once."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[SearchQuerySerializer],
        responses=SearchSerializer,
        tags=["catalog"],
    )
    def get(self, request: Request) -> Response:
        """Grouped results with totals."""
        query = SearchQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        text, kind = query.validated_data["q"], query.validated_data["type"]
        limit = min(query.validated_data["limit"], MAX_LIMIT)
        wanted = GROUPS if kind == "all" else (kind,)
        body: dict[str, Any] = {}
        if "artists" in wanted:
            people = Artist.objects.filter(name__icontains=text).order_by("name", "id")
            body["artists"] = self._group(
                people,
                limit,
                lambda a: {"id": a.pk, "name": a.name, "image": a.image_url, "subtitle": ""},
            )
        if "albums" in wanted:
            discs = self._matching(Album.objects.prefetch_related("credits__artist"), text)
            body["albums"] = self._group(
                discs,
                limit,
                lambda a: {
                    "id": a.pk,
                    "title": a.title,
                    "image": a.cover_url,
                    "subtitle": _artists_line(a),
                },
            )
        if "tracks" in wanted:
            songs = self._matching(
                Track.objects.select_related("album", "recording").prefetch_related(
                    "recording__credits__artist"
                ),
                text,
                credits="recording__credits",
            )
            body["tracks"] = self._group(
                songs,
                limit,
                lambda t: {
                    "id": t.pk,
                    "title": t.title,
                    "image": t.album.cover_url,
                    "subtitle": _artists_line(t),
                    "album": t.album.title,
                },
            )
        return Response(body)

    @staticmethod
    def _matching(queryset: QuerySet[Any], text: str, credits: str = "credits") -> QuerySet[Any]:
        """By title or credited artist."""
        credited = Q(**{f"{credits}__artist__name__icontains": text})
        ids = queryset.filter(Q(title__icontains=text) | credited).values("pk")
        return queryset.filter(pk__in=ids).order_by("title", "id")

    @staticmethod
    def _group(found: QuerySet[Any], limit: int, row: Any) -> dict[str, Any]:
        return {"count": found.count(), "results": [row(item) for item in found[:limit]]}
