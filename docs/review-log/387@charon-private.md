# Review: 387@charon-private
**PR:** chore(STOP-WORKER-GRACEFUL-EXIT): launcher auto-commit — droid exited without committing (review for completeness)
**URL:** https://github.com/Nnyan/charon-private/pull/387
**Date:** 2026-08-02T04:37:50Z
**Reviewer:** reviewer-Tardis-3791246
**Author:** frontier-2842939

## Verdict
NEEDS-REVISION

## Findings
- Test (g) is broken. The g-launcher.py calls `bash "$SRC/stop-worker.sh"` without setting BASH_ENV=disable-kill.sh, without STUB_KILL_LIVE=1, and without ensuring the stub kill script is on PATH ahead of the bash builtin. The real `kill -9` terminates the stub HTTP server before the fail-closed HTTP check ever fires, so stop-worker.sh exits 0 ("STOPPED") instead of exit 1 ("FAILED to verify stop"). This /replaces/ the working old test (f) and removes the fail-closed regression guard for PR #272.
- Test (e) tests a hand-written mock (`stop-worker-escalate.sh`) instead of the real `stop-worker.sh`. The mock duplicates the escalation logic from the real script; any future change to the real script's loop structure or message format would not be caught because the mock is an independent copy.
- Test (e) uses `kill-sigtrack` which unconditionally returns 0 for `kill -0`, so the mock's `[(kill -0) || break]` condition is never exercised. Only output formatting is tested, not the control-flow branch where a process dies mid-escalation.
- The `kill-sigkill` stub is defined during setup but never referenced by any test assertion. Dead code.

## Fail-on-revert check
The misleading "INT/TERM exit 0 in <1s" claim returns, causing operators to trust that closeOnExit:graceful always auto-closes tabs when non-zero exits leave tab litter.

## Status
Pending Manager dispensation
