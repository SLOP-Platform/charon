# Charon Fleet — Session Handoff (2026-07-03T02:28:07Z)

> **This is THE canonical handoff file.** Previous handoffs (HANDOFF.md,
> HANDOFF-CONTINUE.md, SESSION-RESTART.md) are superseded. There is exactly
> ONE handoff file per session end: `SESSION-HANDOFF.md`.

---

## Bootstrap (copy-paste into next session)

Read `/home/stack/charon-private/fleet/SESSION-HANDOFF.md` fully, then run
`bash /home/stack/charon-private/fleet/status.sh && bash /home/stack/charon-private/fleet/validate_board.sh`,
check the board for claimed names, register with an unused Jedi name + `repo="charon"`, then go.

---

## Auto-generated state (from `handoff.sh` run at 2026-07-03T02:28:07Z)

### Git
```
feat/prod-install

?? docs/review-log/ATC-AUDIT.md

--- last 10 commits ---
ffcf02b feat: TIER-RECS Phase B + UX-POLISH batch + sandbox reload fix
1e7b003 feat(PROD-INSTALL): add charon update subcommand + doctor --gateway preflight
ec20f02 feat(WCI-MVP): static reconciler + depth pre-sort
c9fedf5 feat: Batch 1 — console mgmt, obs capture, client connect, ADR-0015, routing proxy, DTC infra, OBS-UI, fallback provider
b430ee8 Merge pull request #76 from SLOP-Platform/feat/model-discovery
168036e chore(MODEL-DISCOVERY): fix line-too-long (ruff E501)
aee120d fix(MODEL-DISCOVERY): adversarial review fixes — model_meta pass in api.py, missing review fragment
3399fb8 feat: enrich /v1/models with model metadata, exclude pool IDs
ad9d276 Merge pull request #67 from SLOP-Platform/feat/test-ephemeral-ports
778bc0d Merge pull request #75 from SLOP-Platform/feat/secret-scan-envvar-fp
```
### Open PRs
```
[]
```
### Gate
```
........................................................................ [ 94%]
..........................................                               [100%]
834 passed in 72.01s (0:01:12)
All checks passed!
```
### Board
```

  CHARON-FLEET STATUS @ 2026-07-03T02:29:24Z

  DROIDS (live tabs)        TIER    UPTIME    WORKING-ON
  (no droid tabs running)

  BOARD
  ID     TIER    STATE     BRANCH                 HELD-BY / NOTE
  BRIDGE-HARDEN strong  DONE      feat/bridge-harden     -
  CI1    sonnet  DONE      feat/ci-runner-var     -
  CLIENT-CONNECT opus    DONE      feat/client-connect    -
  CWD-CONFIG frontier DONE      feat/cwd-config        -
  DEP1   sonnet  DONE      feat/httpx-test-dep    -
  DOCKER-INSTALL opus    DONE      feat/docker-install    -
  DOCS-TWO-MODE sonnet  DONE      feat/docs-two-mode     -
  E0     sonnet  DONE      feat/engine-boundary-guard -
  E1     opus    DONE      feat/engine-board-claim -
  E10    opus    DONE      feat/aimd-capacity     -
  E2     opus    DONE      feat/engine-scheduler  -
  E3     sonnet  DONE      feat/engine-scanner-matrix -
  E4     opus    DONE      feat/intake-phase1     -
  E6     opus    DONE      feat/engine-integration -
  E7     sonnet  DONE      feat/engine-docs       -
  E8     opus    DONE      feat/auto-land         -
  E9     opus    DONE      feat/intake-phase2     -
  FB1    sonnet  DONE      feat/fix-boundary-relimports -
  FB3    sonnet  DONE      feat/review-log-fragments -
  FB4    opus    DONE      feat/fix-engine-concurrency -
  FB5    sonnet  DONE      feat/ci-hardening      -
  FB6    sonnet  DONE      feat/decisions-lint    -
  FR1    sonnet  DONE      feat/first-run-polish  -
  HARD1  sonnet  DONE      feat/run-task-routing-test -
  INTAKE1 opus    DONE      feat/intake-import     -
  N1     opus    DONE      feat/per-unit-worktree -
  N2     opus    DONE      feat/charon-land       -
  N4     sonnet  DONE      feat/validator         -
  N5     sonnet  DONE      feat/windows-exe       -
  ORCH-ROUTE frontier DONE      feat/orch-route        -
  PREFLIGHT n/a     DONE      n/a                    -
  PROD-INSTALL frontier DONE      feat/prod-install-bootstrap -
  RELEASE-SMOKE-FIX sonnet  DONE      feat/release-smoke-fix -
  S1     sonnet  DONE      feat/sandbox-policy    -
  SECRET-SCAN-ENVVAR-FP sonnet  DONE      feat/secret-scan-envvar-fp -
  SETUP-UX-A opus    DONE      feat/setup-ux-a        -
  T7     opus    DONE      feat/l3-unattended     -
  T8     sonnet  DONE      feat/consensus-breaker -
  TEST-PORT-FLAKE sonnet  DONE      feat/test-ephemeral-ports -
  TIER-1 opus    DONE      feat/tier-config-store -
  TIER-2 opus    DONE      feat/gateway-tier-pools -
  TIER-3 sonnet  DONE      feat/cli-tier          -
  TIER-4 opus    DONE      feat/tier-web-ui       -
  TIER-5 opus    DONE      feat/fleet-tier-claim  -
  TIER-6 opus    DONE      feat/fleet-tier-launch -
  TIER-7 opus    DONE      feat/agnostic-tier-routing -
  TIER7B-FOLLOWUP sonnet  DONE      feat/tier7b-followup   -
  TIER7B opus    DONE      feat/tier-phase-b-multitier -
  WCI-FOLLOWON frontier DONE      feat/wci-semantic-slice -
  WORK-AGENT-BEARINGS sonnet  DONE      feat/work-agent-bearings -
  WORK-BEARINGS-WORKPATH opus    DONE      feat/work-bearings-workpath -
  WORK-GATEWAY-WIRE opus    DONE      feat/work-gateway-cred -
  WORK-LAND-PR opus    DONE      feat/work-land-pr      -
  WORK-OBSERVABILITY opus    DONE      feat/work-observability -
  WORKTREE-ADD-FORCE sonnet  DONE      feat/worktree-add-force -

  OPEN PRs (draft → operator merges)
  (CI per PR:  gh pr checks <n> --repo SLOP-Platform/charon)

  SUMMARY  droids:0   ready:0  claimed:0  PR-open:0  done:55  blocked:0

  (token/usage is NOT faked here — see Claude's own /usage. board.sh = the quick view.)

```
### Board validation
```
== validate_board ==
  INFO owns hand-off (all-done, ok): .github/workflows/ci.yml <- CI1 FB5
  INFO owns hand-off (all-done, ok): .github/workflows/heavy.yml <- CI1 FB5
  INFO owns hand-off (all-done, ok): .github/workflows/release.yml <- CI1 FB5 RELEASE-SMOKE-FIX
  INFO owns hand-off (all-done, ok): .github/workflows/windows-exe.yml <- FB5 N5
  INFO owns hand-off (all-done, ok): README.md <- DOCKER-INSTALL DOCS-TWO-MODE E7 FR1 PROD-INSTALL
  INFO owns hand-off (all-done, ok): cli.py <- E6 N2 S1
  INFO owns hand-off (all-done, ok): config.py <- E8 S1
  INFO owns hand-off (all-done, ok): coordinator.py <- N1 T7
  INFO owns hand-off (all-done, ok): decompose.py <- E9 N4
  INFO owns hand-off (all-done, ok): docs/DECISIONS.md <- CI1 FB6
  INFO owns hand-off (all-done, ok): engine/capacity.py <- E10 E2
  INFO owns hand-off (all-done, ok): engine/claim.py <- E1 FB4
  INFO owns hand-off (all-done, ok): engine/scheduler.py <- E2 FB4
  INFO owns hand-off (all-done, ok): fence.py <- S1 T7
  INFO owns hand-off (all-done, ok): intake.py <- E4 E9
  INFO owns hand-off (all-done, ok): land.py <- E3 E8 N2
  INFO owns hand-off (all-done, ok): pyproject.toml <- DEP1 FB5 N5
  INFO owns hand-off (all-done, ok): src/charon/adapters/acp.py <- TIER-7 TIER7B WORK-AGENT-BEARINGS
  INFO owns hand-off (all-done, ok): src/charon/api.py <- ORCH-ROUTE TIER-7 TIER7B-FOLLOWUP TIER7B WORK-AGENT-BEARINGS
  INFO owns hand-off (all-done, ok): src/charon/cli.py <- CLIENT-CONNECT FR1 INTAKE1 PROD-INSTALL SETUP-UX-A TIER-3 WORK-BEARINGS-WORKPATH WORK-LAND-PR WORK-OBSERVABILITY
  INFO owns hand-off (all-done, ok): src/charon/engine/board.py <- WCI-FOLLOWON WORK-BEARINGS-WORKPATH
  INFO owns hand-off (all-done, ok): src/charon/engine/scheduler.py <- WORK-BEARINGS-WORKPATH WORK-OBSERVABILITY
  INFO owns hand-off (all-done, ok): src/charon/intake.py <- INTAKE1 WCI-FOLLOWON WORK-AGENT-BEARINGS
  INFO owns hand-off (all-done, ok): src/charon/ports/agent_launch.py <- CWD-CONFIG ORCH-ROUTE TIER-7 WORK-GATEWAY-WIRE
  INFO owns hand-off (all-done, ok): src/charon/proxy_server.py <- FR1 TIER-4
  INFO owns hand-off (all-done, ok): tests/test_agent_launch_routing.py <- CWD-CONFIG ORCH-ROUTE TIER-7 WORK-GATEWAY-WIRE
  INFO owns hand-off (all-done, ok): tests/test_boundary.py <- E0 FB1
  INFO owns hand-off (all-done, ok): tests/test_claim.py <- E1 FB4
  INFO owns hand-off (all-done, ok): tests/test_cli.py <- FR1 INTAKE1 WORK-LAND-PR
  INFO owns hand-off (all-done, ok): tests/test_gateway_tiers.py <- TEST-PORT-FLAKE TIER-2
  INFO owns hand-off (all-done, ok): tests/test_intake.py <- E4 INTAKE1 WORK-AGENT-BEARINGS
  INFO owns hand-off (all-done, ok): tests/test_scheduler.py <- E2 FB4
  INFO owns hand-off (all-done, ok): tests/test_tier_lifecycle.py <- TIER7B-FOLLOWUP TIER7B
  INFO owns hand-off (all-done, ok): tests/test_work_bearings.py <- WORK-AGENT-BEARINGS WORK-BEARINGS-WORKPATH
  INFO owns hand-off (all-done, ok): tools/check_boundary.py <- E0 FB1 FB6
  INFO owns hand-off (all-done, ok): validate.py <- E6 N4
  WCI-ADVISORY semantic: prompt-intent contradiction / hidden coupling is NOT machine-checked — eyeball overlapping or dep-linked tickets by hand.
  RED  bad-dep: WCI-FOLLOWON depends_on 'WCI' (no such ticket)
  RED  orphan-marker: state/done/DTC-7 matches no board ticket
  RED  orphan-marker: state/done/CONNECT-OMP-WSL matches no board ticket
  RED  orphan-marker: state/done/DTC-3 matches no board ticket
  RED  orphan-marker: state/done/SETUP-KEY-UX matches no board ticket
  RED  orphan-marker: state/done/MODEL-DISCOVERY matches no board ticket
  RED  orphan-marker: state/done/ADR-0015 matches no board ticket
  RED  orphan-marker: state/done/OBS-UI matches no board ticket
  RED  orphan-marker: state/done/WCI matches no board ticket
  RED  orphan-marker: state/done/DTC-5 matches no board ticket
  RED  orphan-marker: state/done/DTC-2 matches no board ticket
  RED  orphan-marker: state/done/DTC-4 matches no board ticket
  RED  orphan-marker: state/done/CONSOLE-PROVIDER-MGMT matches no board ticket
  RED  orphan-marker: state/done/DTC-8-TEST-PATTERNS matches no board ticket
  RED  orphan-marker: state/done/PUBLIC-CLEAN-LINT matches no board ticket
  RED  orphan-marker: state/done/OBS-CAPTURE matches no board ticket
  RED  orphan-marker: state/done/DTC-1 matches no board ticket
  RED  orphan-marker: state/done/CLIENT-CONNECT-GUI matches no board ticket
  RED  orphan-marker: state/done/FALLBACK-PROVIDER matches no board ticket
  RED  19 issue(s) — fix before launching
```
### Parked tickets
```
ADR-0015.md.parked
ATC.md.parked
BRIDGE-RELAYFEATURES.md.parked
CLIENT-CONNECT-GUI.md.parked
CONNECT-OMP-WSL.md.parked
CONSOLE-PROVIDER-MGMT.md.parked
CWD-CONFIG-VERIFY.md.parked
DOGFOOD.md.parked
DS-PLAN-REVIEW.md.parked
DSGN-WCI-PROOF.md.parked
DSGN-WRITEBACK.md.parked
DTC-1.md.parked
DTC-2.md.parked
DTC-3.md.parked
DTC-4.md.parked
DTC-5.md.parked
DTC-6.md.parked
DTC-7.md.parked
DTC-8-TEST-PATTERNS.md.parked
FALLBACK-PROVIDER.md.parked
MODEL-DISCOVERY.md.parked
OBS-CAPTURE.md.parked
OBS-UI.md.parked
OHMYPI-ASSESS.md.parked
PROVIDER-FLATRATE.md.parked
PUBLIC-CLEAN-LINT.md.parked
SETUP-KEY-UX.md.parked
TIER-RECS.md.parked
UX-POLISH.md.parked
WCI.md.parked
```
### Live tickets (.md, not parked)
```
BRIDGE-HARDEN.md  tier=strong  depends_on=
CI1.md  tier=sonnet  depends_on=
CLIENT-CONNECT.md  tier=opus  depends_on=
CWD-CONFIG.md  tier=frontier  depends_on=
DEP1.md  tier=sonnet  depends_on=
DOCKER-INSTALL.md  tier=opus  depends_on=
DOCS-TWO-MODE.md  tier=sonnet  depends_on=
E0.md  tier=sonnet  depends_on=
E1.md  tier=opus  depends_on=E0
E10.md  tier=opus  depends_on=E2
E2.md  tier=opus  depends_on=E1
E3.md  tier=sonnet  depends_on=E2
E4.md  tier=opus  depends_on=E2
E6.md  tier=opus  depends_on=E4
E7.md  tier=sonnet  depends_on=E9
E8.md  tier=opus  depends_on=E6, FB4
E9.md  tier=opus  depends_on=E8
FB1.md  tier=sonnet  depends_on=
FB3.md  tier=sonnet  depends_on=
FB4.md  tier=opus  depends_on=
FB5.md  tier=sonnet  depends_on=FB6
FB6.md  tier=sonnet  depends_on=
FR1.md  tier=sonnet  depends_on=
HARD1.md  tier=sonnet  depends_on=
INTAKE1.md  tier=opus  depends_on=
N1.md  tier=opus  depends_on=
N2.md  tier=opus  depends_on=
N4.md  tier=sonnet  depends_on=N2
N5.md  tier=sonnet  depends_on=
ORCH-ROUTE.md  tier=frontier  depends_on=CWD-CONFIG
PREFLIGHT.md  tier=n/a  depends_on=
PROD-INSTALL.md  tier=frontier  depends_on=
RELEASE-SMOKE-FIX.md  tier=sonnet  depends_on=
S1.md  tier=sonnet  depends_on=
SECRET-SCAN-ENVVAR-FP.md  tier=sonnet  depends_on=
SETUP-UX-A.md  tier=opus  depends_on=
T7.md  tier=opus  depends_on=N1
T8.md  tier=sonnet  depends_on=
TEST-PORT-FLAKE.md  tier=sonnet  depends_on=
TIER-1.md  tier=opus  depends_on=
TIER-2.md  tier=opus  depends_on=TIER-1
TIER-3.md  tier=sonnet  depends_on=TIER-1
TIER-4.md  tier=opus  depends_on=TIER-2
TIER-5.md  tier=opus  depends_on=TIER-3
TIER-6.md  tier=opus  depends_on=TIER-3
TIER-7.md  tier=opus  depends_on=
TIER7B-FOLLOWUP.md  tier=sonnet  depends_on=
TIER7B.md  tier=opus  depends_on=HARD1
WCI-FOLLOWON.md  tier=frontier  depends_on=WCI
WORK-AGENT-BEARINGS.md  tier=sonnet  depends_on=
WORK-BEARINGS-WORKPATH.md  tier=opus  depends_on=WORK-LAND-PR
WORK-GATEWAY-WIRE.md  tier=opus  depends_on=
WORK-LAND-PR.md  tier=opus  depends_on=
WORK-OBSERVABILITY.md  tier=opus  depends_on=CLIENT-CONNECT
WORKTREE-ADD-FORCE.md  tier=sonnet  depends_on=
```

---

## Human analysis

**Session name:** yoda
**Session model:** deepseek-v4-pro
**Consensus partners:** obi-wan-kenobi, mace-windu

### What was done this session

**T0: Provider failover — NOT YET BUILT.** Coordination + review consumed entire session.
The actual failover code is pending. See "What must happen next."

**Built:**
1. **Bridge daemon** (`~/.config/opencode/session-bridge/daemon.py`): Unix socket listener at
   `~/.charon/bridge.sock`, SQLite-backed, 7 MCP tools (register/board/update/unregister/claim/
   release/nudge), SIGHUP graceful restart, graduated purge, PID liveness check. Tested: init,
   register, board, nudge, update all working via `nc -U` to the socket.

2. **Bridge TTL fix** (`server.py:24`): env-var configurable `SESSION_BRIDGE_TTL`, PID liveness
   check in `_purge_stale()`, graduated response (nudge→escalate→purge).

3. **`charon models import --all`** (uncommitted on `feat/prod-install`): iterates all preset +
   custom providers with keys set, imports models in bulk. Mypy/ruff clean. Help text shows
   `--all`. NOTE: first implementation lost to PR #78 merge collision; recovered.

4. **Cost tracking pipeline** (committed `bb75206` on `feat/global-fallback-provider`, pushed):
   upstream pricing capture → model registry → `/v1/models` → opencode config `cost` field.
   876 passed, all gates green.

5. **AGENTS.md fix**: 300s→600s TTL doc bug (3 instances). File is gitignored, local only.

**Reviewed (adversarial):**
- `bridge-update-nudge-return`: APPROVED (2 CONCERN — yoda + obi-wan)
- `CROSS-SESSION-REVIEW-PROTOCOL.md`: REJECTED → FIXED → ACCEPTED
- `BRIDGE-DAEMON-PROPOSAL.md`: CONCERN → FIXED → APPROVED (all 3 findings resolved)
- `PROPOSAL-1-COST-AWARE-ROUTING.md`: APPROVED (15 findings addressed across yoda + obi-wan)
- `PROPOSAL-2-SESSION-COMMUNICATION.md`: REJECTED (blocking: subagent timeout) → FIXED → APPROVED

**Tickets created:**
- `BRIDGE-HARDEN` (parked): 5 bridge improvements from mediastack droid patterns
- `PROVIDER-FLATRATE` (parked): featherless.ai + DeepInfra + Cerebras presets
- `BRIDGE-RELAYFEATURES` (parked): 6 RelayFreeLLM features + 3 transformative gaps

**Docs written:**
- `BRIDGE-IMPROVEMENT-PLAN.md`: bridge improvement roadmap
- `EVAL-RelayFreeLLM.md`: relay comparison + reusable evaluation template
- Provider research: featherless.ai ✓, synthetic.net ✗, useapiary.com ✗

### Key findings / decisions

**Critical: billable billing failure.** Operator hit "Insufficient balance" on opencode
sessions. Gateway did NOT fail over. Root causes:
1. OpenCode returns 401 for everything (billing, bad key, bad model) — `_EXHAUSTION_STATUSES = {429, 402, 503}` never matches 401
2. No pools/fallback configured — `pools.json` + `fallback.json` + `providers.json` all empty
3. No API keys for fallback providers

**Three-session consensus reached:**
- bridge-nudge: APPROVED
- cross-session-protocol: ACCEPTED (after fixes)
- bridge-daemon: APPROVED (after fixes)
- File division: ALL AGREE — yoda=failover/proxy/gateway/config/routing/coordinator, obi-wan=cli/connect/secrets/gitleaks/recommend/intake, mace-windu=new modules (cache, guardrails, observability, response_normalizer, request_inspector, quality_scorer, speculative_execution, consensus, virtual_keys, policy_router, session_affinity) + tests + wiring after yoda lands. ZERO collision.

**PROP-1 and PROP-2 both APPROVED** after all 15 review findings addressed.

**Bridge daemon architecture:** Single daemon process replacing 4 per-session server.py instances.
Fixes everything: stale code, lost nudges, race conditions, inconsistent state. Deploy via: start
daemon, update opencode MCP config to proxy.py, restart sessions.

**Session-bridge usage pattern (proven today):**
1. Register immediately: `session-bridge_register(session_id="<jedi>", name="<work>", repo="charon")`
2. Check board before any work: `session-bridge_board(repo="charon")` — includes liveness refresh
3. Before subagent dispatch: `session-bridge_update(status="in-progress", busy="subagent")` — extends TTL to 1800s
4. After subagent returns: `session-bridge_update(status="in-progress", busy=null)` — restores 600s TTL
5. Heartbeat every 2-3 min: `session-bridge_update(status="in-progress")`
6. During coordination: poll `board()` every 30s
7. Communicate via blockers field (plain text) or nudge tool (structured — post daemon deploy)

### What must happen next (in priority order)

**1. T0 FAILOVER — BUILD IMMEDIATELY. This is the #1 priority. Operator hit billing failure
and work stopped. Files owned: `src/charon/proxy.py`, `src/charon/proxy_server.py`,
`src/charon/gateway.py`, `src/charon/config.py`, `src/charon/cli.py`.**

Package A — Expand exhaustion detection (`proxy.py`):
- Add `_is_billing_error(response_body, status_code)` — inspects response JSON for
  patterns: "insufficient_balance", "insufficient quota", "billing", "out of funds"
- Extend `classify()` to detect billing errors in the response body, not just HTTP status
- Add `EXHAUSTION_BODY_PATTERNS = ["insufficient_balance", "insufficient quota", "billing",
  "out of funds", "payment required", "credits exhausted"]`

Package B — Fix OpenCode 401 false-negative (`proxy.py`):
- OpenCode returns 401 for billing. `_EXHAUSTION_STATUSES = {429, 402, 503}` never matches.
- When status=401 and body contains billing patterns, treat as exhausted (fail over).
- When status=401 and body contains "invalid key" / "unauthorized" / "authentication",
  do NOT fail over (auth error, not billing).
- Add `_is_auth_error()` to distinguish: 401 + auth patterns → return immediately.
  401 + billing patterns → fail over.
- Test: add test case for OpenCode billing response format.

Package C — Pool/fallback auto-config (`cli.py`, `gateway.py`, `config.py`):
- `charon doctor --gateway` should flag "no pools configured = no failover" as a WARNING
- `charon setup` should offer to create a sensible default pool from imported models
- Add `_missing_failover_chain()` check to doctor: if pools.json + fallback.json are empty,
  print actionable guidance

Package D — Probe provider error codes (new `tools/probe_provider_errors.py`):
- Catalog what HTTP status + body pattern every provider returns for billing/rate-limit/
  model-not-found/auth failures
- Run `charon models import <provider>` first to populate keys, then probe each provider
- Write `~/.charon/provider_errors.json` with per-provider error signatures
- Goal: feed Package A with concrete pattern lists per provider

**Gate command for all work:**
```
PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py
```

**2. Commit `--all` import:** code is on disk (`feat/prod-install`), gate green, needs commit+push.

**3. Cost tracking rebase:** commit `bb75206` on `feat/global-fallback-provider` needs rebase onto
master. PR #79-#81 landed independently.

### Collision matrix

| File | Owner (live) | Owner (next-yoda) |
|---|---|---|
| `src/charon/proxy.py` | none | yoda — T0 packages A+B+D |
| `src/charon/proxy_server.py` | none | yoda — T0 packages A+B+C |
| `src/charon/gateway.py` | none | yoda — T0 package C |
| `src/charon/config.py` | none | yoda — T0 package C |
| `src/charon/cli.py` | obi-wan (ATC fixes) | yoda — T0 package C (doctor check only) + obi-wan for CLI fixes |

**Note:** yoda's `cli.py` change for T0-C is a single doctor warning addition — low collision risk
with obi-wan's ATC CLI fixes. Coordinate on the bridge.

### Open questions / Blockers

- **Bridge daemon NOT deployed.** The daemon is built and tested but the 4 stale server.py
  instances are still running. New bridge features (nudge tool, structured messages, auto-refresh)
  won't work until sessions restart with proxy.py MCP config.
- **All consensus partners agreed but bridge still runs stale code.** Commands work but
  structured nudges are garbled. Use plain-text blockers for coordination until daemon deployed.
- **`feat/global-fallback-provider` needs rebase** for cost tracking commit to land.
- **OpenCode billing error format NOT verified.** Need to probe the exact HTTP status + body
  OpenCode returns for "Insufficient balance." This is Package D work.

### Files modified this session

| File | Change |
|---|---|
| `~/.config/opencode/session-bridge/daemon.py` | **New**: bridge daemon core (Unix socket + SQLite + 7 tools) |
| `~/.config/opencode/session-bridge/server.py` | Env-var TTL + PID liveness + graduated purge + nudge return |
| `~/.config/opencode/opencode.json` | MCP config: `SESSION_BRIDGE_TTL=600` env var |
| `AGENTS.md` | 300s→600s TTL fix (3 instances) — gitignored |
| `src/charon/cli.py` | `_import_all_models()` + `--all` flag (uncommitted) |
| `src/charon/providers.py` | `_pricing_fields()` + cost capture |
| `src/charon/config.py` | `cost_input`/`cost_output` in registry |
| `src/charon/gateway.py` | `_META_KEYS` + cost (5 sites) |
| `src/charon/proxy_server.py` | cost in `/v1/models` |
| `src/charon/connect.py` | `discover_models()` returns dicts; cost+metadata in `_write_opencode()` |
| `fleet/BRIDGE-IMPROVEMENT-PLAN.md` | **New** |
| `fleet/EVAL-RelayFreeLLM.md` | **New** |
| `fleet/board/BRIDGE-HARDEN.md.parked` | **New ticket** |
| `fleet/board/PROVIDER-FLATRATE.md.parked` | **New ticket** |
| `fleet/board/BRIDGE-RELAYFEATURES.md.parked` | **New ticket** |
| `fleet/prompts/bridge-harden.md` | **New prompt** |
| `fleet/prompts/provider-flatrate.md` | **New prompt** |
| `fleet/prompts/bridge-relay-features.md` | **New prompt** |

### Cross-repo improvements to propose

**Charon → mediastack:** The bridge daemon architecture (single Unix socket listener replacing
per-session MCP instances) could replace mediastack's filesystem-based heartbeat system.
Benefits: single codebase (no stale instances), SQLite persistence (survives crashes),
graduated purge (nudge→escalate→reap), structured messaging (machine-readable coordination).
Mediastack's warden election pattern is not needed with a single daemon.

### Session-bridge quick reference (for next yoda session)

```
# 1. Register (pick unused Jedi name)
session-bridge_register(session_id="yoda", name="T0 failover packages A-D", repo="charon", status="in-progress")

# 2. Check board before work — auto-refreshes liveness
session-bridge_board(repo="charon")

# 3. Before subagent: extend TTL
session-bridge_update(session_id="yoda", status="in-progress", busy="subagent")

# 4. After subagent: restore TTL
session-bridge_update(session_id="yoda", status="in-progress", busy=null)

# 5. Communicate: use blockers (plain text) or nudge (structured — post daemon deploy)
session-bridge_update(session_id="yoda", blockers=["@target: message"])

# 6. Coordinate with obi-wan-kenobi (cli.py collision risk) and mace-windu
session-bridge_board(repo="charon")  # poll every 30s during coordination

# 7. Heartbeat every 2-3 min
session-bridge_update(session_id="yoda", status="in-progress")
```

---

## Handoff file maintenance

- **One file:** `SESSION-HANDOFF.md` replaces `HANDOFF.md`, `HANDOFF-CONTINUE.md`,
  and `SESSION-RESTART.md`. Archive the old ones.
- **Generate:** run `bash /home/stack/charon-private/fleet/handoff.sh > fleet/SESSION-HANDOFF.md`
  at session end, then fill in the Human analysis section.
- **Commit:** commit the completed `SESSION-HANDOFF.md` to the charon-private fleet repo.
- **Read:** the next session reads ONLY `SESSION-HANDOFF.md` — it is the single source of truth.
