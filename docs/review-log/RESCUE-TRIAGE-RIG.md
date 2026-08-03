# RESCUE-TRIAGE-RIG — Review Log

## Ticket
RESCUE-TRIAGE-RIG: read-then-dispose pass over the nine rig branches that
RESCUE-PUSH-TOOL pushed on 2026-08-01 with no PR of any kind against them. The push made
them safe from disk loss; it did not make them reviewed or visible. For each of the nine,
prove (a) whether its change is already on master by another route and (b) whether it still
contributes — then OPEN a PR, CLOSE-DEAD with evidence, or HELD-WITH-REASON.

## What was done
- Triaged all nine branches against `origin/master` (67c7eaa) using content-level evidence:
  byte-identical file diffs, commit shas on master, patch-id checks, and the live board.
- **Opened PR #392** for `feat/pr-queue-rest-etag` — the only branch whose files
  (`fleet/pr-queue.sh`, `fleet/tests/pr-queue.test.sh`) are absent from master while its
  board ticket is LIVE on master. PR body states what it delivers, what is already on
  master, and what is left (the `review-pool.sh` cutover, owned by REVIEWER-TAB-POOL).
- **Closed 7 dead branches** with evidence (all content on master, byte-identical or
  evolved-superset): `chore/retire-wire-graphify`, `feat/bench-oob-grading`,
  `feat/coverage-meta-gate`, `feat/substrate-first-gate`, `feat/substrate-first-gate-v2`,
  `fix/budget-source-reconcile`, `salvage/session-notes-20260719`.
- **Left `fix/broker-bare-tier-legs` HELD**: its blocker GRADE-MODEL-PROVIDER-PAIR is still
  a live board ticket on master, so the hold is not spent; master has additionally since
  moved tier routing toward provider-qualified ids, contradicting the branch's bare-id
  premise. Recorded, not disposed.

## The two-shape decision
`feat/substrate-first-gate` (v1) and `feat/substrate-first-gate-v2` are two shapes of one
change. Neither was opened — the gate live on master supersedes both: master's
`substrate-first-gate.sh` is byte-identical to v2's, and master's `substrate_first_gate.py`
is an evolved superset of v2's. v1 was the loser of the shape race (hand-rolled 285-line
parser with nine adversarial evasions, replaced by the real YAML parser in v2); v2 won the
shape but its content had already landed on master before this triage ran.

## Why not nine PRs
Nine PRs would have been the failing outcome — it converts the rescue into review-queue
slots for content master already holds. Closing dead work with evidence is the equally
valid outcome the done-contract names. Exactly one PR was opened; seven branches were
closed with proof of landing; one remains held with the reason on record.

## Verdicts
- PR-OPENED #392: `feat/pr-queue-rest-etag`
- CLOSED-DEAD: 7 branches (content on master)
- HELD-WITH-REASON: `fix/broker-bare-tier-legs`

Full evidence per branch: `fleet/state/RESCUE-TRIAGE-RIG.md`.
