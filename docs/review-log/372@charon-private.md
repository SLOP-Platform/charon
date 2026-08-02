# Review: 372@charon-private
**PR:** design: TOOL-COMPOSITION-LAYER — re-verify on retry, correct measured facts (basic-memory v0.22.1, board census 436/427, absolute-path 52)
**URL:** https://github.com/Nnyan/charon-private/pull/372
**Date:** 2026-08-02T05:08:58Z
**Reviewer:** reviewer-tab-2795881
**Author:** Nnyan

## Verdict
BOUNCE

## Findings
- **MISSING ARTIFACT — `join_probe.py` is referenced in 4 places as the executed probe (`/tmp/opencode/join_probe.py`), yet this file does not exist in the diff and is not in the `owns:` manifest. The ADOPT-NOW verdict for the join shim rests entirely on this script's output. If the upstream removed the script (as noted in line 72: "re-opened after the prior run's upstream was removed"), there is no proof the shim works — only narrative re-statement of its prior output. A docs PR that cannot reproduce its own evidence is not a record; it is an assertion.
- **INTERNAL COUNT INCONSISTENCY — absolute path count drifts by 1 across sections**: the review-log says "52" (line 30/82), the research note says "52" (line 168), but in three places it says "51" (lines 178, 241, 288 row). The difference is material: line 288 is the EVAL-REGISTRY row that becomes the permanent record and the source of truth for future consults — it asserts the edge case is "51 entries" while every other section asserts "52". The correction row (51→52 on line 82) corrected the review-log and research note but the eval-registry row and surrounding prose text were not updated to match.
- **ADOPT-NOW verdict is recorded but no shim is committed**: the PR adopts the join shim in EVAL-REGISTRY and endorses it in the handoff note, but neither the shim itself nor any gate wiring it into CI appears in the diff. The accept bar ("grep count == join count") is described but not enforced. A future PR that implements the shim differently (without normalization) would not be caught by any test from this PR.
- **glob normalization gap acknowledged but not bounded**: the probe output shows "unresolved glob patterns: 4 ('tests/test_gui_*.py (new)', ...)" — glob patterns that match no existing files are silently dropped. The note does not assess whether any `owns:` entries contain such patterns, so the "1,176 concrete files" count could be undercounting due to unresolved globs in production `owns:` fields. This is not a blocker but the count is presented as precise without the uncertainty band.

## Fail-on-revert check
The path-normalization edge case finding (absolute `owns:` silently drops owners; A1-LAND-GATE would be missed) and the graphify-mcp crash verification are the two substantive discoveries — a revert would lose these from the board record, even if the fix is not yet shipped.

## Status
Pending Manager dispensation
