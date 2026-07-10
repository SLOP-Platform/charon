# REVIEW — session-cost-tracker (per-session cost counter)

- Branch: `feat/session-cost-tracker` · commit `47d57c7` (off origin/master)
- Worktree: `/home/stack/code/charon/.worktrees/session-cost`
- Files: `src/charon/proxy.py` (`record(..., session=)`, `session_usage()`, `_session_usage` dict), `src/charon/proxy_server.py` (GET `/charon/cost`, `X-Charon-Session` threading), `tests/test_proxy_server.py`, self-test `fleet/benchmark/selftest/session_cost_selftest.py`
- Reviewer: adversarial, read-only. Full suite 1240 PASS.

## VERDICT: LAND-WITH-FIXES

The isolation is correct, the change is genuinely read-only, and semantics are right. The one real defect is a product-grade unbounded-memory growth on a client-controlled key. Not a correctness blocker for the benchmark's immediate use, but it is product code on the money-observability path meant to run long-lived, so the cap should land with it. Fix routes to Sonnet.

## 1. Unbounded memory growth — CONFIRMED, top finding
`self._session_usage: dict[str, Usage]` (proxy.py:259) is only ever `.get()` + assigned (:422–423). No cap, no LRU, no TTL, no eviction anywhere. The key is the **caller-supplied `X-Charon-Session` request header** (proxy_server.py:698), and the default gateway token is `None` (open on loopback) — so any client can mint arbitrary session ids. A naive client that sets a fresh id per request (e.g. a UUID), or a hostile one, accumulates a permanent bucket per distinct value → unbounded RSS growth / DoS on a long-running gateway. The builder's own inline comment acknowledges it is "unbounded only in the number of distinct session ids a caller chooses to use" — that is an assumption about well-behaved callers, not an enforced bound.
**RECOMMEND:** bound it — an `OrderedDict`-backed LRU with a generous cap (e.g. 4096 sessions, evict oldest on insert) or a TTL sweep. A generous cap keeps benchmark reads intact (evicted session simply reads back as zero `Usage`, never an error). Only the write path creates buckets; GET cannot.

## 2. Isolation correctness — YES
Keying is exact-string, per-session buckets live in a separate dict, accumulation is additive under the existing `self._lock`. `session=None` never touches the dict; the global counter is unchanged. An unseen id returns zero `Usage`, never raises, never another session's data. The self-test is **strong, not weak**: it drives a concurrent request under a *different* session id AND a *no-header* request between snapshots, then asserts the bench bucket == exactly its own spend, the dummy bucket == its own, global == sum of all three, and unseen == 0. Product test `test_session_cost_isolated_across_sessions_and_from_global` corroborates (a/b/None). Session A can never see B. (Minor: the self-test `join()`s the dummy thread before the third post, so it is not a true race-stress — but the lock makes races safe and keying correctness is proven regardless.)

## 3. count_usage semantics — CORRECT as built
Session usage folds on the identical `count_usage=True` rule as the global counter. Failed-over/unreachable/429/402/stream-broke attempts (`count_usage=False`) are NOT counted — right, no money was spent. The one case that counts an attempt not delivered to the client is the paid **downgrade** that fails over onward (`pseudo_success and more` → `record(count_usage=True)`): that provider was genuinely billed, so counting it is correct for "attributable spend." Matching the global rule is a virtue — session totals sum to ≤ global, and `/charon/cost` with no session == global. Do NOT narrow it to "genuinely-served responses only"; that would under-report real money spent.

## 4. Read-only / injection — clean
GET `/charon/cost` only calls `session_usage()`/`cumulative_usage()` (read under lock) and returns JSON — no mutation, no billing change. `?session=` is `parse_qs`→first value→single dict `.get()`; unknown key → zero, no enumeration, no unbounded query, cannot return another session's data (exact match). Empty header → `or None` avoids a "" bucket. The `session` value is reflected in the JSON body but JSON-escaped and visible only to its own caller (low risk). Hot-path overhead in `record()` is one get + one `Usage` construct + one assign, inside the pre-existing lock — negligible, no new lock. Note: `/charon/cost` is only as protected as the general token gate (default open), same exposure class as the already-existing `/charon/status` — no new leak.

## 5. Gate/test adequacy — good, with gaps tied to the fix
Covered: header-present, no-header, cross-session isolation, global sum, GET-endpoint agreement, unseen-session-zero. Missing: (a) no cap/eviction test — because there is no cap (the finding itself); add alongside the fix; (b) malformed/huge/empty header value — untested (empty handled by `or None`; others are just dict keys, low risk); (c) true concurrent same-session race — untested but lock-covered.

## Bottom line
Isolation ✔, read-only ✔, semantics ✔. Land after adding a bounded cap/TTL on `_session_usage` (route to Sonnet). Everything else is production-ready.
