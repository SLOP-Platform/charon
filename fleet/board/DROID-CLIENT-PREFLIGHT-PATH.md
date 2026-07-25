repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: rig-meta
branch: fix/DROID-CLIENT-PREFLIGHT-PATH
owns: fleet/charon-run.sh, fleet/fleet-droid.sh, fleet/env-registry.sh, fleet/droid-bridge.sh,
  fleet/tests/charon-run-client-preflight.test.sh, fleet/tests/droid-bridge.test.sh
priority_justification: |
  P:0 — operator-escalated and CG-active: every droid launched from a NON-INTERACTIVE shell dies
  rc=127 (`opencode` off PATH) and the launcher misreports it as model exhaustion, while
  is_infra_fault() books those infra crashes as model BLOCKs — 42 of 46 lifetime BLOCKs are infra,
  so the live scorecard routing ranks are being corrupted right now. The fix is BUILT; only landing
  is left, so the P:0 band buys an immediate stop-the-bleed rather than a new build.
work_class_note: |
  scorecard-integrity + launcher-governance. A misattributed infra crash writes a BLOCK against a
  model that never failed, which is exactly the ranking data the real-outcomes ledger routes on
  [[scorecard-live-lane-is-the-ledger]] [[monitored-preflight-failure-attribution]].
note: |
  DARK WORK, TICKETED RETROACTIVELY 2026-07-24. The branch fix/DROID-CLIENT-PREFLIGHT-PATH was built
  and pushed (HEAD 8f0a4e5, 2 commits) with NO board ticket; `work-lease.sh guard-branch`
  (landed PR #267, work-lease.sh:408 on origin/master) refuses exactly this. This ticket closes the
  mapping so the branch is committable and landable without WORK_LEASE_BYPASS.

  WHAT IS ON THE BRANCH (all three faults are STILL LIVE on master — none of this is landed):
  1. PATH DERIVATION — a droid launched from a non-interactive shell cannot see `opencode`; the run
     dies rc=127 and is reported as model exhaustion. Fix derives + exports PATH in charon-run.sh.
  2. GATEWAY TOKEN FROM A STALE ENV VAR — src availability.py:197 PREFERS the pre-existing env var,
     so a set-if-unset export is a NO-OP and the preflight authenticates with a dead token. Fix
     overwrites UNCONDITIONALLY from `env-registry.sh:bearer_token()`, and the preflight JSON-parses
     the gateway response so it catches a 302 (redirect to a login page) and not only a 401.
  3. INFRA FAULT BOOKED AS A MODEL BLOCK — `is_infra_fault()` classified crashes (rc >= 128, signal
     deaths) as model BLOCKs. Fix suppresses the scorecard BLOCK for infra faults.
  Plus the OPERATOR-REQUESTED idle push droid (`--push` / `--push-only`, fleet-droid.sh:558-559)
  and the F4 fix: a missing `work_class` no longer bypasses detention / capped-exclusion / cost-cap.
accept: |
  - fleet/tests/charon-run-client-preflight.test.sh green (new, 475 lines, on the branch).
  - fleet/tests/droid-bridge.test.sh green (new, 338 lines). Last run 41 passed / 1 failed, where
    the single failure was a TEST bug (G5 asserted the wrong ledger path); that fix is on the branch
    and MUST be re-run green before landing — do not land on an unverified suite.
  - fleet/tests/capture-wiring.test.sh and fleet/tests/assign-dispatch.test.sh still green after the
    merge with master (both were also edited on master; see ds:).
  - LIVE-ON-MASTER verification, not merely "merged": after the land,
    `grep -c 'push-only' fleet/fleet-droid.sh` > 0, `grep -c 'rc -ge 128' fleet/charon-run.sh` > 0,
    and the PATH export + JSON-parsing gateway preflight are present on master.
  - FAIL-ON-REVERT: revert the unconditional token overwrite -> the preflight test that asserts a
    STALE env token is replaced (not preferred) goes RED; revert the is_infra_fault change -> the
    "infra crash writes NO scorecard BLOCK" assertion goes RED.
scope: |
  Rig-only launcher + run-wrapper hardening. No product (/home/stack/code/charon) files. Touches the
  shared money-path launcher fleet/fleet-droid.sh, so it is an ANCHOR land: other launcher tickets
  rebase onto it rather than co-writing it [[anchor-lines-serialize-parallel-work]].
ds: |
  ## Dependencies & sequence
  No BUILD prerequisite — the work is complete and pushed. What this ticket carries is a MERGE-ORDER
  obligation on two live owns-collisions, declared here rather than left un-ordered:

  - `fleet/charon-run.sh` is also owned by CAPTURE-WIRING-TIMEOUT-FIX (rc=124 stray capture row).
    That ticket is UNSTARTED (its worktree sits at the base commit). This branch is BUILT, TESTED and
    pushed, so this lands FIRST as the anchor and CAPTURE-WIRING-TIMEOUT-FIX sequences onto the
    landed file. Direction recorded on that ticket as `depends_on: DROID-CLIENT-PREFLIGHT-PATH`
    — a merge-order edge, NOT a build prerequisite [[disjoint-owns-not-no-dependency]]. The two
    changes are disjoint within the file (client preflight/PATH/exit-classification here; the
    capture-enqueue path there), so this is sequencing, not conflict.
  - `fleet/droid-bridge.sh` + `fleet/tests/droid-bridge.test.sh` are owned by DROID-BRIDGE-REGISTER,
    whose push-mode fold-in IS the second commit on this branch (`feat(DROID-BRIDGE-REGISTER): push
    mode`). Same anchor rule and same recorded edge; that ticket's remaining scope (register /
    heartbeat / unregister-trap lifecycle) rebases onto the landed bridge file.

  Merged onto origin/master before landing. Resolution rule used: fleet/board/* takes MASTER; the
  branch CODE (fleet/charon-run.sh, fleet/fleet-droid.sh, its tests) takes the BRANCH.
