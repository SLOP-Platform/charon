repo: charon
tier: economy
priority: 0
difficulty: 1
work_class: ci-infra
branch: chore/release-0-6-2
owns: pyproject.toml
depends_on:
dep-kind:
work_class_note: ci-infra — a version bump that cuts the release which DEPLOYS the D-012 money fix.
  No feature change; the whole value is making already-merged money-path code actually run.
note: |
  ⛔ OPERATOR-INSTRUCTED 2026-08-04: "cut the release".

  ## WHY THIS IS PRIORITY 0
  The gateway runs as a CONTAINER — `ghcr.io/slop-platform/charon:v0.6.1` — and there is NO charon
  git checkout on the deployment host at all. master is **14 commits ahead of v0.6.1**, and those
  commits include `1d675bc` = D-012: a fully-parked pool returns a terminal 503 instead of a silent,
  billed 200.

  ⇒ Until this release is cut AND the container is pulled, THE MONEY LEAK IS STILL LIVE. Measured
  2026-08-03: kimi-k2.6 (5/5 legs parked) and minimax-m2.5 (2/2 parked) both served 200. Nothing has
  changed that in production. Landing D-012 on master did not stop the spend; deploying it does.

  This is the deploy-drift class already on record: DEPLOYED IMAGE != SOURCE.

  ## WHAT SHIPS IN v0.6.2 (the 14 commits since v0.6.1)
  Headline: D-012 (503 for a fully-parked pool), the three relocated security scanners now REQUIRED
  on master, the public-repo runner hard-pin, and the outcome test.

  ## MECHANISM (verified by reading .github/workflows/release.yml)
  Version SSOT is `pyproject.toml::project.version` (ADR-0002 §4; enforced by tools/check_version.py).
  release.yml fires on a `v*` TAG PUSH and publishes `ghcr.io/slop-platform/charon:v<version>`.
  Deployment is MANUAL and deliberately so — the host pulls immutable `:vX.Y.Z` tags via
  `/home/stack/charon/docker-compose.yml` on the gateway host.

  ## ⚠ TAG PUSH: use the GitHub API, NOT land-push.sh
  On record: land-push mangles tags (commits are safe). Create the tag as a ref instead:
    gh api -X POST repos/SLOP-Platform/charon/git/refs \
      -f ref=refs/tags/v0.6.2 -f sha=<merge-commit-sha>

  ACCEPTANCE: (a) pyproject version = 0.6.2 and the version gate is green; (b) tag v0.6.2 exists on
  the merge commit; (c) release.yml completed and `ghcr.io/slop-platform/charon:v0.6.2` exists in
  the registry; (d) the gateway host runs v0.6.2; (e) a fully-parked pool returns 503 IN PRODUCTION,
  not just in tests — that is the only proof that matters here.
