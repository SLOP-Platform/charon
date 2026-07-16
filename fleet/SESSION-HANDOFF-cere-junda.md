# Charon Fleet — Session Handoff — cere-junda (2026-07-16)

**Session:** cere-junda
**Rig HEAD committed@:** 05c7d0f (both charon-private + code/charon clean, pushed to origin/master)

## Bootstrap (paste into next session)
```
Read and fully follow /home/stack/charon-private/fleet/SESSION-HANDOFF-cere-junda.md — you are the fresh Charon fleet MANAGER, carry it out, then flip to fleet mode.
```

## FIRST ACTIONS (priority order)
0. **Read `fleet/STARTUP-FRICTION-LOG.md` FIRST + run its BOOT CHECKLIST** (new — durable boot-problem memory; fix recurring items; append your own entry at session end).
1. `git -C /home/stack/charon-private pull --ff-only origin master` AND `git -C /home/stack/code/charon pull --ff-only origin master` (masters DRIFT).
2. **`bash fleet/foreman.sh`** — surfaces tier starvation + WHY, loudly (built this session, 8/8 tests, wired into `preflight.sh`). `--fix` clears provably-safe stale blocks. #1 fix for the recurring "tabs idle / board starved" problem.
3. **Feed the idle tabs.** At handoff the board was STARVING (all tiers 0 claimable) — most ready work is consumed or blocked. Refill: land open PRs (auto-done-marks → cascade-unblocks) + un-park/serial-justify the P0 chain.
4. **Money/important/routing PRs get a FOCUSED ADVERSARIAL REVIEW before land** — not just gate-green.
4b. **Before building ANY new tool: REUSE-CHECK it doesn't already exist** (operator directive) — audit `TOOL-INVENTORY.md` + a FRESH graphify map (`GRAPHIFY-MAP-FRESHNESS` boarded — refresh the stale map first). Don't reinvent.
5. **HIGH-PRIORITY INVESTIGATION (operator directive): `GATE-CREATION-STANDARDIZE` (boarded, frontier).** Research every case where a GREEN gate missed a real issue (this session had several) → build a durable `GATE-GAP-LEDGER.tsv` (appended on every future miss) + a standardized gate-creation checklist + a meta-gate. Goal: eliminate issues at the CLASS level, not one-off. Read the ticket for scope.

## DELIVERED THIS SESSION (headlines)
- **The FOREMAN** (`fleet/foreman.sh`): claimability + composition monitor — confirm-first, blast-radius-aware, LOW-water warning; composes claim/validate_board/parallelizability/wci; 8/8 tests (fail-on-revert), dogfooded, **wired into preflight scan** (auto-surfaces STARVE/LOW/COLLISION). Doctrine: run after every feed.
- **Class-level fixes landed:** inert-gate **determinism**; land.sh **false-DONE fix + auto-done-mark self-heal + merge-pacing**; done.sh **2min→1.2s + repo-aware**; **stiffness class** (shared `failover_loop`, all 4 callers); **memory store + memory-wire (ends MEMORY.md wholesale dump)**; **config-SSOT**; **gh-cache** (batch merged-PR lookups → fixes API rate-limit exhaustion).
- **ADR-0016 switchboard:** `DELETE-STATIC-RANK` (gateway half) **LANDED**; `FLEET-DEMAND-DRIVEN-ROUTING` boarded. **DEPLOY NOT DONE — see gotcha.**
- **Audits:** SLOP+KSF rule-port (337 rules, two-way gate #76); reorg (**21 retired**); perf (5m46s preflight → fix); wiring-gap (inert catalog-detector → CATALOG-GATE-WIRE).
- **Doctrine:** SLOP blast-radius/§6/independent-review; 5 core principles; slowness-is-a-trigger; foreman-after-feed; startup-friction-log.
- **GitHub-limits:** batch-cache + land-pacing landed; GITHUB-LIMITS-HARDENING open (search-API 30/min, large-file guard). Runners: 4-LOM has headroom (12 cores, load ~0.9) — can add ~3 more (operator registers).

## KEY OPEN / GOTCHAS
- **🔴 ADR-0016 deploy is UNSAFE as-is (money exposure).** Adversarial review (`fleet/session-notes/adversarial-delete-static-rank.md`): purging `cost_rank` from live 4-LOM `/data/models.json` collapses any un-priced model to the 1000 fallback → route-to-pricier leak; override removed; no priced-completeness preflight. **DO NOT purge cost_rank on 4-LOM until `ADR0016-DEPLOY-PRICED-COMPLETENESS` (boarded) lands.** Landed CODE is safe; the DEPLOY is the risk.
- **CONFIG-SSOT-PROPAGATE** (boarded, write-path DECIDED = docker exec into charon-gateway-1 /data).
- **Stuck PRs:** rig #47 (mergeable=UNKNOWN), #62 (CONFLICTING + stray .pyc, needs rebase); product #86 (public-clean SHA-pin false-pos), #135 (retry — its contract-test fix landed).
- **git push DENIED to manager** — use `land.sh`/`land-push.sh`. `git rebase`/`merge` in a COMPOUND bash cmd trip a permission prompt — run as a single command.
- **land.sh false-DONE on a fresh PR:** mergeability=UNKNOWN briefly → land.sh correctly refuses; retry once it computes.
- **GitHub secondary content-creation limit** trips on burst lands — `gh api rate_limit` shows exact reset (free call); land.sh now paces.

## session-bridge
- No active bridge sessions at handoff (single manager session cere-junda; no coordination sessions in flight). Next session picks a fresh name; do not re-register cere-junda.

## STATE
- Both repos clean, pushed to origin/master. Board STARVING at handoff (refill = first-action #3). No sub-sessions running (all closed).
- **Code map (graphify) is STALE** — product graph last built 2026-07-13 (missing this session's failover_loop/context_shaper/memory modules); rig has NO graph. `GRAPHIFY-MAP-FRESHNESS` boarded to auto-refresh; run `graphify update /home/stack/code/charon` before relying on reuse-check/review.
