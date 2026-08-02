# KSF LOAD-BEARING PLAN

**Ticket:** KSF-LOAD-BEARING
**Date:** 2026-07-31
**Source:** FRAMEWORK-CONVERGE restructured after two-lane KSF audit.
**Status:** PLAN — implementation to be executed in keystone repo + consumers.

## PREMISE

KSF at `/home/stack/code/keystone`: 2,557 LOC, 16 commits, 28/28 tests pass in 11s.
Sound architecture (reconcile-first, redproof, module lifecycle) but single contributor,
never pip-installed, never consumed unmodified, never in production CI. The audit
verdict: "right idea, not yet load-bearing."

Four fixes make KSF capable of gating three repos (charon, rig, SLOP) instead of only
itself. Each is individually small; together they close the gap between "gate framework"
and "framework anyone can adopt."

## FIX 1: Make KSF installable

**Current state:** `pip show keystone-framework` → not found. Charon vendors 5 of 9
gates in `tools/_vendor/ksf_gates/` with rewritten imports. The vendor header admits:
*"a cross-repo local-path dependency on a sibling checkout would break."*

**Plan:**

1. Verify `pyproject.toml` is complete (already has `[build-system]`, `[project]`,
   `[project.scripts]`, `[tool.setuptools.packages.find]` — name `keystone-framework`,
   version `0.1.0`).
2. Ensure `pip install -e .` succeeds from keystone repo root.
3. Add a proper `pip install` path so consumers don't need a sibling checkout:
   - Option A: publish to PyPI (requires operator credentials — deferred).
   - Option B: `pip install git+https://github.com/nnyan/keystone-framework.git@v0.1.0`
     in consumer requirements.
   - Option C: `pip install /path/to/keystone` with explicit path — least preferred
     but works for CI where repos are co-located.
4. **Replace charon's vendored fork.** After KSF is installable:
   - Delete `tools/_vendor/ksf_gates/`.
   - Replace all `from tools._vendor.ksf_gates.X import check_X` with
     `from ksf.gates.X import check_X`.
   - Gate path configurable: KSF must find gates in the consumer repo's layout, not
     hardcoded `ksf/gates/` (see Fix 2).
5. **Prove with a consumer import:** `python -c "from ksf.gates import check_inert_code;
   print(check_inert_code)"` succeeding from a consumer repo with KSF installed.

**Files in keystone:** `pyproject.toml` (may need minor fixes), `setup.cfg` (if added).
**Files in charon:** `tools/_vendor/ksf_gates/*` (delete), gate callers (import fixup).

## FIX 2: Fix gate_runner's hardcoded ksf/gates/ path

**Current state:** `gate_runner.py:22` hardcodes `self.gates_dir = self.repo_root /
"ksf" / "gates"`. This finds zero charon gates (the real gates live at
`tools/_vendor/ksf_gates/`). The actual mechanism runs through a separate adapter
(`tools/check_coverage_ssot.py`) that bypasses gate_runner entirely. KSF is not
consumed — it's forked per-repo.

**Plan:**

1. Make `gates_dir` configurable via `.ksf/manifest.toml`:
   ```toml
   [paths]
   gates = "tools/_vendor/ksf_gates"  # or whatever the consumer layout uses
   ```
2. Fall back to `ksf/gates` if not configured (backward compat for keystone).
3. `repo_root` itself should be configurable via CLI flag `--repo-root` (already
   present in CLI per `ksf --repo-root . gate` usage).
4. **Retire the bypass adapter** (`tools/check_coverage_ssot.py`) if it becomes
   redundant after gate_runner works. Check: does `check_coverage_ssot` do anything
   gate_runner can't after the fix? If not, its callers switch to `ksf gate`.
5. **Prove with a run:** `ksf --repo-root /path/to/charon gate` finds and runs
   charon's gates (not just keystone's).

**Files in keystone:** `ksf/gate_runner.py` (:22, :26-28), `ksf/cli.py` (manifest
loading), `.ksf/manifest.toml` (schema update).
**Files in charon:** `tools/check_coverage_ssot.py` (retire), gate callers (switch
to `ksf gate`).

## FIX 3: Fix inert_code resolver precision

**Current state:** `_resolve_call()` at `inert_code.py:269` is best-effort and cannot
trace re-exports. 200+ false positives against charon (31K LOC). Noise — not speed
(4.5s) — is why it's unregistered. The flagship class-detector is functionally disabled.

**Root cause:** When module A does `from B import foo`, then module C does `import A;
A.foo()`, the resolver cannot connect C's `A.foo()` call to B's `foo` definition
because it doesn't trace the re-export chain (B → A → C). Every re-exported symbol
appears as "unreferenced" even though callers exist.

**Plan (test empirically, overturn if wrong):**

1. **Add re-export tracing to `_resolve_call()`.**
   - When resolving `head.tail` and `head` maps to a `from_imports` entry `(mod,
     orig)`, check whether the resolved target module `mod` has the symbol `tail`
     exported via `__all__` or defined in its `definitions`.
   - If not found, check whether the resolved module re-exports it (a chain).
   - Key insight: the information is already in `modules_info` — we just need to
     follow the re-export chain through `from_imports` across modules until we find
     the definition.
2. **Fallback: scope `inert_code` down** if full re-export tracing proves intractable.
   Options:
   - Opt-in per-directory: gate only specified packages, not the whole repo.
   - Require `@inert_by_design("reason")` annotation on known re-exported symbols.
   - Flag "possibly inert" with lower confidence rather than hard-failing.
   - **Prefer fix over scope-down.** The litellm_plane benchmark REQUIRES proper
     resolution — it's imported only by tests and must show up as inert.
3. **Empirical benchmark:** Run fixed `inert_code` against charon (31K LOC).
   - Before: 200+ false positives.
   - After: report the false-positive count. Target is <10% of initial.
   - **Must flag `src/charon/litellm_plane/`** (imported ONLY by tests) and must
     NOT drown that signal in noise.
4. **Red-proof the fix:** Write a targeted test that constructs re-export chains and
   asserts the resolver follows them. Example:
   ```
   # a.py: def foo(): pass
   # b.py: from a import foo  # re-export
   # c.py: from b import foo; foo()
   ```
   The resolver must find that `c.foo()` resolves to `a.foo`, marking it reachable.

**Files in keystone:** `ksf/gates/inert_code.py` (:269-303), tests for inert_code.

## FIX 4: Make KSF gate itself in CI

**Current state:** keystone GitHub Actions workflow (`ksf-gate.yml`) exists with
`ksf gate` + `ksf verify-self` steps, but it has apparently never been run in
production CI. The workflow references a self-hosted runner pool.

**Plan:**

1. Verify the workflow is active and running on push/PR.
2. If the self-hosted runner is unavailable (CI_RUNNER variable unset → falls back
   to `ubuntu-latest`):
   - Ensure `pip install -e .` works on `ubuntu-latest`.
   - Ensure `ksf gate` succeeds on `ubuntu-latest` (stdlib-only, should work).
3. **Prove with a green run:** Trigger a push to keystone, observe the workflow run,
   paste the green output showing `ksf gate` passing.
4. If the workflow is already configured correctly but just never triggered, a
   trivial push (e.g., bump patch version or add a comment) suffices.
5. **Dogfood:** KSF's own gates must gate KSF. The framework that enforces
   completeness must itself be subject to completeness checks.

**Files in keystone:** `.github/workflows/ksf-gate.yml` (verify, possibly no changes
needed — just trigger and verify).

## FIX 5: Adopt the class register

**Done in this ticket.** `fleet/state/KSF-CLASS-REGISTER.md` is the requirements spec
for any framework we converge on. 15 deduplicated classes from 30+ incidents, ranked
by frequency × blast radius. 10 classes hit 3+ times with no gate. This register
outlives the KSF question — it's the answer to "what must a framework catch?"

## DONE CONTRACT (verification checklist)

When implementation is complete, verify:

- [ ] **Installable:** Consumer imports KSF without a vendored copy.
  ```bash
  python -c "from ksf import __version__; print(__version__)"
  ```
- [ ] **gate_runner finds consumer gates:** Run against charon (or rig) and see
  real gates listed.
  ```bash
  ksf --repo-root /path/to/charon gate
  ```
- [ ] **inert_code precision:** Run against charon, report before/after false-positive
  counts. `litellm_plane` MUST appear in the after-list.
- [ ] **inert_code red-proof:** Resolver test passing with re-export chain fixtures.
- [ ] **KSF gates itself in CI:** Green workflow run on keystone showing `ksf gate` pass.
- [ ] **Class register landed:** `fleet/state/KSF-CLASS-REGISTER.md` present.
- [ ] **Vendored fork retired:** `tools/_vendor/ksf_gates/` deleted from charon,
  imports rewritten to `ksf.gates.*`.

## EXPLICITLY OUT OF SCOPE

- Do NOT converge SG/rig/SLOP onto KSF. That is re-decided after this lands.
- Do NOT add new gates for the 10 uncovered classes. Register them; building them
  is separate, sequenced work.
- Do NOT prune `leak_guard`/`wiring_alignment` in this ticket — proposed with
  evidence in the class register.
- Do NOT add cross-repo federation or `.ksf/keystone.db` sharing.

## RISKS

1. **Re-export tracing may be hard.** The manager hypothesis is that `_resolve_call()`
   can be fixed in <100 LOC. If it requires a full import graph solver, the honest answer
   may be to scope `inert_code` down (opt-in per-directory) rather than chase full
   resolution. The litellm_plane benchmark is the acid test.
2. **CI runner availability.** If the 4-LOM self-hosted runner is unavailable for
   keystone, the fallback to `ubuntu-latest` should work (KSF is stdlib-only +
   `pip install -e .`).
3. **Charon vendored import rewrite.** 5 gates are vendored, plus the bypass adapter.
   Rewriting imports is mechanical but must not break the existing gate suite.

## SEQUENCE

1. KSF-CLASS-REGISTER.md (this ticket — DONE).
2. Fix 4 (CI gate) — trivial, can be done independently.
3. Fix 1 (installable) — prerequisite for Fix 2 consumers to test.
4. Fix 2 (gate_runner path) — depends on Fix 1 for consumer testing.
5. Fix 3 (inert_code precision) — most technically risky, save for last after
   framework is otherwise solid.
6. Convergence question re-evaluated against evidence.

## REFERENCES

- `KSF-SURFACE-AUDIT.md` — gate assessment, performance, vendoring analysis
- `KSF-CLASS-CORPUS.md` — full incident corpus with source citations
- `/home/stack/code/keystone` — KSF source repo
- `GATE-GAP-LEDGER.tsv` — 8 classes, 25 rows of gate misses
