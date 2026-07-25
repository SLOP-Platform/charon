repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: rig-meta
branch: feat/droid-bridge-register
owns: fleet/droid-bridge.sh, fleet/tests/droid-bridge.test.sh
depends_on:
serial_justified: name-claim + register + heartbeat + unregister-trap + pickup-gate are ONE session
  lifecycle — a droid that registers but never heartbeats (goes stale) or never unregisters (strands its
  report) is the exact dark-work gap this closes; splitting them ships a half-lit session.
source: |
  F47 (no-dark-work: register every session + pickup-gate) + F19 (bridge-unregister-trap). This session
  confirmed droids run DARK: fleet/fleet-droid.sh:232 sets DROID="$TIER-$$" (a PID label, no allocator) and
  has ZERO bridge wiring — 5 live droids sat 28-min heartbeat-stale, none on the bridge board. REUSE (do NOT
  re-implement): fleet/claim-jedi-name.sh (conflict-free allocator, LANDED via #223) + the session-bridge
  proxy.py JSON-RPC entry (bash-reachable: register/update/unregister). Belongs to the launcher-governance
  family — coordinate with SUBAGENT-WORKTREE-SANDBOX (both edit the fleet-droid.sh launch block).
push-mode: |
  ### FOLDED IN 2026-07-24 — PUSH MODE. Design: fleet/state/DESIGN-DROID-PUSH-MODE-agen-kolar.md
  OPERATOR GOAL: a droid that IDLES until the manager/supervisor SENDS it work, instead of polling
  the board.

  VERDICT FROM THE DESIGN PASS: **THIS IS WIRING, NOT A BUILD.** Push already works, PROVED BY
  EXECUTION over the raw Unix socket: `register` -> `nudge("DISPATCH ticket=…")` -> `board()`, with the
  message delivered carrying seq / ack / liveness. `nudge` writes the target's queue
  (daemon.py:606-643), and `board()` returns that queue AND refreshes the 600s lease — so **the poll IS
  the heartbeat, free**. NO daemon change and NO new RPC are required. Anyone scoping this as "build a
  push channel" has mis-scoped it [[adopt-substrate-build-only-novel-slice]].

  THE WORK IS THREE FLEET-SIDE GAPS:
    1. `fleet-droid.sh` never REGISTERS on the bridge. (This ticket already covers it — see note:.)
    2. IDLE IS A BLIND `sleep`. fleet-droid.sh:567 does `sleep "$((WAIT_MIN*60))"` on an empty board.
       It should BLOCK ON THE BRIDGE instead, so a dispatch wakes it immediately rather than up to
       WAIT_MIN minutes later.
    3. THE `CLAIM_ONLY` PIN IS LAUNCH-TIME ONLY. fleet-droid.sh:461 does `export CLAIM_ONLY="$ONLY_TICKET"`
       ONCE, before the loop. It must move PER-ITERATION so a dispatch can target a specific ticket on
       any iteration, not just at launch.

  CONSTRAINTS — RECORD THESE, THEY ARE WHAT MAKE PUSH SAFE:
    - A DISPATCH CARRIES ONLY A TICKET ID. Every existing gate (claim, lease, parallelizability,
      leak-guard) therefore stays fully intact and **NO DARK WORK IS POSSIBLE** — push changes WHICH
      ticket is attempted, never WHETHER the gates run. A dispatch that carried a command or a diff
      would be a different, unacceptable design.
    - PUSH MUST BE ADDITIVE. Hybrid push-then-pull with LOUD degrade: if the manager session dies or
      the bridge is unreachable, the droid still free-claims and keeps working. A push-only droid that
      silently idles when its manager dies is a worse failure than polling
      [[no-stiff-single-provider-tools]].
    - CROSS-REF: `DROID-LIFECYCLE-REAP` should CONSUME the bridge's expired/escalated signal rather
      than grow a SECOND liveness notion. The bridge already emits it (see that ticket's
      bridge-evidence:); two liveness notions would drift, and the reaper is the thing that would be
      wrong when they did.
corrections: |
  ### TWO CORRECTIONS TO EARLIER REPORTS — both re-verified here rather than inherited
  [[confirm-dont-trust-documentation]] [[document-model-self-report-lies]]

  (C1) **THE BRIDGE IS NOT DOWN. THE DESIGN DOC IS WRONG ON THIS POINT — DO NOT INHERIT IT.**
       DESIGN-DROID-PUSH-MODE-agen-kolar.md:108 concludes "The LIVE bridge daemon is DOWN:
       `/tmp/charon-bridge.sock` does not exist". **That is the wrong path.** The bridge is a REMOTE
       daemon on `rocinante`, reached through an SSH tunnel. VERIFIED LIVE 2026-07-24 by execution,
       not by reading:
         - tunnel process pid 312: `ssh -N -L /home/stack/.charon/coordinator-charon.sock:/run/charon-bridge/charon.sock`
           (ServerAliveInterval=15, ExitOnForwardFail) — i.e. LOCAL `~/.charon/coordinator-charon.sock`
           maps to REMOTE `/run/charon-bridge/charon.sock`;
         - the local socket EXISTS: `srw------- stack stack /home/stack/.charon/coordinator-charon.sock`;
         - `board(repo=charon)` returned **`ok: true`** with a live session listed.
       `/tmp/charon-bridge.sock` is absent because NOTHING EVER USED THAT PATH — its absence is not
       evidence of a dead daemon [[bridge-topology-roci-tunnel]].
       CONSEQUENCE: **push-mode is NOT blocked on restarting anything.** The design doc's
       "`--push-only` must wait for SERVICE-LIVENESS-WATCHDOG" caveat (:89, :115) rests on this FALSE
       PREMISE and is VOID as stated. SERVICE-LIVENESS-WATCHDOG remains the right owner of the
       daemon's ongoing supervision — that is a durability concern, not a precondition for building
       push mode.

  (C2) **`work-lease.sh guard-branch` DOES EXIST — the "it does not exist" report is itself the error,
       and this ticket DELIBERATELY DOES NOT APPLY THAT CORRECTION.**
       A correction was circulated today claiming `guard-branch` is not a real subcommand and that the
       b784de1 gate enforces at `bind`/`dispatch` instead, with an instruction to fix the name wherever
       it appears on the board. VERIFIED BY EXECUTION against the actual branch — the claim is WRONG:
         - `git show b784de1:fleet/work-lease.sh` line 408: `guard-branch)  cmd_guard_branch "$@" ;;`
           (5 occurrences of guard-branch on that revision);
         - `git show b784de1:fleet/fleet-droid.sh` ~:375 calls
           `bash "$FLEET/work-lease.sh" guard-branch "$branch" "ticket $id"` and RELEASES the claim on
           refusal — exactly as TICKET-MAP-GATE and DROID-LIFECYCLE-REAP already describe.
       WHY THE CONFUSION AROSE, so it is not repeated: on **MASTER**, work-lease.sh has only
       `acquire|check|holds|bind|dispatch|release` — `guard-branch` is ADDED BY b784de1, which is built
       and pushed but NOT YET LANDED. Checking master and concluding "no such subcommand" is correct
       about master and wrong about the branch.
       ACTION TAKEN: the board text was left UNCHANGED, because it accurately describes built code.
       Renaming `guard-branch` to `bind`/`dispatch` across the board would have introduced a real error
       into three tickets to match a mistaken correction
       [[adversarial-review-must-not-silently-override-operator]].
note: |
  Wire the droid launcher's bridge lifecycle:
  - ON CLAIM: claim-jedi-name.sh -> a conflict-free session name (replace $TIER-$$); session-bridge register
    (via proxy.py). FAIL-LOUD if register fails — never run dark silently (that's the pickup-gate: refuse to
    start work unregistered).
  - WHILE ALIVE: a background heartbeat loop pings the bridge every < 600s (lease TTL) as long as the droid
    PID lives, so the session never goes stale on the board.
  - ON EXIT (trap, incl. INT/TERM): unregister + RELEASE the name. Use ephemeral markers (never committed) so
    the 69-name pool can't drain from droid churn.
accept: |
  ### PUSH-MODE ACCEPTANCE (added 2026-07-24 with the push-mode fold-in)
  - IDLE BLOCKS ON THE BRIDGE, NOT ON `sleep`: with the board empty, a `nudge("DISPATCH ticket=<id>")`
    from a manager session wakes the droid and it starts THAT ticket. Red-proof: revert the idle path
    to the blind `sleep` at fleet-droid.sh:567 -> the "woke within seconds of the nudge" assertion goes
    RED. Asserting on WALL-CLOCK is the point; a test that only checks the ticket eventually ran would
    still pass against the blind sleep [[latency-is-a-failure-class]].
  - `CLAIM_ONLY` IS PER-ITERATION: a dispatch arriving on iteration N pins iteration N, not just
    launch. Red-proof: move the export back outside the loop (fleet-droid.sh:461) -> a mid-run dispatch
    is ignored -> RED.
  - ADDITIVE / HYBRID, PROVEN BY KILLING THE MANAGER: with the bridge unreachable, the droid emits a
    LOUD degrade line and STILL free-claims and completes work. A droid that idles silently when its
    manager dies fails this ticket. Red-proof both directions: bridge up -> dispatch honoured; bridge
    down -> degraded pull path runs AND says so.
  - NO DARK WORK, ASSERTED NOT ASSUMED: a dispatch for a ticket that the claim/lease/parallelizability
    gates would refuse is REFUSED AND REPORTED, not executed. The dispatch carries only a ticket id, so
    this is a property to demonstrate, not to argue.
  - NOT IN SCOPE HERE: the bridge daemon's own supervision (SERVICE-LIVENESS-WATCHDOG). Per
    corrections: (C1) it is NOT a precondition — the bridge is live.
  - e2e DOGFOOD: launch a REAL droid -> it appears on `session-bridge board` -> its heartbeat refreshes past
    at least one 600s TTL window -> on exit it is UNREGISTERED and its name RELEASED back to the pool. Real run.
  - FAIL-LOUD: a forced register failure makes the droid refuse to start (pickup-gate), never run dark.
  - REUSE claim-jedi-name.sh (landed) — do NOT re-implement name allocation.
  - fail-on-revert test: remove the heartbeat loop -> the "stays live past one TTL" assertion goes RED; remove
    the exit trap -> the "unregistered on exit" assertion goes RED.
  - ADVERSARIAL REVIEW (reviewer != builder) — edits the shared money-path launcher fleet-droid.sh.
scope: |
  The droid-launcher bridge lifecycle (name-claim + register + heartbeat + unregister-trap + pickup-gate)
  PLUS the push-mode wiring folded in 2026-07-24 (bridge-blocking idle, per-iteration CLAIM_ONLY,
  hybrid push-then-pull with loud degrade). All of it is WIRING on a bridge that already delivers
  dispatches — see push-mode:. The bridge DAEMON's own liveness/reboot-survival is
  SERVICE-LIVENESS-WATCHDOG's job (session-bridge daemon is a registry entry there), NOT this ticket,
  and per corrections: (C1) it is NOT a prerequisite — the daemon is live over the rocinante tunnel.
  Coordinate the fleet-droid.sh launch-block edit with SUBAGENT-WORKTREE-SANDBOX — anchor whichever
  lands first; this is the bridge slice.
ds: |
  ## Dependencies & sequence
  P0. HANDOFF-NAME-ALLOCATOR (claim-jedi-name.sh) is LANDED so the naming prereq is satisfied. Shares the
  fleet-droid.sh launch block with SUBAGENT-WORKTREE-SANDBOX — sequence, do NOT parallel-edit. Pairs with
  SERVICE-LIVENESS-WATCHDOG (which supervises the bridge daemon itself).

  ### PUSH-MODE FOLD-IN (2026-07-24) — CONTENTION NOTE, NOT A NEW DEP
  The push-mode gaps 2 and 3 are edits to `fleet/fleet-droid.sh` (:567 idle, :461 CLAIM_ONLY), which
  this ticket does NOT own. Live owners of that file: DROID-LIFECYCLE-REAP, FLEET-DEMAND-BROKER,
  FLEET-DEMAND-DRIVEN-ROUTING (LANDED today, PR #264), LAUNCHER-CRASH-PARTIAL-DETECT, TICKET-MAP-GATE
  (built+pushed at b784de1, anchors guard-branch at :375). Treat :567 and :461 as ANCHOR EDITS
  coordinated with those owners — this ticket must not become a concurrent rewriter of the launcher
  [[one-checkout-one-agent]]. No new `depends_on:` is added here because the ordering is a merge-order
  question among already-related launcher tickets, not a build prerequisite
  [[disjoint-owns-not-no-dependency]] — but whoever claims this MUST rebase onto the landed launcher
  rather than branching off a stale one.
