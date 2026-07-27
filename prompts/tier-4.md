Add the Tiers web-UI surface (DTC HARD REQ #3). Canonical tier for this ticket: **high**
(mapped to fleet `opus`). Depends on TIER-2 (merged): `gateway.make_setup_handler` already
has the `"tiers"` branch + `_reload`; `config.set_tiers` exists. Read
`/home/stack/charon-private/fleet/DTC-tier-abstraction.md` §"Web-UI surface (HARD REQ #3) +
backend API" FIRST, plus `src/charon/proxy_server.py` (`_SETUP_HTML` ~147, `addPool` pattern
182-185, POST allowlist 409-411, CSRF/Origin guard 414-420, console 80-103/738-763).

GOAL: Add a "Tiers" fieldset to `_SETUP_HTML`, add `"/charon/tiers"` to the POST allowlist
(`proxy_server.py:409-411`), add a `tier` tag column to the console.

DESIGN ANCHORS (cite in your review note):
- New "Tiers" fieldset: rows = canonical tiers from `order`, each a comma-separated member-id
  input (reuse the `addPool` pattern) + alias chips. Operator types model ids straight from
  the registry list already rendered on the page. POST `{order, members, aliases}` to
  `/charon/tiers` (the TIER-2 backend branch handles persist + reload).
- CRITICAL (Stance A missed this): add `"/charon/tiers"` to the HARDCODED POST allowlist
  (`proxy_server.py:409-411`) — else the POST falls through to chat-completions and 502s. The
  CSRF/Origin guard (414-420) then covers it for free.
- Console (read-only) already renders pools + recent failovers; add a `tier` tag column so
  tier vids are visually distinct. Do NOT change failover logic — display only.

BUILD:
1. src/charon/proxy_server.py — EXTEND in place: Tiers fieldset in `_SETUP_HTML`;
   `/charon/tiers` in the POST allowlist; `tier` tag column in the console render. Do NOT add
   backend persist/reload logic here — that's TIER-2's handler; this ticket only POSTs to it.
2. tests/test_setup_tiers.py — proven-red: `/charon/tiers` is in the allowlist (POST does not
   fall through to chat-completions); the setup page renders a Tiers fieldset with member
   inputs from `order`; the console shows the tier tag column.

CONSTRAINTS: own ONLY the files in your board ticket's `owns:` line
(src/charon/proxy_server.py, tests/test_setup_tiers.py) — nothing else. proxy_server.py
already exists: EDIT it. The backend `"tiers"` handler + `set_tiers` belong to TIER-2/TIER-1
— do NOT edit gateway.py or config.py. Same wave as TIER-5/6/7 (disjoint files). If your work
needs a file outside `owns:`, STOP and run release.sh with a one-line reason. Stdlib-only
core. Gate green every commit (pytest, ruff, mypy src tests, check_boundary, check_version).
No secrets. Conventional commits. Write your review note as `docs/review-log/TIER-4.md`
(NEVER the shared `docs/REVIEW-LOG.md`). Commit ALL work on your branch and STOP — do NOT
push, do NOT open a PR, do NOT run submit.sh; the launcher publishes after you exit.

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
