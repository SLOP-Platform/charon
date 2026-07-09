# SR-3 — cache correctness + stats

## Dependencies & sequence
**depends_on: (none) — Wave 2 (W2), parallel with SR-4 and SR-5.** Board-unblocked. Owns
`src/charon/cache.py` + `tests/test_cache.py`, disjoint from SR-2 (proxy_server.py), SR-4 (doc),
SR-5 (config/discover/providers) — fully concurrency-safe within W2. No disjoint-owns dep to justify.

## Shared context (grounding for a fresh session)
This is part of the SR "smart-routing / gateway cost-correctness" series. The gateway has a semantic
cache used on the request path; SR-2 (W2) additionally makes streaming 200s cacheable. Cache
correctness matters because a FALSE hit returns a WRONG answer for code/precise work.

## What to build (in cache.py)
1. **Keep exact SHA-256 keying.** Do NOT introduce fuzzy/semantic similarity matching. Document (in
   a module docstring / comment) WHY: for code and precise work a near-miss "similar prompt" hit
   returns a wrong answer — exact-hash keying is the safe default.
2. **Add hit/miss counters.** Track cache hits and misses and surface them via `charon cache stats`
   and/or the status output (counts, and hit-rate). Keep the surface minimal and stdlib-only.

## Acceptance / tests (tests/test_cache.py)
- Hit and miss counters increment correctly across a set/get sequence.
- Exact-match get returns the stored value (hit); a differing prompt is a miss (no false hit).
- `charon cache stats` (or the status surface) reports the counters.
- Full suite green: `PYTHONPATH=src python3 -m pytest -q`.

## CONSTRAINTS
- **Owns:** `src/charon/cache.py`, `tests/test_cache.py`. If the stats surface needs a CLI line,
  keep it inside cache.py's public API — do NOT edit cli.py in this ticket (avoid W2 collisions).
- Stdlib-only; product-clean; provider/agent-agnostic.

## accept
```
PYTHONPATH=src python3 -m pytest -q tests/test_cache.py && ruff check src/charon/cache.py && mypy src/charon/cache.py
```
