# Charon — droid ticket plan (Robot Mode, non-colliding) — 2026-06-26

Organizes all **non-parked** remaining work into file-disjoint tickets so droids can
run in parallel without ever touching the same file. **Rule:** every edit to a given
file lives in ONE ticket; tickets in the same WAVE own disjoint file sets.

Execution order (handoff): **import-all-models (DONE) → PERF-4 + decomposition → the rest.**

## Status
- ✅ **T0 import-all-models** — DONE this session, committed `38e640a`, gate green
  (177 tests). Files touched: `cli.py`, `config.py`, `gateway.py`, `providers.py`,
  `proxy_server.py`, `README.md`, `docs/REVIEW-LOG.md`, `tests/test_models_import.py`,
  `tests/test_config.py`.

## Model routing (tag each droid by the best model for the job)
Tier = how much reasoning/blast-radius the ticket carries (mirrors Charon's own
role→pool idea). Suggested models are from the operator's gateway presets; swap for an
equivalent in the same tier.
- 🔴 **Frontier** — deep reasoning / concurrency correctness / security-critical.
  Suggest **Claude Opus 4.8** (`claude-opus-4-8`). Needs the adversarial-review muscle.
- 🟠 **Strong** — real coding + live-integration / protocol fidelity / moderate
  judgment. Suggest **Claude Sonnet 4.6** (or Kimi-k2-code / GLM-4.6 via zai).
- 🟢 **Economy** — mechanical, well-scoped, low blast radius. Suggest **DeepSeek-V3**
  (or Qwen-Coder / a Groq Llama) — fast + cheap, spread load off the frontier pool.

| Ticket | Tier | Suggested model | Why this tier |
|---|---|---|---|
| T1 PERF-4 + decomposition | 🔴 Frontier | Claude Opus 4.8 | concurrency races, privileged-loop safety, the ADR's binding HIGHs |
| T2 downgrade normalize | 🟢 Economy | DeepSeek-V3 | tiny, contained `classify` bugfix |
| T3 more presets | 🟢 Economy | DeepSeek-V3 | data entry + live `providers test` |
| T4 Docker default CMD | 🟢 Economy | DeepSeek-V3 | config + docs, trivial |
| T5 live ACP↔ACP handoff | 🟠 Strong | Claude Sonnet 4.6 | real-agent protocol fidelity, debugging |
| T6 Tier-2b worker split | 🟠 Strong | Claude Sonnet 4.6 | web/worker boundary; exposed web must NOT run the loop |
| T7 L3 unattended autonomy | 🔴 Frontier | Claude Opus 4.8 | highest blast radius, fence/security-critical |
| T8 consensus + breaker | 🟠 Strong | Claude Sonnet 4.6 | correctness + judgment, moderate scope |

## Collision map (the only shared-file hotspots)
- `coordinator.py` — wanted by **T1 (PERF-4)**, **T7 (L3)**, **T8 (consensus)** → these
  three MUST be in different waves (serialize).
- `ledger.py` / `router.py` / `api.py` / `cli.py` — wanted by **T1** only (decomposition
  folded into T1, see below) → no cross-ticket collision once T1 owns them.
- Everything else (`proxy.py`, `providers.py`, Docker, `adapters/acp.py`+`doctor.py`,
  `service/`) is owned by exactly one ticket → freely parallel.

## Tickets

### T1 — PERF-4 parallel units + work-decomposition  (PRIORITY #2; do FIRST after T0)
- **Model:** 🔴 Frontier — Claude Opus 4.8.
- **Owns:** `coordinator.py`, `api.py`, `cli.py`, `router.py`, `ledger.py`, NEW
  `parallel.py` (run_parallel worker pool), NEW `decompose.py` (triage→roles→DAG).
  Tests: `tests/test_parallel.py`, `tests/test_decompose.py`, extend `test_coordinator.py`.
- **Why folded together:** PERF-4 and decomposition both need `coordinator`/`ledger`/
  `router` and are architecturally coupled (decompose a ticket → units → run_parallel).
  Splitting them collides on 3 files; one droid owns the whole vertical.
- **Gate first:** **ADR-0006** + adversarial self-review reconciled in `docs/REVIEW-LOG.md`
  BEFORE code (handoff step 3). Base: PLAN-tier4 §3/§6, ADR-0004 D6/D8. Resolve open Qs
  D1 (isolation: git global config, process env, `.charon` parent, shared Budget) and D2
  (L3+parallel over-build). Binding fixes from §6: escape-scan races on shared worktree
  parents, shared-budget overspend, sticky backend subprocess state.
- **Change:** `run_parallel(units, max_parallel)` bounded pool; **separate ledger +
  separate git worktree per unit** + per-task lock (non-collision); `--max-parallel` CLI
  flag; `api.run_task` orchestrates decompose→parallel.
- **Branch:** `feat/perf4-parallel-decomposition`.

### T2 — Gateway: R10d downgrade normalization
- **Model:** 🟢 Economy — DeepSeek-V3.
- **Owns:** `proxy.py` (the `classify` path). Tests: extend `tests/test_proxy.py`.
- **Change:** prefix/normalized compare so an upstream returning a normalized/alias model
  id (e.g. provider-prefixed) is not misflagged as a downgrade.
- **ADR:** none (bugfix-class); note in REVIEW-LOG.  **Branch:** `fix/gw-downgrade-normalize`.

### T3 — Gateway: more presets / real-provider quirks
- **Model:** 🟢 Economy — DeepSeek-V3.
- **Owns:** `providers.py`. Tests: extend `tests/test_providers.py`.
- **Change:** add presets + per-vendor quirks; verify bases live via `providers test`.
- **ADR:** none.  **Branch:** `feat/gw-more-presets`.

### T4 — Gateway: default Docker image CMD → gateway
- **Model:** 🟢 Economy — DeepSeek-V3.
- **Owns:** `Dockerfile`, `docker-compose.yml`, `README.md` (Docker section).
- **Change:** default container command runs `charon gateway`; compose service + docs.
- **ADR:** none.  **Branch:** `feat/docker-default-gateway`.

### T5 — Live ACP↔ACP handoff (two real agents)
- **Model:** 🟠 Strong — Claude Sonnet 4.6.
- **Owns:** `adapters/acp.py`, `doctor.py`. Tests: `tests/test_handoff_crossvendor.py`
  (integration/proof), extend `test_handoff.py`.
- **Change:** real cross-vendor handoff between two live ACP agents + a doctor proof.
- **ADR:** light plan note (integration shape).  **Branch:** `feat/live-acp-handoff`.

### T6 — Tier-2b web/worker split (real `POST /v1/runs`)
- **Model:** 🟠 Strong — Claude Sonnet 4.6.
- **Owns:** `service/app.py`, NEW `service/worker.py`. Tests: extend
  `tests/test_service_api.py`, `test_service_main.py`.
- **Change:** real run submission + background worker (web/worker split).
- **ADR:** plan note (queue/worker boundary).  **Branch:** `feat/tier2b-worker`.

### T7 — L3 unattended autonomy
- **Model:** 🔴 Frontier — Claude Opus 4.8.
- **Owns:** `fence.py`, `coordinator.py`. Tests: extend `test_fence.py`,
  `test_coordinator.py`.
- **Change:** L3 unattended autonomy gate + fence policy.
- **ADR:** plan note (autonomy escalation; security-sensitive — adversarial review).
- **Branch:** `feat/l3-unattended`.  ⚠ collides with T1 & T8 on `coordinator.py`.

### T8 — Real consensus reviewer + circuit breaker
- **Model:** 🟠 Strong — Claude Sonnet 4.6.
- **Owns:** `adapters/review_mock.py` → real reviewer, NEW `adapters/review.py`,
  `ports/reviewer.py`, **circuit breaker in `failover.py`** (NOT coordinator, to
  decouple from T7). Tests: extend `test_consensus_gate.py`, `test_failover.py`.
- **Change:** real consensus reviewer adapter + circuit breaker on repeated failures.
- **ADR:** plan note.  **Branch:** `feat/consensus-breaker`.
- ⚠ **If** the breaker must live in `coordinator.py` instead, T8 collides with T1/T7 and
  drops to WAVE 3. Putting it in `failover.py` keeps it parallel-safe in WAVE 2.

## OUTSTANDING WORK — post-WAVE-1 (2026-06-26)
WAVE 1 (T1–T6) is DONE + merged. Remaining non-parked work = T7, T8 (above) + the
**ADR-0007 first increment** decomposed below (N1–N4). Run via the **droid-fleet method**
(Claude Code worker per ticket); workers route model calls through the Charon **gateway**
(`http://localhost:8080/v1`) to dogfood failover. **Default = PROPOSE** (PR per ticket,
operator merges) per ADR-0007 D4. The full Charon work-engine that would self-run this is
the very thing N1–N4 build, so it can't self-orchestrate yet.

### N1 — Per-unit git worktree off base (ADR-0007 D2)
- **Model:** 🔴 Frontier — Claude Opus 4.8.  **Branch:** `feat/per-unit-worktree`.
- **Owns:** `api.py` (`_prepare_repo`: create a per-unit `git worktree add` off base for
  REAL repos too, nested so `guard_dir` is unique per unit), `coordinator.py` (guard_dir),
  `gitutil.py` (worktree helper). Tests: extend `test_parallel.py`, `test_coordinator.py`.
- **Why:** today real `--repo` units share one tree + guard_dir (verified) — the one
  genuinely-missing isolation primitive + prerequisite for branch-based landing.

### N2 — `charon land`: propose-default gated landing (ADR-0007 D4/D6 + D3 units loader)
- **Model:** 🔴 Frontier — Claude Opus 4.8.  **Branch:** `feat/charon-land`.
- **Owns:** NEW `land.py`, `cli.py` (`charon land` + a `--units <file>` loader for
  consumer-supplied units). Tests: NEW `test_land.py`.
- **Change:** take a completed unit's branch → run the gate (diff-scope guard +
  sensitive-path HOLD + acceptance/tests + gitleaks-if-present) → **green = open PR /
  advance lkg; red = hold.** Default propose (human merges); batch-atomic auto-land is a
  later opt-in. Reads ledgers/worktrees (from N1); does NOT modify `api.py`.

### N4 — End-product Validator (ADR-0007 D12)  [lower priority]
- **Model:** 🟠 Strong — Claude Sonnet 4.6.  **Branch:** `feat/validator`.
- **Owns:** NEW `validate.py`, `decompose.py` (role wiring). Tests: NEW `test_validate.py`.
- **Change:** a Validate worker runs ONCE on the integrated result vs. a top-level
  acceptance; quality gate, NOT a trust boundary. Partial until ADR-0008 captures a
  product-level acceptance — meantime validates against the unit-level acceptance.

### Outstanding wave schedule (disjoint files per wave)
- **WAVE 2-A (launch now):** **N1** ‖ **N2** ‖ **T8**
  - disjoint: N1{api,coordinator,gitutil} · N2{land,cli} · T8{adapters/review*,ports/reviewer,failover} ✓
  - (N2 integration assumes N1's worktrees; files are disjoint so they build in parallel, integrate after.)
- **WAVE 2-B (after N1 merges → coordinator.py):** **T7** ‖ **N4**
  - disjoint: T7{fence,coordinator} · N4{validate,decompose} ✓
- Prompts: `t7.md`, `t8.md` exist; `n1.md`, `n2.md` added; `n4.md` draft-when-N4-starts.

## Wave schedule (each wave = parallel droids on disjoint files; waves serialize)
- **WAVE 1:** T1 ‖ T2 ‖ T3 ‖ T4 ‖ T5 ‖ T6
  - disjoint check: T1{coordinator,api,cli,router,ledger,parallel,decompose} ·
    T2{proxy} · T3{providers} · T4{Dockerfile,compose,README} · T5{adapters/acp,doctor} ·
    T6{service/app,service/worker} → ✅ no overlap.
- **WAVE 2 (after T1 merges):** T7 ‖ T8
  - T7{fence,coordinator} · T8{adapters/review*,ports/reviewer,failover} → ✅ disjoint
    **iff** the breaker is in `failover.py`. (Else T8 → WAVE 3.)

Note: T7 & T8 wait for WAVE 1 because both build on T1's coordinator changes (rebase on
merged T1, not the pre-T1 coordinator).

## Hand-off to droids
One droid per ticket, draft PRs, operator merges. Each droid: branch as named, keep the
gate green every commit (`pytest` / `ruff check` / `mypy src/charon` /
`tools/check_boundary.py src` / `tools/check_version.py`), stdlib-only in privileged
core, no keys in the repo. Tickets needing an ADR/plan note must land that + the
adversarial-review reconciliation in `docs/REVIEW-LOG.md` BEFORE code.
