repo: charon-private
tier: economy
priority: 2
difficulty: 3
work_class: rig-meta
branch: feat/fn-memory-retire-adopt
owns: fleet/memory/, fleet/research.sh
serial_justified: One cohesive retire+adopt around a single owned surface (fleet/memory/) + its dangling refs; the delete and the reference-purge must land atomically or a gate points at a dead path.
depends_on:
note: |
  FN1 shipped a HAND-ROLLED term-frequency store MISLABELED "basic-memory/MCP-native/FastEmbed"
  (fleet/memory/__init__.py:1-3); basic-memory is imported NOWHERE. It is INERT: 0 hook/gate/CI/
  preflight callers (audit-harvest.md:224 "0 callers CONFIRMED"; ON-DEMAND-TOOL-LEDGER "NO-TRIGGER").
  FN3 (curate.sh) is ALSO an inert hand-roll but imports NOTHING from FN1, so retiring FN1 does not
  break it; retired together. curate.sh default NOTES_DIR (/home/stack/charon-private/memory) does not
  even exist. The in-repo fleet/memory/markdown/ (92 files) was a STALE copy of the real store
  (~/.claude/.../memory/, 146 files) — NOT source of truth. FN2 (fleet/memory/bitemporal.py +
  fleet/tests/test_bitemporal.py) is ALSO inert and is DELETED here too (operator gap-B2 option i:
  fully atomic FN1+FN2+FN3 retire); its unbuilt model-signal ledger-decay intent is PRESERVED as the
  ROUTER-side ticket ROUTER-LEDGER-DECAY so nothing is lost.
  The "wholesale dump" is Claude Code's native MEMORY.md auto-injection (136-line index), NOT a
  settings.json hook (settings.json cats no memory file). Adopt real basic-memory MCP + its Claude
  Code plugin pointed at the operator's existing memory dir; build only a thin curation sliver.
accept: |
  RETIRE (repo, DONE on feat/fn-memory-retire): delete ALL of fleet/memory/ (__init__.py, search.py,
    load.sh, session-preamble.sh, pin.md, migrate.py, markdown/, tests/, curate.sh, bitemporal.py) +
    fleet/tests/curate.test.sh + fleet/tests/test_bitemporal.py — fully atomic FN1+FN2+FN3 retire.
    Purge dangling refs in ON-DEMAND-TOOL-LEDGER.tsv (session-preamble.sh + migrate.py rows),
    research.sh:347-348 (memory/markdown pointers), research.test.sh fixture.
  INTENT PRESERVED (not deleted-and-lost): the gap-B2 model-signal ledger-decay intent of the retired
    bitemporal.py is re-opened as ROUTER-LEDGER-DECAY (router-side, build-when-needed).
  PROOF-OF-NO-BREAK: `bash fleet/checks/rig-ci-scope.sh tests` stays green (no memory suite is in
    CI_SUITES — that is the fail-safe: if it were, this would go red).
  ADOPT (glue, repo): one-shot frontmatter migration (tags+last_referenced) over the REAL vault;
    a scheduled, APPROVAL-GATED curation job (dedup/conflict/decay→archive) over the real vault.
  OPERATOR (own machine, tracked as pending actions, NOT repo): install basic-memory + register MCP
    pointed at ~/.claude/.../memory/; install the basic-memory Claude Code plugin; trim MEMORY.md to a
    tiny pinned core (kills the index dump).
  FAIL-ON-REVERT: a test asserts fleet/memory/ contains no hand-rolled search/decay module and no
    "basic-memory"/"FastEmbed" self-label docstring; re-adding either -> red.
  GREEN-IS-NOT-PROOF: demonstrate a real point-of-need recall of a fact that is NOT in the pinned
    core, served by basic-memory (not the deleted hand-roll).
scope: Rig-only (manager/session memory). basic-memory is AGPL-3.0 — fine for the internal rig;
  txtai/MIT is the documented swap IF productized. Store+retrieval solved by basic-memory + its CC
  plugin; the only build is the curation sliver (+ optional semantic index if CC search proves weak).
ds: |
  Dependencies & sequence:
   1. RETIRE (delete + reference-purge) lands FIRST, atomically — one PR (feat/fn-memory-retire).
      Blast radius near-zero (only self-tests consume it; none are in CI).
   2. OPERATOR install/plugin/MEMORY.md-trim — can proceed in parallel on their machine; the index
      bloat persists until they trim MEMORY.md, so this is the gating action for the actual win.
   3. Frontmatter migration + curation job land AFTER retire (same or follow-up PR).
   Does NOT depend on FN4/FN5 (unrelated). Supersedes FN1/FN2/FN3. FN2's (bitemporal.py) unbuilt
   gap-B2 ledger-decay intent is carried forward by ROUTER-LEDGER-DECAY, not lost.
