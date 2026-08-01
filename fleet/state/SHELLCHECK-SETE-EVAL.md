# shellcheck — consult-first evaluation for the `set -e` tab-kill defect class

**Date:** 2026-08-01 · **Evaluator session:** saba-sebatyne · **Ticket:** LAUNCHER-GATE-SETE-KILL
**shellcheck version:** 0.11.0

## Question

Does the established external linter for this language (shellcheck — already adopted and already
wired into the rig gate) catch the defect class in LAUNCHER-GATE-SETE-KILL, so that no new
hand-rolled guard is needed?

The defect class, stated precisely:

1. **Redirect-before-mkdir.** A command redirects into a directory that a LATER line creates.
   bash opens the redirection target when it sets up the command, so the command fails outright;
   under `set -e` the script exits.
2. **Non-zero compound command under `set -e`.** `( ... ) > f` in plain statement position exits
   the shell on a non-zero result, making the following `RC=$?` unreachable — so a "record the
   failure and continue" design silently becomes "die".

## Method (EXECUTED — not inferred)

Ran shellcheck against the **pre-fix** `fleet/fleet-droid.sh` (`git show master:fleet/fleet-droid.sh`),
at default severity (all levels: error/warning/info/style), not just `-S error`.

```
shellcheck -f gcc /tmp/fd-prefix.sh | wc -l                        -> 9      (whole file)
shellcheck -f gcc /tmp/fd-prefix.sh | awk -F: '$2>=1390 && $2<=1412'  -> 0    (the defective block)
shellcheck -S error /tmp/fd-prefix.sh                              -> CLEAN  (exit 0)
shellcheck -S error fleet/fleet-droid.sh   (post-fix)              -> CLEAN  (exit 0)
```

Finding codes across the whole file: 4x SC2034 (unused var), 4x SC1091 (not following source),
1x SC2143. **None of the 9 falls in the defective block, and none describes either defect.**

## Result

**shellcheck is SILENT on both defects, at every severity, before AND after the fix.** It cannot
serve as the guard. This is not a configuration miss:

- There is no shellcheck rule for "the redirect target's directory is created on a later line" —
  that requires ordering/reachability analysis across statements, which shellcheck does not do.
- There is no shellcheck rule for "this non-zero compound command unwinds the caller under
  `set -e`". SC2164 (`cd` without `||`) is the nearest relative and is about `cd` specifically;
  the `set -e` family (SC2310/SC2311 etc.) concerns functions in conditional contexts, not a
  compound command in statement position.
- Both defects are runtime ORDERING/control-flow facts about one specific block, not lint patterns.

`bash -x` tracing and bashdb reproduce the behaviour once you already suspect the line, but
neither is a merge gate, so neither closes the class.

## Verdict

**ADOPT shellcheck (already adopted, already wired) — and it does NOT cover this class.** The
remaining slice is genuinely novel and rig-specific: "our launcher must survive its own gate
failing." That is asserted by `fleet/tests/launcher-gate-sete-kill.test.sh`, which EXTRACTS the
shipped block out of `fleet-droid.sh` and executes it under the launcher's own shell options
rather than re-implementing it. Externally red-proofed: 11/11 pass with the fix, 10 FAIL on revert.

No new tool is introduced and nothing shellcheck already does is hand-rolled.

## Generalisation (why this matters beyond one ticket)

The rig is ~60,259 LOC of Bash and runs `set -euo pipefail` widely. This evaluation shows the
adopted linter cannot see "a failing sub-command kills a long-running loop." Every launcher/pool
loop that must treat a child's failure as DATA has the same exposure and the same blind spot.
A cheap follow-up is a targeted grep-based check for `( ... ) > ...` / `cmd; RC=$?` shapes inside
`set -e` scripts; filed as a gap finding here rather than built inside this ticket.
