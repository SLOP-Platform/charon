## 2026-06-27 — FB3 — retire shared-append REVIEW-LOG → per-ticket fragments

- **Change under review:** kill the merge-conflict class that fired whenever two
  tickets appended a dated section to the single `docs/REVIEW-LOG.md` at end-of-file
  (it blocked S1 #27 vs E2 on 2026-06-27). Same fix-shape as per-droid mailbox files:
  one file per ticket, never a shared append.
- **Mechanism:** every legacy dated section was migrated **verbatim** into one
  `docs/review-log/<id>.md` fragment. `tools/render_review_log.py` (stdlib-only)
  concatenates the fragments — in stable lexical filename order, README excluded —
  under a generated `DO NOT EDIT` header into the rollup `docs/REVIEW-LOG.md`, which
  is now a generated artifact. `--check` re-renders and exits non-zero if the
  committed rollup is stale, for CI.
- **Design decisions (pre-code):**
  - **Stable order = lexical by filename**, not chronological. The rollup's job is
    determinism + conflict-freedom, not preserving insertion order; lexical is the
    spec's first suggested option and needs no embedded sort key polluting the
    verbatim fragment text. New fragments slot in deterministically wherever their id
    sorts; landing order no longer matters.
  - **Header (title + preamble + notice) is a renderer constant**, not a fragment —
    it is rollup chrome, not a ticket entry. The README (excluded from the rollup)
    carries the convention.
  - **Migration is verbatim per section**; only the global ordering changes (legacy
    reverse-chron → lexical). No section content was edited or editorialized.
- **Scope (owns):** `docs/REVIEW-LOG.md`, `docs/review-log/*`,
  `tools/render_review_log.py`, `tests/test_render_review_log.py` — nothing else.
  Wiring `--check` into `.github/workflows/*` is OUT of scope (workflow files are not
  owned); requested in the PR body for the manager to add.
- **Net:** the shared-append conflict class is structurally gone — droids write only
  their own fragment; the rollup regenerates. Stdlib-only; gate green.
