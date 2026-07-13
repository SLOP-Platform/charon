---
description: "portable stdlib orchestration store plan (\"obol\", ADR-0008 Phase 1) — v1 DTC-rejected, v2 folds 7 blocker-fixes + 3 operator rulings"
metadata: 
name: charon-portable-orchestration-store
node_type: memory
originSessionId: a8f924d0-22f6-4f2b-ac52-79591b72effd
type: project
tags: [charon]
last_referenced: 2026-07-13
---
DECISION 2026-07-02: consolidate the fragmented "Droid Method" (two coexisting coordination planes — file/flock markers+`waves/*.json`+`validate_board.sh` AND the newer SQLite bridge daemon) into ONE portable, **stdlib-only** orchestration store, deployable to Charon, SLOP/mediastack, and future products as a reusable tool. Working name **obol** (operator-owned open decision). Scoped as the ADR-0007/0008 in-tree work-engine reference — the rig design that graduates into the shipping product, so it must stay stdlib-only (no beads/Dolt/Pydantic/Redis) to avoid rig→product leak. See [[charon-own-work-engine]], [[wci-rig-enforced-product-deferred]], [[product-vs-build-rig-boundary]].

Design doc (durable, private): `/build-rig/fleet/PLAN-PORTABLE-ORCHESTRATION-STORE.md`.

Core thesis: the Droid Method already independently reinvented ~90% of the multi-agent-orchestration field and is AHEAD on 3 things (idle=free cold pooling; ephemeral-per-ticket anti-drift; physics-grounded lie-detection via git-HEAD/diff hashes). The gap is FRAGMENTATION, not mechanism — fix is subtraction to one store with **derived** readiness (beads-style `ready` = no open blockers + no owns-overlap), atomic claim, typed-nudge inbox, quorum consensus. Mechanizes WCI ([[charon-work-composition-intelligence]]).

DTC OUTCOME (2026-07-02): a 4-lens adversarial panel (arch/simplicity, portability/stdlib-leak, store-concurrency, testing/migration) **unanimously REJECTed v1**, all "fixable not fundamental." 7 consensus blockers — incl. a real bug (`conn.total_changes` misused as rowcount → silent double-claim), an undecidable `fnmatch` pattern-vs-pattern collision gate, at-most-once inbox that loses nudges, single-writer-vs-N-claimer contradiction + daemon SPOF, reaper double-assign (no fencing), stdlib violated by Pydantic/TOML/systemd defaults, and race tests that never race. Operator rulings: **one daemon per project** (drop multi-tenant key); **add optional checkpoint/barrier** (auto-release default, no forced eyeball); **keep consensus but diverse-lens not N clones, drop loopback crypto**. v2 revision pass in progress folding all of it. STATUS: design only — nothing built; no code changes made.
