# CWD-CONFIG — write per-run opencode.json to cwd instead of OPENCODE_CONFIG_CONTENT env var

## Dependencies & sequence
**depends_on: NONE — Wave 1 (unblocks ORCH-ROUTE).** Owns `agent_launch.py` + its test.
ORCH-ROUTE depends_on CWD-CONFIG (transitive: CWD-CONFIG → ORCH-ROUTE). Run BEFORE ORCH-ROUTE.
No other ticket owns these files. Safe to claim immediately.

## Why
Empirical test 2026-06-30 (see `docs/review-log/ORCH-ROUTE-STEP-0.md`) proved:

- `OPENCODE_CONFIG_CONTENT` env var is **NOT honored** by opencode 1.17.11 `acp` mode
- **cwd `opencode.json` IS honored** — the agent resolves providers/models from a per-run
  `opencode.json` in its working directory

The current `OpencodeRenderer.render()` (`agent_launch.py:104-120`) injects the per-run
config entirely via `OPENCODE_CONFIG_CONTENT`. Because ACP ignores this env var, the agent
falls through to its global config — breaking per-run proxy routing.

## What to build
Change `OpencodeRenderer.render()` to write the per-run provider config as `opencode.json`
in the cwd alongside the env var. The ACP subprocess already runs with `cwd=str(worktree)`
(`acp.py:102-104`). Each worktree is a per-run, per-unit directory — zero race risk, no
global-config mutation.

**Implementation (all in `src/charon/ports/agent_launch.py`):**

1. In `OpencodeRenderer.render()`, after building the `cfg` dict, write it as JSON to
   `<cwd>/opencode.json` (the `render()` method receives `proxy_url`; derive cwd from the
   current working directory or accept it as a parameter — the caller sets it).

   The cleanest approach: add an optional `cwd: str | None = None` parameter to `render()`
   (and the `AgentRenderer.render()` signature). The caller (`AcpBackend._start()`) already
   has the worktree path — thread it through.

2. **Keep the `OPENCODE_CONFIG_CONTENT` env var too** — belt and suspenders. If a future
   opencode release starts honoring it, both paths work. The cwd file is the primary
   mechanism; the env var is harmless redundancy.

   Actually, do NOT keep it — it's untested dead code and could mask regressions. Remove
   `OPENCODE_CONFIG_CONTENT` from `render()` entirely. The only config injection is via
   cwd `opencode.json`.

3. Update `_acp_passthrough_env()` docs — note that `OPENCODE_CONFIG_CONTENT` is no longer
   the injection mechanism; cwd `opencode.json` is.

**Test updates (`tests/test_agent_launch_routing.py`):**

4. Update `test_agent_launch_pins_vid_at_the_seam_and_excludes_keys`: assert the launch
   includes a cwd that would receive the `opencode.json`, and that `OPENCODE_CONFIG_CONTENT`
   is NOT in the env.

5. Add a new test `test_renderer_writes_cwd_opencode_json` that:
   - Calls `render()` with a cwd and proxy URL
   - Asserts `opencode.json` was written to cwd with correct provider/model config
   - The written config's baseURL points at the proxy URL
   - The written config's model is the tier vid

6. Update the stub agent in `test_run_task_routing.py` to read from `opencode.json` in cwd
   instead of (or in addition to) `OPENCODE_CONFIG_CONTENT` env var. This mirrors the real
   opencode behavior.

7. `test_tier_routes_through_gateway_failover_no_engine_selection` — the cwd passed via
   `render()` must match the worktree the AcpBackend will use. Add an assertion.

## Acceptance
- All existing `test_agent_launch_routing.py` tests pass (updated for new mechanism)
- New test proves cwd `opencode.json` is written correctly
- `test_run_task_routing.py` stub reads from cwd `opencode.json`
- Agent NEVER carries a real provider key (D4 invariant intact)
- Gate GREEN: `PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`

## CONSTRAINTS
Stdlib core only. Conventional commits. Review note → `docs/review-log/CWD-CONFIG.md`.

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
