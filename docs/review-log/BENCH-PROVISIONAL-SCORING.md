# BENCH-PROVISIONAL-SCORING — Review Log (per-ticket fragment)

## Ticket
BENCH-PROVISIONAL-SCORING (#20) — design of record
(`fleet/state/BENCH-PROVISIONAL-SCORING-DESIGN.md`). Money/trust-adjacent:
the stage mechanism gates every score that steers budget + routing; a
wrong promotion rule makes untrusted scores steer real spend. Operator-
led deep-dive per operator 2026-07-16 ("bench-provisional-scoring was
supposed to be something I would have next session do a deep dive").

## What the design doc does
- Captures the stage mechanism (provisional / active) in ONE place —
  the on-disk code is scattered across `model-scorecard.sh`,
  `capability/grades.py`, `benchmark/lib/{tier_chart,close_season}.py`,
  `benchmark/{bench.sh,promote.py,units.tsv}`, and
  `benchmark/item-bank/pipeline.py`. The design doc grounds every
  claim with a `file:line` citation.
- Decides the operator's open questions (Q1–Q9) and surfaces them with
  recommendations. The one genuinely open one is **Q1** — tighten
  `bench.sh::unit_stage`'s units.tsv-miss default from `active` to
  `provisional` (one-line change; zero impact on the S0–S6 grandfathered
  rows; fails closed on typos).
- Specifies the composition with #26: the OOB daemon does NOT introduce
  a new stage. It is the trusted OOB grader whose verdict the live
  capture path writes as `source=live / stage=active` via
  `pipeline._enqueue_capture`. `promote.py --apply` and
  `pipeline._enqueue_capture` are the only two writers of `stage`,
  and they stay distinct. #26 is unblocked the moment this design
  lands and the operator signs off.

## State of the build today
- Per `fleet/ADR-BENCH-OOB-GRADING.md` §0, the build landed earlier as
  `9c5714a` + `facfc23` ("#20 provisional-vs-active scoring gate") +
  sibling A2 (#16) + #16 BENCH-AGGREGATE-N. The on-disk code matches
  the pivot plan §2 verbatim. The live ledger
  (`fleet/model-scorecard.tsv`) holds 43 rows today, all `source=live /
  stage=active` — production ticket close-outs via `done.sh`; no
  `provisional` row in the live ledger because the S0–S6 sections are
  grandfathered `active` and no replayed-red / harder-section unit has
  been registered yet.
- The v1 review (`fleet/scratch/bench-provisional-review.md`) found
  fail-closed composition PASS, legacy default-active PASS (with the
  one documented caveat that is the v1 Q1), promotion-gate PASS, test
  adequacy PASS, and ONE smoke-only consistency gap (close_season.py
  missing the stage filter) that is now FIXED on master. No blocker.

## Why a fresh design doc was needed anyway
The pivot plan §2 is an *intent* document, not a design of record: it
describes the mechanism but leaves the operator's nine open decisions
unresolved, scattered across `scratch/pivot-implementation-plan.md` §8,
`fleet/ADR-BENCH-OOB-GRADING.md` §0, the v1 review's
`bench-provisional-review.md`, and various inline comments. The
operator's deep-dive was to write them down in one place with the
operator's actual decisions attached, and to give #26 a single design
artifact to rebase onto. That is what `BENCH-PROVISIONAL-SCORING-
DESIGN.md` is.

## Decisions I would push back on (operator review)
- **Q1 — tighten to `provisional` on units.tsv-miss.** This design
  recommends YES. The current `active` default was acceptable while
  S0–S6 was the entire universe and everything was grandfathered, but
  #25 (replayed reds) and #17 (harder sections) will both register
  new units and a typo in `units.tsv` would silently promote an
  unproven unit. The one-line change is documented in
  `BENCH-PROVISIONAL-SCORING-DESIGN.md` §8.1. **If** the operator
  prefers to keep the current default, that's defensible too — but
  the review must explicitly accept the typo risk.
- **Q7 — `retired` state.** The pivot plan shows a third state; this
  design defers it to #17. If the operator wants it in #20's scope,
  the state machine is ready (`units.tsv` already accepts
  `stage=retired` as a string in principle; the readers default `active`
  on an unknown value, which would be wrong for `retired` — a third
  `VALID_STAGE` value with a reader-side default of `provisional` is
  the right shape). My recommendation: defer.

## What I did NOT do
- No code change. The ticket's `owns:` is `fleet/state/BENCH-PROVISIONAL-
  SCORING-DESIGN.md` only; the rewire described in the ticket's accept
  is already on master (see "State of the build today" above), and the
  ones not on master (Q1's one-line, Q7's retired state, §8.2–8.5
  follow-ons) are out of scope for this design-only ticket.
- No edits to any other ticket's `owns:`. The review fragment
  (this file) is the only other file I touched; it is the per-ticket
  fragment the launcher prompt explicitly carves out as a permitted
  exception.

## Unblocks
Once the operator signs off on this design (and decides Q1):
- **BENCH-OOB-GRADING (#26)** is unblocked. Its ADR
  (`fleet/ADR-BENCH-OOB-GRADING.md`) is already drafted and rebase-
  ready; the stage plumbing it was told not to co-write is on master
  per the §0 finding. #26 simply rebases onto current `master` and
  implements the OOB substrate (Q1=A already locked).
- **BENCH-REDS-REPLAY (#25)** is unblocked at the design level
  (replayed reds register as `provisional` per the
  `units.tsv` header, earn `active` via `promote.py --apply` on the
  v2 control-panel rule; the OOB-grade paired-final is what writes
  the row).

## Cross-references
- Design of record: `fleet/state/BENCH-PROVISIONAL-SCORING-DESIGN.md`
- v1 review: `fleet/scratch/bench-provisional-review.md`
- Original intent: `scratch/pivot-implementation-plan.md` §2
- Sibling build ADR: `fleet/ADR-BENCH-OOB-GRADING.md` §0
- Composition: `fleet/state/EVAL-PIPELINE-DESIGN.md` §"single-capture-
  path guarantee" (F12)
- Promotion gate rule: `fleet/benchmark/promote.py:1-82` (F10 fix)
- F13 live-row gate: `fleet/capability/grades.py:44-82, 492-643`
- FAIL-ON-REVERT tests: `fleet/capability/selftest.py` +
  `fleet/tests/promotion-gate.test.sh` +
  `fleet/tests/dogfood-to-scorecard.test.sh`
