# DIRTY-WORKTREE-SWEEP — review fragment

## What was done

Swept the 17 abandoned dirty worktrees (uncommitted/untracked files, no live claim) detected by
fleet/checks/stranded-work.sh. Full per-worktree verdicts with byte-compare evidence live in
fleet/state/DIRTY-WORKTREE-SWEEP.md (state file, gitignored).

Decision rule applied per worktree, in the ticket's order:
(a) ALREADY ON MASTER — byte-compare against origin/master before clearing.
(b) REAL WORK — preserved untouched, must be committed to its ticket's branch + PR'd.
(c) DEBRIS — regenerable artifact / scratch / leftover, deleted, naming what it was.

Outcome (17/17):
- 13 cleared: 9 x regenerable `graphify-out/manifest.json` (restored to HEAD; the whole rig
  graphify-out/ was untracked on master in 50426cd, 8 of 9 copies byte-identical = shared
  regeneration), 1 x NS-CONTENTION redundant/superseded handoff docs (one byte-identical to the
  landed blob, one an earlier draft superseded by the landed 20:20:52Z revision), and 4 x one-off
  debris (`.venv-gate/` virtualenv, `full_pytest.log`, `scratch/dogfood/` dogfood sandbox,
  `maestro-repo/` 32 MB nested research clone).
- 5 preserved as REAL WORK: PARK-REARM-FUNDED-PROVIDER (code: proxy.py +160 / test +489 / review
  log +142, on a PUSHED branch with NO PR), BASH-INERT-COVERAGE (staged 394-line inert-coverage G1
  check + test + review log), CLAIM-LIVENESS-BINDING (claim.sh heartbeat/reap-stale + test),
  GRAPHIFY-AFFECTED-WIRE (blast-radius.sh + test + reuse-check wiring + TOOL-INVENTORY), and
  SHELLCHECK-OPTIONAL-CHECKS-ON (gate.sh BLOCKING-SHELLCHECK flip + .shellcheckrc). None of this
  content exists on origin/master.

## Post-sweep drift (verified on retry)

- Detector re-run confirms the 13 cleared worktrees are all still CLEAN.
- 3 of the (b) worktrees still hold their real work on disk: PARK-REARM-FUNDED-PROVIDER (code
  repo, 3 tracked modifications), BASH-INERT-COVERAGE (3 staged paths), CLAIM-LIVENESS-BINDING
  (modified claim.sh + untracked test). All three branches are local-only/behind master except
  PARK-REARM (pushed, no PR).
- New out-of-scope drift: DONE-SH-INTEGRITY-FIX (a known BLOCKED ticket, deps GITHUB-LIMITS-
  HARDENING + VERIFY-MERGED-REPO-AWARE) is dirty again — fleet/done.sh, fleet/gh-cache.sh,
  fleet/tests/done-gate.test.sh — real work owned by its own branch, committed when deps land.
- GRAPHIFY-AFFECTED-WIRE and SHELLCHECK-OPTIONAL-CHECKS-ON worktrees were RECREATED from
  origin/master by the launcher after this lane's first run; their uncommitted working copies are
  no longer on disk and no commit survives (branch reflogs show a single "Created from
  origin/master" entry; `git fsck` finds no dangling commit carrying blast-radius.sh or
  .shellcheckrc). Both tickets have since been re-launched as their own lanes (agent briefs
  economy-4068869-GRAPHIFY-AFFECTED-WIRE, economy-4068773-SHELLCHECK-OPTIONAL-CHECKS-ON), so the
  work   is being re-done there, not lost. This lane should NOT rebuild it.
- Out of scope (dirty worktrees minted after this ticket's snapshot, left for their own lanes):
  INERT-CHECKS-WIRE, PREFLIGHT-OWNS-ARBITRATE, PROOF-SUITES-ENFORCE, WORKFLOW-E2E-AUDIT,
  SHARED-NAMESPACE-CONTENTION, MISSING-CLASS-DETECTORS, WCI-DEC-SRC-CHARON-PROVIDERS-PY,
  DONE-SH-INTEGRITY-FIX.

## Notes / caveats

- NS-CONTENTION SESSION-HANDOFF-satele-shan.md: byte-compare FAILED against master, but the master
  revision is strictly NEWER (20:20:52Z > 19:45:22Z header) and is the landed document (main
  checkout == master blob), so the worktree draft is a superseded revision, not unique content.
  Classified (a)-adjacent and cleared.
- No work was committed to any branch, nothing pushed, no PRs opened — the launcher's rule. The
  preserved (b) cases need the manager / their owning tickets to commit + PR.
