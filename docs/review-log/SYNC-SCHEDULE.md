# SYNC-SCHEDULE review log

## Change
Wire `fleet/sync-checkouts.sh` into:
1. `fleet/preflight.sh` — called at the top of the `scan` dispatch, so every build wave runs against a current local master
2. `fleet/hooks/session-start.sh` — already called it (pre-existing wiring from prior ticket)

Session-start was already wired; this ticket adds the preflight.sh call.

## Verification
- `preflight.sh:779` — `bash "$HERE/sync-checkouts.sh"` is the first command in the scan dispatch, ahead of `reconcile-merged.sh` and all gates (incl. `hold_reason_gate`, added on master after this ticket branched)
- `session-start.sh:31-35` — already calls `$SYNC_SH` at hook start
- Both calls are idempotent (FF-only, dirty-safe, divergence-guarded)

## Scope
Only touched `owns:` files:
- `fleet/preflight.sh`
- `fleet/hooks/session-start.sh` (no change needed — already wired)

## Adversarial review (PR #128 @ 5fcce09) — DO-NOT-LAND, remediated
The review's verdict was that the WIRING was fine but the SCRIPT it now calls on every scan was
not fit for the session-start critical path. Fixed on this branch rather than ticketed (standing
"never ignore pre-existing issues" rule) — all three defects were already live via the
SessionStart hook; this PR only raised their frequency.

- **HIGH / silent branch flip.** `sync-checkouts.sh` restored the pre-existing branch only on the
  FAILURE path; the success path ran `checkout master` unconditionally, so a checkout on a feature
  branch was flipped to master while logging `master FF'd` as success — against two main checkouts
  shared by ~70 worktrees. FIX: a `master:master` refspec fetch does not need master checked out,
  so when HEAD is not on master there is now NO checkout at all. When HEAD *is* on master we
  detach, fetch and restore master on BOTH paths; a failed restore is reported LOUDLY on stderr
  with the recovery command instead of silently leaving a detached HEAD.
- **HIGH / unbounded hang.** Both fetches now run under `timeout` (`SYNC_CHECKOUTS_FETCH_TIMEOUT`,
  default 20s) with `GIT_TERMINAL_PROMPT=0`, `ssh -o BatchMode=yes -o ConnectTimeout=5`, and
  `http.lowSpeedLimit/lowSpeedTime`. A credential/host-key prompt or a blackholed network is now a
  bounded, printed failure. Measured: 3s vs an outer-killed 90s+ block on a TEST-NET-1 remote.
- **MEDIUM / vacuous test evidence.** No test executed the `scan` dispatch at all (the
  `BASH_SOURCE` guard means sourcing skips it, and the other tests call `hold-check`), so the
  cited green counts would have been identical if the new command were `sleep 600`.
  `fleet/tests/sync-checkouts.test.sh` (D) now runs the real dispatch against a fixture fleet with
  recorder stubs and asserts the sync ran, ran FIRST, and that the rest of the chain is intact.
- **Also fixed:** per-repo `flock` around each sync (concurrent scans no longer interleave
  checkout/fetch); paths derived from `fleet/repo-registry.sh` (the path SSOT) instead of a second
  hardcoded copy; and `preflight.sh` now guards the call with `[ -f ]` like the hook does, warning
  instead of emitting a bare `bash: No such file` at the top of every scan.

Fail-on-revert demonstrated for each on scratchpad copies: reverting the branch-restore reds A1/A3
(with the same misleading `master FF'd` line), reverting the timeout reds B1, deleting the dispatch
command reds D1/D3. Added happy-path latency from these guards: ~+9 ms per run on local fixtures
(registry lookup + flock + timeout fork, both repos); the network round-trip is unchanged and is
now bounded at <=20s per fetch instead of unbounded.

## Tests
- `fleet/tests/sync-checkouts.test.sh` — 17/17 (new; added to the rig-ci allowlist so it is actually enforced)
- `fleet/tests/rig-ci.test.sh` — 11/11
- `fleet/tests/hold-reason-gate.test.sh` — 8/8
