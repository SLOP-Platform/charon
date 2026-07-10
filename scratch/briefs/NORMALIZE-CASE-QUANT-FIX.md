# SESSION — NORMALIZE-CASE-QUANT-FIX: case/quant-insensitive model-id normalization (kill false downgrades)

**Model:** opus (frontier) — money-path classify/scoring correctness; do NOT economize.
**Repo:** charon · **Ticket:** NORMALIZE-CASE-QUANT-FIX
**Base branch/worktree:** `fix/normalize-case-quant` at `/home/stack/code/charon-fleet-NORMALIZE-CASE-QUANT-FIX`
(an isolated worktree off latest `origin/master` — do NOT work in the shared main tree
`/home/stack/code/charon`).

## FIRST ACTS (mandatory)
1. `cd` into the worktree (create it off latest `origin/master` if absent).
2. `git fetch origin && git merge origin/master`; resolve conflicts; re-run tests after.
3. Register on the session-bridge (`register`: your `session_id`, `repo: "charon"`,
   `ticket: "NORMALIZE-CASE-QUANT-FIX"`, `status: "in-progress"`); heartbeat via `update`.
4. Read `scratch/provider-cost-rationalization.md` (Fix 2 normalize evidence) first.

## FILES OWNED (touch only these)
- `src/charon/proxy.py`
- `tests/test_normalize_model_id.py` *(new — deliberately NOT `tests/test_proxy_downgrade.py`,
  which SR-1 owns; avoids a test-file collision)*
- `tools/check_catalog_case_quant.py` *(new detector; relates #30)*

## THE TASK (what's broken)
`_normalize_model_id` (`proxy.py:247`, currently `model_id.rsplit("/",1)[-1]`) is
case-sensitive and keeps quant suffixes. A provider that echoes `Kimi-K2.7-Code` (vs pool
`kimi-k2.7-code`) or `GLM-5.2-FP8` (vs `glm-5.2`) is false-flagged `pseudo_success` → recorded
as a quality FAILURE (`forwarder.py:312`) and served with a spurious `X-Charon-Downgrade`. This
is why NeuralWatt scores 0/4 while actually working.

## REQUIRED CHANGE
1. Make normalization **case-insensitive** AND **quant-suffix aware** (strip `-FP8`, `-FP16`,
   `-BF16`, `-Q4…`, `-INT8`, etc.) on BOTH the expected and returned id before comparison —
   WITHOUT breaking the SR-1 namespaced-id fix (still compare the FINAL path segment via the
   existing rsplit-on-`/`). Do this in `_normalize_model_id` at `proxy.py:247`.
2. Add a small detector `tools/check_catalog_case_quant.py` that flags catalog/live model-id
   case+quant mismatches, and wire it into `gates.json` / `charon.cli gate` (mechanizes the #30
   catalog-mismatch directive).

## ACCEPTANCE CRITERIA
- Per-ticket: `PYTHONPATH=src python3 -m pytest tests/test_normalize_model_id.py -q` green.
- **FAIL-ON-REVERT test (required):** `test_quant_case_variant_is_not_downgrade` — feed
  `classify()` expected `kimi-k2.7-code` / `glm-5.2` against returned `Kimi-K2.7-Code` /
  `GLM-5.2-FP8`; assert `obs.pseudo_success is False` (a clean success, NO `X-Charon-Downgrade`
  header served to the client). RED today (case/quant mismatch → pseudo_success True), GREEN
  with the fix, RED again on revert — it asserts the client-observable downgrade outcome.
- The new detector runs under `charon.cli gate` and flags a seeded case/quant mismatch.

## MERGE GATE (not pytest-alone)
FULL CI from the worktree, ALL green before this is merge-eligible:
- `ruff` (lint)
- `mypy` (types)
- `PYTHONPATH=src python3 -m charon.cli gate`  (ruff/mypy/SLOP-boundary/version/gate-registry)
- `PYTHONPATH=src python3 -m pytest -q`
Money-path change (touches classify/downgrade path) → ADVERSARIAL review before merge. Product
ships STANDALONE: no `/home/stack`, fleet, SLOP, or runner references in `src/` or committed
config.

## Dependencies & sequence
- **depends_on:** *(empty)* — Wave 1, launches immediately, parallel with the other two.
- **Concurrency safety:** owns `proxy.py` + two NEW files, disjoint from BILLING-EST-COST-FIX
  (forwarder.py) and TEST-HARDEN-CONTRACT (conftest/contract-test/lint). No shared Wave-1 file.
  New test file is deliberately NOT `test_proxy_downgrade.py` (SR-1's) to avoid collision.

## REPORT BACK (short — no diffs)
Files changed, test names, gate pass/fail, and the commit SHA.

## LAST STEP (REQUIRED) — commit, do not skip
```
git add -A && git commit -m "NORMALIZE-CASE-QUANT-FIX: case/quant-insensitive model-id compare + catalog mismatch detector"
```
Report the commit SHA back to the manager.

do NOT push, do NOT open a PR, do NOT merge — the launcher publishes; the deny-list blocks push inside the session.
