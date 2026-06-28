# Review log — SECRET-SCAN-ENVVAR-FP

## Problem
`gitleaks detect --source <repo>` flags `.github/workflows/release.yml:64`
(`-H "Authorization: Bearer ci-smoke-token"`, RuleID `curl-auth-header`).
The value `ci-smoke-token` is the CI integration smoke-test placeholder — not a real
secret — but gitleaks has no way to know this without an explicit allowlist.

## Decision: repo-level `.gitleaks.toml`, no `land.py` change needed

Gitleaks v8 auto-loads `(target path)/.gitleaks.toml` as config option #3:
```
order of precedence:
1. --config/-c
2. env var GITLEAKS_CONFIG
3. (target path)/.gitleaks.toml
```
Confirmed with gitleaks 8.21.2: `gitleaks detect --source <repo>` picks up
`<repo>/.gitleaks.toml` automatically — even when called from a different CWD.
Therefore `land.py` does NOT need a `--config` flag; no file outside `owns:` touched.

## Allowlist design

Two `regexTarget = "line"` patterns in the global `[allowlist]`:

1. `Authorization:\s*Bearer\s*\$\{?[A-Z_][A-Z0-9_]*\}?` — env-var references
   (defensive; gitleaks 8.21.2 doesn't flag `$VAR` by default, but a future rule
   change could).

2. `Authorization:\s*Bearer\s*ci-smoke-token` — the concrete CI placeholder.

Using `regexTarget = "line"` means the regex must match the whole source line, not
just the extracted secret value. This is narrower than a secret-value match and
cannot accidentally suppress a real secret that happens to contain the substring.

Real hardcoded tokens (e.g. `Bearer sk-live-abc123abcdef456789`) don't match either
pattern and are still caught — verified by `test_hardcoded_token_still_flagged_with_config`.

## Scope self-check
Changed paths: `.gitleaks.toml`, `tests/test_land_secret_allowlist.py`,
`docs/review-log/SECRET-SCAN-ENVVAR-FP.md` — all within `owns:`.
