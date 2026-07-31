# CLIENT-CONNECT — `charon connect <client>`: one-command client wiring (gateway-first last mile)

## Why
PROD-INSTALL installs Charon itself, but there's NO helper to install + wire a CLIENT pointed at the
Charon gateway. The operator lived the friction (2026-06-27) setting up oh-my-pi: install Bun →
`bun install -g @oh-my-pi/pi-coding-agent` → hand-write `~/.omp/agent/models.yml` → set
`$env:CHARON_GATEWAY_TOKEN` → and omp still wasn't on PATH. Same manual dance for opencode, aider.
Operator: "this whole install setup with the tokens and installs is WAY too complicated... I thought
we had a simple setup script that installs everything depending on where you're installing charon,
maybe even installing the client of your choice." This is the gateway-first vision's last mile.

## DESIGN (settled for this ticket — agent/provider-agnostic, product-clean)
Add a **`charon connect <client>`** subcommand. Command shape:
```
charon connect <client> [--host H] [--port 8080] [--model M] [--token T] [--install] [--yes]
```
Behavior, in order:
1. **Verify the gateway FIRST** — `GET http://<host>:<port>/v1/models` (with the token). If
   unreachable, print exactly how to start it (`charon gateway`) and exit non-zero. Never write a
   client config pointing at a dead gateway.
2. **Discover a served model** — pick `--model` if given, else the first id from `/v1/models`.
3. **Install the client if missing** (only with `--install`) — per-OS best-effort
   (brew / curl / npm / bun / pip / winget as appropriate per client) and DETECT Windows vs WSL,
   guiding on the PATH gap (the omp case). Without `--install`, just detect + tell the user the
   install command.
4. **Write that client's provider config** pointing at the gateway (baseURL
   `http://<host>:<port>/v1`, the token, the discovered model id). Each client has a different
   format — the per-client writer knows it.
5. **Print the exact "now run: <client launch cmd>"** to verify end-to-end.

**Client matrix for THIS ticket** (CLI/config-file clients): `opencode` (writes/merges
`~/.config/opencode/opencode.json`), `omp` (`~/.omp/agent/models.yml`), `aider`
(`~/.aider.conf.yml` or the documented env vars). GUI clients (`cline`, `continue`) are a documented
follow-on — leave a clean extension point (a writer registry keyed by client name), don't build them
here. The supported list and each writer live ONLY in `connect.py`.

## Hard constraints
- **Agnostic:** support several clients; hardcode NONE as "the" client. The ONLY client-specific
  knowledge is the per-client writers in `connect.py` — never in the gateway/request path.
- Product-clean (no SLOP/fleet/rig leak); privileged core stdlib-only; **never print/log the token**
  beyond writing it into the client's own config file; don't commit secrets.
- Idempotent / re-runnable: writing a config merges/updates rather than clobbering unrelated keys
  where the format allows (esp. opencode.json which may already have providers).
- Reuse the existing `/v1/models` discovery + token handling already in the codebase (gateway.py /
  cli first-run) rather than re-implementing.

## Acceptance
- `tests/test_connect.py` (new): for each supported client, `charon connect <client>` (gateway
  mocked reachable, a model discoverable) writes the correct config shape (baseURL + token + model)
  to the right path, and is idempotent (re-run doesn't duplicate/clobber). Unreachable gateway →
  non-zero exit, NO config written, helpful message. `--install` absent → no install attempted.
- Token never appears in stdout/logs.
- The writer registry makes adding a client a one-entry change (assert the registry is the single
  source of the supported-client list).

## CONSTRAINTS
Own ONLY: `src/charon/cli.py`, `src/charon/connect.py`, `tests/test_connect.py`. Stdlib core only;
no `pip install -e`; no secrets committed. Gate GREEN every commit:
`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`.
Conventional commits; new behavior ships with its test in the same commit. Review note →
`docs/review-log/CLIENT-CONNECT.md` (per-ticket fragment; NEVER the shared REVIEW-LOG.md).
Open a DRAFT PR (base master), run `submit.sh CLIENT-CONNECT`, then STOP — never merge.

## ⚠ SEQUENCING — stays PARKED until WORK-LAND-PR merges
Owns `src/charon/cli.py`, which WORK-LAND-PR (and WORK-OBSERVABILITY) also own → cannot run
concurrently with them. Unpark (`mv CLIENT-CONNECT.md.parked CLIENT-CONNECT.md`) only after the
current `cli.py` holder has merged. Branch: `feat/client-connect`.

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
