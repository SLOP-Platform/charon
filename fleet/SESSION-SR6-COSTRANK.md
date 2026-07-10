# Build session — #6: auto-derive cost_rank + cost_class (routing defaults go cheap-first)

You are a Charon build session (strong coder — DeepSeek V4 Pro / Kimi K2.6). Repo: `/home/stack/code/charon`.

## MANDATORY isolation (Fleet-Droid process — no exceptions)
1. `git worktree add /home/stack/code/charon-sr6 -b feat/sr6-auto-cost-rank master`
2. Register on the session-bridge (repo:"charon"), claim this ticket, announce you OWN `src/charon/gateway.py`, `src/charon/config.py`, model-registry schema. Work ONLY in `charon-sr6`. Do NOT touch `proxy_server.py`.

## Scope
SR-5b made per-token cost real (`cost_input`/`cost_output` in the model registry). Make routing cheap-first automatically instead of the hand-set `cost_rank:1000`:
1. In `gateway.py::_build_routes_and_pools`, DERIVE each model's effective `cost_rank` from `cost_input`/`cost_output` (blended, e.g. 3:1 in:out) when present; genuinely-free models (`free:true`) still sort first (keep the `(not free, cost_rank)` contract).
2. Add a **`cost_class`** field to the registry schema + honor it: `free-daily | expiring | prepaid | metered | premium`. `premium` (GPT-5.5 / Opus-class) is GATED OUT of default-primary — usable only when explicitly requested or in a premium role, never the cheap-first default.
3. Preserve all existing behavior (per-model overrides, the gpt-5.5-or-first quirk). Add unit tests: derived-rank ordering, free-first, premium-not-default, missing-pricing fallback.

## Gate + finish
Run BOTH `python3 -m charon.cli gate` AND `PYTHONPATH=src python3 -m pytest -q`. Commit to `feat/sr6-auto-cost-rank`. **DO NOT push or open a PR** — a Claude reviewer + operator gate every merge (this is money-path/routing). Report branch + test counts + the cost_rank formula you used. No fleet/SLOP/personal strings in `src/`. **D&S:** owns gateway.py+config.py; disjoint from #5 (proxy_server.py) + #17 (new balance.py); #19 sequences AFTER this.
