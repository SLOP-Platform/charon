---
description: "NEXT-session plan (operator 2026-06-26) — organize non-parked work into file-grouped non-colliding tickets, write ADR-0006 for PERF-4+decomposition (PRIORITY), then hand off to Droid Robot Mode. Full prompt in /build-rig/HANDOFF-next-session.md."
metadata: 
name: charon-perf4-next-session
node_type: memory
originSessionId: 2683d853-b25a-4778-9fb0-d458d14b54d2
type: project
tags: [charon, session]
last_referenced: 2026-07-13
---
**Operator 2026-06-26 — next-session order of work.** Full copy-paste prompt:
`/build-rig/HANDOFF-next-session.md`.

1. **Organize** all non-parked work into **maximum-efficiency, NON-COLLIDING tickets**
   (Droid Robot Mode style): group by FILE — every edit to a file lands in ONE ticket;
   tickets that run in parallel own **disjoint** file sets so droids never touch the
   same file. Output a PRIVATE tickets doc (not the public repo).
2. **BUILD import-all-models FIRST** (operator 2026-06-26): pull a provider's
   `/v1/models` (with the stored key) and add them all to config as a CATALOG —
   `charon models import <provider>` + a wizard y/N prompt + a web "import" button.
   Pools stay curated (do NOT dump all models into one failover pool). Files: cli.py,
   gateway.py, proxy_server.py, config.py.
3. **THEN PERF-4 + work-decomposition.** Write **ADR-0006** with an adversarial
   self-review, reconcile in REVIEW-LOG, BEFORE code. Base it on PLAN-tier4 §3
   (`run_parallel(units, max_parallel)`, separate ledger+worktree per unit, per-task
   lock; D1 isolation sufficiency — git global config/env/`.charon` parent/shared
   Budget; D2 over-build; §6 binding fixes) + ADR-0004 D6 (thin DAG runner) / D8 (role
   decomposition Triage→Plan→Implement→Review→Validate).
4. **THEN the rest, by logical priority.**
5. **Hand off to Droids (Robot Mode)** — one droid per non-colliding group, in parallel;
   draft PRs; operator merges.

Today only role→cost-ranked routing + cross-vendor failover exist (single unit,
sequential). The **gateway (v0.2.0)** is the prerequisite that makes N parallel agents
sustainable (spreads load across providers).

**PARKED — do NOT schedule:** Windows `.exe` packaging (future); deny-list guard fix
([[charon-push-guard-gap]], operator-only settings edit). The operator will route droids
through the Charon gateway when Claude Code weekly limits hit, to keep working.

See [[remaining-work-includes-designed-not-built]], [[charon-vision-gateway-first]],
[[charon-project-state]].
