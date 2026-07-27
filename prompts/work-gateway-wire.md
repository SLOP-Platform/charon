# WORK-GATEWAY-WIRE — forward the gateway credential so the `charon work` agent authenticates

## Why (proven by live diagnostic — do NOT re-derive)
A live dogfood proved `charon work --backend acp` cannot route the spawned agent's LLM calls
through Charon: every call returns `401 missing or invalid bearer token`, so the agent never edits
or commits. Root cause (definitive, from the code):

- `charon work` → `run_work` → `api._resolve_backends(..., "acp", ..., acp_cmd)` builds a **bare**
  `AcpBackend(shlex.split(acp_cmd), passthrough_env=_acp_passthrough_env())`. It stands up **no**
  per-run proxy and injects **no** config override.
- So the spawned `opencode acp` falls back to its OWN `~/.config/opencode/opencode.json`, whose
  `charon` provider points at the standing Charon gateway and reads its apiKey from
  `{env:CHARON_GATEWAY_TOKEN}`.
- But `_acp_passthrough_env()` (`src/charon/ports/agent_launch.py:34-43`) only forwards
  `HOME/PATH/XDG_*` + the `*_API_KEY` provider keys — **never `CHARON_GATEWAY_TOKEN`**. The env var
  resolves empty in the child → 401.

DECISION (operator, gateway-first): the `charon work` agent should authenticate to the **standing
Charon gateway it is already configured for** by forwarding that one credential. (The per-run
in-process proxy approach is deferred to a future orchestrator-mode ticket; its plumbing is parked
on remote branch `feat/work-gateway-wire` — do NOT pull it in here.)

Routing is already proven sound: an out-of-band control (the agent with the token present) moved the
gateway's served counter and returned real output. The ONLY missing link is forwarding the token.

## What to build (minimal, surgical)
Forward `CHARON_GATEWAY_TOKEN` into the env of the spawned ACP agent on the **bare `charon work`
acp path** — but ONLY when it is set in the environment (never inject an empty value), and ONLY the
single gateway credential (this is a deliberate, scoped fence exception — the agent legitimately
needs that bearer to use the gateway it is pointed at).

Implementation lives entirely in `src/charon/ports/agent_launch.py`. The bare path calls
`_acp_passthrough_env()` (default `include_keys=True`). Add `CHARON_GATEWAY_TOKEN` to the forwarded
set so it is carried on that path. Choose the placement so the invariant holds:

- **Forwarded** on the bare `charon work` acp path (`include_keys=True`), when set.
- **NOT force-injected** on the renderer / per-run-proxy path (`include_keys=False`): that path
  points the agent at an in-process proxy and supplies the proxy's own credential, so the standing
  gateway token must not bleed in there. (Putting it alongside `_ACP_KEY_PASSTHROUGH`, which
  `include_keys=False` already excludes, satisfies this cleanly — confirm by reading the two
  call sites.)
- The fence whitelist (`src/charon/fence.py` `_ENV_ALLOW`) stays **untouched** — the credential
  rides `passthrough_env` (merged over the scrubbed env at `adapters/acp.py:72`), not a fence hole.

Keep it agent-agnostic: forward the env var; do not hardcode opencode specifics.

## Acceptance
- `tests/test_agent_launch_routing.py` gains a test proving `CHARON_GATEWAY_TOKEN`, when set, IS
  present in the bare-path passthrough env (`_acp_passthrough_env()` / the env that the bare
  `AcpBackend` is built with) — so the spawned agent can authenticate to the standing gateway.
- A test proving it is **absent** when not set in the environment (no empty/placeholder injection).
- **Security regression guard (REQUIRED):** forwarding this ONE credential opens no general hole —
  an arbitrary `SECRET_*` (and any non-forwarded var) is still absent from the spawned child's env;
  only the gateway token (plus the pre-existing whitelisted vars/provider keys) crosses.
- A test (or assertion) that the renderer / `include_keys=False` path does NOT force-forward
  `CHARON_GATEWAY_TOKEN` (the proxy path owns its own credential) — mirror the existing seam test
  `test_agent_launch_pins_vid_at_the_seam_and_excludes_keys` (~lines 108-122).
- Existing `tests/test_fence.py` secret/escalation-leak tests stay GREEN unchanged.

## CONSTRAINTS
Own ONLY: `src/charon/ports/agent_launch.py`, `tests/test_agent_launch_routing.py`. Stdlib core
only; no `pip install -e`; no secrets committed. Gate GREEN every commit:
`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`.
Conventional commits; new behavior ships with its test in the same commit. Review note →
`docs/review-log/WORK-GATEWAY-WIRE.md` (per-ticket fragment; NEVER the shared REVIEW-LOG.md).
Open a DRAFT PR (base master), run `submit.sh WORK-GATEWAY-WIRE`, then STOP — never merge. If a fix
genuinely needs a file outside owns, STOP and `release.sh WORK-GATEWAY-WIRE` with the reason.

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
