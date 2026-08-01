repo: charon-private
tier: frontier
priority: 0
difficulty: 4
work_class: rig-meta
branch: feat/grade-model-provider-pair
owns: fleet/model-scorecard.sh, fleet/capability/grades.py, fleet/charon-run.sh, fleet/tests/grade-model-provider-pair.test.sh
serial_justified: One schema axis threaded end-to-end — capture (charon-run) -> append (model-scorecard) -> grade (grades.py) -> test. Landing any leg alone writes rows the next leg cannot read.
substrate: N/A
substrate-novel: |
  Nothing external to adopt: this is a schema/key change to OUR OWN append-only ledger and OUR OWN
  grading function, reading a provider id OUR OWN gateway already emits. No library models "this
  rig's scorecard rows must key on (model, provider)".

  Considered under the ADOPT-FIRST lens and genuinely inapplicable, not dismissed:
    * Experiment/eval platforms (MLflow, Weights & Biases, Langfuse, Phoenix) DO model
      run-metadata + per-dimension aggregation, and a real adopt-test of them for the WHOLE
      scorecard/capture stack is a legitimate open question — flagged in CAPTURE-WIRING-TIMEOUT-FIX
      as a candidate. But that is a wholesale substrate replacement, an order of magnitude larger
      than adding one column, and it does not block on this ticket nor this ticket on it. Adding
      the axis now is strictly forward-compatible: any future migration carries a
      (model, provider) key instead of having to invent one from lost data.
    * statsmodels / scipy for the eventual two-factor decomposition — NOT needed yet and
      deliberately NOT added here (see "decomposition" below): with no overlap in the ledger the
      decomposition is unidentifiable, so importing a stats dependency now would be building
      ahead of the data.
depends_on: LEDGER-NO-EVIDENCE-NO-VERDICT
note: |
  OPERATOR DIRECTIVE 2026-08-01: "performance of a model (ex: token per sec) is a grade on the
  PROVIDER not the actual model — that model could be faster on a different provider. The quality
  of work on a model can also be affected by a provider, as different providers offer 'better'
  versions of that model (quantization, hardware they run on, hidden system prompts, API
  defaults)." Refined on push-back: performance is not TOTALLY a provider property either — model
  size/architecture is intrinsic. Both are true; see "decomposition".

  MEASURED STATE 2026-08-01:
    * `model-scorecard.sh append` takes `<model>` and has NO provider field (:51).
    * `capability/grades.py` keys on model x work_class only — its 3 "provider" hits are the
      class name `GradesProvider`, unrelated.
    * The gateway ALREADY emits the serving provider on every response:
        header  `X-Charon-Provider: <name>`
        body    `provider` (e.g. "Baidu" for model deepseek/deepseek-v4-flash)
      `charon-run.sh` reads NEITHER — it logs "upstream provider chosen by gateway" (:205) and
      drops it. The data is on the wire and being thrown away.

  WHY IT IS URGENT NOW: BROKER-BARE-TIER-LEGS (branch pushed, HELD UNMERGED pending this ticket)
  strips provider suffixes from tier-models.tsv so the broker picks the provider. That is correct
  for routing, but those suffixes were the ONLY provider signal reaching the ledger — crude, but
  `deepseek-v4-flash-ds` at least recorded "DeepSeek-direct". With bare ids and no provider
  capture, every future row is provider-BLIND and unrecoverable. Merging bare legs before this
  lands spends the interval writing rows we can never key.

  ROUTING DOES NOT NEED THE DECOMPOSITION. Route on the PAIR: if (minimax-m2.5, opencode-go) is
  slow, avoid that pair — no need to know whether the model or the host is at fault. Separation
  matters for exactly two narrower jobs: (a) cold-start priors for an UNSEEN pair, (b) detecting
  that a provider is DEGRADING a model (the interaction term — quantization/hidden prompts).

  DECOMPOSITION IS NOT IDENTIFIABLE TODAY AND MUST NOT BE FAKED. It needs overlap: the same model
  on >=2 providers AND the same provider serving >=2 models. Verified against the live ledger:
  only `deepseek-v4-flash` appears under two ids and one has a single row — effectively ZERO
  overlap. So this ticket RECORDS the axis and STOPS. Overlap then accrues for free, because
  failover naturally samples one model across providers.

  EXISTING DATA READS DIFFERENTLY UNDER THIS AXIS: the 11 `minimax-m2.5-go` rc=124 timeout rows
  (currently scoring that model -100) are a verdict on opencode-Go SERVING MiniMax M2.5, not on
  MiniMax M2.5. They should re-key onto the pair, never be deleted.
accept: |
  - `model-scorecard.sh append` accepts a provider argument and writes it to a new column;
    validation rejects an empty/missing provider for NEW rows.
  - BACK-COMPAT IS MANDATORY (append-only ledger, 89 existing rows): every legacy row without the
    column reads as `provider=unknown` and its grade is UNCHANGED. A legacy row must never be
    dropped, renumbered, or silently re-scored. Prove with a fixture of real legacy rows.
  - `charon-run.sh` captures the serving provider from the gateway response
    (`X-Charon-Provider` header, falling back to the body `provider` field) and threads it into
    the capture/append path. If neither is present the value is `unknown` — NEVER guessed, and
    never inferred from the model id suffix.
  - `grades.py` grades the PAIR: `model x provider x work_class`, with a model-level roll-up
    retained for tier placement so nothing that reads grades today breaks.
  - Speed/latency signals roll up to the PROVIDER; quality rolls up to the MODEL with a
    per-provider outlier flag. No decomposition/statistics are implemented in this ticket.
  - fail-on-revert tests in fleet/tests/grade-model-provider-pair.test.sh, externally red-proofed
    (assert the fix green AND the revert red, and record both counts in the PR).
  - DOGFOOD: a real routed run records a real provider, and that pair appears in the grade output.
    Not a fixture-only proof.

## Dependencies & Sequence

- **depends_on: LEDGER-NO-EVIDENCE-NO-VERDICT** — collision ordering only (both edit
  `fleet/charon-run.sh`, in disjoint regions); rebase onto its landed version. It BLOCKS
  BROKER-BARE-TIER-LEGS, which is held unmerged for it.
- **Sequence: FIRST in the grading lane.** Real-work grading already functions (verified: 7 of 8
  models graded off the live ledger); it is grading the WRONG KEY. Every run before this lands
  writes another provider-blind row.
- **Blocks / unblocks:** unblocks (a) merging BROKER-BARE-TIER-LEGS, (b) any honest per-provider
  speed signal, (c) the eventual promotion/demotion pass, which must not promote a model on
  evidence that actually belongs to one provider.
- **owns-collision:** `fleet/charon-run.sh` is also owned by LEDGER-NO-EVIDENCE-NO-VERDICT (landing
  now, disjoint region: the `is_infra_fault()` predicate), CAPTURE-WIRING-TIMEOUT-FIX and
  MODEL-HARDCODE-PURGE. Sequence AFTER LEDGER-NO-EVIDENCE-NO-VERDICT lands and rebase onto it.
  `fleet/capability/grades.py` and `fleet/model-scorecard.sh` carry no other live owner.
- **Related, NOT in scope:** the ledger is owned by the `bench-grader` unix user and is read-only
  to manager sessions; any correction of EXISTING rows goes through the grader's append/stage path
  (see fleet/state/scorecard-correct-saba-20260801.sh for the sanctioned shape).
