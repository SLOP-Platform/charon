# CONSOLE-PROVIDER-MGMT — manage providers + served models from the gateway web console

## Dependencies & sequence
**depends_on: NONE.** Owns `proxy_server.py` (the console) + config + a console asset/module + test.
**Owns `proxy_server.py` → SERIALIZE with OBS-UI** (which also owns it) — cannot run concurrently;
sequence the two (either order). Otherwise disjoint. Wave: standalone.

## Why (operator, 2026-06-28 — repeated manual friction)
Adding/removing providers and toggling served models is CLI-only today (`charon providers add`,
`charon models`, hand-edited config). A fresh-install user shouldn't need the CLI. The gateway
already serves a token-gated web console + a first-run web setup; extend it to MANAGE
providers/models live.

## What to build
A provider/model management panel in the gateway web console (token-gated, loopback/LAN as the
gateway already is):
1. **Providers:** list configured providers + key status; ADD a preset or custom provider with its
   API key; REMOVE one. **VALIDATE the key on add** by probing a real completion (tie to
   SETUP-KEY-UX) and show pass/fail — don't accept a key blindly.
2. **Models:** show the catalog from `/v1/models`; let the user ENABLE/DISABLE which are served.
3. Apply changes to the live gateway (reload, no container restart needed if feasible).

## Hard security constraints
- The console is already token-gated — keep it so; the management endpoints MUST require the gateway
  token. **NEVER return a stored key to the browser** (show only set/unset + last-4); store keys in
  the existing `secrets.json` (0600), never in logs or the page source.
- No new public-network exposure; respect the existing bind (loopback default).
- Privileged core stays stdlib-only; agent/provider-agnostic; product-clean.

## Acceptance
- `tests/test_console_provider_mgmt.py`: an authenticated request adds a provider (key stored, NOT
  echoed back), key-validation probe runs, and toggling a model changes what `/v1/models` serves;
  unauthenticated requests are rejected; no key appears in any response body/log.

## CONSTRAINTS
Own (finalize at activation): `src/charon/proxy_server.py`, `src/charon/config.py`, a console
asset/module, `tests/test_console_provider_mgmt.py`. Stdlib core only; no secrets in logs/responses.
Gate green; conventional commits; review-log → `docs/review-log/CONSOLE-PROVIDER-MGMT.md`. Draft PR,
`submit.sh`, STOP. BACKLOG (parked). Branch `feat/console-provider-mgmt`.

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
