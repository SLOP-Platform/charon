# CWD-CONFIG-VERIFY — verify opencode ACP reads config from git repo CWD

## Dependencies & sequence
**depends_on: NONE — Wave 2 (unblocks ORCH-ROUTE if verified).** Research-only; no src/ files.

## Why
The opencode config docs say: "When OpenCode starts up, it first looks for a config file in the current directory, then traverses up to the nearest Git directory." If ACP mode honors this, we could write a per-run `opencode.json` in the worktree and launch `opencode acp` from there — unblocking ORCH-ROUTE.

## STEP 0 — verify (tested 2026-07-01)
Created a temp git repo with `opencode.json` containing a custom provider pointing at a probe proxy. Launched `opencode acp` with cwd set to the repo. Sent ACP protocol messages. **Result: 0 proxy hits — NOT HONORED.** ACP mode ignores project-local `opencode.json` in a git repo.

Same root cause as opencode#34638: ACP mode bypasses the standard config initialization pipeline.

## What to build (blocked)
Once opencode fixes ACP config initialization:
1. In `charon work`, write a temporary `opencode.json` to the worktree with per-run provider config
2. Launch `opencode acp` from the worktree directory
3. The ACP subprocess reads the worktree's `opencode.json` and routes through our proxy

## CONSTRAINTS
Research-only until opencode fixes ACP config. No product src changes possible yet.

## REPORT BACK — MECHANIZED FORMAT (required)
End your session by emitting EXACTLY this block. Fixed fields, one line each, no diffs or logs.
Validate it before you finish: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Full spec + rationale: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`

```
=== SESSION REPORT v1 ===
TICKET:       <ticket-id>
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha> | none
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> is owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> | n/a — <why> | NOT-DONE
OBSERVABLE:   MET | DEFERRED — <what could not be observed and why>
RAN:          <what you proved by EXECUTING>
READ:         <what you concluded by READING only>
BRIEF-ERRORS: none | <what this brief got factually wrong>
BLOCKED-BY:   none | <ticket or condition>
BUDGET:       ok | TRUNCATED — <what you could not finish and why>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
