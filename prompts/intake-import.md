Build `charon intake import` — turn an external work-list into a Charon plan, generally and
agnostically. This is the #1 fresh-user cliff (the README pitches "Intake" as the non-coder front
door, but no CLI command exists) AND the dogfood's critical path. Canonical tier: **high**
(fleet `opus`). Reshaped per the design + adversarial review — read both constraints below.

READ FIRST: `src/charon/intake.py` (`RawItem` :68-79, `analyze` :475-583, `intake_file` :372,
`Plan.write`/`to_markdown` :317-359, the existing text `Adapter` seam + `register_adapter`
:211-223, the field grammar `_apply_field`/`_split_accept` :161-202, `_make_id` :673), and
`src/charon/cli.py` (the subcommand style of `_cmd_work` ~:839-866, and the `_load_plan`
dead-end at ~:635 `"intake plan has no loadable units"`).

DESIGN CONSTRAINTS (from the adversarial review — do NOT violate):
- **Do NOT add a new `TicketSource` port.** Reuse the EXISTING text `Adapter` seam
  (`register_adapter`, intake.py:211-223) and the already-wired plan-JSON contract that
  `charon work --units` consumes. A new port is unnecessary and is itself a SLOP-coupling risk.
- **Nothing SLOP/tracking.db/mediastack-specific in `src/`** — `tools/check_boundary.py` fails CI
  on it. The MVP source is generic **markdown** (the adapter that already exists but has no CLI).
  The SLOP exporter is OUT OF TREE and NOT part of this ticket.

BUILD (own ONLY: cli.py, intake.py, tests/test_cli.py, tests/test_intake.py):
1. **`charon intake import <file> [--out plan.json] [--format markdown] [--run]`** (cli.py) — wrap
   the existing `intake_file()` → `Plan.write(json)` + print `Plan.to_markdown()` for human review.
   Default = write plan + stop (Phase-1 posture). `--run` (OFF by default) chains into the existing
   run path. Fixes CLIFF 1.
2. **Better empty-plan error** (cli.py ~:635): when a plan has `review_items` but no loadable
   `units`, DON'T just say "no loadable units" — surface the review-item reasons (e.g. "N item(s)
   need an executable `accept:` command to become runnable"). Fixes CLIFF 2.
3. **Enrichment convention** (intake.py): ensure the field grammar lets a source line supply
   `accept:` (executable check) and `owns:`/paths so a ticket becomes a RUNNABLE unit, not just a
   propose-only review item. Document the convention in the command help + a short README/docs line.
   Without `accept`+`owns` a ticket stays propose-only (correct, per ADR-0011) — the convention is
   how a user opts in to runnable.
4. **Preserve the EXTERNAL id** (intake.py `_apply_field`): recognize an `id:` field so a source
   ticket's own id survives import (today `_make_id` slugifies the title and loses it). This is
   load-bearing for the future write-back/sink feature (so Charon can report completion back to the
   right source ticket). If absent, fall back to the slug as today.
5. **Security note**: `--run` EXECUTES each unit's `accept` string in the worktree. Document the
   trust boundary in the command help: importing-then-running EXTERNAL tickets runs commands the
   ticket author wrote. (No code gating needed in this ticket — just the explicit doc warning.)

TESTS (test_cli.py, test_intake.py): `charon intake import` writes a plan + markdown; the
empty-plan error surfaces review-item reasons; an enriched source (with `accept:`+`owns:`) yields a
RUNNABLE unit; an `id:` field is preserved through import; a plain work-list yields propose-only
review items (no silent runnable). Injection-safety: ticket text stays DATA at parse time
(reuse the existing intake parse-as-data tests).

CONSTRAINTS: own ONLY the 4 files. Stdlib core only. Gate green every commit (pytest, ruff, mypy
src/charon, check_boundary — MUST stay clean, no SLOP refs — check_version, check_decisions).
Conventional commits. Review note → `docs/review-log/INTAKE1.md`. Commit ALL work and STOP — no
push / PR / submit.sh. If a fix needs a file outside owns, STOP and run release.sh with a reason.

## REPORT BACK — MECHANIZED FORMAT (required)
End your session by emitting EXACTLY this block. Fixed fields, one line each, no diffs or logs.
Validate it before you finish: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Full spec + rationale: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`

```
=== SESSION REPORT v1 ===
TICKET:       <ticket-id>
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha> | none
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> is owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> | n/a — <why> | NOT-DONE
OBSERVABLE:   MET | DEFERRED — <what could not be observed and why>
RAN:          <what you proved by EXECUTING>
READ:         <what you concluded by READING only>
BRIEF-ERRORS: none | <what this brief got factually wrong>
BLOCKED-BY:   none | <ticket or condition>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
