# WORKTREE-ADD-FORCE — make add_worktree resilient to stale registrations

## Why (surfaced by the 2026-06-27 live certification)
A `charon work` re-run crashed at `_integrate` with `git worktree add --detach … exit 128` because
a stale-but-registered worktree path lingered in `.git/worktrees`. `charon/gitutil.add_worktree`
uses `git worktree add --detach` **without `-f` and without pruning**, so any stale registration
(common after an interrupted run) aborts the whole run instead of recovering.

## What to build
Make `gitutil.add_worktree` re-run-resilient: prune stale registrations and/or pass `-f` so a
lingering registration for the same path does not abort. Prefer `git worktree prune` (+ remove the
target dir if present) before the add, falling back to `-f`; keep behavior identical on the
clean-first-run path. Don't mask a genuine "path in use by a LIVE worktree" error — only recover
from STALE registrations.

## Acceptance
- Test: `add_worktree` succeeds when a stale registration exists for the target path (simulate a
  leftover `.git/worktrees/<name>` with a missing/old dir); still errors clearly if the path is held
  by a live worktree. Existing gitutil tests stay GREEN.

## CONSTRAINTS
Own ONLY: `src/charon/gitutil.py`, `tests/test_gitutil.py` (or a new `tests/test_gitutil_worktree.py`
if `test_gitutil.py` is absent — finalize at activation). Stdlib core; no secrets; gate GREEN every
commit. Conventional commits; review note → `docs/review-log/WORKTREE-ADD-FORCE.md`. Draft PR,
`submit.sh`, STOP. BACKLOG — tackle after the priority cluster if budget remains.

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
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
