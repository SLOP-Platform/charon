# WCI-FOLLOWON — merge_after concurrency payoff (§5.1 proof implementation)

## Dependencies & sequence
**Wave: 2** (after WCI-MVP landed on master + DSGN-WCI-PROOF approved).
**depends_on: WCI** — extends the MVP's reconcile/ordering layer.
**real-dep: DSGN-WCI-PROOF** — the §5.1 proof contract IS the spec for this build.

## Why
WCI-MVP landed the static reconciler + depth pre-sort (WCI-1 + WCI-2). The `merge_after`
edge label and its concurrency payoff were HELD until the §5.1 semantic-independence proof
contract was approved. DSGN-WCI-PROOF is now approved. This ticket implements:

1. **WCI-4:** The `merge_after` edge label on the unit schema + the F1 gate-relaxation in
   `board.claimable`. A `merge_after` edge permits two units to be CLAIMED concurrently
   ONLY when a positive `IndependenceCertificate` exists for the pair. Without a
   certificate (or with a failed certificate), the edge is conservatively demoted to a
   normal `depends_on` — zero new concurrency, zero false-concurrency path.

2. **§5.1 proof computation:** The 4-signal semantic-independence analysis, implemented
   as pure deterministic functions in a new `engine/semantic_proof.py` module. This is the
   "proof engine" that produces `IndependenceCertificate` instances consumed by `claimable`.

3. **WCI-6 (auto-slice) is NOT in scope.** Gated behind ADR-0008 Phase-2 conflict-rate
   tripwire — deferred.

This is the concurrency payoff Pillar 3 has been waiting for. The F1 invariant (§7.1) is
the safety guarantee: the split is invented by the proof, never by the label alone.

## What to build

### 1. `merge_after` schema (intake.py + board.py)

Add an optional `merge_after: list[str]` field to the Unit model in `intake.py`.
A unit may have BOTH `depends_on` AND `merge_after` edges. The distinction:
- `depends_on(A)` → "B cannot start until A is DONE" (build prerequisite)
- `merge_after(A)` → "B must land/merge AFTER A, but may build concurrently IF
  the pair passes §5.1 proof" (land-order, potentially concurrent)

In `board.py`:
- `_deps_done()` currently checks all `unit.depends_on` are DONE.
- Extend it: for each dep in `unit.depends_on() UNION unit.merge_after()`, check:
  - If dep is in `merge_after` AND a certificate exists with `cert.proven == True`
    → dep is satisfied (skip; the upstream need not be DONE).
  - Otherwise → dep must be DONE (conservative-demote: F1 third branch).
- The M-owns gate (board.py:227-235) is UNCHANGED. Two units with overlapping
  `owns` still serialize via lowest-id regardless of certificates (F1 condition ii).
- Certificates are stored on the board as annotations: `board.set_cert(A, B, cert)`.

### 2. `engine/semantic_proof.py` — the 4-signal computation

New module, stdlib-only (no external dependencies). One public entrypoint:

```python
def compute_certificate(
    unit_a: Unit,
    unit_b: Unit,
    repo_path: Path,
    config_dir: Path | None = None,
) -> IndependenceCertificate:
```

Implements the 4 signals per DSGN-WCI-5-1-PROOF.md:

**Signal 1 — Import-graph reachability:**
- Parse `import`/`from-import` statements in all `src/charon/` modules using Python's
  `ast` module. Build a directed graph. Follow re-export chains (`__init__.py` →
  submodule).
- Compute transitive reachability from unit A's owned files and unit B's owned files.
- If A reaches B's files OR B reaches A's files → FAIL.
- Dynamic imports (non-literal strings) → FAIL (uncertainty → conservative).
- Ignore stdlib and third-party imports.

**Signal 2 — Shared-symbol analysis:**
- For each owned file, extract module-level write sites (Assign, AugAssign targets,
  decorator calls to names imported from another src/charon/ module).
- Exclude function/method-local scopes. Class/function definitions are NOT writes
  (unless decorated with a mutating call).
- A decorator like `@registry.register` on a function at module scope is a write to a
  shared object → flag the callable name as a write.
- Extract module-level read sites (Name nodes at module scope, excluding the write
  targets themselves).
- Intersect: A's write set ∩ B's read set OR B's write set ∩ A's read set → FAIL.
- `os.environ` mutations at module scope → FAIL.
- Dynamic names (variable, not literal identifier) → FAIL.

**Signal 3 — Shared-config touch:**
- Enumerate all config files: `~/.charon/charon-config.json`, `tiers.json`, `secrets.json`,
  plus any `*.json`/`*.yaml` in `~/.charon/`.
- Extract key sets from each file.
- Scan owned source files for string-literal config key references matching the real keys
  (`config["key"]`, `.get("key")`, etc.).
- If both units reference the same key in the same config file → FAIL.
- Sub-key overlap (e.g., both touch `providers` top-level key, even different sub-keys)
  → FAIL.
- Dynamic key access (`config[var]`) → FAIL.
- Any owned file writes to `secrets.json` → FAIL.

**Signal 4 — Test co-failure:**
- Map owned files to test files by convention: `src/charon/foo.py` → `tests/test_foo.py`
  (and `tests/test_foo/` directory).
- If units share a test file → FAIL.
- If unit A's test imports from unit B's owned modules (or vice versa) → FAIL.
- Scan ancestor `conftest.py` files up to test root:
  - Fixtures imported from the other unit's modules → FAIL.
  - `@pytest.fixture(autouse=True)` whose directory scope covers both units' tests → FAIL.
- If either unit has no test file → FAIL (conservative: can't prove negative).

### 3. Certificate caching on the board

- `board.set_cert(a_id, b_id, cert)` — stores the certificate.
- `board.get_cert(a_id, b_id)` — retrieves it (returns None if not computed).
- Certificates are computed ONCE, when a `merge_after` edge is first added and both
  units transition to READY. Never recomputed on the drain hot path.
- `claimable` reads the pre-computed `cert.proven` field.

### 4. `claimable` extension (board.py)

```python
def _deps_done(self, unit: Unit) -> bool:
    all_deps = set(unit.depends_on) | set(getattr(unit, 'merge_after', []))
    for dep_id in all_deps:
        dep = self._units.get(dep_id)
        if dep is None:
            raise BoardError(...)
        if dep.state == DONE:
            continue
        # merge_after edge with positive cert → allow concurrent
        if dep_id in getattr(unit, 'merge_after', []):
            cert = self._get_cert(dep_id, unit.id)
            if cert is not None and cert.proven:
                continue
        return False
    return True
```

### 5. Tests (`tests/test_semantic_proof.py`)

- `test_signal1_disjoint_imports_pass` — two units whose owned files don't import each other
- `test_signal1_direct_import_fails` — unit B imports from unit A's owned file
- `test_signal1_transitive_import_fails` — chain through a third module
- `test_signal1_reexport_chain_fails` — `__init__.py` re-export hides coupling
- `test_signal1_dynamic_import_fails` — `importlib.import_module(var)` → FAIL
- `test_signal2_no_shared_state_pass` — no module-level mutable writes
- `test_signal2_shared_mutable_fails` — unit A writes `_cache = {}`, unit B reads `_cache`
- `test_signal2_decorator_registration_fails` — `@registry.register` mutates shared object
- `test_signal2_os_environ_mutation_fails` — `os.environ["X"] = "v"` at module scope
- `test_signal3_disjoint_keys_pass` — different config keys
- `test_signal3_shared_key_fails` — both reference `config["providers"]`
- `test_signal3_dynamic_key_fails` — `config[var]` → FAIL
- `test_signal4_disjoint_tests_pass` — separate test files, no cross-imports
- `test_signal4_cross_import_fails` — unit A's test imports from unit B's source
- `test_signal4_autouse_conftest_fails` — autouse fixture covers both
- `test_signal4_no_test_file_fails` — unit has no test → FAIL (conservative)
- `test_certificate_all_signals_must_pass` — 3 pass + 1 fail → proven=False
- `test_claimable_merge_after_without_cert_serializes` — no cert → treated as depends_on
- `test_claimable_merge_after_with_cert_allows_concurrent` — positive cert → concurrent
- `test_claimable_merge_after_with_overlapping_owns_still_serializes` — M-owns still gates

## Acceptance
- All existing tests pass (874+)
- New `test_semantic_proof.py` tests pass (20+ tests)
- Gate GREEN: ruff, mypy, boundary, version, gate-registry
- F1 invariant preserved: no `merge_after` without certificate → treated as `depends_on`

## CONSTRAINTS
- Stdlib-only (`ast`, `json`, `pathlib`, `hashlib`) — no external deps per ADR-0010 D2.
- Product-clean (no SLOP/fleet/tracking.db).
- `engine/` boundary: gateway never imports from `engine.*`.
- ALL signal computations are deterministic pure functions of source files + config files.
  No LLM, no clock, no RNG, no network.
- WCI-6 (auto-slice) is OUT OF SCOPE. Do not build it.
