# TOOL-UTILIZATION AUDIT — how much of what we ALREADY OWN is switched on

**Date:** 2026-08-01 · **Session:** saba-sebatyne · measured on this box, not read from docs.
**Question asked:** not "what should we adopt" — *"for every tool already installed, what fraction
of its capability are we actually using?"*

---

## THE HONEST NUMBER: ~20%

| tool | surface (M) | we use (N) | biggest unused | measured | cost to enable |
|---|---|---|---|---|---|
| ruff 0.15.16 | **962 rules**, ~40 cfg keys | **150 active** (195 reachable, 45 preview-gated), 4 cfg keys, 0 sub-tables | `preview` under our OWN select | **12** defects CI misses (4x F401, 1x B909); `--select ALL`=2981, ALL+preview=3934 | 1 line |
| ruff unselected families | 54 off | 0 | PL 334, TRY 184, T20 180, TC 95, RUF 77, SLF 73, TID 68, **C90 62**, ARG 50, **S 47**, PTH 27, BLE 25 | src is 0-findings under current select | per-family |
| vulture 2.16 | 8 flags + `[tool.vulture]` | min-confidence only | `--make-whitelist`, `--ignore-decorators`, `--config` | 176@60 → 12@80/90/100 (**cliff**) | low |
| deadcode 2.4.1 | 16 ignore flags + `--fix/--dry/--count` | ad-hoc, no flags | `--fix --dry`; 11 `--ignore-*-if-*` predicates | 169 (DC04 64, DC01 42, DC02 42, DC05 14, DC03 4, DC08 3); **no config-file support at all** | low |
| mypy | 14 strict components | **0** | check-untyped-defs / warn-unreachable / warn-return-any | clean now; `--strict`=2311. Deltas: untyped-defs 1952, any-generics 448, incomplete 279, unused-ignores 153, untyped-calls 127, return-any 85, unreachable 58, check-untyped-defs 33 | 3 lines |
| pytest 9.0.3 | 8 plugins installed | **xdist only** | timeout, randomly, hypothesis, mutmut | zero `addopts`/`--timeout`/`-p` in any config (grep=0) | 1 line |
| graphify | ~15 analysis subcmds | update 114, path 42, explain 33, watch 18, diagnose 3 | **`affected`** (blast-radius) = **0 uses** | cited as method in HAND-ROLLED-AUDIT.md but 0 call sites | zero |
| gh 2.63.2 | REST+GraphQL 5k each, cache, paginate, ETag | 49 `gh api`, `--jq` 55, `--cache` 8 | `--paginate` 0; no deliberate endpoint choice | live: core 0/5000, graphql 2025/5000 | zero |
| shellcheck 0.11.0 | 4 severities + **11 optional, ALL OFF** | severities only; rig-only, not product CI | all 11 | fleet 286 scripts: default 1589 (15 error); `-o all` **31810**; set-e-suppressed **1696** | 1 flag |
| bandit 1.9.4 | 75 tests | rig only, 0 in product CI | product run | 58 (3 HIGH, 1 MED) | low |
| yamllint 1.38 | ~20 rules, 3 presets | **NOTHING** | all | **95** findings, no config | 1 line |
| actionlint 1.7.12 | ~30 checks + embedded shellcheck | **NOTHING** (orphan config) | all | 0 findings — workflows genuinely clean | 1 line |

**Breakdown:** ruff 16% of rules / 4 of ~40 config keys · mypy 0/14 · pytest 1/8 · shellcheck 0/11
optional · graphify 9/~15 · gh ~2/6.

> **The failure mode is not missing tools — it is DEFAULT CONFIGURATION ACCEPTED AS THE TOOL'S
> FULL SURFACE.**

---

## TOP 5 BY VALUE — all approved 2026-08-01, NOT YET DONE

1. **`preview = true` in `[tool.ruff.lint]`** — 12 defects inside families we ALREADY select,
   7 auto-fixable. One line.
2. **`extend-select = ["S","BLE","ARG","C90"]`** — 184 findings, **3 HIGH-severity security**.
3. **mypy `check_untyped_defs` + `warn_unreachable` + `warn_return_any`** — **176 real bugs**.
   Deliberately SKIP `disallow_untyped_defs` (1952 findings = churn, not signal).
4. **`shellcheck -o all` on the rig** — 15 error-level findings invisible today; 1696 set-e
   findings, 15 on `fleet-droid.sh` itself.
5. **`graphify affected`** — the blast-radius subcommand. The graph is already built by 114
   `update` call sites; the query has **0 invocations**. Directly relevant to the wiring/reachability
   work (WIRING-DONE-CONTRACT).

Each must be **dogfooded**, not just switched on — operator directive 2026-08-01.

---

## CAPABILITIES NOT NAMED IN ANY FLEET DOC, REGISTRY ROW, OR TICKET

`shellcheck --list-optional` (0 files) · ruff `extend-select` (0) · `check-set-e-suppressed` (0) ·
`graphify merge-graphs` / `merge-driver` (0) · `gh api graphql` (0) · pytest-randomly (0) ·
vulture `--ignore-decorators` (0) · deadcode having **no config file support** ·
actionlint **embedding shellcheck** for `run:` blocks.

## INSTALLED AND ENTIRELY UNUSED

yamllint · actionlint · vulture · deadcode · mutmut · hypothesis (as a gate) · diff-cover /
diff-quality · pytest-randomly / timeout / asyncio / playwright · pylint / pyreverse / symilar ·
bandit-baseline · bandit-config-generator · stubgen / stubtest · pysemgrep · litellm-proxy ·
git-filter-repo · **+~30 more `~/.local/bin` scripts at 0 references**.

---

## THREE NEW "UNDER-SCOPED TRIAL" INSTANCES (highest-value finding)

The anti-pattern (registered in EVAL-REGISTRY 2026-08-01): *an eval that genuinely RUNS the
candidate and honestly counts output — so it is stamped `aligned` — but configures the INCUMBENT
too narrowly, so the candidate wins a comparison it should have lost.* **Execution is not
completeness.**

**1. `bandit` row (EVAL-REGISTRY:65) — `aligned` → `drifted`. STRONGEST.**
Basis was "net-new danger-pattern coverage (eval/exec, shell=True, pickle, yaml.load, weak crypto)
the rig has no gate for." ruff was ALREADY adopted and in CI, and **ruff's `S` family IS
flake8-bandit** (73 rules). Measured: bandit 58 findings (B603 13, B110 15, B404 9, B607 8, B105 4,
B101 3, B602 3, B112 2, B104 1) vs `ruff --select S` 47 (S110 15, S603 13, S607 8, S105 4, S101 3,
S112 2, S104 1, S602 1) — **8 of 9 test ids map 1:1**. The ninth (B404) is `S404`, preview-gated,
measured at exactly 9 under `--preview`. **`ruff --select S --preview` reproduces 100% of bandit's
findings here.** The eval never states which ruff families were enabled. We adopted a second
security tool for a job the adopted linter already does.

**2. `pyscn` row (:79) — `aligned` → `mixed`.**
Claimed pyscn fills "cognitive complexity" as an uncovered gap. Complexity is an UNENABLED ruff
family: `--select C90` = **62** C901, plus PLR0912/PLR0915 inside PL(334) and preview
PLR1702(8)/PLR0914(15)/PLR0917(10), with `[tool.ruff.lint.mccabe] max-complexity` for the
threshold. Duplicate-detection and architecture rules remain genuine → `mixed`, not `drifted`.

**3. `shellcheck` SETE row (:142) — `aligned` → `mixed`. Registered the SAME DAY as the
anti-pattern it exhibits, by this session.**
The row says it ran "at ALL severities" and asserts "**Not a config miss**", dismissing SC2310/2311.
**Severity is orthogonal to shellcheck's 11 optional checks, all off by default.** Same file
`fleet/fleet-droid.sh`: default **9** findings (the number the row reports) vs
`-o check-set-e-suppressed` **24**, including **15 SC2310 never seen**;
`-o check-extra-masked-returns` 21.
HONEST QUALIFIER — the narrow verdict SURVIVES: the SC2310 lines are 220/251/252/276/278/399/402/
453/537/1097/1125/1133/1172/1209/1453, **none in the defective 1390-1412 block**. shellcheck still
misses that specific defect. But the row's stated BASIS is unsupported: it ran the incumbent at
9 of 24 available findings and dismissed a rule family it never enabled.

**4.** `vulture` (:66, already reclassified `drifted`) and `deadcode` (:82, WATCH) are consistent
with their evidence — no new drift.

---

## RELATION TO THE PRIOR AUDIT

`fleet/state/reviews/AUDIT-UNDERUSED-ADOPTED-TOOLS-agen-kolar.md` (2026-07-24) asked the same
question but scoped to **litellm only**. Its headline correction: the fix is
`litellm_params["order"]`, NOT `routing_strategy="cost-based-routing"` (which raises
`RouterRateLimitError` on our sync path). It enumerated the dependency inventory but measured no
linter/analyzer rule surface. This audit extends it to the 12 static-analysis and test tools it did
not touch.

---

## THE STANDING RULE THIS PRODUCES

Before accepting any "tool X covers a gap tool Y does not": **enumerate Y's FULL relevant rule /
feature surface and state which parts were enabled during the trial.** An eval that does not say
what the incumbent was configured with has not made the comparison it claims.
See MANAGER-OPERATING-RULES.md §14 and the `ANTI-PATTERN: under-scoped trial` row in EVAL-REGISTRY.
