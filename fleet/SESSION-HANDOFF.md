# Charon Fleet — Session Handoff (2026-07-01T22:20:06Z)

> **This is THE canonical handoff file.** Previous handoffs (HANDOFF.md,
> HANDOFF-CONTINUE.md, SESSION-RESTART.md) are superseded. There is exactly
> ONE handoff file per session end: `SESSION-HANDOFF.md`.

---

## Bootstrap (copy-paste into next session)

Read `/home/stack/charon-private/fleet/SESSION-HANDOFF.md` fully, then read
`/home/stack/code/charon/AGENTS.md`, run
`bash /home/stack/charon-private/fleet/status.sh` and
`bash /home/stack/charon-private/fleet/validate_board.sh`, check the board for
claimed names, then `register` with an unused **Jedi name** + `repo="charon"`,
then tell the operator the state and next action.

---

## Auto-generated state (from `handoff.sh` run at 2026-07-01T22:20:06Z)

### Git
```
feat/global-fallback-provider

--- last 10 commits ---
9e4a1f8 feat(ORCH-ROUTE): e2e orchestrator proxy routing test
ffde252 feat(CWD-CONFIG): write per-run opencode.json to cwd, remove OPENCODE_CONFIG_CONTENT
17e7a14 fix(SETUP-KEY-UX): implement missing _mask_key and _probe_key helpers
274835d feat: consolidate subagent work — SETUP-KEY-UX, PUBLIC-CLEAN-LINT, CONNECT-OMP-WSL
fc3290d Merge branch 'feat/connect-omp-wsl' into feat/global-fallback-provider
5660fe6 feat(CONNECT-OMP-WSL): reject Windows-interop binaries on WSL, ensure native bun/npm + unzip for omp install
460b9e1 fix(gate): resolve gate registry domain overlaps and missing arch entry
aa479a7 Merge branch 'feat/obs-ui' into feat/global-fallback-provider
29a50b7 Merge branch 'feat/wci-mvp' into feat/global-fallback-provider
d31573c feat(WCI-MVP): static reconciler + depth pre-sort
```
### Open PRs
```
[{"headRefName":"feat/obs-ui","number":78,"state":"OPEN","title":"feat: Batch 1 — console mgmt, obs capture, client connect, ADR-0015, routing proxy, DTC infra, OBS-UI, fallback provider"}]
```
### Gate
```
874 passed in 74s, ruff clean, mypy clean, boundary/version clean
```
### Board
```
droids:0   ready:1 (CWD-CONFIG)   blocked:1 (ORCH-ROUTE)   done:50   PR-open:0 (PR #78 is draft)
Board validation: GREEN
```
### Parked tickets (30)
```
ADR-0015, ATC, CLIENT-CONNECT-GUI, CONNECT-OMP-WSL, CONSOLE-PROVIDER-MGMT,
CWD-CONFIG-VERIFY, DOGFOOD, DS-PLAN-REVIEW, DSGN-WCI-PROOF, DSGN-WRITEBACK,
DTC-1 through DTC-8, FALLBACK-PROVIDER, MODEL-DISCOVERY, OBS-CAPTURE, OBS-UI,
OHMYPI-ASSESS, PROD-INSTALL, PUBLIC-CLEAN-LINT, SETUP-KEY-UX, TIER-RECS,
UX-POLISH, WCI-FOLLOWON, WCI
```

---

## Human analysis

**Previous session name:** `obi-wan-kenobi` (Jedi — Charon session)
**Previous session model:** deepseek-v4-pro

### What was done this session

1. **Session naming convention — IMPLEMENTED (cross-repo).**
   - `~/.config/opencode/session-bridge/SESSION.md`: added Star Wars naming table
     (Jedi pool for Charon, droid pool for SLOP)
   - `fleet/handoff.sh`: bootstrap text updated to pick an unused Jedi name
   - `fleet/SESSION-HANDOFF.md`: bootstrap line updated
   - `mediastack/.opencode/proposals/session-naming-convention.md`: decision record
     filled — all 4 questions: **Adopted**
   - Cross-repo proposal surfaced via session-bridge; already enshrined in
     AGENTS.md/SESSION.md rules

2. **ORCH-ROUTE — COMPLETED (commit `9e4a1f8`).**
   - `tests/test_agent_launch_routing.py` (+96 lines):
     `test_orchestrator_proxy_path_routes_agent_via_inprocess_gateway`
   - Stub ACP agent reads cwd opencode.json, fires POST through in-process proxy
   - Asserts upstream received model id + proxy recorded usage
   - Accept: `PYTHONPATH=src python3 -m pytest -q tests/test_agent_launch_routing.py`
     → 11/11 passed

3. **Gate:** 874 passed, ruff clean, mypy clean, boundary/version clean.

### Key findings / decisions

**Docker gateway break — root cause identified (post-hoc):**
The "Increase subagent context window" session (~2026-07-01 02:02 UTC) rsynced the
repo to 4-LOM and ran `docker compose up -d --build` in `/home/stack/charon-test/charon/`.
This rebuilt the container using commit `ede04b8`'s docker-compose.yml, which has
`127.0.0.1:8080:8080` (loopback) + requires `CHARON_GATEWAY_TOKEN`. The container
was recreated without a `.env` file, breaking external access and exiting code 78.
A subsequent web session fixed it by creating `/home/stack/charon/docker-compose.yml`
with `8080:8080` (0.0.0.0) + proper token. **Lesson:** never `docker compose up -d`
to 4-LOM from a session — it rebuilds with the repo's security defaults, not the
production config.

### What must happen next (in priority order)

1. **Push charon branch** — `feat/global-fallback-provider` has 1 unpushed commit
   (`9e4a1f8` ORCH-ROUTE). `git push origin feat/global-fallback-provider`.

2. **Merge PR #78** (operator) — 874 tests, all gates green. Batches 15+ tickets.

3. **Mark ORCH-ROUTE done in fleet state** — the board still shows it as
   `blocked (needs CWD-CONFIG)`. The test is written and commited; unblock
   ORCH-ROUTE's state. CWD-CONFIG is listed as `ready`.

4. **After CWD-CONFIG + ORCH-ROUTE → WCI-FOLLOWON** (Wave 1, after WCI).
   Ticket at `board/WCI-FOLLOWON.md.parked`. depends_on: WCI (in PR #78).

5. **After WCI-FOLLOWON → ATC** (adversarial ticket check) — audit all committed work.

6. **Design-required tickets blocked (need spec first):**
   - DSGN-WCI-PROOF (`board/DSGN-WCI-PROOF.md.parked`)
   - DSGN-WRITEBACK (`board/DSGN-WRITEBACK.md.parked`)
   - OHMYPI-ASSESS (`board/OHMYPI-ASSESS.md.parked`) — research ticket

### Collision matrix

| File | Owner (live) | Owner (next) |
|---|---|---|
| `api.py` | ORCH-ROUTE (done) | none |
| `agent_launch.py` | CWD-CONFIG (ready) | ORCH-ROUTE (done, on top) |
| `test_agent_launch_routing.py` | ORCH-ROUTE (done) | none |

### Open questions / Blockers

- PR #78 needs operator review and merge.
- ORCH-ROUTE board state is stale (shows "blocked") — needs a state update.
- Docker gateway on 4-LOM: confirmed working after fix session (port 8080 open
  to LAN, token-gated). The docker-compose.yml at `/home/stack/charon/docker-compose.yml`
  is the canonical production config — don't rebuild from the repo's compose file.

### Files modified this session

| File | Change |
|---|---|
| `tests/test_agent_launch_routing.py` | +96 lines — ORCH-ROUTE e2e orchestrator proxy test |
| `~/.config/opencode/session-bridge/SESSION.md` | Star Wars naming convention section |
| `fleet/handoff.sh` | Bootstrap updated for Jedi naming |
| `fleet/SESSION-HANDOFF.md` | Bootstrap + full handoff (this file) |
| `mediastack/.opencode/proposals/session-naming-convention.md` | Decision record filled |

### Cross-repo improvements to propose

None outstanding. The session naming convention was the only cross-repo improvement
this session — it has been proposed, adopted, and enshrined in both repos'
instructions.

---

## Handoff file maintenance

- **One file:** `SESSION-HANDOFF.md` replaces `HANDOFF.md`, `HANDOFF-CONTINUE.md`,
  and `SESSION-RESTART.md`. Archive the old ones.
- **Generate:** run `bash /home/stack/charon-private/fleet/handoff.sh > fleet/SESSION-HANDOFF.md`
  at session end, then fill in the Human analysis section.
- **Commit:** commit the completed `SESSION-HANDOFF.md` to the charon-private fleet repo.
- **Read:** the next session reads ONLY `SESSION-HANDOFF.md` — it is the single source of truth.
