"""Read-only activity and log views."""

from typing import Any, cast

import django_filters  # type: ignore[import-untyped]
from django.db.models import QuerySet
from django_db_logger.models import StatusLog
from django_filters.rest_framework import DjangoFilterBackend  # type: ignore[import-untyped]
from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from activity.models import ActivityLog

from .serializers import ActivityLogSerializer, TechnicalLogSerializer


class Pagination(PageNumberPagination):
    """50-row pages, up to 200.

    Logs grow large, so the whole table is never returned.
    """

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class ActivityFilter(django_filters.FilterSet):  # type: ignore[misc]
    """Activity history filters."""

    date_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    user = django_filters.NumberFilter(field_name="user_id")
    username = django_filters.CharFilter(field_name="username", lookup_expr="iexact")
    action = django_filters.CharFilter(lookup_expr="icontains")
    object_type = django_filters.CharFilter(method="filter_object_type")
    object_id = django_filters.CharFilter(field_name="object_id")

    def filter_object_type(self, queryset: QuerySet[ActivityLog], name: str, value: str) -> Any:
        """Filters by ``app.model``, e.g. ``catalog.artist``."""
        app_label, _, model = value.partition(".")
        return queryset.filter(content_type__app_label=app_label, content_type__model=model)


class TechnicalLogFilter(django_filters.FilterSet):  # type: ignore[misc]
    """Technical log filters."""

    min_level = django_filters.NumberFilter(field_name="level", lookup_expr="gte")
    module = django_filters.CharFilter(field_name="logger_name", lookup_expr="icontains")
    date_from = django_filters.DateFilter(field_name="create_datetime", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="create_datetime", lookup_expr="date__lte")
    task = django_filters.NumberFilter(method="filter_task")
    search = django_filters.CharFilter(field_name="msg", lookup_expr="icontains")

    def filter_task(self, queryset: QuerySet[StatusLog], name: str, value: Any) -> Any:
        """Filters by task: every line carries the ``[job N]`` prefix set in the logging config."""
        return queryset.filter(msg__startswith=f"[job {int(value)}] ")


class ActivityViewSet(viewsets.ReadOnlyModelViewSet[ActivityLog]):
    """Activity history. Read only: nobody deletes or edits records."""

    # core.AppendOnlyQuerySet is typed for AppendOnlyModel; the cast corrects it here.
    queryset = cast("QuerySet[ActivityLog]", ActivityLog.objects.select_related("content_type"))
    serializer_class = ActivityLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = Pagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = ActivityFilter


class TechnicalLogViewSet(viewsets.ReadOnlyModelViewSet[StatusLog]):
    """Technical logs stored in the database, administrators only."""

    queryset = cast("QuerySet[StatusLog]", StatusLog.objects.all())
    serializer_class = TechnicalLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = Pagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = TechnicalLogFilter
