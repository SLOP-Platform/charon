repo: charon
tier: strong
difficulty: 3
work_class: doc-deliverable
branch: docs/charon-flowchart
serial_justified: One cohesive whole-system diagram — the value is a single coherent map; splitting produces disconnected fragments.
owns: docs/CHARON-FLOWCHART.md
depends_on:
dep-kind:
note: |
  OPERATOR REQUEST (2026-07-16): a PRINTABLE Charon flowchart the operator can put on paper.
  It must show the FULL flow of WORK and DATA through Charon end to end — every GATE, every
  data flow, how components are WIRED (what connects to what) — so the operator can VISUALLY
  see what's connected to what and what each thing does. Labels VERY CONCISE (a few words per
  node). Not prose — a diagram.
accept: |
  - A single printable flowchart at docs/CHARON-FLOWCHART.md as a Mermaid `flowchart`
    (renders on GitHub + exportable to SVG/PDF for printing). If one page is too dense, at
    most 2-3 linked sub-charts (e.g. work-intake pipeline; gateway/switchboard request path;
    gates/quality lane) — but the TOP chart shows the whole flow at a glance.
  - COVERAGE (derive from CODE + docs, not guesswork — cite sources in a footer):
    * WORK path: NEED → ticket/board → creation-gate + parallelizability/decompose → claim →
      droid/worker → land-push gate suite → PR → merge → done → dependents unblock.
    * DATA/request path (the SWITCHBOARD, ADR-0011): request → gateway → guardrails/cache/
      spend/quality → router/forwarder picks cheapest-capable-with-context-and-available
      provider → failover → response normalize → meter/cost → ledger.
    * GATES: every merge/creation/quality gate (validate_board, parallelizability, security,
      handoff-check, preflight, the charon.cli gate suite) shown as gate nodes on the path.
    * Wiring truth comes from: fleet/state/WIRING-AUDIT-MATRIX.md (WIRED/INERT/PARTIAL), the
      router/forwarder/routing_policy/capability modules, docs/adr/0003/0004/0005/0010/0011,
      and a FRESH graphify map. Mark INERT/PARTIAL components distinctly (e.g. dashed) so the
      operator sees what's built-but-not-wired.
  - Each node ≤ ~4 words + what it does; edges labeled with what flows (work / request / cost / signal).
  - Legend: node types (gate / component / store / external provider) + WIRED vs INERT styling.
  - fail-on-revert: a check (doc-lint or test) asserting docs/CHARON-FLOWCHART.md exists and
    contains a mermaid flowchart block; keep it from silently disappearing.
scope: |
  Documentation deliverable, product repo. Blast radius: none (docs only). HIGH operator value —
  a single source-of-truth picture of how Charon actually works. Build from verified code + the
  wiring audit, NOT from memory; cite sources so it can be re-verified/refreshed.
ds: Next session. No code deps; needs a fresh graphify map + WIRING-AUDIT-MATRIX as inputs.
