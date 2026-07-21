# Drift/Staleness Tool-Adoption Audit — Charon/SLOP

Doctrine: ADOPT-FIRST (hand-rolling is last resort). No code changes; written audit only.
Date: 2026-07-21. Evidence is code/config-verified (per `confirm-dont-trust-documentation`),
not doc-trusted.

---

## Part A — CONSULT-FIRST (EVAL-REGISTRY prior verdicts)

Source: `/home/stack/charon-private/fleet/state/EVAL-REGISTRY.md` (+ `-RECONCILE.md`).
Reality: the EVAL-REGISTRY is **almost entirely LiteLLM + egress-security rows**. It has
**no rows** for the DRIFT/STALENESS tool classes this audit targets (renovate, dependabot,
mergify, kodiak, argocd, flux, driftctl, git-branchless, graphite, vulture, gitleaks, semgrep).
Those tools are instead tracked as **board tickets** (KS31/KS32 sweep), not registry rows.
So for the drift classes there is little to "not re-litigate" — the settled rows are LiteLLM-scoped.

| tool (registry row) | scope | prior verdict | alignment | re-test? |
|---|---|---|---|---|
| LiteLLM (full proxy-core) | replace gateway core | REJECTED / keep-custom | aligned | NO — settled; core is the differentiator |
| LiteLLM Router (library only) | commodity plane, no proxy/FastAPI | **ADOPT** (shipped first slice, commit 7e16e4a) | aligned | NO — settled, adopted |
| LiteLLM price JSON (data only) | static pricing source | ADOPT — shipped | aligned | NO |
| LiteLLM tool-call translation | embed `litellm.completion()` | not-a-clean-win | mixed | maybe, if tool-call class reopened |
| Semgrep | CI required-check backstop (all harnesses) | **ADOPT** | aligned | NO — adopt confirmed; landing pending |
| CodeQL | CI secret→network taint (public mirror) | ADOPT-as-defense-in-depth | aligned | NO |
| Gitleaks | (NOT a registry row — see Part B; tracked as board `GITLEAKS-ADOPT`) | — | — | — |
| Smokescreen / docker-egress-denial / nginx-broker | egress key-exfil control | ADOPT (various) | aligned | NO |
| Squid / tinyproxy / Envoy / Vault / SPIFFE | egress alternatives | REJECT | aligned | NO |
| Claude Code hooks / OPA / Danger / Invariant | on-plan enforcement | ADOPT hooks+Semgrep; DEFER/REJECT rest | aligned/mixed | NO |
| ReviewerCircuitBreaker (in-tree reuse) | doom-loop breaker | ADOPT-REUSE | aligned | NO |

**Registry hygiene finding:** the drift/staleness tool class is a **blind spot in the registry
itself** — the adopt decisions for gitleaks/semgrep/vulture/bandit live only as board tickets
and have never been backfilled as EVAL-REGISTRY rows. Whatever lands from Part C should append
rows (KS32's `build-vs-adopt-gate` is exactly the mechanism to force this).

**Anti-pattern lens (registry §"HAND-ROLL JUSTIFICATION ANTIPATTERNS"):** AP-1 ("stdlib/no-dep
core") applies ONLY to the product privileged core, NEVER to rig/CI/dev-tooling. Every drift
tool below is rig/CI-tier, so "keep it stdlib" is INVALID as a reason to hand-roll them.

---

## Part B — the SLOP tools audit (was it implemented?)

**The SLOP audit found:** `/home/stack/code/mediastack/docs/EXTERNAL-TOOLS.md` (generated
2026-07-11 from SLOP's real `requirements*.txt`, `.pre-commit-config.yaml`, `.github/workflows/`).
It is SLOP's inventory of ~30 external tools it actually runs. The Charon-reuse target set
(the drift/quality/security tools worth porting) and their **verified** Charon status:

| SLOP tool (recommended reuse) | in SLOP? | in Charon? — VERIFIED | gap |
|---|---|---|---|
| ruff | yes | **YES** — `pyproject [dev]`, `gate_runner.py:36` runs `ruff check src tests` in `charon gate` (CI ci.yml:38) | none |
| mypy | yes | **YES** — `gate_runner.py:37`, CI | none |
| pip-audit | yes | **YES** — `[dev]`, CI ci.yml + heavy.yml:93 | none |
| gitleaks | yes (pre-commit + CI) | **PARTIAL** — `.gitleaks.toml` exists at root but is **ORPHANED**: not referenced by pre-commit (`.pre-commit-config.yaml` only runs `check_public_clean.py`) and **not in any workflow**. Adoption is BOARDED not landed (`board/GITLEAKS-ADOPT.md`, branch `feat/gitleaks-adopt`, dep on SEMGREP) | **CONFIG-ONLY, NOT WIRED** |
| semgrep | yes (`.semgrep/rules/`) | **NO (boarded)** — `board/SEMGREP-CI-REQUIRED-CHECK.md`, not landed. EVAL-REGISTRY says ADOPT | **un-implemented** |
| vulture (dead code) | yes | **NO** — Charon hand-rolls `tools/check_inert_code.py` instead. Swap boarded: `board/VULTURE-INVESTIGATE-RETIRE-INERT.md` (dep on GITLEAKS+BANDIT) | **un-implemented; hand-roll in place** |
| bandit (Python SAST) | yes | **NO (boarded)** — `board/BANDIT-ADOPT.md` | **un-implemented** |
| trivy (image CVE) | yes | **NO** — no trivy in Charon workflows | **un-implemented** |
| hadolint / actionlint / shellcheck / sqlfluff / radon | yes | **NO** — none in Charon | un-implemented (lower priority) |
| dependabot | (SLOP uses its own) | **YES** — `.github/dependabot.yml` LIVE, but scoped to **github-actions only** (pip/docker deliberately excluded; core is `dependencies=[]`) | partial-by-design |
| SLSA provenance + digest-pin | — | **YES** — `release.yml` GitHub-native `attest-build-provenance` (SLSA via OIDC) + fresh base-digest pin. No cosign (deliberate) | none |

**Bottom line (Part B):** KS31's own summary — "Charon currently uses only 3 of ~15" — is
**CONFIRMED by code**: only **ruff, mypy, pip-audit** are actually wired into `charon gate`/CI.
Everything else the SLOP audit recommended (gitleaks, semgrep, vulture, bandit, trivy) is
**boarded but NOT landed** — gitleaks is the worst case: config file committed, giving a false
impression of coverage, but zero enforcement. The Charon-side `board/ON-DEMAND-TOOL-AUDIT.md`
(branch `audit/on-demand-tools`, ledger `ON-DEMAND-TOOL-LEDGER.tsv`) is a *different* audit
(tool cadence/trigger wiring, per `dynamic-tools-never-on-demand`), not the SLOP-reuse audit.

**tracking.db note:** SLOP tickets live in `mediastack/tracking/tracking.db` via query.py and
are gitignored/org-orphaned (per memory `slop-tickets-location`). I did not open that DB, so the
SLOP-side ticket *status* for these tools is not asserted here — only the code-verified reality
of what SLOP and Charon actually run. State this to the operator; do not guess ticket states.

---

## Part C — drift-class → best-in-class tool map (core deliverable)

| # | drift/staleness class | best-in-class tool(s) | what it does | VERDICT for Charon |
|---|---|---|---|---|
| 1 | Merged/stale git branches | **GitHub "auto-delete branch on merge"** (repo setting) primary; git-branchless / Graphite / git-town for stacked-branch hygiene | Auto-removes merged head branches; branchless/graphite garbage-collect + restack local branches | **ADOPT the GitHub repo setting** (zero-cost, kills the merged-branch class at source). git-branchless = **GAP-BUILD-NOT-JUSTIFIED**: the real pain is *stranded un-landed* branches (memory `detection-ticketed-never-built`, `board/STRANDED-WORK-AUDIT.md`), which is a *landing-discipline* problem a branch tool doesn't solve. ALREADY-HAVE partial: `land.sh`/`land-push.sh`. |
| 2 | Stale/behind PRs + merge hygiene | **GitHub native merge queue** (GA) primary; **Mergify** (richer rules) / Kodiak / bors | Serializes merges, auto-rebases each PR against fresh base, re-runs required checks, auto-merges when green — kills "green against stale base" | **ADOPT GitHub merge queue** once branch-protection required-checks exist (Semgrep/gitleaks land first). Directly retires the hand-rolled `refresh-branch.sh` / manual base-rebuild pain (memory `gate-hardening-strands-open-branches`). Mergify = ADOPT-if queue rules outgrow native. This is the single highest-value adopt (see TOP-5). |
| 3 | Dependency staleness | **Renovate** (or keep **Dependabot**) | Automated dependency-update PRs; Renovate adds grouping, custom managers, monorepo, scheduled batching; Dependabot is GitHub-native/simpler | **ALREADY-HAVE (Dependabot, actions-only)** and that scope is correct while core is `dependencies=[]`. **Do NOT adopt Renovate now** — no lockfile, open `>=` ranges make version PRs near-no-ops (per dependabot.yml rationale). Re-evaluate Renovate only if/when Charon takes real pinned runtime deps (LiteLLM Router adoption may trigger this). |
| 4 | Config/catalog/infra drift (declared vs live) | GitOps (**ArgoCD/Flux**), **driftctl**, **Terraform plan** — the desired-vs-observed reconciliation primitive | Continuously diff declared spec against live cluster/cloud state, alert/auto-heal | **GAP-BUILD-JUSTIFIED (thin).** These are IaC/k8s-shaped; Charon is a solo docker-compose box with NO Terraform/k8s → ArgoCD/Flux are AP-9 overkill, and **driftctl is in maintenance mode since 2023** (frozen, cloud/TF-only) — none fit Charon's drift, which is `providers.json`/catalog/tier-config vs **live gateway `/models`** and deployed-image-config vs source (memory `charon-deploy-drift-lessons`: CHARON_HOME empty, keys missing on live box). The *algorithm* (content-hash / set-diff / schema-conformance / staleness-probe) is commodity and IS what KS24/KS29 spec. ALREADY-HAVE partial: `config-ssot-gate.sh`, `check_catalog_case_quant.py`, boarded `SSOT-DRIFT-GATE`. **Adopt the k8s reconciliation *pattern*, not an IaC product.** |
| 5 | Deployed-artifact vs source drift | **image digest pinning + SLSA provenance** (GitHub `attest-build-provenance` / cosign) + build-SHA stamping | Pin base by digest, attest build provenance, verify deployed digest == attested built digest; stamp source SHA into the running artifact | **ALREADY-HAVE (build side)** — `release.yml` does SLSA-via-OIDC + fresh base-digest pin (no cosign, deliberate). **GAP (verify side):** nothing on the **live box** verifies the running image's digest/source-SHA matches the attested build — that is precisely the `charon-deploy-drift-lessons` gap. Small adopt: a `docker inspect` digest-vs-provenance check at deploy/startup (build-SHA stamp into `/version`). |
| 6 | Dead/inert code | **Vulture** (Python), deadcode, knip (JS) | Static unused-symbol/dead-code detection with allowlist | **ADOPT Vulture, RETIRE the hand-roll.** Charon hand-rolls `tools/check_inert_code.py`; SLOP already runs vulture. Swap is boarded (`VULTURE-INVESTIGATE-RETIRE-INERT`) with the right guardrail (eval + canary + atomic retirement so two checkers never co-run). Pure KS31 "thin adapter over best-in-class, never reimplement." |
| 7 | Gate/detector/registry freshness | **the k8s reconciliation pattern** (declare→conformance+discovery+drift) — no single OSS tool | Registry-driven: declare a registry (schema+scope) → auto conformance gate + fail-closed discovery gate + drift check | **GAP-BUILD-JUSTIFIED (this is the genuine novel ~30%).** No off-the-shelf tool wraps "arbitrary in-repo registry → conformance+discovery+drift for free" — this IS KS29's registry-primitive. Ground it in the k8s controller-runtime reconcile pattern (desired vs observed), but the in-tree registries (bad-patterns, catalog, entrypoints, rules) have no product analog. Charon already has the seed: `test_gate_registry_execution.py` (PR #119) proves gates fire; generalize it, don't buy it. |

---

## Part D — reconcile with KEYSTONE (compose, don't duplicate)

KS ticket bodies (source: `fleet/state/ROADMAP.tsv` rows 155/161/163/164; `KEYSTONE-AUDIT.md`):
- **KS24 lens-drift** — declared≠live: config/catalog/pools vs live provider state; deployed-artifact vs source checksum; dead/stale entries. Explicitly the desired-vs-observed (k8s/Terraform) algorithm. Is KS29's drift leg.
- **KS29 component-registry-primitive** — ONE primitive: declare registry → conformance + discovery(fail-closed) + drift, for free. SUBSTRATE; everything else waits on it.
- **KS31 component-tool-adapters** — KSF gates are **thin ADAPTERS over best-in-class tools (ruff/mypy/bandit/gitleaks/semgrep/vulture/radon/mutmut/…); NEVER reimplement.** Custom only for novel classes (inert/verification-delta/drift/firing/grounding).
- **KS32 build-vs-adopt-gate** — TOOL-FIRST gate: a custom impl for a new class is RED unless it ships a tool-eval record (candidate + real test + verdict). The tool-ecosystem analog of reuse-check.

| Part-C recommendation | folds into KS# / net-new |
|---|---|
| C6 Adopt Vulture, retire `check_inert_code.py` | **FOLDS → KS31** (canonical "thin adapter, never reimplement"). Already boarded `VULTURE-INVESTIGATE-RETIRE-INERT`. |
| C1/C2 config-file / CI-scanner adopts (gitleaks, semgrep, bandit, trivy) | **FOLD → KS31** (tool-adapters). Boarded: GITLEAKS-ADOPT, SEMGREP-CI-REQUIRED-CHECK, BANDIT-ADOPT. |
| C4 config/catalog declared-vs-live drift | **FOLDS → KS24 (drift leg) on KS29 (registry primitive).** Also boarded `SSOT-DRIFT-GATE`. Compose, don't build a parallel drift checker. |
| C7 gate/detector/registry freshness | **FOLDS → KS29** (the registry primitive IS this) + KS30 enforcement-spine firing layer. |
| C5 deployed-artifact vs source *verify* (build side already done) | **PARTIAL-FOLD → KS24** ("deployed artifact vs source checksum" is named in KS24). The live-box digest/SHA verify step is **NET-NEW-BUT-SMALL** — a deploy/startup check, currently unticketed; smallest home is a KS24 instance. |
| C1 GitHub auto-delete-branch-on-merge (repo setting) | **NET-NEW** (trivial, operator repo-setting; not a KS ticket). No build. |
| C2 **GitHub merge queue / Mergify** | **NET-NEW — the biggest KEYSTONE blind spot.** No KS ticket owns merge-hygiene/merge-queue; KS covers *gates*, not *the merge mechanism that runs them against fresh base*. Note AP-8 in the registry: "durable-exec engines / merge-queue were **never even evaluated**." This is the highest-leverage un-covered adopt. |
| C3 Renovate | **NET-NEW but DEFER** — not KS-covered; correctly out of scope until real runtime deps land. |

**Net:** Parts C6, C1-scanners, C4, C7 all COMPOSE into existing KS31/KS29/KS24 + existing board
tickets — do not duplicate. The only genuinely un-covered, high-value net-new is **merge-queue
(C2)** and the trivial **auto-delete-branch setting (C1)**.

---

## TOP-5 highest-leverage adopts (ranked by drift-pain-reduced / adoption-cost)

1. **GitHub native merge queue** (net-new, not in KEYSTONE) — kills the "green-against-stale-base"
   + stranded-branch class that recurs constantly (`gate-hardening-strands-open-branches`); retires
   hand-rolled `refresh-branch.sh`. Cost: branch-protection config once required-checks exist.
2. **GitHub auto-delete-branch-on-merge** (repo setting) — eliminates merged-branch clutter at the
   source. Cost: one checkbox per repo. Near-infinite leverage/cost ratio.
3. **Land the boarded CI scanners as required checks: gitleaks + semgrep + bandit** (KS31) — gitleaks
   is config-committed-but-orphaned TODAY (false coverage); Semgrep is the un-bypassable all-harness
   backstop the EVAL-REGISTRY already graded ADOPT. Cost: finish 3 boarded tickets on the CI runner.
4. **Adopt Vulture, retire `check_inert_code.py`** (KS31, boarded) — replace a hand-rolled dead-code
   checker with the maintained tool SLOP already runs. Cost: one eval + canary + atomic swap.
5. **Deploy-time image-digest / source-SHA verify** (folds into KS24) — closes the deployed-vs-source
   drift that already bit the live box (empty CHARON_HOME, missing keys); build-side SLSA/pin already
   done, only the live-verify leg is missing. Cost: one `docker inspect` startup check + `/version` stamp.

Sources: [driftctl maintenance status](https://github.com/snyk/driftctl), [Spacelift Terraform tools 2026](https://spacelift.io/blog/terraform-tools)
