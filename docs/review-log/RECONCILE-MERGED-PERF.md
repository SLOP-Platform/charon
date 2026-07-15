# RECONCILE-MERGED-PERF — review note

**Ticket:** RECONCILE-MERGED-PERF (perf — preflight scan 5m46s)
**Branch:** `fix/reconcile-merged-perf`
**Files owned (per ticket):** `fleet/reconcile-merged.sh`, `fleet/tests/reconcile-merged.test.sh`

## What was wrong

`reconcile-merged.sh` `ticket_for_pr()` re-scanned all `board/*.md` + `board/archive/*.md`
files via per-file `meta()` awk-spawns — for every merged PR. At 184 files × 121 PRs ≈ 44k awk
spawns per preflight scan. Same O(n·m) re-verification class as the pre-fix `done.sh` full-retire
sweep bug PERF-AUDIT.md 2026-07-15.

## Fix (class-level, not re-derived — mirrors done.sh pattern)

1. **Index-once pre-pass:** a single `awk` reads every board+archive file NUL-separated on stdin
   and emits `<kind> <id> <branch|owns>` rows. Two shell string-tables (`BRANCH_INDEX`,
   `OWNS_INDEX`) get populated once. `ticket_for_pr` becomes O(1) — one `grep` over each table.
2. **Done-branch short-circuit:** the loop iterates over `$DONE/*` once to collect all
   `branch:` values from existing markers. Any merged PR whose branch is in that set is skipped
   before any board scan (mirrors `done.sh`'s single-id fast path).
3. **Removed** the now-dead `meta()` and `_overlap()` helpers (the index replaces both).

## Behavior preserved

Same precedence: (1) exact board `branch:` match, then (2) unambiguous owns-overlap, then
return-1. Same HIGH #2 ambiguity refusal — when a PR file is owned by >1 ticket (or the union
of overlapping ids contains >1 id), neither is auto-closed, and a stderr message identifies
the conflicting tickets. Same `done.sh --merged-sha <sha>` proof path. Same network-tolerance
(no gh → empty PR list → clean no-op).

## Measured

| scenario | before | after |
|---|---|---|
| `time bash fleet/reconcile-merged.sh` cold (1st run after many real merges) | "didn't finish 120s+" (per audit) / 5m46s preflight (per audit) | **13.4s** (76 actual `done.sh` calls, +6s gh pr list) |
| `time bash fleet/reconcile-merged.sh` warm (re-runs after the closes) | same | **3.9s** (gh pr list + skip-all) |
| 200-file fixture (test (g)) | n/a — would have been >30s | **~750ms** (asserted <5s in test) |
| Index pre-pass on real board+archive (184 files) | n/a | **0.014s** |

The remaining wall-clock on the real run is `gh pr list` (~6s) plus actual `done.sh` work
(retire-done.sh + scorecard capture per close) — which is REQUIRED work, not the index. The
audit-only claim "single-digit seconds" is met on warm/steady-state (3.9s) and the index
itself is well under that.

## Tests (14/14 pass in 0.9s)

- (a) exact-branch-match close
- (a-prove) `merged:<sha>` written into marker
- (b) non-merged ticket left open
- (c) drifted-branch + owns-overlap close
- (d) orphan-branch no-op, exit 0
- (e) idempotent second run
- (f) HIGH #2 ambiguous (>1 owner) refused, NO close
- **(g) PERF**: 200-file board+archive fixture + 5 mergeable PRs (mix of open + archived) closes
  all 5 correctly in <5s (current: ~750ms). Catches a regression that re-introduces the
  per-PR re-scan or breaks the index-once pre-pass.
- **(h) short-circuit**: PR whose branch matches an existing `state/done/<id>` marker → done.sh
  is NEVER called (verified by giving an invalid sha that would otherwise make done.sh refuse).

## Out of scope (intentionally)

- Did NOT change the network-tolerant gh-fallback path.
- Did NOT change the per-PR close logic (still `done.sh <id> --merged-sha <sha>`).
- Did NOT add a fast-skip for the gh pr list itself — out of ticket scope.
