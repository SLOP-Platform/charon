repo: charon
tier: frontier
difficulty: 4
work_class: greenfield-feature
branch: feat/decompose-model-wiring
serial_justified: Cohesive ~30-line env-wiring diff (DECOMPOSE-WIRING-PLAN.md §3) — planner+recommend share the CHARON_DECOMPOSE_*_MODEL naming contract; splitting adds contract-coupling/contention risk with zero wall-clock gain (decompose_surface.py is in owns for sequencing only, untouched by the diff).
depends_on: WORK-DECOMPOSER
owns: src/charon/decompose_planner.py, src/charon/decompose_surface.py, src/charon/recommend.py, tests/test_decompose_planner.py, tests/test_recommend.py, tests/test_decompose_surface.py
note: |
  This IS a chunk of WORK-DECOMPOSER (which already owns decompose_planner.py /
  decompose_surface.py via its DEC-PLANNER/DEC-AST-WRAP chunks) — the PLANNER/WORKER
  env-wiring piece specifically. Sequenced (depends_on: WORK-DECOMPOSER) so it lands
  on top of that engine's in-flight chunks, not concurrently against the same files.
  Full root-cause diff (file:line, exact code to paste) is at
  fleet/state/DECOMPOSE-WIRING-PLAN.md — READ IT FIRST, do not re-derive the diff.
accept: |
  ## Task (see DECOMPOSE-WIRING-PLAN.md §3 for the exact diff — apply it, don't redesign)
  1. `src/charon/decompose_planner.py` `_select_planner_model` (currently at line ~380):
     add `CHARON_DECOMPOSE_PLANNER_MODEL` env override (checked first, must match a
     trusted+non-detained model); if unset, prefer a trusted model whose id is in
     `config.tiers.tier_members("high")`; fall through to today's first-trusted-model
     behavior unchanged. ~15-line diff, no signature/caller change (plan §3.A has the
     literal function body to paste).
  2. `src/charon/recommend.py` `recommend_tiers` (currently consumes `trusted =
     _find_trusted_models(config_dir)` at line ~182): add `CHARON_DECOMPOSE_WORKER_MODEL`
     env override; sort `trusted` so a pinned/tier-"high" match comes first before
     `trusted[:3]` is taken (plan §3.B has the literal sort-key block to paste).
  3. `decompose_planner.py` needs a top-level `import os` added (stdlib-only imports,
     matches its existing convention); `recommend.py` already imports `os`.
  4. Confirm naming has no collision with `CHARON_REVIEW_MODEL` (that's the
     outcome-reviewer's env var, a different role — plan §5 flags this, just confirm
     it stays distinct, no code change needed there).

  ## Accept (all must pass)
  - New unit test (add to `tests/test_decompose_planner.py`): set
    `CHARON_DECOMPOSE_PLANNER_MODEL` env var to a model placed SECOND in a mocked
    `recommend._find_trusted_models` return list, call `_select_planner_model`, assert
    it returns the pinned model (not the first-in-list one) — proves the override
    actually reorders selection rather than passing by luck. Plan §4 has a runnable
    version of this exact test.
  - Mirror test in `tests/test_recommend.py` for `CHARON_DECOMPOSE_WORKER_MODEL`:
    patch `_ask_model`, assert the pinned/tier-"high" model is queried FIRST even when
    it is not first in the raw trusted list.
  - Fail-on-revert: strip the pinned/tier-lookup block from either function → its new
    test goes RED (selection reverts to plain first-in-list order).
  - `PYTHONPATH=src python3 -m pytest tests/test_decompose_planner.py
    tests/test_recommend.py tests/test_decompose_surface.py -q` → full green.
  - `PYTHONPATH=src python3 -m charon.cli gate` → GREEN (no regression to the existing
    gate suite).

  ## Dependencies & sequence
  depends_on: WORK-DECOMPOSER (owns overlap on decompose_planner.py/decompose_surface.py
  — this ticket is WORK-DECOMPOSER's env-wiring chunk, must land on top of its
  DEC-PLANNER/DEC-AST-WRAP chunks, not concurrently). Disjoint from FAIL-LOUD-CONTRACT
  and the forwarder.py collision (DECOMPOSE-MODEL-WIRING never touches forwarder.py —
  plan §5 confirms neither function is in the proxy_server.py per-request forwarding
  hot path). Single wave, lands after WORK-DECOMPOSER's current chunks merge.
