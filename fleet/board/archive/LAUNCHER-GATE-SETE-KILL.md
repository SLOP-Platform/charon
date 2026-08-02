repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: rig-meta
branch: fix/launcher-gate-sete-kill
owns: fleet/fleet-droid.sh, fleet/tests/launcher-gate-sete-kill.test.sh
serial_justified: One ordering/set-e fault in a single launcher block plus its fail-on-revert test; splitting them would land a fix with no proof.
substrate: |
  shellcheck — adopt (already in the gate) — the ESTABLISHED tool for this class is
  shellcheck, and it is already wired into the rig gate. It does NOT catch either defect here:
  SC2164-family rules cover `cd` without `||`, and there is no shellcheck rule for "redirect
  target directory is created on a later line" or for "non-zero compound command under set -e
  unwinds the caller" — both are ORDERING/control-flow facts about this specific block, not
  lint patterns. Verified: `shellcheck -S error fleet/fleet-droid.sh` is CLEAN both before and
  after this fix, so the linter cannot be the guard. `set -o errexit` debuggers (bashdb) and
  `bash -x` tracing diagnose it once you already suspect the line, but neither is a merge gate.
  Hence the novel slice below; no library is being hand-rolled — this is a 3-line ordering fix
  plus a fail-on-revert test that EXTRACTS the shipped block rather than re-implementing it.
substrate-novel: |
  The guard has to assert a runtime property of ONE block in OUR launcher under
  OUR shell options (a RED gate must be recorded as data, not unwind the tab). No external tool
  models "this project's launcher must survive its own gate failing" — that is rig-specific
  behaviour, so the test is the novel slice.
depends_on:
note: |
  ROOT CAUSE of the pipeline's measured 24% end-to-end success rate (6 DONE / 3 PR / 4 claimed /
  12 fell back to READY, of 25 tickets worked). Running-list item 3, previously NO TICKET.

  fleet-droid.sh runs `set -euo pipefail` (:17). Its launcher gate block had TWO ways to kill the
  WHOLE TAB instead of recording a FAIL and continuing:

    1. ORDERING — the redirect `( cd "$wt" && eval "$RR_GATE" ) > "$FLEET/state/gate-results/..."`
       (:1403) ran BEFORE the `mkdir -p` of that dir (:1405). bash opens the target while setting
       up the redirection, so a missing dir fails the command outright -> `set -e` exits the tab.
    2. RED GATE — a failing gate is a non-zero compound command in plain statement position, so
       `set -e` exits the tab there too. `GATE_EXIT=$?` (:1404) was therefore UNREACHABLE on any
       failure, which makes the `GATE_EXIT=1` "default to FAIL" (:1397) and the 125 NOT-RUN
       sentinel (:1400) dead code for exactly the path they exist to describe.

  Both confirmed empirically, not inferred: `set -euo pipefail; ( false ) > f; RC=$?; echo B`
  never reaches the assignment or prints B.

  This single block explains three separate entries in the handoff's 10-defect chain: #1 (false
  RED -> publish skipped), #2 (gate RED -> launcher silently skips publish, "unticketed") and #5
  (the mkdir ordering). The recorded framing of #2 was wrong in a way that mattered — the tab
  does not "silently skip publish", it DIES mid-ticket, which is also why claims are left held
  and tickets fall back to READY to be silently redone by another tab.

  THIRD defect, same block: `$FLEET/state/gate-results/` had NO reader anywhere in the rig
  (`grep -rn gate-results` matched only the two write lines), so a RED gate discarded its own
  diagnosis and the skipped publish downstream looked causeless. That is handoff chain item #10's
  "silent report loss".
accept: |
  - A missing `gate-results/` dir does NOT kill the tab; the dir is created BEFORE the redirect.
  - A RED gate does NOT kill the tab; it is recorded as DATA — GATE_EXIT carries the real
    non-zero code through to the report, so the FAIL default and 125 sentinel become reachable.
  - A RED gate SURFACES the tail of its gate log on stderr, naming the log path, so the failure
    is diagnosable instead of silently discarded.
  - The gate log is still written to `gate-results/<droid>-<id>.txt` (no regression in capture).
  - fail-on-revert proof: `fleet/tests/launcher-gate-sete-kill.test.sh` EXTRACTS the real block
    from fleet-droid.sh (never re-implements it) and runs it under the launcher's own shell
    options. Externally red-proofed 2026-08-01: 11/11 pass with the fix, 10 FAIL on revert.

## Dependencies & Sequence

- **depends_on: (none).** This is a self-contained ordering fix inside ONE block of
  fleet-droid.sh plus its test. It reads no other ticket's output and needs no prereq build.
- **Sequence: FIRST, before any tab is launched.** Every pool tab runs through this block, so
  dispatching tabs before this lands means dispatching them into a launcher that dies on its own
  gate. This is the anchor line — land it, then fan out.
- **Blocks / unblocks:** landing this is what makes a RED gate survivable, so it is a
  prerequisite for trusting ANY pool-tab throughput number measured after it.
- **owns-collision note:** `fleet/fleet-droid.sh` is also owned by BRIEF-ABSOLUTE-PATHS,
  LAUNCHER-CRASH-PARTIAL-DETECT and LOOP-GUARD-REASON-WIRE. Those three are already ordered
  behind LOOP-GUARD-REASON-WIRE (PR #334). This ticket touches a DISJOINT block (the launcher
  gate run at ~:1402) and lands first; the others rebase onto it. Sequence is
  LAUNCHER-GATE-SETE-KILL -> LOOP-GUARD-REASON-WIRE -> {BRIEF-ABSOLUTE-PATHS,
  LAUNCHER-CRASH-PARTIAL-DETECT} to keep the file single-writer at any moment.
