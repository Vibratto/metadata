"""Tests for the ``proxies`` model."""

import pytest
from django.db import IntegrityError

from proxies.models import Proxy, ServiceIpSupport

pytestmark = pytest.mark.django_db


def test_counters_start_at_zero() -> None:
    proxy = Proxy.objects.create(url="http://127.0.0.1:8080")
    assert proxy.success_count == 0
    assert proxy.failure_count == 0
    assert proxy.last_used_at is None


def test_url_is_unique() -> None:
    Proxy.objects.create(url="http://127.0.0.1:8080")
    with pytest.raises(IntegrityError):
        Proxy.objects.create(url="http://127.0.0.1:8080")


def test_counters_update_in_database() -> None:
    proxy = Proxy.objects.create(url="http://127.0.0.1:8080")
    Proxy.objects.filter(pk=proxy.pk).update(failure_count=proxy.failure_count + 1)
    proxy.refresh_from_db()
    assert proxy.failure_count == 1


def test_proxy_str_is_its_url() -> None:
    assert str(Proxy(url="http://127.0.0.1:8080")) == "http://127.0.0.1:8080"


def test_service_ip_support_str_is_its_host() -> None:
    assert str(ServiceIpSupport(host="music.youtube.com")) == "music.youtube.com"
