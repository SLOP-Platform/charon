# DIVERGED-BRANCH-TRIAGE — review-log fragment

**Ticket:** DIVERGED-BRANCH-TRIAGE
**Branch:** chore/diverged-branch-triage
**Date:** 2026-08-02
**Author:** droid

## What this ticket produced

A measurement + per-branch triage of the 7 permanently at-risk (diverged) branches, plus the
classification spec for the `diverged-parked` reporting shape. Documentation only (owns: the two
state/log files) — the stranded-work.sh code change is specified in `fleet/state/DIVERGED-BRANCH-TRIAGE.md` §5 for the ticket that owns that file.

## Measured findings (all verified by running git/gh on the live rig)

1. **706 is a broken upstream ref, CONFIRMED.** `feat/ft-limits-groq-reconcile` local tip is an
   ancestor of master (0 commits absent from master); every one of the "706" is already on master.
   The real work is the remote side + OPEN PR #116 (2 commits).
2. All 7 branches are diverged (ahead AND behind) → never fast-forward, never force.
3. All 7 local tips are parked on `rescue/*` → content safe.
4. 4 branches are SUPERSEDED (content provably landed on master): `feat/reconcile-gate-wired`
   (wired version is a master commit), `feat/semgrep-ci-required-check` (semgrep.sh byte-identical
   to master), `fix/sandbox-containment` (patch-id == merged #393), `docs/work-converge-review`
   (patch-id LANDED via #108).
5. 3 branches are STILL WANTED: `eval/workflow-e2e-audit` (audit files not on master),
   `feat/ft-catalog-seed` (4 real commits, OPEN PR #135), `feat/ft-limits-groq-reconcile` (remote
   side, PR #116).

## Scope self-check

Changed files (all within `owns:`):
- `fleet/state/DIVERGED-BRANCH-TRIAGE.md` — owned
- `docs/review-log/DIVERGED-BRANCH-TRIAGE.md` — this fragment

No out-of-scope files touched. The stranded-work.sh classification change was deliberately NOT
made here — it belongs to the ticket that owns that file; the rule + fail-on-revert assertions are
specified in the state file §5.
