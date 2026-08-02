# Review: 214@charon
**PR:** docs(adr-0021): disposition all 52 litellm.Router.__init__ params (ADOPT/DECLINE/DEFER)
**URL:** https://github.com/SLOP-Platform/charon/pull/214
**Date:** 2026-08-02T04:37:42Z
**Reviewer:** reviewer-Tardis-3690908
**Author:** Nnyan

## Verdict
NEEDS-REVISION

## Findings
- Summary counts contradict the disposition table. The ADR table contains ADOPT 26 / DECLINE 12 / DEFER 14 (verified by enumerating all 52 rows; 26+12+14=52), but both the ADR Summary section and ADOPT-MAP's "Full capability disposition" state ADOPT 28 / DECLINE 14 / DEFER 10 and "22 un-scheduled". That makes the claimed backlog wrong: only 20 ADOPT verdicts are un-scheduled (26 − 6 already passed), not 22. The document's entire purpose is to be the authoritative decision register, and its headline arithmetic is wrong — anyone claiming "22 claimable groups" or planning deletion LOC from these counts will misplan. The per-category DECLINE breakdown (7 proxy / 5 policy / 2 duplicate) also does not match the actual 12 declines.
- The drift-guard does not guard the ADR. `tests/test_litellm_capability_map.py` claims to "assert the ADR's param list matches the installed signature," but it hard-codes its own `EXPECTED_PARAMS` duplicate and never reads `docs/adr/0021-*.md`. Editing the ADR table (add/remove/reorder a row) cannot trip any assertion — the two sources of truth drift independently. The guard as shipped can only catch future litellm changes, not present-day or ADR-side corruption, which is exactly the "silent drift" the stated goal claims to prevent.
- Unversioned dependency makes the gate either a global breaker or a no-op. `EXPECTED_PARAMS` is pinned to 1.93.0 (verified accurate) with strict count + exact-order equality, but nothing pins litellm to ==1.93.0 in the dependency spec. Any litellm upgrade that adds/reorders a param turns CI globally RED on main, forcing an emergency re-disposition — while on any CI leg that does not install the `router` extra the test silently skips, so the "must never drift" guarantee is enforced inconsistently. The guard needs either a version pin or a version-scoped expectation, and a non-skipped sanity path.
- Minor: the ADOPT-MAP deletion-table LOC sums to ~1,734 (370+53+65+23+95+14+125+27+28+165+557+99+99), not the stated "~1,650 LOC"; another numeric inconsistency in the same register.
- Not a defect, credit where due: the param list, order, and the security posture (DECLINE of `router_general_settings`, `default_litellm_params`, `ignore_invalid_deployments` protecting egress/base-bound-key controls; money-path flags on the six billing-touching ADOPTs) are correct and match the installed library.

## Fail-on-revert check
Reverting drops the only automated linkage between the 52-param disposition and the installed Router signature, so a litellm upgrade could silently invalidate every ADR-0021 verdict (esp. the money-path ADOPTs) with no signal — while the wrong 28/14/10 counts go unfixed.

## Status
Pending Manager dispensation
