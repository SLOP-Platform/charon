# REVIEW-06b — SR-6 DeepSeek-v4-pro REDO (re-review)

- Branch: `feat/sr6-auto-cost-rank`  worktree `/home/stack/code/charon-sr6`
- HEAD (committed): `104db71` — "Merge remote-tracking branch 'origin/master' into feat/sr6-auto-cost-rank"
- `origin/master` = `2b443aa` — **merged in** (confirmed ancestor of HEAD).
- Reviewer: adversarial (read-only). Date: 2026-07-05.

## VERDICT: **BLOCK**

The **committed branch is STILL INERT** — the exact SR-6 defect the ticket must
close is unfixed in every commit. A correct fix exists **only in the
UNCOMMITTED working tree**. Merging HEAD as-is ships the same inert feature the
glm-5.2 attempt did, with a green suite that dodges the real path.

---

## THE DECIDER — empirical INERT test (committed HEAD, clean `git archive`)

Ran a throwaway repro against a **clean checkout of committed HEAD** (`git
archive HEAD | tar -x`), driving the ACTUAL `config.add_model` path with real
per-token pricing and NO `cost_rank` argument, then loading a deliberately
**dear-first** pool via `gateway.load_config`:

```
COMMITTED-HEAD persisted models.json:
  dear:  cost_rank=1000  cost_input=1.5e-05
  cheap: cost_rank=1000  cost_input=1e-06
POOL order (dear-first input): ['https://dear.example/v1', 'https://cheap.example/v1']
REORDERED cheap-first? False        >>> INERT (NOT reordered) <<<
```

**INERT? → YES.** The dear-first pool is NOT reordered. Both models get
`cost_rank=1000` stamped, so `_derived_cost_rank` treats it as an operator
override and pricing derivation NEVER fires — identical to the original defect.

### Root cause in the COMMITTED source

`git show HEAD:src/charon/config.py`:

```python
def add_model(..., free: bool = False, cost_rank: int = 1000, ...):
    ...
    entry: dict = {"free": bool(free), "cost_rank": int(cost_rank)}   # STAMPS 1000 unconditionally
```

`add_models_bulk` (committed):

```python
"cost_rank": int(e.get("cost_rank", 0 if free else 1000)),          # STAMPS 1000/0 unconditionally
```

`gateway._derived_cost_rank` (committed, nested):

```python
explicit = spec.get("cost_rank")
if explicit is not None:
    return int(explicit)        # 1000 is "present" → derivation short-circuited
```

Combined: every models.json-path model carries an explicit `cost_rank=1000`, so
the derived-from-pricing branch is dead code on the real path.

---

## WHY THE EARLIER GREEN WAS A FALSE POSITIVE (critical)

The worktree is **DIRTY**. `git status --short`:

```
 M src/charon/cli.py
 M src/charon/config.py
 M src/charon/gateway.py
 M src/charon/pools.py
 M src/charon/proxy_server.py
 M tests/test_gateway.py
 M tests/test_models_import.py
```

`PYTHONPATH=src` reads the **working tree**, not HEAD. The gate (green) and
`pytest -q` (1206 passed) I first ran, and the first inert-repro that showed
"REORDERED cheap-first? True", all executed the **uncommitted** code. The
uncommitted working tree DOES contain the real fix: `add_model` signature
becomes `cost_rank: int | None = None` with conditional stamping, and
`derived_cost_rank` is extracted to `pools.py`. That fix is correct and
complete — but **none of it is committed**, so it is not what a merge lands.

**Verify-the-branch, not the self-report** was decisive here: the self-report /
worktree gate is green; the committed branch is inert.

---

## NEW-TEST ANALYSIS (item 3)

- Do the new tests **fail on buggy (pre-fix) code?** The TOML-path derivation
  tests (`test_sr6_derived_rank_orders_by_blended_cost`, `..._premium_class_gated_out`)
  WOULD fail against master's `_rank` (no derivation) — good in isolation.
- BUT they **PASS on the committed-inert branch**: run against the clean HEAD
  checkout, `pytest -k sr6` = **7 passed** while the feature is INERT. The tests
  drive `gateway.load_config(toml_path=...)`, where models never pass through
  `add_model` and so never receive the `cost_rank=1000` stamp. **No test
  exercises the `add_model`/`add_models_bulk` → `load_config` pipeline for
  cost_rank derivation.** The two add_model/bulk tests only assert `cost_class`
  normalization, never the cost_rank-stamping defect.
- **Net: the suite DODGES the real path** — the same failure mode as glm-5.2.
  A green suite over an inert feature. Does the new test fail on buggy code on
  the path that matters (models.json)? **NO.**

---

## Items 4–5 (evaluated; moot given INERT but recorded)

- Operator-explicit `cost_rank` override: honored in the working-tree fix
  (rank 9999 + cheap pricing → sorts LAST, verified). On committed branch this
  is trivially "honored" only because EVERYTHING is 1000.
- Missing pricing: working-tree fix → neutral 1000, no crash, correct interleave
  (cheap < unpriced < dear), verified. No crash path observed.
- Gate: working tree `charon gate` = all checks pass; `pytest -q` = **1206
  passed**; no version-gate false positive this run. **These greens are on the
  DIRTY tree, not HEAD** — do not treat as branch validation.
- Blast radius: `SLOP-boundary` gate OK — no `/home/stack`/fleet leaks in
  committed source. Removing the default stamp (working-tree fix) is safe:
  `_derived_cost_rank` falls back to 1000 when pricing absent, preserving the
  historical neutral rank for un-priced models.

---

## REQUIRED TO CLEAR (for the redo)

1. **COMMIT the working-tree fix** (config.py conditional stamping + pools.py
   `derived_cost_rank` extraction + the cli/proxy_server/test changes). The
   branch cannot merge with the fix uncommitted.
2. Add a regression test that closes the dodge: use `config.add_model` /
   `add_models_bulk` (NO cost_rank) to persist priced models, then
   `load_config(state_dir=...)` and assert a dear-first pool is reordered
   cheap-first AND assert `"cost_rank" not in persisted_model`. This test MUST
   fail on the current committed HEAD.
3. Re-run gate + pytest **against a clean checkout of the new HEAD** (or after
   `git stash`-clean), not the working tree.

---

## One-line bottom line

The fix is written but **never committed**; the committed branch reproduces the
original SR-6 defect and the new tests pass over it — **BLOCK** until the
working-tree changes are committed and guarded by an add_model-path regression
test.
