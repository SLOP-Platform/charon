# SESSION — BRIDGE-PROXY-HEARTBEAT (P0): make board presence match reality

**Model:** a NON-ANTHROPIC model through the Charon gateway. Never Claude/Anthropic.
Graded sample, work_class `rig-meta`.
**Repo:** `/home/stack/.config/opencode/session-bridge` — **its OWN git repo.** Not charon, not
charon-private. Commit there. Do NOT create a worktree in either charon repo.

## FIRST ACTS
0. **Claim your session name MECHANICALLY — do not invent one:**
   ```
   NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"
   echo "claimed: $NAME"
   ```
   Then `session-bridge_register(session_id="<the claimed NAME>", name="BRIDGE-PROXY-HEARTBEAT",
   repo="charon", ticket="BRIDGE-PROXY-HEARTBEAT", status="in-progress", model="<your model>")`.
   **Never reuse a name you see on the board — those sessions are LIVE.** (A session did exactly that
   today and took over the manager's entry. You are fixing the cause.)
1. `cd /home/stack/.config/opencode/session-bridge && git status --short && git log --oneline -1`
2. Read the ticket (BINDING): `/home/stack/charon-private/fleet/board/BRIDGE-PROXY-HEARTBEAT.md`
3. Read `proxy.py` and `daemon.py` before changing anything.

## ⚠ YOU ARE EDITING THE THING YOU ARE RUNNING ON
This proxy is how your own session talks to the board. A broken edit can cut your own connection
mid-task. Test changes by launching a SEPARATE proxy process against the same socket — never by
restarting the one your session depends on. If you lose the bridge, keep working and report; do not
thrash trying to reconnect.

## THE DESIGN IS CORRECT — DO NOT REDESIGN IT
Already working, leave alone: shared durable daemon on Roci · **lease-based liveness, deliberately
NOT PID** (daemon.py:10 — the daemon runs on a DIFFERENT HOST, so PID liveness is impossible) ·
graduated purge nudge->nudge->escalate->purge (daemon.py:222) · atomic claim/release · secret
allowlist keeping `lease_token` inside the daemon (daemon.py:94).

**The hole:** `proxy.py` has no heartbeat. `grep -nE "thread|Timer|atexit" proxy.py` returns nothing.
It is a pure stdio forwarder (`_forward`, `main`, `_respond`, `_error`). The only thing refreshing a
lease is the model deciding to call `update`. Models do not — three for three today, with an explicit
instruction in the prompt. Asking politely has failed; enforce it in the transport.

## OBSERVED RIGHT NOW (your test fixtures, effectively)
- A live `opencode --model charon/minimax-m3-free` session is working and is **absent from the
  board** — purged mid-task for not heartbeating.
- **3 `proxy.py` processes but only 1 opencode.** PID 1794037 is orphaned: its parent exited, the
  forwarder never did. That is the missing `atexit`, visible in `ps`.

## THE FIX
1. **Heartbeat.** Capture the `session_id` from the `register` call as it passes through `_forward`,
   then refresh the lease from a background timer at ~TTL/3. Liveness becomes "the proxy is alive" —
   the truth we want — while staying LEASE-based. **Do NOT switch to PID liveness** (cross-host).
2. **Clean exit.** `atexit` + SIGTERM/SIGINT -> `unregister` (which releases the ticket claim too).
3. **Guard the regression:** a hung proxy must not fake liveness forever. Bind the heartbeat to the
   session really being alive — stop refreshing when stdin closes or the parent goes away. A
   heartbeat that outlives its session recreates ghosts with extra steps.

## REQUIRED PROOF (green is not proof)
- **The primary claim, proven by WAITING:** register a session, leave it completely IDLE for longer
  than `SESSION_BRIDGE_TTL` (600s — so wait >10 minutes, really wait), then show `board()` still
  lists it. Reasoning about the timer is not proof; the wait is the test.
- Kill the proxy -> entry gone from `board()` and the ticket released. Show before/after.
- A killed proxy does NOT keep refreshing — prove the heartbeat stops.
- **RED-PROOF BY EXECUTION:** disable the heartbeat -> the idle-session test goes RED (purged).
  **Report BOTH exit codes.**
- NON-VACUOUS: a zero-length or sub-TTL wait must FAIL the test, not pass it.
- **Do NOT modify `daemon.py`**, the lease model, or the secret allowlist. The daemon is shared across
  hosts and repos. If the fix seems to need a daemon change, STOP and report.
- FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail` on verification paths.
- State what you proved by RUNNING vs by READING.

## BONUS (only if trivially safe)
Orphaned `proxy.py` PID 1794037 has no parent session. Do NOT kill processes you cannot attribute —
report what you find and let the operator dispose.

## OWNS
`proxy.py` (+ a test file in that repo). Nothing else.

## REPORT BACK (short — no diffs)
How long you actually waited for the idle test and the board result after it · kill-test before/after
· both exit codes from the red-proof · confirmation daemon.py is untouched · the commit SHA.

## LAST STEP (REQUIRED)
```
cd /home/stack/.config/opencode/session-bridge && git add -A && git commit -m "proxy: heartbeat the lease and unregister on exit — board presence now matches process liveness"
```

Do NOT push.

## Dependencies & sequence
- **Depends on: NOTHING.** Own repo, disjoint from charon and charon-private — cannot collide with
  any board ticket or worktree.
- **Blocks:** nothing formally; every session dispatched before this lands is one the manager may
  lose sight of. Run it early.
- **Wave:** parallel lane, P0.
