# DeepSeek build session — TIER-SELECT Phase-A only (catalog + CLI picker)

You are a Charon build session (DeepSeek V4 Pro). Repo: `/home/stack/code/charon`. Implement
**TIER-SELECT Phase-A ONLY** — the curated model catalog module + the CLI picker. Leave the web
`/charon/setup` edit (Phase-B) for a later session.

**This session runs in PARALLEL with the SR-7/SR-5b/SR-8 chain session — that is SAFE:** Phase-A does
NOT touch `src/charon/proxy_server.py` (or `gateway.py`), so there is no shared-file collision with
that chain.

## 1. Ground yourself first (read these)
- `/home/stack/code/charon/AGENTS.md` — standing orders (mandatory)
- `/home/stack/charon-private/fleet/WORKFLOW.md` — claim / build / gate / commit process

## 2. The ticket — read it, then build only the Phase-A half
- board: `/home/stack/charon-private/fleet/board/TIER-SELECT.md`
- prompt: `/home/stack/charon-private/prompts/tier-select.md` — read the whole thing, but the prompt's
  **"Optional phasing"** note defines your split: Phase-A = catalog module + CLI picker.
- Curated source of the catalog data: `/home/stack/charon-private/fleet/MODEL-ROLE-EVALUATION.md`
  §4 + §4a. Distil the FACTS only (id + tier hint + access note) into product-clean data — carry NO
  fleet/SLOP/rig references into `src/`.

## 3. Scope — Phase-A ONLY
- branch: `feat/tier-select-catalog-a` (off latest `master`; `depends_on:` is EMPTY for Phase-A —
  it does NOT wait on SR-8).
- **owns (Phase-A):** `src/charon/model_catalog.py` (NEW), `src/charon/cli.py`,
  `tests/test_model_catalog.py` (NEW).
- **DO build:**
  1. `src/charon/model_catalog.py` — stdlib DATA module, provider-agnostic (no
     `if provider == "…"` logic). Entries `{id, tier_hint (low|med|high), access, note}`. Provide
     `catalog()` and `catalog_for_tier(tier)` (folds tier_hint via `config.resolve_tier`). Small,
     append-only.
  2. CLI picker in `src/charon/cli.py` that REUSES `config.set_tiers` (do NOT reimplement
     persistence): `charon tier catalog [--tier …]` to print curated options grouped by tier hint;
     extend assignment so a user picks FROM the catalog (`tier set high --from-catalog id1,id2`
     validates ids are in the catalog) and/or an interactive `tier pick`. A custom / off-catalog id
     must still be assignable (pick-from-catalog OR enter-your-own — permissive, advisory validation,
     never a hard-fence); reuse `config.add_model` for registering an unknown id.
- **DO NOT touch (Phase-B, later session):** `src/charon/proxy_server.py`, `src/charon/gateway.py`,
  `tests/test_tier_select.py`, the web `/charon/setup` picker. Also do NOT edit `config.py` — reuse
  its existing tier APIs.
- If you need a file outside the Phase-A owns, **STOP and flag it** — do not create/edit it.

## 4. Tests (Phase-A)
`tests/test_model_catalog.py` (hermetic — tmp config dir, no network):
- `catalog()` non-empty; every entry has `id`, a `tier_hint` in `{low,med,high}` (post-resolve),
  `access`, `note`; ids unique; module imports stdlib-only (assert no third-party import).
- CLI: `charon tier catalog --tier strong` lists strong-tier options; `set … --from-catalog <ids>`
  (or `pick`) writes those ids into the tier's `members` in `tiers.json` and `tier list` shows them;
  a non-catalog id via `--from-catalog` is rejected with a clear error; a custom id via the
  enter-your-own path still persists (advisory warning, no hard failure).

## 5. Rules — non-negotiable
- Before committing, the FULL gate + tests must be green:
  ```
  python3 -m charon.cli gate && PYTHONPATH=src python3 -m pytest -q
  ```
  (Use `python3 -m charon.cli gate` — NOT bare `mypy src/charon`; the CLI gate runs
  ruff/mypy/boundary/version/gate-registry, and pytest is the separate test pass. `mypy src/charon`
  alone misses tests and reddens CI.)
- Provider/agent-agnostic + product-clean: catalog is DATA, zero vendor branching in logic, zero
  fleet/SLOP/rig strings in `src/`. Stdlib-only core (no new deps).
- Commit with a conventional message (e.g. `feat(TIER-SELECT): Phase-A catalog + CLI picker`).
- **Do NOT push and do NOT open a PR.** Stop after committing — a Claude reviewer + the operator gate
  the merge.

When committed, report the branch name + final `pytest` counts, then stop.
