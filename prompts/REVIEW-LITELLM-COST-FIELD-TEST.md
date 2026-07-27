# SESSION — ADVERSARIAL REVIEW: d79ac77 (RELEASE GATE for v0.6.1)

**Model:** NON-ANTHROPIC via the Charon gateway. Never Claude/Anthropic. work_class `money-path`.
**You are the REVIEWER. You did NOT build this. Do not fix, do not commit code.**

## WHY THIS REVIEW GATES A RELEASE
`d79ac77` on `fix/litellm-cost-field-test` is the last thing standing between this fleet and cutting
`v0.6.1`. Published GHCR tags are **immutable** — whatever ships is permanent for that tag. And the
deploy matters: the live gateway is currently **15+ commits behind master**, so NOTHING merged today
is running anywhere.

## FIRST ACTS
0. `NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"; echo "claimed: $NAME"`
   Then `session-bridge_register(session_id="<NAME>", name="REVIEW LITELLM-COST-FIELD-TEST",
   repo="charon", ticket="LITELLM-COST-FIELD-FIX", status="in-progress", model="<your model>")`.
   If the lease expires do NOT renew — **re-register**.
1. `git -C /home/stack/charon-wt/LITELLM-COST-FIELD-TEST show d79ac77`
2. Read the review it answers:
   `/home/stack/charon-private/fleet/handoff-notes/ADVREVIEW-LITELLM-COST-FIELD.md`

## WHAT IT CLAIMS TO FIX (both from a prior adversarial review of 6782236)
1. **BLOCKING** — the `_hidden_params["response_cost"]` branch had ZERO test coverage.
2. **SHOULD-FIX** — `0.0` was conflated with "missing", so a legitimately-$0.00 request logged
   `COST DIVERGENCE` on every call, saturating an alarm that has previously driven rollback decisions.

## CALIBRATE — do not hunt a money bug that was already refuted
The prior review PROVED this module is verify-only: `litellm_cost` has **zero production callers**, and
authoritative spend runs `forwarder.py -> proxy._model_provider_cost -> BalanceTracker`, untouched.
You are hardening an ALARM, not billing. Confirm that is still true after `d79ac77` — and if the fix
accidentally made this module authoritative for spend, that IS a BLOCKING finding.

## ATTACK THESE
1. **Do the new tests actually pin the BRANCH EDGES**, or do they assert the happy path twice? Name
   each edge: hidden-param present / absent / malformed / genuine-zero.
2. **The genuine-$0.00 case.** A real $0.00 must still be reportable as zero, NOT silently converted
   into a fallback value. Does the sentinel preserve that? Construct the case and run it.
3. **Re-run the red-proofs yourself.** Report the exit codes YOU observed, not the ones claimed.
4. **Did it touch anything outside `metering.py` + its test?** `gateway.py` (4 claimants),
   `forwarder.py`, `proxy.py`, `balance.py` were all off-limits.
5. **Is the divergence alarm still able to fire at all?** A fix that quiets the false positives by
   quieting the alarm is worse than the bug — prove a REAL divergence still logs.

## RULES
- Default to REFUTING. Every finding: `file:line` + concrete failure scenario + severity.
- Do NOT edit/commit/push. A zero-hit grep is NOT evidence — read the callers.
- Say what you verified by RUNNING vs by READING. If nothing is BLOCKING, say so plainly; do NOT
  invent findings to look thorough — on a release gate that costs a real deploy.

## ANSWER EXPLICITLY
**"Is d79ac77 safe to land, and is 6782236+d79ac77 safe to publish as an immutable v0.6.1 image?"**
MERGE/BLOCK plus RELEASE/HOLD. Those two lines are what the operator acts on.

## REPORT
Write to `/home/stack/charon-private/fleet/handoff-notes/ADVREVIEW-LITELLM-COST-FIELD-TEST.md`.
Then emit the SESSION REPORT v1 block (spec: `fleet/SESSION-REPORT-FORMAT.md`; validate with
`bash fleet/check-session-report.sh <file>`).

## Dependencies & sequence
- **Depends on: NOTHING.** Read-only review; owns one report file. Cannot collide.
- **Blocks:** the `v0.6.1` release and therefore the 4-LOM deploy and every deferred live observable.
- **Wave:** release lane, P0.
