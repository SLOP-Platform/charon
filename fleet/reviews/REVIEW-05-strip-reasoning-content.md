# Adversarial Review — `feat/strip-reasoning-content` (fleet #5)

- **Verdict:** MERGE
- **Branch:** `feat/strip-reasoning-content` @ `c5cecf1`
- **Base:** `origin/master` @ `f79a898`
- **Reviewer:** Charon fleet manager adversarial review (read-only)
- **Date:** 2026-07-05

## What the branch actually contains (verified, not self-reported)

`git diff --stat origin/master...HEAD` — 4 files, +340 / -0:

| File | Change |
|---|---|
| `src/charon/request_normalizer.py` | NEW, 70 lines — strip module |
| `src/charon/proxy_server.py` | +8 lines — wired into `_build_upstream_req` |
| `tests/test_request_normalizer.py` | NEW, 139 lines — 11 unit tests |
| `tests/test_proxy_server.py` | +123 lines — 3 integration tests through the real proxy |

Single commit. No product code touched beyond the two src files. No hidden changes.

## Gate + tests (real results)

- `PYTHONPATH=src python3 -m charon.cli gate` → **PASS**
  `[ruff] OK  [mypy] OK  [SLOP-boundary] OK  [version] OK  [gate-registry] OK`
- `PYTHONPATH=src python3 -m pytest -q` → **PASS**, `1158 passed in 83.89s`
  (note: `python3 -m charon.cli gate` without `PYTHONPATH=src` fails with ModuleNotFoundError — invocation quirk, not a branch defect.)

## Correctness (adversarial)

**Does it strip `reasoning_content` from inbound assistant messages on the request path?** Yes.
`normalize_messages()` removes `reasoning_content` and `reasoning` from any message whose `role == "assistant"`. There are BOTH a unit test asserting the field is gone AND an integration test (`_MessageCapturingUpstream`) that captures what the upstream actually received and asserts `forwarded[1] == {"role":"assistant","content":"hello"}` with `reasoning_content` absent. This is real proof, not a claim.

**Applied at the right point?** Yes — best possible point. The strip lives in `_build_upstream_req`, which is called **inside the failover loop** (`proxy_server.py:751`), once per route/attempt, always rebuilt from `orig_bj`. Consequences:
- Every failover target (free-tier substitution, non-DeepSeek provider) receives a clean body — the exact multi-provider case the ticket targets.
- It runs **unconditionally** after the `stream_options` block, so streaming and non-streaming are both covered. Streaming only affects the *response* decode path; the outbound request body is identical, so a single strip point is correct.
- It operates on the request body only; the existing `response_normalizer` (line 821) is on the response path and is untouched — no ordering conflict.

**Does it strip too much?** No.
- Only two fields, only on `assistant` role. `system`/`user`/`tool` messages pass through verbatim (test: user-role `reasoning_content` is preserved).
- `tool_calls` survive (both a unit and an integration test assert the tool_calls array is byte-identical after strip).
- Non-dict / `None` entries pass through without crashing (test present).

**Single-provider DeepSeek round-trip broken?** No. DeepSeek's own API spec marks `reasoning_content` as output-only and explicitly says it must NOT be sent back in subsequent turns, so stripping is correct even when the next hop is DeepSeek again. No provider requires an assistant-message top-level `reasoning`/`reasoning_content` on replay.

**`reasoning` top-level request param collision?** None. The strip only removes `reasoning` when it is a key **inside an assistant message dict**, never the top-level request-body `reasoning` param (e.g. OpenRouter effort control) — that is left intact.

**Non-chat routes (`/v1/models`, embeddings)?** Safe. `bj.get("messages")` is `None`/absent → `normalize_messages` returns `None` → body unchanged.

**Mutation / idempotency:** deep-copies each message, returns a new list, does not mutate `orig_bj` (important since `orig_bj` is reused across every failover attempt). Idempotent and non-mutating — both covered by tests.

## Blast radius

Request path is the money/correctness path, but the change is minimal and additive: it removes two provably-invalid fields and forwards everything else verbatim (`test_proxy_forwards_normal_body_unchanged` asserts a normal body is byte-for-byte identical). No existing test regressed (1158 pass). Only realized cost is a `copy.deepcopy` of the messages array per attempt — negligible and necessary for per-attempt isolation.

Minor (non-blocking) nits:
1. `reasoning_content` in DeepSeek is a top-level message key, which is exactly what's handled. If a future provider nests reasoning inside a `content` array element, this won't catch it — out of scope for the current bug and no such case exists on the OpenAI-compatible path today.
2. Integration tests use a module-level `_SEEN_MESSAGES` global cleared per test — fine under serial pytest; would be fragile under `-p xdist` parallelism. Cosmetic.

## Product / build-rig boundary

Clean. `grep -rn 'home/stack|fleet|SLOP|charon-private|charon-strip'` over `src/` returns only pre-existing generic `runner` seam references in `engine/scheduler.py` (test-injection seam, unrelated). No `/home/stack` paths, no fleet/SLOP/runner leaks in the new files or committed config. `[SLOP-boundary]` gate check passes.

## Verdict

**MERGE.** Well-scoped, correct, applied at the single right point (per-attempt, before forward, covering all failover targets + streaming), does not over-strip, does not break DeepSeek round-trips, gate green, 1158 tests pass with real assertions that the field is actually gone from the forwarded body, no boundary leaks.
