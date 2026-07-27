# ADVERSARIAL REVIEW: d79ac77 — LITELLM-COST-FIELD-TEST

## CALIBRATE (verify-only still true)
Grep confirms ZERO callers of metering.py outside itself — no imports anywhere in src/.
`litellm_cost`, `_cost_from_hidden`, `crosscheck_observation`, `classify_and_crosscheck`
are defined but never called by any production code path. The module docstring still
says verify-only. d79ac77 does NOT change this — it does NOT make this module authoritative
for spend. BalanceTracker + drain-then-park remain untouched.

## COMMIT SCOPE
Only files touched:
- `src/charon/litellm_plane/metering.py` (+3/-2 in _cost_from_hidden, +1/-1 in litellm_cost object branch)
- `tests/test_gw_bridge2_metering.py` (+147 lines: TestHiddenParamsCost class)
Off-limits files (gateway.py, forwarder.py, proxy.py, balance.py): untouched.

## ATTACK RESULTS

### 1. BRANCH EDGE COVERAGE — PASS
Every new test names exactly one branch edge. Coverage:
- hidden present/absent/malformed/genuine-zero — each pinned
- dict and object paths — both tested
- total_cost fallback (object) — separate test
- cost vs total_cost preference — separate test
Not happy-path-twice. Each test has a concrete edge name in its docstring.

### 2. GENUINE $0.00 CASE — PASS
`test_genuine_zero_preserved_via_usage`: _hidden_params.response_cost=0.0 + usage.cost=0.0
→ litellm_cost returns 0.0. Zero is preserved via usage fallback, not lost.
Verified: `assert litellm_cost(obj) == 0.0` passes.

### 3. RED-PROOF (observed, not claimed)
- Zero-sentinel revert (remove `if result == 0.0: return None`): exits broken=1
  → 3 tests go RED: test_zero_response_cost_is_sentinel,
  test_litellm_cost_zero_hidden_falls_back_to_usage_object,
  test_litellm_cost_zero_hidden_falls_back_to_usage_dict
- total_cost fallback revert (object path): exits broken=1
  → 1 test goes RED: test_object_total_cost_fallback
- Full suite restored: exits green=0, 36 passed, 0 failed, 0 skipped

### 4. SCOPE CHECK — PASS
Only metering.py + test_gw_bridge2_metering.py changed. No off-limits files touched.

### 5. DIVERGENCE ALARM STILL FIRES — PASS
`check_divergence` is untouched. test_divergence_beyond_tolerance_logs_warning verifies
a genuine divergence (delta=0.05) still logs COST DIVERGENCE at WARNING level.
The fix quiets false positives without quieting the alarm.

## FINDINGS

### BLOCKING: none

### SHOULD-FIX
`metering.py:68,72` — `float(cost_value or 0.0)` raises TypeError if usage.cost or
usage.total_cost is explicitly None (key exists, value is None/null). Pre-existing
from 6782236, not introduced by d79ac77. Litellm rarely sets these to None and the
_hidden_params path is the primary cost source. Still, a defensive
`if cost_value is not None else 0.0` would eliminate the crash path.

### NIT: none

## VERDICT

**Is d79ac77 safe to land?** MERGE
**Is 6782236+d79ac77 safe to publish as an immutable v0.6.1 image?** RELEASE

The commit does exactly what it claims: pins branch edges that were previously
untested, and stops conflating 0.0 with absent via a sentinel. No evidence of
scope creep, no new production callers, divergence alarm still fires. The one
SHOULD-FIX (None-in-usage crash path) is pre-existing from 6782236 and does not
warrant holding the release.

=== SESSION REPORT v1 ===
TICKET:       LITELLM-COST-FIELD-FIX
SESSION:      kyle-katarn | deepseek-v4-pro
STATUS:       DONE
COMMIT:       d79ac77
FILES:        2 changed: src/charon/litellm_plane/metering.py,tests/test_gw_bridge2_metering.py
OWNS-OK:      yes
GATE:         PASS — zero-sentinel + total_cost fallback correct, scope clean, verify-only intact
TESTS:        36 passed, 0 failed, 0 skipped
RED-PROOF:    broken=1 green=0 — 4 tests go RED on revert (zero-sentinel: 3, total_cost fallback: 1)
OBSERVABLE:   DEFERRED — live gateway cost divergence rate not observable; no live deploy access
RAN:          full test suite (36/36), red-proof revert (4 targeted failures), caller grep (zero production callers)
READ:         prior review 6782236, module docstring (verify-only), off-limits file list, divergence alarm path
BRIEF-ERRORS: referenced handoff file /fleet/handoff-notes/ADVREVIEW-LITELLM-COST-FIELD.md does not exist
BLOCKED-BY:   none
NEXT:         merge d79ac77, cut v0.6.1; then address SHOULD-FIX None-in-usage crash path (metering.py:68,72 pre-existing)
=== END REPORT ===
