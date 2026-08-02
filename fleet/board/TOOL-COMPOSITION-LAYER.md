repo: charon-private
tier: frontier
difficulty: 4
work_class: design-review
priority: 0
branch: design/tool-composition-layer
depends_on:
owns: fleet/handoff-notes/TOOL-COMPOSITION-RESEARCH.md
reopened: |
  REOPENED 2026-08-02 by operator directive — it was a FALSE DONE.
  MEASURED: the ticket was archived with a done-marker, but its sole deliverable
  `fleet/handoff-notes/TOOL-COMPOSITION-RESEARCH.md` DOES NOT EXIST on disk. Commissioned,
  marked complete, no artifact — the same class as operator action #15 (~10 review verdicts
  commissioned, completed, never read) and as PR-QUEUE-REST-ETAG (merge-proven on PART of its
  owns while the rest was never built). "Archived + DONE" is not evidence that work happened.
  `fleet/state/EVAL-REGISTRY.md` was DROPPED from this ticket's owns on reopen: the active work
  on that file is now EVAL-REGISTRY-DERIVE (P0), and two live tickets owning it would be an
  owns-collision. This ticket owns its RESEARCH NOTE only.
  WHY IT MATTERS NOW, not just as hygiene: this ticket's central finding is the missing JOIN
  between four producers that all describe the same code — the board's `owns:` field (318
  tickets), graphify's `graph.json` code map, memory directives, and the gate-gap ledger. That
  join is EXACTLY what EVAL-REGISTRY-DERIVE, CRON-REGISTRY-VISIBLE and PRIORITY-DROPOUT-AUDIT
  each need in order to reconcile a list against reality. Three tickets are about to hand-roll
  three private versions of the same join. Landing this research FIRST is what stops that.
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

## Dependencies & Sequence

- **depends_on: none.** Read-only study over the board, graphify's `graph.json`, memory and the
  gate-gap ledger. Every input already exists.
- **RUN IT NOW, AHEAD OF THE THREE RECONCILERS IT FEEDS.** `EVAL-REGISTRY-DERIVE` (tools),
  `CRON-REGISTRY-VISIBLE` (scheduled jobs) and `PRIORITY-DROPOUT-AUDIT` (work items) are all
  instances of ONE class — "a list and reality disagree, silently" — and each needs the SAME join
  between `owns:`, the code map and live state. Without this research they will hand-roll three
  private joins that drift apart. This ticket is what makes them share one.
- Reopened 2026-08-02 (see `reopened:`) because the archived DONE marker had no deliverable.
  Re-verify the ticket's own central measurement before building on it — `registry-discovery.sh`
  being the only `graph.json` consumer, and its zero `owns:` references — since it is now ~2 days
  old and this rig's facts rot fast `[[confirm-dont-trust-documentation]]`.
- Related but NOT blocking: `KSF-PLUGIN-FRAMEWORK-RESUME` asks whether KSF is the right HOST for
  a shared framework; this asks what the COMPOSITION layer between tools should be. Disjoint
  owns, and they inform each other — read its findings if it lands first.
- Deliverable is a RESEARCH NOTE. No build, no wiring, no adoption without an operator decision.
