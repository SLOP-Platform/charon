# RFL-3 — finish image-aware routing (exclude non-vision models from image requests)

## Dependencies & sequence
**depends_on: RFL-1 — Wave RFL, on the proxy_server.py single-writer chain.** `proxy_server.py` is the
single-writer bottleneck; once RFL-1 lands it is the chain tail (… SR-13 -> RFL-1). RFL-3 edits the SAME
failover-loop candidate/exclude step in `_handle`, so it MUST rebase onto RFL-1's file, never write it
concurrently (`real-dep: RFL-1 build`, single-owner file). Depending on RFL-1 transitively orders RFL-3
after the whole SR chain (RFL-1 -> SR-13). RFL-2 sequences after RFL-3. Concurrency-safe vs RFL-5
(disjoint owns).

## Why
RelayFreeLLM comparison R3. Charon ALREADY detects `has_images` in `request_inspector.py` and carries
`vision` per-model metadata (`_META_KEYS`) — the detection and the data both exist. The only thing
missing is the routing EXCLUSION: without it, an image request can be routed to a text-only model and
fail (400/unsupported). This is a small, high-correctness wiring gap.

## Shared context (grounding for a fresh session)
- `request_inspector.py` sets `has_images` (scans message content parts for `image_url` — ~:12/:33).
- Per-model `vision` metadata is in `_META_KEYS` (`gateway.py:235`; surfaced in proxy_server.py ~:556).
- The failover chain is built in `proxy_server.py:_handle` (~:649 `srv.chain_for`, ~:697
  `order_by_cooldown`). The route/model meta for each chain entry carries the `vision` flag.

## What to build (proxy_server.py)
In the failover-loop candidate/exclude step, when the request `has_images`, DROP chain entries whose
model meta is not `vision:true`, so an image request is only ever routed to vision-capable models
(failover within/across providers proceeds as normal among the remaining vision models). Leave a
symmetric hook for `audio` (metadata already present) but scope THIS ticket to images. If NO
vision-capable model remains in the chain, fail cleanly with a clear error rather than silently trying a
text-only model. Additive + backward-compatible: non-image requests are unaffected.

## Acceptance / tests (`tests/test_image_routing.py` + regression)
- An image request routes ONLY to `vision:true` models; a text-only entry in the chain is excluded (assert
  the text-only upstream is never called).
- A non-image request is unaffected (full chain considered).
- An image request with NO vision model available fails with a clear error (not a silent text-only call).
- Full suite green.

## Red-proof
Include a test that FAILS if the vision exclusion is removed (assert the text-only upstream is not
invoked for an image request).

## CONSTRAINTS
- **Owns:** `src/charon/proxy_server.py`, `tests/test_image_routing.py` ONLY.
- Stdlib only; provider/agent-agnostic; product-clean; no `/home/stack` paths or dev-meta.

## accept
```
PYTHONPATH=src python3 -m pytest -q tests/test_image_routing.py && PYTHONPATH=src python3 -m pytest -q && ruff check src/charon/proxy_server.py && mypy src/charon/proxy_server.py
```

## REPORT BACK — MECHANIZED FORMAT (required)
End your session by emitting EXACTLY this block. Fixed fields, one line each, no diffs or logs.
Validate it before you finish: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Full spec + rationale: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`

```
=== SESSION REPORT v1 ===
TICKET:       <ticket-id>
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha> | none
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> is owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> | n/a — <why> | NOT-DONE
OBSERVABLE:   MET | DEFERRED — <what could not be observed and why>
RAN:          <what you proved by EXECUTING>
READ:         <what you concluded by READING only>
BRIEF-ERRORS: none | <what this brief got factually wrong>
BLOCKED-BY:   none | <ticket or condition>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
