Close the highest-value gap both TIER-7 reviewers flagged: there is NO test that the engine's
`run_task(role=…)` actually routes the resolved tier vid to the gateway end-to-end. The existing
tests verify the renderer and the gateway in isolation, but the GLUE
(`config.resolve_tier(role)` → `gateway.load_config(state_dir).pools[tier_vid]` → per-run
`GatewayProxyServer` → `OpencodeRenderer`) is verified-by-reading only. The reviewers' concern:
"the suite could stay green while nothing routes" — if that glue regressed (vid not a pool key,
tiers.json/models.json mismatch), the dry-pool early-return fires and `run_task` returns
`{status:"exhausted"}` routing NOTHING, while all other tests still pass. Canonical tier: **med**
(fleet `sonnet`).

READ FIRST: `src/charon/api.py` (`run_task` role branch ~:99-160: resolve→load_config→pool→proxy→
renderer→result), `docs/adr/0014-agent-and-provider-agnostic-tier-routing.md`,
`src/charon/gateway.py` (`load_config`/`_tier_pools`/`_build_routes_and_pools`),
`src/charon/config.py` (`resolve_tier`/`tier_members`), and the capture pattern in
`tests/test_gateway_failover.py:19-31` (mock upstream appends `body.get("model")`).

BUILD — own ONLY `tests/test_run_task_routing.py` (NEW file, the only file you create/edit):
- Stand up a populated registry (models.json + tiers.json with a tier `high` whose members map to
  ≥1 real upstream) and a mock upstream using the `test_gateway_failover.py:19-31` capture.
- Drive `api.run_task(role="high", …)` (or the closest public entry that exercises the role branch)
  against it, with the opencode renderer + a stub ACP agent that performs one
  `/v1/chat/completions` POST to its configured base URL using its configured model id.
- ASSERT AT THE WIRE: the mock upstream `received` contains the tier vid's resolved upstream model
  (proving resolve_tier→load_config→pool→proxy→renderer all connected), NOT
  `{status:"exhausted"}`. Add a second assertion that a tiers.json/models.json MISMATCH (vid not a
  pool key) surfaces the exhausted/empty-pool result — so the test pins BOTH the happy path and the
  exact regression mode the reviewers named.
- Keep it hermetic (no network beyond the local mock; reuse existing test fixtures/helpers).

If exercising `run_task` requires touching a non-test file, STOP and run release.sh with a reason
(this ticket is test-only by design; do NOT edit src/).

CONSTRAINTS: own ONLY `tests/test_run_task_routing.py`. Gate green (pytest, ruff, mypy, check_*).
Conventional commits. Review note → `docs/review-log/HARD1.md`. Commit ALL work and STOP — no
push / PR / submit.sh.

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
