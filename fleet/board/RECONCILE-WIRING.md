repo: charon-private
tier: strong
difficulty: 4
priority: 1
work_class: ci-infra
branch: feat/reconcile-wiring
owns: fleet/checks/reconcile-timer.sh, fleet/tests/reconcile-wiring.test.sh, fleet/preflight.sh, fleet/land.sh, fleet/foreman-cadence.sh, fleet/state/GATE-GAP-LEDGER.tsv
serial_justified: One cohesive enforcement contract — the preflight scan-chain insertion, the
  land.sh pre-merge pre-condition, the timer (reconcile-timer.sh) and its foreman-cadence.sh
  dispatch, and the GATE-GAP-LEDGER open-seam row are ONE invariant ("the four reconcilers fire
  from every real firing layer, and the one seam they cannot yet close is declared, not
  faked-green"). Splitting ships a partially-wired gate — the exact built-but-inert class this
  work exists to close.
depends_on: RECONCILE-BOARD-PR-DONE, RECONCILE-OWNS-TRACKED, RECONCILE-GATE-WIRED, RECONCILE-REVIEW-GATE, MARKER-PROOF-MECHANIZE
real-dep: RECONCILE-BOARD-PR-DONE — build dep: this ticket wires fleet/checks/reconcile-board-pr-done.sh
  into the firing layers; the check file must exist before it can be inserted. dep-kind: build.
real-dep: RECONCILE-OWNS-TRACKED — build dep: wires fleet/checks/reconcile-owns-tracked.sh into
  the firing layers; the check must exist first. dep-kind: build.
real-dep: RECONCILE-GATE-WIRED — build dep: wires fleet/checks/reconcile-gate-wired.sh into the
  firing layers; the check must exist first. dep-kind: build.
real-dep: RECONCILE-REVIEW-GATE — build dep: wires fleet/checks/reconcile-review-gate.sh into the
  firing layers (land.sh BLOCK point); the check must exist first. dep-kind: build.
real-dep: MARKER-PROOF-MECHANIZE — shared single-owner of fleet/preflight.sh scan-chain region;
  this ticket inserts into the SAME chain. Rebase behind the existing preflight edit chain
  (MARKER-PROOF-MECHANIZE -> REPO-MAP-CONVERGE -> SYNC-SCHEDULE — transitively ordered), do not
  run concurrently. dep-kind: build/rebase.
source: fleet/state/UNIFIED-RECONCILIATION-GATE-DESIGN.md §3 + §3.3 (design PR #178, RANK-0 LEAD)
work_class_note: ci-infra — the enforcement wiring (required-check + timer) that turns four
  standalone reconcilers into an actually-firing gate. Blocks operator adoption of v1.
note: |
  §3 — enforcement, three rig-side points and no fourth. (1) fleet/preflight.sh:841 scan-chain:
  insert `bash fleet/checks/reconcile-board-pr-done.sh` + reconcile-owns-tracked.sh +
  reconcile-gate-wired.sh + reconcile-review-gate.sh immediately AFTER reconcile-merged.sh and
  BEFORE board_gate (order matters: reconcile-merged writes done-markers, the reconcilers read
  them, then the existing gates see the post-reconciliation board). (2) fleet/land.sh pre-merge
  pre-condition: re-run all four against the head SHA's tree + live state; ANY RED refuses
  mark-done / advance-to-merge (both autonomous and operator-merged land paths must call this).
  (3) fleet/checks/reconcile-timer.sh: runs the same four on a fixed cadence, wired into
  fleet/foreman-cadence.sh `cadence` dispatch (the existing interval-gated timer,
  foreman-cadence.sh:87-102 — report-only, never --fix) so overnight/between-run drift is caught
  at the next tick. The cadence interval is a data value (KS29 — interval_seconds is data).

  REUSE-FIRST: foreman-cadence.sh already IS the interval-gated timer (session-start / post-land /
  handoff / cadence triggers) — compose its `cadence` subcommand, do NOT build a new cron shim.
  land.sh already has the AUTONOMOUS-lever + marker pre-conditions — add the reconcile block
  alongside, do not restructure. preflight.sh:841 is the existing single scan dispatch line.
revisions_baked_in: |
  REVISION-1 (fail CLOSED, #182): the wiring propagates each check's non-zero exit as a hard RED —
  a reconciler that errors or returns UNVERIFIED is treated as RED at the land.sh pre-condition,
  never skipped. land.sh refuses to advance on ANY non-GREEN reconciler.
  REVISION-2 (timer-wireable today, #182) — THIS ticket IS the confirmation: the timer/cadence
  firing layer already exists (fleet/foreman-cadence.sh `cadence`, interval gate at :87-102) and
  preflight.sh:841 + land.sh are live firing layers. All three are wireable TODAY; nothing here is
  an inert gate. The ONE seam that CANNOT be closed today is declared, not faked-green (see below).
  DECLARED OPEN SEAM (§3.3, fail-closed honesty): the land.sh `git -C <other-worktree> merge` /
  direct-push-to-master bypass is NOT closed on the private rig until the Gitea-primary migration
  (server-side pre-receive hook) lands. This ticket appends a GATE-GAP-LEDGER.tsv row
  `status=open; closure=depends-on-gitea-primary` and a README note — it does NOT pretend land.sh
  is a closed gate. Interim mitigations (non-blocking detectors): the timer leg catches direct-merge
  drift at the next tick; a post-receive hook on the bare repo can re-run + notify. Per
  [[detection-ticketed-never-built]] the seam is flagged so no future reviewer ships a false-green
  claiming reconciliation is fully enforced on the rig.
accept: |
  - fleet/preflight.sh:841 scan chain invokes all four reconcile-*.sh after reconcile-merged.sh,
    before board_gate; each RED propagates to the scan exit code.
  - fleet/land.sh pre-merge block re-runs the four against head SHA; ANY RED refuses mark-done /
    merge on BOTH land paths (autonomous + operator-merged).
  - fleet/checks/reconcile-timer.sh runs the four; wired into fleet/foreman-cadence.sh `cadence`
    (report-only, interval-gated). KS20 dogfood: reconcile-timer.sh + the new reconcile-*.sh +
    their tests are themselves owns:-tracked (RECONCILE-OWNS-TRACKED's own check must pass on this
    build's files) and the timer is itself in the firing layer (RECONCILE-GATE-WIRED must not flag
    the reconcilers as inert).
  - fleet/state/GATE-GAP-LEDGER.tsv gains the land.sh `git -C` open-seam row
    (status=open; closure=depends-on-gitea-primary); a README/design note records the explicit
    non-fix.
  - fail-on-revert test (fleet/tests/reconcile-wiring.test.sh): (a) a fixture reconciler forced RED
    -> land.sh pre-condition REFUSES (exit non-zero); make it GREEN -> land proceeds. (b) remove a
    reconciler from the preflight chain -> the wiring test detects the missing invocation (RED).
    (c) the timer subcommand invokes all four (asserted by grep/dry-run).
  - Cite the stass-allie WLS-7 validation (implement-as-pattern is the sanctioned hand-roll).
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
scope: |
  Rig-only. Turns four standalone reconcilers into an enforced gate across preflight + land + timer,
  and declares the one un-closable seam honestly. Blast radius: every preflight scan, every land,
  every cadence tick. Product-side native required-check (§3.2, .github/workflows/reconcile.yml on
  /home/stack/code/charon) is a SEPARATE product-repo ticket, not in this rig ticket's owns:.
ds: |
  ## Dependencies & sequence
  Wave-2 — lands AFTER all four reconciler checks exist (build deps) and rebases behind the
  existing fleet/preflight.sh edit chain (MARKER-PROOF-MECHANIZE -> REPO-MAP-CONVERGE ->
  SYNC-SCHEDULE; depend on the chain head, transitively ordered). Concurrency: NOT parallel with
  any preflight.sh owner. Reuse foreman-cadence.sh `cadence` + land.sh existing pre-conditions;
  do not build a new timer.
