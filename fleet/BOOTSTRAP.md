# Bootstrap — read these in order to ground any session

1. /home/stack/code/charon/AGENTS.md              (standing orders — mandatory)
2. /home/stack/charon-private/fleet/WORKFLOW.md    (full process: claim, build, gate, merge)
3. /home/stack/charon-private/fleet/waves/smart-routing.json  (wave manifest — find your wave)
4. /home/stack/charon-private/fleet/SESSION-HANDOFF-*.md     (all recent handoffs)
5. /home/stack/code/charon/docs/DECISIONS.md       (settled design decisions)

## Model-scorecard anti-rot (manager first-act)

At startup run:  `bash /home/stack/charon-private/fleet/model-scorecard.sh --due`
If it prints a nudge, skim the pivot, adjust model tiering if warranted, then run
`bash /home/stack/charon-private/fleet/model-scorecard.sh reviewed`. Silent = nothing owed.
The ledger lives at `fleet/state/model-scorecard.tsv` (append via the same script); only the
small `render` pivot ever enters context, and only on demand.

## Context discipline (token-burn guard — always on)

1. **Auto-compact ON.** At startup verify `grep autoCompactEnabled ~/.claude/settings.json` shows `true`. If not, STOP and tell the operator (see `SETTINGS-GUARD-PROPOSAL.md`) — a never-compacting transcript makes per-turn token cost climb all session.
2. **Sub-sessions write, don't dump.** A sub-session WRITES its findings to a file and returns only a 2-3 line pointer + the absolute path. NEVER paste a full sub-session report back into the primary.
3. **Read big docs in narrow slices, once.** Read handoffs/plans/big files by line-range (offset/limit), never the whole file, never re-read each turn.
4. **Keep-alive is a light heartbeat.** Fold the bridge heartbeat into real work (`board()` TTL 600s); do NOT run a 4-min idle wakeup loop that reprocesses full context.

## Session-bridge — inter-session communication

  session-bridge_board(repo="charon")                    # see who's active
  session-bridge_board(repo="charon", session_id="<id>")  # heartbeat + receive nudges
  session-bridge_register(session_id="<jedi>", name="...", repo="charon", status="in-progress")
  session-bridge_nudge(session_id="<you>", target="<them>", message="...")

  Use board() with session_id for every heartbeat — it auto-refreshes liveness AND
  delivers pending nudge messages. update() alone may not surface nudges.

## Auto-advance

  SESSION=<name> WAVE=<wave> bash /home/stack/charon-private/fleet/next.sh
