# Charon — next-session handoff (prepared 2026-06-26)

## ✅ PROGRESS (2026-06-26 later session — steps 1-3 of "DO, IN THIS ORDER" done)
On `master`, 177 tests green (ruff/mypy/boundary/version clean). **Commits NOT pushed**
— operator runs `! git push` (or `git -C <path> push`).
- **Step 1 — tickets organized:** `/home/stack/charon-private/TICKETS.md` (this dir).
  Non-colliding, file-disjoint, WAVE schedule. `coordinator.py` is the only real
  collision hotspot (T1/T7/T8 must serialize).
- **Step 2 — import-all-models BUILT + committed** (`38e640a`). All three surfaces +
  security guards + 10 tests. Plan note + self-review in `docs/REVIEW-LOG.md`.
- **Step 3 — ADR-0006 written + self-reviewed** (`cfe2f11`): `docs/adr/0006-…`
  PERF-4 + decomposition design gate. Implementation = ticket **T1** (not yet built).
- **NEXT:** hand T1 (PERF-4) to a droid — ADR is done, so it's ready to implement per
  TICKETS.md WAVE 1; then T2-T6 in parallel; T7/T8 in WAVE 2. (Original plan below.)

---


Charon **v0.2.0** is shipped: gateway-first (standalone gateway, transparent
cost-ranked failover, 13 presets + any base-URL provider, setup via CLI/wizard/web,
console, optional Docker). Public repo `SLOP-Platform/charon`, branch `master`.
**164 tests green.** README is now a lean user quickstart.

## House rules (follow exactly)
- **Plan-before-code:** any design decision opens with an ADR/plan note + an
  **adversarial self-review**, reconciled in `docs/REVIEW-LOG.md`, BEFORE code.
- **Keep the gate green every commit:** `pytest` (run as bare `pytest` / `PYTHONPATH=src`),
  `ruff check`, `mypy src/charon`, `python3 tools/check_boundary.py src`,
  `python3 tools/check_version.py`. **Check the gate result BEFORE committing.**
- Privileged core stays **stdlib-only**; new deps behind a pyproject extra. Conventional
  commits. `gh`/`git push` is harness-gated → operator runs `! git push` or use the
  `git -C <path> push` form. **Keys/secrets NEVER in the repo** (`~/.charon`, 0600).
- CI is `[self-hosted, 4-lom]` Linux. Adversarially review critical/security work.

## DO, IN THIS ORDER
**1. Organize all non-parked work into maximum-efficiency, NON-COLLIDING tickets
(Droid Robot Mode style).** Group by FILE: every edit to a given file goes in ONE
ticket; tickets that run in parallel must own **disjoint** file sets so droids never
touch the same file. Output a private tickets doc (NOT in the public repo). Each ticket
states: files owned, the change, tests, ADR/plan note if it's a decision, branch.

**2. BUILD import-all-models FIRST** (small, high-value; operator-requested 2026-06-26).
Pull a provider's full model list from its `/v1/models` (with the stored key) and add
them all to config — as a CATALOG (each becomes selectable / listed in `/v1/models`).
Surfaces: `charon models import <provider> [--free-only] [--into-pool <name>]`; a y/N
"import all N models?" prompt in `charon setup` after a provider+key is added; an
"import models" button + `POST /charon/models/import` on the web setup page. NOTE the
framing: this is for the catalog — POOLS stay curated (comparable, cost-ranked models),
do NOT dump all models into one failover pool. Files: `cli.py`, `gateway.py`
(setup_handler), `proxy_server.py` (web button/endpoint), `config.py` (bulk add).

**3. THEN PERF-4 + decomposition. Write ADR-0006** ("Parallel units +
work-decomposition") with an adversarial self-review, reconcile in REVIEW-LOG, BEFORE
implementing. Base it on:
- **PLAN-tier4 §3 (PERF-4):** `run_parallel(units, max_parallel)` bounded worker pool;
  **separate ledger + separate git worktree per unit** + per-task lock (non-collision).
  Open Qs **D1** isolation sufficiency (git global config, process env, the `.charon`
  parent, shared Budget counter), **D2** L3+parallel over-build. PLAN-tier4 §6 records
  binding fixes (escape-scan races on shared worktree parents, shared-budget overspend,
  sticky backend subprocess state).
- **ADR-0004 D6** (thin DAG-of-stages runner, no LangGraph) + **D8** (role decomposition
  Triage→Plan→Implement→Review→Validate) — analyze a ticket → roles → stages.
- Today only role→cost-ranked-model routing + cross-vendor failover exist (single unit,
  sequential). The gateway (v0.2.0) is the prerequisite that makes N parallel agents
  sustainable (spread load across providers).

**4. THEN the rest, by logical priority.**

**5. Hand off the tickets to Droids (Robot Mode)** — one droid per non-colliding
ticket-group, in parallel; draft PRs; operator merges.

## Non-parked work to organize (file hints for grouping)
Execution order: **(1) import-all-models → (2) PERF-4 + decomposition → (3) the rest.**
| Ticket area | Files (rough) |
|---|---|
| **import-all-models** (DO FIRST) | `cli.py` (models import + wizard prompt), `gateway.py` (setup_handler), `proxy_server.py` (web button/endpoint), `config.py` (bulk add) |
| **PERF-4 parallel units + `max_parallel`** (PRIORITY #2) | `coordinator`, `api.py`, `cli.py`; new `run_parallel`; worktree/ledger isolation |
| **Decomposition / triage + DAG runner** (PRIORITY #2) | new module(s); `router.py`; ledger metadata |
| L3 unattended autonomy | `fence`, `coordinator` |
| Live ACP↔ACP handoff (two real agents) | `adapters/acp.py`, `doctor.py` (integration/proof) |
| Tier-2b web/worker split (real `POST /v1/runs`) | `service/app.py`, new worker |
| Real consensus reviewer + circuit breaker | `adapters/review*`, `coordinator` |
| Gateway: default image CMD → gateway | `Dockerfile`, `docker-compose.yml`, README |
| Gateway: R10d downgrade normalization (prefix/normalized compare) | `proxy.py` (`classify`) |
| Gateway: more presets / real-provider quirks | `providers.py` |

## PARKED — do NOT schedule
- **Windows `.exe` packaging** (PyInstaller + `windows-latest` workflow) — future.
- **Deny-list guard fix** (`.claude/settings.local.json` `git -C`/interpreter bypass) —
  operator-only settings edit.

## Notes
- Estimates (rough): gateway polish ~2 days; PERF-4 + decomposition ~3–4 weeks; the
  rest of the orchestrator unbuilt ~2–3 weeks. Grand total ~6–8 weeks.
- The operator will route droids/OpenAI-compatible agents through the Charon gateway
  (`http://localhost:8080/v1`) to keep working when Claude Code weekly limits hit.
- Private docs live in `/home/stack/charon-private/` (HANDOFF.md original, this file).
