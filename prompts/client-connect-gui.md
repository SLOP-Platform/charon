# CLIENT-CONNECT-GUI — add cline + continue to `charon connect` (CLIENT-CONNECT follow-on)

## Dependencies & sequence
**depends_on: NONE — Wave 1.** Owns `connect.py` (+ test) ONLY. CLIENT-CONNECT (which created
`connect.py`) is already merged, so this is unblocked. Owns are DISJOINT from every other backlog
ticket → safe to run CONCURRENTLY with all Wave-1 tickets. A fresh Charon can claim it immediately.

## Why
CLIENT-CONNECT (#72) shipped `charon connect <opencode|omp|aider>` with a writer registry that is
the single source of the supported-client list, leaving a clean extension point. The two GUI
clients flagged as follow-ons — `cline` (VS Code extension) and `continue` — were deferred.

## What to build
Add `cline` and `continue` to the connect registry + their per-client config writers in
`connect.py`, reusing the existing verify-gateway → discover-model → write-config → print-launch
flow. Each is a registry entry + a writer that knows that client's on-disk config format:
- **continue** — `~/.continue/config.json` (or `config.yaml`): add an OpenAI-compatible model
  entry pointing at the gateway baseURL + token + discovered model. Research the exact current
  schema before writing (continue's config has a `models` array).
- **cline** — a VS Code extension; its settings live in the VS Code `settings.json` (or the
  extension's storage). Research the exact key for an OpenAI-compatible/custom baseURL + apiKey.
  If cline has no file-writable config (GUI-only settings), DON'T fake it — emit clear manual
  setup instructions instead and register it as "guided" rather than "auto-written" (note this in
  the review-log). Don't invent a config path that doesn't exist.

## Hard constraints
Agnostic — knowledge lives ONLY in `connect.py`'s writers/registry. Token written only into the
client's own config (never printed). Idempotent re-runs. Registry stays the single source of the
supported list.

## Acceptance
- `charon connect continue` (gateway mocked reachable) writes the correct continue config shape;
  idempotent. `charon connect cline` either writes the correct config OR (if GUI-only) prints
  correct manual steps and exits 0. `tests/test_connect_gui.py` covers both. Token never in stdout.

## CONSTRAINTS
Own ONLY: `src/charon/connect.py`, `tests/test_connect_gui.py`. Stdlib core only; gate GREEN
(`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`).
Conventional commits; review note → `docs/review-log/CLIENT-CONNECT-GUI.md`. Draft PR, `submit.sh`,
STOP. BACKLOG (parked).

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
