tier: strong
priority: 2
difficulty: 3
work_class: ci-infra
branch: audit/land-sh-postmortem
repo: charon-private
depends_on:
owns: fleet/state/LAND-SH-POSTMORTEM.md
accept: |
  ADVERSARIAL PROCESS REVIEW (blast-radius mindset) — not the fix (LAND-SH-SAFE-SYNC does that), but WHY a
  data-loss bug shipped in the SANCTIONED merge tool and what class of gap allowed it.
  ROOT-CAUSE: land.sh's step-7 sync does a destructive reset/clean over the working tree with (a) NO test
  exercising the DIRTY-tree case, (b) no dirty-state guard, (c) no red-proof that the destructive path was ever
  run against uncommitted/untracked files. Establish exactly which test/gate SHOULD have caught it and why none did.
  TESTING-GAP: our fail-on-revert discipline covers FEATURE code but INFRASTRUCTURE scripts that MUTATE STATE
  (land.sh, done.sh, retire-done.sh, deploy.sh, land-push.sh, leak_worktree_setup, roadmap/report writers) may
  have no test for their DESTRUCTIVE/precious-state paths. Name the gap in the discipline.
  BLAST-RADIUS SWEEP (the class): enumerate every rig/product script that does a DESTRUCTIVE op —
  `reset --hard`, `clean -fd`, `checkout -f`, `worktree remove --force`, `rm -rf`, in-place file/config overwrite,
  branch -D — and for EACH: does it guard precious/uncommitted state + carry a test proving it? Produce a
  matrix (script -> destructive op -> guarded? tested?) and flag every unguarded/untested one as a latent
  land.sh-class bug.
  MECHANIZED GATE (proposal + red-proof): a gate that REQUIRES any state-mutating rig script to carry a
  "preserves uncommitted/precious state" test (or an explicit justification), so this class can't recur. State
  whether it's mechanizable now or guidance.
  ADVERSARIAL: assume there are MORE land.sh-class bugs latent right now; the review's job is to find them, not
  to conclude "land.sh was a one-off."
scope: Process/blast-radius review of the destructive-op-without-guard class exposed by the land.sh data-loss. [[green-is-not-proof]] [[investigate-and-backup-before-data-loss]] [[standing-blast-radius-lens]] [[gates-must-actually-run]]
ds: |
  depends_on: none (parallel to LAND-SH-SAFE-SYNC, which fixes the instance; this reviews the CLASS). Read-only
  audit -> writes one findings doc. Frontier/strong review model. Adversarial by default.
note: filed 2026-07-13 after land.sh's sync wiped session board state. Review the CLASS + testing gap, not just the one bug.
