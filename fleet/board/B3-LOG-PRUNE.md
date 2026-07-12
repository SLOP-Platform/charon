repo: charon-private
tier: economy
difficulty: 2
work_class: rig-meta
branch: chore/b3-log-prune
depends_on:
owns: /home/stack/charon-private/fleet/log-prune.sh
accept: |
  3.4M / ~59 unrotated fleet logs accrete forever. Ship a NEW self-contained `fleet/log-prune.sh` that rotates/prunes
  fleet log output by age+size (e.g. `find <logdir> -name '*.log' -mtime +N -delete` and/or gzip-rotate, size cap),
  idempotent, safe to run from preflight or a schedule. Print what it pruned (count + bytes reclaimed). Must NEVER
  touch board/, state/ markers, or anything but log files — hard-scope the target dir(s).
  FAIL-ON-REVERT: create a dummy stale `*.log` older than the threshold + a fresh one → run log-prune.sh → the stale
  one is gone, the fresh one remains; revert the age filter → the fresh one is wrongly pruned (test RED). Add a rig
  self-test under fleet/tests/ asserting both.
  GREEN-IS-NOT-PROOF: the script exiting 0 does NOT prove it pruned the right set — the self-test MUST assert the stale
  file was removed AND a fresh/non-log file was preserved (guards against a no-op OR an over-broad rm).
scope: |
  GAP-REGISTER B3. Tiny compounding hygiene: every board op / validate_board run reads less cruft. Source:
  QUICKWINS-LEVERAGE.md #7. Owns a NEW script → disjoint from B4 (branch/worktree reaper) and everything else.
ds: FLEET Wave G / FOUNDATION hygiene. depends_on EMPTY — launch NOW. Owns ONE new script → zero owns-collision; runs
  fully concurrently with B4 and the rest of the wave.
