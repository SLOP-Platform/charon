# SESSION HANDOFF — barriss → next manager

**Date:** 2026-07-13

## Bootstrap (paste this as the next session's first message)
```
Read and fully follow /home/stack/charon-private/fleet/SESSION-HANDOFF-barriss.md — you are the fresh Charon fleet MANAGER.
```

## SHIPPED / DONE this session
- **Routing root-cause SOLVED (not a redesign):** cheapest-provider-per-model + roll-on-exhaust is **BUILT + LIVE**; the "-ds/-go/-ng" are provider-pinned aliases over ONE base model, NOT pools. The failures were **stale config DATA** (dead providers ranked cheapest). `.60` stopgap applied + verified — `deepseek-v4-pro`/`-flash` now route to `deepseek` (funded direct), **0 failovers**. See memory `pool-is-single-source-already` + `fleet/state/POOL-INVESTIGATION.md`.
- **ADR-0016 — demand-driven capability match (zero static rank)** landed to product master (PRs #96 + #97). Pricing decision: **adopt** LiteLLM `model_prices` (MIT) + OpenRouter `/models` + changedetection.io (Portkey = secondary cross-check); off-hot-path, bottleneck-SAFE. Evidence `fleet/state/PRICING-TOOLS-EVAL.md`.
- **F29 COMPLETE** — all 3 slices merged to product master `085e74f`: providers-data (#98), config-package (#99), module-registry (#100). Behavior-preserving (presets byte-identical; declarative `_MODULE_SPECS`). **Unblocks the R46 serial chain.**
- **Off-Claude fleet PROVEN + hardened:** droids build via the gateway (`CHARON_AGENT_CMD` → `charon-run.sh` → `opencode --model charon/*`, ZERO Claude); leak-guard (`fleet/checks/no-claude-executor.sh`) + operating-rule §9 landed. Multi-repo harness (`repo:` field, `repo-registry.sh`) + `charon-private` repo support landed. A1 (land-push gated) + B4 (branch-reaper) landed.
- **DSV4pro offloaded** — `tier-models.tsv` (PR #18): DSV4pro is frontier-only; strong/economy are free-first (deepseek-flash-free, minimax-m3-free, gpt-5.4-nano) with a paid backstop. New models added to the opencode client map + smoke-verified.
- charon-private master `7de44cf`. Memories added: `pool-is-single-source-already`, `gates-must-actually-run`, `gateway-client-agnostic`, `slow-lean-primary-channel`, `evaluate-tools-by-code-not-stars`.

## NEXT / IN-FLIGHT WAVE (first actions, priority order)
1. **The demand-driven build wave is ALREADY RUNNING** — 2 droids (frontier + strong) launched **detached** (`setsid nohup`, survive `/quit`), draining the board off-Claude. Currently building **PRICE-REFRESHER** (adopt, not build) ‖ **FAIL-LOUD-CONTRACT** ‖ **R46-BALANCE-WIRE** (unblocked now F29 is done); then the serial chain continues **R46 → R11-DRAIN-THEN-PARK → DELETE-STATIC-RANK**. **Your job: monitor + REVIEW every draft PR with the FULL CI gate** (see gotchas), then land; add tabs (`fleet-droid.sh <tier> --wait 3 --retries 10`) or stop (`pkill -f fleet-droid.sh`) as needed. Check `fleet/state/claims/` + `fleet/state/droid-logs/` + `gh pr list --draft` on both repos for progress.
2. **`.60` restart** to apply the staged batch: `gemini-3.1-flash-lite-or` + `morph` (provider+key+model) + `zai` (provider+key+glm-4.7/4.5-flash) — all staged in `/data/*.json` with `*.bak-*` backups. Restart is docker-gated; do it when the fleet is IDLE (it kills in-flight builds). Then verify each routes, add to the opencode map + tier-models.tsv free-first.
3. **v0.5.1 deploy** (cost-rank-auto) — ready; `deploy.sh` preflight fixed. Operator bump `pyproject` → tag `v0.5.1` → `fleet/deploy.sh v0.5.1`. Dormant until R46 wires the meter. See `fleet/state/V050-DEPLOY-VIABILITY.md`.
4. The demand-driven E2E acceptance is in ADR-0016 (`docs/adr/0016-*.md`): cheapest live provider wins · drained rolls+parks · no-provider fails loud · price flip re-orders with no hand-edit.

## PENDING / PARKED (operator)
- Draft PR **#101** (WORK-CONVERGE-REVIEW, docs-only review-log) — review/land or close.
- **CommandCode** — parked (Go plan 403s the API); wire `enabled:false` when operator supplies base_url or upgrades to the Provider plan.
- **OpenRouter `:free` models** (Hy3, Nemotron 3 Ultra, Gemma 4 31B…) — add to pool free-first (OpenRouter `?q=free`).
- **Keys:** ZAI (saved, valid), MORPH (saved, valid — **EXPOSED in chat → rotate in Morph dashboard**), NW (never saved — operator deferred). Use the visible `read -r` recipe (not `-s`).
- **Pricing dogfood targets:** `fleet/state/PRICE-REFRESHER-DOGFOOD.md` (chutes.ai = existing provider, top priority) — validate the tool against real pages once PRICE-REFRESHER + R46 land.
- **Elevate R43 / R44 / R45** (real-path / dogfood / inert-startup gates) — the durable fix for the ghost-bug class the operator flagged (we verify proxies, not reality, once not continuously). Operator's call to pull forward.

## GOTCHAS / avoid / DENIED
- **land.sh gate < CI gate** — `land.sh` runs `charon.cli gate` but NOT the full `pytest`; it missed an arch-lint circular-import AND a fixed-port test flake on F29 (#98/#100). For PRODUCT PRs: mark ready → let CI run → **wait for the `gate` check SUCCESS then `gh pr merge`** (SLOP-Platform/charon has branch protection; auto-merge is DISABLED). Fold "land.sh product gate == full pytest" into A1's follow-up.
- Merges via `fleet/land.sh` ONLY (raw `git merge`/`push` denied). Its step-7 local sync fails harmlessly when landing from a worktree ("master already used by worktree") — the origin merge still happened.
- **docker is operator-gated locally, BUT `ssh -i ~/.ssh/4lom stack@10.0.1.60` + `docker exec` WORKS** — the manager edits `/data/{models,pools,providers,fallback,secrets}.json` there directly. The RESTART is the consequential step — never restart mid-fleet-build.
- **Meter is INERT** ($0 across 4.8M tokens) — R46 un-inerts it; free-first ordering can't be validated by real spend until then.
- `.60` config is deploy-drifted from the repo (live = v0.4.1 + the stopgap retune). Edit `/data`, not just the repo. Backups: `*.bak-*`.
- **AUTONOMOUS lever ON** (`fleet/state/AUTONOMOUS`) — land.sh pushes without asking.
- Adversarial review is STANDING for all money-path/harness work — it caught real defects behind green builds every time this session.

## session-bridge
No active SESSION-BRIDGE coordination sessions at handoff. The bridge daemon still runs OLD code (restart = a deploy; low priority).
