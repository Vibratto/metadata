"""Proxy selection tests."""

import pytest

from integrations.youtube import NoProxyAvailable, ProxyPool

A, B = "http://a:1", "http://b:1"


def test_empty_pool_means_direct_connection() -> None:
    assert ProxyPool([]).acquire(0) is None


def test_round_robin() -> None:
    pool = ProxyPool([A, B])
    assert [pool.acquire(0) for _ in range(3)] == [A, B, A]


def test_failed_proxy_is_skipped_until_cooldown_ends() -> None:
    pool = ProxyPool([A, B], base_cooldown=60)
    pool.report_failure(A, now=0)
    assert pool.acquire(10) == B
    assert pool.acquire(10) == B
    assert pool.acquire(60) == A


def test_cooldown_doubles_and_is_capped() -> None:
    pool = ProxyPool([A], base_cooldown=60, max_cooldown=100)
    pool.report_failure(A, now=0)
    pool.report_failure(A, now=0)  # 120 -> capped to 100
    with pytest.raises(NoProxyAvailable) as info:
        pool.acquire(0)
    assert info.value.retry_in == 100


def test_all_cooling_reports_shortest_wait() -> None:
    pool = ProxyPool([A, B], base_cooldown=60)
    pool.report_failure(A, now=0)
    pool.report_failure(B, now=30)
    with pytest.raises(NoProxyAvailable) as info:
        pool.acquire(40)
    assert info.value.retry_in == 20


def test_success_clears_failures() -> None:
    pool = ProxyPool([A], base_cooldown=60)
    pool.report_failure(A, now=0)
    pool.report_failure(A, now=0)
    pool.report_success(A)
    pool.report_failure(A, now=0)
    assert pool.acquire(60) == A  # back to the base wait
