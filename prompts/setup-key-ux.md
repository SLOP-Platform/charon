# SETUP-KEY-UX — validate the provider key at setup + stop the blind key input

## Dependencies & sequence
**depends_on: NONE.** Owns `src/charon/cli.py` (+ its test). No other parked backlog ticket owns
`cli.py`, so this is DISJOINT and safe to run CONCURRENTLY with all of them. A fresh Charon can claim
it any time.

## Why (live dogfood 2026-06-28)
A fresh 4-LOM `setup` reported "2 models configured / Done" with an INVALID opencode-zen key. The
gateway imported the catalog (`/v1/models` → 200) but every real completion 401'd
(`AuthError: Invalid API key`) — the failure only surfaced at first chat, far from setup. Two
causes: (1) setup never VALIDATES the key (it imports the catalog, which doesn't auth); (2) the key
is entered via a BLIND `getpass` (`cli.py:202` providers-add, `cli.py:335` setup), so a mistyped/
mis-pasted key is invisible.

## What to build
1. **Validate the key at setup:** after storing a provider key, probe a real **completion** (a tiny
   `/v1/chat/completions`), not just `/v1/models` — and clearly WARN (don't silently "succeed") if
   it fails auth. Surface the provider's error so the user knows the key is bad immediately.
2. **Stop the blind input:** the masked `getpass` must let the user CONFIRM what they entered —
   e.g. echo a masked-but-checkable confirmation (show length + last 4 chars), or a "re-enter to
   confirm", or honor a visible `--show-key` opt-in. The existing `providers add --key <value>`
   (visible) is the escape hatch; make the interactive path verifiable too. Never log the full key
   to a file/stdout by default.

## Acceptance
- `tests/test_setup_key.py`: storing a key triggers a completion-probe; an auth failure is surfaced
  as a warning/non-zero (not a silent success). The interactive key entry exposes a confirmation
  (assert the confirm/echo path). No full key written to logs.

## CONSTRAINTS
Own ONLY: `src/charon/cli.py`, `tests/test_setup_key.py`. Stdlib core only; no secrets committed
(do not write the key to logs). Gate GREEN every commit
(`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`).
Conventional commits; review note → `docs/review-log/SETUP-KEY-UX.md`. Draft PR, `submit.sh`, STOP.
BACKLOG (parked). Branch `feat/setup-key-ux`.

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
