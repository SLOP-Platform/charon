repo: charon-private
tier: strong
difficulty: 2
work_class: rig-meta
priority: 1
branch: fix/stop-worker-graceful-exit
depends_on:
owns: fleet/stop-worker.sh, fleet/tests/worker-lifecycle.test.sh
serial_justified: |
  ONE shutdown contract: the escalation timing, the header that documents it, and the assertion
  that proves the exit code are inseparable. Fixing the timing without correcting the header leaves
  a false "verified" claim in the file that the next session will trust; adding the assertion
  without the timing fix just documents the litter.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session. Own worktree.
  Model note: opencode silently falls back to the DEAD gpt-5.4 pool for any model not in
  opencode.json's charon provider list (36 of 2567 gateway models). Verified-listed AND funded
  2026-07-31: deepseek-v4-pro, gpt-oss-120b-groq, grok-build-0.1, minimax-m2.7, big-pickle.
  NOT usable via opencode despite working on the API: devstral-2512, gemini-2.5-pro.
source: |
  Operator observed 2026-07-31: TRIAGE-B1 and TRIAGE-B2 tabs stayed open after stop-worker
  reported STOPPED, showing `[process exited with code 15]`.
note: |
  ## FACTS (verified)
  - The tabs displayed `[process exited with code 15 (0x0000000f)]`. 15 = SIGTERM.
  - `fleet/stop-worker.sh` escalation loop gives each signal `5 x sleep 0.4` = **2 seconds**:
    `for sig in INT TERM KILL; do kill -"$sig" "$PID"; for _ in 1 2 3 4 5; do sleep 0.4; ...`
  - So SIGINT did NOT kill opencode within 2s and the ladder escalated to SIGTERM.
  - Windows Terminal `closeOnExit: graceful` closes a tab only on exit code **0**. Exit 15 is
    non-zero, so the tab is NOT closed.
  - `fleet/stop-worker.sh:3-4` claims: *"Verified ladder: SIGINT -> SIGTERM -> SIGKILL. INT/TERM
    exit 0 in <1s ... and the WT tab AUTO-CLOSES (closeOnExit: graceful). SIGKILL exits 9 and
    LEAVES TAB LITTER, so it is a fallback only."* **This is false for SIGTERM.**
  - Processes were genuinely dead: no listener on :47344/:47345, `health=000`, no stray opencode
    or `scoop` children. The litter is cosmetic, not a leak.

  ## FRAMING (hypothesis — TEST IT, overturn it loudly if wrong)
  The manager believes 2 seconds is simply too short for opencode to shut down gracefully while
  holding a live session against an SQLite+WAL store, and that giving SIGINT a longer window
  (~10s) will let it exit 0 so the tab self-closes. **UNVERIFIED.** It is equally possible that
  opencode never exits 0 on SIGINT by design, in which case the correct fix is different — close
  the tab explicitly, or change the WT profile's closeOnExit policy, or simply document the real
  behaviour and stop promising auto-close. Establish which BEFORE changing the timing: measure
  what exit code opencode actually returns for SIGINT at 2s, 5s, 10s, 30s.

  ## WHY THIS SURVIVED A REVIEW (do not repeat it)
  `WORKER-LIFECYCLE-FIX` (landed today, PR #272) reviewed this very file and fixed the `000000`
  double-output bug in its verification block — but never questioned the exit-code claim in the
  header four lines above. A documented "verified" fact was trusted rather than re-tested. The
  manager also piped every invocation through `| tail -1`, which discarded the
  `still alive after SIGINT, escalating` line the script was printing on every single stop.
  **Do not swallow this script's escalation output in your own testing.**

  ## DONE CONTRACT — RED, GREEN, AND THE HEADER
  - Measure first: opencode's actual exit code under SIGINT at several wait windows. Paste the
    real output. The fix follows the measurement, not the hypothesis.
  - Whatever the mechanism, `stop-worker.sh` must end in a state where a normal stop leaves NO tab
    litter, or the header must state plainly that litter is expected and why.
  - **Correct the header either way.** A false "verified" claim in a file header is worse than no
    claim — it is what made this survive a review.
  - New assertions in `fleet/tests/worker-lifecycle.test.sh`, each WATCHED RED against the
    externally-specified break then GREEN, both transcripts pasted:
      a. a stop that completes on SIGINT reports exit code 0 (the auto-close precondition)
      b. the escalation path is VISIBLE — `still alive after SIG<x>, escalating` reaches the
         caller and is not swallowed; a caller that only reads the last line still learns a
         non-graceful stop occurred
      c. ANTI-OVER-BLOCK: a worker that is already dead still returns STOPPED cleanly, and a
         longer SIGINT window does not make an ordinary stop slow (assert an upper bound)
      d. FAIL-CLOSED preserved: a port still answering 200 with the pid alive is still FAILED
         (do not regress the guard PR #272 added)
  - Hermetic: stub signals/ports under `mktemp -d`; never stop a live fleet worker in a test.

  ## GUARDS
  - Do NOT weaken the pid-gone AND port-refuses verification — that guard was just landed.
  - Do NOT extend the SIGKILL window; a hung worker must still die promptly.
  - Killing is safe (store is SQLite+WAL, reads cleanly after a mid-turn kill; only the in-flight
    turn is lost) — so a longer SIGINT wait costs latency, never data.

D&S — Deps & Sequence:
  - Depends on: nothing. WORKER-LIFECYCLE-FIX landed and its `owns:` are released.
  - Blocks: nothing. QUEUED at operator request — cosmetic litter, not a leak.
  - Related: WORKER-LIFECYCLE-FIX (archived) owned this file previously; rebase onto its changes.
