# POOLS-SIMPLIFICATION — Replace 50 per-model pools with sparse overrides + default chain

## Context
The gpt-5.5 incident showed that 50 hand-maintained per-model pools accreted inconsistent
manual orders. Some have NanoGPT-primary (deepseek-v4-pro, after manual fix), others have
stale -or-first order (gpt-5.5). POOLS-EDIT-PLAN.md explicitly preserved the broken
gpt-5* order.

## Sub-session recommendation (approved, decision #9)
Replace 50 per-model pools with sparse overrides + existing tiers.json/fallback.json as
default draw-down chain. Keep explicit pools ONLY where routing policy differs from
"exact model then default fallback":
- `auto` (cross-model cheap/default pool).
- Free-tier virtual IDs (`*-free`).
- `deepseek-v4-pro` (until request-normalizer lands — non-DeepSeek exclusion).
- `gpt-5.5`, `gpt-5.4-pro` (OpenRouter-first behavior for opencode terminal 400).
- Pinned operator IDs whose provider order is intentionally non-default.

Everything else: delete from pools.json, serve as exact model route + default fallback.

## Migration plan
1. Backup live `/data/{models,pools,providers,secrets}.json`.
2. Land DRAIN-ROUTING + COST-RANK-AUTO first (default chain must exist).
3. Shrink `pools.json` to sparse overrides only.
4. Keep all concrete aliases in `models.json`; do not remove pinned IDs.
5. Verify route snapshots before/after for: `auto`, `deepseek-v4-pro`, `gpt-5.5`,
   `gpt-5.4-pro`, all `*-free`, representative pinned Claude/Gemini/Kimi/GLM IDs.
6. Deploy with pool-count decrease expected.
7. Update deploy checks so they assert required route behavior, not `pool count == 50`.

## Dependencies & sequence
- depends_on: DRAIN-ROUTING, COST-RANK-AUTO (default draw-down chain must exist first).

## Gate
`PYTHONPATH=src python3 -m pytest tests/test_gateway.py -v -q ; ruff check ; mypy src
tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`

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
BUDGET:       ok | TRUNCATED — <what you could not finish and why>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
