repo: charon-private
tier: strong
priority: 1
difficulty: 3
work_class: rig-meta
branch: chore/diverged-branch-triage
depends_on:
owns: fleet/state/DIVERGED-BRANCH-TRIAGE.md, docs/review-log/DIVERGED-BRANCH-TRIAGE.md
serial_justified: |
  One classification rule plus one triage pass over the same seven branches. Split, the reporting
  half and the triage half disagree about what "at risk" means, which is the defect.
substrate: N/A
substrate-novel: |
  fleet/checks/stranded-work.sh and fleet/rescue-push.sh both already exist and are adopted; the
  rescue/* parking mechanism already works. The novel slice is the DISTINCTION between "unprotected"
  and "protected but unresolved" — a semantic only this fleet has.
accept: |
  MEASURED AT SESSION CLOSE 2026-08-02: 7 branches report at-risk on EVERY cycle and always will.
  All 7 are DIVERGED (local and remote each hold commits the other lacks), so they can never
  fast-forward. Their content IS SAFE — rescue-push parks the local side on a parallel `rescue/*`
  ref and refuses to force, which is correct. What remains is a HUMAN MERGE DECISION per branch:
    eval/workflow-e2e-audit 23 · **feat/ft-limits-groq-reconcile 706** · feat/reconcile-gate-wired 35
    · feat/semgrep-ci-required-check 3 · fix/sandbox-containment 1 · docs/work-converge-review 1
    · feat/ft-catalog-seed 4
  TWO HALVES, DIFFERENT PRIORITIES:
  (A) REPORTING — do this FIRST, it is small and it protects the alarm.
      The cadence detector reports `n=8` every 20 minutes and SEVEN are permanent: the work-loss
      alarm is ~87% noise on day one. A genuinely NEW stranded branch would land in that list and
      be invisible. Teach stranded-work.sh to report a DISTINCT shape — `diverged-parked` — for a
      branch whose local side is already on a `rescue/*` ref, counted and surfaced SEPARATELY from
      unprotected work. **Do NOT simply suppress them**: silence is how the class returns. The
      point is to keep "unprotected" at zero and visible.
  (B) TRIAGE — the actual merge decisions, per branch, with evidence:
      is the local side superseded (drop the rescue ref), still wanted (merge by hand), or dead
      (delete both)? `feat/ft-limits-groq-reconcile` at 706 commits needs a real look — that count
      suggests a broken upstream ref, not 706 pieces of unlanded work. Verify before assuming.
      NEVER force-push to resolve a divergence: the remote side holds commits the local side lacks.
  Fail-on-revert on (A): a diverged-parked branch must NOT be counted as unprotected, and an
  unprotected branch must still RED.

## Dependencies & Sequence

Half (A) belongs in PHASE 1 on **L4 cost-to-value + L6 surfacing** — it is small and it stops the
brand-new work-loss alarm from crying wolf, which protects every future use of it.
Half (B) belongs in PHASE 3 with `PR-QUEUE-DRIVE` on **L5 compounding** — same shape, a backlog of
finished-but-undelivered work needing per-item judgement. Not urgent: **L7 does not apply, the
content is safe.**
