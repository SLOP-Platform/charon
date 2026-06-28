# SECRET-SCAN-ENVVAR-FP — stop the land gate false-positiving on env-var auth headers

## Why (surfaced by the 2026-06-27 live certification)
`land.run_gitleaks` (`gitleaks detect --source <repo>`) flags `.github/workflows/release.yml:63`
(`-H "Authorization: Bearer $CHARON_GATEWAY_TOKEN"`, RuleID `curl-auth-header`) as a secret and
`land` correctly HOLDS — but that's an **env-var reference, NOT a hardcoded secret**. Effect: a
`charon work` run can never reach `propose` on the charon repo itself (and any user repo using
env-var bearer headers hits the same false hold). The hold logic is right; the rule is too broad.

## What to build
Add a baseline gitleaks allowlist so legitimate **env-var** auth-header references are not flagged,
without weakening detection of REAL hardcoded secrets:
- Add a repo-root `.gitleaks.toml` that `extend`s the default config and allowlists the env-var
  bearer pattern (e.g. regex `Authorization:\s*Bearer\s*\$\{?[A-Z_][A-Z0-9_]*\}?`) — match the
  reference form, NOT a literal token.
- Confirm `land.run_gitleaks` honors a repo-level `.gitleaks.toml` (gitleaks auto-loads it from the
  scanned source root). If it does not, pass `--config`/baseline explicitly in `land.py` so the
  product ships this allowlist by default (not only when a target repo happens to have one).
- A real hardcoded secret (e.g. `Bearer sk-live-abc123…`) must STILL be caught — assert both.

## Acceptance
- Test: a tree containing only an env-var bearer header lands `propose` (no false hold); a tree with
  a literal hardcoded token still `hold`s on gitleaks. Existing land/gitleaks tests stay GREEN.

## CONSTRAINTS
Own ONLY: `.gitleaks.toml` (new) and the land test file (`tests/test_land.py` or a new
`tests/test_land_secret_allowlist.py`); add `src/charon/land.py` to owns ONLY if the config must be
passed explicitly (finalize at activation). Stdlib core; no secrets committed; gate GREEN every
commit. Conventional commits; review note → `docs/review-log/SECRET-SCAN-ENVVAR-FP.md`. Draft PR,
`submit.sh`, STOP. BACKLOG — tackle after the priority cluster if budget remains.
