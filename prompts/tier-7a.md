Make the work-engine route a tier through the gateway's EXISTING failover, agent- & provider-
AGNOSTICALLY. This is the rebuild of the failed TIER-7 (do NOT repeat the inert `ANTHROPIC_MODEL`
env var, and do NOT hardcode the tier vid into opencode's config — both couple/route wrongly).
Canonical tier for this ticket: **high** (fleet `opus`).

READ FIRST: `docs/adr/0014-agent-and-provider-agnostic-tier-routing.md` (the full decision, D1–D6
+ Consequences). This ticket implements ADR-0014 **Ticket A** (Phase A). Also read
`src/charon/api.py` (the opencode coupling: `_split_model` :247-255, `_acp_for_proxy` :258-277,
`_pool_routes` :280-291, `_start_proxy_acp` :316-350, `_ACP_KEY_PASSTHROUGH` :239,
`_acp_passthrough_env` :242-244 / call site :372-373, and the retiring `select_live_entry` path
:166-177), `src/charon/adapters/acp.py` (`dispatch` receives `tier` at :141 and ignores it;
EXHAUSTED map :162-163), `src/charon/proxy_server.py` (`pools=`/`model_ids=` kwargs :620-621,
`chain_for`/`order_by_cooldown` :677-686, `status_snapshot` :738, failover events :651/:727,
chain-exhausted 502 :489-492), `src/charon/gateway.py` (`_build_routes_and_pools` :77, free-first
ordering :92-99), and `tests/test_gateway_failover.py` (:19-31 capture pattern to reuse).

GOAL: the engine resolves a **tier vid** for each dispatch and builds the per-run
`GatewayProxyServer` with `pools={tier_vid:[...]}` + `model_ids=[tier_vid]`; the agent's requested
model id IS the tier vid; the gateway resolves vid→pool→provider and fails over. The engine does
NO provider selection of its own. Opencode's launch config moves behind a renderer seam so the
engine never names opencode.

BUILD (own ONLY these files):
1. `src/charon/ports/agent_launch.py` (NEW) — define `AgentLaunch` (the rendered launch contract:
   argv, passthrough env, `requested_model`) + a `render(...)` seam + `OpencodeRenderer` (move the
   EXISTING opencode blob here verbatim, but `requested_model` = the tier vid and `baseURL` = the
   per-run gateway). SHIP ONLY THE OPENCODE RENDERER (ADR-0014 D3/B1 — no generic/claude-code
   renderer on spec; extra renderers are gated on a live `charon doctor` probe, out of scope here).
   Every renderer forces `include_keys=False` as an INVARIANT (ADR-0014 D4 — the proxy holds the
   key; no real provider key reaches the agent).
2. `src/charon/api.py` — relocate the opencode blob behind the seam; build the per-run pool via
   `gateway._build_routes_and_pools` (free-first/cost-ranked), NOT `_pool_routes` (delete it;
   ADR-0014 D2). Construct the per-run `GatewayProxyServer(pools={tier_vid:[...]}, model_ids=
   [tier_vid])`. **RE-HOME the retired `select_live_entry` contract (ADR-0014 Consequences, B4):**
   a dry pool must still surface `{status:"exhausted", note:"…"}` and the `failover` result must
   still carry the served-model + skipped-provider list — translate them from the gateway's
   `status_snapshot()` / failover events; a whole-chain 502 maps to `OutcomeStatus.EXHAUSTED`. Do
   NOT drop these keys — downstream readers depend on them.
3. `src/charon/adapters/acp.py` — resolve the tier vid PER-DISPATCH from the `tier` param (:141)
   and request it (ADR-0014 D5). Keep the dispatch body otherwise unchanged. Phase A runs one warm
   backend per run but keys its pool by the resolved tier vid; per-stage backend lifecycle is
   Phase B (a SEPARATE later ticket) — do NOT build it here, but do NOT bake in assumptions that
   block it (tier resolved per-dispatch; backend-selection-by-tier left to `router.route`).
4. `tests/test_agent_launch_routing.py` (NEW) — the wire contract that proves agnosticism:
   - Reuse the `tests/test_gateway_failover.py:19-31` mock-upstream capture (`received.append(
     body.get("model"))`), two providers in one pool (a free/low-cost-rank + a paid).
   - Build the per-run `GatewayProxyServer(pools=…, model_ids=[tier_vid])` from a registry via
     `gateway._build_routes_and_pools` (asserts free-first ordering, D2).
   - Assert ON THE `AgentLaunch` (the agnostic seam, NOT opencode internals): `launch.requested_
     model == tier_vid`; the rendered env contains NO `_ACP_KEY_PASSTHROUGH` key (include_keys=
     False).
   - Drive a request with the rendered model id + proxy baseURL (a tiny HTTP client standing in
     for the agent) and assert via `received`: the FREE provider got the request first; on a
     forced 429 the PAID provider captured the retry (inherited gateway failover, no engine-side
     selection); the failed provider appears in the re-homed `failover`/skipped list (B4).
   - The assertions pin the VID AT THE WIRE + the seam output, never an opencode-specific config
     shape — any renderer honoring the seam satisfies them.

CONSTRAINTS: own ONLY the 4 files above. Import gateway/proxy_server/config; do NOT edit them.
Privileged core stays stdlib-only (no new deps). Gate green every commit (pytest, ruff, mypy
src/charon, check_boundary, check_version, check_decisions). Conventional commits. Write your
review note as `docs/review-log/E11.md` covering the 3 lenses ADR-0014 names: coupling-inventory
completeness · contract re-homing (B4) · over-claimed modularity (only opencode ships). NEVER edit
the shared `docs/REVIEW-LOG.md`. Commit ALL work on your branch and STOP — do NOT push, do NOT
open a PR, do NOT run submit.sh; the launcher publishes after you exit. If your work needs a file
outside the owns list, STOP and run release.sh with a one-line reason (this is exactly what the
prior attempt failed to do).

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
