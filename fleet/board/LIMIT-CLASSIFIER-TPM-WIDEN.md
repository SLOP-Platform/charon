repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: money-path
branch: fix/limit-classifier-tpm-widen
depends_on: CAPTURE-WIRING-TIMEOUT-FIX, MODEL-HARDCODE-PURGE
owns: fleet/charon-run.sh, fleet/tests/limit-classifier-tpm.test.sh
serial_justified: |
  One regex and its fail-on-revert suite, in one file. Splitting the pattern from its test is the
  defect this ticket exists to fix — a classifier whose cases are owned separately drifts, which is
  exactly how the two shapes below fell out of it unnoticed.
substrate: N/A
substrate-novel: |
  The classification itself already exists and is already adopted — this ticket does NOT introduce
  a mechanism, it corrects a live one. `fleet/charon-run.sh:247` already runs a limit-signal regex
  over each failed leg's tail and already routes a match to `led "$M" "limit-failover"`, which
  `dogfood-to-scorecard.sh`'s `classify()` already SKIPs as non-model-attributable. Every moving
  part is in place and working; two provider error shapes simply are not in the pattern.
  No external substrate applies. There is no library of "LLM provider error taxonomies" to adopt:
  the strings are per-provider free text (Groq's TPM ceiling message, DeepSeek's region-opt-in
  message), they are not standardised, and no error-code field carries them — the gateway surfaces
  them only as tail text. LiteLLM-style exception mappers were considered and do not apply here:
  charon-run.sh classifies the TAIL OF A SUBPROCESS (`opencode run`), not an SDK exception object,
  so there is no typed error to map. The novel slice is two additional alternations in a regex that
  already exists plus the anti-over-exempt case, and it is deliberately tiny.
source: |
  MEASURED 2026-08-02 against the live tree and `fleet/state/agent-logs` (380 logs). Every number
  in `accept:` was produced by running the check, not read from a document.
note: |
  ## THE DEFECT — TWO PROVIDER-FAULT SHAPES CHARGED TO THE MODEL
  `fleet/charon-run.sh:247` classifies a failed leg as a provider/session LIMIT only when the
  attempt tail matches this pattern:
  ```
  \b429\b|rate.?limit|quota exceeded|insufficient (funds|credit|balance)|session limit|no capacity|model (is )?(over|exhausted)|out of (credit|quota)
  ```
  A match routes to `led "$M" "limit-failover"` and is explicitly NOT scored against the model. A
  non-match falls through to the generic arm and is recorded as
  `exited nonzero (rc=..., not a limit, not an infra fault)` — a MODEL QUALITY failure.

  Two real, recurring provider faults miss that pattern entirely.

  1. **Groq free-tier token-per-minute ceiling.** Verbatim shape:
     `Request too large for model \`openai/gpt-oss-120b\` ... service tier \`on_demand\` on tokens
     per minute (TPM): Limit 8000, Requested 44225`
     This is a HARD RATE LIMIT. It contains no `429`, no `rate limit`, no `quota exceeded` — it says
     "Request too large" and "tokens per minute". VERIFIED by running the live regex against the
     literal string: NO MATCH.

  2. **DeepSeek region opt-in.** Verbatim shape:
     `The latest version of this model is only available hosted in China and requires explicit opt
     in`
     A PROVIDER CONFIGURATION fault — the leg can never succeed until someone opts the account in.
     VERIFIED against the live regex: NO MATCH.

  ## WHAT WAS AND WAS NOT MEASURED — read this before writing the test
  A prior framing of this defect claimed the limit branch NEVER FIRES and that 100% of failover
  classifications read "not a limit, not an infra fault". **That is FALSE and was disproved here**
  [[confirm-dont-trust-documentation]]: 120 of 380 agent logs contain
  `hit a provider/session LIMIT -> failing over`, led by `minimax-m3-free` (56),
  `deepseek-v4-flash-ds` (24), `deepseek-v4-flash` (22), `minimax-m2.5-go` (21), `glm-5.2` (20).
  The pattern works. It has two SPECIFIC HOLES, and the fix must be a widening — not a rewrite, and
  emphatically not a loosening that exempts everything.

  ## THE COST — A POISONED LEDGER AND A QUARANTINED TICKET
  Two consequences, both money-path:
  - `fleet/model-scorecard.tsv` takes a false BLOCK for a failure the model never caused. The
    scorecard is the live ledger [[scorecard-live-lane-is-the-ledger]], so a provider's free-tier
    ceiling permanently demotes a model that answered correctly every time it was actually given a
    prompt it could hold.
  - via the loop-guard reason, the TICKET is quarantined too — the work is punished for the leg's
    configuration.

  ## THE ANTI-REQUIREMENT — DO NOT OVER-EXEMPT
  The failure mode of this fix is a pattern so wide that every failure becomes "not the model's
  fault", which silently switches the scorecard off. That is strictly worse than the current state:
  a ledger that never blocks is a ledger nobody can use. The done contract below therefore requires
  a case proving a GENUINE model failure still counts against the model. A test that only asserts
  the two new shapes are exempt would pass a regex of `.*`.
accept: |
  MEASURED 2026-08-02 (each figure produced by executing the check against the live tree):
  - `fleet/charon-run.sh:247` carries the pattern quoted in `note:`.
  - Running that exact pattern against the literal Groq TPM string: NO MATCH. Against the literal
    DeepSeek China-opt-in string: NO MATCH. Both therefore fall through to the model-quality arm.
  - `tokens per minute (TPM)` appears in **16** of 380 logs under `fleet/state/agent-logs`;
    `hosted in China and requires explicit opt` appears in **12**.
  - `not a limit, not an infra fault` appears **85** times across **39** logs. Top models charged:
    `deepseek-v4-flash` 17, `free-groq` 14, `gpt-oss-120b-groq` 13, `minimax-m3-free` 13
    (rc=134 x6, rc=1 x4, rc=127 x3), `gpt-5.4-mini` 9.

  DONE CONTRACT — red then green, externally red-proofed:
  a. Widen the limit pattern at `fleet/charon-run.sh:247` to cover the TOKEN-CEILING shape
     (request-too-large / tokens-per-minute / TPM / token limit exceeded) and the PROVIDER
     REGION-OPT-IN shape (requires explicit opt in / only available hosted in <region>). Keep every
     existing alternation — this is additive.
  b. `fleet/tests/limit-classifier-tpm.test.sh` asserts the verbatim Groq TPM string classifies as
     NON-model-attributable (`limit-failover`, not the generic arm).
  c. Same test asserts the verbatim DeepSeek China-opt-in string classifies as NON-model-attributable.
  d. ANTI-OVER-EXEMPT, the case that matters most: a genuine model failure tail (a plain nonzero
     exit with ordinary error output carrying none of the limit tokens) still classifies as
     model-attributable and still reaches the scorecard. Reverting only the widening must turn (b)
     and (c) RED while (d) stays GREEN; a widening that turns (d) green as well is a regression and
     the test must catch it.
  e. FAIL-ON-REVERT, reported both ways: revert the widened alternations, show (b) and (c) RED;
     restore, show all four GREEN. Registration is not proof — the guard must be SEEN to fail
     [[gates-must-actually-run]].
  f. Hermetic. No live gateway call, no network. Feed fixture tails through the classifier directly.
  g. `bash fleet/validate_board.sh` GREEN.
scope: |
  The limit-signal classifier at `fleet/charon-run.sh:247` and its new test only. Does NOT touch
  `dogfood-to-scorecard.sh` (its `classify()` already SKIPs `provider-*` correctly — the bug is
  upstream of it, in what gets labelled a provider fault in the first place). Does NOT change tier
  chains — a leg that can never serve our prompt size is a CHAIN-COMPOSITION defect and belongs to
  FREE-TIER-PROMPT-SIZE-FIT, not here. Does NOT rewrite the existing alternations.

## Dependencies & Sequence

- **depends_on: `CAPTURE-WIRING-TIMEOUT-FIX` — a SEQUENCING dependency, not a build prereq.** The
  change itself needs nothing to land first: it is one regex and one hermetic test. The dependency
  exists because `fleet/charon-run.sh` is contended — `CAPTURE-WIRING-TIMEOUT-FIX` and
  `GRADE-MODEL-PROVIDER-PAIR` both own it and are both LIVE, and `CAPTURE-WIRING-TIMEOUT-FIX`
  already depends on `GRADE-MODEL-PROVIDER-PAIR`. Declaring this ticket downstream of
  `CAPTURE-WIRING-TIMEOUT-FIX` therefore orders it after BOTH transitively, which is what makes the
  three safe to schedule [[disjoint-owns-not-no-dependency]]. **If the contended file is freed
  earlier — either of those two lands, or a manager re-sequences — this ticket can run immediately;
  nothing in its diff waits on their content.**
- **This is a P0 sitting behind two tickets, and that is a real cost worth surfacing.** Every hour
  it waits, `fleet/model-scorecard.tsv` accrues more false BLOCKs. If the queue is long, the right
  move is to re-sequence the contended file in this ticket's favour rather than to let the ledger
  keep poisoning — that is a manager decision, recorded here so it is a choice and not an accident.
- **Pairs with `LOOP-GUARD-REASON-WIRE` — EITHER ORDER, not a build prereq.** That ticket makes the
  failure REASON reach the loop guard; this one makes the reason CORRECT. Wired-but-wrong and
  right-but-unwired are each half a fix, and neither blocks the other's build
  [[disjoint-owns-not-no-dependency]]. They own different files and cannot conflict.
- **Sibling, do NOT fold in: `FREE-TIER-PROMPT-SIZE-FIT`.** That ticket removes legs that can never
  hold our prompt from the work chains. This one stops mis-charging the model when such a leg
  fails. Both are needed: even with the chains corrected, a provider can introduce a new ceiling at
  any time and the classifier must not blame the model for it. Disjoint owns.
- **owns-collision: `fleet/charon-run.sh` is the collision risk.** Verified against the live board
  before claiming; any ticket that also edits it must be sequenced, not run in parallel.
  `fleet/tests/limit-classifier-tpm.test.sh` is a NEW path owned by nobody.
- **Sequence: NOW, ahead of any further scorecard-driven promotion or demotion.** Every hour this
  is open, the live ledger accumulates BLOCKs that are not the models' doing, and those entries are
  what future routing decisions read [[always-fix-catalog-mismatches]].
- **Blocks / unblocks:** unblocks trustworthy model grading off real work
  [[model-grading-prelim-then-real-work]] — the ledger cannot rank models while provider faults are
  scored as model quality.
