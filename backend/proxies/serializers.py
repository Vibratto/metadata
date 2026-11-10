"""Proxy serializers."""

from typing import Any
from urllib.parse import urlsplit

from django.utils.translation import gettext as _
from rest_framework import serializers

from .bulk import MAX_BYTES, MAX_LINES
from .models import Proxy

ALLOWED_SCHEMES = ("http", "https", "socks5", "socks5h")


class ProxySerializer(serializers.ModelSerializer[Proxy]):
    """Outbound proxy. The counters are maintained by downloads, not by the API."""

    class Meta:
        """Exposed fields."""

        model = Proxy
        fields = [
            "id",
            "url",
            "ip_version",
            "enabled",
            "success_count",
            "failure_count",
            "last_used_at",
            "last_failed_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "success_count",
            "failure_count",
            "last_used_at",
            "last_failed_at",
            "created_at",
        ]

    def validate_url(self, value: str) -> str:
        """Known proxy schemes with a host.

        Args:
            value: Proxy URL.

        Returns:
            The same URL.

        Raises:
        """
        parsed = urlsplit(value)
        if parsed.scheme not in ALLOWED_SCHEMES or not parsed.hostname:
            raise serializers.ValidationError(
                _("Use a proxy with an http, https, socks5 or socks5h scheme and a host.")
            )
        return value


class ProxyCheckSerializer(serializers.Serializer[dict[str, Any]]):
    """Result of testing a proxy."""

    ok = serializers.BooleanField()
    status_code = serializers.IntegerField(allow_null=True)


class BulkProxySerializer(serializers.Serializer[dict[str, Any]]):
    """Pasted proxy list for bulk import."""

    text = serializers.CharField(trim_whitespace=False, allow_blank=True)
    ip_version = serializers.ChoiceField(
        choices=Proxy.IpVersion.choices, default=Proxy.IpVersion.IPV4
    )
    enabled = serializers.BooleanField(default=True)
    default_scheme = serializers.ChoiceField(choices=ALLOWED_SCHEMES, default="http")

    def validate_text(self, value: str) -> str:
        """Caps lines and size before parsing.

        Raises:
        """
        if len(value.splitlines()) > MAX_LINES:
            raise serializers.ValidationError(_("There are more than 1000 lines."))
        if len(value.encode()) > MAX_BYTES:
            raise serializers.ValidationError(_("The text is larger than 100 KB."))
        return value


class BulkProxyResultSerializer(serializers.Serializer[dict[str, Any]]):
    """Summary of a bulk import."""

    created = serializers.IntegerField()
    duplicates = serializers.ListField(child=serializers.DictField())
    invalid = serializers.ListField(child=serializers.DictField())
