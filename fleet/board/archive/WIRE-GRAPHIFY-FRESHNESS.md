repo: charon-private
tier: strong
difficulty: 2
priority: 1
work_class: rig-meta
branch: fix/wire-graphify-freshness-gate
owns: fleet/checks/graphify-freshness.sh, fleet/tests/graphify-freshness.test.sh
depends_on:
source: operator 2026-07-23 ("mechanized automated method to always keep the code map updated as things change"); ON-DEMAND-TOOL-LEDGER.tsv row (graphify: 0 callers, hand-refresh only)
note: |
  The code map (graphify-out/graph.json) is refreshed ONLY by hand — product graph is days stale, rig
  graph absent/week-stale, and `grep graphify` over fleet/*.sh + checks = 0 callers. The freshness gate
  fleet/checks/graphify-freshness.sh ALREADY EXISTS ("MECHANIZED WIRING … never-on-demand") but is
  ORPHANED (0 callers) — built-but-not-wired. REUSE it; do NOT rebuild. This is the [[dynamic-tools-never-on-demand]]
  contract (cadence + multiple smart triggers + tested) and a reconciler leg (code-map == actual code).
accept: |
  - WIRE the existing graphify-freshness.sh gate so it runs automatically on ALL smart triggers, never
    on-demand: (a) fleet/preflight.sh scan-dispatch, (b) post-land (fleet/land.sh success hook),
    (c) SessionStart, (d) a cadence timer (foreman-cadence.sh). Each wiring is a one-line anchor into a
    shared file — COORDINATE with the owners of preflight.sh/land.sh, do not rewrite them.
  - STALE == RED: `graphify-freshness.sh check` fails LOUD when any tracked graph is older than its repo's
    latest code change (map != code drift), covering BOTH the product AND the rig graph (rig currently
    unmapped — add it). A trigger auto-runs `graphify update` to refresh, then re-checks.
  - fail-on-revert test (fleet/tests/graphify-freshness.test.sh): seed a code change newer than the graph
    => check RED; refresh => GREEN. Revert the wiring/staleness logic => a stale map passes silently (RED).
  - bash fleet/validate_board.sh GREEN.
scope: |
  Wire the orphaned graphify-freshness gate (reuse) + add the rig to mapped repos. Makes the code map
  self-refreshing + drift-loud. A leg of the plane-canary suite ("map plane": code-map == actual code).
ds: |
  ## Dependencies & sequence
  P1, no build prereq. Reuse graphify-freshness.sh — do NOT rebuild. Wiring anchors coordinate with
  preflight/land owners. Composes with the reconciliation-gate + the plane-canary design.
