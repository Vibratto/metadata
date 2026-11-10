"""Proxy views.

Administrators only. The connection test does not return the raw error: it
may contain the proxy URL with credentials.
"""

from typing import Any

import requests
from django.db import IntegrityError, transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer

from activity.services import log_activity
from integrations.http import build_session

from .bulk import parse_text
from .models import Proxy
from .serializers import (
    BulkProxyResultSerializer,
    BulkProxySerializer,
    ProxyCheckSerializer,
    ProxySerializer,
)

# A small, stable page of the service the proxies are mostly used for: enough to tell
# whether traffic gets out through the proxy.
CHECK_URL = "https://music.youtube.com/generate_204"


def _fetch_status(proxy: Proxy) -> int | None:
    """Requests ``CHECK_URL`` through the proxy.

    Returns:
        HTTP status, or ``None``
        when there was no response.
    """
    with build_session() as session:
        session.proxies = {"http": proxy.url, "https": proxy.url}
        try:
            return session.get(CHECK_URL).status_code
        except requests.RequestException:
            return None


class ProxyViewSet(viewsets.ModelViewSet[Proxy]):
    """Proxy CRUD and connection test."""

    queryset = Proxy.objects.all()
    serializer_class = ProxySerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer: BaseSerializer[Any]) -> None:
        """Saves and logs the creation."""
        proxy: Proxy = serializer.save()
        log_activity(self.request.user, "proxies.created", proxy)

    def perform_update(self, serializer: BaseSerializer[Any]) -> None:
        """Saves and logs the change."""
        proxy: Proxy = serializer.save()
        log_activity(self.request.user, "proxies.updated", proxy)

    def perform_destroy(self, instance: Proxy) -> None:
        """Logs and deletes."""
        with transaction.atomic():
            log_activity(self.request.user, "proxies.deleted", instance)
            instance.delete()

    @extend_schema(
        request=None,
        responses={200: ProxyCheckSerializer},
        tags=["proxies"],
    )
    @action(detail=True, methods=["post"], url_path="check")
    def check(self, request: Request, pk: str | None = None) -> Response:
        """Checks that the proxy relays traffic.

        A 2xx or 3xx status counts as success.
        """
        proxy = self.get_object()
        status_code = _fetch_status(proxy)
        ok = status_code is not None and status_code < 400
        log_activity(
            request.user, "proxies.checked", proxy, detail={"ok": ok, "status_code": status_code}
        )
        return Response(ProxyCheckSerializer({"ok": ok, "status_code": status_code}).data)

    @extend_schema(
        request=BulkProxySerializer,
        responses={200: BulkProxyResultSerializer, 400: BulkProxyResultSerializer},
        tags=["proxies"],
    )
    @action(detail=False, methods=["post"], url_path="bulk")
    def bulk(self, request: Request) -> Response:
        """Adds the valid proxies of a pasted list.

        With no valid line it answers 400 and creates nothing. Duplicates, against the
        database or inside the list, are counted and not created.
        """
        body = BulkProxySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        options = body.validated_data
        parsed = parse_text(options["text"], options["default_scheme"])
        invalid = [{"line": p.line, "reason": p.reason} for p in parsed if p.url is None]
        valid = [(p.line, p.url) for p in parsed if p.url is not None]
        if not valid:
            return Response(
                {"created": 0, "duplicates": [], "invalid": invalid},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing = set(
            Proxy.objects.filter(url__in=[url for _, url in valid]).values_list("url", flat=True)
        )
        seen: set[str] = set()
        duplicates: list[dict[str, int]] = []
        created = 0
        for line, url in valid:
            if url in existing or url in seen:
                duplicates.append({"line": line})
                continue
            seen.add(url)
            try:
                with transaction.atomic():
                    Proxy.objects.create(
                        url=url,
                        ip_version=options["ip_version"],
                        enabled=options["enabled"],
                    )
                created += 1
            except IntegrityError:
                # Created by another admin first.
                duplicates.append({"line": line})

        log_activity(
            request.user,
            "proxies.bulk_created",
            detail={"created": created, "duplicates": len(duplicates), "invalid": len(invalid)},
        )
        return Response({"created": created, "duplicates": duplicates, "invalid": invalid})
