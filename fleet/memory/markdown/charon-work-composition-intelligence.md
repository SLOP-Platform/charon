---
description: "CORE Charon feature — compose & schedule work intelligently (no redundancy, max concurrency, dependency-minimizing chunking); productize the manager doctrine into the engine"
metadata: 
name: charon-work-composition-intelligence
node_type: memory
originSessionId: dbc15100-af3f-415f-ae56-66e13a77d57e
type: project
tags: [charon]
last_referenced: 2026-07-13
---
CORE Charon feature direction (operator, 2026-06-27): Charon must compose and schedule work
INTELLIGENTLY — productize the manager doctrine (adversarial review + blast-radius + dependency
reasoning) INTO the engine/intake/scheduler. Three pillars:

1. **No duplicate/redundant/contradictory work.** Before scheduling AND re-run on every merge,
   reconcile the pending board against current reality: detect tickets that are duplicates,
   made redundant/obsolete by already-merged work, contradict another ticket, or impact files
   another owns/depends on. Static half EXISTS (`validate_board.sh`: transitive-dep, owns-collision,
   orphan checks); the GAP is the SEMANTIC half (dedup/obsolescence/contradiction = LLM-judgment).
2. **Maximize CONCURRENCY.** Schedule as much work in parallel as possible. Execution substrate
   EXISTS (engine board+claim+scheduler+AIMD capacity, per-unit worktrees, PERF-4 parallel units,
   DAG `depends_on` → scheduler claims only the ready set).
3. **Dependency-minimizing CHUNKING.** When work has a dependency, chunk/restructure it so it
   blocks as LITTLE as possible — only the truly-dependent sliver waits, everything else proceeds.
   Today dependencies block at whole-ticket granularity; this finer decomposition is the GAP
   (intake/decompose intelligence — minimize critical path + blocking surface). The TIER-7 A/B
   split (structure A so B never has to redo it) is the manual example to enshrine.

Charon's engine already launches agents, so it can launch reconciler/reviewer agents for the
semantic work (fits gateway-first + agent-agnostic). To be designed via an ADR + a peer-reviewed
design sub-session (the design→adversarial-review loop). Relates to [[charon-build-methodology]],
[[standing-blast-radius-lens]], [[charon-production-readiness-mindset]], [[charon-perf4-next-session]].
