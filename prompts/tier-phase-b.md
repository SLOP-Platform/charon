TIER-7 Phase B (ADR-0014 D6): make multi-tier decompose runs route each stage to the RIGHT model,
and clean up the dead code Phase A left. Phase A (merged) routes ONE tier per run; a decompose run
whose stages span tiers currently collapses to one model. Canonical tier: **high** (fleet `opus`).
THIS IS THE DEFERRED MULTI-TIER FEATURE — build only when scheduled.

READ FIRST: `docs/adr/0014-agent-and-provider-agnostic-tier-routing.md` (D5/D6 — the per-dispatch
vid + backend-selection-by-tier extension point), `src/charon/router.py` (`route` :70-84 — today
returns `candidates[0]`, IGNORING the resolved tier), `src/charon/adapters/acp.py` (warm agent
started once at construction, `:63-66`; `dispatch` receives `tier` :141), `src/charon/api.py`
(`run_task` role branch + warm backend construction), `src/charon/decompose.py` (stages span
task-classes→tiers, :48-56,129), and `docs/decisions` D010 (warm-pool default).

BUILD (own: router.py, adapters/acp.py, api.py, failover.py, tests/test_failover.py,
tests/test_tier_lifecycle.py):
1. **Backend selection by tier** — `StaticRouter.route` (router.py:84) must select the backend for
   the dispatch's `tier`, not blindly `candidates[0]`.
2. **Warm-agent-per-tier** — maintain a `{tier: backend}` warm map (honor D010: reuse subprocess;
   ephemeral only for untrusted/L2+). On a stage whose tier differs, route to that tier's warm
   agent (or relaunch-on-tier-change as the fallback). A single-tier run stays the `len==1` special
   case of the map — Phase A's behavior must be preserved exactly for single-tier runs.
3. **Delete the orphaned dead code**: `failover.select_live_entry` has no caller in `src/` post
   Phase A (only `tests/test_failover.py` references it). Remove the function from `failover.py` and
   its test(s) from `test_failover.py`. FIRST verify `api.py` references it only in COMMENTS (not a
   live import/call) — if there is a live import, leave it and note it (api.py edits are in your
   owns here, so you MAY remove a dead import too, but do not change routing behavior).
4. **Tests** (tests/test_tier_lifecycle.py, new): a multi-tier decompose run routes each stage's
   dispatch to its tier's model (assert at the wire, reuse test_gateway_failover.py:19-31 capture);
   a single-tier run is unchanged; warm-agent reuse vs relaunch behaves per D010.

NOTE: the run_task routing integration test (HARD1, a dependency of this ticket) must be GREEN on
master first — it guards that your changes don't regress single-tier routing.

CONSTRAINTS: own ONLY the listed files. Stdlib core only. Gate green every commit (pytest, ruff,
mypy src tests, check_boundary, check_version, check_decisions). Conventional commits. Review note
→ `docs/review-log/TIER7B.md`. Commit ALL work and STOP — no push / PR / submit.sh. If a fix needs
a file outside owns, STOP and run release.sh with a reason.

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
