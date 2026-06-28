# Charon — Session Handoff (2026-06-28)

Resume doc for a fresh MANAGER session. Read `/home/stack/.claude/projects/-home-stack-code-charon/memory/MEMORY.md`
+ this + `/home/stack/charon-private/fleet/WORKFLOW.md` first, then run
`bash /home/stack/charon-private/fleet/board.sh` · `validate_board.sh`.

## STATE — board FULLY CLEAR (no active tickets, no open PRs)
The autonomous-ticket-runner cluster shipped + was **certified live** this session. Backlog is
ticketed, optimized into waves, and parked.

## SHIPPED THIS SESSION (merged #68–#75)
- **#68 WGW** — `charon work` forwards `CHARON_GATEWAY_TOKEN` to the spawned acp agent (fixed 401).
- **#70 BEARINGS + #71 BEARINGS-WORKPATH** — agent dispatch carries ticket body + acceptance
  criteria end-to-end (on base `WorkUnit`, boundary-clean).
- **#69 WORK-LAND-PR** — `charon work --open-pr` (off-by-default, fail-closed) opens a DRAFT PR per
  propose-unit, NEVER auto-merges; wires the real `GatewayReviewer`.
- **#72 CLIENT-CONNECT** — `charon connect <opencode|omp|aider>` one-command client wiring.
- **#73 WORK-OBSERVABILITY** — live progress→stderr (`--progress/--quiet`) + `charon runs`.
- **#74 WORKTREE-ADD-FORCE · #75 SECRET-SCAN-ENVVAR-FP · #67 TEST-PORT-FLAKE** — backlog fixes.
- **Rig fixes:** `fleet-droid.sh` launcher now AUTO-OPENS PRs (commit-subject title, not `--fill`);
  gate command is `mypy src tests` everywhere (matches CI — caught only by #72's red).
- **LIVE PROOF CERTIFIED:** non-Claude agent worked a real ticket via `charon work` — authenticated,
  full bearings, edited+committed, accept gate passed, gateway served 13→17. (Detail in
  `charon-project-state` memory.)

## STANDING RULE (NEW, mechanized) — Dependencies & Sequence (D&S)
Every SLOP + Charon ticket MUST open with a `## Dependencies & sequence` section (depends_on / wave
/ concurrency-safety) so a fresh processor sequences it without collisions. **Mechanized:**
`validate_board.sh` HARD-FAILS any live ticket whose prompt lacks it; `WORKFLOW.md §4` requires it.
(memory `ds-standing-rule`.) SLOP-side audit/mechanization was delegated this session — see status
below.

## OPTIMIZED BACKLOG (parked; waves — see `fleet/OPTIMIZATION-PASS.md` for the full analysis)
All buildable tickets are SOLE writers of their files (no collisions); sequence is encoded in each
ticket's `depends_on` + `## Dependencies & sequence`. Unpark = `mv <id>.md.parked <id>.md`; launch
`fleet-droid.sh <tier> --wait 3 --retries 10` (operator opens tabs; launcher auto-opens PRs).
- **Wave 1 (all disjoint — launch together):** ADR-0015 [opus,doc], DSGN-WCI-PROOF [opus,design],
  OBS-CAPTURE [sonnet, acp.py], OBS-UI [opus, proxy_server], CLIENT-CONNECT-GUI [sonnet, connect.py],
  ORCH-ROUTE [opus, api+agent_launch], OHMYPI-ASSESS [sonnet, research].
- **Wave 2 (after ADR-0015):** WCI [opus, engine/{reconcile,scheduler,board}.py].
- **Wave 3 (after WCI + DSGN-WCI-PROOF approved):** WCI-FOLLOWON [opus, auto-slice; LARGE, deferred].
- **Wave 4 (after all above):** ATC [opus] — adversarial audit of ALL committed work → findings +
  fix tickets (owns nothing, runs last).

## ALSO PARKED (older on-hold; NOT in the wave schedule — revisit at production-readiness)
DOGFOOD (SLOP exporter, out-of-tree), DSGN-WRITEBACK, **TIER-RECS, PROD-INSTALL (pt.2), UX-POLISH**
(these 3 still present + intact, just parked; they touch `cli.py` → sequence at activation). View
all parked: `ls /home/stack/charon-private/fleet/board/*.parked` (15 tickets).

## IN PROGRESS (delegated, may still be running)
- **SLOP D&S audit** — a sub-session is auditing mediastack `tracking/tracking.db` (~31 tickets):
  back up the DB, add a D&S section to each open ticket, and mechanize D&S into SLOP ticket
  creation. Check its report; commit any `query.py` tooling change per its instructions (operator
  pushes). SLOP DB is local/gitignored.

## WCI EFFORT (if asked): MVP (ADR-0015 doc → WCI engine) = SMALL-MEDIUM; §5.1 proof
(DSGN-WCI-PROOF) = the hard keystone; WCI-FOLLOWON (auto-slice) = LARGE & deferred. Product WCI MUST
ship opt-in-orchestrator-only + advisory (zero behavior on a gateway-only install).

## KEY DOCTRINE (memories in MEMORY.md)
Manager never launches droids (operator opens tabs) / never pushes by hand; gates+merges+recovers;
delegates substantive work to sub-sessions. Droid PRs auto-open now but EYEBALL correctness before
merge (a green gate ≠ proof — the first WGW PR was green but a no-op). Adversarial-by-default;
re-confirm OP-owned decisions. Product ships standalone — no rig/SLOP/runner leak into `src/`.
"TL" = terse one-line-per-ticket status. Always give the literal command WITH `--wait`/`--retries`.

## NEW-SESSION BOOTSTRAP ONE-LINER
```
You are the Charon fleet MANAGER. Read /home/stack/.claude/projects/-home-stack-code-charon/memory/MEMORY.md + /home/stack/charon-private/fleet/HANDOFF.md + /home/stack/charon-private/fleet/WORKFLOW.md; run board.sh/validate_board.sh. Board is CLEAR; the autonomous-ticket-runner cluster shipped+certified. Backlog is optimized into waves (fleet/OPTIMIZATION-PASS.md): Wave 1 = ADR-0015/DSGN-WCI-PROOF/OBS-CAPTURE/OBS-UI/CLIENT-CONNECT-GUI/ORCH-ROUTE/OHMYPI-ASSESS (all disjoint, parallel); then WCI; then WCI-FOLLOWON; then ATC (audit) last. STANDING RULE: every ticket carries a ## Dependencies & sequence section (validate_board hard-fails without it). Operator opens droid tabs (fleet-droid.sh <tier> --wait 3 --retries 10) + merges; manager gates/recovers; eyeball correctness before merge. Check the SLOP D&S audit sub-session's result. Pause after any question/handed-action; token-conscious; "TL" = terse status.
```
