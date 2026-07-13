---
description: "The operator's working multi-agent \"robot mode\" droid-fleet harness — where it lives, what it does, and its durable consolidated home."
metadata: 
name: droid-robot-mode-harness
node_type: memory
originSessionId: eaa099fd-f9c2-4e3e-b1af-040f07dd4472
type: reference
tags: [droid, fleet]
last_referenced: 2026-07-13
---
The operator runs autonomous multi-agent coding fleets via a battle-tested **bash
"robot mode" droid harness**. It is collision-free and the proven pattern (vs. the
ad-hoc `claude --bg` fan-out that collided/polluted during Charon WAVE 1).

**Live source (READ-ONLY — running infra, do not mutate):**
`/repo/mediastack/.claude/mailbox/` + `mediastack/docs/MANAGER-HANDOFF.md`
+ `tracking/` + `tools/true_state.py`. Key scripts: `claim_role.sh` (atomic Star-Wars
identity + model-tier claim, flock under TOKEN.lock), `claim_work.sh` (atomic ticket
claim), `tier_route.py` (sonnet/opus pools; higher tier steals from a drained lower
pool only when no lower-tier droid is live), `heartbeat*.sh`/`warden*.sh` (liveness +
reaper), `droid_loop.sh` (perpetual per-tab loop relaunching fresh `claude` sessions),
`push_main.sh` (flock-serialized merge-to-main), `JOIN-PROMPT.md` (universal boot
prompt). Mechanism: generic session → claim identity → claim work → loop; worktree per
droid; a long-running MANAGER session polls `.claude/run/status/` + drives merges.

**Durable consolidated home (2026-06-26):** `/repo/droid-harness/` —
a git-init'd, audited, deduplicated copy (scripts/ + docs/HARNESS.md spec + AUDIT.md +
PROVENANCE.md + README.md). Built so the harness isn't trapped in mediastack's
`.claude/`. NOT yet pushed to a remote (operator's call — recommend pushing it).

**Open decision (DTC in progress):** which parts of this harness should become Charon
CORE/default vs opt-in vs out, for a fresh public install — see [[charon-vision-gateway-first]]
(gateway-first; orchestrator opt-in) and [[charon-project-state]] (PERF-4 already built
run_parallel + per-unit worktree/ledger/PID-lock + SharedBudget + role→pool routing,
which overlap many harness primitives).
