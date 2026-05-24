"""Unit tests for scripts/replay_cache.py."""

from __future__ import annotations

import pytest

from scripts.replay_cache import InMemoryReplayReservationCache


def test_reserve_commit_suppresses_replays_until_ttl_expiry() -> None:
    cache = InMemoryReplayReservationCache(ttl_seconds=10, max_entries=10)
    key = "delivery-1"

    assert cache.reserve(key, now=0.0) is False
    cache.commit(key, now=0.0)
    assert cache.reserve(key, now=5.0) is True
    assert cache.reserve(key, now=10.1) is False


def test_rollback_releases_inflight_reservation() -> None:
    cache = InMemoryReplayReservationCache(ttl_seconds=10, max_entries=10)
    key = "delivery-2"

    assert cache.reserve(key, now=0.0) is False
    assert cache.reserve(key, now=0.0) is True
    cache.rollback(key)
    assert cache.reserve(key, now=0.0) is False


def test_max_entries_evicts_oldest_expiration_record() -> None:
    cache = InMemoryReplayReservationCache(ttl_seconds=100, max_entries=2)

    assert cache.reserve("k1", now=0.0) is False
    cache.commit("k1", now=0.0)
    assert cache.reserve("k2", now=1.0) is False
    cache.commit("k2", now=1.0)
    assert cache.reserve("k3", now=2.0) is False
    cache.commit("k3", now=2.0)

    assert cache.reserve("k1", now=2.0) is False  # evicted oldest
    assert cache.reserve("k2", now=2.0) is True
    assert cache.reserve("k3", now=2.0) is True


def test_constructor_rejects_non_positive_values() -> None:
    with pytest.raises(ValueError, match="ttl_seconds must be positive"):
        InMemoryReplayReservationCache(ttl_seconds=0, max_entries=1)

    with pytest.raises(ValueError, match="max_entries must be positive"):
        InMemoryReplayReservationCache(ttl_seconds=1, max_entries=0)
