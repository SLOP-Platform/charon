repo: charon-private
tier: frontier
priority: 0
difficulty: 4
work_class: design-review
branch: eval/own-tools-capability-audit
depends_on:
owns: fleet/state/OWN-TOOLS-CAPABILITY-AUDIT.md
substrate: N/A
substrate-novel: |
  The subject IS our adopted-tool inventory. Nothing external can audit what WE use of what WE
  adopted. Reuses the existing EVAL-REGISTRY as the record and TOOL-INVENTORY.md as the starting
  enumeration rather than building a new registry.
serial_justified: |
  One sweep across one inventory. Per-tool audits in isolation are what produced the current
  state — each tool looked fine on its own; the UNUSED-CAPABILITY pattern is only visible across
  the whole set.
execution: |
  Off-Claude via fleet-droid.sh, own worktree. EVAL lane — measure and report. Wire NOTHING.
source: |
  Operator, 2026-08-01: "Review all our current tools too — not surface scanning but REAL full
  capabilities." Follows the Faktory precedent, where a tool was adopted, declared the fleet's
  sole substrate, and 7 days later had zero workers and a headline guarantee it never possessed.
note: |
  ## THE PATTERN THIS AUDIT EXISTS TO MEASURE
  The prior handoff already recorded it: **every adopted tool is 10-55% wired.**
  | Tool | Available | Actually used |
  |---|---|---|
  | `litellm.Router` | 52 params | **5** (litellm_plane imported by TESTS ONLY) |
  | KSF | 9 gates + modules | **5 gates, 0 modules, 1 of 3 repos**, never run in CI |
  | graphify | full code graph, refreshed every land | **1 query consumer** |
  | opencode client catalog | 2,567 gateway models | **36 listed** |
  | basic-memory | 4-ticket adoption | 2 done |
  | `discover.py` cost map | price + free flags | **never persisted** |
  | Faktory | queue/lease/retry/morgue + Enterprise set | **5 verbs, 0 workers, never wired** |
  Measured again 2026-08-01: **212 of 859 catalog entries carry `cost_rank`, and the gateway's
  ordering ignores it** — a capability present in the DATA and unused by the CODE.

  ## SCOPE — FULL CAPABILITY, NOT SURFACE SCAN
  Start from `fleet/TOOL-INVENTORY.md` and `fleet/state/EVAL-REGISTRY.md`, then go BEYOND them —
  an inventory that is itself incomplete is a finding. For EVERY tool we own or have adopted
  (rig scripts, product tools, adopted libraries, MCP servers: graphify/graphify-mcp,
  basic-memory, session-bridge, litellm, KSF, ruff, mypy, bandit, gitleaks, semgrep, pip-audit,
  opencode, gh, Faktory, plus every `fleet/*.sh` and `fleet/checks/*`):

  1. **FULL capability surface** — from the tool's OWN docs/source/`--help`, not from our usage.
  2. **What we actually use** — measured by grep/execution, not assumed.
  3. **The DELTA** — capabilities present and unused. For each, is there a NAMED ticket or
     measured incident it would serve? An unused capability with no need is fine; an unused
     capability that maps onto an open problem is a finding.
  4. **CLAIMED-BUT-ABSENT** — capabilities our docs/tickets/comments assert that the tool does NOT
     actually have. Faktory's exactly-once is the precedent: `CLAIM-LEASE-EXACTLY-ONCE` was
     recorded as coding against a guarantee OSS Faktory does not provide. **This class is more
     dangerous than unused capability** — something may depend on it.
  5. **INERT** — tools present, wired nowhere, never run. `gate-integrity.sh` already lists
     candidates (G1 INERT: `selfcheck-cycle.sh`, `dark-work-check.sh`).

  ## PRIORITISE THE E2E PIPELINE
  The operator's pain is the ticket lifecycle. Audit tools touching CREATE/SCHEDULE/CLAIM/WORK/
  GATE/COMMIT/PR/REVIEW/MERGE/CLOSE **first**, and for each ask: **does a capability we already
  own close one of the 12 measured silent failures in WORKFLOW-E2E-AUDIT?** A fix we already own
  and have not switched on beats anything new.

  ## HARD RULES
  - Verdicts and per-tool rows land in `fleet/state/EVAL-REGISTRY.md`; long-form in the owned file.
  - **Do NOT recommend building anything.** Output is "capability X exists, unused, would serve
    problem Y". Builds are separate tickets.
  - Size / dep count are NOT criteria. Ops burden and control direction ARE.
  - Verify by EXECUTION or source, never by README claim — the README claim is what got us here.

  ## DELIVERABLE
  1. Per-tool table: full surface | used | delta | claimed-but-absent | inert?
  2. **Ranked list of unused capabilities that map to an OPEN problem** — the actionable output.
  3. The CLAIMED-BUT-ABSENT list, flagged loudly, with what depends on each.
  4. An honest statement of inventory coverage: which tools you could not fully audit and why.

D&S — Deps & Sequence:
  - Depends on: nothing. Read-only, owns one doc, collision-free.
  - Pairs with WORKFLOW-E2E-AUDIT (that one maps the pipeline's failures; this one maps the
    capabilities we already own that could close them). Neither blocks the other.
  - Feeds PR-AUTOMATION-EVAL and the REVIEWER-TAB-POOL decision.
