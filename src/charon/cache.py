"""Thread-safe SHA-256 prompt cache with LRU eviction and TTL expiry.

Cache correctness is critical for code / precise work — a FALSE positive (serving
a cached response for a *similar* but not identical prompt) returns a WRONG answer.
For that reason this cache uses **exact SHA-256 hash keying only**; it deliberately
does NOT implement fuzzy / semantic similarity matching. The caller hashes the full
canonical prompt before lookup, so a near-miss ("add two numbers" vs "add 2 numbers")
is always a cache miss, never a false hit.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict

from .types import CachedResponse, CacheStats


def format_stats(cache: SemanticCache) -> str:
    """Human-readable hit/miss/eviction summary for status / CLI output."""
    s = cache.stats()
    total = s.hits + s.misses
    rate = s.hits / total if total > 0 else 0.0
    return (
        f"cache: {s.size} entries, {s.hits} hits, {s.misses} misses "
        f"({rate:.1%} hit rate), {s.evictions} evictions"
    )


class SemanticCache:
    def __init__(self, max_size: int = 1000) -> None:
        self._max_size = max_size
        self._cache: OrderedDict[str, CachedResponse] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._lock = threading.RLock()

    def get(self, prompt_hash: str) -> CachedResponse | None:
        with self._lock:
            entry = self._cache.get(prompt_hash)
            if entry is None:
                self._misses += 1
                return None
            if time.time() > entry.created_at + entry.ttl:
                del self._cache[prompt_hash]
                self._misses += 1
                return None
            self._cache.move_to_end(prompt_hash)
            self._hits += 1
            return entry

    def set(self, prompt_hash: str, response: bytes, headers: dict, ttl: float) -> None:
        with self._lock:
            if prompt_hash in self._cache:
                del self._cache[prompt_hash]
            self._cache[prompt_hash] = CachedResponse(
                content=response, headers=headers, created_at=time.time(), ttl=ttl
            )
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)
                self._evictions += 1

    def stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(
                hits=self._hits, misses=self._misses,
                size=len(self._cache), evictions=self._evictions,
            )
