# REVIEW-WORKLOOP-ATTEMPT3 — Adversarial Verdict

**Reviewer:** mace-windu (independent, did NOT author PR #179)
**PR:** #179 (`feat/workloop-stack-spike-run` → `master`)
**Date:** 2026-07-23
**Scope:** NARROW — attempt-2's bounce-fix items only (adnanh/webhook trial, pydantic/cerberus trial, separate-commit provenance)

---

## Item 1: adnanh/webhook trial REAL? ✅

**Ground-truth on 4-LOM (10.0.1.60, `ssh -i ~/.ssh/4lom stack@10.0.1.60`):**

| Artifact | Path | Status |
|---|---|---|
| Binary | `/tmp/webhook-bin` (12,929,444 bytes, `webhook version 2.8.3`) | EXISTS |
| Hooks config | `/tmp/wltrial/hooks.json` (488 B, value trigger-rule on ref) | EXISTS |
| HMAC hooks | `/tmp/wltrial/hooks-hmac.json` (622 B, payload-hmac-sha1 + value) | EXISTS |
| CI gate script | `/tmp/wltrial/ci-gate.sh` (532 B, build → fail→retrigger loop) | EXISTS |
| Receiver | `/tmp/wltrial/receiver/server.py` (946 B, BaseHTTPRequestHandler on :9090) | EXISTS |
| CI gate log | `/tmp/wltrial/ci-gate.log` (560 B, 3 trials: BUILD_OK rc=0, BUILD_FAIL rc=7 ×2) | EXISTS, real output |
| Retrigger log | `/tmp/wltrial/retrigger.log` (128 B, 2 retrigger events) | EXISTS, real output |
| Events log | `/tmp/wltrial/receiver/events.log` (283 B, 3 POSTs: /test + 2×/retrigger with payload) | EXISTS, real output |
| Transcript dir | `/tmp/wltrial/transcript/` (setup, hooks, ci-gate, receiver, run script, observed logs) | EXISTS |

**ao §1.3 re-ranking verified from PR diff:** adnanh/webhook LEADS (#1 ADOPT EXECUTED), Windmill #2, hand-roll moved to after-adopt-disproven fallback. The hand-roll is no longer ranked #1.

**Verdict: REAL.** Trial artifacts exist, show real executed runs (timestamps, host, commands, observed output — not source citations). The adopt-first ranking is corrected.

---

## Item 2: pydantic/cerberus trial REAL? ✅

**Ground-truth on 4-LOM:**

| Artifact | Path | Status |
|---|---|---|
| pydantic version | `python3 -c "import pydantic; print(pydantic.__version__)"` → `2.13.4` | INSTALLED |
| cerberus version | `python3 -c "import cerberus; print(cerberus.__version__)"` → `1.3.8` | INSTALLED |
| DoD schema | `/tmp/wltrial/pydtrial/dod_schema.py` (4313 B, TicketFrontmatter BaseModel + CerbValidator) | EXISTS, runs |
| fx_valid.yaml | `/tmp/wltrial/pydtrial/fx_valid.yaml` (valid ticket) → ALLOW both engines | ✅ |
| fx_missing_field.yaml | `/tmp/wltrial/pydtrial/fx_missing_field.yaml` (no `branch`) → DENY both engines | ✅ |
| fx_bad_type.yaml | `/tmp/wltrial/pydtrial/fx_bad_type.yaml` (`tier: 999`, `owns: str`) → DENY both engines (both errors caught) | ✅ |
| fx_bad_workclass.yaml | `/tmp/wltrial/pydtrial/fx_bad_workclass.yaml` (unknown `work_class`) → DENY both engines | ✅ |
| fx_money_no_test.yaml | `/tmp/wltrial/pydtrial/fx_money_no_test.yaml` (money-path without test in owns) → ASK both engines | ✅ |
| Transcript dir | `/tmp/wltrial/pydtrial/transcript/` (contains observed output) | EXISTS |

**Archon §4.3 re-ranking verified from PR diff:** pydantic LEADS (#1 ADOPT EXECUTED), cerberus #2 (ADOPT EXECUTED, alternate), hand-roll moved to after-adopt-disproven fallback. The hand-roll is no longer ranked #1.

**Verdict: REAL.** All 5 fixtures run through both engines, produce correct tri-state (ALLOW/DENY/ASK) verdicts matching the doc's matrix. The adopt-first ranking is corrected.

---

## Item 3: EVAL-REGISTRY provenance (separate commits) ✅

**Verified on PR branch (`feat/workloop-stack-spike-run`):**

```
89320e6 design(workloop-integrity): re-rank ao seam adopt-first — execute adnanh/webhook trial, demote hand-roll to after-adopt-disproven fallback
d89a0ef design(workloop-integrity): re-rank Archon approval-gate seam adopt-first — execute pydantic+cerberus trials, demote hand-roll to after-adopt-disproven fallback
```

| Claim | Commit | Status |
|---|---|---|
| ao seam in separate commit | `89320e6` | ✅ |
| Archon seam in separate commit | `d89a0ef` | ✅ |

**Verdict: CONFIRMED.** Two separate commits as claimed.

---

## Additional adversarial checks

### Hand-roll is NOT ranked #1 anywhere ❌→✅ (corrected)
- §1.3: adnanh/webhook #1 (ADOPT, EXECUTED) — hand-roll is after-adopt-disproven fallback
- §4.3: pydantic #1 (ADOPT, EXECUTED) — hand-roll is after-adopt-disproven fallback
- §3 (Windmill) and §2 (Omnigent) were already adopt-led in attempt 2 and left unchanged
- No hand-roll is ranked #1 in any remaining layer

### Omnigent (§2) and Windmill (§3) left unchanged — acceptable
Per the ticket scope, attempt 2's four trials (ao/Omnigent/Windmill/Archon) were verified real; only the two bounce-fix items needed re-litigation.

### PR state: OPEN, base master, branch feat/workloop-stack-spike-run ✅

---

## VERDICT: APPROVE-FOR-OPERATOR

**Summary:**
- [✅] adnanh/webhook trial: REAL (all artifacts exist, show real run output)
- [✅] pydantic/cerberus trial: REAL (all 5 fixtures produce correct verdicts on both engines)
- [✅] EVAL-REGISTRY provenance: separate commits confirmed (89320e6 + d89a0ef)
- [✅] Hand-roll no longer ranked #1 anywhere (corrected to after-adopt-disproven fallback)

The attempt-2 bounce is fixed. The claims in the PR prose match ground truth on 4-LOM. No gap found. The operator may merge after their own review.
