# SESSION HANDOFF — shaak-ti → next manager (2026-07-11)

**Date:** 2026-07-11 17:10 PDT

## Bootstrap (paste this as the next session's first message)
```
Read and fully follow /home/stack/charon-private/fleet/SESSION-HANDOFF-shaak-ti.md — you are the fresh Charon fleet MANAGER.
```

## SHIPPED / DONE this session (all pushed to charon-private origin/master)
- **F21** — fleet pytest gate stopped collecting the benchmark fixture tree (59-error red) via a repo-root `pytest.ini norecursedirs`; retired the cwd-fragile conftest. `9a70ed1`.
- **project-audit.sh** — mechanized scan-before-build gate (board + branches + commits + briefs; exit 2 on prior work) + preflight `detect_inflight_landscape`. `c24d85f`. Then adversarially reviewed → **false-negatives fixed** (spaced/underscored/suffix queries + regex-metachar + base-ref robustness). `d2fabdf`.
- **Session-guardrails design (DTC-approved) + cg-drift wake-trigger.** `2b12291`. Files: `/home/stack/charon-private/fleet/PROPOSAL-SESSION-GUARDRAILS.md`, `/home/stack/charon-private/fleet/cg-drift.sh` (+ preflight `detect_cg_drift`), parked ticket `GATEWAY-CONTRACT-INJECT`, meter brief `/home/stack/charon-private/prompts/drain-and-park.md`.
- **KSF linter-tools review** → NO-GO, but premise corrected: KSF stdlib-only = CORE only; PLUGINS wrap industry best-in-class first (memory `ksf-modular-plugin-best-in-class`).
- **KS4 inert-code false-positive fix** — the detached CG job finished and committed on **keystone `main`** (SHA in the report); it is **UNVERIFIED and unpushed**. Report: `/home/stack/charon-private/fleet/state/overnight/KS4-INERT-FIX-REPORT.md`.
- **Memories saved:** `ksf-modular-plugin-best-in-class`, `charon-gateway-host`, `charon-gateway-contract-inject-deferred`, `session-guardrails-two-tier`.
- 5 guardrail tool evals + 4-lens DTC reports live LOCAL-only in gitignored `fleet/state/reviews/` (conclusions are in the committed PROPOSAL + memories).

## NEXT — first actions, priority order
1. **BUILD the approved guardrails** (design of record: the "DTC OUTCOME" block at the top of `/home/stack/charon-private/fleet/PROPOSAL-SESSION-GUARDRAILS.md`): **D1** make `charon.cli gate` a *required* CI branch-protection check (the real, un-bypassable, CG-reaching enforcement); **D3** add the money-path review-record gate to `/home/stack/charon-private/fleet/land-push.sh` (`--override` escape); **D4** fold the 4 disciplines into `/home/stack/charon-private/fleet/MANAGER-OPERATING-RULES.md` as one SSOT that JOIN-PROMPT + CG AGENTS.md reference. Then the **backfill review-debt audit** (ranked list). The git pre-push hook is **REJECTED — do not revive** (see memory `session-guardrails-two-tier`).
2. **METER (drain-and-park)** — folded build brief authored at `/home/stack/charon-private/prompts/drain-and-park.md` (METER-Wave2 → DRAIN-ROUTING → DRAIN-THEN-PARK; sole-leg guard). WAITING on operator's model + timing. Run on **CG**, not Claude. Adversarial review of the sole-leg guard mandatory before merge. Wave-1 observer/cost-rank meter is already merged — do NOT rebuild it.
3. **KS4 VERIFY (green-is-not-proof)** — in the keystone repo: `ksf gate` must exit 0 on clean KSF **and** a truly-orphan fn must still fail it; read `/home/stack/charon-private/fleet/state/overnight/KS4-INERT-FIX-REPORT.md`, do NOT trust its SUCCESS line. Only then **KS6** (keystone → private `SLOP-Platform/keystone`).
4. **v0.5.1 deploy HELD** until the meter is real (operator directive).
5. **GR11 Agent session channel** — operator wants DTC critics to talk/argue directly (today it's blind fan-out + manager synthesis). Scoping only; needs session-bridge-for-subagents or shared-file rebuttal rounds.

## GOTCHAS / avoid / DENIED
- **Adversarial review / DTC is standing for all key work** — it caught the git-hook design as brick-every-push + product-leak BEFORE any code. Money-path work is not merged without it. Downgrades stated, not silent.
- **Verify exit codes PIPE-FREE:** `cmd; echo $?` — NEVER `cmd | tail; echo $?` (that reads tail's exit; it bit us this session). Mechanizing this is the parked `HANDOFF-PIPEFAIL` ticket (`set -o pipefail`).
- **Run the audit before building:** `fleet/project-audit.sh <TICKET>` before authoring/launching — it caught the METER collision this session. Preflight surfaces the landscape.
- **Charon gateway is at `10.0.1.60:8080`, NOT localhost** (recurring waste — memory `charon-gateway-host`).
- Push only via `/home/stack/charon-private/fleet/land-push.sh <branch> <repo>`; raw `git push` is DENIED.
- **reviewer ≠ builder is UNVERIFIABLE** in this solo setup (single git identity) — gates can require "a review record exists," not enforce independence.
- **NW costs real money** — KS4 ran on it; be sparing with CG jobs on paid providers.
- Do NOT commit into mediastack's working tree (active SLOP WIP).

## session-bridge
No active SESSION-BRIDGE sessions at handoff. Register (`repo:"charon"`) if coordinating with a SLOP session.
