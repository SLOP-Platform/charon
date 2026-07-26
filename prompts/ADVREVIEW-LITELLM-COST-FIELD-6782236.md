# SESSION — ADVERSARIAL REVIEW: 6782236 metering change (RELEASE GATE, money path)

**Model:** a NON-ANTHROPIC model through the Charon gateway. Never Claude/Anthropic.
Graded sample, work_class `money-path`.
**You are the REVIEWER. You did NOT build this. Do not fix anything. Do not commit code.**

## WHY THIS REVIEW EXISTS — it gates an IMMUTABLE release
Commit `6782236` is HEAD of product master and is about to be published as GHCR tag `v0.6.1`.
Published tags are **immutable — never overwritten, never re-pushed**. If this code is wrong, the bad
image is permanent and only another release can replace it.

The commit is `chore(LITELLM-COST-FIELD-FIX): launcher auto-commit — droid exited without committing
(review for completeness)`. Read that literally: a droid **exited without committing**, the launcher
swept the working tree into a commit, and the message itself asks for a completeness review. It
merged as PR #190 with **0 reviews and 0 review comments**. Nobody has ever read this code.

It changes `src/charon/litellm_plane/metering.py`, +41/-4 — **billing code**.

## CONTEXT YOU NEED (verified, do not re-derive)
This gateway has a live history of metering being wrong in exactly this area:
- `fd03840 fix(gateway): stop booking energy_kwh 1:1 as USD (money bug)` — energy units billed as
  dollars.
- The live gateway currently reports `cost_usd = $0.000704` against **252,724,415 input tokens**, and
  `remaining_usd: null` for every provider. The meter is effectively inert or wrong TODAY.
So "the metering code has a units/None/zero bug" is not a hypothetical here — it is the base rate.

## FIRST ACTS
0. **Register** — `session-bridge_register(session_id="<UNUSED Jedi name; kit-fisto, qui-gon-jinn,
   mace-windu, rey-skywalker taken>", name="ADVREVIEW LITELLM-COST-FIELD", repo="charon",
   ticket="LITELLM-COST-FIELD-FIX", status="in-progress", model="<your model>")`.
   **`session-bridge_update` every ~5 min as a HEARTBEAT** (600s lease or you are purged).
1. `cd /home/stack/code/charon` is the MANAGER's checkout — do NOT work there. Use a read-only view:
   `git -C /home/stack/code/charon show 6782236` and
   `git -C /home/stack/code/charon show 6782236 -- src/charon/litellm_plane/metering.py`
   You are reviewing, not editing, so no worktree is required. Do not create branches.

## ATTACK THIS — a droid abandoned it mid-task, so assume it is INCOMPLETE
1. **Is it finished?** A droid exited without committing. Look for the signature of abandonment:
   a helper defined but never called, a branch that returns early, a TODO, a field read but never
   written, an import added for code that is not there, half-updated call sites.
2. **Units.** Every cost/usage field: what unit does the SOURCE provide, what unit does the SINK
   expect? Name each field and its unit. The `energy_kwh`-as-USD bug was exactly this and shipped.
3. **None / zero / missing-field handling.** What happens when the upstream response omits the cost
   field? Silently books 0? Books None? Raises? A meter that silently books 0 is INDISTINGUISHABLE
   from a working meter until the bill arrives — and the live meter is reporting near-zero right now.
4. **Double-billing / no-billing.** Can one request be metered twice (retry, failover leg, streaming
   chunk + final)? Can a failover leg go unmetered? This gateway fails over between providers
   routinely, so both paths are live.
5. **Does it agree with the other meter?** There are two metering surfaces (the proxy's
   `_model_provider_cost` and the litellm plane). If they disagree, which one bills?
6. **Test coverage.** Does any test exercise the changed lines? A money change with no test is a
   BLOCKING finding on its own.

## RULES
- **Default to REFUTING.** A finding is real only with a CONCRETE FAILURE SCENARIO: specific input,
  specific field, what gets booked vs what should be. "Looks fragile" is not a finding.
- **Do NOT edit, commit, or push.** Findings only.
- A zero-hit grep is NOT evidence of absence — read the file and its callers.
- Every finding: `file:line` + failure scenario + severity (BLOCKING / SHOULD-FIX / NIT).
- Say what you verified by RUNNING vs by READING.
- If you find nothing BLOCKING after real effort, say so plainly and state what you attacked. Do NOT
  invent findings — a manufactured finding on a money path is worse than none.

## THE QUESTION YOU MUST ANSWER EXPLICITLY
**"Is 6782236 safe to publish as an immutable release image?"** Answer RELEASE or HOLD, with reasons.
That single line is what the operator acts on.

## REPORT BACK
Write findings to `/home/stack/charon-private/fleet/handoff-notes/ADVREVIEW-LITELLM-COST-FIELD.md`.
Your reply: the file path + <=10 lines — RELEASE/HOLD, counts by severity, and the single most
dangerous finding.
