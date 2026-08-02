repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: rig-meta
branch: fix/board-frontmatter-repair-v3
owns: fleet/board/*.md
depends_on: TICKET-CHECK-SCOPE-SEMANTIC
substrate: |
  PyYAML — ADOPT (already adopted, pinned 6.0.3, EVAL-REGISTRY row exists). No new dependency and
  no second parser: the set of broken tickets was ENUMERATED with the gate's own
  substrate_first_gate.parse_frontmatter (never by grep or eyeball), and the same parser proves
  the repair. yamllint REJECTED on merit — it is a STYLE linter (indentation, line length,
  truthy); the question here is PARSEABILITY, which PyYAML already answers authoritatively.
  Nothing here is new code: this is a DATA repair driven by the existing rule module.
note: |
  Companion to GATE-OWNERSHIP-FAILOPEN. That ticket stops the gate LYING about ownership; this
  one removes the condition that made it lie. Split deliberately — see "Dependencies & Sequence".

  WHAT WAS BROKEN (enumerated with the gate's own parser, not by grep):
  23 LIVE fleet/board/*.md tickets whose frontmatter failed the strict-YAML parse, ~21% of the
  board. Two recurring shapes, both "prose leaking into a scalar a strict parser must read":
    (a) a column-0 line (`D&S — Deps & Sequence:`, a bare URL, a backtick) TERMINATING an open
        `note: |` / `source: |` block scalar, after which YAML reads the following lines as a new
        top-level mapping and dies;
    (b) a plain scalar carrying ": ", a backtick, or " #" inside prose.
  Plus 6 tickets carrying `priority: 0 # inherited: blocks a P0 ticket` — the SAME class one level
  down: an inline comment inside a value the line-based reader must read strictly, which is why
  fleet/tests/priority-validator.test.sh was RED (7 failed) on every PR. 2 of those 6
  (MARKER-PROOF-MECHANIZE, REPO-MAP-CONVERGE) are also in the 23 — the two symptom sets OVERLAP
  but are not the same population.

  HOW IT WAS REPAIRED — three meaning-preserving transforms, nothing deleted:
    1. an escaping column-0 `D&S — Deps & Sequence:` line is PROMOTED to a real
       `## Dependencies & Sequence` markdown heading. That ends the frontmatter (the gate's _HALT
       rule) so the YAML parses, AND it satisfies the D&S standing rule that the column-0 line
       never satisfied — 13 tickets gained a real D&S section this way.
    2. any other escaping column-0 line is INDENTED back inside the block scalar it escaped.
    3. `key: <prose>` containing YAML-hostile text becomes `key: |` + the prose indented beneath.
       Never applied to repo/branch/owns/base/depends_on — the fields the sed/awk readers consume.
    4. the inline priority comment moves to an INDENTED YAML comment line above the field. Column
       0 is unavailable: the gate's _HALT rule treats a col-0 "# " as a markdown heading and would
       truncate the frontmatter (measured — it silently emptied work_class on all six).

  PROOF: unparseable live tickets 23 -> 0; `owns:` entries visible to the gate 172 -> 236;
  priority-validator RED (7 failed) -> GREEN; and every line-based reader's view of
  repo/branch/owns/base/depends_on is BYTE-IDENTICAL before and after.
accept: |
  - `substrate_first_gate.read_frontmatter` parses every live fleet/board/*.md — 0 failures.
  - `owns:` entry count strictly INCREASES (172 -> 236) — the repair restores ownership that was
    invisible, and removes none.
  - `bash fleet/tests/priority-validator.test.sh` is GREEN (was RED, 7 failed).
  - A byte-identical diff of the line-based readers' view of repo/branch/owns/base/depends_on
    across all 27 touched tickets — no content deleted, no field value changed.
  - PROJECT-MEMBERSHIP-GATE's two ABSOLUTE `owns:` paths are rewritten to repo-relative form.
    An absolute dev-box path in a tracked file is a real defect independent of everything else
    (it cannot survive a repo boundary), and the normalised owns comparison in
    TICKET-CHECK-SCOPE-SEMANTIC treats it as the SAME file set, so the ticket stays grandfathered.
  - `rig-ci-scope.sh board` is GREEN on this branch, because TICKET-CHECK-SCOPE-SEMANTIC now
    de-grandfathers on MEANING rather than on file-touch. Every repaired ticket is skipped as
    "changed no substrate-relevant field"; only the two tickets minted here are checked in full.

## Dependencies & Sequence

- `GATE-OWNERSHIP-FAILOPEN` (PR #365) is ORTHOGONAL — that PR makes the failure legible, this one
  removes it; either order is safe.
- **depends_on: TICKET-CHECK-SCOPE-SEMANTIC (build order, HARD).** This branch is CUT FROM it.
  Without it this repair is unlandable: repairing a ticket puts it in the PR diff, which used to
  DE-GRANDFATHER it (`rig-ci-scope.sh` substrate-checked every ticket present in the diff), so
  tickets that had never been in a diff since they were written failed the per-ticket content
  rules the moment they were touched — 21 pre-existing REDs, 13 of them "no `substrate:` field".
  The gate made the repair of a gate defect unlandable. THAT was fixed at the root rather than
  worked around: de-grandfather on MEANING, not on file-touch.
- **The pre-existing debt is NOT silently absorbed — it is still there and still owed.** 13 live
  tickets carry no `substrate:` field, LITELLM-CAPABILITY-ADOPTION is `work_class: design-review`
  while owning a test file, and SSOT-DRIFT-GATE + GITHUB-LIMITS-HARDENING have no D&S section.
  Authoring those verdicts for other owners would be exactly the fabrication the substrate gate
  exists to prevent; they need their owners. They will fire the moment any of those tickets'
  substrate-relevant fields actually change, which is the correct moment.
- **owns-collision:** board data only. Touches no script. Serialised through `fleet/board-lock.sh`.
