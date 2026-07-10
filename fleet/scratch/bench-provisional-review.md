# Adversarial review — BENCH-PROVISIONAL-SCORING (#20)

Branch `feat/bench-provisional-scoring` @ 9c5714a, worktree `/home/stack/charon-private-wt-provisional`.

## VERDICT: SHIP (one recommended minor FIX; no blocker)

The fail-closed property #20 exists to protect is intact and *empirically proven*. The
stage gate composes as a strict AND with the `{live}` source allow-list, legacy rows
default safely, the promotion gate is correct, and the new tests are real (not tautologies).
One smoke-layer consistency gap found (non-blocking).

## Scrutiny results

1. **Fail-closed composition — PASS.** `grades.py:285-288` — the source allow-list and
   the stage gate are two independent `continue` guards, i.e. strict AND (a provisional
   row is dropped regardless of source; a non-live row is dropped regardless of stage).
   No OR / short-circuit / default leak. Every live-grade path (`grade()` at
   grades.py:297/300/303) calls `_rows_for()` with the default `include_provisional=False`;
   nothing in the live path opts back in. `include_provisional=True` is analysis/promotion-only.

2. **Legacy default-active — PASS (with 1 documented caveat).** `<16`-col rows and
   empty-stage cells default to `active` consistently across all four parsers
   (grades.py:253, tier_chart `_stage`, model-scorecard.sh append `${..:-active}` + render
   `NF>=16`). Correct: legacy rows predate the concept and were always counted, so no
   historical grade shifts. This is fail-open ONLY on the legacy axis; the trust gate
   stays fail-closed (only an explicit `provisional` excludes). Caveat (process, not code):
   a genuinely-NEW unit that is *not registered* in `units.tsv` also defaults active
   (`bench.sh:unit_stage` END→active), so it would count immediately. Mitigated today
   because new sections are `source=bench` (already source-excluded) and reds-replay (#25)
   is unbuilt; the units.tsv header documents that new units MUST be registered
   `provisional`. Acceptable for #20 scope.

3. **Promotion gate (`promote.py`) — PASS.** `evaluate_gate` (promote.py:233) promotes
   IFF `distinct_models >= K(2) AND spread >= 15`. Saturated all-100 → spread 0 → refused;
   discriminating (100,40) → promoted; single-model → refused. selftest proves all three
   pure-function cases AND end-to-end `--apply` (flips discriminating, leaves saturated).
   Known v1 limitation (documented, deferred to #16/#17): two models with a spurious
   15-pt spread from noise CAN promote — the bar is deliberately low per plan §8 Q5.

4. **Test adequacy — PASS (verified real).** Empirically reverted the stage gate in-memory:
   glm-5.2/routing goes n=3/merge=2 → n=4/merge=3, which FAILS the selftest assertion
   (`selftest.py:531`). The fixture's provisional row (`scorecard-fixture.tsv:73`,
   source=live so it passes the source allow-list — ONLY the stage gate can exclude it) is
   the right adversarial probe. `include_provisional` collected-not-counted check and the
   gate checks are also real. Both selftests pass (capability EXIT 0, token-capture EXIT 0).

5. **Consumer blast radius — ONE gap (non-blocking).** grades.py, tier_chart.py (both
   `bench_rows_for` and `bench2_rows_for`), and model-scorecard.sh `render` are all gated;
   assign() unaffected; token/legacy positional reads unaffected (stage is the *trailing*
   16th col). **GAP:** `fleet/benchmark/lib/close_season.py:126` (`bench2_rows_from_tsv`)
   filters `source == "bench2"` but does NOT apply the stage filter that the builder added
   to tier_chart's `bench2_rows_for`. So a future provisional bench2 row WOULD enter a
   season composite, violating the builder's own stated smoke invariant ("a provisional
   section can never move even the demoted smoke chart"). NOT a fail-closed leak — bench2
   season composites are smoke-only and never feed capability grades — and inert today
   (S0–S6 all active; no provisional bench2 rows exist). Minimal fix: add the same
   `if _stage(cols) != "active": continue` guard in `bench2_rows_from_tsv`.

## S6-grader jsdom/npm failure — UNRELATED (confirmed)

`git diff --name-only master...` touches 10 files; zero are grader/section/jsdom/package
files. jsdom lives in `benchmark/package.json` + s6 `vite.config.js` goldens, none in the
diff. The builder's claim (touched no grader files) checks out. Pre-existing, independent.

## Confidence: HIGH
Core fail-closed property verified by code-read + in-memory revert experiment + green
selftests. Only finding is a smoke-only consistency gap that cannot move a live grade.
