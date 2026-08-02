repo: charon
tier: economy
priority: 1
difficulty: 2
work_class: ci-infra
branch: fix/ruff-preview-on
depends_on: RUFF-SEC-RULES-ON
dep-kind: merge-order
owns: pyproject.toml, tests/test_lint_preview_enabled.py
real-dep: |
  real-dep: RUFF-SEC-RULES-ON — co-owns `pyproject.toml`; MERGE-ORDER only, not a build
  prerequisite [[disjoint-owns-not-no-dependency]]. That ticket is LIVE and UNCLAIMED as of
  2026-08-01. The edge exists so the collision is ORDERED rather than silent: three tickets
  (this one, RUFF-ARG-C90-ON, MYPY-STRICTNESS-3-FLAGS) all need the same file, and an
  unordered board is a RED under validate_board.sh's owns-collision rule.
serial_justified: |
  One config flag plus the burn-down it forces plus the fail-on-revert assertion. Splitting the
  flag from its burn-down ships a lint config that nobody can pass; splitting the assertion from
  the flag ships an enablement that can silently rot back off, which is the exact failure mode
  this whole A-series exists to end.
substrate: N/A
substrate-novel: |
  NO TOOL IS BEING ADOPTED HERE, so there is nothing to consult a registry about. ruff is already
  adopted, already configured at `pyproject.toml:45-52`, and already runs on every file of every
  PR via `fleet/checkin.sh` and product CI. This ticket changes ONE line of that tool's config.
  The candidate substrates were considered and none of them applies:
  A second linter (pylint, flake8, pyflakes) would ADD a dependency to obtain rules that the
  linter we already run has behind a flag. That is the textbook under-scoped-trial anti-pattern
  the EVAL-REGISTRY itself catalogues at its ANTI-PATTERN row: configuring the incumbent too
  narrowly and then adopting a challenger for a job the incumbent already does. Enabling the flag
  is strictly cheaper than any adoption and carries zero new dependency and zero new runtime.
  A "lint baseline" tool (e.g. a ratcheting suppression generator) was considered for the
  burn-down half and REJECTED for this ticket's size: 12 defects with 7 auto-fixable is a
  same-sitting burn-down, and a generated baseline over a 12-item set would freeze known bugs in
  for no saving. That is the D4 lesson stated as policy below, not a tool gap.
  THE GENUINELY NOVEL SLICE is therefore not code at all — it is the DISPOSITION of the 12
  findings (fix vs baseline, per finding, with a reason) plus a fail-on-revert assertion that
  makes the enablement irreversible-by-accident. No external tool supplies either. That is the
  ~30% that has to be hand-written, and it is all this ticket ships.
source: |
  fleet/state/PRIORITY-TODO.md section A, row A1. Verified live 2026-08-01 against
  pyproject.toml:51-52 — `[tool.ruff.lint]` carries `select = ["E","F","I","B","UP"]` and NO
  `preview` key anywhere in the file.
note: |
  ## THE FINDING — DEFECTS INSIDE FAMILIES WE ALREADY SELECT

  This is not a request to lint more code or to add rule families. The families `E`, `F`, `I`,
  `B` and `UP` are ALREADY selected and already gate every PR. ruff gates a subset of the rules
  inside those very families behind `preview = true`, and with the flag off we are running a
  partial implementation of the config we believe we have.

  MEASURED (PRIORITY-TODO A1): 12 defects surface inside already-selected families, 7 of them
  auto-fixable by `ruff check --fix`. Nobody chose to exclude these. They are excluded by a
  default.

  ## WHY THIS IS THE CHEAPEST ROW IN SECTION A, AND WHY IT GOES FIRST

  12 findings, 7 mechanical. Compare A2 (184) and A3 (176). It is deliberately sequenced first
  among the three `pyproject.toml` tickets so that the two larger burn-downs behind it run
  against an already-preview-enabled ruff and never have to be re-measured. See the Dependencies
  & Sequence section for the full chain and its reasoning.

  ## SCOPE

  1. Add `preview = true` under `[tool.ruff.lint]` in `pyproject.toml`.
  2. Run `ruff check src tests` and enumerate every new finding, with its rule code.
  3. Apply `ruff check --fix` for the auto-fixable subset. REVIEW the diff — an auto-fix is still
     a code change and still needs eyes. Do not blind-commit a `--fix` sweep.
  4. Fix the remainder by hand, OR baseline it under the explicit rule in the next section.
  5. Add the fail-on-revert test.
  6. Leave the rest of the ruff config alone. `select`, `extend-select`, `mccabe` and the mypy
     block belong to the two tickets sequenced behind this one — do NOT touch them, or you turn
     an ordered chain into a merge conflict.

  ## BURN DOWN OR BASELINE — STATE WHICH, PER FINDING

  THE DEFAULT FOR THIS TICKET IS BURN DOWN. All 12 are expected to be FIXED.

  A baseline is permitted ONLY per-finding, ONLY with a written reason on the `noqa` line, and
  ONLY if fixing it is a genuine behaviour change out of scope here. A blanket `noqa` sweep, a
  file-level `# ruff: noqa`, or moving a rule out of `select` to make the run green are all
  explicit FAILURES of this ticket — they produce the same green CI while deleting the signal.

  THE D4 RULE, AND IT IS NOT OPTIONAL. PRIORITY-TODO section D4 states the general form: a
  suppression baseline generated BEFORE known defects are fixed "freezes the bugs in
  permanently". If any baseline is used at all it MUST be generated AFTER the burn-down, so it
  contains only the residue that was consciously accepted, never the defects nobody looked at.
  Generating first and fixing later is the failure; the order is the whole safeguard.

  The final report must state, in one line per finding: rule code, file:line, and FIXED or
  BASELINED-because-<reason>. Twelve lines. That is the disposition ledger.

  ## DONE CONTRACT — RED THEN GREEN, EXTERNALLY RED-PROOFED

  a. `preview = true` is present under `[tool.ruff.lint]` in `pyproject.toml`.
  b. `ruff check src tests` is GREEN at the end.
  c. FAIL-ON-REVERT, the assertion that matters: `tests/test_lint_preview_enabled.py` reads the
     ruff config as the tool itself resolves it and asserts preview is ON. Delete or flip the
     `preview` line and that test must go RED. A test that merely asserts `ruff check` exits 0
     is worthless here — it stays green with the flag off, which is precisely today's state.
  d. The test must ALSO assert at least one specific preview-gated rule is actually reachable,
     not just that a config key exists. A key can be present and inert (wrong table, wrong
     spelling); the point is that the RULES fire. Assert against ruff's own resolved rule set or
     against a fixture file that ruff must flag.
  e. The 12-line disposition ledger appears in the review-log entry.
  f. Report BOTH counts — green with the change in place, RED on each revert. A test that passes
     with the enablement removed proves nothing.

  ## HANDS OFF

  Do NOT flip `select`, add `extend-select`, add `[tool.ruff.lint.mccabe]`, or touch
  `[tool.mypy]`. Those are RUFF-ARG-C90-ON and MYPY-STRICTNESS-3-FLAGS, sequenced behind this
  ticket on the same file. Do NOT close, edit or comment on any pull request.

## Dependencies & Sequence

- **depends_on: RUFF-SEC-RULES-ON — merge-order, NOT a build prerequisite.** Nothing in this
  ticket needs the `S`/`BLE` families to exist. The edge is a serialisation of a shared file.
- **THE owns-COLLISION, stated in full.** `pyproject.toml` is wanted by FOUR live tickets:
  `RUFF-SEC-RULES-ON` (already live and unclaimed, owns it today), plus the three minted in this
  batch — this one, `RUFF-ARG-C90-ON`, and `MYPY-STRICTNESS-3-FLAGS`. THEY CANNOT RUN IN
  PARALLEL. `fleet/validate_board.sh` REDs any live owns-collision that carries no dep ordering,
  and two agents editing one TOML table concurrently is a guaranteed conflict on top of that.
- **The chain, and why this order.**
  `RUFF-SEC-RULES-ON` → **RUFF-PREVIEW-ON** → `RUFF-ARG-C90-ON` → `MYPY-STRICTNESS-3-FLAGS`.
  1. Security first. RUFF-SEC-RULES-ON is a security ratchet already live, and every PR merged
     before it lands is unscanned by `S`/`BLE`. It also holds the file today, so it anchors.
  2. Preview second — it is the CHEAPEST (12 findings, 7 mechanical) and it CHANGES WHAT THE
     TWO TICKETS BEHIND IT MEASURE. Several `S` and `ARG`-adjacent rules are preview-gated; the
     EVAL-REGISTRY bandit row records exactly this, that `S404` is preview-gated and measures 9
     under `--preview`. Landing preview LAST would invalidate the ARG/C90 burn-down and force a
     re-measure. Cheapest first AND it shrinks the next one.
  3. `ARG`/`C90` third — a large burn-down (ARG alone measured at 406) that also removes dead
     parameters and unreachable complexity, which SHRINKS the mypy surface behind it.
  4. mypy last — the largest and least mechanical (176 real bugs), run against the smallest
     residue once both ruff passes have cleaned up.
  Every step reduces the next step's work. Reversing any pair means measuring twice.
- **Blocks / unblocks:** blocks `RUFF-ARG-C90-ON` (which blocks `MYPY-STRICTNESS-3-FLAGS`).
  Unblocks nothing else. It does NOT block `SHELLCHECK-OPTIONAL-CHECKS-ON` or
  `GRAPHIFY-AFFECTED-WIRE` — those are rig-repo tickets that share no path with this one and are
  free to run concurrently with the entire chain.
- **Concurrency safety:** `tests/test_lint_preview_enabled.py` is a NEW path owned by no other
  live ticket; verified against the live board 2026-08-01. `pyproject.toml` is safe ONLY under
  the chain above.
- **Related, do NOT fold in:** `PYLINT-UNUSED-ARGS` (submitted, product PR #210) belongs to
  `RUFF-ARG-C90-ON`'s comparison, not to this ticket. Do not touch that PR from here.
