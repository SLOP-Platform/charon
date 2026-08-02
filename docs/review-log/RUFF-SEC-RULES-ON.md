# RUFF-SEC-RULES-ON review note

**Date:** 2026-08-01
**Ticket:** RUFF-SEC-RULES-ON
**Branch:** fix/ruff-sec-rules-on

## What changed

1. `pyproject.toml`: `[tool.ruff.lint].select` now reads
   `["E", "F", "I", "B", "UP", "S", "BLE"]` — the `S` (flake8-bandit) and `BLE`
   (blind-except) families are ON. Every linted file is now security-scanned by
   the linter already running on every PR, at no new dependency.
2. `pyproject.toml`: `[tool.ruff.lint].per-file-ignores` baselines the 70 src +
   13 tools findings that fired on switch-on, per-file and per-rule, each with a
   written reason — no blanket noqa sweep, no global ignore.
3. `tests/test_lint_security_rules.py` (new): fail-on-revert tests asserting the
   families stay selected, that S602 is never exempted for `tests/**`, and that
   the genuine S602/S104 findings stay pinned to their files.

## Measured counts

- Switch-on surface (2026-08-01, `ruff check src tests tools --select S,BLE`):
  **70 src / 4616 tests / 13 tools** findings (the ticket's "72" was a src-only
  snapshot; today src is 70).
- After baseline: `ruff check` on the whole tree is green.

## Baselined findings, by rule (src)

- `BLE001` blind-except: deliberate broad catches that surface loudly or
  continue (fail-closed reviewer, per-unit isolation, poll-and-continue); many
  sites already carry an inline `# noqa: BLE001` with a justification.
- `S603` / `S607`: all `subprocess` uses are argv-list form with **no shell**
  (git/ruff/sys.executable), and bare tool names resolved via PATH — safe and
  intentional.
- `S101` assert (3 src sites): guarded internal invariants / test seam sentinel.
- `S105`: false positives — `_TOKEN_ENV` is an env-var **name**, and
  `review_mock.PASS` is an enum member holding the string `"pass"`.
- `S110` / `S112`: best-effort teardown/parse-and-continue, mostly already
  annotated inline.

## The two genuine findings — pinned, not swept

- `src/charon/acceptance.py:52` **S602 `shell=True`** — the one genuine
  `shell=True`. `AcceptanceCheck.verify()` runs user-configured commands
  verbatim; that **is** the feature. The code already carries `# noqa: S602` on
  the `shell=True` row, one line below the `subprocess.run(` call site, so
  ruff's line-scoped suppression misses it. Relocating the noqa is a `src` edit
  — out of this ticket's `owns:` — so it is pinned to that one file with the
  reason, visible until a source-owning ticket lands the fix.
- `src/charon/gateway.py:824` **S104 bind-all** — false positive: `cfg.host ==
  "0.0.0.0"` is a string equality used to pick the LAN console URL for a log
  line; no socket bind happens at that site. Pinned to the file for the same
  owns reason.

Residual risk, by design: per-file baselines keep those rules off for *new* code
added to the same baselined files. New/untouched files are fully checked (probed:
S602/S607/S105 fire on a fresh path), and `S602` remains enforced under
`tests/**`. A follow-on ticket owning the baselined src files should shrink these
entries as it fixes them.

## Red-proof (external)

- Removing `"S"` from `select` → `tests/test_lint_security_rules.py`:
  `test_security_families_are_selected` and
  `test_fail_on_revert_removing_a_family_goes_red` both RED (2 failed, 2 passed);
  restored → 4 passed. So any revert of the select list is caught by both the
  runtime linter and the static test.
- The fail-on-revert test's verdict depends on the live `select` list, not a
  hardcode.

## Gate

`pytest` 2384 passed, 3 skipped, 1 xfailed, 1 xpassed; `ruff check` clean;
`mypy src tests` clean (269 files); boundary + version checks OK.
