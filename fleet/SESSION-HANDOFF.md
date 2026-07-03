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

## Human analysis

**Previous session name:** mace-windu
**Previous session model:** deepseek-v4-pro (via Charon gateway)

### What was done this session

No commits or PRs — bridge infrastructure + planning session. All work on disk.

**1. Session-bridge fixes (server.py — on disk, needs daemon deploy):**
- F1-F4 fixes: nudge return, board() auto-refresh, BEGIN IMMEDIATE race protection, register preserves nudges
- Structured message support (message_type + payload envelope)
- E2E tested against on-disk code ✓

**2. Bridge daemon + proxy (built by yoda + obi-wan):**
- daemon.py (24KB), proxy.py (8.7KB), MCP config updated
- NOT YET ACTIVE — needs session restart

**3. Fleet documents (authored):**
- ADOPT-GATEWAY-FEATURES.md: 23-ticket competitive plan
- CROSS-SESSION-REVIEW-PROTOCOL.md: consensus, quorum, deadlock
- BRIDGE-DAEMON-PROPOSAL.md: daemon architecture + SLOP/repowire/llm_conversation research
- PROPOSAL-1-COST-AWARE-ROUTING.md: 5-phase cost-aware routing
- PROPOSAL-2-SESSION-COMMUNICATION.md: daemon + structured protocol

**4. Research:** 5 competitors + 4 open-source projects surveyed

### Key decisions

- opencode MCP stubs strip nudge_messages from update() → use board() for nudge delivery
- File division: yoda=failover, obi-wan=cli/ATC, mace-windu=new modules
- Proposals APPROVED via 3-session adversarial review (15/15 findings addressed)
- Daemon uses SIGHUP graceful restart (not importlib.reload)

### Next session priority

1. Activate daemon + restart sessions
2. Build new modules (discover.py, quality_scorer.py, cache.py, guardrails.py, etc.) — ALL new files, zero collision
3. Wire modules into gateway AFTER yoda lands failover
4. Cost-aware routing per PROPOSAL-1 phases A-C

### Session-bridge HOW-TO

- **heartbeat:** update(status="in-progress") every ~3 min
- **before subagent:** update(busy="subagent") — prevents timeout
- **nudge check:** board(repo="charon", session_id="<id>") — returns nudges + auto-refreshes liveness
- **consensus:** 2 CONCERN=APPROVED, any REJECT=REJECTED, see CROSS-SESSION-REVIEW-PROTOCOL.md


## Handoff file maintenance

- **One file:** `SESSION-HANDOFF.md` replaces `HANDOFF.md`, `HANDOFF-CONTINUE.md`,
  and `SESSION-RESTART.md`. Archive the old ones.
- **Generate:** run `bash /home/stack/charon-private/fleet/handoff.sh > fleet/SESSION-HANDOFF.md`
  at session end, then fill in the Human analysis section.
- **Commit:** commit the completed `SESSION-HANDOFF.md` to the charon-private fleet repo.
- **Read:** the next session reads ONLY `SESSION-HANDOFF.md` — it is the single source of truth.
