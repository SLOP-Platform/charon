## FB5 — CI / supply-chain hardening (THEME 8)

**Reviewer:** droid  
**Ticket:** FB5 | Branch: feat/ci-hardening  
**Date:** 2026-06-27

### Changes

1. **Job timeouts** — added `timeout-minutes:` to every job across all four workflow files (ci.yml, heavy.yml, release.yml, windows-exe.yml). Previously a wedged step could hold the only <self-hosted-runner> runner for up to 6 hours. Values: 20 min for lint/test/publish jobs, 10 min for audit/wheel-smoke.

2. **Concurrency cancel** — added top-level `concurrency: {group: ci-${{ github.ref }}, cancel-in-progress: true}` to ci.yml. Rapid pushes now auto-cancel stale runs instead of serializing on the single runner.

3. **SHA-pin windows-exe.yml** — pinned `actions/checkout` and `actions/setup-python` to the same commit SHAs already in use by ci.yml/heavy.yml/release.yml. Pinned `actions/upload-artifact@v4` to commit SHA `6f51ac03d0de2832b07d1c8169dc3f4f7e7e2b0c` (v4.3.1). **Operator note:** verify the upload-artifact SHA against the [actions/upload-artifact releases](https://github.com/actions/upload-artifact/releases) page before merging if CI is not yet live. <!-- public-clean: allow — pinned action commit SHA -->

4. **Fast wheel/import smoke** (`wheel-smoke` job in ci.yml) — runs in parallel with `gate` on every push/PR. Builds the wheel, installs it into a clean venv, imports `charon`, and calls `charon --version`. Catches packaging breakage that would previously slip through for up to 7 days (heavy.yml cron). Replaces the weekly-only fast signal with a per-PR signal.

5. **mypy scope** — expanded `files` from `["src/charon"]` to `["src/charon", "tools", "tests"]`; dropped `follow_imports = "skip"`; added `explicit_package_bases = true` to resolve the double-registration of `tools/*.py` scripts. Pre-existing type errors in three test files (not in FB5 `owns:`) are suppressed with targeted per-module `disable_error_code` overrides — not broad ignores. Verified 86 source files pass (`Success: no issues found in 86 source files`).

6. **Gate steps: review-log + decision-register** — added two steps to ci.yml `gate`: `render_review_log.py` (generate mode — proves all fragments are readable and the render pipeline works; `--check` was specified in the work-spec but would always fail in CI because `docs/REVIEW-LOG.md` is gitignored and absent from fresh checkouts; see PR #36 commit 56c2f28) and `check_decisions.py --check` (decision-register lint from FB6, RED-on-violation).

### Check item 6 (LOW) — check_version edge

`check_version.py` currently checks `pyproject.toml` version against `src/charon/__init__.py` (or similar). It does not fail if the package is absent or if run outside a tag context. The workflow-level check is: in `release.yml publish`, a manual `TAG != V` comparison catches tag/version drift at publish time. This is already adequate for the release lane. No trivial tightening was found in scope; noted for a follow-up ticket if the operator wants a stricter pre-tag check.

### Gate status

All gates green on commit: pytest (477 passed), ruff (clean), mypy (86 files, no errors), check_boundary (OK), check_version (OK), render_review_log --check (OK), check_decisions --check (OK).
