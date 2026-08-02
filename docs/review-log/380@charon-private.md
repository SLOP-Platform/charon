# Review: 380@charon-private
**PR:** feat(FORCE-PUSH-SAFETY-GATE): --force must PROVE it destroys nothing — fail-on-revert gate spec
**URL:** https://github.com/Nnyan/charon-private/pull/380
**Date:** 2026-08-02T05:21:40Z
**Reviewer:** reviewer-tab-2795881
**Author:** Nnyan

## Verdict
NEEDS-REVISION

## Findings
- Fail-open on indeterminate: `git fetch ... || true` + `rev-list ... || orphans=""` turns any fetch/rev-list error into `count=0` → the gate PROCEEDS and force-pushes with no proof. The near-miss would have been destroyed on a network flake. Refuse (fail-closed) or at minimum warn-and-abort when safety cannot be established; "branch absent" and "cannot determine" must not share a return path.
- TOCTOU / no lease: gate inspects `remote_sha` via ls-remote then pushes plain `--force`. A concurrent push between check and push is clobbered un-inspected. Push with `--force-with-lease=<remote_sha>` so the ref-change applies only if the remote still equals the sha that was audited.
- Goal not delivered: the gate is not wired into `land-push.sh`/`rescue-push.sh` (owns-enforced, but the ticket's promise is unmet) — after merge the 20th-incident remains fully reproducible in production, and the reference implementation ships F1/F2 for future wiring to inherit. The ticket must remain open / be split until the production path calls `fps_gate_check`.
- Anti-over-block promise is incomplete: reachability-only comparison false-refuses legitimate rescues where remote work was replicated locally under rewritten shas (rebase/squash/cherry-pick) → `count>0`. Content/reachability equivalence is not detected, so the "19 rescues keep working" guarantee only holds for the literal-identical-history shape.
- Verification caveat: the diff shows `\"` on every quote (likely transport escaping, but verify the committed file does not literally contain backslash-quoted strings); and `git init -b` requires git ≥ 2.28, empty `--force-with-destroy=` silently degrades to plain `--force`, and `git show --stat | tail -1` is fragile for non-additive commits.

## Fail-on-revert check
A revert would drop the 13-assertion fail-on-revert suite pinning the `grep -c .` count fix (empty-orphan anti-over-block) and the refusal/override contract — but since the gate is never wired into the push path, production `--force` remains ungated either way.

## Status
Pending Manager dispensation
