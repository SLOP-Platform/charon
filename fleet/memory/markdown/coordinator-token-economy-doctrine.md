---
description: "mechanical coordinator operating contract for sessions of ANY model — delegate on threshold, sub-sessions write-to-file + return pointers, never paste payloads back; minimizes token burn + keeps coordinator context lean"
metadata: 
name: coordinator-token-economy-doctrine
node_type: memory
originSessionId: aaf1f929-5adf-4f7f-862d-792cd64617af
type: feedback
tags: [doctrine, token-economy]
last_referenced: 2026-07-13
---
STATUS: **v2 APPROVED 2026-07-08** after adversarial review (4 lenses + empirical measurement). The 8 rules below were NARROWED; authoritative version = `/build-rig/fleet/COORDINATOR-DOCTRINE-v2.md`. ROLLOUT PENDING operator go (not yet in any rig). Key corrections vs the v1 rules below: (1) it preserves COORDINATOR-CONTEXT + parallelism, it does NOT reduce total system tokens (usually raises them); (2) trigger = est. ~10k context-residue floor NOT file/line — dropped "any edit / any grep" as auto-triggers, added wall-clock (<~2min→inline) + session-phase (near handoff→inline) gates; (3) return = structured VERDICT+CONFIDENCE+UNVERIFIED, with must-read-full carve-outs at high-stakes gates C1–C7 (security / money-path / review-verdicts / merges+public-push / operator-override / DTC-design-of-record / cross-sub-consistency) + artifact-citation anti-rubber-stamp + independent re-verify for security/money; (4) strong-model-only auto-delegation, weak coordinator is NEVER the sole gate (whitelist/escalate); (5) chain-depth cap 1, backgrounding required (foreground ~12× slower), sub-agent ≠ droid ([[manager-never-spawns-droids]] preserved). Open decisions deferred: residue number (~10k default), strong/weak model→tier mapping (deferred to the [[benchmark-not-a-valid-ranker]] real-outcomes grades), weak-coordinator whitelist, hook thresholds, R-estimator, reconciliation ownership.

FEEDBACK (operator, 2026-07-08): the way the manager works — delegate substantive work to background sub-sessions, have them WRITE findings to files and return only short pointers, keep the primary context lean — should be **mechanized and propagated to SLOP sessions too** (which run VARIOUS models, some weak, so the rules must be mechanical thresholds + a hard output format, NOT "use judgment").

**The contract (any-model coordinator):**
1. Role = COORDINATOR, not worker: gate / sequence / commit / push / dialogue only.
2. Mechanical delegation trigger: task needs >1 file OR >~150 lines OR any code edit OR any repo search → spawn a background sub-session; don't read it yourself.
3. Hand the sub-session the FACTS (exact paths, ticket intent, acceptance) so it never re-investigates what's already known.
4. HARD output contract: "Write findings to `<file>`; your reply is ONLY `FILE: <path>` + ≤5-line summary; never paste file contents/logs/code back." → the big payload stays on disk, only the pointer enters coordinator context.
5. Context hygiene: targeted reads (grep / offset+limit), never `cat` a whole file or echo large output; read a report file only when actually gating on it.
6. Batch & parallelize: independent tasks fan out in one shot; touch each file once; one commit/push per batch; never two writers per file.
7. Right-size the model: cheap model for mechanical work, strong model for security/money-path/gate-critical.
8. State lives on disk (tickets / reds / report files) so sessions stay cheap and stateless.

**Weak-model caveats:** (a) do NOT trust a weak model with the gate/review decision — route review of significant code to a strong model or the operator; (b) weak models drift from the output contract — enforce it structurally (launcher/hook rejects pasted code) not by asking politely.

**Why:** minimizes token burn and keeps the coordinator's window small so it can run long and cheap. This is the manager doctrine mechanized — the same intelligence [[charon-work-composition-intelligence]] is meant to eventually bake into the product.

**How to apply:** I embody it in every session; propagate it to SLOP (mediastack) sessions via an injected rules file (public-repo-clean — no `~` paths). Related: [[manager-delegates-to-subsessions]], [[optimize-execution-wallclock-tokens]], [[subsession-model-and-token-policy]], [[all-work-in-subsessions]].
