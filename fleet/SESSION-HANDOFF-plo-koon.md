# HANDOFF — 2026-07-10 (session plo-koon) — Charon fleet MANAGER

## Bootstrap (paste as the next session's first message)
```
Read and fully follow /home/stack/charon-private/fleet/SESSION-HANDOFF-plo-koon.md — you are the fresh Charon fleet MANAGER
```

## ⚡ ACTIVE DIRECTIVES (honor immediately)
- **ALL sub-sessions run on NeuralWatt** until the sub expires: `opencode run --model charon/glm-5.2-nw` (or `kimi-k2.6-nw`). These are NW-primary (fallback opencode-go only if NW is unreachable). Both were added to the opencode charon model map this session. DRAIN the 6 kWh included allotment **until 7/23 03:30 UTC**; AFTER that, keep using NW to drain the **$22 PAYG** at $10/kWh (does not expire); park NW only when $22 hits ~$0. Reminder routine set: `trig_01U4mjVGBm8VRK3hFTMMLNCE` (fires 7/23 03:30 UTC).
- **HARD project priority (default sequencing):** ROUTER > BRIDGE > FLEET > SECURITY > BACKLOG. Overrides that jump the queue: acute security incident, a dependency that blocks a higher item, a hard deadline, a broken rig/gate. (In MANAGER-OPERATING-RULES.)
- **Fold, don't proliferate:** every new ticket folds into one of the 5 Projects; new project only on a STRONG case + re-analysis. Mechanized by PROJECT-MEMBERSHIP-GATE ticket.

## STATE — SHIPPED THIS SESSION (all committed + pushed; fleet master `e945926`)
- **ROUTER project created (priority #1), R1–R17** — the cost/capability routing brain. Design of record: `fleet/state/ROUTER-DESIGN.md` (price-sorted cheapest-first; fail over on exhausted/problem/slow; capability matrix incl. openrouter✗reasoning; North Star = throttle-as-backpressure + degradation alert + auto-recover on refill; two-bucket NeuralWatt funding; balance source = poll the provider's own usage API; R17 pricing-limits-checker). Free-tier order (R15) done: `fleet/state/FREE-TIER-ORDER-REVIEW.md`; verified limits: `fleet/FREE-TIER-ROUTING.md`.
- **Roadmap is now WAVED** (Projects → Waves → tickets) for all 5 projects in `fleet/state/ROADMAP.tsv`; `fleet/report.sh` renders it and **`fleet/end-session.sh` prints it on screen at close**. (The prior session's "new format" was lost because the wave data never persisted — restored this session.)
- **NeuralWatt reframed correctly:** $20/mo Basic sub = 6 kWh included (use-or-lose, resets 7/23) + separate $22 PAYG at $10/kWh. Break-even vs PAYG ≈ 2 kWh/mo; do NOT resubscribe post-7/16 (renews to PAYG parity); evaluate the new FLEX (latency-tolerant) tier for async fleet work.
- Doctrine added: token-economy DEFAULT, lever-gated push, session-end roadmap print, HARD priority, fold-don't-proliferate.

## FIRST ACTIONS — NEXT (priority order)
0. `bash fleet/preflight.sh`; register on the session-bridge under a NEW Jedi name. Launch ALL sub-work on `charon/glm-5.2-nw` (NeuralWatt).
1. **APPLY THE STAGED FOLD.** A Charon sub-session is producing `fleet/state/ROADMAP.tsv.new` (folds the 53 auditor tickets into the 5 projects, BENCH-OOB-GRADING→ROUTER, deletes 5, projects in priority order, waves assigned). When it lands: VERIFY (row count vs old, `ROADMAP_TSV=fleet/state/ROADMAP.tsv.new bash fleet/report.sh` renders, no ticket lost), then `mv` it over `fleet/state/ROADMAP.tsv`, ADD rows for PROJECT-MEMBERSHIP-GATE and WEB-ROADMAP-GENERATOR (FLEET), confirm the 5 deletes moved to `fleet/board/retired/`, commit + push. Proposal + rationale: `fleet/state/NON-PROJECT-AUDIT.md`.
2. **ROUTER (top priority)** — start the critical path: R4 meter-wire → R5 cost-rank-auto → R2 router-core + R3 capability-matrix (see ROUTER-DESIGN.md). R11 drain-then-park is what makes the NeuralWatt balance-drain automatic.
3. **WEB-ROADMAP-GENERATOR** (FLEET) — persistent self-refreshing web roadmap (regenerate HTML from ROADMAP.tsv + republish the Artifact at session end). Artifact url: 255411a5-edda-46c1-aded-a23b6d53811d.
4. Then BRIDGE (portable work-engine B5/B6/B7), FLEET polish, etc., per priority.

## GOTCHAS
- Push is LEVER-GATED: `bash fleet/land-push.sh <branch> [repo]` (lever ON → pushes; raw `git push` denied; `--force`/`reset` forbidden).
- Two repos: PRODUCT `/home/stack/code/charon` (public SLOP-Platform/charon); FLEET `/home/stack/charon-private` (private).
- `charon/glm-5.2-nw` failed at first because it wasn't in opencode's curated map — now added. If a `-nw` model errors "UnknownError", confirm it's in `~/.config/opencode/opencode.json` provider.charon.models.
- Roci SSH: `ssh rocinante` (NOT bare stack@10.0.1.51). 4-LOM SSH: `-i ~/.ssh/4lom`. Gateway: `10.0.1.60:8080`. Access is auto-reported at boot by `fleet/access-check.sh` (in preflight).

## SESSION-BRIDGE
Was `plo-koon` (unregistered). Next session registers under a NEW Jedi name.

## Open questions
None blocking. The staged fold + the two un-rowed tickets (PROJECT-MEMBERSHIP-GATE, WEB-ROADMAP-GENERATOR) get their ROADMAP rows when the fold is applied (action 1).
