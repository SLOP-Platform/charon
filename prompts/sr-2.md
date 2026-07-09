# SR-2 — serve genuine downgrades instead of discard-and-rebill, + cache streaming 200s

## Dependencies & sequence
**depends_on: SR-1 — Wave 2 (W2).** SR-1 corrects `_normalize_model_id`/`classify()` so that only
GENUINE downgrades remain; SR-2 then changes what the loop DOES with them. `real-dep: SR-1 build` —
same failover decision, disjoint owns (SR-1 proxy.py+test vs SR-2 proxy_server.py). SR-2 is the SOLE
owner of `proxy_server.py` in W2, so it runs concurrency-safe alongside SR-3 (cache.py), SR-4 (doc),
and SR-5 (config/discover/providers) — all disjoint owns. SR-6/SR-7/SR-8 (W3) sequence AFTER SR-2 on
proxy_server.py.

## Shared context (grounding for a fresh session)
Charon's failover loop treats a 200 whose returned model id differs from the requested id as a
"silent downgrade": it discards that already-billed completion (`count_usage=False`) and refetches
from the next provider — DOUBLE-BILLING. CONFIRMED live: `recent_failovers` = 50/50 with
`status==200`, all `asked 'deepseek-v4-pro', got 'accounts/fireworks/models/deepseek-v4-pro'`. Root
cause fixed in SR-1 (`_normalize_model_id`, `proxy.py:174-184`). The discard branches are
`proxy_server.py:756-760` (non-stream) and `:814-817` (stream); the `X-Charon-Downgrade` header is
already computed/sent at `proxy_server.py:778/820`. The non-stream success path already caches at
`proxy_server.py:769-772`; the streaming commit path (`~:818-838`) does NOT cache.

## What to build (both in proxy_server.py)
1. **Serve genuine downgrades, never re-bill a completed 200.** In the failover loop, when
   `pseudo_success` is a GENUINE downgrade, SERVE that already-completed 200 with the existing
   `X-Charon-Downgrade` header (`:778`/`:820`) instead of discarding and continuing to the next
   provider. A completed 200 is already billed — do not throw it away and pay again.
2. **Cache streaming 200s.** Add a `semantic_cache.set()` call on the streaming-200 commit path
   (`~:818-838`), mirroring the existing non-stream cache at `:769-772`, so agent/streaming traffic
   is cacheable (today only non-stream is cached).

## Acceptance / tests
- A genuine downgrade WITH alternatives available is served-with-`X-Charon-Downgrade`-header and
  makes NO second upstream call (assert the upstream is invoked exactly once).
- A streaming 200 populates the semantic cache (a subsequent identical request hits it).
- Full suite green: `PYTHONPATH=src python3 -m pytest -q`.
- **Doc deliverable — `docs/REVIEW-LOG.md` incident entry.** Write a `docs/REVIEW-LOG.md` entry for the
  2026-07-03 silent-downgrade double-bill incident: root cause (v0.2.0 did raw `returned != expected`;
  feat/prod-install's `_normalize_model_id` stripped only the first `/`-segment → provider-namespaced
  echoes like `accounts/fireworks/models/deepseek-v4-pro` false-flagged as downgrades → the completed,
  already-billed 200 was discarded and the next provider re-billed; `count_usage=False` + missing
  pricing made it invisible in `/charon/status`; confirmed 50/50 live). Fix: compare final `/`-segment
  (SR-1) + serve genuine downgrades with the existing `X-Charon-Downgrade` header instead of
  discard-and-rebill (SR-2).
- **Doc deliverable — new `docs/DECISIONS.md` register row.** Register a new row in `docs/DECISIONS.md`:
  Decision = 'Gateway failover never discards-and-rebills an already-billed 200; model-id equality is
  namespace/segment-tolerant (final-segment compare); genuine downgrades are
  served-with-`X-Charon-Downgrade`, not re-billed.' Owner = `OP+AI`. Status = `Settled`. Source =
  SR-1/SR-2 + REVIEW-LOG 2026-07-03. Add a note: the no-double-bill principle is firm; the matching
  heuristic (e.g. later version/date-suffix tolerance) is AI-revisable. NOTE: `docs/DECISIONS.md` and
  `docs/REVIEW-LOG.md` are append-only shared registers — editing them is an expected DOC deliverable
  of this ticket, NOT a new owned code path, and does not conflict with other tickets (append-only
  rows). Do NOT add them to `owns:`.

## CONSTRAINTS
- **Owns:** `src/charon/proxy_server.py` ONLY. Do not touch proxy.py (SR-1) or cache.py (SR-3).
- Provider/agent-agnostic; product-clean; never re-bill a completed 200.

## accept
```
PYTHONPATH=src python3 -m pytest -q tests/test_proxy_server.py && PYTHONPATH=src python3 -m pytest -q && ruff check src/charon/proxy_server.py && mypy src/charon/proxy_server.py
```
