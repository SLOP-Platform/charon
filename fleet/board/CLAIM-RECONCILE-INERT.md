repo: charon-private
tier: strong
difficulty: 2
priority: 1
work_class: rig-meta
branch: fix/claim-reconcile-inert
owns: fleet/reconcile-stale-claims.sh, fleet/tests/reconcile-stale-claims.test.sh, fleet/preflight.sh
depends_on:
source: STALE-CLAIM-RECONCILE shipped BUT is never invoked — 15 stale claims, zero live workers, zero reconciler runs. Phase 1 triage: recon-191.
note: |
  ## Root cause: inert (never invoked)

  `fleet/reconcile-stale-claims.sh` was built, tested, merged to master on
  `feat/stale-claim-reconcile`, and marked DONE — but no script, hook, gate, or cadence
  mechanism ever calls it. Zero references outside its own file and its test.
  This is the class of bug `check_inert_code.py` catches.

  Secondary: the session-bridge claim format change (`ticket:` / `session:` / `worktree:` /
  `heartbeat:` kv format vs the old `<droid-id> <timestamp>` one-liner) means the reconciler's
  `awk '{print $1}'` parser would skip every claim with "format drift" even if called.

  ## Phase 1 triage (fleet/handoff-notes/CLAIM-RECONCILE-TRIAGE.md)

  - Root cause: (a) built but never invoked
  - 15-claim classification: 14 DONE-RELEASE, 1 LIVE-WORK-PRESERVE (GW-CUTOVER-LIVE-WIRE)
  - Diagnostic: LITELLM-COST-FIELD-FIX has DONE MARKER + CLAIM — session-bridge re-touches claims
    independently of done.sh
  - DOGFOOD-GATE (d6267c3) + INERT-STARTUP-CHECK (6ab6035): landed today, NO done-markers — the
    done-marker write path is ALSO missing

  ## Class fix

  1. **Format support**: the reconciler now reads BOTH claim formats. Bridge format
     (`ticket:` + `heartbeat:`) uses heartbeat-based liveness (900s threshold); old format
     uses PID-based liveness. Adopts the same dual-format strategy as `work-lease.sh:claim_epoch()`.

  2. **Worktree guards**: a claim whose worktree has uncommitted changes (`git status --porcelain`)
     or unpushed commits (`git rev-list --count HEAD --not --remotes`) is NEVER released —
     same invariants as `branch-reaper.sh`. A non-existent worktree path is fail-closed (HOLD).
     Done-marker claims bypass worktree checks (the marker is authoritative proof).

  3. **Done-marker fast path**: a claim that already has `state/done/<id>` is released DIRECTLY
     (remove the claim file) rather than re-invoking `done.sh` — the marker IS the proof.

  4. **Dry-run default**: `--apply` opt-in, matching `branch-reaper.sh`.

  5. **Wired to preflight**: `preflight.sh:958` (scan chain) now calls
     `bash "$HERE/reconcile-stale-claims.sh"` (dry-run) after `reconcile-merged.sh` and before
     `retire-done.sh`. Proven with live transcript: all 15 claims classified correctly.

  ## Test: red/green revert transcript

  Each guard proved RED on revert:
  - (a) Done-marker path disabled → (a1-a6)+(g1-g2) go RED
  - (b) Dirty-guard disabled → (b1-b4) go RED (claim released with uncommitted changes!)
  - (c) Unpushed-guard disabled → (c1-c3) go RED (claim released with unpushed commits!)
  - (d) Broken-worktree guard disabled → (d1-d3) go RED (released unreadable claim!)
  - (e) Merge-proof path disabled → (e1-e2) go RED
  - (f) Always-apply (no dry-run) → (f1-f4) go RED

  See: fleet/tests/reconcile-stale-claims.test.sh

accept: |
  - Reconciler detects all 15 live stale claims (DRY-RUN) and classifies: 1 done-marker retirement,
    14 held-with-proof (merge-proven or no-done-marker, no live worktree).
  - Under --apply: done-marker claim released; dirty/unpushed/broken worktree claims held.
  - fail-on-revert: each guard reverts independently to RED (see red/green transcript in commit).
  - Preflight scan chain invokes the reconciler (dry-run); no mutation without --apply.
  - Work-lease format claims (session-bridge kv) parsed and liveness-checked via heartbeat field.
scope: |
  INERT-CLAIM-RECONCILE: root-cause the inert reconciler, add session-bridge claim format support,
  add worktree guards (dirty/unpushed/broken), wire to preflight scan chain. Fix the CLASS, not
  just the instances — the reconciler runs automatically on every preflight scan from now on.
ds: |
  ## Dependencies & sequence
  Depends on: nothing (read-only start, no prerequisites).
  Blocks: trustworthy fleet/status.sh output, and any safe max-parallel fan-out — the manager
  cannot tell real contention from residue until this is fixed.
  Related: WORK-LEASE-WORKTREE-RESOLVE (54h stale claim) touches the same claim store. This
  fix does not co-write its files.
