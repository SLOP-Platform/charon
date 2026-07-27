# SESSION — ADVERSARIAL REVIEW: SW-PHASE0-GRADE-READ (dd28aed)

**Model:** NON-ANTHROPIC via the Charon gateway. Never Claude/Anthropic. work_class `design-review`.
**You are the REVIEWER. You did NOT build this. Do not fix, do not commit code.**

## FIRST ACTS
0. `NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"; echo "claimed: $NAME"`
   Then `session-bridge_register(session_id="<NAME>", name="REVIEW SW-PHASE0-GRADE-READ",
   repo="charon", ticket="SW-PHASE0-GRADE-READ", status="in-progress", model="<your model>")`.
   Never reuse a name on the board. If the lease expires, do NOT renew — **re-register**.
1. Read the change: `git -C /home/stack/charon-private-wt/SW-PHASE0-GRADE-READ show dd28aed`
2. Read the ticket: `fleet/board/SW-PHASE0-GRADE-READ.md` (BINDING contract)

## WHAT IT CLAIMS TO FIX
`fleet/capability/grades.py:544-559` required >=3 `strong-control` rows per ref; the scorecard has
**0**, so `_rows_for` dropped every live row and `assign.py` answered `REFUSED — no eligible
candidate` for EVERY ticket. The fix ports the product-side `_is_fallback_admit` (commit `0947401`).

## ATTACK THESE
1. **Is it a faithful PORT or a re-invention?** Diff it against the product original at
   `/home/stack/code/charon/src/charon/capability/grades.py:149`. A DIVERGENCE between the two copies
   is a finding in itself — say which behaviour differs and which is right.
2. **Does it now admit TOO MUCH?** The old rule demanded 3 controls. If the fallback admits rows with
   no control at all, what stops a single lucky run from grading a model A? Find a concrete scenario
   where a model gets a misleadingly high grade. This is the money question — grades drive routing.
3. **Non-vacuity.** The contract required the test to FAIL on an empty ledger. Verify by RUNNING with
   an empty/scratch scorecard, not by reading the test.
4. **Did it touch the DATA?** `fleet/model-scorecard.tsv` is owned by the `bench-grader` unix user for
   anti-gaming reasons. Any diff touching it is out of contract — check.
5. **Red-proof honesty:** re-run it yourself. Report both exit codes you observed, not theirs.

## RULES
- Default to REFUTING. A finding needs a CONCRETE scenario (which model, which rows, what grade).
- Do NOT edit/commit/push. A zero-hit grep is NOT evidence — read the call sites.
- Every finding: `file:line` + scenario + severity (BLOCKING / SHOULD-FIX / NIT).
- Say what you verified by RUNNING vs READING. If nothing is BLOCKING, say so plainly — do NOT
  invent findings.

## ANSWER EXPLICITLY
**"Is dd28aed safe to land?"** MERGE or BLOCK, with reasons. That line is what the operator acts on.

## REPORT
Write to `/home/stack/charon-private/fleet/handoff-notes/ADVREVIEW-SW-PHASE0-GRADE-READ.md`.
Reply: file path + <=10 lines (verdict, counts by severity, most dangerous finding).
