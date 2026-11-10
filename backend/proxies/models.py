"""``proxies`` app models."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Proxy(models.Model):
    """Outbound proxy with success and failure counters. The counters are the
    operational state the rotation logic reads, so the row is mutable.
    """

    class IpVersion(models.TextChoices):
        """Address family the proxy exits by."""

        IPV4 = "ipv4", "IPv4"
        IPV6 = "ipv6", "IPv6"

    url = models.CharField(_("URL"), max_length=500, unique=True)
    ip_version = models.CharField(
        _("IP version"),
        max_length=4,
        choices=IpVersion,
        default=IpVersion.IPV4,
        # Also in the database, so existing rows
        # and writes from an older version during a rolling deploy get IPv4.
        db_default=IpVersion.IPV4,
    )
    enabled = models.BooleanField(_("enabled"), default=True)
    success_count = models.PositiveIntegerField(_("successes"), default=0)
    failure_count = models.PositiveIntegerField(_("failures"), default=0)
    last_used_at = models.DateTimeField(_("last used"), null=True, blank=True)
    last_failed_at = models.DateTimeField(_("last failure"), null=True, blank=True)
    created_at = models.DateTimeField(_("created"), auto_now_add=True)

    class Meta:
        """Ordered by URL."""

        ordering = ["url"]

    def __str__(self) -> str:
        """Returns the URL."""
        return self.url


class ServiceIpSupport(models.Model):
    """Address families of an external service, checked once. The row is written the
    first time the service is contacted and then only read, so proxy choice never
    repeats the DNS lookup.
    """

    host = models.CharField(_("host"), max_length=255, unique=True)
    ipv4 = models.BooleanField(_("IPv4"))
    ipv6 = models.BooleanField(_("IPv6"))
    checked_at = models.DateTimeField(_("checked"), auto_now_add=True)

    def __str__(self) -> str:
        """Returns the host."""
        return self.host
