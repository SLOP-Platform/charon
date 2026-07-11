# Contributing to Charon

Thank you for your interest in contributing!

## Getting started

1. Fork the repository and clone your fork.
2. Create a virtual environment and install in dev mode:
   ```
   pip install -e '.[dev,service]'
   ```
3. Install the public-clean pre-commit hook (one time — this is a **public**
   repo, so the hook blocks a commit that would stage personal/internal info):
   ```
   git config core.hooksPath tools/hooks
   ```
4. Run the gate locally before pushing:
   ```
   PYTHONPATH=src python3 -m pytest -q
   ruff check src tests tools
   mypy src/charon tools tests
   python3 tools/check_boundary.py src
   python3 tools/check_version.py
   python3 tools/check_public_clean.py
   python3 tools/check_decisions.py --check
   ```

## Public-clean guard

This is a **public** repo. A guard (`tools/check_public_clean.py`) runs in the
gate, in CI, and in the optional pre-commit hook. It reds on personal/internal
tokens: internal IPs (`10.x`, `192.168.x`, `172.16–31.x`), the build-host and rig
names, home paths, long hex secrets, and the maintainer's personal given name.
The pre-commit hook scans the **staged** blob (`--staged`), so what it checks is
exactly what will be committed — `git add -p` cannot slip a leak past it.

If the guard reds on a **legitimate** mention (e.g. an example IP in docs, or a
CI-runner name that is genuinely public), use one of two documented waivers —
add either **only after review**:

1. **Inline waiver** — put `public-clean: allow` in a same-line comment,
   ideally with a short reason. Works in any comment syntax:
   ```
   host = "10.0.0.1"  # public-clean: allow — RFC 5737 example, not a real host
   runs on 4-lom <!-- public-clean: allow — CI runner name is public -->
   ```
   It only suppresses the line it is on.

2. **Exceptions ledger** — `tools/.public-clean-exceptions.json`, keyed by file
   path to the exact **line content** to waive (not line number). If the line is
   later edited or removed, the waiver stops matching and the line is re-checked
   — fail-safe, never fail-silent. A drift-guard test
   (`test_shipped_exceptions_match_tracked_file_content`) reds if any entry no
   longer matches its file verbatim.

Prefer scrubbing the token over waiving it. Reach for a waiver only when the
value is genuinely public and cannot be removed.

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
