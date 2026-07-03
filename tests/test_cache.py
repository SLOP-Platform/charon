from __future__ import annotations

import hashlib
import threading
import time

from charon.cache import SemanticCache, format_stats


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def test_get_set_roundtrips() -> None:
    cache = SemanticCache()
    h = _hash("hello")
    cache.set(h, b"world", {"x": "1"}, 60.0)
    result = cache.get(h)
    assert result is not None
    assert result.content == b"world"
    assert result.headers == {"x": "1"}


def test_get_miss_returns_none() -> None:
    cache = SemanticCache()
    assert cache.get(_hash("nope")) is None


def test_ttl_expiry() -> None:
    cache = SemanticCache()
    h = _hash("doomed")
    cache.set(h, b"data", {}, -1.0)
    assert cache.get(h) is None


def test_ttl_still_valid() -> None:
    cache = SemanticCache()
    h = _hash("alive")
    cache.set(h, b"data", {}, 3600.0)
    result = cache.get(h)
    assert result is not None
    assert result.content == b"data"


def test_stats_tracks_hits_misses() -> None:
    cache = SemanticCache()
    h = _hash("stats")
    cache.set(h, b"payload", {}, 60.0)
    cache.get(h)  # hit
    cache.get(_hash("nope"))  # miss
    s = cache.stats()
    assert s.hits == 1
    assert s.misses == 1


def test_stats_tracks_size() -> None:
    cache = SemanticCache()
    cache.set(_hash("a"), b"", {}, 60.0)
    cache.set(_hash("b"), b"", {}, 60.0)
    assert cache.stats().size == 2


def test_lru_eviction() -> None:
    cache = SemanticCache(max_size=2)
    cache.set(_hash("a"), b"a", {}, 60.0)
    cache.set(_hash("b"), b"b", {}, 60.0)
    cache.set(_hash("c"), b"c", {}, 60.0)
    s = cache.stats()
    assert s.size == 2
    assert s.evictions == 1
    assert cache.get(_hash("a")) is None  # evicted
    assert cache.get(_hash("b")) is not None
    assert cache.get(_hash("c")) is not None


def test_lru_update_moves_to_end() -> None:
    cache = SemanticCache(max_size=2)
    ha = _hash("a")
    hb = _hash("b")
    hc = _hash("c")
    cache.set(ha, b"a", {}, 60.0)
    cache.set(hb, b"b", {}, 60.0)
    assert cache.get(ha) is not None  # moves a to end
    cache.set(hc, b"c", {}, 60.0)  # evicts b (oldest)
    assert cache.get(ha) is not None  # a survived
    assert cache.get(hb) is None  # b evicted
    assert cache.get(hc) is not None


def test_thread_safety() -> None:
    cache = SemanticCache(max_size=200)
    num_threads = 8
    ops_per_thread = 100
    errors: list[Exception] = []
    barrier = threading.Barrier(num_threads)

    def worker() -> None:
        try:
            barrier.wait()
            for i in range(ops_per_thread):
                h = _hash(f"t{threading.get_ident()}-{i}")
                cache.set(h, b"x", {}, 300.0)
                cache.get(h)
                time.sleep(0)
                cache.stats()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"errors during concurrent access: {errors}"
    s = cache.stats()
    assert s.size <= 200
    assert s.size + s.evictions >= num_threads * ops_per_thread


def test_headers_stored() -> None:
    cache = SemanticCache()
    h = _hash("hdr")
    headers = {"content-type": "application/json", "x-request-id": "abc123"}
    cache.set(h, b"body", headers, 60.0)
    result = cache.get(h)
    assert result is not None
    assert result.headers == headers


def test_update_existing_key() -> None:
    cache = SemanticCache()
    h = _hash("dupe")
    cache.set(h, b"v1", {}, 60.0)
    cache.set(h, b"v2", {}, 60.0)
    s = cache.stats()
    assert s.size == 1
    result = cache.get(h)
    assert result is not None
    assert result.content == b"v2"


def test_similar_prompt_is_cache_miss() -> None:
    cache = SemanticCache()
    cache.set(_hash("add two numbers"), b"result1", {}, 60.0)
    assert cache.get(_hash("add 2 numbers")) is None


def test_format_stats_reports_hits_misses_hit_rate() -> None:
    cache = SemanticCache()
    h = _hash("a")
    cache.set(h, b"x", {}, 60.0)
    cache.get(h)       # hit
    cache.get(_hash("b"))  # miss
    out = format_stats(cache)
    assert "1 hits" in out
    assert "1 misses" in out
    assert "50.0% hit rate" in out


def test_format_stats_zero_total_shows_zero_rate() -> None:
    cache = SemanticCache()
    out = format_stats(cache)
    assert "0.0% hit rate" in out
