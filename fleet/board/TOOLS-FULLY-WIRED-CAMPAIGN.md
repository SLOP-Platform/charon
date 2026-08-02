repo: charon-private
tier: frontier
priority: 0
difficulty: 5
work_class: ci-infra
branch: feat/tools-fully-wired-campaign
depends_on:
owns: fleet/state/TOOLS-FULLY-WIRED-CAMPAIGN.md, docs/review-log/TOOLS-FULLY-WIRED-CAMPAIGN.md
serial_justified: |
  One inventory, one definition of "wired", one ledger. Split per tool, each lane invents its own
  bar for what wired means and the ledger becomes incomparable — which is how ~20% utilisation was
  reached while every tool was individually "adopted".
substrate: N/A
substrate-novel: |
  Nothing is adopted or built here — every tool in scope is ALREADY adopted. The novel slice is the
  per-tool DONE-CONTRACT: a uniform, evidence-backed definition of fully wired and tested, and a
  ledger that makes partial adoption visible instead of invisible.
accept: |
  OPERATOR DIRECTIVE 2026-08-02: get the tools we already have FULLY WIRED AND TESTED. This is the
  umbrella for the #1 priority; the A1-A5 enablement tickets are its first instalments, not its
  whole scope.
  MEASURED BASELINE (fleet/state/OWN-TOOLS-CAPABILITY-AUDIT.md + live scans):
    - ~20% of installed tool surface is switched on; every adopted tool is 10-55% wired
    - 52 tools audited, **37 carry measurable unused capability**
    - **9 fleet checks are INERT** — wired nowhere
    - **1 CLAIMED-BUT-ABSENT guarantee already coded against** (Faktory exactly-once)
    - `graphify affected` — **0 call sites** vs 114 for `graphify update`
    - LiteLLM cost tracking — **vendored in-tree, ZERO production importers**
    - monit — listed adopted, **not installed** (see MONIT-INSTALL-OR-RETIRE)
    - vulture/deadcode — the D4 ratchet fix EXISTS and is sitting in **open draft PR #209**, unread
    - 101 suites declare themselves red-proofs and **never execute** in CI
  DEFINITION OF "FULLY WIRED AND TESTED" — one bar for every tool, no exceptions:
    (W1) REACHABLE from a real entrypoint — proven by call graph, not by grep
    (W2) INVOKED on the cadence it is meant to run (CI leg, preflight leg, or cron entry)
    (W3) SEEN TO FAIL — a deliberate violation makes it RED. **Registration is not proof; a green
         that has never been red proves nothing**
    (W4) ITS FINDINGS REACH A HUMAN — escalation path exists and was observed firing
    (W5) ITS UNUSED CAPABILITY IS EITHER ENABLED OR EXPLICITLY DECLINED WITH A REASON — an
         unexamined flag is how 20% happened
  Done contract:
  1. One ledger row per tool with W1-W5 each PASS/FAIL plus the evidence (command + output). No
     prose-only claims.
  2. Rank remediation by blast radius; land in batches; ratchet so a tool cannot silently regress
     from wired to inert.
  3. Consume, do not duplicate: WIRING-DONE-CONTRACT (W1), PROOF-SUITES-ENFORCE (W3),
     INERT-CHECKS-WIRE (the 9), FLEET-STATUS-BOARD (W2/W4), DEADCODE-TOOLS-WIRE / PR #209 (static
     reachability), MONIT-INSTALL-OR-RETIRE, LITELLM-COST-ADOPT. This ticket OWNS THE LEDGER and
     the bar; those tickets own the fixes.
  4. Fail-on-revert: a tool marked wired whose entrypoint is removed must flip to FAIL in the
     ledger and RED the gate.

## Dependencies & Sequence

P0 — the operator's #1 priority, and the umbrella the A1-A5 tool tickets hang under. No inbound
deps; it can start immediately by building the ledger from the existing audit.
Sequence: define the bar and build the ledger FIRST (cheap, and it makes every other lane
measurable), then remediate by blast radius. Do NOT let it become a second audit — the audit
exists; what is missing is a DONE-CONTRACT per tool and a ratchet that holds it.
