# SESSION — SR-6 FIX: make auto-derived `cost_rank` actually fire

**Model:** deepseek-v4-pro (operator-selected; this is a correctness + refactor task on the routing/cost path)
**Repo:** charon  ·  **Ticket:** SR-6 (redo — prior glm-5.2 build was BLOCKED in review)
**Base branch/worktree:** `feat/sr6-auto-cost-rank` at `/home/stack/code/charon-sr6` (the ticket's existing isolated worktree — do NOT work in the shared main tree `/home/stack/code/charon`)

## FIRST ACTS (mandatory — worktree isolation + bridge coordination)
1. `cd /home/stack/code/charon-sr6`
2. `git fetch origin && git merge origin/master` — rebase your base onto current master (now `2b443aa`, includes #5 request-normalizer). Resolve any conflict; re-run tests after.
3. Register on the session-bridge: `register` with `session_id` (your choice), `repo: "charon"`, `ticket: "SR-6"`, `status: "in-progress"`. Heartbeat (`update`) periodically.
4. Read the full failure analysis: `/home/stack/charon-private/fleet/reviews/REVIEW-06-sr6-auto-cost-rank.md`.

## THE DEFECT (verified in adversarial review — this is why it's a redo)
The headline feature — *auto-derive `cost_rank` from real per-token pricing* — is **inert in production.** Root cause:
- `config.add_model` / `add_models_bulk` **always stamp an explicit `cost_rank` (default `1000`)** on every model.
- `_derived_cost_rank` treats **any present `cost_rank`** as an operator override and short-circuits — so the pricing derivation **never runs for any real model** loaded via the models.json path.
- The 7 existing tests pass **only because they use raw-TOML inputs that omit `cost_rank`**; none exercise the `add_model`/`add_models_bulk` (models.json) path, which masked the gap. Empirically, a dear-first pool stays dear-first.
- `cost_class` premium-gating DOES work and there is no live-routing regression (everything currently ties at 1000, NanoGPT anchor safe) — but the feature is **ineffective, not merely unfinished.**

## REQUIRED FIX
1. Make derivation actually fire for models loaded via `add_model`/`add_models_bulk`. The core problem is that a **default-stamped** `cost_rank` is indistinguishable from an **operator-explicit** one. Fix that distinction — e.g. do NOT stamp a default `cost_rank` (leave it absent/`None` so `_derived_cost_rank` computes it from `cost_input`/`cost_output`), OR carry an explicit "operator set this" marker and only short-circuit on that. Preserve genuine operator overrides.
2. Derivation must handle missing pricing gracefully (no crash; fall back to a defined default, don't silently mis-rank).
3. Keep `cost_class` (free-daily / expiring / prepaid / metered) gating intact.

## REQUIRED PROOF (this is non-negotiable — the prior failure was tests dodging the real path)
- Add a test that goes **through `add_model`/`add_models_bulk`** (the models.json path) with real `cost_input`/`cost_output` values and asserts that a pool listed **dear-first is reordered cheap-first** by the derived `cost_rank`. A green suite that only exercises raw TOML will be REJECTED again.
- Add/keep a test that a genuine operator-set `cost_rank` override is still honored (not overwritten by derivation).
- Keep the existing `cost_class` tests.

## GATE (both, from the worktree; must be green)
- `PYTHONPATH=src python3 -m charon.cli gate`  (ruff/mypy/SLOP-boundary/version/gate-registry)
- `PYTHONPATH=src python3 -m pytest -q`

## BOUNDARY / D&S
- Product ships standalone: **no** `/home/stack`, fleet, SLOP, or runner references in `src/` or committed config.
- Depends on: #5 (merged) + SR-5b pricing (already on master). Touches `config.py` + the cost_rank/cost_class logic; other in-flight branches (SR-1/SR-2/SR-10) touch different files — but `git diff` to confirm no collision before finishing.
- **Do NOT push to master and do NOT merge.** Commit on `feat/sr6-auto-cost-rank`, then report back to the manager with a 3-5 line summary (what changed + the new test names + gate result). The manager re-reviews adversarially and merges via the sanctioned push path.

## REPORT BACK (short — do not paste diffs)
Verdict-ready summary: files changed, the models.json-path test name, `dear-first → cheap-first` proof result, gate pass/fail.
