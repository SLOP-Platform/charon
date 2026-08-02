repo: charon-private
tier: strong
priority: 1
difficulty: 4
work_class: rig-meta
branch: chore/closed-pr-unlanded-triage
depends_on:
owns: fleet/state/CLOSED-PR-UNLANDED-TRIAGE.md, docs/review-log/CLOSED-PR-UNLANDED-TRIAGE.md
serial_justified: |
  One sweep over one generated list, where the judgement for each row depends on what the
  earlier rows established about which supersession routes were used. Two tabs would re-derive
  the same supersession map and could reach opposite verdicts on the same branch.
substrate: N/A
substrate-novel: |
  The detector already exists and is adopted as-is — fleet/checks/stranded-work.sh emits the
  closed-pr-unlanded shape and produced this exact list. Nothing is built here. The novel slice
  is the per-branch VERDICT, which no tool can supply because it needs the intent behind each
  closure.
accept: |
  fleet/checks/stranded-work.sh reports 58 x closed-pr-unlanded: a PR was CLOSED while its
  branch still carries commits that are NOT on master. Each is one of three things and they are
  not distinguishable without looking:
    (a) DELIBERATE — bounced or superseded, content landed by another route. Correct, no action.
    (b) SQUASH ARTEFACT — content IS on master, the branch just is not an ancestor. Correct.
    (c) SILENTLY DISCARDED WORK — the failure this ticket exists to find.
  For each of the 58: classify with EVIDENCE (git cherry / git patch-id against master, not a
  filename guess), and for every (c) either reopen with a PR or record why it stays dropped.
  Report the counts per class. A branch that cannot be classified is a (c) until proven otherwise.
  Run `SW_LIMIT=0 bash fleet/checks/stranded-work.sh` for the full list — the default output
  suppresses most rows.

## Dependencies & Sequence

No inbound deps. Independent of the three landing lanes (disjoint owns) so it runs concurrently.
Sequence inside: classify ALL 58 before acting on any, because the supersession map built from
the easy rows is what makes the ambiguous ones decidable.
