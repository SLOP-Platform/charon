repo: charon-private
tier: strong
priority: 1
difficulty: 5
work_class: rig-meta
branch: chore/pushed-no-pr-triage
depends_on:
owns: fleet/state/PUSHED-NO-PR-TRIAGE.md, docs/review-log/PUSHED-NO-PR-TRIAGE.md
serial_justified: |
  189 rows sharing one supersession map. Built once, it decides most rows cheaply; built twice
  in parallel it is derived inconsistently and the same branch gets opposite verdicts.
substrate: N/A
substrate-novel: |
  Adopted as-is: stranded-work.sh for the list, `git cherry` / `git patch-id` for containment,
  `gh pr list --state all` for history. Nothing built. The novel slice is batching policy — how
  to drain 189 without opening 189 PRs nobody reviews.
accept: |
  BIGGEST pileup shape: 189 branches on the remote with NO PR — safe from disk loss and
  invisible to every reviewer. Includes the rescued set (23 of the 47 pushed today) plus a long
  tail predating this session.
  Done contract:
  1. Classify in BATCHES of ~20, by evidence not filename: content already on master (squash
     artefact) / superseded / genuinely unlanded work.
  2. Only genuinely-unlanded work gets a PR. **Do NOT open 189 PRs** — that converts an
     invisible backlog into an unreviewable one, which is worse. Batch by owning ticket where
     several branches serve one ticket (e.g. the FIVE fix/provider-key-exfil variants are ONE
     fix; the two feat/substrate-first-gate shapes are one thing).
  3. Dead branches get DELETED with the evidence recorded — deleting dead work is success.
  4. Report per batch: opened / closed / deleted counts, and the running remainder.
  Note `backup/*` and `rescue/*` are DELIBERATE parking refs and are out of scope; the rescue/*
  refs specifically hold the local side of diverged branches and must not be deleted until their
  divergence is resolved by hand.

## Dependencies & Sequence

P1, no inbound deps. Runs AFTER DIRTY-WORKTREE-SWEEP in priority but concurrently in practice
(disjoint owns). Sequence inside: build the supersession map from the whole 189 FIRST, then act
in batches — acting row-by-row without the map is what produces contradictory verdicts.
