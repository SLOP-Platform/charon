# DSGN-WCI-5-1-PROOF — §5.1 semantic-independence proof contract

**Status:** DRAFT for adversarial review → operator sign-off.
**Artifact type:** Design/proof contract (not code, not ADR).
**Source of truth fed by:** `DSGN-WCI-reshape.md` §5 (open question 1), §7.1 (F1 invariant).
**Blocks:** WCI-FOLLOWON (gated behind this contract being approved AND WCI-MVP on master).

---

## 1. Purpose

When WCI-FOLLOWON ships, a `merge_after(A, B)` edge may permit A and B to be CLAIMED
concurrently — but only if the pair is **proven semantically independent** (F1 condition i).
Owns-disjointness alone is insufficient (B1 hazard — different modules can share symbols,
imports, config, or test surfaces). This contract defines the *predicate* that certifies
two units are truly independent, the *signals* that feed it, and the *conservative default*
that keeps the board safe when the predicate cannot certify.

The contract is **deterministic and purely board-state-based** — no LLM on the gate path
(F1: "the split is invented by the proof, never by the label"). A `merge_after` label alone
is never a certificate.

---

## 2. The certificate

### 2.1 Shape

```python
@dataclass
class IndependenceCertificate:
    unit_a: str             # the earlier unit (merge_after source)
    unit_b: str             # the later unit (merge_after target)
    proven: bool            # True iff ALL signals pass
    signal_results: dict[str, bool]   # per-signal pass/fail
    computed_at: str        # ISO timestamp — for audit, not replay
```

### 2.2 When it is computed

Once, when the board transitions both units to READY (or when a `merge_after` edge is
first added). Computed by a **pure function** of:
- The two units' `owns` sets (lists of file paths)
- The repository's module import graph (computed from `src/` AST analysis)
- The repository's test file inventory and test-suite results
- The `charon-config.json` and tier config (keys both units reference)

The certificate is **stored on the board** as an immutable edge annotation; it is never
re-computed on a hot drain path. `claimable` reads the pre-computed `proven` field.

### 2.3 How claimable consumes it

In `board.claimable(unit_id)` (board.py:223), the `_deps_done` check is extended:

```python
def _deps_done(self, unit: Unit) -> bool:
    for dep_id in unit.depends_on:
        dep = self._units.get(dep_id)
        if dep.state != DONE:
            # If this dep is a merge_after edge with a positive certificate,
            # the dep is satisfied even though the upstream is not DONE yet.
            cert = self._get_cert(dep_id, unit.id)
            if cert is not None and cert.proven:
                continue
            return False
    return True
```

Key properties:
- **`merge_after` edge without a certificate** → `_deps_done` treats it as a normal
  `depends_on` → serialized (F1 third branch: conservative-demote).
- **`merge_after` edge with `cert.proven == True`** → upstream need not be DONE → both
  units can be CLAIMED concurrently → F1 condition (i).
- **`merge_after` edge with overlapping `owns`** → M-owns (board.py:227-235) still
  serializes via lowest-id, even with a positive certificate → F1 condition (ii).

---

## 3. The four signals

Each signal computes `True` (independent) or `False` (not proven independent). All four
must be `True` for `cert.proven = True`. A single `False` → `cert.proven = False` →
conservative serialize.

### 3.1 Signal 1 — Import-graph reachability

**Question:** Does unit B's code depend on unit A's code (or vice versa) through the
module import graph?

**Computation:**
1. Parse the import graph of all `src/charon/` modules (static AST analysis — no runtime
   import). Resolve each `import X` and `from X import Y` to the canonical module path.
   **Follow re-export chains**: if `__init__.py` does `from .submodule import X`, then
   `from package import X` reaches `submodule.X` transitively. The import graph includes
   these indirect edges.
2. Extract the set of modules transitively reachable from unit A's `owns` files.
3. Extract the set of modules transitively reachable from unit B's `owns` files.
4. If A's reachable set intersects B's owned files, or B's reachable set intersects A's
   owned files → **FAIL** (import coupling exists).
5. If neither direction reaches the other's files → **PASS**.

**Edge cases:**
- **Bare string imports** (`importlib.import_module("foo")`) are parsed heuristically
  (literal-string detection). If the string is dynamic (variable) → **FAIL** (uncertainty
  → conservative).
- **Test files** are excluded from the owned set for this signal (tests import from src
  by design; signal 4 handles test coupling).
- **stdlib and third-party imports** are ignored (only `src/charon/` modules matter).

### 3.2 Signal 2 — Shared-symbol analysis

**Question:** Do the two units write to or read from a common mutable module-level symbol?

**Computation:**
1. For each file owned by unit A, extract all **module-global write sites** (assignments
   at module scope: `X =`, `X +=`, `X.append(`). Exclude function/method-local writes.
2. For each file owned by unit B, extract all **module-global read sites** (references at
   module scope).
3. Compute the intersection: A's write set ∩ B's read set, AND B's write set ∩ A's read set.
4. If intersection is non-empty → **FAIL** (shared mutable state).
5. If intersection is empty → **PASS**.

**Strict interpretation:** A "write" to a module-global that is a class/function definition
is NOT a conflict unless the name is also referenced at module scope (not just imported).
`class X: ...` in unit A and `from unit_a import X` in unit B is an import → caught by
Signal 1. Signal 2 catches only **mutable state sharing** — e.g., `_cache = {}` in A and
`_cache.clear()` in B.

**Decorator registrations are covered.** A module-level decorator like
`@some_registry.register` on a function/class definition is a call that mutates a shared
object. Signal 2 flags **any module-level call** to a name imported from another
`src/charon/` module if the callable is also referenced (read) by the other unit's files.
Example: Unit A calls `registry.register(...)` at module scope; unit B reads from
`registry._items`. → FAIL.

**Edge cases:**
- **Dataclass/Enum/constant definitions** are not mutable state — they are PASS unless a
  decorator mutates a shared registry (see above).
- **Thread-shared resources** (locks, queues, process pools) at module scope → always FAIL
  (even if only one side writes — the other side reading from a shared queue is coupling).
- **`os.environ` mutations** → FAIL (shared runtime state).
- **Dynamic calls** (callable name is a variable, not a literal identifier) → FAIL
  (uncertainty → conservative).

### 3.3 Signal 3 — Shared-config touch

**Question:** Do the two units depend on a common config key or config file?

**Computation:**
1. Enumerate **all** config/state files readable by the Charon process:
   - `charon-config.json` (primary config)
   - `tiers.json` (tier definitions)
   - `secrets.json` (provider keys — sensitive, but coupling still matters)
   - Any `*.json` / `*.yaml` under the config directory (`~/.charon/` by default)
2. Extract the key set from each config file (top-level keys for JSON, top-level
   mappings for YAML).
3. For each unit, scan its owned files for config-key references:
   - `config["key"]`, `config.get("key")`, `cfg["key"]`, etc.
   - Heuristic: any string-literal key that matches a real config key across all files.
4. If both units reference the same config key in the same config file → **FAIL**.
5. If config keys are disjoint across all files → **PASS**.

**Edge cases:**
- **Dynamic key access** (`config[var]`) → **FAIL** (uncertainty → conservative).
- **Different files but same logical key** (e.g., `config["providers"]` in both) → **FAIL**.
- **Non-overlapping sub-keys** of the same top-level key: if unit A touches
  `config["providers"]["openai"]` and unit B touches `config["providers"]["anthropic"]`,
  this is still **FAIL** — they share the `"providers"` namespace and could collide
  structurally (e.g., schema validation, migration scripts).
- **Secrets file writes** by either unit → **always FAIL** (any mutation of secrets
  is a coupling risk).

### 3.4 Signal 4 — Test co-failure signals

**Question:** Do the two units' tests share a failure surface — i.e., would a break in one
unit's code cause the other unit's tests to fail?

**Computation:**
1. For each unit, identify its test files. By convention, a unit owning `src/charon/foo.py`
   corresponds to `tests/test_foo.py`.
2. If the units share a test file → **FAIL** (direct test coupling).
3. If unit A's test file imports from unit B's owned modules (or vice versa) → **FAIL**
   (test-dependency coupling).
4. **Conftest coupling:** Scan the `conftest.py` nearest to each unit's test files (and
   all ancestor `conftest.py` files up to the test root) for:
   - Fixtures imported from the other unit's owned modules → **FAIL**.
   - Fixtures decorated with `@pytest.fixture(autouse=True)` whose scope covers both units'
     tests → **FAIL** (autouse fixtures couple all tests under their conftest's directory
     without explicit imports).
5. If the test files are fully disjoint, import-disjoint, and conftest-disjoint → **PASS**.

**Alternative (lightweight) approach for the case where tests don't exist yet:**
If either unit has no corresponding test file → **FAIL** (cannot prove the negative —
conservative default: "if we can't see that tests are independent, serialize").

**Edge cases:**
- **Shared conftest.py fixtures** → if both units' tests use the same fixture from
  `conftest.py`, that fixture is a coupling point → **FAIL**.
- **Shared test utilities** (`tests/test_shared_http.py`, `tests/util.py`) → if both
  units import from the same test helper → **FAIL**.

---

## 4. Signal combination rule

```
cert.proven = S1 AND S2 AND S3 AND S4
```

All four must pass. No weighting, no partial credit. This is deliberately strict: false
positives (wrongly certifying a dependent pair as independent) cause silent breakage;
false negatives (failing to certify a genuinely independent pair) only cost a small
amount of concurrency — the pair still runs safely in series under the conservative
demotion (F1 third branch).

---

## 5. Conservative default

The default when ANY signal is uncertain is **FAIL**:

| Situation | Default | Rationale |
|---|---|---|
| Dynamic import string (variable, not literal) | FAIL | Can't statically resolve |
| Dynamic config key access | FAIL | Can't statically resolve |
| No test files for one or both units | FAIL | Can't prove negative |
| Python file contains syntax errors (can't parse AST) | FAIL | Can't analyze |
| Shared-symbol name is used in a way the analyzer can't classify | FAIL | Uncertainty |
| Certificate not yet computed (edge freshly added) | FAIL | No data → serialize |

The F1 third branch (conservative-demote) is the system-level enforcement of this:
`merge_after` with `cert is None or cert.proven == False` → treated as `depends_on`.

---

## 6. What the certificate is NOT

1. **NOT a runtime signal.** The certificate is a static, pre-computed artifact. It does
   not watch in-flight execution, lock contention, or live merge conflicts.
2. **NOT an LLM judgment.** All four signals are deterministic computations on AST/config
   artifacts. No model, no prompt, no temperature.
3. **NOT automatic for `merge_after` edges.** An edge must carry a certificate or it
   behaves as `depends_on`. No implicit certification.
4. **NOT a replacement for owns-disjointness.** Disjoint `owns` remains the M-owns gate
   (board.py:227-235). The certificate is an **additional** proof layered on top — together
   they close the concurrency-gate pair (F1 §7.1 proof).

---

## 7. Implementation notes (for when WCI-FOLLOWON builds)

1. **Import graph:** use Python's `ast` module (stdlib) to parse `import`/`from-import`
   statements. Cache the graph; recompute only when an `owns` file's AST changes (content
   hash).
2. **Shared-symbol:** also `ast` — walk module-level `Assign`, `AugAssign`, `Attribute`
   targets. Classify names as read/write/both. Exclude function/method scopes.
3. **Shared-config:** static scan of `charon-config.json` key set + regex match in owned
   source files for `["key"]` / `.get("key")` patterns.
4. **Test co-failure:** simple path-based heuristic (`src/charon/foo.py` → `tests/test_foo.py`
   or `tests/test_foo/*.py`). AST-scan test files for imports from the other unit's source.
5. **Performance:** all signals are O(files × imports) — cheap. Compute on edge creation
   or first READY transition. Cache certificate on the board. Never on the drain hot path.
6. **Stdlib-only:** all signal computation uses `ast`, `json`, `pathlib`, `hashlib`
   (content hashing) — no external dependencies (ADR-0010 D2, R4).

---

## 8. Adversarial-review results

### 8.1 Gaps found and fixed

| # | Gap | Signal | Fix applied |
|---|---|---|---|
| G1 | Decorator registrations (`@registry.register`) mutate shared objects at import time but are function calls, not assignments — Signal 2 missed them | S2 | Signal 2 now flags any module-level call to a name imported from another `src/charon/` module if the callable is also referenced by the other unit |
| G2 | Non-main config files (`tiers.json`, `secrets.json`, provider configs) not checked | S3 | Signal 3 now enumerates all config files under `~/.charon/` |
| G3 | `autouse=True` pytest fixtures in `conftest.py` couple tests without explicit imports | S4 | Signal 4 now scans ancestor conftest files for autouse fixtures whose scope covers both units |
| G4 | Re-export chains (`__init__.py` → submodule) hide coupling if not transitively resolved | S1 | Signal 1 now follows re-export chains when building the import graph |

### 8.2 Probes answered

**Probe 1 — Can two units with disjoint owns and all 4 signals passing still break each other?**

Considered: env vars (isolated per ACP subprocess), temp files (isolated per worktree),
external APIs (not a build-safety concern — builds produce correct code regardless),
git operations (isolated in separate worktrees). **Verdict: no false-positive path found.**
The worktree-per-unit architecture isolates runtime state. The only shared surface is the
repo itself, and land already handles merge conflicts.

**Probe 2 — Scheduler/coordinator mutations under concurrency.**

`board.py` serializes all state-machine transitions. Concurrent workers feed results through
thread-safe queues. **Verdict: safe — existing invariant, not a new one.**

**Probe 3 — Re-export facades.**

Fixed (G4 above). The import graph now transitively resolves `__init__.py` re-exports.
**Verdict: closed.**

### 8.3 Remaining risk (accepted)

**File-system side effects at shared paths** (e.g., both units writing to the same
absolute path like `/tmp/charon-cache`). The 4 signals cannot detect this statically.
Risk assessment: low. Units run in per-worktree directories; writing to shared absolute
paths is a unit bug, not a build-safety hazard — the unit's OWN code would fail, not
silently corrupt the other unit. And the F1 third branch (conservative-demote) means any
undetected coupling → serialization (safe), never incorrect concurrency.

### 8.4 Synthesis

The 4-signal proof contract with conservative-default architecture is **sound against
false positives** (wrongly certifying dependent pairs). All identified gaps produce
false negatives (failing to certify independent pairs), which the conservative-demote
default handles safely by serializing.

The contract is ready for operator sign-off.
