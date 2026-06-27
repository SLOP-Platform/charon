# Review-log fragments

Each significant change records its review/decision note as **one file per ticket**
here: `docs/review-log/<id>.md` (e.g. `E1.md`, `gateway-p2.md`, `FB3.md`). The shared
rollup `docs/REVIEW-LOG.md` is a **generated artifact** — concatenated from these
fragments by `tools/render_review_log.py` — and is never hand-edited.

## Why fragments

The old workflow had every ticket append a dated section to the single
`docs/REVIEW-LOG.md`. Two tickets landing in parallel both appended at end-of-file →
a textual merge conflict, a conflicting PR, and no CI. Same fix-shape as per-droid
mailbox files: give each ticket its own file so concurrent notes can never collide.

## Rules

- Write **only** your own fragment, `docs/review-log/<id>.md` (your ticket id).
- **Never** edit another ticket's fragment, and never hand-edit `docs/REVIEW-LOG.md`.
- Start your fragment with a dated `##` heading, matching the existing entries, e.g.
  `## 2026-06-27 — <id> — <one-line title>`.
- Re-render the rollup after adding a fragment:

  ```sh
  python3 tools/render_review_log.py
  ```

- CI runs `python3 tools/render_review_log.py --check`, which fails if the rollup is
  stale vs the fragments. Fragments are concatenated in stable **lexical filename
  order**, so the rollup order is deterministic regardless of who lands first.
