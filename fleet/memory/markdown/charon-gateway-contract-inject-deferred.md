---
description: DEFERRED — gateway contract-injection for CG behavioral steering; build ONLY when cg-drift.sh fires (>=2 CG discipline failures in 30d); high blast radius
metadata: 
name: charon-gateway-contract-inject-deferred
node_type: memory
originSessionId: e2478a55-c53f-48cc-9378-5c328f54aa8f
type: project
tags: [charon, gate, gateway]
last_referenced: 2026-07-13
---
**Decision (2026-07-11):** the session-guardrails design (`fleet/PROPOSAL-SESSION-GUARDRAILS.md`) DEFERS "step-3 gateway contract-injection" — injecting a process-discipline system message into every CG request at `forwarder.py:113-123`. It's the only lever that steers CG sessions *behaviorally at runtime*, but it sits on 100% of the money path and a provider 400 on the extra system turn is in the no-failover set → high blast radius. So we bet the STATIC-doc doctrine (folded into `MANAGER-OPERATING-RULES.md`, referenced by JOIN-PROMPT + CG AGENTS.md) steers CG well enough, and defer the risky runtime inject.

**How we remember / when to build it:** mechanized wake-trigger `fleet/cg-drift.sh` (surfaced by `preflight.sh:detect_cg_drift`). Every CI/land-push rejection of CG-produced work for a discipline reason is logged (`cg-drift.sh log <ticket> <discipline>`). When **≥2 events in a rolling 30 days** (operator-set threshold), the gate FAILS LOUDLY and points here + to the proposal. Also parked board ticket `GATEWAY-CONTRACT-INJECT`.

**When building it (only after the trigger fires):** HARDENED — flag-guarded, **real `try/except` fail-open** (the `forwarder.py:121` precedent has none), byte-identical-off, additive-only, size-capped; keep contract text generic (no repo internals — `[public-repo-no-personal-info]`).

Related: [[charon-silent-downgrade-leak]], [[product-vs-build-rig-boundary]], [[always-give-exact-command]].
