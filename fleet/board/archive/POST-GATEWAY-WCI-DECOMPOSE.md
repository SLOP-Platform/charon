repo: charon
tier: standard
difficulty: 3
work_class: refactor-decompose
status: parked
branch: chore/post-gateway-wci-decompose
depends_on: GATEWAY-PROGRAM (do NOT start until routing_policy/ interface has stabilized & Wave-1 merged)
owns: (decompose wave — split per-file, one worktree per target; NOT co-written)
accept: wci-contention.sh reports each target below < 4 active owners after decompose
scope: |
  DURABLE BACKLOG (operator directive 2026-07-10): the god-file contention is NOT on the
  gateway-program critical path — the program was decomposed-by-design into the NEW
  routing_policy/ package, so it only touches gateway.py (Wave-1 decompose) and proxy.py
  (Wave-1 METER), both isolated in worktrees with a passed coupling check. proxy_server.py's
  call site is UNCHANGED (gateway.py keeps an identical public interface), so the biggest
  god-file is off-path.

  These remaining high-contention files are deferred to a dedicated WCI decompose wave to run
  AFTER the gateway program settles. Active-owner counts (parked tickets excluded), 2026-07-10:
    - proxy_server.py   16 active (+11 parked)  <- top target; money-path adjacent -> adversarial review
    - cli.py            16 active
    - config.py          9 active  (light Wave-2 pools touch = READ + sequence, not a decompose blocker)
    - api.py             7 active
    - scheduler.py       5 active
    - check_boundary.py  5 active
    - providers.py       5 active
    - intake.py          5 active
    - board.py / agent_launch.py / coordinator.py / land.py / acp.py  4 active each
  Method: run wci-contention.sh first; decompose the top offenders one worktree per file,
  collision-free waves (WCI-METHOD.md). proxy_server.py gets adversarial review (money-path).
  Re-point the owning tickets to the split modules. Un-park this once GATEWAY-PROGRAM is merged.
