# PR completeness review — pile D (#86, #127, #130, #131, #135, #144)

Repo: SLOP-Platform/charon (product). Reviewed via `gh pr view/diff/checks` + job logs.

## PR #86 — ci: bump github-actions group (dependabot)
- Pure workflow SHA-pin bump (checkout, setup-python, docker/login,
  docker/build-push, attest-build-provenance, upload-artifact).
- **CI: gate FAILS.** `public-clean` check flags the new 40-char SHA pins
  as "hex token shape (>=40 chars)" false positives (`.github/workflows/
  ci.yml`, `heavy.yml`, `release.yml`, `windows-exe.yml` — 18 lines).
  This is a gate false-positive, not a real leak — SHA-pinned actions are
  standard supply-chain hygiene, not secrets. The gate's public-clean
  heuristic needs an allowlist for `uses: .../action@<40-hex>` lines (or
  dependabot PRs need a gate exemption) before this can ever go green.
- Verdict: **FLAG-INCOMPLETE** — blocked on a gate false-positive that
  needs a fix in the public-clean checker itself, not in this diff.

## PR #127 — perf(test): cut suite wall-clock ~16x
- Three real, well-documented changes: (1) autouse fixture in
  `tests/conftest.py` drops stdlib `socketserver` poll_interval 0.5s→0.05s
  (147s→42s), (2) `pytest-xdist` + `-n auto` in `ci.yml`/`release.yml`
  (→18s alone, ~9s combined), (3) DNS-timeout fix in
  `test_meter_model_provider.py` (`http://x` → `http://127.0.0.1:1`).
  Review-log documents measured before/after numbers and pass-count parity.
- **CI: gate PASSES**, wheel-smoke PASSES.
- Caveat: review-log explicitly surfaces 2 pre-existing red tests
  (`test_boundary.py::test_gateway_path_does_not_import_engine_transitively`,
  `test_routing_proxy.py::test_routing_proxy_cli_reports_port`) and defers
  them to "its own ticket" — this conflicts with the operator's standing
  doctrine ("pre-existing reds fixed on current branch, never a separate
  cleanup ticket" / "never ignore pre-existing issues"). Not blocking CI
  today (gate is green), but manager should decide whether to fold the fix
  into this PR or explicitly waive the doctrine here.
- Verdict: **LAND** (flag the pre-existing-red doctrine question to manager,
  not a completeness gap in the PR's own stated scope).

## PR #130 — feat(PROJECT-MEMBERSHIP-GATE): fold-into-Project gate
- Adds `fleet/validate_board.sh` (new check 5b) and `fleet/state/
  ROADMAP.tsv` (200 rows) **as new files inside the SLOP-Platform/charon
  PRODUCT repo**. Confirmed via `git ls-files | grep '^fleet/'` in this
  repo: **zero** fleet/ files currently tracked — `fleet/` belongs to the
  separate charon-private rig (`/home/stack/charon-private/fleet`), not
  the product.
- This is a direct hit on the standing boundary rule: "Charon PRODUCT
  ships standalone (no fleet/SLOP/runner); never let local build-infra
  leak into product." The PR's own review-log fragment even says the
  work's canonical home is `charon-private` (branch
  `feat/project-membership-gate`) and this is just a "PR-able mirror."
- **CI: gate FAILS** — `public-clean` catches real internal-info leakage
  that is a direct symptom of the same problem: rig name
  "charon-private", hostname "4-lom", and `/home/stack/...` paths baked
  into `fleet/state/ROADMAP.tsv` and `fleet/validate_board.sh`.
- Verdict: **SKIP** — wrong repo entirely. This ticket's work belongs in
  charon-private, not the product. Close (or redirect) rather than fix
  forward; fixing the public-clean leak alone would still leave fleet/
  build-infra shipped inside the product.

## PR #131 — docs(SR-4): review-log only, "already complete on charon-private master"
- Diff is exactly one new file, `docs/review-log/sr-4.md`, 9 lines,
  stating "No changes needed on this worktree" / "git diff is empty."
  Confirmed: zero code changes, pure no-op.
- **CI: gate FAILS** — `public-clean` flags "charon-private" rig-name
  mentions in the review-log text itself (lines 3, 7).
- Verdict: **SKIP** — close as no-op. Nothing to land; the one file it
  adds doesn't even pass the gate as-is.

## PR #135 — chore(FT-CATALOG-SEED): launcher auto-commit, needs scrutiny
- Adds 3 new hosted provider presets (`github_models`, `featherless`,
  `ollama_cloud`) to `provider_presets/hosted.py`, a new
  `routing_policy/free_tier_catalog.py` data module, and
  `tests/test_free_tier_catalog.py` (own new tests pass, well-designed:
  sg-never-anthropic guard test, defensive-copy test, shape-parity test).
- **CI: gate FAILS on `pytest`, not public-clean** — 5 real test failures,
  all consequences of adding 3 new presets without updating the
  *existing* provider contract-test suite:
  - `test_provider_presets.py::test_all_original_keys_present` —
    `assert len(PRESETS) == len(_KNOWN_KEYS)` → 29 != 26 (the
    "known-keys" fixture was never updated for the 3 new presets).
  - `test_provider_response_contract.py::test_every_preset_has_a_declared_
    shape_fixture` and 3 per-preset variants — `featherless`,
    `github_models`, `ollama_cloud` have no declared raw-shape fixture,
    so the wire-shape contract test silently would've skipped them if
    the harness weren't fail-loud by design.
- This is exactly the failure mode the launch note warned about: an
  auto-committed draft that adds new surface without touching the
  pre-existing regression tests that are supposed to catch exactly this.
- Money/security note: new provider presets are a money-path surface
  (routing spend to new vendors) but ship `verified=False` placeholders
  with no live wiring yet — lower risk today, but the missing contract
  coverage is precisely the gap that would let a real wire-shape mismatch
  ship silently once wired.
- Verdict: **FLAG-INCOMPLETE** — needs `_KNOWN_KEYS` and the 3 missing
  shape-fixture entries added in `tests/test_provider_response_contract.py`
  / `test_provider_presets.py` before this can land.

## PR #144 — feat(gate): wire 3 declared-but-unwired checks into charon gate
- Adds `pytest -q`, `render-review-log` (generate mode, not `--check` —
  documented rationale: `docs/REVIEW-LOG.md` is gitignored/generated, and
  `ci.yml` already does the same for the same reason), and
  `check-decisions --check` to `gate_runner.py`'s `CHECKS` list, ordered
  so `render-review-log` runs before `check-decisions` (D002/D011 reference
  the rollup). Also fixes `tools/check_gate_registry.py`'s `ALL_DOMAINS` to
  include `ci-infra`/`no-rig-import` (registry-vs-domain-set drift).
  `validate-board` and `charon-gate` stay declared-but-unwired,
  intentionally (fleet-external / self-referential), documented inline.
- Review-log claims local verification: `charon.cli gate` green with all
  3 new checks executing, full pytest green (1795 passed), registry
  check green (17/17 domains covered).
- **CI: `gate` job was still IN PROGRESS at review time** (this PR wires
  the full `pytest -q` run into the gate job itself, so the job now takes
  materially longer — consistent with the stated change). `wheel-smoke`
  already PASSED. Re-check CI conclusion before merge; diff itself looks
  complete and the wiring is real (not just declared) — it's an actual
  addition to the `CHECKS` list that the CLI iterates, not a doc-only claim.
- Verdict: **LAND, pending final CI green** — diff is substantively
  complete and well-reasoned; just needs the in-flight `gate` run to
  finish before merge (was still `in_progress` via the Actions API at
  time of review).
