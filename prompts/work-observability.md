# WORK-OBSERVABILITY — make a `charon work` run visible while it runs

## Why (verified 2026-06-27)
A `charon work` / `run` run is a BLACK BOX: silent until it prints one final JSON blob. The engine
(`engine/scheduler.py` `drain`) has zero progress output; the only record is per-unit
`charon ledger <id>` + hand-tailing `.charon/work-board.json` / `.charon/<id>/checkpoints.jsonl`.
ADR-0004 D7 explicitly DEFERRED the live "watch the agent" view; this builds it.

## Scope (THIS PR — the two highest-value sub-goals; UI/capture are follow-ons)
1. **Live per-unit progress** as the scheduler drains: emit human-readable lifecycle lines —
   `claimed / started / checkpoint N (verified a0…) / land:propose|hold / done / blocked` — to
   stderr (NOT stdout; stdout stays the final JSON for piping). Gate behind a `--progress/--quiet`
   switch (progress ON by default for a TTY, OFF when stdout is redirected or `--quiet`). Today the
   run is silent until the end.
2. **Aggregate run view**: a `charon work --status` (or `charon runs`/extend `ledger`) command that
   rolls up a WHOLE run — every unit's status / checkpoints / land decision / PR — from the durable
   `.charon` state, not just the per-unit `ledger <id>`.

DEFER to follow-on tickets (note them in the review-log, don't build here): capturing the agent's
ACP transcript to a per-unit log (needs `adapters/acp.py`, stderr currently → DEVNULL), and a
work/board panel in the gateway/Mode-B UI (needs `proxy_server.py`/`service/`).

## Hard constraints
- **Anti-dilution:** observability lives ONLY in the opt-in engine/CLI path — NEVER add cost to the
  gateway per-request hot path.
- Progress → **stderr**; stdout stays machine-readable (the final JSON). No secrets/tokens in any
  emitted line.
- Agent/provider-agnostic; product-clean (no SLOP/fleet/rig leak); privileged core stdlib-only.

## Acceptance
- `tests/test_work_observability.py` (new): a drained run emits the expected lifecycle lines to
  stderr (capture & assert), and stdout remains the unchanged final JSON; `--quiet`/redirected
  stdout suppresses progress. The aggregate view command rolls up a multi-unit run's statuses from
  `.charon` state. No secret strings appear in emitted output.
- Existing `run_work` / scheduler tests stay GREEN.

## CONSTRAINTS
Own ONLY: `src/charon/engine/scheduler.py`, `src/charon/cli.py`, `tests/test_work_observability.py`.
Stdlib core only; no `pip install -e`; no secrets committed. Gate GREEN every commit:
`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`.
Conventional commits; new behavior ships with its test in the same commit. Review note →
`docs/review-log/WORK-OBSERVABILITY.md`. Open a DRAFT PR (base master), run
`submit.sh WORK-OBSERVABILITY`, then STOP — never merge.

## ⚠ SEQUENCING — PARKED until CLIENT-CONNECT merges
Owns `cli.py`, which CLIENT-CONNECT also owns → cannot run concurrently. `depends_on: CLIENT-CONNECT`.
Unpark (`mv WORK-OBSERVABILITY.md.parked WORK-OBSERVABILITY.md`) after CLIENT-CONNECT merges.
Branch: `feat/work-observability`.

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
BUDGET:       ok | TRUNCATED — <what you could not finish and why>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
