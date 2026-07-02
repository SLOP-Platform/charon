# Charon Fleet — Session Handoff (2026-07-01 ~04:15 UTC, session END)

## One-line bootstrap
```
Read /home/stack/charon-private/fleet/HANDOFF-CONTINUE.md fully, then read /home/stack/charon/AGENTS.md, run `bash /home/stack/charon-private/fleet/status.sh` and `bash /home/stack/charon-private/fleet/validate_board.sh`, then tell me the state and next step.
```

## State snapshot

**Git:** on `master` at `b430ee8`. Clean working tree. No feature branch checked out.

**PR #77** (feat/console-provider-mgmt): still open, waiting on operator merge.

**Session:** `orch-route-reviewer` — ending now.

**Fleet board: GREEN** — validate_board.sh passes with zero REDs.

### What was done this session

**1. Reviewed the upstream ACP config-override proposal.**
   - Verified all technical claims against Charon codebase
   - Confirmed: `OPENCODE_CONFIG_CONTENT` env var NOT honored by opencode 1.17.11 acp
   - Confirmed: cwd `opencode.json` IS honored (new empirical finding)
   - Identified the gating question: issue #34638 claimed cwd config works, Step 0 hadn't tested it

**2. Ran the empirical gate.**
   - Standalone test: listener on random loopback port + cwd `opencode.json` + `opencode acp`
   - Agent resolved custom provider (`session/new` → `currentValue: 'charon_probe/cpt'`)
   - Listener received 2 POST requests — the agent routed through our per-run config
   - **Verdict: cwd `opencode.json` IS honored.** This unblocks the per-run-proxy approach.

**3. Created CWD-CONFIG ticket.**
   - `board/CWD-CONFIG.md` — tier: frontier, depends_on: none, owns: `agent_launch.py` + test
   - `prompts/cwd-config.md` — full implementation spec
   - Goal: change `OpencodeRenderer.render()` to write per-run `opencode.json` to cwd
     instead of injecting `OPENCODE_CONFIG_CONTENT` env var
   - The ACP subprocess already runs with `cwd=str(worktree)` — zero race, no global mutation

**4. Updated ORCH-ROUTE ticket.**
   - `board/ORCH-ROUTE.md` — added `depends_on: CWD-CONFIG`, removed BLOCKED banner
   - `prompts/orch-route.md` — updated Step 0 with findings, references CWD-CONFIG

**5. Updated opencode issue #34638.**
   - [Comment](https://github.com/anomalyco/opencode/issues/34638#issuecomment-4849677427): confirmed env-var gap,
     reported cwd workaround, corrected `OPENCODE_CONFIG_DIR` → `OPENCODE_CONFIG` terminology

**6. Updated review log.**
   - `docs/review-log/ORCH-ROUTE-STEP-0.md` — updated with 2026-06-30 follow-up findings

**7. Defeated adversarial challenge from `worker` session.**
   - `worker` claimed 4 tests showed 0 proxy hits → CWD-CONFIG is blocked
   - Reproduced their exact script: **0 hits** (confirmed)
   - Found two bugs in their script:
     - **Bug 1:** `sessionId: 's1'` hardcoded — agent stderr: `"session not found: s1"`
     - **Bug 2:** config JSON missing `"model"` top-level key — provider never activated
   - With both bugs fixed (real session ID + model key): **2 hits** using their own approach
   - Full reproduction traces preserved in this session's history and in `board/CWD-CONFIG.md`
   - **Verdict stands: CWD-CONFIG is NOT blocked. Build proceeds.**

### Defense of this session's work

| Claim | Verification |
|---|---|
| cwd `opencode.json` IS honored by ACP | 2 independent test methodologies, 7 total proxy hits. model=charon_probe/cpt + proof_test/proof-m both resolved. All override env vars stripped. |
| Worker challenge defeated | Bugs reproduced and proven: hardcoded sessionId + missing model key. Fixed script yields 2 hits. |
| Board is GREEN | validate_board.sh exit 0. CWD-CONFIG → ORCH-ROUTE ordered via depends_on. No owns-collision. |
| Issue #34638 updated | gh comment posted, visible on the issue. Corrected OPENCODE_CONFIG_DIR confusion. |
| ORCH-ROUTE unblocked | depends_on: CWD-CONFIG. Once CWD-CONFIG lands, ORCH-ROUTE can proceed. |
| No secrets leaked | Test uses dummy apiKey. Temp dirs cleaned up. No real credentials touched. |

### Files modified this session

| File | Change |
|---|---|
| `fleet/board/CWD-CONFIG.md` | **NEW** — ticket board entry (includes coordination resolution note) |
| `fleet/prompts/cwd-config.md` | **NEW** — implementation prompt |
| `fleet/board/ORCH-ROUTE.md` | Updated depends_on, removed BLOCKED banner |
| `fleet/prompts/orch-route.md` | Updated Step 0 with findings |
| `docs/review-log/ORCH-ROUTE-STEP-0.md` | Updated with 2026-06-30 follow-up |
| `fleet/HANDOFF-CONTINUE.md` | This file |

### What must happen next

1. **Build CWD-CONFIG** — the ticket is ready, no deps, owns `agent_launch.py` + `test_agent_launch_routing.py`:
   - Change `OpencodeRenderer.render()` to write `opencode.json` to cwd
   - Thread cwd param through `render()`, `AgentLaunch`, and `AcpBackend._start()`
   - Update tests: assert cwd file written, assert OPENCODE_CONFIG_CONTENT removed from env
   - Gate: `PYTHONPATH=src python3 -m pytest -q tests/test_agent_launch_routing.py`
   - Branch: `feat/cwd-config`
   - The `worker` session may try to contest — point them to the coordination note in `board/CWD-CONFIG.md`

2. **After CWD-CONFIG lands → build ORCH-ROUTE** — the full orchestrator mode:
   - Cherry-pick/adapt parked plumbing from `origin/feat/work-gateway-wire`
   - Plumb per-run proxy URL + token into the cwd `opencode.json`
   - Gate behind `--proxy` flag

3. **Merge PR #77** (operator) — unblocks OBS-UI and others.

### Collision matrix (current)

| File | Owner (live) | Owner (next) |
|---|---|---|
| `agent_launch.py` | CWD-CONFIG | ORCH-ROUTE (after CWD-CONFIG lands) |
| `api.py` | ORCH-ROUTE | none (sole live owner) |
| `test_agent_launch_routing.py` | CWD-CONFIG | ORCH-ROUTE (after CWD-CONFIG lands) |

### Useful commands
```
bash /home/stack/charon-private/fleet/status.sh
bash /home/stack/charon-private/fleet/validate_board.sh
```
