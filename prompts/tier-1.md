Add the tier config store — the foundation of the model-tier abstraction (DTC consensus
"tier = a first-class, gateway-served pool in its own namespace"). Canonical tier for this
ticket: **high** (mapped to fleet `opus` until the abstraction lands). Read
`/home/stack/charon-private/fleet/DTC-tier-abstraction.md` §"Data model — tiers.json" and
§"Where the mapping lives + the resolution contract" FIRST, plus the existing
`src/charon/config.py` (`add_model`/`_save`, lines ~168-230) and `src/charon/types.py`
(`Tier` = `low/med/high`, lines 12-17).

GOAL: Add `load_tiers`/`set_tiers` (atomic `tiers.json` in `config_dir`) + canonical
`low/med/high`, `resolve_tier`, `tier_members`, `tier_rank` (alias-folded, legacy fallback).

DESIGN ANCHORS (cite in your review note):
- ONE canonical vocabulary `low/med/high` (`types.Tier`); `opus/sonnet/haiku` +
  `frontier/strong/economy` are ALIASES only. Canonical keys are FIXED; only `members` and
  `aliases` are operator-editable (so `capacity.FixedCap` keys never desync).
- Data model = a new tiny OPTIONAL `tiers.json` in `secrets.config_dir()`:
  `{ "order": ["low","med","high"], "members": {tier:[model_id,...]}, "aliases": {name:tier} }`.
  `members[tier]` are model ids ALREADY in `models.json` — reuse the registry; NO new model
  schema, NO DB, NO migration runner.
- Absent file → legacy behavior (fall back to `opus/sonnet/haiku`, ranks
  `opus=3 sonnet=2 haiku=1`).

BUILD:
1. src/charon/config.py — EXTEND in place (do not recreate):
   - `load_tiers()` → parsed `tiers.json` (or a legacy default when the file is absent).
   - `set_tiers(order, members, aliases)` — atomic write reusing the existing `_save` pattern
     (`config.py:168-175`).
   - `resolve_tier(name) -> canonical` — alias-folded (case-insensitive); legacy synonyms map
     to canonical; unknown names raise or pass through per the contract.
   - `tier_members(tier) -> [model_id]` — the ordered member list for a (resolved) tier.
   - `tier_rank(name) -> int` — index into `order` (alias-folded); legacy fallback ranks.
   - Determinism: `order` is an explicit list; within-tier order is the stored member order
     (the gateway later applies free-first→cost_rank — NOT this ticket's concern).
2. tests/test_tier_config.py — proven-red: round-trip set/load; absent file → legacy
   default + legacy ranks; `resolve_tier` folds `opus→high`/`strong→med`/etc.; `tier_members`
   returns stored order; `tier_rank` matches `order` index and legacy fallback.

CONSTRAINTS: own ONLY the files in your board ticket's `owns:` line
(src/charon/config.py, tests/test_tier_config.py) — nothing else. config.py already exists:
EDIT it, do not recreate. If your work needs a file outside `owns:`, STOP and run release.sh
with a one-line reason — do NOT create/edit it. Stdlib-only core. Gate green every commit
(pytest, ruff, mypy src tests, check_boundary, check_version). No secrets. Conventional
commits. Write your review note as `docs/review-log/TIER-1.md` (your own fragment — NEVER
append to the shared `docs/REVIEW-LOG.md`). Commit ALL work on your branch and STOP — do NOT
push, do NOT open a PR, do NOT run submit.sh; the launcher publishes after you exit.

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
