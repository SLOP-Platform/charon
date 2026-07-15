# EVAL-TAXONOMY — canonical work-class taxonomy (single source of truth)

Ticket: `fleet/board/EVAL-TAXONOMY-ALIGN.md`. Fixes the adversarial review's
F3 BLOCKER (`fleet/state/MODEL-TESTING-ADVERSARIAL-REVIEW.md`) and
MSOT-BLAST-RADIUS-AUDIT.md row #2: a 4-way work_class-taxonomy split
(`grades.py` 11 / `model-scorecard.sh` 9 / `model-scorecard.tsv` 9 /
product router 6) meant the product gateway router would query
`grades.py` in ITS OWN vocabulary and get **zero rows back** — "two
consumers, one taxonomy" (grades.py's own docstring) was false.

## Decision

ONE canonical taxonomy for **model-capability grading** (the axis
`grade()` keys on) = the PRODUCT ROUTER's semantic work_class vocabulary,
verbatim:

    CANONICAL_CLASSES = reasoning, coding, translation, creative, analysis, general

Source of truth: `src/charon/routing_policy/matrix.py:20-27` `WorkClass`
Literal, mirrored identically in `src/charon/capability/taxonomy.py:63-125`
`_SEED_CLASSES` (same 6 names). `fleet/capability/grades.py`'s
`CANONICAL_WORK_CLASSES` tuple is a lockstep literal copy (same duplication
discipline `_ALIASES`/`tiers.py` already documents in that file);
`grades.py`'s `_live_product_work_classes()` cross-checks it against the
live product module when importable, as a drift detector.

This was the ticket's explicit call: routing serves the *product*, not the
build rig, so the product router's axis is the meaningful one — not the
fleet's ticket-shape vocabulary.

## Why the fleet ticket-shape classes are NOT the grading axis

`fleet/board/*.md` tickets (and `fleet/model-scorecard.sh`'s
`VALID_CLASS`, `fleet/capture/enqueue-capture.sh`'s
`VALID_WORK_CLASSES`) use a build-ticket vocabulary: money-path, routing,
ci-infra, refactor, bugfix, tests, greenfield-feature, docs, frontend
(`grades.py` additionally carries rig-meta, design-review). These describe
the *shape* of a fleet ticket, not a model capability. The review's F5
finding ("the honest battery is one skill wearing three labels") shows why
this axis is mostly illusory precision for grading purposes: nearly every
fleet ticket is the same underlying skill — a small, local code change —
wearing a different label. `grades.py` keeps this vocabulary as
`WORK_CLASSES` (board-ticket / `assign.py` CLI **input** shape only —
unchanged behavior for `assign.py`/`validate_board.sh`, neither of which
this ticket owns or re-tags) and maps it into the canonical grading space
at **read time** via the mapping below — the TSV on disk keeps its
original raw strings; nothing is rewritten or lost.

## Fleet -> canonical mapping (`grades.py`'s `_LEGACY_TO_CANONICAL`)

| Fleet ticket-shape class | Canonical grading class | Rationale |
|---|---|---|
| money-path | coding | core business-logic code change |
| routing | coding | gateway routing code change |
| ci-infra | coding | CI/infra-as-code change |
| refactor | coding | code restructuring |
| bugfix | coding | code defect fix |
| tests | coding | test-code authorship |
| greenfield-feature | coding | new feature code |
| frontend | coding | UI code |
| design-review | analysis | evaluating/assessing a design tradeoff |
| docs | general | prose/documentation — not code, reasoning, translation, or creative |
| rig-meta | general | fleet-harness meta-work, not a product-facing skill |

No fleet class maps to `reasoning`, `translation`, or `creative` — the
fleet ticket stream has never produced one of those (consistent with F5:
fleet tickets are ~1 skill, "small code edit"). A real per-class grade for
those three classes needs a task source *outside* the fleet ticket stream
(the review's F5/F12 fix — a semantic item-bank). This ticket fixes the
JOIN so the router can see what evidence *does* exist; it does not
manufacture coverage that was never collected.

## What changed in `grades.py`

- `CANONICAL_WORK_CLASSES` (new): the 6-class canonical tuple above.
- `_LEGACY_TO_CANONICAL` (new): the mapping table above, with an
  import-time assertion that every `WORK_CLASSES` entry has a mapping
  (fail loud on drift, not a silent `None` at grade time).
- `_canonical_of()` (new): resolves either vocabulary to a canonical
  bucket.
- `_live_product_work_classes()` (new): best-effort live cross-check
  against the product's own `WorkClass` Literal.
- `ScorecardGradesProvider._rows_for()`: when `grade()`/`assign()` is
  called with one of the 6 CANONICAL strings, each row's raw work_class is
  resolved to its canonical bucket AT QUERY TIME (via `_canonical_of()`,
  never cached/precomputed) and matched against the requested canonical
  class — folding in every mapped legacy row. This is the new capability
  that lets a canonical-space caller (the future gateway router) see real,
  non-zero historical data; resolving per-query (not at `_load()` time)
  also means `_LEGACY_TO_CANONICAL` is a genuinely live mapping, never a
  frozen snapshot — the TSV on disk is never rewritten either way. When
  called with a legacy `WORK_CLASSES` string (today's only real caller,
  `assign.py`, via board-ticket `work_class:` meta), matching stays
  EXACT-STRING as before — zero behavior change to `assign.py` /
  `validate_board.sh` / the existing `selftest.py` fixture-driven proofs.
- The module docstring's "two consumers... SAME work_class taxonomy"
  claim is now TRUE: both consumers share this one canonical space, just
  entering it from a different vocabulary (ticket-shape vs native
  canonical).

## Fail-on-revert (`fleet/capability/selftest.py`)

1. A scorecard row tagged natively with a canonical class (`coding`) is
   retrievable via `grade(model, "coding")` directly.
2. A LEGACY-tagged row (e.g. `bugfix`) is ALSO retrievable via
   `grade(model, "coding")` — its mapped canonical bucket — proving
   historical data isn't lost. This is a real, exercised dependency, not a
   tautology: clearing `_LEGACY_TO_CANONICAL` in the test makes
   `_rows_for(model, "coding")` — the actual router-class query — return
   `[]` (zero rows), the exact F3 regression ("the router-class query
   returns empty"). `grade()` itself still returns a pick via its
   SEPARATE, pre-existing generalist-fallback safety net (should-fix #3)
   — the test also asserts that fallback is visibly flagged
   (`fallback_used=True`), not a silent fabrication of direct evidence.
3. Canonical buckets stay disjoint: a legacy row mapped to `coding` does
   not leak into an unrelated canonical class query (`reasoning`).
4. Drift guard: `CANONICAL_WORK_CLASSES` (code) == the canonical class set
   documented in this file == (best-effort) the LIVE product
   `matrix.WorkClass` Literal, when the product repo is importable.

## Known, deliberately UNTOUCHED residual (out of this ticket's scope)

`grades.py`'s `WORK_CLASSES` (11: adds `rig-meta`, `design-review`) is
already diverged from `model-scorecard.sh`'s `VALID_CLASS` (9, no
`rig-meta`/`design-review`) and `enqueue-capture.sh`'s hardcoded copy
(same 9) — MSOT-BLAST-RADIUS-AUDIT.md row #2's *other* divergence, on the
fleet-ticket-shape axis itself, not the fleet<->router split this ticket
fixes. This ticket's `owns:` is `fleet/capability/grades.py` + this file
only; reconciling the board-ticket-shape vocabulary would touch
`model-scorecard.sh`/`enqueue-capture.sh` (neither owned here) and does
not block the router-data fix above, since `WORK_CLASSES`'s content is
unchanged by this ticket.
