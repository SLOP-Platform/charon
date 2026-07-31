# KSF SURFACE AUDIT — Lane 2
**Target**: `/home/stack/code/keystone` · **Date**: 2026-07-31 · **Session**: `ahsoka-tano`
**LOC**: 2,557 (gates: 1,343, core: 1,214) · **Tests**: 28/28 pass in 11s · **Last commit**: 2026-07-12 · **Single contributor** (Nnyan)

## PERFORMANCE SIGNAL — REFUTED

Two prior `check_inert_code` runs were KILLED (>120s charon, >100s 4-file fixture). **Refuted** (`fece8fa`): 0.066s against keystone (20 files), 4.464s against charon (31K LOC Python). The prior signal was from an earlier version. The real blocker is **noise**: 200+ false positives against charon because `_resolve_call()` at `inert_code.py:269` is best-effort and can't trace re-exports. Noise — not speed — is why it's unregistered.

## GATE ASSESSMENT

| Gate | LOC | Checks | Class/Instance | Width | Time | Blast if OPEN | Prune? |
|---|---|---|---|---|---|---|---|
| **inert_code** | 500 | AST call-graph reachability; 0-caller public symbols = INERT | **CLASS** (built-never-called) | TOO BROAD (200+ FP on charon) | 4.5s | HIGH | NO — but must fix resolver precision |
| **coverage_ssot** | 212 | Rules mechanized/guidance/GAP; modules wired+tested+surfaced | **CLASS** (declared-but-missing) | Right-sized | 0.001s | MEDIUM | NO — hardcoded _RULE_CLASSIFICATIONS is maintenance burden |
| **wiring_alignment** | 97 | String match `import <module>` in tests/ per entrypoint | **INSTANCE** (test import exists) | TOO NARROW (imported≠tested) | 0.000s | LOW | Candidate — supersedable by coverage tooling |
| **redproof** | 74 | Each gate/module must have passing red-proof pytest test | **CLASS** (negative test gap) | Right concept, NARROW exec (naming convention only) | **8.1s** | HIGH | NO — strongest KSF idea |
| **no_vacuous** | 47 | pytest --collect finds >0 tests; gates/ finds >0 files | **CLASS** (empty enforcement) | Right-sized | 0.79s | MEDIUM | NO |
| **no_skip_game** | 125 | AST-walks .py for pytest skip/xfail; baseline shrink = RED | **CLASS** (skip creep/shrink) | NARROW (pytest only). Mutates repo (writes baseline) | 0.04s | MEDIUM | NO — fix write-side-effect |
| **no_pipe_mask** | 146 | Shell scripts need pipefail; CI YAML run blocks; contract test | **CLASS** (silent pipe failure) | BROAD YAML heuristic | 0.07s | MEDIUM | Borderline — YAML parser is naive |
| **fail_loud** | 57 | Temp fixture: failing gate → assert CLI exit≠0 | **INSTANCE** (runner exit code) | Right-sized self-test | 0.04s | LOW | Could live in tests/ |
| **leak_guard** | 84 | `git ls-files` then regex for PII (paths, emails, IPs) | **INSTANCE** (PII patterns) | TOO BROAD (RFC1918, home paths in config) | 0.01s | LOW | **PRUNE** — gitleaks/pre-commit concern, not structural |

## NON-GATE MODULES

| Module | Lines | Verdict | Prune? |
|---|---|---|---|
| `modules/graph_adapter/` | 241 | Functional, graphify-aware reuse-check + stdlib fallback | Borderline |
| `modules/error_injection/` | 19 | Stub — just `is_enabled()` toggle, no actual injection | Placeholder |
| `reuse_check.py` | 115 | Token-jaccard similarity, core pillar B | NO |
| `state_store.py` | 233 | Solid: SQLite reconcile-first, 7 tests, NO-PROOF auto-falsify | NO |
| `verify_self.py` | 89 | Dogfood: AST neuter→redproof→assert fail→restore | NO |
| `module_lifecycle.py` | 145 | Functional but fragile: regex TOML parser, brittle name match | NO |
| `gate_runner.py` | 99 | Hardcodes `ksf/gates/` path (:22) — cannot find vendored gates | Critical defect |
| `cli.py` | 243 | argparse CLI, 7 subcommands | NO |

## META-FRAMEWORK FITNESS

**KSF is the right idea but not yet load-bearing.** It gates only itself. Specifics:

1. **Not installable.** `pip show keystone-framework` → not found. Charon vendors 5 of 9 gates in `tools/_vendor/ksf_gates/` with rewritten imports. The vendor header admits: *"Vendored rather than pip-installed: a cross-repo local-path dependency on a sibling checkout would break."* Every consumer forks.

2. **Vendor drift is live.** Charon's vendored `__init__.py` exports only 5/9 gates. gate_runner hardcodes `ksf/gates/` → finds zero charon gates. The actual mechanism runs through a separate adapter (`tools/check_coverage_ssot.py`) bypassing gate_runner. **KSF is not consumed — it's forked per-repo.**

3. **Hardcodes repo layout.** `.ksf/manifest.toml`, `.ksf/keystone.db`, `ksf/gates/` — not configurable. Non-standard layouts need fork-level changes.

4. **Zero cross-repo visibility.** Each repo has isolated `.ksf/keystone.db`. No federation, no de-duplication across repos — ironic for a framework meant to unify SG+SLOP+future.

5. **SLOP adoption cost.** SLOP has no `.ksf/`. Steps: create manifest, vendor or install KSF, write module.toml per module, red-proof tests per gate+module, wire to CI, resolve path-hardcoding. leak_guard and no_pipe_mask are orthogonal to SLOP's structure.

6. **No production CI.** The keystone GitHub Actions workflow runs only `pytest` — not `ksf gate`. KSF's 9 gates have never run in a CI pipeline outside manual invocation.

## TOP-3 FINDINGS

1. **KSF is the right idea but not yet load-bearing.** Sound architecture (reconcile-first, redproof, module lifecycle) but single-contributor, never pip-installed, never consumed unmodified by another repo, and never in production CI. Converging three repos onto it today would require ~6 weeks of hardening.

2. **Vendoring is the fatal structural flaw.** The vendored fork pattern (`tools/_vendor/ksf_gates/` with path rewrites) means KSF is forked per-repo — the exact problem it was meant to solve. Until KSF is `pip install`able with a configurable gate-path and consumed via import (not copy-paste), it cannot be the meta-framework.

3. **inert_code timing is REFUTED but the noise problem is worse.** 4.5s on 31K LOC (not 100s). But it produces 200+ false positives against charon because the resolver is best-effort. The **flagship class-detector** is functionally disabled by precision, not performance. Fixing this is the single highest-value investment — it's the gate that catches the programme's #1 failure class.