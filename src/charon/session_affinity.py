"""Session-affinity pinning for prompt-cache optimisation (ADOPT B3.1).

An in-memory dictionary keyed by session id pins a client to its first
healthy provider so provider-side prompt caches stay warm.  Pins expire
on idle timeout or when a failover clears them.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class SessionAffinity:
    def __init__(self, ttl: float = 300.0, on_evict: Callable[[str], None] | None = None):
        self._ttl = ttl
        self._on_evict = on_evict
        self._pins: dict[str, tuple[str, float]] = {}  # session_id → (provider, last_used)
        self._lock = threading.RLock()

    def pin(self, session_id: str, provider: str) -> None:
        with self._lock:
            self._pins[session_id] = (provider, time.monotonic())

    def resolve(self, session_id: str) -> str | None:
        with self._lock:
            entry = self._pins.get(session_id)
            if entry is None:
                return None
            provider, last = entry
            if time.monotonic() - last > self._ttl:
                del self._pins[session_id]
                if self._on_evict:
                    self._on_evict(session_id)
                return None
            return provider

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._pins.pop(session_id, None)

    def touch(self, session_id: str) -> None:
        with self._lock:
            entry = self._pins.get(session_id)
            if entry is not None:
                self._pins[session_id] = (entry[0], time.monotonic())

    def cleanup(self) -> int:
        with self._lock:
            now = time.monotonic()
            stale = [sid for sid, (_, last) in self._pins.items() if now - last > self._ttl]
            for sid in stale:
                del self._pins[sid]
                if self._on_evict:
                    self._on_evict(sid)
            return len(stale)

    def size(self) -> int:
        with self._lock:
            return len(self._pins)
