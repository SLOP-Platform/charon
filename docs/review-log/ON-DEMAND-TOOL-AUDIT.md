# ON-DEMAND-TOOL-AUDIT — review note

Ticket: ON-DEMAND-TOOL-AUDIT (frontier, rig-meta). Output: `fleet/state/ON-DEMAND-TOOL-LEDGER.tsv`.

## What was done

Classified every tool in TOOL-INVENTORY.md + fleet/*.sh + fleet/checks/*.sh + fleet/memory/* +
fleet/capability/* + product tools/check_*.py + the WIRING-AUDIT-MATRIX src/charon modules by
INVOCATION REALITY: grepped callers across the whole rig, gates.json, gate_runner.py CHECKS, CI
workflows, crontab, both SessionStart hook files; checked run evidence (state artifacts, mtimes,
git history). Extends TOOL-WIRING-AUDIT.md (2026-07-16T01:05Z) with the never/rarely-run dimension.

## Key corrections to prior audits

- **foreman.sh IS now wired** (preflight.sh:590 `foreman_advisory`) — TOOL-WIRING-AUDIT's P0
  finding and its corrigendum are superseded by a later landing. Remaining gap = cadence +
  multi-trigger, already covered by FOREMAN-MULTI-TRIGGER (claimed, in flight).
- **config-drift.sh degraded-no-op is RESOLVED** — state/CONFIG-SOURCES.tsv exists (07-15 18:19).

## Top offenders (dynamic-data, no trigger/never run)

| rank | tool | class | disposition |
|---|---|---|---|
| P0 | tools/check_catalog_case_quant.py | NO-TRIGGER | covered: CATALOG-GATE-WIRE (unclaimed — claim it) |
| P0 | fleet/checks/no-anthropic-in-sg.sh | NEVER-RUN | **needs boarding** (wire into validate_board + preflight) |
| P0 | fleet/checks/base-integrity.sh | NO-TRIGGER | fold into LAUNCH-PLAN-SH or **board BASE-INTEGRITY-WIRE** |
| P0 | fleet/dark-work-check.sh | ON-DEMAND-ONLY | **board NO-DARK-WORK** (ROADMAP F47 still 'designed') |
| P1 | memory retrieval chain (session-preamble/search/curate) | NO-TRIGGER | covered: STARTUP-CONTEXT-DIET |
| P1 | graphify update | ON-DEMAND-ONLY | covered: GRAPHIFY-MAP-FRESHNESS (claimed) |
| P1 | launch-plan.sh / stale-check.sh | NO-TRIGGER | covered: LAUNCH-PLAN-SH (unclaimed) / STALE-CHECK-SH (in flight) |
| P1 | fleet/checks/rule-sync.sh | NO-TRIGGER | **needs boarding** (small preflight/validate_board wire) |
| P1 | fleet/reuse-check.sh (ksf) | NEVER-RUN | fold into GRAPHIFY-MAP-FRESHNESS reuse entry point (its accept already specs it) |
| P2 | model-scorecard.sh --due leg | RARELY-RUN | ride FOREMAN-MULTI-TRIGGER's handoff.sh edit (same file) or small board |
| P2 | log-prune.sh | NEVER-RUN (124 overnight logs + 12M agent-logs persist) | **needs boarding** (weekly cadence, dry-run) |
| P2 | fleet/checks/gpt55-primary.sh | NEVER-RUN | wire as preflight advisory OR retire — decide at boarding |
| P3 | fleet/memory/migrate.py | DEAD | retire/archive (one-shot migration done) |
| P3 | research.sh | NEVER-RUN | on-demand shape is correct (launcher); dogfood once or retire by 08-01 |

src/charon INERT modules (RequestInspector, SessionAffinity, Observability, SpeculativeExecutor,
ConsensusRouter, VirtualKeyManager, BalanceTracker.record_spend) folded in as NEVER-RUN with the
WIRING-AUDIT-MATRIX one-change wiring map; R44/R45/R46 + DRAIN-ROUTING (claimed) own those.

## Boarding proposals (per accept "Then" — this ticket owns only the ledger, so proposals, not ticket files)

1. **NO-DARK-WORK** — promote ROADMAP F47 from 'designed' to a board ticket: wire dark-work-check.sh
   --pickup into preflight scan, --register into SessionStart, + handoff.sh leg. Reuse-check: tool exists,
   wiring only.
2. **GUARD-WIRE (no-anthropic + rule-sync + base-integrity)** — one small ci-infra ticket wiring three
   existing zero-caller checks into their natural chokepoints (validate_board/preflight/launch path) +
   fail-on-revert tests. Reuse-check: all three scripts exist; wiring only. (base-integrity may instead
   fold into LAUNCH-PLAN-SH if that claims first — disjointness note required either way.)
3. **LOG-PRUNE-CADENCE** — weekly SessionStart-interval dry-run leg for log-prune.sh; apply stays operator.
4. **gpt55-primary.sh** — operator decision requested: wire as timeout-wrapped preflight advisory, or retire.
5. Fold — scorecard --due surface into FOREMAN-MULTI-TRIGGER (it already owns handoff.sh);
   reuse-check entry into GRAPHIFY-MAP-FRESHNESS (its accept already specs the reuse entry point).
   No net-new tools proposed anywhere — every fix is wiring/cadence around existing scripts.
