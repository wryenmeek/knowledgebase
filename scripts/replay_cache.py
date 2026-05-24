"""Shared in-memory replay cache primitives for webhook relay pipelines."""

from __future__ import annotations

import threading
import time


class InMemoryReplayReservationCache:
    """Thread-safe replay suppression using reserve/commit/rollback semantics."""

    def __init__(self, *, ttl_seconds: int, max_entries: int) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._ttl_seconds = float(ttl_seconds)
        self._max_entries = max_entries
        self._expirations: dict[str, float] = {}
        self._inflight: set[str] = set()
        self._lock = threading.Lock()

    def reserve(self, key: str, *, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        with self._lock:
            self._evict_expired(current)
            if key in self._expirations or key in self._inflight:
                return True
            self._inflight.add(key)
            return False

    def commit(self, key: str, *, now: float | None = None) -> None:
        current = time.time() if now is None else now
        with self._lock:
            self._evict_expired(current)
            self._inflight.discard(key)
            self._record_unlocked(key, current)

    def rollback(self, key: str) -> None:
        with self._lock:
            self._inflight.discard(key)

    def _record_unlocked(self, key: str, now: float) -> None:
        # Keep insertion order aligned with expiration order.
        self._expirations.pop(key, None)
        if len(self._expirations) >= self._max_entries:
            self._expirations.pop(next(iter(self._expirations)), None)
        self._expirations[key] = now + self._ttl_seconds

    def _evict_expired(self, now: float) -> None:
        while self._expirations:
            oldest_key = next(iter(self._expirations))
            if self._expirations[oldest_key] > now:
                break
            self._expirations.pop(oldest_key, None)


__all__ = ["InMemoryReplayReservationCache"]
