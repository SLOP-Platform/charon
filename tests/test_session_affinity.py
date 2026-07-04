from __future__ import annotations

import time

from charon.session_affinity import SessionAffinity


def test_pin_and_resolve() -> None:
    sa = SessionAffinity(ttl=60)
    sa.pin("s1", "openai")
    assert sa.resolve("s1") == "openai"


def test_resolve_unknown_returns_none() -> None:
    sa = SessionAffinity()
    assert sa.resolve("unknown") is None


def test_ttl_expiry() -> None:
    sa = SessionAffinity(ttl=0.01)
    sa.pin("s1", "openai")
    time.sleep(0.02)
    assert sa.resolve("s1") is None


def test_clear_removes_pin() -> None:
    sa = SessionAffinity(ttl=60)
    sa.pin("s1", "openai")
    sa.clear("s1")
    assert sa.resolve("s1") is None


def test_touch_resets_ttl() -> None:
    sa = SessionAffinity(ttl=0.1)
    sa.pin("s1", "openai")
    time.sleep(0.06)
    sa.touch("s1")
    time.sleep(0.06)
    assert sa.resolve("s1") == "openai"


def test_cleanup_removes_stale() -> None:
    sa = SessionAffinity(ttl=0.01)
    sa.pin("s1", "openai")
    sa.pin("s2", "together")
    time.sleep(0.02)
    assert sa.cleanup() == 2
    assert sa.resolve("s1") is None
    assert sa.resolve("s2") is None


def test_cleanup_preserves_active() -> None:
    sa = SessionAffinity(ttl=60)
    sa.pin("s1", "openai")
    assert sa.cleanup() == 0
    assert sa.resolve("s1") == "openai"


def test_size() -> None:
    sa = SessionAffinity(ttl=60)
    assert sa.size() == 0
    sa.pin("a", "x")
    sa.pin("b", "y")
    assert sa.size() == 2


def test_multiple_sessions_independent() -> None:
    sa = SessionAffinity(ttl=60)
    sa.pin("a", "openai")
    sa.pin("b", "together")
    assert sa.resolve("a") == "openai"
    assert sa.resolve("b") == "together"


def test_on_evict_callback() -> None:
    evicted: list[str] = []
    sa = SessionAffinity(ttl=0.01, on_evict=lambda sid: evicted.append(sid))
    sa.pin("s1", "openai")
    time.sleep(0.02)
    sa.cleanup()
    assert "s1" in evicted


def test_thread_safety_concurrent_pins() -> None:
    import threading
    sa = SessionAffinity(ttl=60)
    errors: list[Exception] = []

    def pinner(i: int) -> None:
        try:
            for _ in range(50):
                sa.pin(f"s{i}", f"p{i}")
                sa.resolve(f"s{i}")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=pinner, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(errors) == 0
