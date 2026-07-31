# SESSION — METER-MODEL-PROVIDER: the per-(model×provider) cost/token SENSOR

**Model:** opus (frontier) — this is the critical-path HUB sensor that closes the
cost-aware routing loop (sense → decide → act). Money-path. ADVERSARIAL review before merge.
**Repo:** charon · **Ticket:** METER-MODEL-PROVIDER
**Worktree:** `feat/meter-model-provider` at `/home/stack/code/charon-fleet-METER-MODEL-PROVIDER`
(isolated worktree off latest `origin/master` — do NOT work in the shared tree `/home/stack/code/charon`).

## FIRST ACTS (mandatory)
1. `cd` into the worktree (create off latest `origin/master` if absent).
2. `git fetch origin && git merge origin/master`; resolve conflicts; re-run tests after.
3. Register on the session-bridge (`register`: `repo:"charon"`, `ticket:"METER-MODEL-PROVIDER"`,
   `status:"in-progress"`); heartbeat via `update`.
4. Read the ticket `scope:` block (LOCATED grep of the recording path) — it is authoritative.

## FILES OWNED (touch only these)
- `src/charon/usage_meter.py`  *(NEW — the dedicated per-(model,provider) recorder)*
- `src/charon/balance.py`      *(extend per-provider spend → per-(model,provider) grain)*
- `tests/test_meter_model_provider.py` *(new)*

**Deliberately NOT owned — `src/charon/proxy.py`.** OPENROUTER-FLAKINESS-FIX is the live
single-writer of proxy.py this wave; to run concurrently with it, this ticket must NOT edit
proxy.py. Wire the meter through `balance.py`'s spend path (record the cost the classifier
already computed — `obs.usage.cost_usd` / `cost_source`, see BILLING-EST-COST-FIX). If a
`proxy.py` `record()` call-site hook proves unavoidable, it is a FOLLOW-ON rider folded into the
NEXT proxy.py owner AFTER OPENROUTER merges — flag it in your report, do not co-write proxy.py.

## THE TASK
Add a **sensor** (not a dashboard): record per-(model × provider) INPUT tokens, OUTPUT tokens,
AND cost, on top of today's per-provider spend + the single aggregate token counter.
- New `usage_meter.py`: a small recorder keyed by `(model, provider)` accumulating in/out tokens
  and cost; readable by consumers. Record the SAME cost the attribution path already computed
  (`cost_source` = provider|computed|free|unpriced) — do NOT re-derive pricing.
- Extend `balance.py` so per-provider spend also carries the (model, provider) grain.
- It MUST feed three consumers (they READ this signal; they do not own the meter):
  (a) COST-RANK-AUTO — real `cost_rank` per (model, provider) from metered cost (kills BUG-1:
      all gpt-5.5 tied at cost_rank:1000); (b) FREE-TIER-QUOTA-SPILL / DRAIN-THEN-PARK — per-provider
      spend/quota-remaining balance signal; (c) capability/grades table — cost×quality placement.

### #88 REVIEW CARRY-FORWARD (real per-provider pricing across funding classes) — REQUIRED
BILLING-EST-COST-FIX (PR #88) closed only the `free:true` half of the phantom-spend bug. The open
half: a flat-plan provider that reports an EXPLICIT `cost:0` with NO stored per-token pricing is
classified `unpriced` (proxy.py `_gateway_usage` collapses "no cost field" and "explicit 0" to
`cost_usd==0`) and still hits the est-cost floor (`bytes/4·$1.5e-6`) — re-inflating spend.json
(the ~$223 phantom). The meter MUST record real per-(model,provider) cost across ALL funding
classes so a genuine $0 (flat / free / subscription) is recorded as **$0, not the floor**:
- FREE / FLAT-SUBSCRIPTION ($0 marginal): recorded cost = $0 (never the floor).
- PREPAID (drain-then-park) and PAYG (metered): recorded = the real metered/computed cost.
Do NOT re-introduce the est-cost floor into the metered ledger. (The classifier's explicit-0 vs
absent-cost disambiguation is NORMALIZE-CASE-QUANT-FIX / classifier scope — the meter must not
perpetuate the floor for flat $0, and should key cost by the provider's funding class.)

## ACCEPTANCE (fail-on-revert)
`PYTHONPATH=src python3 -m pytest tests/test_meter_model_provider.py -v -q`
A test asserts per-(model, provider) INPUT tokens, OUTPUT tokens, AND cost are EACH recorded and
readable — not merely per-provider spend + the one aggregate counter. Include a case proving a
flat/free explicit-`cost:0` leg records **$0** (NOT the est-cost floor). Reverting the recorder
fails the assertion.

## MERGE GATE (all green from the worktree)
`ruff` · `mypy` · `PYTHONPATH=src python3 -m charon.cli gate` · `PYTHONPATH=src python3 -m pytest -q`.
Product ships STANDALONE — no `/home/stack`, fleet, SLOP, or runner refs in `src/`/`tests/`/`tools/`.
Anti-dilution: this is a SENSOR wired to the actuators, NOT a standalone usage dashboard, and NOT on
the per-request hot path.

## Dependencies & sequence
- **depends_on:** BILLING-EST-COST-FIX (DONE) — reads its real `cost_usd`/`cost_source`; metering a
  fabricated est_cost defeats the sensor. Real correctness prereq (justified, not merge-order).
- **METER-FIRST is deliberate.** METER precedes DRAIN-ROUTING / COST-RANK-AUTO (the actuators
  consume it). Any older "rebase-after DRAIN-ROUTING/COST-RANK" note was a stale shared-file
  artifact from when DRAIN was expected to write proxy.py first — IGNORE it; the meter lands first.
- **Concurrency:** owns `balance.py` + new `usage_meter.py` — disjoint from OPENROUTER (proxy.py),
  CAPABILITY-ENGINE (gateway/config/providers), TEST-HARDEN (tests/gate). Parallel-safe with all
  Wave-1 lanes. NOT parallel-safe with DRAIN-THEN-PARK (balance.py, later/parked).

## REPORT BACK (short — no diffs)
Files changed, test names, gate pass/fail, commit SHA, and whether a proxy.py call-site rider is
needed (flag for the manager).

## LAST STEP (REQUIRED) — commit, do not skip
```
git add -A && git commit -m "METER-MODEL-PROVIDER: per-(model,provider) token+cost sensor (usage_meter.py + balance.py grain)"
```
Report the commit SHA.

do NOT push, do NOT open a PR, do NOT merge — the launcher publishes; the deny-list blocks push inside the session.

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
