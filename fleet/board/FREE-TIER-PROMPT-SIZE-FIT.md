repo: charon-private
tier: strong
priority: 1
difficulty: 3
work_class: routing
branch: feat/free-tier-prompt-size-fit
owns: fleet/checks/chain-prompt-size-fit.sh, fleet/tests/chain-prompt-size-fit.test.sh, fleet/state/chain-prompt-floor.tsv
serial_justified: |
  One admission rule, one measurement it reads, one fail-on-revert suite. The measurement and the
  rule cannot be split: a floor measured by one owner and enforced by another is how the two drift
  apart, and a stale floor silently re-admits the very legs this refuses.
substrate: N/A
substrate-novel: |
  Checked what already exists in-tree and what is available outside before proposing a new check.
  Nothing covers CONFIG-TIME ADMISSION of a chain leg by prompt-size capacity.
  In-tree: `fleet/state/FREE-TIER-LIMITS.tsv` is the closest relative and it is the reason this
  cannot simply be a table lookup — its row for `free-groq|deepseek-v4-pro-groq|gpt-oss-120b-groq`
  is literally suffixed `_MISMATCH_UNRECONCILED` with rpd/rpm/tpm/tpd/context_cap all
  `unpublished`. The SSOT cannot currently answer "what is this leg's token ceiling", so the rule
  has to be able to seed itself from what the PROVIDER reports and then hold that as the floor.
  `fleet/checks/` holds no size-fit or capacity-fit check of any kind (verified by listing it).
  `LIMIT-CLASSIFIER-TPM-WIDEN` fixes ATTRIBUTION after the failure; it does not prevent the leg
  from being in the chain. `BROKER-BARE-TIER-LEGS` owns `fleet/tier-models.tsv` and is about bare
  legs, not capacity.
  Outside: token counters (tiktoken and equivalents) MEASURE a prompt, and every router/proxy we
  evaluated (LiteLLM-class routing, OpenRouter-class fallback lists) treats a capacity refusal as a
  RUNTIME event to fail over from. None of them refuse a leg AT CONFIG TIME for being structurally
  incapable of the caller's floor prompt. A counter is a useful dependency for step 1 of the done
  contract and is not the novel part. The novel slice is the ADMISSION RULE — chain membership
  gated on a measured floor, refused loudly before dispatch rather than discovered on every claim.
source: |
  MEASURED 2026-08-02 against the live tree and `fleet/state/agent-logs`. Provider error text
  quoted below is verbatim from logs on this box, not from documentation.
note: |
  ## THE DEFECT — LEGS IN THE WORK CHAIN THAT CAN NEVER SERVE A TICKET
  `fleet/tier-models.tsv` line 90 defines the live `strong` chain:
  ```
  strong	minimax-m2.5-go,deepseek-v4-flash-ds,gpt-oss-120b-groq,free-groq,minimax-m3-free,deepseek-v4-flash
  ```
  Three of those six legs are structurally incapable of accepting a real ticket:
  - `gpt-oss-120b-groq` and `free-groq` sit behind a Groq free-tier TOKEN-PER-MINUTE ceiling. The
    provider's own refusal, verbatim from our logs, states the numbers: `service tier \`on_demand\`
    on tokens per minute (TPM): Limit 8000, Requested 44225`. Our launcher's join prompt is roughly
    **5.5x over what the leg is allowed to accept**. There is no prompt we could realistically send
    that fits.
  - `deepseek-v4-flash` returns `The latest version of this model is only available hosted in China
    and requires explicit opt in` — a provider-account configuration the leg cannot satisfy on its
    own, so it fails identically every time.

  ## WHY THIS IS A COMPOSITION DEFECT, NOT A BUG
  Nothing is malfunctioning. Each component does exactly what it was built to do: the chain tries
  its legs in order, the leg refuses, failover moves on. The defect is in the SHAPE OF THE CHAIN —
  it contains members that can never discharge its purpose. A leg whose hard limit is BELOW our
  floor prompt size is not a fallback, it is a guaranteed wasted round: a chain slot consumed, a
  failover hop spent, and a log line to read, on every single claim, forever.

  ## THE COST COMPOUNDS WITH THE ATTRIBUTION BUG
  Measured across 380 logs in `fleet/state/agent-logs`: the token-ceiling shape
  (`tokens per minute (TPM)`) appears in **16**, the region-opt-in shape
  (`hosted in China and requires explicit opt`) in **12**. Those same models lead the
  misattribution table — `deepseek-v4-flash` 17, `free-groq` 14, `gpt-oss-120b-groq` 13 occurrences
  of `not a limit, not an infra fault`. So today the fleet pays twice: once in the wasted round,
  and again in a false model BLOCK on the live ledger. `LIMIT-CLASSIFIER-TPM-WIDEN` stops the
  second cost. Only this ticket stops the first.

  ## THE RULE
  **A leg may not be admitted to a work chain unless it can accept the floor prompt the launcher
  actually emits.** Refusal happens at CONFIG TIME, with a loud, specific reason naming the leg,
  its ceiling, and the measured floor — never as a runtime discovery on the Nth claim.

  ## WHY THIS MUST BE MEASURED, NOT TABULATED
  `FREE-TIER-LIMITS.tsv` marks the Groq row `_MISMATCH_UNRECONCILED` with every limit
  `unpublished`. A rule that trusts that table would admit all three legs today and would keep
  admitting them. The floor must come from measuring what the launcher emits, and the ceiling must
  be recorded from the provider's own reported limit when the table has none
  [[confirm-dont-trust-documentation]].

  ## DO NOT SILENTLY DROP
  Refusing a leg quietly recreates the problem one level up — a chain that shrinks without saying
  why is indistinguishable from a chain that was configured that way. The refusal must be loud and
  it must name the number, so the next person can tell "this leg cannot hold our prompt" apart from
  "someone removed this leg".
accept: |
  MEASURED 2026-08-02 (executed, not read):
  - `fleet/tier-models.tsv:90` — the live `strong` chain contains `gpt-oss-120b-groq`, `free-groq`
    and `deepseek-v4-flash` as quoted in `note:`.
  - Groq's verbatim refusal in our logs reports `Limit 8000, Requested 44225` — a 5.5x overage.
  - `tokens per minute (TPM)` in 16 of 380 agent logs; `hosted in China and requires explicit opt`
    in 12.
  - `fleet/state/FREE-TIER-LIMITS.tsv` has no usable ceiling for these legs: the row is
    `free-groq|deepseek-v4-pro-groq|gpt-oss-120b-groq_MISMATCH_UNRECONCILED`, all limits
    `unpublished`.
  - `fleet/checks/` contains no size-fit or capacity-fit check.

  DONE CONTRACT — red then green, externally red-proofed:
  a. MEASURE the floor. Determine the actual token size of the join prompt the launcher emits and
     record it in `fleet/state/chain-prompt-floor.tsv` with the date and the method used. This is a
     measurement, not an estimate — a wrong floor either admits incapable legs or refuses good ones.
  b. `fleet/checks/chain-prompt-size-fit.sh` asserts that EVERY leg of EVERY work chain can accept
     the recorded floor. Ceiling source order: the leg's published limit where one exists, else the
     provider-reported limit captured from a live refusal. A leg with NO known ceiling is reported
     as UNKNOWN and surfaced — it is never silently treated as capable.
  c. A leg that cannot accept the floor is REFUSED AT CONFIG TIME with a loud reason naming the
     leg, its ceiling, and the floor. Not a warning, not a runtime failover.
  d. Running the check against the live chains today RED-lists `gpt-oss-120b-groq` and `free-groq`
     on the TPM ceiling. This is the dogfood: the check must fail on the real current config, not
     only on a fixture [[gates-must-actually-run]].
  e. ANTI-OVER-REFUSAL: a leg that comfortably accepts the floor stays admitted, and a leg whose
     ceiling is merely UNKNOWN is not refused as though it were known-too-small. A check that
     empties the chain is as broken as one that admits everything.
  f. FAIL-ON-REVERT, reported both ways: revert the ceiling comparison and the RED-list in (d) goes
     GREEN, proving the assertion is not a tautology. Restore and show GREEN across (b)-(e).
  g. Hermetic. Fixture chains and fixture ceilings; no live gateway call, no network.
  h. `bash fleet/validate_board.sh` GREEN.
scope: |
  The admission RULE, its measured floor, and its test. This ticket does NOT edit
  `fleet/tier-models.tsv` — that file is owned by `BROKER-BARE-TIER-LEGS` and editing it here would
  double-claim. The check READS the chain definition and refuses; removing or re-ordering legs is a
  follow-on decision for the file's owner, taken with this check's output as evidence. Also does
  NOT touch `fleet/charon-run.sh` (owned by `LIMIT-CLASSIFIER-TPM-WIDEN`), does NOT touch
  `fleet/fleet-droid.sh` (owned elsewhere), and does NOT reconcile
  `fleet/state/FREE-TIER-LIMITS.tsv` (owned by `FREE-TIER-QUOTA-ROUTING`) — it reads it and reports
  the gap.

## Dependencies & Sequence

- **depends_on: none.** The check is a new file reading existing config. Nothing has to land first.
- **owns-collision: NONE, and this was the deciding constraint on the owns set.**
  `fleet/tier-models.tsv` was the obvious file to claim and is ALREADY OWNED by
  `BROKER-BARE-TIER-LEGS` (verified against the live board). `fleet/charon-run.sh` is owned by
  `LIMIT-CLASSIFIER-TPM-WIDEN` and `fleet/fleet-droid.sh` by another live ticket. All three are
  therefore excluded, and the ticket owns three NEW paths instead —
  `fleet/checks/chain-prompt-size-fit.sh`, `fleet/tests/chain-prompt-size-fit.test.sh` and
  `fleet/state/chain-prompt-floor.tsv` — none of which exist or are claimed. Reading a file you do
  not own is fine; writing it is the collision [[disjoint-owns-not-no-dependency]].
- **Sibling of `LIMIT-CLASSIFIER-TPM-WIDEN` — EITHER ORDER, disjoint owns, both required.** That
  ticket stops a provider ceiling being scored as model incompetence. This one stops the incapable
  leg being in the chain at all. Neither subsumes the other: even with perfect chains a provider
  can introduce a new ceiling tomorrow, and even with perfect attribution an incapable leg still
  burns a slot and a round on every claim.
- **Sequence: after the classifier, before any chain re-composition.** Priority 1 rather than 0
  because the attribution fix stops ongoing damage to the live ledger, whereas this one stops
  ongoing WASTE. Waste is cheaper than a poisoned ledger, so it queues second — but it must land
  before anyone re-orders the chains, or the re-order is done by hand against a table the fleet has
  already marked `_MISMATCH_UNRECONCILED`.
- **Blocks / unblocks:** unblocks a defensible chain re-composition for `BROKER-BARE-TIER-LEGS` by
  giving it a mechanical answer to "may this leg be in a work chain", and feeds
  `FREE-TIER-QUOTA-ROUTING` a concrete list of legs whose ceilings the SSOT cannot supply.
- **Related, do NOT fold in:** `FREE-TIER-QUOTA-ROUTING` (quota-aware routing at runtime) and
  `FT-CATALOG-SEED` (populating the limits table). Both touch free-tier limits; this ticket is the
  config-time admission rule only.
