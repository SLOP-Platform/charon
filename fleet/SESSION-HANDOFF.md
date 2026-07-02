# Charon Fleet — Session Handoff (2026-07-02T23:41:47Z)

> **This is THE canonical handoff file.** Previous handoffs (HANDOFF.md,
> HANDOFF-CONTINUE.md, SESSION-RESTART.md) are superseded. There is exactly
> ONE handoff file per session end: `SESSION-HANDOFF.md`.

---

## Bootstrap (copy-paste into next session)

Read `/home/stack/charon-private/fleet/SESSION-HANDOFF.md` fully, then run
`bash /home/stack/charon-private/fleet/status.sh && bash /home/stack/charon-private/fleet/validate_board.sh`,
check the board for claimed names, register with an unused Jedi name + `repo="charon"`, then go.

---

## Auto-generated state (from `handoff.sh` run at 2026-07-02T23:41:47Z)

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
834 passed in 75.60s (0:01:15)
All checks passed!
```
### Board
```

  CHARON-FLEET STATUS @ 2026-07-02T23:43:06Z

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

**Previous session name:** yoda

### What was done this session

1. **Cost tracking pipeline** (committed `bb75206` on `feat/global-fallback-provider`, pushed):
   - `providers.py`: `_pricing_fields()` extracts per-M-token USD pricing from upstream `/models`
   - `config.py`: `add_model()`/`add_models_bulk()` persist `cost_input`/`cost_output`
   - `gateway.py` + `proxy_server.py` + `cli.py`: `_META_KEYS` synced across 5 sites; `/v1/models` emits pricing
   - `connect.py`: `discover_models()` returns full dicts (was list-of-strings); `_write_opencode()` writes `cost` + metadata
   - `api.py`: `_MODEL_FIELDS` synced
   - Tests: pricing parse assertions, cost writer test, no-cost fallback test
   - 876 passed, ruff/mypy/boundary/version green

2. **`charon models import --all`** (uncommitted on `feat/prod-install`):
   - `_import_all_models()` iterates all preset + custom providers with keys set
   - Supports `--free-only` and `--into-pool` flags
   - Mypy/ruff clean; help text shows `--all` option
   - NOTE: first implementation was lost to PR #78 merge collision (branch switch mid-session). Recovered.

3. **Session bridge timeout investigation + fix:**
   - AGENTS.md: fixed 300s→600s TTL doc bug (3 instances) — note: AGENTS.md is gitignored, local-only
   - `~/.config/opencode/session-bridge/server.py:24`: TTL now env-var configurable (`SESSION_BRIDGE_TTL`, defaults to `600`)
   - `server.py:_purge_stale()`: added PID liveness check (`os.kill(pid, 0)`) before purging — alive process = skip purge (mediastack droid pattern)
   - `~/.config/opencode/opencode.json`: MCP config passes `SESSION_BRIDGE_TTL=600` to server
   - Requires opencode restart to take effect

4. **Mediastack droid system research:**
   - Documented full lifecycle (claim→heartbeat→warden→escalate→reap) at `/home/stack/charon-private/fleet/BRIDGE-IMPROVEMENT-PLAN.md`
   - 5 transferrable patterns identified: background ops, graduated response, PID verification, progress detection, end-session gate

5. **Provider research for flat-rate / cost-optimized routing:**
   - **featherless.ai**: $25/mo unlimited flat-rate, 40k+ models, OpenAI-compatible → ADD TO PRESETS
   - **DeepInfra**: ultra-cheap per-token (~$0.05/M), some free models → ADD TO PRESETS
   - **Cerebras**: fastest Llama (1,800+ tok/s), free tier → ADD TO PRESETS
   - **SiliconFlow**: per-token only, $0.05/M on GPT-OSS-120B → optional add
   - **synthetic.net** (all URLs incl. dev.synthetic.net): unreachable — dead
   - **useapiary.com**: B2C chat web app, no API → not a provider

6. **RelayFreeLLM comparative analysis:**
   - Full comparison matrix saved at `/home/stack/charon-private/fleet/EVAL-RelayFreeLLM.md`
   - Includes reusable evaluation template for future project comparisons
   - 6 RelayFreeLLM features to adopt, 3 transformative gaps, 10 RelayFreeLLM weaknesses

7. **Connect config audit (5 client writers):**
   - opencode, omp, aider, continue, cline — all 5 kept
   - Only opencode gets rich metadata (cost, context_window, capability flags) — others don't support it
   - Recommendation: keep all 5; REGISTRY pattern makes them cheap to maintain

8. **Gate: 834 passed, ruff/mypy/boundary clean on `feat/prod-install`**

### Key findings / decisions

- **PR #78 merge collision**: `yoda`'s uncommitted `--all` import work was lost when operator switched branches (23:02) + merged (23:25). Root cause: bridge has no branch/file tracking, no merge notification, no graduated response.
- **Bridge TTL is 600s not 300s**: AGENTS.md was wrong by 2x. Caused unnecessary heartbeat pressure. Fixed in 3 AGENTS.md locations.
- **featherless.ai is the only flat-rate find**: $25/mo unlimited, OpenAI-compatible. The missing anchor for "flat-rate first, then cheapest" pool config.
- **RelayFreeLLM does 6 things better than Charon**: preemptive rate limiting, image-aware routing, response normalization, session affinity, admin dashboard, auto-discovery. All ticketized.
- **Mediastack graduated response (NUDGE→ESCALATE→REAP) is strictly better than binary purge.** Transferring to bridge via BRIDGE-HARDEN ticket.
- **5 connect clients kept**: Only opencode gets rich metadata (its config schema supports it). Others get URL+token+model only.

### What must happen next (in priority order)

1. **Commit `--all` import** on `feat/prod-install` — code is working, gate green, just needs commit+push.
2. **Cost tracking goes to master**: `feat/global-fallback-provider` has cost tracking at `bb75206`. Needs rebase onto master and PR.
3. **BRIDGE-HARDEN** (parked): operator review `BRIDGE-IMPROVEMENT-PLAN.md`, then activate. Builds graduated response + PID claim verification + progress detection + end-session gate + background ops AGENTS.md update. Files: `~/.config/opencode/session-bridge/server.py`, `AGENTS.md`.
4. **PROVIDER-FLATRATE** (parked): add featherless.ai + DeepInfra + Cerebras presets to `providers.py`. Files: `src/charon/providers.py`.
5. **TIER-RECS + UX-POLISH** (from handoff): both touch `cli.py`, single PR. Operator has prompts.

### Collision matrix

| File | Owner (live) | Owner (next) |
|---|---|---|
| `src/charon/cli.py` | `--all` import (uncommitted, yoda) | TIER-RECS, UX-POLISH |
| `src/charon/providers.py` | none | PROVIDER-FLATRATE |
| `~/.config/opencode/session-bridge/server.py` | none (cross-repo) | BRIDGE-HARDEN |

### Open questions / Blockers

- **`feat/global-fallback-provider` needs rebase**: cost tracking commit `bb75206` is on a branch that diverged. PR #79-#81 landed on master independently. Rebase needed.
- **Operator needs to restart opencode** for bridge server changes (env-var TTL + PID liveness) to take effect.
- **BRIDGE-HARDEN is cross-repo** — owns files outside Charon's `src/`. Is this acceptable? Ticket is parked pending operator review.
- **`PROVIDER-FLATRATE` hasn't been claimed** — parked pending operator activation.

### Files modified this session

| File | Change |
|---|---|
| `src/charon/providers.py` | `_pricing_fields()` + cost capture in `_parse_models()` (cost tracking) |
| `src/charon/config.py` | `cost_input`/`cost_output` params in `add_model()`/`add_models_bulk()` |
| `src/charon/gateway.py` | `_META_KEYS` + cost in `model_meta` (4 sites) |
| `src/charon/proxy_server.py` | cost in `/v1/models` response |
| `src/charon/connect.py` | `discover_models()` returns dicts; `Wiring.model_meta`; `_write_opencode()` writes cost+metadata |
| `src/charon/cli.py` | `_META_KEYS` + `_import_all_models()` + `--all` flag |
| `src/charon/api.py` | `_MODEL_FIELDS` + cost fields |
| `AGENTS.md` | 300s→600s TTL fixes (3 instances) — gitignored, local only |
| `~/.config/opencode/session-bridge/server.py` | Env-var TTL + PID liveness check |
| `~/.config/opencode/opencode.json` | MCP config: `SESSION_BRIDGE_TTL=600` env var |
| `/home/stack/charon-private/fleet/BRIDGE-IMPROVEMENT-PLAN.md` | New: bridge improvement plan document |
| `/home/stack/charon-private/fleet/EVAL-RelayFreeLLM.md` | New: RelayFreeLLM comparison + evaluation template |
| `/home/stack/charon-private/fleet/board/BRIDGE-HARDEN.md.parked` | New ticket |
| `/home/stack/charon-private/fleet/board/PROVIDER-FLATRATE.md.parked` | New ticket |
| `/home/stack/charon-private/fleet/board/BRIDGE-RELAYFEATURES.md.parked` | New ticket |
| `/home/stack/charon-private/prompts/bridge-harden.md` | New prompt |
| `/home/stack/charon-private/prompts/provider-flatrate.md` | New prompt |
| `/home/stack/charon-private/prompts/bridge-relay-features.md` | New prompt |
| `tests/test_connect.py` | Cost writer tests + discover_models dict return fix |
| `tests/test_connect_gui.py` | discover_models dict return fix |
| `tests/test_connect_omp.py` | discover_models dict return fix (4 lambdas) |
| `tests/test_models_import.py` | Pricing parse assertions |

### Cross-repo improvements to propose

**Charon → mediastack**: The mediastack droid system's graduated response (NUDGE→ESCALATE→GRACE→REAP) and PID-liveness pattern are now being adopted by the Charon bridge. If mediastack ever wants a lighter-weight session bridge alternative to filesystem heartbeats, the improved Charon bridge (post BRIDGE-HARDEN) could serve as a reference implementation. Specific improvements Charon is adopting that mediastack already has: PID-based liveness check, graduated response chain, background operations pattern.

---

## Handoff file maintenance

- **One file:** `SESSION-HANDOFF.md` replaces `HANDOFF.md`, `HANDOFF-CONTINUE.md`,
  and `SESSION-RESTART.md`. Archive the old ones.
- **Generate:** run `bash /home/stack/charon-private/fleet/handoff.sh > fleet/SESSION-HANDOFF.md`
  at session end, then fill in the Human analysis section.
- **Commit:** commit the completed `SESSION-HANDOFF.md` to the charon-private fleet repo.
- **Read:** the next session reads ONLY `SESSION-HANDOFF.md` — it is the single source of truth.
