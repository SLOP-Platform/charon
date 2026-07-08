# SESSION — <TICKET-ID>: <one-line title>

**Model:** <model> (why this model was picked for this task)
**Repo:** charon  ·  **Ticket:** <TICKET-ID>
**Base branch/worktree:** `<branch>` at `<worktree-path>` (an isolated worktree — do NOT
work in the shared main tree `/home/stack/code/charon`)

## IF THIS BRIEF CREATES/UPDATES A `board/<TICKET-ID>.md` TICKET (required field)
Every LIVE board ticket (any `board/*.md`, i.e. not `.md.parked`) MUST carry a
`work_class:` line — one line, right after `tier:`, matching the existing metadata style
(`tier:`, `branch:`, `depends_on:`, `owns:`, `prompt:`). `validate_board.sh` HARD-FAILs any
ticket missing it or using a value outside the taxonomy. It is the auto-resolve source
`capability/assign.py` reads instead of requiring `--work-class` on the CLI. Pick exactly
one (single source of truth: `capability/grades.py`'s `WORK_CLASSES` + `GENERALIST`):
`money-path, routing, ci-infra, refactor, bugfix, tests, greenfield-feature, docs,
frontend, generalist`. Example:
```
tier: strong
work_class: bugfix
branch: feat/fix-thing
depends_on:
owns: src/charon/thing.py, tests/test_thing.py
prompt: /home/stack/charon-private/prompts/fix-thing.md
```

## FIRST ACTS (mandatory — worktree isolation + bridge coordination)
1. `cd <worktree-path>` (create it off latest `origin/master` if it doesn't exist yet).
2. `git fetch origin && git merge origin/master` — rebase onto current master. Resolve
   any conflict; re-run tests after.
3. Register on the session-bridge: `register` with `session_id` (your choice),
   `repo: "charon"`, `ticket: "<TICKET-ID>"`, `status: "in-progress"`. Heartbeat
   (`update`) periodically.
4. Read any linked design/review doc before starting.

## THE TASK
<what's broken / what's wanted, and why>

## REQUIRED CHANGE
<the concrete change(s) to make>

## REQUIRED PROOF
<tests to add/keep; what a reviewer will check for>

## GATE (both, from the worktree; must be green)
- `PYTHONPATH=src python3 -m charon.cli gate`  (ruff/mypy/SLOP-boundary/version/gate-registry)
- `PYTHONPATH=src python3 -m pytest -q` (scope to the touched package/module with `-k`
  or a path if the full suite is slow)

## BOUNDARY / D&S
- Product ships standalone: **no** `/home/stack`, fleet, SLOP, or runner references in
  `src/` or committed config.
- Depends on / touches: <list dependent tickets and files; confirm no collision with
  other in-flight branches via `git diff --name-only` against `owns:`>

## REPORT BACK (short — do not paste diffs)
Verdict-ready summary: files changed, test names, gate pass/fail, and the commit SHA
(see LAST STEP below).

## LAST STEP (REQUIRED) — commit, do not skip
```
git add -A && git commit -m "<ticket>: <what changed>"
```
Report the commit SHA back to the manager.

Do NOT push. Do NOT merge. (Commit is REQUIRED; pushing/merging is the manager's job.)
