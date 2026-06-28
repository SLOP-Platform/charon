# Charon — Session Handoff (2026-06-27, late)

Resume doc for a fresh MANAGER session. Read `/home/stack/.claude/projects/-home-stack-code-charon/memory/MEMORY.md`
+ this + `/home/stack/charon-private/fleet/WORKFLOW.md` first, then run
`bash /home/stack/charon-private/fleet/board.sh` · `validate_board.sh`.

## FIRST ACTS (fresh session)
1. Read `MEMORY.md` + this + `/home/stack/charon-private/fleet/WORKFLOW.md`.
2. `bash /home/stack/charon-private/fleet/board.sh` · `validate_board.sh` — confirm the board state.
3. **There are NO in-flight droid PRs to gate** — #65 + #66 merged; the board is CLEAR of active
   claimable tickets except the one new ticket below. Verify with `bash board.sh`.
4. Pick up the real work (no gating queue): **(a)** TEST-PORT-FLAKE (new ACTIVE ticket, below);
   **(b)** the OUT-OF-TREE SLOP exporter (north-star dogfood, below); **(c)** assess oh-my-pi
   (another OpenAI-compatible agent that points at Charon via `~/.omp/agent/models.yml`);
   **(d)** the parked production-readiness tickets. Surface the next decision; do NOT launch droids
   yourself (operator opens tabs). Build PRODUCTS in fresh droid sessions, never in the manager.

## ACTIVE BOARD — what's claimable now
The board is CLEAR of in-flight droid PRs — #65 and #66 both MERGED this session. The only ACTIVE /
claimable ticket is:
- **TEST-PORT-FLAKE** — `feat/test-ephemeral-ports`, tier `sonnet`, no deps. Real CI-robustness bug:
  the gateway tests bind a FIXED port (8080), so on the shared 4-lom self-hosted runner they fail
  `OSError: [Errno 98] Address already in use` whenever anything else holds 8080 (a leftover
  `charon gateway`, a Docker container, or a concurrent CI job — it bit #65 and #66; freeing 8080
  by `docker compose down` on 4-lom unblocked them). Fix = bind an EPHEMERAL port (port 0) and read
  the actually-bound port back (`server.server_address[1]`). TEST-ONLY (no src/ change). Tab:
  *****
  bash /home/stack/charon-private/fleet/fleet-droid.sh sonnet
  *****
  Then gate adversarially + merge on green per the bar. Everything else is PARKED (see below).

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

## DOGFOOD — NEXT STEP (north-star)
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

## PARKED / DEFERRED (will NOT auto-build)
- **CLIENT-CONNECT** (TOP production-readiness priority, operator 2026-06-27): `charon connect <client>` — one command to install + wire up a CLIENT (opencode|aider|omp|cline|continue) pointed at the Charon gateway (the gateway-first "last mile"). Design first, then build. PARKED `.parked`.
- **PROD-INSTALL** (part 2): `charon update`/`reinstall` subcommand + `charon doctor`
  gateway-preflight + the pipx-ensurepath PATH nit.
- **TIER-RECS**: Phase A mostly delivered by #63; Phase B = LLM-judge tier recommendations grounded
  on the live `/models` catalog — held until §5.1.
- **UX-POLISH** (8 items): [HIGH] validate-API-key-at-setup; getpass paste feedback; hardcoded
  `charon` in messages → use `argv[0]`; console-URL-local-only hint; docker-group prereq doc;
  gateway-vs-orchestrator → now DOCS-TWO-MODE.
- **WORK-OBSERVABILITY**: `charon work` is a black box (no live progress, agent output discarded,
  no aggregate/work UI; ADR-0004 D7 deferred the watcher).
- **DSGN-WRITEBACK**: report completed work back to the source tracker (needs INTAKE1's external-id
  preservation, now merged).
- **WCI / WCI-FOLLOWON / ADR-0015 / PRODUCT-WCI**: DEFERRED until production-ready — product WCI
  must be opt-in-orchestrator-only + advisory-override.

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
You are the Charon fleet MANAGER. Read /home/stack/.claude/projects/-home-stack-code-charon/memory/MEMORY.md, then /home/stack/charon-private/fleet/HANDOFF.md, then /home/stack/charon-private/fleet/WORKFLOW.md. Run `bash /home/stack/charon-private/fleet/board.sh` and `bash /home/stack/charon-private/fleet/validate_board.sh`. There are NO in-flight droid PRs to gate (#65 + #66 merged). Pick up the real work: the new TEST-PORT-FLAKE ticket (test-only ephemeral-port CI fix), then the OUT-OF-TREE SLOP exporter dogfood (build per /home/stack/charon-private/dogfood/SLOP-EXPORT-SPEC.md in a FRESH droid session), then assess oh-my-pi, then the parked production-readiness tickets. Operator opens droid tabs (`fleet-droid.sh <tier>`) — never launch droids or build products in the manager session. Work only under /home/stack/charon-private; pause after any question or handed-action.
```
