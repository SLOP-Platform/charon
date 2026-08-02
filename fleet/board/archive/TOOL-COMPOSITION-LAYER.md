repo: charon-private
tier: frontier
difficulty: 4
work_class: design-review
priority: 0
branch: design/tool-composition-layer
depends_on:
owns: fleet/handoff-notes/TOOL-COMPOSITION-RESEARCH.md, fleet/state/EVAL-REGISTRY.md
serial_justified: |
  ONE comparison under ONE lens. Split across tickets, each candidate is scored against a
  slightly different bar and the results are not comparable — the exact defect that produced this
  programme's prior too-narrow verdicts.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session. Own worktree. READ-ONLY study.
  Verified funded 2026-07-31: deepseek-v4-pro, gpt-oss-120b-groq, grok-build-0.1, minimax-m2.7.
source: |
  Operator 2026-07-31: "Even if we have a tool 100% wired into the code is it wired at a META/CLASS
  high level? The framework tool layer that allows tools to work with each other and have
  visibility to the data/functions/output of other tools? If you touch a piece of code/thread you
  should have knowledge not just of why it is that way but the things it depends on, depend on it,
  how it gets the data, what it does with it and how it hands it off."
note: |
  ## THE OPERATOR'S QUESTION, MADE CONCRETE BY A MEASUREMENT
  Touching a piece of code should tell you: why it is that way · what it depends on · what depends
  on it · how data reaches it · what it does with it · how it hands off.

  **The join key ALREADY EXISTS on both sides and nothing performs the join** (verified 2026-07-31):
  - **318 board tickets carry `owns:`** — machine-readable code paths they govern.
  - **5 tickets own `fleet/land.sh`**, including `LAND-SH-SAFE-SYNC` — the exact provenance a
    manager needed and failed to find, nearly reverting a data-loss guard as a result.
  - `fleet/checks/registry-discovery.sh` is the ONLY consumer of graphify's `graph.json` and
    contains **ZERO** references to `owns:` (`grep -c "owns:"` -> 0).

  graphify answers *what calls what*; the board answers *why it is this way*; memory holds
  directives; `GATE-GAP-LEDGER` holds failure classes. **Four producers, no join.** graphify is NOT
  underperforming — a code graph was never the WHY tool; expecting provenance from it is a
  category mismatch.

  ## FRAMING (hypothesis — TEST IT, overturn loudly if wrong)
  The manager believes the missing thing is a COMPOSITION/JOIN layer, not another tool, and that
  the cheapest real win may be joining `owns:` to the code graph — turning "touch land.sh" into
  "here are the 5 tickets that govern it, one of which explains the guard you were about to
  revert". **UNVERIFIED**, and possibly too small: the operator is asking for data-flow visibility
  (how data arrives, is transformed, is handed off) which a static owns<->symbol join does NOT
  provide. Say so if the join is a partial answer.

  ## HARD CONSTRAINT
  **DO NOT propose hand-rolling a framework tool layer.** That is the exact disease this programme
  has spent months unwinding. Find what EXISTS. Candidates to RESOLVE and RUN (not assert):
  MCP as the composition protocol (we already run graphify-mcp, basic-memory and session-bridge and
  have NEVER composed them); Graphiti/Zep temporal graphs ingesting multiple producers into ONE
  graph; SCIP/LSP as code-relation standards; OpenTelemetry for runtime data flow. Add your own.

  ## THE LENS (corrected — see MANAGER-OPERATING-RULES.md §11)
  Weight **B leverage** and **C verification** highest, not code-deleted. **Size is NOT a rejection
  criterion** — judge on maintenance liveness, fit-without-bending, control direction, exit cost.
  Every benefit claim must name a MEASURED incident it would have prevented. Use these real ones:
  a manager nearly reverting `LAND-SH-SAFE-SYNC` for want of provenance · `litellm_plane` imported
  only by tests and unnoticed · two capability engines (~6,900 LOC) neither knowing the other
  exists · a CrewAI verdict discoverable only inside a handoff note.

  ## DONE CONTRACT
  - Per candidate: what it IS from the CODE, how it was RUN (commands + real output), whether it
    performs a genuine cross-producer join, verdict, and what of ours it would delete or connect.
  - An explicit answer on the cheap `owns:`<->graph join: worth doing now, or a distraction?
  - **Verdicts land in `fleet/state/EVAL-REGISTRY.md`, never only in a handoff note.**
  - `ADOPT-CANDIDATES: <list or NONE>`; if NONE, what you tried hardest to make work and why.

D&S — Deps & Sequence:
  - Depends on: nothing (read-only study).
  - Related: KSF-LOAD-BEARING (the framework that "gates only itself"), ENGINE-CONVERGE.
  - Sequence: research only. No build without an operator decision on the outcome.
