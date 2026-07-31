# SESSION — DOGFOOD-GATE REWORK (P0): the gate does not fail

**Model:** NON-ANTHROPIC via the Charon gateway. Never Claude/Anthropic. work_class `tests`.
**Repo:** charon (PUBLIC) · **Branch:** `feat/dogfood-gate` — CONTINUE it, do not cut a new one.
**Worktree:** `/home/stack/charon-wt/DOGFOOD-GATE` — exists, at `f0f3666`.

## FIRST ACTS
0. `NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"; echo "claimed: $NAME"`
   Then `session-bridge_register(session_id="<NAME>", name="DOGFOOD-GATE rework", repo="charon",
   ticket="DOGFOOD-GATE", status="in-progress", model="<your model>")`.
   If the lease expires, do NOT renew — **re-register**.
1. `cd /home/stack/charon-wt/DOGFOOD-GATE && git log --oneline -1`  (expect f0f3666)

## WHAT IS WRONG — reproduced by the manager, not theoretical
Your gate PASSES a build containing the exact production bug it was built to catch.

Reproduce it yourself, first thing:
```
cd /home/stack/charon-wt/DOGFOOD-GATE
cp src/charon/proxy.py /tmp/p.bak
sed -i 's/fp4|fp8|fp16/fp8|fp16/' src/charon/proxy.py      # break the fp4 fold
python3 -c "import sys;sys.path.insert(0,'src');from charon.proxy import _normalize_model_id as n;print(n('MiniMaxAI/MiniMax-M2.5-FP4'))"
#   -> prints minimax-m2.5-fp4  (BROKEN; correct is minimax-m2.5)
python3 tools/check_dogfood.py; echo "exit=$?"
#   -> prints "all routing assertions passed", exit 0   <-- THE DEFECT
cp /tmp/p.bak src/charon/proxy.py
```

## WHY THIS IS BLOCKING, NOT A NIT
The ticket's acceptance criterion is verbatim: *"Demonstrate it would have caught the 2026-07-26
miss: show it going RED against a build where the fp4 fold is reverted. This is the acceptance test
for the gate itself."*

This fleet already has four gates that do not gate: `land-push` allowed a push UNVERIFIED-BY-CI,
`done.sh` closed a ticket citing an unrelated PR, `check_inert_code.py` cleared six provably-dead
modules, and now this. **A gate that cannot fail is worse than no gate**, because it reads as
coverage on the merge path. Landing it would install false confidence — the precise harm it exists
to prevent.

## THE FIX
Make the gate assert the OBSERVABLE EFFECT, not the code's self-consistency. The bug it must catch is:
an id that should fold into a pool does not, so a funded provider becomes unreachable and the pool
splits. Concretely, at minimum:
- a real advertised id (`MiniMaxAI/MiniMax-M2.5-FP4`) and its base (`minimax-m2.5`) must resolve to
  the SAME routable pool id; assert on the resolved pool, not on the regex.
- assert NO orphan pool exists for a variant spelling of a model that has a base pool.
- the same shape for the `:low|:medium|:high|:max` capacity tiers and the aistudio `-preview` alias —
  all three were real live strands today.

## PROOF REQUIRED — and it is the whole point this time
- **RED-PROOF #1 (the acceptance test):** run the reproduction above. The gate MUST exit NON-ZERO with
  the fold reverted, and name the fp4 case. Report BOTH exit codes (broken, restored).
- **RED-PROOF #2:** break a second asserted effect (e.g. re-introduce a `:low` orphan) -> RED naming it.
- NON-VACUOUS: with zero pools / empty catalog the gate is RED, never a silent pass. Prove by running.
- Prove it is still INVOKED: paste real `charon.cli gate` output showing `dogfood` execute.
- `PYTHONPATH=src python3 -m charon.cli gate` GREEN and `pytest -q` GREEN on the restored tree.

## OWNS
`tests/e2e/test_dogfood_gate.py`, `tools/check_dogfood.py`, `tools/gates.json`.
`src/charon/gate_runner.py` — you already added the one registration line; that is ACCEPTED (owner
GATE-REENTRANCY-GUARD has been notified). Do not expand your footprint there.
Do NOT modify `src/charon/proxy.py` — revert it exactly as shown after each experiment.

## PREVIOUS RUN DID NOT EMIT A SESSION REPORT
That omission is why this defect reached the manager instead of being caught by your own RED-PROOF
field. Emit the block this time — it is mandatory.

## REPORT BACK — MECHANIZED FORMAT (required)
Validate before finishing: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Spec: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`
```
=== SESSION REPORT v1 ===
TICKET:       DOGFOOD-GATE
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha>
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> — MUST show non-zero on the reverted fp4 fold
OBSERVABLE:   MET | DEFERRED — <why>
RAN:          <proved by EXECUTING>
READ:         <concluded by READING only>
BRIEF-ERRORS: none | <what this brief got wrong>
BLOCKED-BY:   none | <condition>
BUDGET:       ok | TRUNCATED — <what you could not finish and why>
NEXT:         <single next action for the manager>
=== END REPORT ===
```

## LAST STEP
```
git add -A && git commit -m "DOGFOOD-GATE: assert observable pool effects so the gate fails on a broken fold"
```
Do NOT push. **NEVER use `WORK_LEASE_BYPASS=1`.**

## Dependencies & sequence
- **Depends on:** the existing `f0f3666` on this branch — continue it, do not rebase or restart.
- **Concurrency safety:** owns its test + two tools files (unowned). One accepted line in gate_runner.py.
- **Wave:** gate lane, P0.
