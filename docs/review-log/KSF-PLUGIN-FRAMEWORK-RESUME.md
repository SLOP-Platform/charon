# KSF-PLUGIN-FRAMEWORK-RESUME — review notes

**Ticket:** KSF-PLUGIN-FRAMEWORK-RESUME
**Date:** 2026-08-02
**Type:** DESIGN-REVIEW — audit, recommendation, verdict

## Decisions

### Decision 1: KSF is a library, not a framework (yet)
**Verdict:** CONFIRMED by evidence. Zero consumers in production. Charon vendored 5 of 9 gates rather than installing KSF. `gate_runner` hardcoded paths, `redproof` fails from installed venv.

### Decision 2: ca7d046 should be LANDED WITH CHANGES
**Verdict:** The stdlib-only prohibition removal is correct under adopt-first, but:
- Engine-layer isolation is a separate concern and should be preserved
- Plugin-namespace exemption (~3 LOC) beats nuking all enforcement (~215 LOC deleted)
- Red-proof tests should be skip-reasoned, not deleted

### Decision 3: KSF is NOT the right host for a shared test framework
**Verdict:** KSF answers "is this done?" (gate framework); pytest answers "does this work?" (test framework). The right answer is a thin shared config package wrapping pytest + plugins, distributed via pip install, with KSF gating the testing process.

### Decision 4: KSF should NOT be retired
**Verdict:** Sound architecture (reconcile-first, red-proof, module lifecycle). 5 fixes (KSF-LOAD-BEARING-PLAN) close the gap between "library" and "framework." Retiring it would lose the only mechanized completeness gate infrastructure we have.

### Decision 5: CORE-stdlib / PLUGIN-deps split avoids the collision
**Verdict:** The recorded architecture is `stdlib CORE + best-in-class PLUGINS`. If a `src/charon/plugins/` namespace exempts `check_stdlib_only()`, no prohibition removal is needed to adopt pytest-bdd or Hypothesis. This is the cheapest answer.

## Evidence Collected

- **Install test:** `pip install -e /home/stack/code/keystone` into clean venv → SUCCESS. `ksf gate` from installed venv → 3 of 9 gates FAIL (path dependency defect).
- **Gate execution audit:** `ksf gate` enumerated all 9 gates. Charon `tools/gates.json` has 20 gates; only `inert-code` is a KSF gate. The 5 vendored gates bypass gate_runner entirely.
- **Consumer count:** 0. Charon is the only user and uses vendoring, not dependency.
- **Commit ca7d046 review:** 14 files, -215/+85 lines. 2 enforcement functions deleted, 2 test classes deleted, 8 doc updates. Methodical but uses sledgehammer for a scalpel problem.
- **TOOL-SCAN re-examination:** "~0% adopt" verdict was pre-adopt-first framing. Under adopt-first, the question reverses and different answers emerge.
- **WIRING-PLAN status:** Part 1 DONE, Parts 2-4 NOT DONE. Stalled.
- **Class register:** 15 classes, 10 uncovered. Primary gap: no shared test framework exists.

## Open Questions (For Manager Synthesis)

1. Does the operator agree with the CORE/PLUGIN split, or was the intent to remove stdlib-only EVERYWHERE?
2. Which repo hosts the `charon-test-config` package — new standalone repo, or a subdirectory of an existing repo?
3. Is the engine-layer-dependency-isolation worth preserving as a separate gate, distinct from the stdlib-only supply-chain posture?
4. The other two lanes (BDD-FRAMEWORK-EVAL, HYPOTHESIS-FAILOVER-EVAL) feed their tool verdicts into this recommendation — if one is ADOPT and the other is REJECT, does the thin config package bundle only the adopted one?
