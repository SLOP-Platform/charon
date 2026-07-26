# SESSION — PREFLIGHT-OWNS-ARBITRATE: clear the board's only standing RED

**Model:** a NON-ANTHROPIC model through the Charon gateway (`opencode --model charon/<model>`).
Never Claude/Anthropic. This run is a GRADED sample, work_class `rig-meta`.
**Repo:** charon-private (PRIVATE rig) · **Ticket:** PREFLIGHT-OWNS-ARBITRATE
**Branch:** `fix/preflight-owns-arbitrate`
**Worktree:** `/home/stack/charon-private-wt/PREFLIGHT-OWNS-ARBITRATE` — ISOLATED.
**Do NOT work in `/home/stack/charon-private` directly** — the manager session holds that checkout.
One checkout, one agent.

## WHY THIS IS URGENT (escalated 2026-07-26)
This is no longer cosmetic. `fleet/land-push.sh` runs `validate_board.sh` as its pre-push gate and
**refuses to push on RED (exit 4)**. The rig is 20+ commits ahead and CANNOT BE PUSHED until this
RED clears. Every other piece of rig work is now stuck behind it.

## FIRST ACTS
0. **Register on the session-bridge first** — `session-bridge_register(session_id="<an UNUSED Jedi
   name; kit-fisto and qui-gon-jinn are taken>", name="PREFLIGHT-OWNS-ARBITRATE", repo="charon",
   ticket="PREFLIGHT-OWNS-ARBITRATE", status="in-progress", model="<your model>")`.
   MCP is already configured — nothing to install.
1. `git -C /home/stack/charon-private worktree add -b fix/preflight-owns-arbitrate /home/stack/charon-private-wt/PREFLIGHT-OWNS-ARBITRATE master`
2. `cd /home/stack/charon-private-wt/PREFLIGHT-OWNS-ARBITRATE`
3. Read the ticket — it is BINDING: `fleet/board/PREFLIGHT-OWNS-ARBITRATE.md`
4. Reproduce the RED: `bash fleet/validate_board.sh` (expect exactly 1 RED).

## THE RED
    owns-collision LIVE (no dep ordering): fleet/preflight.sh <- MARKER-PROOF-MECHANIZE
    PREFLIGHT-GATE-RUN-HELPER RECONCILE-WIRING REPO-MAP-CONVERGE SYNC-SCHEDULE
Colliding pairs the validator names: MARKER-PROOF-MECHANIZE|PREFLIGHT-GATE-RUN-HELPER,
PREFLIGHT-GATE-RUN-HELPER|RECONCILE-WIRING, PREFLIGHT-GATE-RUN-HELPER|REPO-MAP-CONVERGE,
PREFLIGHT-GATE-RUN-HELPER|SYNC-SCHEDULE.
PREFLIGHT-GATE-RUN-HELPER appears in all four — it looks like the natural anchor. CONFIRM OR REFUTE
that from the tickets themselves; do not assume it.

## WHAT TO PRODUCE — a RULING, not edits
Read all five tickets. Determine what each actually needs from `fleet/preflight.sh`. Disposition each
by exactly one of: **SEQUENCE** (add `real-dep:` + `dep-kind: build` so writers are ordered),
**NARROW OWNS** (it does not need the whole file — drop it, with a reason), **MERGE** (two tickets
are one change), **RETIRE** (stale or already satisfied). Every disposition states its evidence.

## HARD CONSTRAINTS
- **Do NOT edit `fleet/preflight.sh`.** Do NOT edit the five tickets. You own ONE file:
  `fleet/state/PREFLIGHT-OWNERSHIP-RULING.md`. Rewriting another live ticket's ownership without the
  operator in the loop is exactly the override this ticket exists to avoid.
- Write the prescribed `depends_on:`/`owns:` line edits out VERBATIM so applying them is mechanical.
- A zero-hit grep is NOT evidence: read each ticket, do not pattern-match. Locate with search,
  CONCLUDE only by reading.
- DRY-RUN PROOF required: show current `validate_board.sh` RED output and the PREDICTED post-ruling
  output — state exactly which RED lines your ruling clears and which remain.
- NON-VACUOUS: fewer than five dispositions is incomplete, not partial credit.
- FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail` on verification paths.

## REPORT BACK (short — no diffs)
The five dispositions one line each · the ruling file path · predicted post-ruling validator state ·
whether PREFLIGHT-GATE-RUN-HELPER is genuinely the anchor · the commit SHA.

## LAST STEP (REQUIRED)
```
git add -A && git commit -m "PREFLIGHT-OWNS-ARBITRATE: ruling to resolve the 5-way preflight.sh owns collision"
```

Do NOT push.
