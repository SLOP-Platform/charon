tier: economy
difficulty: 3
work_class: ci-infra
branch: feat/no-dark-work
repo: charon-private
depends_on:
owns: /home/stack/charon-private/fleet/dark-work-check.sh
accept: |
  Root problem (2026-07-11): background/detached work goes UNSEEN and its result STRANDS —
  (1) VISIBILITY: an active session can run "dark" (a live opencode/CG session was found never
      registered on the session-bridge, invisible to coordination); and
  (2) PICKUP: detached jobs report by writing a file the manager must hand-collect, so if the
      session ends (or a handoff omits the pointer) the result silently strands (the KS4
      "finished, committed, but UNVERIFIED + unpushed" shape).
  This ticket mechanizes both so no work is invisible and no report is lost:
  - REGISTER leg: every session auto-registers on the session-bridge at start (Claude via the
    SessionStart hook; opencode/CG via the proxy wrapper). `fleet/dark-work-check.sh` scans
    running claude/opencode PIDs and flags any NOT registered on the bridge (a dark session);
    preflight surfaces the list.
  - PICKUP leg: every launched detached job is recorded in a job registry with a result-pointer;
    the session-end gate blocks a CLEAN exit while any launched job's result is un-picked.
  Fail-on-revert (both legs must go RED on revert):
  - start/leave a session unregistered -> dark-work-check.sh exits non-zero and names the PID;
    register it -> clean exit 0.
  - launch a job, leave its result-pointer un-picked -> end-session gate exits non-zero;
    pick it up (or explicitly waive) -> exit 0.
scope: Rig-only (build-infra; never ships in the Charon product). May split into a REGISTER leg
  and a PICKUP leg if sized too large at build time; keep as one theme for now (fold, don't proliferate).
ds: Now (rig-only). Pairs with F19 (bridge-unregister-trap, the exit complement) and F38
  (handoff-mechanize, where the omitted-pointer strand happens). Disjoint from all product work;
  owns a single new script so no owns-collision with live tickets.
