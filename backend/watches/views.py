"""New-release views.

Checks (``WatchRun``) are read-only here: the check task writes them.
"""

from typing import Any

from django.db import transaction
from django.db.models import ProtectedError
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend  # type: ignore[import-untyped]
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from activity.services import log_activity

from .filters import WatchFilter
from .models import Watch, WatchRun
from .serializers import WatchRunSerializer, WatchSerializer


class WatchInUse(APIException):
    """The watch has recorded checks."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = _("The watch has recorded checks and cannot be deleted.")
    default_code = "watch_in_use"


class WatchPagination(PageNumberPagination):
    """50 items per page."""

    page_size = 50


class WatchViewSet(viewsets.ModelViewSet[Watch]):
    """Watch CRUD and check history."""

    queryset = Watch.objects.prefetch_related("watch_artists__artist")
    serializer_class = WatchSerializer
    pagination_class = WatchPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = WatchFilter
    search_fields = ["name", "watch_artists__artist__name"]
    ordering_fields = ["name", "next_run_at"]
    ordering = ["name"]

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        """Saves and logs the creation."""
        watch: Watch = serializer.save()
        log_activity(self.request.user, "watches.created", watch)

    def perform_update(self, serializer: BaseSerializer[Any]) -> None:
        """Saves and logs the change."""
        watch: Watch = serializer.save()
        log_activity(self.request.user, "watches.updated", watch)

    def perform_destroy(self, instance: Watch) -> None:
        """Deletes unless it has checks, in which case it answers 409. The log
        row is written inside the same transaction, so a refused delete leaves
        no trace.
        """
        try:
            with transaction.atomic():
                log_activity(self.request.user, "watches.deleted", instance)
                instance.delete()
        except ProtectedError as error:
            raise WatchInUse() from error

    @extend_schema(responses=WatchRunSerializer(many=True), tags=["watches"])
    @action(detail=True, methods=["get"])
    def runs(self, request: Request, pk: str | None = None) -> Response:
        """Check history, newest first."""
        watch = self.get_object()
        paginator = WatchPagination()
        page = paginator.paginate_queryset(WatchRun.objects.filter(watch=watch), request, self)
        serializer = WatchRunSerializer(page, many=True)  # type: ignore[arg-type]
        return paginator.get_paginated_response(serializer.data)
