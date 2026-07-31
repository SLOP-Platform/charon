repo: charon-private
tier: frontier
difficulty: 4
work_class: design-review
priority: 0
branch: design/router-substrate-reeval
depends_on:
owns: fleet/handoff-notes/ROUTER-SUBSTRATE-REEVAL.md, fleet/state/EVAL-REGISTRY.md
serial_justified: |
  ONE comparison under ONE lens. Split across tickets, each target gets scored against a slightly
  different bar and the results are not comparable — which is precisely the defect that produced
  the prior too-narrow verdicts this ticket exists to redo.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session (charon/* gateway model), NOT Claude.
  GLM and Kimi are OFFLINE (operator action #14). Verified-funded legs as of 2026-07-31:
  deepseek-v4-pro, minimax-m3-together, devstral-2512, gemini-2.5-pro. Own worktree.
source: |
  Operator, 2026-07-31: "Are we FULLY implementing/using all the features/capabilities of the tools
  we already have... We have done multiple evals on some of these but I think it was with the wrong
  lenses applied, in some ways too narrow, not realizing the potential overall benefits."
note: |
  ## WHY THE PRIOR EVALS MUST BE REDONE, NOT CITED
  Existing verdicts in `fleet/state/EVAL-REGISTRY.md` were reached under a lens that asked mainly
  **"what of OURS does this delete?"** That question is structurally blind to capability GAPS: a
  tool that FILLS something we lack scores zero, because there is nothing for it to replace.
  **A REJECT reached under a bad lens must be RE-DERIVED, not quoted.** Read the prior verdict,
  then independently re-reach or overturn it under the corrected lens below.

  ## THE CORRECTED LENS — value taxonomy (weight B and C highest)
  | | Value type | Weight |
  |---|---|---|
  | A | Substitution — deletes code we own | real, one-time |
  | B | **Leverage** — routing/session quality more capable, consistent, reliable | **highest, compounds** |
  | C | **Verification** — catches defects we currently ship | **high** |
  | D | Throughput — same work, less wall-clock/tokens/cost | medium |
  | E | Product capability — makes SG better for ITS users | high |

  **Adoption predictors REPLACE size.** Size is a proxy for maintenance burden and is only valid
  when WE are the maintainer; for a live dependency it is near-irrelevant. Judge on: maintenance
  liveness · fit-without-bending · control direction (library vs framework) · exit cost ·
  whose-2am-is-it. Size matters ONLY for supply-chain/CVE surface and use-5%-inherit-100%.
  **A 75K dependency that works beats 5K of ours that keeps generating errors.**

  ## GROUNDING DISCIPLINE — B/C claims must cite a REAL failure
  "It improves routing" justifies anything. Every B/C claim must answer: *would this have prevented
  [incident], which cost [what]?* Test against these MEASURED incidents from this rig:
  - `glm-5.2` exists as SIX separate catalog entries routing cannot reach from one name
  - "all providers exhausted": openrouter/neuralwatt/deepinfra 402, nanogpt weekly-capped,
    cline-pass 429 monthly, huggingface credits depleted — no budget-aware routing
  - `deepseek-v4-flash` silently truncates at a 48-request session cap, still reports success
  - free tiers pass a 1-shot probe then collapse under session load
  - the SOLE-LEG GUARD fired 199 times in one log window
  Concrete answer → ADOPT candidate. Abstract promise → WATCH.

  ## TARGETS
  `LiteLLM` (proxy-server mode + Router features we do not use — see LITELLM-CAPABILITY-ADOPTION) ·
  `Portkey` · `RouteLLM` · `OmniRoute` · `llm-route` · `github.com/walidboulanouar/maestro` ·
  **`OpenRouter`'s own routing features** (provider preferences, fallback ordering, price/latency
  routing — we may be paying for a router and using it as a dumb pipe).

  Bare names may resolve to nothing. Not-found is a legitimate result — record what you searched.

  ## REAL CAPABILITY STUDY — NOT DOC-READING
  Clone it. Install it. RUN it against a REAL request through our own gateway config where
  possible. Record exact commands and real output. "Could not run it: <reason>" is a finding; an
  unrun tool is NEVER upgraded to a recommendation.

  ## HARD SCOPE LIMITS
  - **Charon's gateway IS THE PRODUCT.** Do NOT recommend replacing it wholesale. Evaluate these as
    things that strengthen it or delete RIG code.
  - Some policy is genuinely ours and encodes our differentiation — free-tier windows,
    funding-class ordering, outcome-grading. Do NOT recommend surrendering those.
  - **Sequencing:** LITELLM-CAPABILITY-ADOPTION runs in parallel and answers "what are we not using
    in the tool we ALREADY adopted". Several targets here may be redundant once that lands. Where a
    target duplicates an unused litellm capability, SAY SO — that is the highest-value finding in
    this ticket.

  ## DONE CONTRACT
  - Per target: what it is (from the CODE, not the pitch), how it was run (commands + output),
    A–E scoring, verdict (ADOPT / ADOPT-PARTIAL / WATCH / REJECT / UNVERIFIABLE), and — where a
    prior verdict exists — whether it is UPHELD or OVERTURNED and why.
  - Maintenance liveness, licence, control direction and exit cost per target.
  - `fleet/state/EVAL-REGISTRY.md` updated with the re-derived verdicts, each marked
    RE-EVALUATED-2026-07-31 so the lens change is auditable.
  - Explicit line: `ADOPT-CANDIDATES: <targets, or NONE>` — and if NONE, what you tried hardest to
    make work and why it failed.

D&S — Deps & Sequence:
  - Depends on: nothing to RUN (read-only study).
  - Blocks: nothing directly; informs the routing roadmap after the cutover.
  - Runs in parallel with: LITELLM-CAPABILITY-ADOPTION (disjoint owns), the DTC protocol reviews.
  - Do NOT act on conclusions before LITELLM-CAPABILITY-ADOPTION lands (see Sequencing above).
