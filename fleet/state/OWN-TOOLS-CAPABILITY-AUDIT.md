# OWN-TOOLS-CAPABILITY-AUDIT — unused capability vs. open problems

**Date:** 2026-08-01 · **Session:** own-tools-capability-audit · measured on this box, NOT read from docs.
**Paired with:** WORKFLOW-E2E-AUDIT (maps pipeline failures; this maps owned capabilities that could close them).

---

## HONEST HEADLINE: ~20% surface utilization, INERT checks guarding seams that leak, and 1 CLAIMED-BUT-ABSENT guarantee already coded against

Every adopted tool is 10–55% wired. The prior audits (TOOL-UTILIZATION-AUDIT, WIRING-AUDIT-MATRIX) covered the linter/analyzer + gateway-module surfaces. This audit covers the FULL inventory: fleet scripts, product gates, MCP servers, CI tools, and the E2E pipeline. **52 tools audited; 37 have measurable unused capability; 9 fleet checks are INERT (wired nowhere); 1 CLAIMED-BUT-ABSENT guarantee (Faktory exactly-once) is already coded against.**

---

## 1. PER-TOOL TABLE

### 1.1 PRODUCT GATE SUITE (13 checks + registry)

| Tool | Full surface | Used | Delta (unused) | Claimed-but-absent | Inert? |
|---|---|---|---|---|---|
| `charon.cli gate` umbrella | 13 `check_*.py` + `render_review_log.py` + `gates.json` registry | Subset — umbrella invokes <13 (gates.json registered set ≠ umbrella invocations per TOOL-INVENTORY) | check_test_patterns, check_public_clean, check_workflows, check_catalog_case_quant, check_decisions, render_review_log — existence in gates.json not verified as live-invoked | "gates.json is the registered set" but umbrella runner diverges from it | No (core subset active) |
| `check_gate_registry.py` | Self-validator: no duplicate/overlapping gates, every gate has living enforcer | YES — active | — | — | No |
| `check_inert_code.py` | Reachability-from-entrypoint dead-code detector with disposition ledger | YES — active in product CI | — | — | No |
| `gates.json` | Gate registry with `enforcer`, `covers`, `invariant`, `red_proof` per entry | Wired but umbrella invocations not 1:1 with registered set | Registry as single source of truth vs umbrella runner is a seam | Per TOOL-INVENTORY §3: "see `tools/gates.json` for the full registered set vs. what the umbrella actually invokes, they are not 1:1 today" | No |

**E2E pipeline hit:** GATE stage — if gates.json declares a gate that the umbrella SKIPS, it is silent false-green. This directly enables the "merged-but-not-done" class (failure #1): no gate checks that done-marking ran because no gate enumerates the full set.

### 1.2 graphify

| Capability | Used? | Delta mapped to open problem? |
|---|---|---|
| `update` | YES (114 call sites) | — |
| `path` | YES (42) | — |
| `explain` | YES (33) | — |
| `watch` | YES (18) | — |
| `diagnose multigraph` | YES (3) | — |
| `affected` (reverse traversal / blast-radius) | **0 uses** | **WORKFLOW-E2E-AUDIT failure #7 (stale real-dep):** `graphify affected` could map all dependents of a changed file, validating `depends_on:` entries. Also cited in HAND-ROLLED-AUDIT.md but 0 call sites. |
| `merge-graphs` / `merge-driver` | **0 uses** | Cross-repo reachability (charon ↔ charon-private) — PRIORITY-TODO item |
| `save-result` | **0 uses** | QA feedback loop for graph quality |
| `clone` / `add` / `cluster-only` / `label` / `install` / `uninstall` | **0 uses** | Lower priority |

**Claimed-but-absent:** None.
**Inert:** No — core subcommands are wired. But `affected` is cited as a method in HAND-ROLLED-AUDIT.md while having 0 real invocations — effectively claimed-but-unused.

### 1.3 Keystone Framework (KSF)

| Capability | Used? | Delta mapped to open problem? |
|---|---|---|
| `reuse-check` (token-Jaccard similarity) | **0 fleet call sites** | **CREATE stage:** reuse-check would prevent duplicate-proposal creation. Currently the board has NO mechanical duplicate detector — droids eyeball the board manually. Closes the "merge resolution destroyed 10 tickets" class (failure #6) by detecting double-creation |
| `module register` | **0 fleet call sites** | Module lifecycle tracking — no module in Charon is registered |
| `gate` (9 built-in gates) | **Only 1 of 9** (inert_code, via vendored adapter) | 8 KSF gates unused: coverage_ssot, wiring_alignment, redproof, leak_guard, no_pipe_mask, no_skip_game, no_vacuous, fail_loud |
| `reconcile` | **0 fleet call sites** | Re-resolves falsified close_proofs — mechanism for self-healing stale decisions |
| `verify-self` | **0 fleet call sites** | Dogfood meta-harness |

**Claimed-but-absent:** Charon's `.ksf/keystone.db` exists with tables `decisions`, `built_inventory`, `backlog` — **all empty**. Initialized but never populated. No module/decision has been registered against it. The DB claims to be a decision registry but stores nothing.
**Inert:** The live `ksf` CLI's subcommands (reuse-check, module register, gate, reconcile, verify-self) are NOT wired into any fleet script — admitted as "a gap, not a dead end" in TOOL-INVENTORY.md §2.

### 1.4 litellm / litellm.Router

| Capability | Used? | Delta mapped to open problem? |
|---|---|---|
| `litellm.Router` (52 params) | **~5 params used** | cost_rank ordering (NOT routing strategy — that raises RouterRateLimitError on sync path per AUDIT-UNDERUSED-ADOPTED-TOOLS) |
| pricing DATA (`model_prices_and_context_window.json`) | ADOPTED, shipped | — |
| tool-call translation | NOT adopted | — |
| cost-based routing via `order` param | **NOT wired** | **SCHEDULE/CLAIM stage:** 212 of 859 catalog entries carry `cost_rank` but the gateway ordering ignores it. The DATA is present, the CODE does not use it. |
| `litellm_plane` | **Imported by TESTS ONLY** | Largest inert subsystem in product tree |

**Claimed-but-absent:** None from litellm directly. But the full-provider-cooldown/health-circuit was stated as "litellm.Router handles this" — while the Router is adopted as a library, the cooldown/health logic is not yet wired through it on the real request path.
**Inert:** `litellm_plane` is the largest inert subsystem: all ~2000 LOC imported by test files only.

### 1.5 ruff

| Capability | Used? | Delta mapped to open problem? |
|---|---|---|
| 962 rules | **~150 active** (195 reachable, 45 preview-gated) | `--select ALL` = 2981 rules; ALL+preview = 3934 |
| `preview = true` | **NOT enabled** | 12 defects inside families we ALREADY select, 7 auto-fixable. One line. |
| `extend-select = ["S","BLE","ARG","C90"]` | **NOT enabled** | 184 findings, 3 HIGH-severity security. S family = 100% overlap with bandit (proven). ARG = 50 findings vs pylint W0613 = 46 — more with 0 new deps. |
| `[tool.ruff.lint.mccabe] max-complexity` | **NOT configured** | C90 = 62 C901 findings |
| Per-rule config sub-tables | **NOT used** | — |
| ruff format (formatter) | **NOT adopted** | — |

**Claimed-but-absent:** None. ruff's capability is documented; what's claimed-but-absent is the *incumbent configurability* in prior evals (see under-scoped trial findings in TOOL-UTILIZATION-AUDIT §THREE).
**Inert:** No — active in product CI. But 85% of rules are selected OFF.

### 1.6 mypy

| Capability | Used? | Delta mapped to open problem? |
|---|---|---|
| 14 strictness components | **0 of 14 enabled** | check_untyped_defs (33), warn_unreachable (58), warn_return_any (85), disallow_any_generics (448), warn_unused_ignores (153) |
| `--strict` | No (2311 findings) | Deliberately SKIP `disallow_untyped_defs` (1952 findings = churn, not signal) |

**E2E relevance:** Typed money-path code (forwarder, proxy_server) would be GATE-enforceable. Currently 0 type-enforcement beyond default mypy.
**Inert:** Present in CI but minimal config. Effective surface = default mypy run only.

### 1.7 pytest

| Capability | Used? | Delta mapped to open problem? |
|---|---|---|
| 10 installed plugins | **xdist only** | timeout (no `--timeout`/`-p timeout` in any config), randomly (order-dependent test detection), hypothesis (property-based), playwright (browser E2E), asyncio, base-url, schemathesis, syrupy, anyio |
| `addopts` | 0 in any config (grep=0) | — |

**E2E relevance:** `pytest-timeout` would prevent GATE deadlock from hung tests. `pytest-randomly` would catch order-dependent failures (the "CI deadlocked 2 PRs" class, failure #10 — order-dependent passes).
**Inert:** 9 of 10 plugins installed but never configured. `pytest.ini` content = `norecursedirs` only.

### 1.8 shellcheck

| Capability | Used? | Delta mapped to open problem? |
|---|---|---|
| 4 severities | YES — default only | — |
| 11 optional checks | **0 of 11 enabled** | `check-set-e-suppressed` = 1696 findings across fleet. `check-extra-masked-returns` = 21. |
| Product CI | **NOT in product CI** (rig-only) | 277 fleet `.sh` files un-scanned in product gate path |

**E2E relevance:** `check-set-e-suppressed` = 15 findings on `fleet-droid.sh` alone. The set-e suppression bug class was reported (SHELLCHECK-SETE-EVAL) but never fully enabled. Silent failures in fleet scripts (WORK stage) survive because the checker is configured to skip them.
**Inert:** 11 optional checks = inert. Product CI coverage = 0.

### 1.9 bandit

| Capability | Used? | Delta mapped to open problem? |
|---|---|---|
| 75 test plugins | rig CI only, 0 product CI | Product run; **100% overlap with ruff S family with `--preview`** (proven 2026-08-01) |
| bandit-config-generator | 0 uses | — |
| bandit-baseline | 0 uses | — |

**Claimed-but-absent:** The EVAL-REGISTRY bandit row (:65) claimed "net-new danger-pattern coverage the rig has no gate for." FALSE — ruff's S family (flake8-bandit, 73 rules) was ADOPTED and in CI before bandit. MEASURED: bandit 58 findings vs `ruff --select S --preview` covering 100% (8 of 9 test ids map 1:1, the 9th is preview-gated S404 = 9). **UNDER-SCOPED TRIAL** — reclassified `drifted` 2026-08-01.
**Inert:** Effectively inert as a UNIQUE check — duplicates an adopted linter's capability.

### 1.10 gitleaks

| Capability | Used? | Delta mapped to open problem? |
|---|---|---|
| Secret scanning | CI required-check on merge boundary | Pre-commit hook (local guard), custom `.gitleaks.toml` (relies on default) |

**E2E relevance:** PR/COMMIT merge boundary. Wired and working.
**Inert:** No.

### 1.11 semgrep

| Capability | Used? | Delta mapped to open problem? |
|---|---|---|
| Custom rules (`fleet/semgrep-rules/charon-policy.yml`) | CI required-check | 1000+ community rules, autofix, taint tracking |

**E2E relevance:** GATE/PR merge boundary. Only enforcer covering the opencode leg and non-Claude harness. Wired and working.
**Inert:** No.

### 1.12 pip-audit

| Capability | Used? | Delta mapped to open problem? |
|---|---|---|
| Dependency vulnerability audit | ADOPTED in CI | `--fix` (auto-upgrade), `--require-hashes`, cyclonedx output |

**Inert:** No.

### 1.13 opencode (the CLI harness)

| Capability | Used? | Delta mapped to open problem? |
|---|---|---|
| `run` (with message) | Primary droid invocation via `fleet-droid.sh` | — |
| `serve` (headless server) | **0 uses** | Connect via HTTP for headless operation — would enable remote droid control |
| `web` | **0 uses** | — |
| `acp` (Agent Client Protocol) | **0 uses** | Standardized agent control plane |
| `session` management | Partial | Export/import for session portability |
| `db` tools | **0 uses** | Session database inspection |
| `providers` management | **0 uses** (we use our own gateway) | — |
| `models` | Likely used | — |
| `stats` (token/cost) | **0 uses** | Per-droid cost tracking — would directly feed model-scorecard live data |
| `plugin` system | **0 uses** | Extensibility |
| `mcp` server management | Partial | — |
| Permission system | Configured | Subagent-bypass bug (issue #5894, OPEN) |

**Claimed-but-absent:** opencode's `tool.execute.before` hook claimed as enforcement — but has subagent-bypass bug (same class Claude Code just closed). EVAL-REGISTRY row :60 correctly notes this.
**Inert:** No — actively used. But ~60% of subcommands are unused.

### 1.14 gh (GitHub CLI)

| Capability | Used? | Delta mapped to open problem? |
|---|---|---|
| `gh api` REST | 49 call sites per TOOL-UTILIZATION-AUDIT | — |
| `--jq` | 55 uses | — |
| `--cache` | 8 uses | — |
| `--paginate` | **0 uses** | Large result sets silently truncated (max 100 per page) |
| `gh api graphql` | **0 deliberate endpoint choices** | **PR stage (failure #2 — DRAFT PRs):** GraphQL can bulk-query PR state, status checks, review status in ONE round-trip vs N REST calls |
| `gh search` | **0 uses** | **MERGE stage:** Bulk PR discovery across all fleet repos |
| Rate-limit-aware retry | gh-cache.sh provides batching; no inherent retry | — |

**E2E relevance:** gh-cache.sh is the fleet's rate-limit defense — it batches O(PRs) into two calls. This is the CORRECT pattern. But the underlying `gh` capability (`--paginate`, GraphQL) that would further reduce call count is unused.
**Claimed-but-absent:** `gh-cache.sh`'s comment about "the next-to-burn tier" (GraphQL search) is accurate — documented gap, not claimed capability.
**Inert:** No.

### 1.15 Faktory

| Capability | Used? | Delta mapped to open problem? |
|---|---|---|
| `push` | YES (lease-enqueue.sh) | — |
| `reserve` (with timeout) | YES | — |
| `ack` | YES | — |
| `fail` | YES | — |
| `info` | YES | — |
| `beat` (heartbeat) | **0 uses** | Worker liveness detection — would close silent worker death (loop-guard false-negative class) |
| Web UI | **Likely 0 production monitoring** | — |
| Enterprise: unique jobs | **NOT available (OSS limitation)** | exactly-once semantics |
| Enterprise: cron scheduling | N/A | — |
| Enterprise: batch operations | N/A | — |

**Claimed-but-absent — LOUD FLAG:** **`CLAIM-LEASE-EXACTLY-ONCE`.** Our test suite (`fleet/tests/lease-exactly-once.test.sh`) codes against "an ACKed ticket cannot be re-fetched" — a guarantee OSS Faktory does NOT provide. Unique-job deduplication is an ENTERPRISE feature. The test properly gates on real Faktory availability and reports PENDING-FAKTORY when absent, but the test's EXISTENCE with an exactly-once assertion means something in our pipeline (lease-enqueue.sh) is counted on to provide exactly-once. **Coding against a guarantee the tool does not make is the most dangerous class** — precedent: Faktory's own exactly-once, recorded in the ticket's note as the precedent for this audit.
**Inert:** Worker plane inert — `faktory-worker.sh` and `faktory-client.sh` exist but have **0 production workers** (Faktory was adopted, the worker NEVER wired).

### 1.16 session-bridge

| Capability | Used? | Delta mapped to open problem? |
|---|---|---|
| `register` / `board` / `update` / `claim` / `release` / `nudge` | YES (via opencode MCP tools) | — |
| `ack` (message acknowledgment) | **Not observed** | Messages may accumulate without explicit clear |
| Graduated response (nudge→escalate→purge) | Automatic | — |
| Board advisories | Automatic | — |

**Claimed-but-absent:** Session records carry **NO `model` field** (confirmed by `fleet/capability/availability.py`: "confirmed by reading /home/stack/.config/opencode/session-bridge/proxy.py"). The `assign.py` availability query therefore cannot differentiate sessions by model — all sessions look identical. This is a KNOWN GAP, documented, not hidden.
**Inert:** No — actively used.

### 1.17 basic-memory

| Capability | Used? | Delta mapped to open problem? |
|---|---|---|
| MCP server (12 tools: search-notes, read-note, write-note, etc.) | Partially wired | — |
| `project` (multi-project) | **0 uses** | Cross-repo memory scoping |
| `cloud` (remote sync) | **0 uses** | — |
| `ci` (GitHub delivery capture) | **0 uses** | Automatic memory from PR/merge events |
| `orphans` (unlinked entity detection) | **0 uses** | **REVIEW stage:** Surfaces handoff notes with no connected code/decision — the "stranded context" detection class |
| `import` | **0 uses** | Migration from legacy memory/ |
| `tool` (MCP tools via CLI) | **0 uses** | Scriptable memory access outside MCP sessions |

**Inert:** Adoption incomplete — 2 of 4 adoption tickets done (per ticket note: "4-ticket adoption | 2 done").

### 1.18 FLEET RIG SCRIPTS (83 top-level — E2E pipeline mapping)

#### ACTIVE and WIRED by pipeline stage:

| Stage | Scripts | Wired? | Notes |
|---|---|---|---|
| CREATE | `validate_board.sh`, `wci-contention.sh`, `preflight.sh`, `decompose.sh`, `board.sh` | Wired | `decompose.sh` is DEC-DRIVER; `preflight.sh` runs reds test |
| SCHEDULE | `claim.sh`, `assign.sh`, `fleet-droid.sh`, `launch-plan.sh`, `foreman.sh` | Wired | `foreman.sh` drives cadence; `assign.py` feeds capability grades |
| CLAIM | `claim.sh`, `work-lease.sh`, `board-lock.sh`, `claim-jedi-name.sh` | Wired | `board-lock.sh` prevents double-claim |
| WORK | `fleet-droid.sh`, `charon-run.sh`, `leak-guard.sh`, `loop-guard.sh` | Wired | `leak-guard.sh` catches main-checkout writes; `loop-guard.sh` quarantines |
| GATE | `land.sh`, `push-verify.sh`, `gate.sh` | Wired | `land.sh` refuses on red |
| COMMIT/PUSH | `land.sh`, `land-push.sh`, `land-needs-push.sh`, `submit.sh` | Wired | — |
| PR | `submit.sh` | Wired | opens PR |
| REVIEW | `review-pool.sh`, `reject.sh` | Wired | reviewer != builder enforcement |
| MERGE | `land.sh`, `reconcile-merged.sh`, `verify-merged.sh` | Wired | — |
| CLOSE | `done.sh`, `retire-done.sh`, `branch-reaper.sh`, `reap-orphans.sh`, `release.sh` | Wired | `reap-orphans.sh` + `branch-reaper.sh` = worktree cleanup |
| REPORT | `report.sh`, `handoff.sh`, `model-scorecard.sh`, `check-session-report.sh` | Wired | `handoff.sh` generates session handoff |

#### INERT FLEET SCRIPTS (from gate-integrity.sh scan, executed 2026-08-01):

| Script | Gate-integrity finding | What it would catch | Maps to E2E failure |
|---|---|---|---|
| `fleet/checks/board-file-ratchet.sh` | G1 INERT | Board file count never decreases without explicit remove | Failure #6 (merge destroys tickets) |
| `fleet/checks/egress-key-canary.sh` | G1 INERT | Egress proxy key liveness | Security class — keys silently die |
| `fleet/checks/gate-creation-standard.sh` | G1 INERT | New gates follow creation standard (red-proof, etc.) | Gate quality degradation over time |
| `fleet/checks/large-file-guard.sh` | G1 INERT | Files exceeding size threshold | Performance creep |
| `fleet/checks/reconcile-board-pr-done.sh` | G1 INERT | **MERGED but not marked done** | **Failure #1 (19 tickets merged-but-submitted)** |
| `fleet/checks/reconcile-review-gate.sh` | G1 INERT | Review gate consistency | Failure #2 (draft PRs never reviewed) |
| `fleet/checks/registry-discovery.sh` | G1 INERT | EVAL-REGISTRY / tool-inventory freshness | Tool inventory drifts from actual usage |
| `fleet/checks/selfcheck-cycle.sh` | G1 INERT | Gates checking themselves (cycle detection) | Self-verification integrity |
| `fleet/checks/stuck-ticket-loud.sh` | G1 INERT | **Tickets stuck with no movement** | **Failure #3 (46 tickets never dispatched), #4 (false quarantine)** |

Additionally, `dark-work-check.sh` was previously flagged INERT (G1). Now wired through `foreman-cadence.sh` — RESOLVED.

#### UNPROVEN TESTS (exist but never run in CI):

8 test suites exist but are absent from `CI_SUITES` allowlist in `rig-ci-scope.sh`: bandit-canary, config-ssot-gate, registry-catalog, egress-key-canary, gate-creation-standard, gate-parity, gitleaks-canary, graphify-freshness. These suites have NEVER executed in CI — their green is assumed, not observed.

### 1.19 REMAINING TOOLS (installed, low or zero utilization)

| Tool | Status | Capabilities unused |
|---|---|---|
| yamllint | Installed, **0 uses**, 0 config | 95 findings on fleet YAML, no config file |
| actionlint | Installed, **0 uses**, orphan config | 30+ checks + embedded shellcheck for GitHub Actions `run:` blocks. 0 findings on current workflows. |
| vulture | Installed, used ad-hoc for evals | `--make-whitelist`, `--ignore-decorators`, `--config` |
| deadcode | Installed, used ad-hoc | `--fix`, `--dry`, 11 `--ignore-*-if-*` predicates. **No config-file support at all** |
| pylint / pyreverse / symilar | Installed, **0 ad-hoc uses** | W0613 unused-argument already covered by ruff ARG |
| mutmut | Installed, **0 uses** | Mutation testing — never run |
| diff-cover / diff-quality | Installed, **0 uses** | Diff-based coverage — never run |
| git-filter-repo | Installed, **0 references** | Repository history rewriting |
| ~30+ `~/.local/bin` scripts | Installed, **0 references in any fleet doc** | Unknown capability |

---

## 2. RANKED LIST — UNUSED CAPABILITIES THAT MAP TO MEASURED OPEN PROBLEMS

Ranked by: **which E2E failure it closes × how much capability already exists × cost to enable**.

### TIER 1 — enable today, closes measured failures (no new tools)

1. **`fleet/checks/reconcile-board-pr-done.sh`** — INERT. Closes failure #1 (19 tickets merged but still `submitted`). **The detection exists, the wire does not.** Wire into preflight/land or foreman cadence. Cost: one line in a calling script.

2. **`fleet/checks/stuck-ticket-loud.sh`** — INERT. Closes failure #3 (46 tickets never dispatched — oldest 22 days) AND failure #4 (false quarantine). The detector exists; wire it. Cost: one line.

3. **`fleet/checks/board-file-ratchet.sh`** — INERT. Closes failure #6 (merge destroyed 10 tickets). File-count never-decrease guard. Cost: one line.

4. **`graphify affected <file>`** — capability exists, 0 invocations. Closes failure #7 (stale `real-dep` — validates `depends_on:` entries against actual code impact). The graph is built (114 `update` call sites); the blast-radius query has 0 invocations. Cost: one invocation per changed file in preflight/land.

5. **`shellcheck -o check-set-e-suppressed` on fleet scripts** — 1696 findings, 15 on `fleet-droid.sh` alone. Closes the set-e tab-kill class that silently fails scripts at WORK/GATE stages. Cost: one flag.

6. **ruff `preview = true`** — 12 defects inside families we ALREADY select, 7 auto-fixable. One line. Also enables S404 which closes the bandit redundancy — we could DROP bandit from CI and run `ruff --preview --select S`.

### TIER 2 — enable within the sprint, closes open seams

7. **`gh api graphql` for bulk PR state queries** — REST `gh pr list` does N+1 calls; GraphQL does one. Closes failure #2 (9/10 draft PRs — detection exists, would surface in realtime). `gh-cache.sh` pattern is already built; GraphQL is the next tier its own comment documents.

8. **pytest `--timeout` + `pytest-randomly`** — 0 config in any file. Closes failure #10 (CI deadlocked two PRs — order-dependent passes survive because no randomization). Cost: two `addopts` lines.

9. **mypy `check_untyped_defs` + `warn_unreachable` + `warn_return_any`** — 33 + 58 + 85 = ~176 findings. Not churn (skip `disallow_untyped_defs` at 1952). Cost: 3 config lines.

10. **ruff `extend-select = ["ARG","C90"]`** — 50 ARG + 62 C901. Closes the "unused-argument" class that was claimed pylint-only (UNDER-SCOPED TRIAL). Cost: one config line, zero new deps.

### TIER 3 — real improvement, needs a ticket-sized change

11. **Faktory `beat` (heartbeat)** — worker liveness without loop-guard false positives. The client supports `info`; beat monitoring is a thin wrapper. Closes failure #4 (false quarantine on INFRA fault — beat would distinguish "healthy but idle" from "dead").

12. **KSF `reuse-check` wired into CREATE stage** — prevents duplicate proposals. Combined with `graphify affected`, this creates a mechanical "do we already have X?" answer at ticket-creation time. Cost: one fleet script wrapping `ksf --repo-root <repo> reuse-check`.

13. **Litellm `order` param for cost_rank routing** — 212 of 859 catalog entries carry `cost_rank`; the gateway ignores it. The DATA is wired (pricing JSON), the CODE is not. Cost: one routing param in gateway config.

14. **`fleet/checks/reconcile-review-gate.sh`** — INERT. Closes failure #2 (draft PRs never reviewed) from the review stage rather than the PR stage. Complementary to `gh api graphql` approach.

15. **`graphify merge-graphs`** — cross-repo reachability (charon ↔ charon-private). `graphify update` already runs on both repos; merging the graphs would surface cross-repo blast-radius. Relevant to PRIORITY-TODO's `REPO-MAP-CONVERGE`.

---

## 3. CLAIMED-BUT-ABSENT — capabilities asserted but not present

Ranked by danger (what depends on the absent capability):

| # | Tool | Claimed capability | Actual state | What depends on it | Danger |
|---|---|---|---|---|---|
| **1** | **Faktory (OSS)** | **Exactly-once job delivery** ("an ACKed ticket cannot be re-fetched") | OSS Faktory does NOT provide unique-job deduplication — it is an Enterprise feature. OSS reserves with timeout; re-enqueue of same jid creates a second job. | `lease-exactly-once.test.sh` explicitly codes against this guarantee. `lease-enqueue.sh` has a dedup guard (`live_faktory_job`) but the `revert_dedup` test path proves it's reachable. | **CRITICAL** — precedent class: coding against a guarantee the tool doesn't make. This IS the pattern the ticket note cites as the precedent. |
| **2** | **bandit (EVAL-REGISTRY :65)** | "Net-new danger-pattern coverage the rig has no gate for" | ruff's `S` family was ADOPTED and in CI before bandit. MEASURED: `ruff --select S --preview` reproduces 100% of bandit's findings. | The bandit adoption row itself. The CI step runs but produces 0 UNIQUE signal. | **HIGH** — false dependency: we adopted, configured, and maintain a security tool whose entire detection surface is already covered by an adopted linter. Ops burden with 0 marginal signal. |
| **3** | **pyscn (EVAL-REGISTRY :79)** | "Fills uncovered gaps in code-quality gate suite" — specifically "cognitive complexity" as an uncovered gap | ruff HAS a C90 (mccabe) family — 62 C901 findings. `PL` family ports pylint including complexity rules. C90 and cognitive complexity thresholds are unconfigured ruff sub-tables, not an absent capability. | The pyscn ADOPT row. Partial signal survives (duplicate-code, architecture analysis). | **MEDIUM** — under-scoped trial. The complexity gap is real but the claim it's "uncovered" by the incumbent is false. |
| **4** | **pylint W0613 (EVAL-REGISTRY :83)** | "The ONLY class no other tool fully covers" | ruff ARG family = 50 findings vs pylint W0613 = 46. ruff finds MORE, with 0 new deps. | The pylint ADOPT recommendation. | **MEDIUM** — under-scoped trial. The gap is real but the claim it requires pylint is false. |
| **5** | **KSF (`charon/.ksf/keystone.db`)** | Decision/built_inventory/backlog registry | All three tables EMPTY. DB initialized, never populated. Zero modules registered, zero decisions recorded. | Any process that consults the KSF DB expecting populated state. Currently none — it's inert. | **LOW** — zero dependents today. Becomes HIGH the first time something reads it and expects content. |
| **6** | **session-bridge** | Session model identification | Records carry NO `model` field (confirmed from proxy.py source). `capability/assign.py` and `capability/availability.py` both document this as KNOWN GAP. | `assign.py` availability queries — all sessions look identical regardless of model. | **LOW-MEDIUM** — KNOWN GAP, documented. But model-differentiated scheduling cannot work without it. |

---

## 4. INVENTORY COVERAGE — HONEST STATEMENT

### Fully audited (verified by execution + source read)

- ruff (rule surface + config keys from `--help` + executed rule counts)
- mypy (14 strict components from `--help`)
- pytest (plugins from `pytest --trace-config`)
- shellcheck (11 optional checks from `--list-optional`, executed counts)
- graphify (15 subcommands from `--help`, usage counts from grep)
- gh (API surface from fleet script grep, `--help` flags)
- Faktory (OSS feature set from README, 5 verbs from faktory-client.sh source)
- opencode (22 subcommands from `--help`)
- pip-audit (flags from `--help`)
- basic-memory (16 commands from `--help`)
- bandit (75 plugins, overlap with ruff S proven)
- gate-integrity scan (executed — 9 inert checks, 8 unproven tests)
- Fleet script wiring (call-site counts from grep, INERT list from gate-integrity)

### Partially audited (source-read, not all surface enumerated)

- KSF: 5 CLI subcommands verified from `--help`. 9 built-in gates identified from KSF source tree (ksf/gates/*.py). Individual gate logic NOT individually verified — the gates directory was not traversed.
- litellm.Router: ~52 params cited from prior audit. Individual param semantics NOT verified — the full litellm source was not instrumented.
- session-bridge: proxy.py/daemon.py source located but NOT fully read — the `model` field absence was confirmed from `availability.py`'s own read of proxy.py. Full internal state machine (graduated response, purge logic) NOT verified.
- gh GraphQL API: schema NOT enumerated (5000+ fields). The claim of 0 deliberate endpoint choices comes from gh-cache.sh's own comments + TOOL-UTILIZATION-AUDIT.
- actions/semgrep/gitleaks rulesets: Custom rules read (semgrep-rules/charon-policy.yml). Full community registry NOT enumerated.
- product gate suite: 13 checks identified from TOOL-INVENTORY.md. Exact wiring of gates.json vs umbrella runner NOT verified on the product repository — requires access to `/home/stack/code/charon/tools/gates.json` and `charon.cli gate` source.

### Could not audit

- **Faktory Enterprise feature set**: We run OSS Faktory. Enterprise features (unique jobs, batch, cron, expiration) are documented in the upstream wiki but were NOT inspected in a running Enterprise instance. The CLAIMED-BUT-ABSENT exactly-once finding is therefore scoped to OSS Faktory.
- **30+ `~/.local/bin` scripts**: Not enumerated. Their names and functions are unknown. Low risk (0 references in any fleet doc = unlikely to be depended on).
- **Product gate suite internals**: The `tools/gates.json` registered set vs umbrella invocation divergence is cited from TOOL-INVENTORY.md but NOT independently verified against the product repo's current state.
- **vulture/deadcode/pylint full rule surfaces**: These tools are installed but were audited only through the lens of prior evals (DEADCODE-TOOL-REDERIVE, VULTURE-EVAL). Their full flag/ruleset surfaces were NOT independently re-enumerated — the prior evals' counts are reused.
- **yamllint rule surface**: Installed, 0 config, 0 uses. Rule set NOT enumerated. Finding count (95) from TOOL-UTILIZATION-AUDIT, not independently verified.
- **actionlint checks**: Installed, orphan config. Check list NOT enumerated. 0 findings from TOOL-UTILIZATION-AUDIT, not independently verified.

### Inventory completeness

TOOL-INVENTORY.md enumerates 5 sections but is **incomplete** — it lists ~60% of the tools this audit found. Missing from TOOL-INVENTORY.md:
- Faktory (entire faktory/ subsystem)
- session-bridge (referenced in scripts, no entry in inventory)
- basic-memory (MCP server with 16 commands, no entry)
- pip-audit
- yamllint, actionlint, deadcode, vulture, pylint, mutmut, diff-cover (all installed and partially referenced in evals)
- `fleet/checks/` as a sub-inventory (32 files, 9 inert)
- `fleet/faktory/`, `fleet/memory/`, `fleet/watchdog/`, `fleet/canary-service/`, `fleet/capture/`, `fleet/hooks/`

**Recommendation:** TOOL-INVENTORY.md needs a sweep to reflect the FULL inventory this audit found. This is a separate ticket — updating it is not in this audit's owns:.

---

## 5. THE STANDING RULES THIS AUDIT PRODUCES

1. **Before adopting any new tool, enumerate the FULL relevant surface of incumbents.** Every under-scoped trial (bandit → ruff S, pyscn → ruff C90/PL, pylint W0613 → ruff ARG) came from testing the candidate against a NARROW incumbent configuration. The rule: "state which incument features were enabled during the trial."

2. **An INERT check is a false sense of safety.** 9 gate scripts read as protection and provide none. The gate-integrity.sh scan proves this is detectable. Wire the check or delete the file — an inert guard is worse than no guard because it breeds false confidence.

3. **Never code against a guarantee you have not verified in the tool's source.** Faktory's exactly-once is the precedent. The `lease-exactly-once.test.sh` guards with real-server availability and reports PENDING — the correct pattern. But the TEST'S existence proves the pipeline was DESIGNED for a guarantee the tool does not make.

4. **Compose what you own before adopting what you don't.** The 9 INERT gate scripts are capabilities we ALREADY BUILT that would close 4 of the 12 measured E2E failures — with zero new tools. A one-line wire in preflight/land/foreman cadence is the cheapest fix in the fleet.
