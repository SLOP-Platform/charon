# RIG PR-clearing review — 2026-07-16 (master = fa07ca0)

> Master advanced to `71215d1` mid-review. Delta vs fa07ca0 = one commit touching only
> `fleet/board/BENCH-PROVISIONAL-SCORING.md`, which none of the nine PRs touch. **All findings
> and merge-tree results below still hold against 71215d1.**

READ-ONLY review. Repo: `/home/stack/charon-private` (Nnyan/charon-private). No CI in this repo —
land-time local gates are the only gate, so every verdict below rests on **executed** evidence,
not on "no checks reported".

## Verdict table

| PR | Verdict | Unblocks | Blocker |
|----|---------|----------|---------|
| #101 GITHUB-LIMITS-HARDENING | **NEEDS-WORK** | DONE-SH-INTEGRITY-FIX | prod path dead (`gh -r`); 2 accept bullets unmet |
| #103 DROID-LIFECYCLE-REAP | **NEEDS-WORK** | LAUNCHER-CRASH-PARTIAL-DETECT | reaper deletes committed work on unresolvable base |
| #106 FOREMAN-MULTI-TRIGGER | **MERGE-READY** | — (operator priority: Foreman) | none |
| #108 STARTUP-CONTEXT-DIET | **MERGE-READY** | SYNC-SCHEDULE | none |
| #105 ASSIGN-DISPATCH-PICK-FIX | **NEEDS-WORK** | — | carve-out leaks past dispatcher → silently un-gates F13 for `assign.sh` |
| #92 LAUNCH-PLAN-SH | **MERGE-READY** (land after #94) | — | coverage gap if landed before #94 |
| #94 STALE-CHECK-SH | **MERGE-READY** | — | none |
| #98 ON-DEMAND-TOOL-AUDIT | **MERGE-READY** | — | none (docs + ledger only) |
| #99 TSV-APPEND-UNIFY | **MERGE-READY** | — | none |

All nine merge **textually clean** against fa07ca0 (`git merge-tree` — no conflicts, none BEHIND/DIRTY).

---

## #101 GITHUB-LIMITS-HARDENING — NEEDS-WORK (highest unblock leverage, do not land as-is)

**Killer: the production code path is dead, and 19/19 tests pass anyway.** Textbook green-is-not-proof.

`fleet/gh-cache.sh:_gh_merged_files_tsv` builds its cache with:
```
gh pr list --repo "$slug" --state merged --limit 800 --json number,files \
   -r '.[] | . as $pr | .files[]? | "\($pr.number)\t\(.path)"' > "$cf.tmp"
```
`-r` is **not a valid `gh pr list` flag** (verified against `gh pr list --help`: the jq flag is
`-q/--jq`; `-r` is unclaimed). Live probe:
```
$ gh pr list --repo Nnyan/charon-private --state merged --limit 1 --json number,files -r '.[] | .number'
unknown shorthand flag: 'r' in -r
```
Consequence chain: gh call fails → `rm -f "$cf.tmp"`, cache never written → `cat "$cf"` empty →
`merged_prs_touching_file` returns empty → `done.sh:merged_pr_touching_owns` returns nothing →
**silent false negative on every real owns-match**. Proven live (fixtures unset):
```
merged_prs_touching_file Nnyan/charon-private fleet/done.sh  -> ''      (should find a merged PR)
cache dir after call                                          -> empty  (no file written)
branch_merged_pr Nnyan/charon-private fix/parked-semantics    -> 109    (control: uses valid -q, works)
```
Per the branch's own test comments, an unresolved owns-match makes done.sh **REFUSE** (exit 3).
So merging #101 makes done.sh refuse to done-mark tickets whose branch was squash-merged but whose
`owns:` files landed — a regression on the exact gate needed to done-mark and unblock dependents.

**Why the tests miss it:** every case sets `GH_MERGED_FILES_FIXTURE`, which short-circuits
`_gh_merged_files_tsv` at line 1. The broken `gh` call is never executed by any test.
`fleet/tests/test_github_limits.sh` = 19 passed / 0 failed while production is dead.

**Fix:** `-r` → `-q` in `_gh_merged_files_tsv`. Add one non-fixture test that asserts the cache file
is actually written (that is the seam the current suite structurally cannot see).

**Two accept bullets also unmet** (`fleet/board/GITHUB-LIMITS-HARDENING.md`):
- *"wired into preflight scan"* — diff touches **no** `preflight.sh`. `large-file-guard.sh` ships
  **inert**; nothing invokes it. (Its own 8 tests pass — the script works, it just never runs.)
- *"land/land-push pace sequential merges (small delay)"* — diff touches **no** `land.sh`/`land-push.sh`.
  Not implemented at all.

Note the ticket's `owns:` list excludes `preflight.sh` / `land.sh`, so those two bullets are
unsatisfiable within owns — ticket contradiction, needs an operator scope call (widen owns, or split
the wiring into a follow-up).

Also cosmetic-but-misleading: `_gh_merged_tsv`'s comment claims files are fetched in the *same* gh
call, but it requests `--json number,headRefName,files` and then discards `files` via `-q`;
`_gh_merged_files_tsv` makes a **second** call. Two calls per TTL, not one. Harmless for the
search-limit goal (still zero `--search`), but the comment is false.

## #103 DROID-LIFECYCLE-REAP — NEEDS-WORK (data-safety; reproduces the P0 it exists to fix)

Good news first — the P0 #4 guard is **real and wired**: `p0_worktree_setup` is defined at
`fleet/fleet-droid.sh:40` and actually called at `fleet/fleet-droid.sh:345` (not inert). It fetches
first, reuses a branch with unique commits, and never falls back to a `-B` reset. `foreman.sh`
wiring is real (new §5, reaper dry-run by default, `--apply` only under `--fix`). 40/40 tests pass.
Merges cleanly with fa07ca0's foreman.sh changes (master added §1–§5 at lines 35–120; #103 inserts
its §5 at 114 and renumbers verdict to §6 — git auto-merges, verified).

**But `fleet/reap-orphans.sh` has a fail-OPEN data-loss path.** Lines 155–162:
```bash
if git -C "$REPO" show-ref --verify --quiet "refs/heads/$branch"; then
  unique="$(git -C "$REPO" log --oneline "$BASE_REF..$branch" 2>/dev/null | wc -l | tr -d ' ')"
else
  unique=0
fi
```
If `$BASE_REF` is **unresolvable** (origin/master not fetched, wrong `RR_BASE` e.g. `main` vs
`master`, missing remote), `git log` errors → `2>/dev/null` swallows it → `wc -l` → **`unique=0`** →
falls into the DEAD+CLEAN branch (lines 195–210) → `worktree remove --force` / `rm -rf` →
**`git branch -D "$branch"`**. "Couldn't compute" is indistinguishable from "no work to lose".

**`fleet/reap-orphans.sh` never fetches** (`grep -nE 'fetch'` → no match), unlike
`p0_worktree_setup` which does `git fetch origin --quiet` before its equivalent check. So the
precondition for the bad path is a normal, reachable state.

Reproduced verbatim against lines 200–206 (worktree removed first, so the "used by worktree"
protection that would otherwise block `branch -D` is gone by the time it runs):
```
SETUP: branch feat/work carries commit 224c331 ('precious unmerged commit')
reaper computes unique='0'
==> DEAD+CLEAN path, executing reap-orphans.sh:200-206 verbatim:
    Deleted branch feat/work (was 224c331).
  RESULT: branch feat/work DELETED. Commit 224c331 is now unreachable.
  reachable from any ref? -> 0 refs
```
That is exactly consequence #3/#4 in the ticket ("a bad reaper deletes work"; the branch the manager
`branch -D`'d with 2 commits) — reproduced *by the fix*. Tests miss it because every fixture builds a
resolvable `origin/master` via `REAPER_BASE`.

**Fix (fail-closed):** capture `git log`'s exit status; if the rev-range fails to resolve, treat as
**UNKNOWN → PRESERVE**, never clean. Add `git fetch origin --quiet || true` before the check, and
guard on `git rev-parse --verify "$BASE_REF"` succeeding. Fail-on-revert test: dead-PID claim +
branch with commits + **unresolvable base** → branch must SURVIVE.
The same "unresolvable base → has_unique=0" shape exists in `fleet-droid.sh:p0_worktree_setup`
(there it falls through to `leak_worktree_setup`'s `-B` reset); the fetch mitigates but does not
eliminate it, since the fetch is `|| true`. Fix both call sites.

Minor: PID-reuse (`alive(){ kill -0 "$1"; }`, line 90) fails **safe** — a recycled PID reads as live,
so the claim is left alone (stale claim, no data loss). Acceptable.

## #106 FOREMAN-MULTI-TRIGGER — MERGE-READY (operator priority)

- `fleet/tests/test_foreman_triggers.sh`: **24/24 pass** (executed).
- Accept *"No automated path calls `foreman.sh --fix`"* — **verified**: `foreman-cadence.sh:12`
  documents report-only and no subcommand passes `--fix`.
- All four triggers present + fail-on-revert coverage per trigger (session-start / post-land /
  handoff / cadence each assert "recognized subcommand" AND "runs foreman.sh, not stubbed").
- `fleet/handoff.sh` hunk is +6 lines at line 341 — disjoint from #108's hunks. Clean vs fa07ca0.
- `handoff.sh:344` hardcodes `/home/stack/charon-private`, but matches the adjacent pre-existing
  `validate_board.sh` line in the same file; rig-only file, not a product path. Not a blocker.

## #108 STARTUP-CONTEXT-DIET — MERGE-READY

- Budget gate is **genuinely wired**: `preflight.sh:709` default `scan|""` path runs
  `startup_budget_gate` **before** `cmd_scan`, so a breach auto-registers a blocking P1 red.
- Gate **executed** post-merge (all five artifacts within budget, TOTAL 85441/89500, exit 0).
- Fail-on-revert **proven, not inferred**: `preflight.sh startup-budget-selftest` →
  `PASS (gate fires on over-budget file — fail-on-revert verified)`.
- The earlier `error: registry not found: fleet/reds.tsv` in a detached worktree is a test-env
  artifact — `reds.tsv` is gitignored live state (`.gitignore:31`), present in the real fleet dir.

**#108 ↔ #106 interaction — measured on a real double merge, both orders safe:**
```
BASE master:     handoff.sh=18389   <-- ALREADY OVER #108's own 17500 budget
after #108 DIET: handoff.sh=16505   (budget 17500)
after #106:      handoff.sh=16724   (budget 17500, 776 bytes headroom)
```
No conflict; #106's +219 bytes fit. Note master's handoff.sh is **already over** the budget #108
introduces — #108's diet is what brings it under, so the gate is self-consistent only *with* #108.
Headroom is thin across the board (362–1513 bytes; `handoff-check.sh` is tightest at 362). Any
future PR growing these five files should land **before** #108 or raise the budget in the same commit.

## #105 ASSIGN-DISPATCH-PICK-FIX — NEEDS-WORK (silent gate degradation)

The carve-out itself is well-reasoned (dispatcher has a pre-vetted candidate set, so the F13
control-panel gate is the wrong discipline there; `real_only=True` preserved so synthetic rows stay
denied). **But it is applied one level too high.**

`assign.py:528` swaps the provider inside `main()` — i.e. for the **entire CLI**, not the dispatcher
lane:
```python
grades = _DispatchGradesProvider(args.tsv) if args.tsv else _DispatchGradesProvider()
```
The class docstring (`assign.py:84`) claims: *"Production capability grades (the SESSION-MANAGER's
path) are unchanged — that path still uses the F13-gated `ScorecardGradesProvider` directly via its
own import in the SESSION-MANAGER, never through this wrapper."* **That consumer does not exist.**
Only `fleet/capability/selftest.py` imports `ScorecardGradesProvider` directly (frozen fixture, tests).
The real SESSION-MANAGER path is `fleet/assign.sh:9` → `exec python3 capability/assign.py "$@"` —
the documented "ticket → best-agent recommendation" entrypoint (`START-SESSION.md:54`,
`BRIEF-TEMPLATE.md:13`). So #105 silently disables the F13 control-panel gate for the manager's
agent-pick path — the gate-degradation class, justified by a docstring describing an architecture
that isn't in the tree.

**Fix (discriminator already exists):** `--candidates` is dispatcher-only —
`fleet-droid.sh:88` passes `--candidates "$static_csv" --print-model`; `assign.sh`'s manager form
does not. Gate the swap on it:
```python
_G = _DispatchGradesProvider if args.candidates else ScorecardGradesProvider
grades = _G(args.tsv) if args.tsv else _G()
```
Then correct the docstring to describe the real seam. Add a test asserting the **non**-`--candidates`
path still enforces the control panel.

## #92 / #94 — MERGE-READY as a PAIR, #94 FIRST

#92 removes 39 lines of stale-check coverage from `fleet/tests/launch-plan.test.sh`, handing it to
#94's new `fleet/tests/stale-check.test.sh`. **Verified the handoff is 1:1** — stale-flagged /
fresh-not-flagged / loop-guard-quarantine cases all reappear in #94. Both executed:
`stale-check.test.sh: ALL PASS`, `launch-plan.test.sh: ALL PASS`.
**Land #94 before #92** — the reverse order leaves a window with zero stale-check coverage.
fa07ca0 added `parked-claim-e2e.test.sh` + `parked-semantics.test.sh` (different files) — no conflict.

## #98 — MERGE-READY. Docs + ledger only (`docs/review-log/ON-DEMAND-TOOL-AUDIT.md`,
`fleet/state/ON-DEMAND-TOOL-LEDGER.tsv`). No code, no gates, zero blast radius.

## #99 — MERGE-READY. `auto_append.py` genuinely delegates to `model-scorecard.sh` via
`subprocess.run` (`auto_append.py:90`, `SCORECARD_SH` at :26) — real dedupe, not an inert wrapper.
`pytest test_tsv_append_unify.py` → **4 passed**.

---

## RECOMMENDED MERGE SEQUENCE

**Wave 1 — land now (all verified green, zero collisions):**
`#98` → `#99` → `#94` → `#92` → `#106`
(#94 strictly before #92. #106 is the operator-priority Foreman; +6 lines at handoff.sh:341,
disjoint from #108.)

**Wave 2 — land after Wave 1:** `#108`
Order-critical: the budget gate goes live on **every** preflight. Land it after #106 so handoff.sh
growth is already accounted (measured: 16724/17500, 776 bytes spare). Re-run `preflight.sh` once
after landing to confirm the gate reports green on the real fleet.

**Wave 3 — send back, do NOT land:**
- `#101` — one-char fix (`-r`→`-q`) + a non-fixture cache test; then an operator call on the two
  unsatisfiable accept bullets (preflight wiring + land pacing are outside `owns:`).
- `#103` — fail-closed the reaper's unique-commit check (+fetch, +`rev-parse --verify` guard, both
  call sites) + a fail-on-revert test with an unresolvable base.
- `#105` — gate the provider swap on `args.candidates`; fix the docstring; add a test that the
  manager path still enforces F13.

**Net:** Wave 1+2 lands 6 PRs and frees **SYNC-SCHEDULE** (via #108). The two highest-leverage
unblocks — **DONE-SH-INTEGRITY-FIX** (#101) and **LAUNCHER-CRASH-PARTIAL-DETECT** (#103) — stay
blocked; both are small, well-scoped fixes worth a droid round-trip rather than a land-and-regret.
#101 in particular would actively break done-marking (the mechanism that unblocks dependents) if
landed as-is.

**Crash-partial classification:** none of the nine reviewed PRs is crash-partial. All carry coherent,
scoped work matching their ticket's `owns:` (#101's `owns:` gap is under-reach, not debris). The
launcher-auto-commit PRs flagged in the prior audit (#107, #104, #62) were out of this review's scope.
