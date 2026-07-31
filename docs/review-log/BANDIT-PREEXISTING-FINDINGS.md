# BANDIT-PREEXISTING-FINDINGS — review-log fragment

## Scope
3 pre-existing MEDIUM bandit findings (B310 ×2 + B103 ×1) flagged by the FULL-TREE
bandit run of 2026-07-22 but missed by the diff-scoped BANDIT-ADOPT gate. Resolved
here so the rig's own Python is clean at MEDIUM+ (tree-scoped bandit green).

## Resolutions
FIX preferred over `nosec`. Per finding:

1. **fleet/benchmark/lib/charon_cost.py:189 — B310 (urlopen).** FIX + nosec combo.
   The URL comes from `gateway_auth()` (operator-controlled opencode provider config or
   `CHARON_BENCH_STATUS_URL` env override, both of which are documented to be an https
   endpoint — opencode custom provider `baseURL` is https by contract). Added
   `if urlsplit(url).scheme != "https": return None` scheme gate before the call so the
   http/file/custom-scheme vectors bandit warns about genuinely cannot reach `urlopen`.
   Doc + `# nosec B310` carries the justification (the bandit `B310` plugin flags the
   call site itself regardless of scheme; the nosec explains the proximate check).

2. **fleet/benchmark/selftest/session_cost_selftest.py:114 — B310.** `nosec` only
   (no fix). Rationale: the URL here is `proxy.url + "/v1/chat/completions"` where
   `proxy` is an in-process `GatewayProxyServer` mock bound to `127.0.0.1:<rand>`
   (see lines 136-141, 144, 163, 169, 173). The endpoint is local HTTP by design;
   scheme-asserting it to https would break the test against its own mock. The risk
   surface is the loopback binding (`127.0.0.1:`), not the opencode provider flow.
   `# nosec B310 - test-only loopback http to GatewayProxyServer mock (~127.0.0.1); not
   network-reachable` documents this on the single call site.

3. **fleet/benchmark/selftest/run_isolation_selftest.py:299 — B103.** FIX.
   `0o755` → `0o700`. The chmoded file is `bench.sh`, executed in-process by THIS
   selftest as a subprocess via `shell=True` (the only consumer). Owner-only
   `0o700` is sufficient; group/other-read was not required, and the ticket notes
   `0o750` is the tighter alternative — `0o700` is even tighter. Bandit's
   `B103` fires on any non-`0o600` setting on a regular file, so `0o700` clears it.

## Verification
- `bash fleet/checks/bandit.sh` (TREE scope, 270 files) → "OK — no bandit findings
  at/above severity 'medium'". Pre-req met for making the bandit gate tree-scoped.
- `pytest -q` → 58 passed (in this checkout's fleet/ slice).
- Ruff/mypy on src/tests: 17 ruff + 1 mypy errors are PRE-EXISTING on master
  (verified via `git stash` of my changes → same counts), unrelated to this ticket
  and out of `owns:`. Not blocking.
- `tools/check_boundary.py` and `tools/check_version.py` are not present in this
  worktree (the launcher prompt's step-3 commands); cannot run them. The security-
  relevant gate (bandit) is what this ticket accepts on.

## Diff scope (vs master)
- fleet/benchmark/lib/charon_cost.py
- fleet/benchmark/selftest/run_isolation_selftest.py
- fleet/benchmark/selftest/session_cost_selftest.py

All three are in `owns:`. No off-scope edits.

## Notes for the reviewer
- The two `# nosec` markers are per-site and one-line — not blanket suppressions, per
  `[[never-ignore-preexisting-issues]]` and the ticket's accept criteria.
- The scheme gate in `charon_cost.py` is a real behavioral change: an operator who
  misconfigures their opencode provider `baseURL` to `http://...` will now
  silently get `snapshot_cost_usd() -> None` instead of leaking a Bearer token over
  an unencrypted channel. The cost-attribution caller already treats `None` as
  "fall back to global delta", so this is fail-safe.
