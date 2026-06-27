# Contributing to Charon

Thank you for your interest in contributing!

## Getting started

1. Fork the repository and clone your fork.
2. Create a virtual environment and install in dev mode:
   ```
   pip install -e '.[dev,service]'
   ```
3. Run the gate locally before pushing:
   ```
   PYTHONPATH=src python3 -m pytest -q
   ruff check src tests tools
   mypy src/charon tools tests
   python3 tools/check_boundary.py src
   python3 tools/check_version.py
   python3 tools/check_decisions.py --check
   ```

## CI

CI runs automatically on every pull request via GitHub Actions.

**For forks:** CI uses GitHub-hosted `ubuntu-latest` runners automatically — no
configuration needed. Open a PR and CI will run.

**For maintainers:** The upstream repo uses a self-hosted runner pool (`4-lom`) by setting
the `CI_RUNNER` repo variable (Settings → Variables → Actions variables) to
`["self-hosted","4-lom"]`. Forks do not inherit repo variables, so they fall back to
GitHub-hosted runners transparently.

If `CI_RUNNER` is unset — even in the upstream repo — CI falls back to `ubuntu-latest`
with no error. The variable is advisory; CI is never blocked by its absence.

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/):
`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `ci:`, etc.

## Pull requests

- Target `master`.
- All gate checks must be green before review.
- One logical change per PR; keep diffs small and reviewable.
