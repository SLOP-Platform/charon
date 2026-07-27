# COST-RANK-AUTO — Auto-derive cost_rank from pricing + cost_class enum

## Context
The gpt-5.5 incident root cause (BUG 1): all pool entries tied at `cost_rank:1000` because
ranks were hand-set and never differentiated. Stale list order won. NanoGPT (working,
$12/mo flat) was ranked behind OpenRouter (no credits) and opencode-zen (depleted).

## Operator-approved design (decision #16: design/spec first, then implement)
- Compute `cost_rank` from `cost_input`/`cost_output` (SR-5b's now-real pricing).
- Add a `cost_class` enum: `free-daily`, `expiring`, `prepaid`, `metered`.
- One scalar (cost_rank) cannot express "spend expiring credits first" — cost_class is the
  policy axis, cost_rank is the within-class ordering.

## Spec (write first, then implement)

### cost_class enum
- `free-daily`: free tier with daily reset (groq, cerebras, mistral free models).
- `expiring`: prepaid balance that expires by a date (NeuralWatt 6kWh before 7/22).
- `prepaid`: prepaid balance with no expiry (OpenRouter $10 deposit, NanoGPT $12/mo flat).
- `metered`: pay-as-you-go, no prepaid balance (DeepSeek direct, Together).

### cost_rank derivation
- `cost_rank = cost_input * input_weight + cost_output * output_weight`
- For prepaid flat (NanoGPT $12/mo): effective per-token cost → 0 as usage increases.
  Set `cost_rank = 0` for prepaid-flat providers (they're already paid for).
- For free-daily: `cost_rank = 0` (free).
- For metered: `cost_rank = cost_input + cost_output` (direct per-token cost).
- For expiring: `cost_rank = 0` while balance > 0 (drain it), then `cost_rank = metered
  rate` after balance hits 0.

### Sort order (gateway.py:109-139)
Current: `(not free, cost_rank)`.
New: `(cost_class_priority, cost_rank)` where `cost_class_priority` =
`free-daily=0, expiring=1, prepaid=2, metered=3` (operator decision #2: free-first-then-drain).

## Dependencies & sequence
- depends_on: SR-5b (pricing real), DRAIN-ROUTING (cost_class is DRAIN's ordering primitive).
- Spec first (decision #16), then implement after DRAIN Phase 1 is verified.

## Gate
`PYTHONPATH=src python3 -m pytest tests/test_gateway.py -v -q ; ruff check ; mypy src tests
; python3 tools/check_boundary.py src ; python3 tools/check_version.py`

## REPORT BACK — MECHANIZED FORMAT (required)
End your session by emitting EXACTLY this block. Fixed fields, one line each, no diffs or logs.
Validate it before you finish: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Full spec + rationale: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`

```
=== SESSION REPORT v1 ===
TICKET:       <ticket-id>
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha> | none
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> is owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> | n/a — <why> | NOT-DONE
OBSERVABLE:   MET | DEFERRED — <what could not be observed and why>
RAN:          <what you proved by EXECUTING>
READ:         <what you concluded by READING only>
BRIEF-ERRORS: none | <what this brief got factually wrong>
BLOCKED-BY:   none | <ticket or condition>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
