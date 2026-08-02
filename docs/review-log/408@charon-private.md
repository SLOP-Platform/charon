# Review: 408@charon-private
**PR:** chore(REPO-MAP-CONVERGE): launcher auto-commit — droid exited without committing (review for completeness)
**URL:** https://github.com/Nnyan/charon-private/pull/408
**Date:** 2026-08-02T15:33:10Z
**Reviewer:** reviewer-tab-2541120
**Author:** frontier-3197544

## Verdict
NEEDS-REVISION

## Findings
- Silent fail-closed with an inaccurate contract (validate_board.sh `_make_repo_roots`): the `except Exception: pass` swallows every registry-subprocess failure (missing bash, registry syntax error, 10s timeout, failed `source "$0"`) with no diagnostic, and the unconditional `result["charon"] = PRODUCT_REPO; result["product"] = PRODUCT_REPO` lines run outside the try — so REPO_ROOTS is never `{}` as the docstring and decision note claim. On any failure the accepted-key set silently collapses to {charon, product}, so every rig/keystone/charon-private ticket suddenly REDs as `unknown-repo` with no way for operators to distinguish a bad ticket from a broken registry. This converts a config failure into a silent policy change — fail-closed, but fail-silent, which the REPO-MAP-CONVERGE note explicitly claimed to avoid.
- The shell bridge derives the validator's trust whitelist from unstructured output: `for k in $(repo_known_keys)` is unquoted command substitution (word-split on IFS; `$()`/glob metacharacters in a key are expanded), and every line of `out.stdout` is parsed as `key path` pairs via `line.split(None, 1)`, so any stdout diagnostic from `repo_resolve`/the sourced registry becomes a phantom key in REPO_ROOTS. A malformed or noisy registry silently produces a malformed whitelist (sometimes admitting a key that should not be known) — a supply-chain/robustness regression from the old pure-Python dict lookup to execute-and-parse.
- The central fix lives outside this diff and cannot be verified: base-integrity.sh:64 invokes `$(_vm_ticket_repo_field "$id")` (and the whole STALE-RIG-REF behavior relies on ticket-aware `_vm_repo`/`_vm_refresh`/`verify_merged` in `_lib.sh`), none of which are in the PR's "5 owned files." If the helper is not already deployed, the "repo not found" diagnostic path itself emits a command-not-found and misleads; the diff as submitted cannot establish that the fix works.
- The "Gate is GREEN" claim is unverified and hedged in the PR's own test: (1e) explicitly accepts a non-zero (RED) result on the real fleet dir ("pre-migration copies may linger") while the decision note asserts GREEN. If any surviving fleet script (e.g., preflight.sh or a capability file) still carries a private map, wiring repo-map-single-home.sh as a merge-blocking gate REDs every CI run and blocks all merges. The patterns are also evadable: pattern 1 requires `^REPO_ROOTS\s*=\s*\{` at column 0 (an indented dict inside a function escapes), and pattern 2 requires literal `/home/stack/(code/(charon|keystone)|charon-private)` paths (a map using `$HOME`, relative, or other base paths escapes) — so the drift class REPO-MAP-CONVERGE targets is not actually closed.
- Per-marker `_vm_refresh "$id"` in preflight.sh detect_needs_push (:447) and done_merge_gate (:508) adds a new failure/liveness dependency per marker, yet test (2e) requires rc=0 on a repo with no remote — proving `_vm_refresh` is failure-tolerant, which means a failed fetch silently leaves the stale-ref false-negative the fix claims to eliminate. The tests never exercise the refresh path meaningfully (2c passes because `refs/remotes/origin/master` is pre-seeded), and test (3c)'s else-branch blesses "not GREEN for any reason" as proof of registry-derivation, so a registry-derivation regression can pass while an unrelated RED exists.

## Fail-on-revert check
A revert would restore the hand-maintained dict and id-less _vm_refresh, and the R1–R3 fail-on-revert assertions would catch that — but they cannot catch the silent registry-subprocess fail-closed, the unverified-GREEN/evadable gate, or the out-of-diff `_vm_ticket_repo_field` dependency, so a suite-green revert would re-land the drift invisibly while these regressions go undetected.

## Status
Pending Manager dispensation
