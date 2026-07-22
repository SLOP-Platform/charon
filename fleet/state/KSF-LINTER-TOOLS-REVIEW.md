# KSF ← vinta "python-linters-and-code-analysis" — adversarial go/no-go

Reviewer verdict up front: **ADD NOTHING by wrapping. Build ~2 tiny native gates only if operator wants the capability.**
Date 2026-07-11. Source list: https://github.com/vintasoftware/python-linters-and-code-analysis (86 tools). KSF source: /home/stack/code/keystone.

## (a) KSF current stack — what it already does (all stdlib: `ast`/`re`/`subprocess`/`tomllib`, zero third-party deps)

pyproject.toml has **no `dependencies` key** — KSF ships stdlib-only. It does NOT bundle ruff/mypy/black; those live in Charon's *build* gate, not the KSF product. KSF is a *meta*-gate framework (enforces enforcement integrity), not a style linter.

| Gate | File:line | What it enforces |
|---|---|---|
| inert-code | ksf/gates/inert_code.py:335 | AST call-graph reachability from entrypoints; public symbol with 0 callers + unregistered + no `@inert_by_design` = RED. **Registration-aware unused-code finder.** |
| leak-guard | ksf/gates/leak_guard.py:28 | Regex-scans all git-tracked files for home paths / emails / IPs / hostnames / personal names |
| no-pipe-mask | ksf/gates/no_pipe_mask.py:18 | `.sh` + CI YAML: missing `set -o pipefail` / `|| true` exit-masking; + CLI pipe-mask contract test |
| no-skip-game | ksf/gates/no_skip_game.py:90 | Every skip/xfail justified (reason/ticket) + baseline anti-shrink |
| coverage-ssot | ksf/gates/coverage_ssot.py:31 | Meta: every declared gate is implemented + red-proofed + wired (4-class taxonomy) |
| redproof | ksf/gates/redproof.py:21 | Every gate/module ships a negative test that actually goes red |
| wiring-alignment | ksf/gates/wiring_alignment.py:71 | Each entrypoint has a test importing the same module path |
| fail-loud | ksf/gates/fail_loud.py:12 | Contract: runner exits non-zero on a failing fixture |
| no-vacuous | ksf/gates/no_vacuous.py:12 | 0 tests collected / 0 gates discovered = RED |
| reuse-check | ksf/reuse_check.py (cli.py:160) | Similarity/dedup block on new modules |
| reconcile | ksf/state_store.py (cli.py:35) | Reopen modules whose close-proof falsified |

KSF's job = catch *process* lies (inert code, masked exits, vacuous passes, skip-gaming). Conventional linters catch *style/type* defects — a different, already-covered axis.

## (b) Candidate ranking (86 tools → only ~7 merit individual judgement; the rest bucket-rejected)

| Tool | Verdict | Rationale | Cost if taken |
|---|---|---|---|
| **vulture** (#10) | 🔴 REJECT | Unused/unreachable code = duplicates inert-code, and is *worse*: not registration-aware, no `@inert_by_design`, adds a pip dep. Replacing our gate with it LOSES capability. | — |
| **dodgy** (#27) | 🔴 REJECT | "passwords / exposed diffs / suspicious patterns" = duplicates leak-guard; adds dep for less coverage of our specific leak set | — |
| **bandit** (#26) | 🟡 ADD-AS-MODULE *(weakest pass)* | Genuinely net-new: general insecure-AST patterns (eval/exec, `shell=True`, pickle, yaml.load, weak crypto) — KSF has no danger-pattern gate | subprocess wrap like graphify, ~40 LOC glue + 1 dep (+ its transitive `pbr`/`stevedore`) |
| **pycycle** (#20) | 🔴 REJECT | Circular-import detection IS net-new, but the tool is a niche dep — and inert_code.py already builds the import graph (:373-392). Build native, don't wrap. | (native: ~30 LOC, 0 deps) |
| **safety / dependency-check / pyt** (#25/#29/#30) | 🔴 REJECT | CVE/dep-vuln + web-taint scanning need an online DB (non-self-contained) and KSF has ~0 deps to scan; violates self-contained | — |
| **eradicate** (#77) | 🔴 REJECT | Removes commented-out code — cosmetic; ruff `ERA` already does it; not an integrity check | — |
| **xenon / radon / mccabe** (#33-35) | 🔴 REJECT | Complexity thresholds = style/quality, not enforcement-integrity; ruff `C901` covers it | — |
| **pre-commit** (#55) | 🔴 REJECT | A gate *runner* — KSF *is* the runner; orthogonal/duplicative | — |
| flake8, pylint, pyflakes, pycodestyle, pydocstyle, pep8-naming, flake8-* (#7-9,17-21) | 🔴 REJECT | Classic style/lint — the ruff/mypy lane, deliberately outside KSF | — |
| mypy, pyre, pytype, retype, typycal (#14-15,83-85) | 🔴 REJECT | Type checking — mypy lane; not KSF's axis | — |
| black, autopep8, yapf, isort, autoflake, unimport (#16,60-64) | 🔴 REJECT | Auto-formatters — ruff/black lane | — |
| Coala, Yala, prospector, Pylama, Ciocheck, wemake (#1-6) | 🔴 REJECT | Meta-wrappers pulling in whole plugin ecosystems — maximal dep weight, antithesis of stdlib-first | — |
| ast, typed_ast, parso, astor, astunparse, gast, commonast, asteval, astviewer, baron, redbaron (#65-79) | 🔴 REJECT | AST *libraries/viz/refactor kits*, not gates; KSF already uses stdlib `ast` directly | — |
| all Django/pylint/ORM plugins (#37-54), scspell3k, pyroma, check-manifest, pipenv, review-bots #56-59, misc | 🔴 REJECT | Framework-specific, packaging, spell-check, PR-comment bots — irrelevant to a provider-agnostic meta-gate | — |

## (c) Bottom line

- **Wrap nothing.** Every tool that *works* duplicates an existing KSF gate (vulture→inert-code, dodgy→leak-guard) or the ruff/mypy lane KSF intentionally omits; every tool that *adds* capability drags a third-party dep + config/plugin ecosystem into a stdlib-first, self-contained product — a strike per the operator's bar.
- **The only two genuinely net-new axes** KSF lacks are (1) insecure-AST patterns (bandit-class) and (2) circular-import detection. Neither justifies a dependency:
  - If security coverage is wanted, build a **native `danger_ast` gate** (~50 LOC, 0 deps): flag `eval`/`exec`, `subprocess(..., shell=True)`, `pickle.load`, `yaml.load` w/o SafeLoader, `tempfile` predictable paths. Do **not** wrap bandit (pulls `pbr`+`stevedore`, own config, CWE noise off-mission).
  - If circular imports matter, build a **native `import_cycle` gate** (~30 LOC, 0 deps) reusing the import graph inert_code.py already constructs (:373-392). Do **not** wrap pycycle.
- **Adversarial case against even those two:** both are speculative — no operator pain cited, and KSF's own codebase is tiny/stdlib so the risk they catch is low. Default REJECT stands unless a concrete incident motivates them. "Add nothing" is the recommended action today.

**Recommendation: NO-GO on the entire catalogue. Do not add a dependency. Park the native `danger_ast` / `import_cycle` ideas as optional ~1-hour builds, gated on a real incident.**
