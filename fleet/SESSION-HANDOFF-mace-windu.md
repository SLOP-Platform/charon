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

**Session name:** obi-wan-kenobi
**Consensus partners:** yoda, mace-windu

### What was done this session

**Built and committed (feat/prod-install, pushed):**
1. TIER-RECS Phase B — recommend.py (LLM-judge tier ranking), charon tier recommend, 11 tests
2. UX-POLISH items 4,5,9,10 — sys.argv[0], LAN/loopback URL hints, setup discoverability, token cookie
3. UX-POLISH docs 6,7,8 — Docker group, gateway-vs-orchestrator, secrets hot-reload
4. reload/fence fix — eliminated importlib.reload(config), defense-in-depth fence.py is→==
5. ATC audit report — docs/review-log/ATC-AUDIT.md (19 findings, 4 dimensions)

**Built (bridge, not in Charon repo):**
6. proxy.py — thin Unix socket JSON-RPC forwarder (~/.config/opencode/session-bridge/)
7. opencode.json migration — MCP command server.py → proxy.py

**Reviewed (adversarial):**
- bridge-update-nudge-return: CONCERN (4 findings) → 2 CONCERN = APPROVED
- CROSS-SESSION-REVIEW-PROTOCOL: CONCERN (3 findings) → REJECTED → FIXED → ACCEPTED
- PROP-1-COST-AWARE-ROUTING: CONCERN (5 findings) → FIXES ADDRESSED → APPROVED
- PROP-2-SESSION-COMMUNICATION: CONCERN (5 findings) → FIXES ADDRESSED → APPROVED

### Key decisions

1. Three-session consensus: ALL 3 agreed on file division.
   yoda = failover/proxy/gateway/config/routing/coordinator
   obi-wan = cli/connect/secrets/gitleaks/recommend/intake
   mace-windu = new modules (cache, guardrails, etc.) + tests

2. Bridge upgrades deferred to next session cluster — 4 stale server.py instances.
   Use blockers for coordination. Structured nudges don't work until daemon deployed.

3. ATC fix tickets (9 items, 6 files) assigned to obi-wan but NOT BUILT.
   Consensus consumed the session.

### What must happen next (priority order)

**1. Build ATC fixes (obi-wan-kenobi, ~50 min):**

CRITICAL (build first):
- ATC-001: cli.py line 932 — add "body": u.get("body", "") to _load_plan
- ATC-003: connect.py line 411,526 — mask raw token, replace with "<your-gateway-token>"

MEDIUM (build second):
- ATC-006: secrets.py — expand _SENSITIVE_ENV blocklist
- ATC-007: .gitleaks.toml — tighten allowlist regex to CHARON_ prefix only
- ATC-008: intake.py line 62 — DEFAULT_TIER = "med" (canonical, not "sonnet")
- ATC-009: cli.py line 730 — abstract _is_anthropic() or document vendor coupling

LOW (build third):
- ATC-013: recommend.py — add comment about heuristic rot
- ATC-015: gateway.py — consider moving _invocation_name to shared module

Files NOT owned by obi-wan (yoda owns):
- ATC-002: gateway.py token leak → yoda
- ATC-004: proxy_server.py CSRF → yoda
- ATC-005: config.py secure save → yoda
- ATC-010: failover.py wiring → yoda

**2. Coordinate with yoda on cli.py collision:**
yoda adds doctor warning, obi-wan fixes body drop + anthropic filter.
Sequence: yoda lands first (T0), obi-wan rebases.

**3. Gate command:**
PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py

### Session-bridge quick reference

# Register
session-bridge_register(session_id="<jedi>", name="<work>", repo="charon", status="in-progress")

# Check board (includes liveness refresh)
session-bridge_board(repo="charon")

# Heartbeat every 2-3 min
session-bridge_update(session_id="<jedi>", status="in-progress")

# Coordinate: poll board every 30s during active coordination
session-bridge_board(repo="charon")

# Communicate via blockers (plain text — structured nudges not deployed)
session-bridge_update(session_id="<jedi>", blockers=["@target: message"])

# Before subagent dispatch (daemon-only — not deployed)
session-bridge_update(session_id="<jedi>", status="in-progress", busy="subagent")

### Collision matrix

| File | obi-wan (ATC) | yoda (failover) |
|---|---|---|
| cli.py | ATC-001, ATC-009 | T0-C doctor check |
| connect.py | ATC-003 | — |
| secrets.py | ATC-006 | — |
| .gitleaks.toml | ATC-007 | — |
| intake.py | ATC-008 | — |
| recommend.py | ATC-013 | — |
| proxy_server.py | — | T0 A+B+C |
| gateway.py | — | T0 C |
| config.py | — | T0 C |

### Cross-repo improvements

Charon → mediastack: The session-bridge daemon architecture (single Unix socket + SQLite)
could replace mediastack's filesystem-based heartbeat. See PROP-2 appendix.
