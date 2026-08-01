repo: charon-private
tier: strong
priority: 1
difficulty: 2
work_class: ci-infra
branch: feat/gate-integrity-c
owns: fleet/preflight.sh, fleet/tests/gate-integrity-c.test.sh
serial_justified: One preflight leg flipped from advisory to enforcing, plus the test that proves it now blocks.
substrate: N/A
substrate-novel: |
  Nothing to adopt — this flips a MODE on the rig's own already-built detector
  (fleet/checks/gate-integrity.sh, landed by GATE-INTEGRITY-A/B). No tool, no dependency, no new
  code path: the enforcing mode (`check`) already exists and is already used by CI; only the
  preflight leg still calls the advisory mode (`scan`) and discards the verdict.
depends_on: MARKER-PROOF-MECHANIZE, PREFLIGHT-GATE-REGISTRY, PREFLIGHT-GATE-RUN-HELPER, RECONCILE-WIRING, REPO-MAP-CONVERGE, SYNC-SCHEDULE, WCI-DEC-FLEET-PREFLIGHT-SH
note: |
  NOT A REGRESSION — a SCHEDULED PROMOTION COMING DUE. This distinction matters and should not be
  written up as a bug.

  GATE-INTEGRITY-A and -B are done and `fleet/checks/gate-integrity.sh` IS registered in
  rig-ci-scope's suites. But fleet/preflight.sh:807-810 runs it as:
      [ -x "$script" ] || { ...; return 0; }
      bash "$script" scan ... || true
  i.e. advisory mode, verdict discarded.

  preflight.sh:802-806 documents this AS DELIBERATE: "a detector that hard-blocks startup on day
  one is a detector that gets commented out... That is the mode CI should adopt once this has
  ridden a few PRs." It has now ridden many.

  MEASURED 2026-08-01: the live run reports 37 findings — 1 NEW, 36 baseline. The ratchet has real
  signal and a real baseline, which is exactly the precondition the comment set for promotion.
accept: |
  - The preflight leg calls `check` (the ratchet/enforcing mode), not `scan`.
  - `|| true` removed so a ratchet breach actually fails preflight.
  - The `[ -x ] || return 0` fail-OPEN guard is replaced by a fail-CLOSED refusal: a MISSING
    detector must be loud, never a silent pass. (This is one of the 16 fail-open guards in
    preflight.sh; the rest are PREFLIGHT-GATE-RUN-HELPER's scope, not this ticket's.)
  - The existing 36 baseline findings do NOT block; only a NEW finding does. Confirm the baseline
    mechanism works before flipping, or this wedges every preflight.
  - fail-on-revert test: a seeded new finding makes preflight RED; reverting the flip makes it
    pass. Red-proof externally, report both counts.

## Dependencies & Sequence

- **depends_on: (none)** — detector and baseline both already exist.
- **Sequence: after confirming the baseline holds.** Flipping to enforcing with a broken baseline
  wedges every preflight run, so verify the 36 baseline findings are genuinely suppressed first.
- **Blocks / unblocks:** turns an existing detector from advisory into a real gate; no other ticket
  waits on it.
- **owns-collision:** `fleet/preflight.sh` is owned by several tickets (MARKER-PROOF-MECHANIZE,
  PLANE-CANARY-WIRE, PREFLIGHT-GATE-REGISTRY, PREFLIGHT-GATE-RUN-HELPER, RECONCILE-WIRING,
  REPO-MAP-CONVERGE, SYNC-SCHEDULE). MUST be dep-ordered before claiming — resolve against the
  live board, do not co-write.
