# SESSION — ADVERSARIAL REVIEW: SW-IDENTITY-FOLD (money/routing path)

**Model:** a NON-ANTHROPIC model through the Charon gateway (`opencode --model charon/<model>`).
Never Claude/Anthropic. Graded sample, work_class `design-review`.
**You are the REVIEWER. You did NOT build this.** Do not fix anything. Do not commit code.

## YOUR JOB
Attack `46eab38` on branch `fix/sw-identity-fold` (worktree
`/home/stack/charon-wt/SW-IDENTITY-FOLD`). This gates its merge. The ticket
(`/home/stack/charon-private/fleet/board/SW-IDENTITY-FOLD.md`) demands adversarial review because
routing identity is a **money path**: a wrong fold merges two genuinely different models into one
pool, which is WORSE than the orphan pool it was fixing — traffic silently gets a different model
than it asked for, and the bill and the quality both move.

**Default to REFUTING.** A finding is only real if you can state a CONCRETE FAILURE SCENARIO:
specific model ids, which provider serves them, what the caller asked for, what they would get
instead. "This looks risky" is not a finding. Neither is a verdict without a scenario.

## FIRST ACTS
0. **Claim your session name MECHANICALLY — do not invent one.** Names collide when models pick
   them; use the allocator (atomic, claim-before-build):
   ```
   NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"
   echo "claimed: $NAME"
   ```
   Then `session-bridge_register(session_id="<the claimed NAME>", name="ADVERSARIAL REVIEW SW-IDENTITY-FOLD", repo="charon",
   ticket="SW-IDENTITY-FOLD", status="in-progress", model="<your model>")`.
   **Never reuse a name you see on the board — those sessions are LIVE.**
   Then `session-bridge_update` every ~5 min as a HEARTBEAT (600s lease, else you are purged).
1. Read the change: `git -C /home/stack/charon-wt/SW-IDENTITY-FOLD show 46eab38`
2. Read the ticket and `docs/adr/0011-the-switchboard-demand-routed-no-pools.md` (INV-SW1/2/3).
3. Read the LIVE catalog — the real corpus, not the test's:
   `/data/models.json` on the gateway host via the charon status surface, or the committed catalog in
   the product tree. Your best findings will come from ids that EXIST but are not in the test corpus.

## ATTACK THESE SPECIFICALLY (the builder's own dispositions)
It FOLDED: `fp4 fp8 fp16 fp32 bf16 int8 int4` (precision), `nvfp4 mxfp4` (stacked quant),
**`awq gptq w8a8` (quantization METHODS)**, GGUF `q*` forms, and `:free :nitro :online` (deployment
tiers). It did NOT fold: `:thinking :reasoning` and `-turbo -fast -instruct -latest -preview -hf`.

1. **`awq` / `gptq` / `w8a8` are the weakest link — start here.** These are not precision tags, they
   are quantization METHODS producing weights that can measurably differ in quality from the base
   model. Is folding them into the base pool defensible? Find a real id pair in the live catalog
   where this fold would route a caller to different weights than requested. If you can, that is a
   CONFIRMED money-path defect.
2. **`:free` folded into the base pool.** A `:free` variant often has different rate limits, context,
   or quality than the paid one. Folding means a request for the paid id can be served by the free
   deployment (or vice-versa). Cost and reliability both change. Real scenario?
3. **The blanket non-fold of six suffixes on one example.** `gpt-4` vs `gpt-4-turbo` justifies
   `-turbo`. Does it justify `-latest` and `-hf`? Is anything ELSE stranded the way the aistudio
   `-preview` ids were (a funded provider whose ids never join the pool)? Search the live catalog for
   stranded families — that is the INV-SW2 class and it is release-blocking.
4. **Order dependence.** Quant, marketing and mode suffixes are stripped in sequence inside a loop.
   Find an id where the ORDER changes the result, or prove order-independence. Stacked forms like
   `-awq-fp16` or `:free` after a quant tag are the place to look.
5. **Over-folding two REAL models into one id.** The nightmare case. Try to construct it from ids that
   actually exist.
6. **Is the corpus honest?** 38 entries. Does it contain the hard cases, or only ids that pass? A
   corpus that tests what the regex already does is theater. Name what it should contain and doesn't.

## RULES
- **Do NOT edit code, do NOT commit, do NOT push.** You produce findings only.
- A zero-hit grep is NOT evidence of absence — read the code and the catalog.
- Every finding: `file:line` + concrete failure scenario + severity (BLOCKING / SHOULD-FIX / NIT).
- Say explicitly what you verified by RUNNING vs by READING.
- If after real effort you find nothing BLOCKING, say so plainly and state what you attacked and how.
  A clean review that names its attack surface is a valid and useful outcome — do NOT invent findings
  to look thorough. Manufactured findings are worse than none.

## REPORT BACK
Write findings to `/home/stack/charon-private/fleet/handoff-notes/ADVREVIEW-SW-IDENTITY-FOLD.md`.
Your reply: the file path + a <=10-line summary — verdict (MERGE / BLOCK), count by severity, and the
single most dangerous finding. No diffs, no code dumps.

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
