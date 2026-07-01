# CI1 — CI runner variable (A-Clean pattern)

**Date:** 2026-06-27  
**Ticket:** CI1 (tier: sonnet)

## What was done

Replaced `runs-on: [self-hosted, <self-hosted-runner>]` on every pinned job across three workflow files
with the A-Clean repo-variable pattern:

```yaml
runs-on: ${{ fromJSON(vars.CI_RUNNER || '"ubuntu-latest"') }}
```

Jobs updated:
- `ci.yml`: `gate`, `wheel-smoke`
- `heavy.yml`: `modeA-isolation`, `image-smoke`, `supply-chain-audit`
- `release.yml`: `gate`, `image-smoke`, `publish`

`windows-exe.yml` was left untouched — it already uses `windows-latest` and works on forks.

Added decision register row D020, created `CONTRIBUTING.md` with a CI section.

## Operator action required

**Set repo variable `CI_RUNNER=["self-hosted","<self-hosted-runner>"]` in Settings → Variables → Actions
variables on the upstream `SLOP-Platform/charon` repo.**

Until this variable is set, upstream CI runs on GitHub-hosted `ubuntu-latest` (no error,
no queue stall). Once set, upstream uses the <self-hosted-runner> self-hosted pool as before.

Forks never inherit repo variables, so fork PRs always fall back to `ubuntu-latest`
automatically — no action needed for contributors.

## No blast-radius concerns

Change is purely CI config. No product code, no src/, no pyproject.toml. The gate
(`check_decisions.py --check`) was verified green after adding D020.
