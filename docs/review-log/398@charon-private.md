# Review: 398@charon-private
**PR:** docs(PREFLIGHT-OWNS-ARBITRATE): add judgment fragment
**URL:** https://github.com/Nnyan/charon-private/pull/398
**Date:** 2026-08-02T05:15:22Z
**Reviewer:** reviewer-tab-2812490
**Author:** strong-2841812

## Verdict
BOUNCE

## Findings
- The RED this ruling claims to fix does not exist. On the current board (`fix/preflight-owns-arbitrate`), `validate_board.sh` check 4 emits `INFO owns hand-off (dep-sequenced/historical, ok): fleet/preflight.sh <- GATE-INTEGRITY-C MARKER-PROOF-MECHANIZE PREFLIGHT-GATE-REGISTRY PREFLIGHT-GATE-RUN-HELPER RECONCILE-WIRING REPO-MAP-CONVERGE SYNC-SCHEDULE WCI-DEC-FLEET-PREFLIGHT-SH` — GREEN, no RED. The 8 rig-tree owners are already transitively dep-sequenced via the merge-order edges that landed since the ticket was minted (PREFLIGHT-GATE-REGISTRY's depends list, GATE-INTEGRITY-C's and WCI-DEC's depends_on). The ruling's quoted "pre-ruling RED output" is fabricated: the validator keys owns by the literal path string with no normalization (validate_board.sh:401-404), so BENCH-OOB-GRADING's bare `preflight.sh` is a distinct single-owner path and can never appear under `fleet/preflight.sh` — it only produces the `WARN owns-path-missing` the ruling itself quotes. The judgment doc admits the tell: "the observation that the RED was not firing was investigated and resolved." The ruling's predicted post-ruling INFO line is byte-identical to today's actual output, i.e. the fix changes nothing.
- The prescribed edit is destructive and re-enables the silent multi-writer defect the mechanism exists to prevent. MARKER-PROOF-MECHANIZE's real-dep declares its edge to BENCH-OOB-GRADING precisely "to keep preflight single-writer even where the two owns strings do not textually collide" — the board's recorded intent is that BENCH's preflight work be sequenced against the rig tree. Deleting the owns claim silently drops that protection; the ticket's own instructions warn "a wrongly-dropped owns: re-creates the collision silently later." The correct disposition is to re-qualify the token to `benchmark/preflight.sh` or add a depends_on edge to sequence BENCH — not to delete the claim. The "different file" justification rests on a misquote: the ruling renders MARKER-PROOF-MECHANIZE:24-25 as "a DIFFERENT file" when the actual text declares the opposite intent (an ordering edge, confirmed by the validator's own `WCI-ADVISORY justified-disjoint-dep (ok): MARKER-PROOF-MECHANIZE -> BENCH-OOB-GRADING`).
- The DRY-RUN "proof" is not a faithful reproduction of the validator: it hardcodes the 9-owner list and conflates `preflight.sh` with `fleet/preflight.sh`, whereas the validator keeps them as distinct path keys. The claimed "2 unsequenced pairs" and "RED fires: True" cannot arise from the validator's own model. The judgment doc's assertion that "the validator's own ordered() logic was replicated and confirmed" is false on the path model, and the analysis script is "not committed" — evidence is non-reproducible from the repo.
- The PR is inert and scope-misrepresenting: it contains no board edit, only the ruling and judgment docs. Merging it changes nothing on the board, which is already GREEN on `fleet/preflight.sh`. Its sole actionable prescription — removing `preflight.sh` from BENCH-OOB-GRADING's owns — would, if applied by the manager, delete a protective ownership claim with zero benefit and convert a non-problem into a regression. An arbitration ruling that falsifies its premise and quotes evidence in the opposite of its actual meaning is a supply-chain/governance integrity failure, not a merge candidate.

## Fail-on-revert check
Reverting this PR removes the arbitration record while the board edit it prescribes is applied separately by the manager — so the BENCH-OOB-GRADING `preflight.sh` ownership claim is dropped with no justification left in the tree, permanently unguarding the preflight single-writer invariant it was meant to document.

## Status
Pending Manager dispensation
