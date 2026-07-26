# RFL-3 — vision-aware route exclusion (self-contained)

You are working in an isolated git worktree checked out from `origin/master`. Everything you
need is in this repo. Do NOT register anywhere, do NOT wait on any other ticket — just make the
change below and stop.

## What's broken

Charon already detects images in a request and already carries per-model vision capability —
but nothing connects the two for routing:

- `src/charon/request_inspector.py` — `RequestInspector.inspect()` already computes
  `has_images` (scans message content parts for `type: "image_url"`, lines ~12/32-33).
- `src/charon/gateway.py:230` — `_META_KEYS` includes `"vision"`; per-model metadata
  (`model_meta`, keyed by registry model id) already carries a `vision: bool` flag when the
  registry entry sets it.
- `src/charon/forwarder.py` (`forward_with_failover`, the money-path failover loop) builds the
  ordered candidate `chain` for the requested model (`srv.chain_for(requested)`) and already has
  a precedent for exactly this kind of thing — the "capability-based route exclusion" block
  (~line 279) drops routes that don't support a *reasoning* capability. **There is no equivalent
  exclusion for images/vision.** An image-bearing request can be routed to a text-only model,
  which will 400/fail upstream.

`tests/test_image_routing.py` does not exist.

## Required change (`src/charon/forwarder.py`)

In `forward_with_failover`, after the chain is built (`chain = srv.chain_for(requested)` and its
no-route guard) and before/alongside the existing capability-based exclusion block, add a
vision-aware exclusion:

1. If `srv.request_inspector` is set, call `.inspect(orig_bj.get("messages") or [])` to get
   `RequestHints` (see `src/charon/types.py`).
2. If `hints.has_images` is true: look up each chain entry's own `model_id` (an `UpstreamRoute`
   field — the registry model id for that specific leg, which may differ per provider within the
   same pool) in `srv.model_meta`, and keep only the entries whose meta has `vision: true`.
3. If at least one vision-capable entry remains, narrow `chain` to just those entries (failover
   proceeds normally among the remaining vision-capable legs).
4. **If NO vision-capable entry remains, fail cleanly** with a clear 502 error — do **NOT**
   silently fall back to the full chain (this is a HARD functional exclusion, unlike the softer
   reasoning-capability heuristic which DOES fall back to avoid stranding — sending an image to
   a text-only model is not a heuristic near-miss, it will hard-fail upstream regardless).
5. A request with no images is completely unaffected — this filter must be a no-op when
   `has_images` is false.
6. Leave a symmetric hook/shape open for `audio` (metadata key already exists) but scope this
   ticket to images only.

## Hard constraints

- **Owns:** `src/charon/forwarder.py`, `src/charon/proxy_server.py` (only if strictly needed —
  the exclusion belongs in `forwarder.py`'s existing filter-block style; do not move it into
  `proxy_server.py` unless there's a concrete reason), `tests/test_image_routing.py` ONLY.
- Stdlib only. No behavior change to non-image requests.
- Reuse `RequestInspector`/`RequestHints` and `model_meta` as they exist today — do not invent a
  parallel image-detection or vision-flag mechanism.

## Acceptance (what will be checked)

1. An image request (a message with a `content` part of `type: "image_url"`) routes ONLY to
   chain entries whose `model_meta[route.model_id]["vision"]` is `true` — a text-only entry in
   the SAME chain is excluded and never receives the request.
2. A non-image request is completely unaffected — the full chain (in its normal cost/cooldown
   order) is still considered.
3. An image request where NO chain entry is vision-capable fails with a clear error (502) — the
   text-only upstream must NEVER be silently called as a fallback.
4. Full suite green (no regression).
5. **`tests/test_image_routing.py` contains a NEW test function named
   `test_image_request_excludes_text_only_model`** (or a materially equivalent name covering the
   same assertion — exclusion actually happens) — checked mechanically (grep-by-name), not just
   "some test file exists," since a stub/empty test file would otherwise pass a naive existence
   check trivially.

### DOGFOOD_TEST_CMD (discriminating — new test file+name added, it passes, no regression)

```
PYTHONPATH=src python3 -m pytest -q tests/test_image_routing.py \
  && python3 -c "import re,sys; c=open('tests/test_image_routing.py').read(); \
       sys.exit(0 if re.search(r'def test_image_request_excludes_text_only_model', c) else 1)" \
  && PYTHONPATH=src python3 -m pytest -q
```

This fails on unmodified `origin/master` today — `tests/test_image_routing.py` doesn't exist at
all, so `pytest -q tests/test_image_routing.py` errors out (rc=4, file/dir not found) before the
grep-confirm or full-suite steps are even reached. It only turns GREEN once the exclusion is
actually implemented AND the specifically-named new test is added AND passing AND the full
suite still passes. Verified via a throwaway `git worktree`, 2026-07-13 — RED-proof=OK per
`fleet/benchmark/test-quality-gate.py` (unmodified rc=4; with a real reference-fix diff applied,
rc=0 and the full 1726-test suite stays green).

## Un-parking note (throwaway eval use only)

`RFL-3` is `.parked` on the real board for real sequencing reasons (behind the
`proxy_server.py`/`RFL-1` single-writer chain — see `fleet/board/RFL-3.md.parked`). That parked
status governs the real board/land path only. For THIS throwaway dogfood-eval worktree (never
committed/merged/pushed), the parked flag is not a blocker — it just runs the candidate against
current `origin/master` content. Do not un-park `RFL-3` on the actual board as a side effect of
using this brief here.
