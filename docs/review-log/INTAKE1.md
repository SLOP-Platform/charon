# INTAKE1 — `charon intake import` (the non-coder front door)

**Ticket:** INTAKE1 (tier opus) — turn an external work-list into a Charon plan,
generally and agnostically. Fixes the #1 fresh-user cliff (README pitches "Intake"
but no CLI command existed) and the dogfood critical path.

## What shipped (own: cli.py, intake.py, tests/test_cli.py, tests/test_intake.py)

1. **`charon intake import <file> [--out plan.json] [--format markdown] [--run]`**
   (cli.py `_cmd_intake`). Wraps the existing `intake_file()` → `Plan.write(json)`
   and prints `Plan.to_markdown()` to stdout for human review; the plan-path note
   goes to stderr. Default = write plan + STOP (Phase-1 posture, ADR-0008). `--out`
   defaults to `<file>.plan.json`. **Fixes CLIFF 1.**

2. **Better empty-plan error** (cli.py `_no_units_reason`, called from `_load_plan`).
   When a plan has `review_items`/`issues` but no loadable `units`, surface the
   review-item reasons ("N item(s) need an executable `accept:` command (and owned
   `files:`/`owns:`) to become runnable — …") instead of the dead-end "no loadable
   units". **Fixes CLIFF 2.**

3. **External id preserved** (intake.py: `_ID_LABELS`, `RawItem.declared_id`,
   `_apply_field`, `analyze`). An `id:` field on a source item survives import:
   `_make_id(item.declared_id or item.title, …)` slugifies it board-safe and dedupes
   it, falling back to the title slug when absent. Load-bearing for the future
   write-back/sink (report completion back to the right external ticket). Parsed as
   DATA — first token only, never executed.

## Design constraints honoured (from the adversarial review)

- **No new `TicketSource` port.** Reused the EXISTING text `Adapter` seam
  (`register_adapter`) and the already-wired plan-JSON contract `charon work --units`
  consumes. The enrichment convention (`accept:` + `owns:`/`files:` → runnable;
  without them → propose-only, ADR-0011) already existed in the field grammar — no
  grammar change was needed, only the CLI front door + the `id:` field. Documented in
  the `intake import` help epilog.
- **Nothing SLOP/tracking.db/mediastack-specific in `src/`.** The MVP source is
  generic markdown; `tools/check_boundary.py src` stays green. The SLOP exporter is
  out of tree and out of scope.
- **Security (`--run`)**: `--run` is OFF by default and EXECUTES each unit's `accept`
  string in a worktree. The trust boundary (importing-then-running EXTERNAL tickets
  runs commands the ticket author wrote) is documented in the command help/epilog and
  the `--run` flag help. No code gating added in this ticket — explicit doc warning
  only, per spec. Without `--run`, intake reads input as DATA and only emits an
  artifact (the existing parse-as-data injection tests still hold).

## Gate

`pytest` (545 passed), `ruff check`, `mypy src/charon`, `check_boundary src`,
`check_version` — all green. `check_decisions` reports `docs/REVIEW-LOG.md not found`
— a **pre-existing** condition on origin/master itself (the shared file is absent; the
fleet uses per-ticket `docs/review-log/<id>.md` fragments), NOT a regression from this
ticket and outside this ticket's ownership.
