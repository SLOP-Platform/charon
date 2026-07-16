# DESTIFF-SPECULATIVE — review fragment

**Ticket:** DESTIFF-SPECULATIVE — "No stiff single-provider tools" class-fix
(operator directive 2026-07-15) — speculative_execution is the 4th and last
known stiff caller.

## What changed

`src/charon/speculative_execution.py` adopts the shared
`failover_loop.invoke_with_failover` primitive (#141 on master) **by composition**
to replace the single hard-fail upstream call with a provider-classification +
ordered-candidate exhaustion flow.

A new `_classify(SpecResult) -> (kind, attribution)` helper maps each race
result to the `failover_loop` vocabulary:

* `OK` — 200 (race returns immediately, rest cancelled) or any non-provider-fault
  upstream response (e.g. an upstream-issued 400 — the verdict is valid, return
  it; do not skip it as FAILOVER or POST again as RETRY).
* `FAILOVER` — provider-level fault: 401/403/408/425/429/500/502/503/504 or a
  transport exception. The race's failover picks the next candidate.

After the race, if every completion was a `FAILOVER`, the ordered candidate
list is walked through `invoke_with_failover` with `max_retries=0`. The
`attempt` callable returns the **already-collected, already-classified** result
— no new HTTP call is issued, so the speculation never double-issues. If the
primitive exhausts, it raises the standard `"all candidates exhausted — <per-cand
attribution> — <recommendation>"` error.

## Why composition, not direct call

The ticket's note: *"don't double-issue / race the primitive"*. Calling
`invoke_with_failover` in parallel across candidates would (a) re-issue requests
the race already issued and (b) break the primitive's serialization invariant
(attributions + recommendation are sequential, not interleaved). Composing via
classification + post-race walk preserves both:

1. The race's first-good-wins (first 200 returned, rest cancelled).
2. The primitive's exhaustion contract (every candidate named, recommendation).
3. Single-issue per candidate.

## Accept test mapping

* `test_execute_failover_mid_race_yields_next_result` — A 401s first, B 200s
  second → race returns B's 200 (first-good-wins for OK). Passes via the
  existing race loop; the new classification just makes the OK detection
  explicit.
* `test_execute_all_fail_raises_exhaustion` — every candidate 401/429/503 →
  `RuntimeError` with `"all candidates exhausted"`, every candidate named
  (a:, b:, c:), each status surfaced (401, 429, 503), and the
  recommendation tail ("check keys, balances, and provider health") present.
* `test_execute_failover_does_not_reissue` — counts `urlopen` invocations:
  exactly one per candidate, no re-issues from the failover_loop walk.
* `test_execute_first_good_wins_unaffected` — race still picks the first 200.

## Files

* `src/charon/speculative_execution.py` — refactored
* `tests/test_speculative_execution.py` — 9 new tests (classify × 5, race × 4)

No off-owns changes. No new deps. Stdlib-only privileged core preserved.
