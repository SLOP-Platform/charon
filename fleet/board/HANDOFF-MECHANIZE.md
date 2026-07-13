tier: economy
difficulty: 2
work_class: ci-infra
branch: feat/handoff-mechanize
repo: charon-private
depends_on:
owns: /home/stack/charon-private/fleet/handoff.sh, /home/stack/charon-private/fleet/handoff-check.sh, /home/stack/charon-private/fleet/preflight.sh
accept: |
  `bash fleet/handoff-check.sh <a-known-incomplete-handoff>` EXITS NON-ZERO and names the missing
  section; on a complete handoff it exits 0. handoff.sh emits ALL sections handoff-check.sh requires
  (bootstrap one-liner, done/committed@SHA, next-action/in-flight, gotchas, session-bridge) PLUS the
  live machine-state the manager currently hand-types: active `git worktree list`, in-flight
  charon-run jobs + their CHARON_RUN_RESULT, `provider-exhaustion-ledger.tsv` tail, session-bridge
  board. Fail-on-revert: delete a required-section check from handoff-check.sh -> a meta-test that
  feeds it an incomplete fixture goes GREEN when it should be RED.
scope: |
  ROOT CAUSE of the recurring poor/inaccurate/incomplete-handoff problem: handoff.sh (a state
  GENERATOR) existed but was under-used and incomplete, and there was NO validator to catch a bad
  handoff. handoff-check.sh (v1, built 2026-07-10) is the completeness+accuracy GATE. This ticket:
  (1) enriches handoff.sh to auto-emit worktrees / in-flight jobs / exhaustion tail / bridge board so
  facts are pulled from live state (accurate by construction, not memory); (2) keeps handoff.sh's
  emitted section headers IN SYNC with handoff-check.sh's required-section list; (3) wires
  `handoff-check.sh` into preflight.sh as an ACTIVE DETECTOR (warn if the newest HANDOFF-*.md fails).
  Rig tooling, not product. The operating rule `[mechanized-handoff-gate]` already added to
  MANAGER-OPERATING-RULES.md.
ds: Rig-only, disjoint from all product work. Route to Charon (glm-5.2 / economy — shell tooling).
