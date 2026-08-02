# Review: 393@charon-private
**PR:** fix(SANDBOX-CONTAINMENT): contain test sandboxes, fail closed, stop the gate-killer
**URL:** https://github.com/Nnyan/charon-private/pull/393
**Date:** 2026-08-02T04:35:46Z
**Reviewer:** reviewer-Tardis-3691021
**Author:** Nnyan

## Verdict
NEEDS-REVISION

## Findings
- **False-GREEN in the CI check when the fix is unwired.** `fleet/checks/sandbox-containment.sh` validates the ABSENCE of forbidden patterns (TMPDIR assignment, fire-time trap expansion, in-tree residue) but does NOT validate the PRESENCE of the remediation (the `source fleet/tests/lib/sandbox.sh && sandbox_init` call in `fleet/gate.sh`). If that call is removed, `gate.sh` contains none of the forbidden patterns — the check passes green — but the gate runs without containment, which is the exact incident condition this PR claims to fix. The check should verify that `gate.sh` both sources `sandbox.sh` and calls `sandbox_init`, not merely that it lacks violations.
- **Incomplete trap detection pattern in the check.** The grep in Check 1b requires `rm -rf` (`trap[[:space:]]+'[^']*rm[[:space:]]+-rf[^']*\$[^']*'[[:space:]]+EXIT`). It misses: `rm -r` without `-f`, `rm -fr`, `rm -rfv`, traps with `--` separator (`trap -- '...' EXIT`), and traps with multiple signals (`trap '...' EXIT INT TERM` — though the latter accidentally matches, it's luck, not design). Any of these undetected shapes could produce the same fire-time-expansion defect that killed 124/124 tests. A single-quoted EXIT trap whose body issues ANY `rm` over a local variable is the hazard class; narrowing to `rm -rf` leaves variants live.
- **`sandbox_in_worktree` depends on `git` being in PATH and un-tampered.** If `git` is absent, the function returns 1 ("not in a work tree") and `sandbox_init` accepts the candidate directory as safe. This is an in-band signaling trust: a compromised or missing git binary silently defeats the containment predicate. A fallback stat check (`[ -d "$p/.git" ]` or walking up the directory tree) would provide defense-in-depth.

## Fail-on-revert check
Removing `source fleet/tests/lib/sandbox.sh; sandbox_init` from `fleet/gate.sh` restores the incident root cause — unconstrained $TMPDIR lets bare `mktemp -d` create test sandboxes inside the git work tree, re-enabling `git add` exit-128 tab kills, cross-test sandbox deletion, and live-checkout fall-through commits under `t <t@t>`.

## Status
Pending Manager dispensation
