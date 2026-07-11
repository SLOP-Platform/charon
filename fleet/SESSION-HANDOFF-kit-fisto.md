# SESSION HANDOFF — kit-fisto → next manager (2026-07-11, session end)

## Bootstrap (paste this as the next session's first message)
```
Read and fully follow /home/stack/charon-private/fleet/SESSION-HANDOFF-kit-fisto.md — you are the fresh Charon fleet MANAGER.
```

## SHIPPED / DONE this session
- **ROUTER lint+mypy gate-debt cleared** and pushed to `origin/master` @ **`5f6f580`** (was `d463d73`). Full `charon gate` (ruff + mypy + boundary) exits 0. This fixed the FAILED v0.5.0 release, whose gate died at the lint step because tonight's R3/R8/R17 waves were verified pytest-only, not with the FULL gate.
- KSF MVP: KS3 Graphify + KS4 inert-code gate merged into the local `keystone` repo (separate repo; its HEAD is the KS4 merge).
- Meter finding confirmed by reading the code + recorded (see NEXT #1).

## NEXT — first actions, in priority order
1. **METER = #1 remediation (operator's explicit priority).** The per-provider cost meter is INERT: `BalanceTracker` is never constructed from config (`cfg.balance_tracker` stays `None`), so the `record_spend` calls in `/home/stack/code/charon/src/charon/forwarder.py` (lines 467/561) never fire and the ledger is EMPTY (the code says so itself at `/home/stack/code/charon/src/charon/balance.py` ~line 170). FIRE: construct a real BalanceTracker from provider config, wire it into the gateway build in `/home/stack/code/charon/src/charon/gateway.py`, prove the ledger fills under a real-traffic probe (green-is-not-proof), then `cost_rank.derived_cost_rank(metered_cost)` yields real "which provider is cheaper" numbers. Also fix the `est_cost` fabricated-floor.
2. **DEPLOY is HELD** by operator until the meter is real. Do NOT deploy. When ready, re-tag **v0.5.1** (v0.5.0 is a dead tag — its release failed, no image published) and run the deploy recipe; back up `/data` on `.60` first.
3. **KSF → private repo `SLOP-Platform/keystone` (KS6)** — operator APPROVED private. GATED on `ksf gate` being green on KSF itself, which needs the **KS4 inert-code false-positive fix** (still running as a detached NW `opencode` job at session end; watch `/home/stack/charon-private/fleet/state/overnight/KS4-INERT-FIX.log`). Only push once KSF passes its own gate.

## GOTCHAS / avoid / DENIED
- **RUN LEAN — minimize token use.** Operator directive: keep the inline session terse (no walls of text, tight tool use, delegate substantive work to sub-sessions that return pointers-to-files, not pasted payloads). We are NOT in max-burn mode.
- **NEVER verify a merge with pytest alone** — use the FULL gate: `PYTHONPATH=src python3 -m charon.cli gate`. Pytest-green ≠ gate-green (that is exactly how the v0.5.0 release broke).
- **NW now costs real money** — base 6kWh spent, into the **$22 PAYG (~$19 and falling)**. Be sparing; do mechanical work inline, not via NW jobs.
- Raw `git push` / `reset --hard` / `git checkout` in the main tree may be permission-DENIED. Push only via the lever: `bash /home/stack/charon-private/fleet/land-push.sh <branch> [repo]`.
- Do NOT commit into mediastack's working tree (an active SLOP session has uncommitted WIP there).
- Time estimates from prior sessions were unreliable — do not promise ETAs; say "when it lands".
- Two leftover keystone worktrees exist (`/home/stack/keystone-wt/graphify`, `/home/stack/keystone-wt/inert`) — clean up when convenient.

## session-bridge
No active SESSION-BRIDGE sessions at handoff. Register on the session-bridge if coordinating with a SLOP session; pass `repo:"charon"`.
