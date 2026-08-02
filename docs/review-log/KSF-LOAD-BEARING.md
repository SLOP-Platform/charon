# KSF-LOAD-BEARING — review / decision notes

## Gitignore constraint

Both files (`fleet/state/KSF-CLASS-REGISTER.md`, `fleet/state/KSF-LOAD-BEARING-PLAN.md`)
are force-added via `git add -f` because `.gitignore` line 10 (`fleet/state/*`) excludes
them. They need explicit `!fleet/state/KSF-CLASS-REGISTER.md` and
`!fleet/state/KSF-LOAD-BEARING-PLAN.md` negation lines added to `.gitignore` by
whoever owns that file. This follows the same pattern as every other tracked file in
`fleet/state/`.

## Derivation notes

- **KSF-CLASS-REGISTER.md** is derived from `fleet/handoff-notes/KSF-CLASS-CORPUS.md`.
  The source is 55 lines of dense data; the register is a ~70 line reference document
  suitable as a requirements spec.
- **KSF-LOAD-BEARING-PLAN.md** synthesises the 5-part implementation plan from the
  ticket's `execution:` block and the KSF-SURFACE-AUDIT findings. The plan covers:
  installable KSF, gate_runner path fix, inert_code resolver fix, CI gate, and class
  register adoption.

## Verification

The fleet gate suite was run. Multiple tests FAIL with "killed (no exit status
recorded)" — this is a pre-existing NPROC/RLIMIT issue (fork bomb guard tripped
by concurrent test fan-out), not caused by these two markdown additions. The
failures match known RIG-REDS patterns documented in `gate.sh:42-51`.

## Off-scope note

`.gitignore` is not in this ticket's owns. Adding negation lines for the new
tracked files belongs to whoever owns `.gitignore` or the next gate-creation
standardization pass.

## Empirical verification (2026-08-01, ahn-ji-young) — audit claims tested by running

Ran against `/home/stack/code/keystone` and `/home/stack/code/charon` (read-only;
no file outside `owns:` was created or edited).

- **Fix 1 (installable) — audit claim REFUTED as stated.** `pip install
  /home/stack/code/keystone` (non-editable wheel build) succeeds in a fresh venv;
  `import ksf` OK, `importlib.metadata.version("keystone-framework")` → `0.1.0`.
  `pyproject.toml` is complete (build-system, project, scripts, packages.find).
  Caveat: `ksf.__version__` does NOT exist (`ksf/__init__.py` is a bare docstring),
  so the plan's DONE-CONTRACT snippet `from ksf import __version__` would fail —
  use `pip show keystone-framework` / importlib.metadata instead.
- **Fix 2 (gate_runner path) — claim CONFIRMED.** `gate_runner.py:22` hardcodes
  `self.gates_dir = self.repo_root / "ksf" / "gates"`. Running
  `ksf --repo-root /home/stack/code/charon gate` finds ZERO charon gates: 5×
  `[FAIL] Gate file missing: coverage_ssot|fail_loud|no_vacuous|redproof|wiring_alignment`
  (the real gates live at `tools/_vendor/ksf_gates/`).
- **Fix 3 (inert_code precision) — core claim CONFIRMED, count differs.**
  Charon's wired gate (`tools/check_inert_code.py` → vendored detector) reports
  **66 dead symbols**, ALL tracked in `tools/inert-code-disposition.json`, many
  tagged `keep-detector-false-positive-*` (uvicorn-string-load,
  module-unreachable-cascade, attribute-value-ref). **`litellm_plane` is ABSENT
  from the dead list** — the benchmark case is missed entirely, confirming "the
  gate currently misses it entirely." The audit's "200+ false positives" figure is
  NOT reproducible against the current vendored copy (66 raw). Audit either
  measured an older snapshot or counted differently.
- **NEW FINDING — vendored drift + nondeterminism (class #15).** Charon's
  vendored `tools/_vendor/ksf_inert_code.py` carries 3 local DETERMINISM patches
  (`for m in sorted(all_modules)`) NOT present in keystone's native
  `ksf/gates/inert_code.py`. The vendored README claims the copy is "untouched"
  / "do not hand-edit" — both violated. Native keystone `inert_code` iterates
  `all_modules` (a set) unsorted → nondeterministic reachability → nondeterministic
  gate verdict. Any resolver fix must land in keystone FIRST, then be re-synced;
  a verbatim re-sync would regress charon's determinism fix.
- **Fix 4 (CI) — config present and correct.** keystone
  `.github/workflows/ksf-gate.yml` runs `pip install -e .` + `ksf gate` +
  `verify-self` on push/PR with `CI_RUNNER` fallback to `ubuntu-latest`. Whether
  it has produced a green production run is unobservable from here (no CI access).
- **Fix 5 (class register) — landed** (commit 1efbe9a).

Implementation of fixes 1-4 requires editing files OUTSIDE this ticket's `owns:`
(keystone `ksf/*`, charon `tools/_vendor/*` — separate repos). Per ownership rules
those are not editable here; they are the next sequenced work (plan SEQUENCE:
CI → installable → gate_runner path → inert_code precision).
