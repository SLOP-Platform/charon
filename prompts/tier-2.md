Compile tiers INTO the gateway's existing pool machinery (DTC HARD REQ #2). Canonical tier
for this ticket: **high** (mapped to fleet `opus`). Depends on TIER-1 (merged): `config.py`
already exposes `load_tiers`/`tier_members`/`resolve_tier`/`set_tiers`. Read
`/home/stack/charon-private/fleet/DTC-tier-abstraction.md` §"Gateway alignment (HARD REQ #2)"
and §"Web-UI surface … backend API" FIRST, plus `src/charon/gateway.py`
(`load_config`, `_build_routes_and_pools` lines 77-104, `make_setup_handler` 190-248,
`_reload`/`apply_routes` 185-188).

GOAL: In `load_config`, compile `tiers.json.members` via the EXISTING
`_build_routes_and_pools` into `GatewayConfig.pools`/`model_ids` (pools.json wins on
collision); add a `make_setup_handler` `"tiers"` branch + `_reload`.

DESIGN ANCHORS (cite in your review note):
- Tiers live in `tiers.json`, NOT `pools.json` — the strict `pools.load_pools` /
  `router.from_charon_dir` path must NEVER see tier data (web-authored models have no `agent`
  field and would crash the ACP router). This ticket reads `tiers.json` via TIER-1's
  `config.load_tiers`, separate from the strict loader.
- After reading `models.json`/`pools.json`, also read tiers and feed `members` through the
  UNCHANGED `_build_routes_and_pools(registry, members, providers_cfg)`; merge resulting tier
  vids into `GatewayConfig.pools` and `model_ids`. Each tier is then published in `/v1/models`
  and fails over via the unchanged request loop (cools 429/402/503).
- PRECEDENCE: an explicit `pools.json` vid WINS on name collision (no surprise override).
- Within-tier order = free-first→`cost_rank` stable sort — already what
  `_build_routes_and_pools` does (mirrors `pools.py:91`); do NOT reimplement sorting.

BUILD:
1. src/charon/gateway.py — EXTEND in place:
   - In `load_config`: load `tiers.json` (via TIER-1 config API), compile members through
     `_build_routes_and_pools`, merge into pools/model_ids with pools.json precedence on
     collision. Absent `tiers.json` → no tier vids, behavior unchanged.
   - Add a `"tiers"` branch to `make_setup_handler` that calls `config.set_tiers(...)` then
     `_reload()` (recompiles tier pools into the live server via `apply_routes`).
2. tests/test_gateway_tiers.py — proven-red: tier members compile into `GatewayConfig.pools`
   + `model_ids`; pools.json vid wins on name collision; absent file → no tier vids / behavior
   unchanged; the `"tiers"` setup branch persists + reloads.

CONSTRAINTS: own ONLY the files in your board ticket's `owns:` line
(src/charon/gateway.py, tests/test_gateway_tiers.py) — nothing else. gateway.py already
exists: EDIT it. Import `config` (TIER-1) and reuse `_build_routes_and_pools`; do NOT edit
config.py or proxy_server.py. The POST allowlist + web fieldset belong to TIER-4 — do NOT
touch proxy_server.py. If your work needs a file outside `owns:`, STOP and run release.sh
with a one-line reason. Stdlib-only core. Gate green every commit (pytest, ruff,
mypy src tests, check_boundary, check_version). No secrets. Conventional commits. Write your
review note as `docs/review-log/TIER-2.md` (NEVER the shared `docs/REVIEW-LOG.md`). Commit
ALL work on your branch and STOP — do NOT push, do NOT open a PR, do NOT run submit.sh; the
launcher publishes after you exit.

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
