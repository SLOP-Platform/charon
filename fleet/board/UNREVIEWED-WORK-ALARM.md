repo: charon-private
tier: strong
difficulty: 2
work_class: rig-meta
priority: 0
branch: feat/unreviewed-work-alarm
depends_on:
owns: fleet/checks/unreviewed-work.sh, fleet/tests/unreviewed-work.test.sh
serial_justified: |
  ONE alarm and its regression suite. The check without the suite is an unproven gate; the suite
  without the check has nothing to assert. The wiring is the point of the ticket — an alarm with
  no invocation site is the exact defect it exists to catch.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session. Own worktree.
source: |
  Operator question 2026-07-31: "why did you not do what you said you would do (monitor them,
  review them, then close them)? How can we mechanize so this doesn't keep happening?" Rec accepted.
note: |
  ## THE FAILURE THIS CLOSES
  Three P0 fixes finished and then sat unreviewed and unlanded for ~4 days while their worker tabs
  idled. One of the three was actively WRONG (a regression that reported the fleet IDLE while three
  workers ran). The manager had said it would monitor and land them, then ended its turn — a session
  cannot wake itself, so nothing resumed. Relying on an agent's stated intention is not a mechanism.

  ## THE DATA ALREADY EXISTS — THAT IS THE POINT
  `fleet/fleet-idle.sh` has always printed an "unlanded commits awaiting review" section, and it
  listed 23 branches while this was happening. A passive list that nobody is obliged to act on is
  not a control. The fix is to turn existing data into an AGED ALARM, not to collect new data.

  ## WHAT TO BUILD
  A check that goes RED on: branch has commits not in master, AND no live worker owns it, AND age
  exceeds a threshold. It names the branch and the age.

  ## DO NOT WIRE YOURSELF INTO preflight.sh — THIS IS A HARD SCOPE LIMIT
  Build ONLY `fleet/checks/unreviewed-work.sh` + its suite, as a standalone check that is correct
  and provable when invoked directly. **Do not edit fleet/preflight.sh. Do not add a *_red_status /
  *_red_ensure_open / *_gate triad.**

  Reason (measured 2026-07-31): preflight.sh is 968 lines in which ONE gate template is copy-pasted
  9 times — the identical awk reopen block appears 9x verbatim, 23 `_*_red_*` helpers, 377/969 lines
  (38%) of duplication. PREFLIGHT-GATE-REGISTRY is running IN PARALLEL to extract that into a
  declarative registry. Wiring yourself the old way would create the 10th copy and would collide
  with that ticket on the most contended file in the rig.

  After the registry lands, this check becomes a single ROW in the registry table — the manager
  wires it. Your job is to make the check itself unimpeachable.

  REUSE, DO NOT REBUILD: `fleet/reconcile-stale-claims.sh` (landed PR #273) already has the
  dead-vs-live worker predicate and a stale threshold. `fleet/fleet-idle.sh` already enumerates
  unlanded branches. Do NOT introduce a second notion of liveness — the bridge also computes
  `stalled`/`stall_seconds`. Compose the existing three; write as little new code as possible.

  ## GUARDS
  - Advisory-vs-blocking is a real decision: measured 2026-07-31, **24 branches would fire on day
    one**. A RED that immediately flags 24 items gets muted, and a muted gate is a gate that does
    not run — which is the exact defect this ticket exists to fix. PROPOSE the threshold and the
    advisory-then-blocking ramp, list which of the 24 fire on day one, and justify the cut. Do not
    pick a threshold silently.

  ## DONE CONTRACT — RED, GREEN AND DOGFOOD
  - RED-PROOF, breaks EXTERNALLY SPECIFIED (do not choose your own):
      a. branch with commits not in master + no live worker + age over threshold -> RED, names it
      b. branch with commits + a LIVE worker on it -> NOT flagged (reuse the existing dead/alive
         predicate; do NOT invent a second notion of liveness)
      c. branch fully landed (empty three-dot content diff) -> NOT flagged
      d. age UNDER threshold -> NOT flagged
      e. FAIL CLOSED: branch whose state cannot be determined (unreadable/broken .git) -> flagged,
         never silently passed. "Could not check" must never resolve to "reviewed".
      f. ANTI-OVER-BLOCK: a clean fleet with nothing stranded -> GREEN, exit 0. A check that always
         fires is as useless as one that never does.
    Apply each break, WATCH it RED, restore, watch GREEN. Paste both transcripts.
  - DOGFOOD: run the real check against the REAL fleet (read-only) and show it correctly identifies
    the genuinely stranded branches among the 24, with ages. Name any it gets wrong.
  - Hermetic suite: mktemp -d fixtures with real git repos, offline, never mutating the live fleet.
  - Fail closed on "cannot determine", but never so loudly that the alarm is noise.

D&S — Deps & Sequence:
  - Depends on: nothing. reconcile-stale-claims.sh and fleet-idle.sh are landed in master.
  - Blocks: nothing structurally; it is the guard that prevents finished work from being stranded.
  - Sequence: independent of the bridge migration and the research lanes.
