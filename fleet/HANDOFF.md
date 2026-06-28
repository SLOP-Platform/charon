# Charon — Session Handoff (2026-06-27, late)

Resume doc for a fresh MANAGER session. Read `/home/stack/.claude/projects/-home-stack-code-charon/memory/MEMORY.md`
+ this + `/home/stack/charon-private/fleet/WORKFLOW.md` first, then run
`bash /home/stack/charon-private/fleet/board.sh` · `validate_board.sh`.

## FIRST ACTS — THE ONE-TICKET PROOF (do this first, start to finish)
0. Read `MEMORY.md` + this + `WORKFLOW.md`; run `board.sh` · `validate_board.sh`. Then:

**#1 JOB: prove the non-Claude-agent-runs-a-ticket loop on ONE ticket.** Everything else is ON HOLD
until this is done. GOAL: prove a non-Claude agent (opencode, using a non-Claude model VIA Charon)
can work a real ticket through `charon work`, and surface exactly where a human still steps in.

OUTSIDE-THE-BOX KEY: `charon work`'s engine does NOT route the agent through Charon's gateway (gap
**WORK-GATEWAY-WIRE**). Get "non-Claude via Charon" TODAY by configuring the AGENT: opencode's
`~/.config/opencode/opencode.json` already has a `charon` provider (baseURL = a running charon
gateway, model `gpt-5.4`). Set opencode's DEFAULT model to `charon/gpt-5.4` so when `charon work`
spawns `opencode acp`, the agent's brain is Charon→opencode-zen gpt-5.4 (non-Claude). Routing is
proven by the gateway console's "served" count rising during the run.

STEPS:
1. Charon gateway up with `gpt-5.4` served (charon-vm `10.0.3.91:8080`, token
   `f77ffd3b920f65b642238333a3d88f0e`). Note URL + token + model.
2. opencode (WSL) DEFAULT model set to `charon/gpt-5.4` (routes via Charon).
3. `charon doctor --backend-cmd 'opencode acp'` → expect `spawned:true`, `initialized:true`. STOP if not.
4. Throwaway clone to work in: `git clone <repo> /tmp/proof-repo && cd /tmp/proof-repo && git switch -c proof`.
5. Write `ticket.md`: ONE unit, a SELF-SUFFICIENT TITLE (the agent sees only the title — gap
   **WORK-AGENT-BEARINGS**), explicit `files:` / `owns:`, and an EXECUTABLE `accept:` check.
6. `charon intake import ticket.md` → writes `ticket.plan.json`, prints it; review it (stops here by default).
7. `charon work --units ticket.plan.json --repo /tmp/proof-repo --backend acp --acp-cmd 'opencode acp' --autonomy L1`
8. EXPECT: opencode edits the worktree, Charon commits (detached HEAD), runs the `accept` gate,
   prints ONE JSON report with `units[].status` + `units[].land.decision=propose/hold`. EXPECT NO PR, NO PUSH.
9. CONFIRM non-Claude-via-Charon: gateway console `served`/usage jumped = agent routed LLM through
   Charon→gpt-5.4. (Cost ~0 — no proxy observer in work path = gap **WORK-GATEWAY-WIRE**.)
10. HUMAN FINISHES (the gaps, by hand): branch + push the worktree commit, then
    `charon land <task_id> --open-pr --branch <b> --units ticket.plan.json` (draft PR, never
    auto-merges), then review + merge. Eyeball correctness (no automated adversarial review in work
    path = gap **WORK-LAND-PR**).

OUTCOME: proves the autonomous MIDDLE (dispatch→edit→commit→accept-gate→report) with a non-Claude
model via Charon, and shows which 3 gaps hurt → grounds the build priority below.

## PRIORITIES — build AFTER the proof (droid tickets; operator opens tabs)
- **Run-tickets axis (in order):** 1) **WORK-GATEWAY-WIRE**, 2) **WORK-AGENT-BEARINGS**,
  3) **WORK-LAND-PR** (+ **WORK-OBSERVABILITY** = the 4th, to watch it).
- **Connect-clients axis (parallel):** **CLIENT-CONNECT**.

## ON HOLD — do NOT work unless required
Paused: ADR-0015, WCI-MVP, DSGN-WCI-PROOF, DOGFOOD, DSGN-WRITEBACK, TIER-RECS, PROD-INSTALL pt.2,
UX-POLISH. **EXCEPTION:** TEST-PORT-FLAKE only if CI port-collisions block a priority PR (or just
free port 8080 by stopping any leftover gateway / Docker container on the 4-lom runner). Do NOT
re-park the board — focus per this HANDOFF.

## WHAT MERGED to master THIS session (master now has #54–#66)
- **#54 INTAKE1** — `charon intake import` front door (markdown/plan → tickets, external-id preserved).
- **#55 HARD1** — `run_task(role=…)` end-to-end routing guard test.
- **#56 TIER7B** — ADR-0014 Phase B: per-stage multi-tier routing (router selects backend by tier).
- **#57 PRESETS** — Hugging Face + Neuralwatt provider presets.
- **#59 TIER7B-FOLLOWUP** — multi-member within-tier ordering guard + proxy-teardown hardening.
- **#60 REAPWIN** — router/fence/budget proxy reap-window.
- **#61 CLI-HELP** — plain-language top-level `--help`, gateway-first command order.
- **#62 INSTALL** — one-liner bootstrap `install.sh` + README (prereq check, pretty, re-runnable).
- **#63 SETUP-UX-A** — imported catalog surfaced at the "model served by" prompt + serve-all +
  0-models warn guard + colorized presets. (Delivers most of TIER-RECS Phase A.)
- **#64 DOCKER-INSTALL** — token-gated gateway container, `CHARON_HOME=/data` volume, entrypoint
  token-guard, `/v1/models` healthcheck, `docs/docker.md`.
- **#65 RELEASE-SMOKE-FIX** — `.github/workflows/release.yml` image-smoke retargeted from the stale
  Mode-B `:8473/healthz` to the token-gated gateway default (`:8080 /v1/models` with a
  `CHARON_GATEWAY_TOKEN` bearer) — the next release's smoke would otherwise have FAILED.
- **#66 DOCS-TWO-MODE** — operator-APPROVED two-mode onboarding now on master: README top +
  `docs/getting-started.md` (gateway mode vs. orchestrator mode), per the approved draft.

## RIG CHANGES this session
- **WCI enforcer** added to `validate_board.sh`: hard-gates unjustified disjoint-owns deps +
  redundant tickets; `real-dep:` marker convention to justify a true build-dep; semantic checks
  stay advisory.
- `charon-private` now has a PRIVATE git remote `Nnyan/charon-private` (committed + pushed).
  **Build-rig only — NEVER public; never leak into `src/`.**
- Local `/home/stack/code/charon` synced to master; 32 fleet worktrees pruned;
  `docs/adr-0014` local branch deleted.

## DOGFOOD / PREFLIGHT — VALIDATED end-to-end this session
- Fresh Charon install on **charon-vm (10.0.3.91)** — needed Python 3.11 via deadsnakes+venv
  (the Ubuntu-22.04/3.10 barrier). `charon setup` (opencode-zen, 49 models imported, gpt-5.4
  served). `charon gateway` loopback **and** LAN (`--host 0.0.0.0`, token
  `f77ffd3b920f65b642238333a3d88f0e`). Real `/v1/chat/completions` round-trip
  (client→Charon→opencode-zen→reply), live web-console telemetry, LAN browser console from the
  operator PC (10.0.1.69; net 10.0.0.0/22).
- **Docker** install verified on **4-lom (10.0.1.60)**: `docker compose up --build` → healthy
  gateway serving `/v1/models`.
- **Agentic clients (Mode A / gateway):** Windows opencode GUI (did create+edit+run) **and** WSL
  opencode CLI (listed the board, picked + implemented RELEASE-SMOKE-FIX) both validated as
  Charon-backed.

## DOGFOOD — NEXT STEP (north-star, ON HOLD per priorities above)
The OUT-OF-TREE SLOP exporter spec is READY at
`/home/stack/charon-private/dogfood/SLOP-EXPORT-SPEC.md` (stdlib sqlite3, httpx-free; reads
mediastack `tracking.db` open tickets; emits `charon intake import`-compatible markdown with
`id: slop-<id>` preserved). **Not yet built.** Route the build to a FRESH DROID session (not the
manager). Build command (out-of-tree; writes only `/home/stack/charon-private/dogfood/slop_export.py`):
```
cd /home/stack/code/charon && claude "Build the SLOP→Charon exporter EXACTLY per the spec at /home/stack/charon-private/dogfood/SLOP-EXPORT-SPEC.md ..."
```
Then: export → `charon intake import` → enrich with `accept:`/`owns:` → `charon work --backend acp`.
SLOP tickets live in `/home/stack/code/mediastack/tracking/tracking.db` (~31 open).

## PENDING OPERATOR ACTIONS
- **CLEANUP — delete the throwaway scratch branches** in `/home/stack/code/charon` (their real work
  is already captured on master / in PRs): `test/gateway-agent` (left by the WSL-CLI dogfood;
  RELEASE-SMOKE-FIX work landed in #65) and any `charon-work-*` / `slop-work-*` branches left by
  `charon work` dogfood runs. List first, then delete:
  *****
  git -C /home/stack/code/charon branch | grep -E 'test/gateway-agent|charon-work-|slop-work-'
  git -C /home/stack/code/charon branch -D test/gateway-agent
  git -C /home/stack/code/charon for-each-ref --format='%(refname:short)' 'refs/heads/charon-work-*' 'refs/heads/slop-work-*' | xargs -r git -C /home/stack/code/charon branch -D
  *****
- **oh-my-pi** (https://github.com/can1357/oh-my-pi) — operator wants it working next. Assess what
  it is + whether it's another OpenAI-compatible client to point at Charon (Mode A, via
  `~/.omp/agent/models.yml`). Research + report; don't build in the manager.

## KEY DOCTRINE (memories — all in `MEMORY.md`)
- **Pause after a question or a handed-action** — move slowly; STOP and WAIT, keep it SHORT, don't
  bury the ask in a wall of text.
- **Don't build PRODUCTS in the manager session** — route product builds to FRESH DROID sessions
  via activated tickets + tab commands. Manager sub-agents do ONLY manager work (investigate /
  design / board / review / gate).
- **All substantive work in sub-sessions**; primary stays responsive (gate / merge / talk).
- **disjoint-owns ≠ no-dependency** — a merge-order is not a build-dep; the WCI enforcer is now in
  `validate_board.sh`.
- Adversarial-by-default reviews; always give MY recommendation; multi-lens the high-blast-radius.
- Charon is modular: engine NOT hardcoded to any agent (opencode) or provider — gateway is neutral.
- Product ships standalone: never leak the rig / SLOP / runner / `charon-private` into `src/`.
- WCI is rig-enforced; product WCI deferred. Always use the fleet rig by ABSOLUTE path.
- Always give the literal command; droid launches = `fleet-droid.sh <tier>` once + a one-liner of
  what it picks up; wrap operator-run commands in `*****` lines.

## NEW-SESSION BOOTSTRAP ONE-LINER (paste to start the next manager session)
```
You are the Charon fleet MANAGER. Read /home/stack/.claude/projects/-home-stack-code-charon/memory/MEMORY.md + /home/stack/charon-private/fleet/HANDOFF.md + /home/stack/charon-private/fleet/WORKFLOW.md; run board.sh/validate_board.sh; FIRST do the one-ticket non-Claude proof in HANDOFF (opencode default model charon/gpt-5.4 → `charon work` one ticket → accept-gate → report; human finishes the PR); THEN build WORK-GATEWAY-WIRE → WORK-AGENT-BEARINGS → WORK-LAND-PR + CLIENT-CONNECT; everything else on hold; operator opens droid tabs (`fleet-droid.sh <tier>`); never build products in the manager session; batch edits (touch a file once) + one commit/push per batch; pause after any question/handed-action; token-conscious (operator low on weekly limit).
```
