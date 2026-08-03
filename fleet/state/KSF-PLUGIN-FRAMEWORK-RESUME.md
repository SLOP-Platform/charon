# KSF-PLUGIN-FRAMEWORK-RESUME — what happened to the framework, and what now

**Ticket:** KSF-PLUGIN-FRAMEWORK-RESUME
**Date:** 2026-08-02
**Source:** Operator question — "I had previously asked for a framework that all projects plug into, not sure what happened to that."
**Status:** DESIGN-REVIEW — audit, recommendation, verdict. Lands nothing, merges nothing.

---

## a. Operator Answer — What Happened to the Framework You Asked For

You asked for a framework all projects plug into. We built it — it's called **Keystone** (KSF), at `/home/stack/code/keystone`. It's 2,557 lines of Python, has 9 gates (completeness checks for what "done" means), and all 28 of its tests pass. It works.

But it was never *plugged into*. The only consumer — Charon — **vendored** (copied verbatim) 5 of KSF's 9 gates into its own source tree (`tools/_vendor/ksf_gates/`) rather than installing KSF as a package. This vendoring was intentional: "a cross-repo local-path dependency on a sibling checkout would break," so they copied the code instead of depending on it. The result: KSF exists as a separate project, Charon has a stale fork of 5/9 gates, the remaining 4 gates exist only inside the KSF repo itself, and KSF has never gated anyone else's code in production CI. You asked for a plug-in framework and got a library that was copy-pasted instead of plugged in.

The good news: the architectural bones are sound (reconcile-first, red-proof tests, module lifecycle). The wiring plan to make it load-bearing (`KSF-LOAD-BEARING-PLAN.md`) has 5 fixes, all individually small. Only Fix 4 (CI gating) and Fix 5 (class register) are done. Fixes 1-3 (installable, path-configurable gate runner, inert_code precision) are the gap between "library" and "framework."

---

## b. Q1 — What Is KSF Today, Actually?

### Install Test

**Result: INSTALLS cleanly.** Installed into a clean Python 3.12 venv:

```
$ python3 -m venv /tmp/ksf-test-venv
$ /tmp/ksf-test-venv/bin/pip install -e /home/stack/code/keystone
Successfully installed keystone-framework-0.1.0
$ /tmp/ksf-test-venv/bin/ksf --help
usage: ksf {reconcile,gate,module,reuse-check,verify-self} ...
```

**BUT** the gates do not all pass when invoked from an installed venv (as opposed to in-repo):

| Gate | Status | Why |
|---|---|---|
| `coverage_ssot` | PASS | 100% (9/9 rules covered) |
| `fail_loud` | PASS | |
| `inert_code` | FAIL | `check_inert_code` unreachable (0 callers) + `check_reuse` unreachable — installed-venv paths break the caller-graph |
| `leak_guard` | PASS | |
| `no_pipe_mask` | PASS | |
| `no_skip_game` | PASS | |
| `no_vacuous` | FAIL | Pytest collection failed (exit=1) — red-proof test paths differ in installed venv |
| `redproof` | FAIL | **All 9 red-proof tests fail** — `.ksf/gates/test_redproof_*.py` files exist only in the repo directory, not in the installed package |
| `wiring_alignment` | PASS | |

**Root cause:** `gate_runner.py:22` hardcodes `self.gates_dir = self.repo_root / "ksf" / "gates"` — the installed package has no `.ksf/` directory, only the source repo does. `redproof` looks for companion test files at `.ksf/gates/test_redproof_<name>.py` — in an installed venv, those paths don't exist. KSF is designed to run *from its own source tree*, not as an installed framework gating another repo. This is the central architectural defect identified in `KSF-LOAD-BEARING-PLAN.md` Fix 2.

`verify-self` (the dogfood meta-harness) **PASSES** from the installed venv — it neuters each gate and asserts the red-proof catches the neutering, operating within the installed package structure.

### Gate Execution — What Runs Where

| Gate | KSF self-gates | Charon (vendored) | Charon (registered gate) |
|---|---|---|---|
| `coverage_ssot` | YES (ksf gate) | YES (adapter `tools/check_coverage_ssot.py`) | NO — not in `tools/gates.json` |
| `wiring_alignment` | YES | YES (adapter `tools/check_wiring_alignment.py`) | NO |
| `redproof` | YES | YES (adapter `tools/check_redproof.py`) | NO |
| `no_vacuous` | YES | YES (adapter `tools/check_no_vacuous.py`) | NO |
| `fail_loud` | YES | YES (adapter `tools/check_fail_loud.py`) | NO — not in `tools/gates.json` |
| `no_skip_game` | YES | NO — not vendored | NO |
| `no_pipe_mask` | YES | NO — not vendored | NO |
| `leak_guard` | YES | NO — not vendored | NO |
| `inert_code` | YES | YES (adapter `tools/check_inert_code.py`) | YES — registered as `inert-code`, `ci_step: true` |

**Key finding:** The 5 vendored gates (`coverage_ssot`, `wiring_alignment`, `redproof`, `no_vacuous`, `fail_loud`) run as standalone adapter scripts that **bypass gate_runner entirely**. They are NOT registered in `tools/gates.json` and are NOT wired into the CHECKS list. The `inert_code` gate is the ONLY KSF gate properly registered in Charon's 20-gate system — and it's also the one with 200+ false positives due to the re-export resolution defect documented in `KSF-LOAD-BEARING-PLAN.md` Fix 3.

**The GREEN RECEIPT pattern (registered-but-dead gates):** Of Charon's 20 registered gates, 2 (`validate-board`, `reachability-gate`) have `ci_step: false` — they are registered but do not execute in any automated pipeline. A prior audit (`WORK-FRAMEWORK-WIRING-PLAN.md` Part 1) found 5 orphaned gates and wired 4 of them; the 5th (`workflow-policy`) was also wired.

### Consumer Count

**ZERO real consumers.** The only repository that uses any KSF code is Charon, and it does so via vendoring (copy-paste), not by installing KSF as a dependency. No other repo imports `ksf.*` or lists `keystone-framework` as a dependency. KSF's own internal modules (`graph_adapter`, `error_injection`) are experimental and self-referential — features of KSF, not consumers of KSF.

**Consumer count: 0.**

A framework nothing plugs into is a library, and calling it a framework is how it stayed invisible.

### Relationship to WORK-FRAMEWORK-WIRING-PLAN and WORK-FRAMEWORK-TOOL-SCAN

**`WORK-FRAMEWORK-TOOL-SCAN.md` (2026-07-11):** Scanned 5 tool categories for the unified work-creation framework. Verdict: **~0% adopt, ~100% thin-glue/wiring.** Every category concluded "KEEP-CUSTOM" — KSF `inert_code` beats `vulture`, `graphify` + KSF `reuse_check` are best-in-class, `tools/gates.json` + `gate_runner.py` are the right gate framework. No external tool was recommended for adoption. **Re-examination under adopt-first:** the scan was done BEFORE the adopt-first directive (2026-07-21). It asked "what tool already exists?" and when none matched perfectly, it concluded "keep our custom one." Under adopt-first, the question is reversed: "what existing tool is closest, and what's the least glue needed?" — a different frame that would have produced different answers (e.g., `pytest` plugins for test framework, `pre-commit` hooks for gate-style checks). The scan's "0% adopt" conclusion is a function of its framing, not of the actual tool landscape.

**`WORK-FRAMEWORK-WIRING-PLAN.md` (2026-07-11):** 4-part plan connecting existing pieces into a creation-gate + done-contract. Status:
- **Part 1 (orphan-gate detection): DONE.** All registered gates now execute.
- **Part 2 (inert_code wire): PARTIALLY DONE.** `inert_code` is now a registered gate (`ci_step: true`) with a Charon-side adapter, but the vendor-vs-dep question was never resolved — it's still a vendored copy, not a true KSF plugin. The re-export resolution defect (Fix 3 in KSF-LOAD-BEARING-PLAN) means the gate produces 200+ false positives and is functionally muted.
- **Part 3 (reuse dedup at ticket birth): NOT DONE.** `reuse_check` exists but is not called during intake.
- **Part 4 (done-contract): NOT DONE.** No composition of built+wired+dogfood-proven exists.

**The plan is partially executed but stalled.** The core insight — that everything needed already exists, only wiring is required — remains valid, but the wiring was never completed.

---

## c. Q2 — The Stdlib-Only Collision

### Branch Review: `chore/remove-stdlib-only-prohibition` (commit `ca7d046`)

**Repo:** `/home/stack/code/charon` (NOT `/home/stack/code/keystone` — this is a Charon-side change).
**Net diff:** 14 files, +85 lines, -215 lines. PUSHED WITH NO PR. One of 211 `pushed-no-pr` findings.

### What Was Removed

**Enforcement code (2 files, ~105 lines deleted):**

1. **`check_stdlib_only()` in `tools/check_arch.py`** — AST-scanned every `src/charon/*.py` file and flagged any third-party `import`/`from ... import`. Covered the gateway, proxy, CLI, netutil — all top-level core files. This was the primary enforcement mechanism.

2. **`scan_engine()` / `scan_engine_file()` in `tools/check_boundary.py`** — AST-scanned every file under `src/charon/engine/` and `src/charon/ports/worker.py` for non-stdlib imports. This was the secondary enforcement, specifically targeting the engine layer (ADR-0010 D2, ADR-0005 R3).

**Red-proof tests (2 files, ~124 lines deleted):**

3. **`TestStdlibOnly` class in `tests/test_check_arch.py`** — 5 adversarial tests ensuring the `check_stdlib_only` gate caught violations (third-party import, third-party from-import) and didn't false-positive (stdlib, charon, relative).

4. **7 engine boundary test functions in `tests/test_boundary.py`** — Tested empty-dir, stdlib-passes, third-party-flags, relative-passes, mixed-imports, ports-worker.

**Documentation/Policy (8 files, +85 lines of notes):**

5-12. **`pyproject.toml`**, **`docs/SUPPLY-CHAIN.md`**, and **6 ADRs** (0001, 0005, 0010, 0012, 0014, 0018, 0019) — each received a "SUPERSEDED (stdlib-only)" dated note. These are accurate and well-written — each one explicitly states what clause is retired while preserving what is NOT retired (layer isolation, anti-dilution, product-clean).

13. **`tools/gates.json`** — Removed "stdlib-only" from the `check-arch` gate's `covers` and `invariant` fields. Cosmetic.

### Protections Lost (Per Deletion)

| Deletion | What Protection It Dropped |
|---|---|
| `check_stdlib_only()` (entire function) | Any third-party package can now be imported in top-level `src/charon/*.py` files without CI failure |
| `scan_engine()` (entire function) | Any third-party package can now be imported in `src/charon/engine/` and `src/charon/ports/worker.py` |
| `TestStdlibOnly` (5 test methods) | Automatic verification that the check catches violations — no safety net if someone reinstates the check |
| 7 engine boundary tests | Same — red-proof tests for the engine scan are gone |

### Protections Preserved

- **Layer isolation unchanged:** `check_boundary.py` still enforces engine↔gateway isolation (cannot import each other).
- **Circular import detection unchanged.**
- **Product-clean (no vendor hardcodes) unchanged.**
- **Host-project boundary unchanged.**
- **ADR-0010 D2 anti-dilution (gateway path transitively imports no engine modules) unchanged** — tested via subprocess, not affected.

### Assessment

The commit is **methodical and thorough** — every enforcement mechanism deleted has a corresponding documentation update explaining why. It's clean (all 16 CI gates were green when pushed). It does NOT add a dependency — it removes the prohibition on adding one. The -215/+85 ratio means it deleted exactly the enforcement it meant to delete and documented it clearly.

### Recommendation on ca7d046

**LAND-WITH-CHANGES.** The core content — removing the stdlib-only prohibition — is correct under the adopt-first directive. But two issues:

1. **The engine boundary is a separate concern from stdlib-only.** `scan_engine()` was removed alongside `check_stdlib_only()`, but engine isolation (no third-party dependencies in the engine *as a layer isolation concern*, not a supply-chain concern) may still be worth enforcing. The commit bundles "stdlib-only" (a supply-chain posture that adopt-first overrides) with "engine-layer purity" (an architectural invariant that may still be desired). These should be separated: land the stdlib-only prohibition removal, but consider whether engine-layer dependency isolation should be a separate gate with different justification.

2. **Red-proof tests should not be deleted just because the gate is.** If the gate is ever reinstated (under different justification), the tests must come back too. Better to convert them to SKIP-reasoned `pytest.mark.skip` with a comment explaining they protect a retired invariant, preserving institutional memory.

### Does the CORE-stdlib / PLUGIN-deps Split Avoid the Need for ca7d046 Entirely?

**Yes, partially.** If the architecture is:
- **CORE remains stdlib-only** (the privileged loop in `src/charon/engine/`, `src/charon/gateway.py`, `src/charon/cli.py`)
- **PLUGINS can have dependencies** (a separate package namespace, e.g., `src/charon/plugins/`)

Then adopting `pytest-bdd` or `Hypothesis` in a PLUGIN requires **no prohibition removal at all** — the CORE stays stdlib-only, the PLUGIN pulls in what it needs. This is the cheapest possible answer and was the recorded architecture (`[[ksf-modular-plugin-best-in-class]]`).

**But this means `ca7d046` is the WRONG tool for adopting test frameworks.** It removes the prohibition EVERYWHERE (core + plugins), when the need is only to allow dependencies in PLUGINS. The more surgical approach — add a `src/charon/plugins/` namespace that `check_stdlib_only` explicitly exempts — would add ~3 lines to `check_stdlib_only()` instead of deleting ~105 lines of enforcement. This preserves core integrity while enabling plugin adoption.

**Verdict on the collision:** The CORE/PLUGIN split solves it without `ca7d046`. The branch's approach (nuke all enforcement) is a sledgehammer for a problem that needs a scalpel. LAND-WITH-CHANGES: separate engine-layer-isolation from stdlib-only, add a plugin-namespace exemption instead of deleting the checker, keep red-proof tests as skip-reasoned.

---

## d. Q3 — Is KSF the Right Host for a Shared Test Framework?

### Short Answer

**No.** KSF is a GATE framework (answers "is this done?"), not a TEST framework (answers "does this work?"). Using it to host a shared test framework would be like using a door lock as a door — related but wrong tool. The right answer is a separate, thin shared test configuration, with KSF gating THAT configuration.

### What "Plugging In" Concretely Means

The operator wants ONE framework every project plugs into. The concrete mechanism for a TEST framework is one of:

| Mechanism | What It Looks Like | Viability |
|---|---|---|
| **Shared pytest conftest** | A single `conftest.py` file defining shared fixtures, markers, plugins. Consumed via `pip install -e ../shared-test-config` or `pytest --override-ini conftest=...` | HIGH — standard pytest pattern, no new tooling |
| **Shared pip-installable package** | A `charon-test-utils` package on PyPI (or `pip install git+https://...`). Contains conftest, fixtures, shared helpers, plugin configs. Versioned, dependency-managed. | HIGH — standard Python package distribution |
| **Copied config (with drift detection)** | Copy a `pytest.ini` / `conftest.py` into each repo, with a CI gate that verifies the copy hasn't drifted from the canonical version. | MEDIUM — works for config, scales poorly |
| **Monorepo tooling** | Move both repos into one monorepo with shared tooling at root. | LOW — operator has explicitly chosen multi-repo |
| **KSF as the test framework** | KSF's `module` lifecycle becomes the test runner, KSF gates become the test assertions. | VERY LOW — reinventing `pytest`, `unittest`, and every test assertion library |

### The Multi-Repo Reality

Charon (public product) and charon-private (rig) are separate repos with separate CI. How does a shared configuration reach both without a vendored copy that drifts?

**The proposed mechanism:** A thin Python package (`charon-test-config`) that is:

1. **Pip-installable** from a Git URL (no PyPI needed initially):
   ```
   pip install git+https://github.com/nnyan/charon-test-config.git@v0.1.0
   ```
2. **Version-pinned** in each consumer's `pyproject.toml` (as a `dev` dependency, not a runtime dependency):
   ```toml
   [project.optional-dependencies]
   dev = ["charon-test-config @ git+https://github.com/nnyan/charon-test-config.git@v0.1.0"]
   ```
3. **Contains:**
   - `conftest.py` with shared fixtures (temp dirs, git repos, etc.)
   - `pytest.ini` fragment with shared markers and plugins
   - If BDD is adopted: shared step definitions, scenario directory convention
   - If Hypothesis is adopted: shared strategy registrations, profile configs
   - **NOT** a copy of pytest-bdd or Hypothesis — those are declared as the shared package's own dependencies
4. **Drift-detected by a CI gate** in each consuming repo:
   - The gate runs `pip install` of the shared config and asserts the installed version matches the pinned version
   - If someone adds a local override, the gate fails — no silent drift

This is **exactly the same mechanism** as the `[[ksf-modular-plugin-best-in-class]]` pattern: "PLUGINS wrap industry best-in-class tools FIRST." The "plugin" in this case is a thin package wrapping `pytest` + plugins, and the shared config is the plugin.

### Why This Beats Maintaining KSF as the Framework

| Concern | KSF as Test Framework | Shared Config Package |
|---|---|---|
| **Test discovery** | Would need to build — pytest already does this | pytest does it for free |
| **Fixtures** | Would need to define — pytest has `conftest.py` | Reuse pytest's proven pattern |
| **Reporting** | Would need to build — pytest has `--junitxml`, `--html`, plugins | Use pytest's ecosystem |
| **IDE integration** | Would need plugins for every editor | pytest is supported by every Python IDE |
| **Community** | One contributor (you) | pytest: thousands of contributors, millions of users |
| **Maintenance burden** | 2,557 LOC of custom code to maintain | ~50 LOC of config to maintain |
| **Onboarding** | Learn KSF's module lifecycle, gate concepts, reconcile protocol | Learn pytest (already the standard) |
| **Multi-repo distribution** | KSF has no packaging story (hardcoded paths, repo-root assumption) | `pip install` is the standard Python distribution story |

### KSF's Proper Role in This Picture

KSF should NOT be retired. Its proper role is to **GATE** the test framework, not to BE the test framework:

- KSF's `no_vacuous` gate ensures the test suite actually collects tests (0 tests = RED)
- KSF's `redproof` gate ensures every gate has a companion negative test
- KSF's `coverage_ssot` gate ensures every declared rule has test coverage
- KSF's `inert_code` gate ensures tested code is actually reachable from entrypoints

These are answers to "is testing done properly?" — not "does the code work?" The latter is what pytest + plugins (pytest-bdd, Hypothesis) answer. The right architecture is:

**KSF (gate framework) WRAPPING `pytest` + plugins (test framework), WITH a thin shared config package (distribution).**

---

## e. RISK Section

### What Breaks If We Adopt the Shared Config Package

1. **Nothing breaks immediately.** Adding a `charon-test-config` dev dependency does not change runtime behavior. The risk is deferred to the adoption of specific test tools (pytest-bdd, Hypothesis), which belong to the other two lanes (BDD-FRAMEWORK-EVAL, HYPOTHESIS-FAILOVER-EVAL).

2. **If ca7d046 is landed AS-IS:** All enforcement is removed. A future contributor could silently add `import requests` to the engine with no CI rejection. The layer isolation checks (`check_boundary.py`) are still intact and would catch engine↔gateway cross-imports, but they would NOT catch engine→third-party imports. This is the reason for the LAND-WITH-CHANGES recommendation — keep the plugin-specific exemption rather than nuking all enforcement.

3. **If the shared config package becomes stale:** The version-pin + drift-detection gate prevents silent drift. The worst case is a version-bump that changes fixture signatures and breaks downstream tests — this is a standard Python dependency problem, not a framework problem.

### What Rots If We Do NOT Adopt (and Do Nothing)

1. **KSF continues as a library, not a framework.** Charon's vendored fork will increasingly diverge from the KSF source. The 5 vendored gates will become a separate codebase (already has different import paths and adapter wrappers). The remaining 4 KSF gates (`no_skip_game`, `no_pipe_mask`, `leak_guard`, `redproof`'s dogfood harness) exist only in the KSF repo and gate only KSF itself.

2. **The operator's request ("one framework all projects plug into") remains unfulfilled.** Each repo continues with its own ad-hoc test configuration. There is no shared mechanism to prove "this works" across projects.

3. **The inertia against adoption grows.** The current posture — vendored copies, hardcoded paths, repo-root assumptions — makes the adoption story harder over time, not easier. More custom code accumulates around the vendored gates, making a switch to native KSF import progressively more expensive.

4. **The class register gap widens.** `KSF-CLASS-REGISTER.md` documents 15 deduplicated failure classes. 10 of 15 have NO KSF gate. Without a shared framework, these classes are addressed piecemeal per-repo, and the same class can be fixed in one repo while festering in another.

---

## f. Retirement/Replacement Verdict

**KSF should NOT be retired.** It has a clear, defensible role: a gate framework that answers "is this complete?" Its 9 gates cover real failure classes, and the architectural pattern (reconcile-first, red-proof, module lifecycle) is sound.

**KSF should NOT be the test framework.** The operator's request for "a framework all projects plug into" should be satisfied by TWO things:

1. **A thin shared test config package** (pypi-installable, version-pinned, drift-detected) — this is the "framework all projects plug into" for TESTING. It's not a bespoke framework; it's a thin wrapper around `pytest` + adopted plugins, distributed via standard Python packaging. Under adopt-first, "ours already exists" is not a reason to keep KSF as the test framework — a thin wrapper around pytest IS the more maintainable choice.

2. **KSF as the GATE framework** — make it properly installable (Fix 1), configurable (Fix 2), and precise (Fix 3) per `KSF-LOAD-BEARING-PLAN.md`. Once it's a real package, retire Charon's vendored forks and make Charon a real consumer (plug in, don't copy-paste). Then extend to charon-private and SLOP.

### Concrete Next Steps (For the Manager's Synthesis)

1. **Land ca7d046 WITH CHANGES** — separate engine-layer-isolation from stdlib-only; add plugin-namespace exemption rather than deleting enforcement.
2. **Complete KSF-LOAD-BEARING-PLAN Fixes 1-3** — make KSF installable, path-configurable, and precise. This unblocks the vendored fork retirement.
3. **Create `charon-test-config`** as a thin package (can start as a single `conftest.py` in its own repo). The BDD-FRAMEWORK-EVAL and HYPOTHESIS-FAILOVER-EVAL lanes determine its contents.
4. **Wire KSF as a gate in both repos** (not vendored) — prove `ksf gate --repo-root /path/to/charon` works against a real consumer.
5. **Extend the class register with gates** — build the missing gates for the top 10 uncovered failure classes, sequenced by frequency × blast radius.

---

## References

- `/home/stack/code/keystone` — KSF source (2,557 LOC, 9 gates, 28 tests)
- `/home/stack/code/charon` — Charon product (vendored KSF gates at `tools/_vendor/`)
- `KSF-LOAD-BEARING-PLAN.md` — 5 fixes to make KSF load-bearing
- `WORK-FRAMEWORK-WIRING-PLAN.md` — 4-part wiring plan (Part 1 DONE)
- `WORK-FRAMEWORK-TOOL-SCAN.md` — ~0% adopt / ~100% wiring verdict (pre-adopt-first framing)
- `KSF-SURFACE-AUDIT.md` — Gate assessment, performance, vendoring analysis
- `KSF-CLASS-REGISTER.md` — 15 deduplicated failure classes from 30+ incidents
- `GATE-GAP-LEDGER.tsv` — 8 classes, 25 rows of gate misses
- Commit `ca7d046` on branch `chore/remove-stdlib-only-prohibition` — stdlib-only prohibition removal
