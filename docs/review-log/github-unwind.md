## 2026-06-25 — UNWIND GitLab → public GitHub `SLOP-Platform` org (HANDOFF §9)

- **Change under review:** the operator reversed the GitLab decision the same day
  (HANDOFF §9, PIVOTED). GitLab added real friction (SSH/token scope, a different
  CI dialect, a heavier UI; the first pipeline failed `yaml invalid`). The
  established cost of GitHub was only Actions minutes — and a **public** repo on a
  **self-hosted runner** costs zero minutes. So Charon becomes the public repo
  `github.com/SLOP-Platform/charon`, CI on the shared self-hosted **<self-hosted-runner>** runner
  pool. This entry SUPERSEDES the GitLab-migration entry directly above (kept as
  history, not rewritten). No application code changed — host plumbing only.
- **Remote:** `origin` set to `git@github.com:SLOP-Platform/charon.git` (SSH,
  verified reachable); the abandoned `gitlab` remote removed. Repo confirmed
  already **PUBLIC**. Tree audited for private/dev files before going public —
  `git ls-files` carries only source/docs/CI; caches, `dist/`, `.venv`, `.claude`
  are all gitignored and untracked. Nothing to scrub.
- **CI rework (operator spec §9a — fast/slow split):**
  - `.gitlab-ci.yml` **deleted**.
  - `.github/workflows/ci.yml` → **fast gate** on every push/PR
    (boundary/version/ruff/mypy/pytest, installing `[dev,service]` so dashboard
    tests run), `runs-on: [self-hosted, <self-hosted-runner>]`.
  - `.github/workflows/heavy.yml` (new) → **slow suites** on `schedule:` (weekly)
    + `workflow_dispatch:` only: Mode-A clean-wheel isolation smoke (INV-B6),
    image build-smoke, advisory `pip-audit`. Keeps the push gate fast.
  - `.github/workflows/release.yml` (new) → GHCR publish on a published Release,
    `needs: [gate, image-smoke]` (an untested image can never be published, BR2-8).
  - `.github/actionlint.yaml` (new) teaches actionlint the `<self-hosted-runner>` label (§9a
    gotcha 2). Validated: `actionlint` clean across all three workflows.
- **Runner-ownership boundary honored:** registered/configured **no** runners and
  touched **no** org runner settings — runner/pool setup is owned elsewhere. These
  workflows only *reference* `[self-hosted, <self-hosted-runner>]`; if the
  pool isn't online yet, runs simply QUEUE. Disclosed honestly: **the workflows
  are YAML-/actionlint-valid but not proven green** until they run on the live
  runner — verify ONE gate goes green there (§9a gotcha 5) before trusting CI.
- **Provenance — the GitLab "open item" evaporated.** Back on GitHub, GHCR +
  GitHub-native `actions/attest-build-provenance` (OIDC, no key management) is the
  original cleanest path; restored in `release.yml` and `SUPPLY-CHAIN.md §5`.
  cosign stays rejected (a compromised runner would hold its key too; OIDC needs
  no stored key).
- **Self-hosted gotchas baked in (§9a):** `actions/setup-python 3.12` (works on
  the Ubuntu runner); wheel-isolation smoke installs into `$RUNNER_TEMP/clean`,
  never root-owned `/usr/local/bin`; no `PYTEST_ADDOPTS --basetemp` (hermeticity).
- **URL/registry redirects** `gitlab.com/slop-platform/charon` →
  `github.com/SLOP-Platform/charon` and `registry.gitlab.com/...` →
  `ghcr.io/slop-platform/charon` across `pyproject.toml`, `README.md`,
  `docker-compose.yml`, `docs/adr/0001`+`0002`, `docs/PLAN-tier1`+`tier2`,
  `docs/SUPPLY-CHAIN.md §5`. HANDOFF §9 and the prior REVIEW-LOG entry keep their
  GitLab references as decision history.
- **What stays operator-only:** the push to `origin` (harness-gated; handed over
  as a `!` command).

WALK-BACK: this entry IS a walk-back — it reverts the immediately preceding
GitLab port. Net for the repo since `e1bd94e`: `.gitlab-ci.yml` removed, three
`.github/workflows/*.yml` + `actionlint.yaml` added/reworked, URLs redirected.
Application code untouched; 114 tests still green locally.
