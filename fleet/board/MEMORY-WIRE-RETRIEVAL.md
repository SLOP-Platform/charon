repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
branch: feat/memory-wire-retrieval
owns: fleet/memory/load.sh, fleet/memory/session-preamble.sh, fleet/memory/tests/test_wire.sh
depends_on:
serial_justified: Cohesive point-of-need wiring around one store (load.sh + preamble emitter + test) — one owned surface family, nothing independent to parallelize.
note: |
  The fleet/memory store (basic-memory adopt + bitemporal decay + curate, PRs #49-51) is LIVE
  but NOT WIRED — sessions still load MEMORY.md WHOLESALE. Per MEMORY-TOOL-EVAL.md migration
  steps 2-4: kill the wholesale dump, load only a tiny pinned index at session start, and make
  everything else PULL via search at point-of-need. This is what ends the manual MEMORY.md
  compaction (curate.sh handles decay/dedup on a schedule instead).
accept: |
  ## Task
  - fleet/memory/session-preamble.sh: emit ONLY (a) the pinned always-on directives (fleet/memory/pin.md)
    + (b) a one-line pointer telling the session to call `fleet/memory/search.py "<topic>"` at point-of-need.
    Do NOT dump all ~95 memory files.
  - fleet/memory/load.sh: the point-of-need entry (already exists from #49 — confirm/extend it wraps search.py).
  - Document the two manager-applied follow-ups (NOT done in this ticket): (1) the SessionStart hook in
    ~/.claude/settings.json switches from cat-ing MEMORY.md to running session-preamble.sh; (2) a scheduled
    (cron/CronCreate) weekly `curate.sh` run for decay/dedup. Leave a MANAGER-WIRING note block.
  ## Accept
  - session-preamble.sh output is SMALL (pinned + pointer, not the full dump) — assert byte size well under
    the wholesale dump; search.py returns ranked results for a known topic (e.g. "failover").
  - bash fleet/memory/tests/test_wire.sh passes.
