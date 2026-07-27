# SESSION — ADVERSARIAL REVIEW: RIG-BRANCH-16-DEEPDIVE (e75155f) — DELETIONS ALREADY HAPPENED

**Model:** NON-ANTHROPIC via the Charon gateway. Never Claude/Anthropic. work_class `design-review`.
**You are the REVIEWER. You did NOT build this. Do not fix, do not commit code, do not delete.**

## WHY THIS REVIEW MATTERS MORE THAN MOST
That session was authorised to **DELETE branches**. Deletions are irreversible and may already have
run. Your job is to establish whether every deletion was justified — and if any was NOT, to surface
it while the SHAs are still recorded and recoverable.

## FIRST ACTS
0. `NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"; echo "claimed: $NAME"`
   Then `session-bridge_register(session_id="<NAME>", name="REVIEW RIG-BRANCH-16",
   repo="charon", ticket="RIG-BRANCH-16-DEEPDIVE", status="in-progress", model="<your model>")`.
   If the lease expires, do NOT renew — **re-register**.
1. `git -C /home/stack/charon-private-wt/RIG-BRANCH-16-DEEPDIVE show e75155f`
2. Read the ruling it produced (`fleet/state/RIG-BRANCH-16-RULING.md`) and the ticket
   `fleet/board/RIG-BRANCH-16-DEEPDIVE.md` (BINDING).

## ATTACK THESE
1. **Was EVERY deleted SHA recorded BEFORE deletion?** The contract made this absolute. For each
   reaped branch confirm the SHA is in the ruling and that `git cat-file -t <sha>` still resolves.
   **Any deleted branch whose SHA is NOT recorded is a BLOCKING finding** — that work is gone.
2. **Is each EQUIVALENT verdict backed by CONTENT evidence?** A commit-count comparison is NOT
   content evidence. Spot-check at least 5 verdicts yourself with an actual diff against
   origin/master. Report any verdict you cannot reproduce.
3. **`feat/github-limits-hardening` and `-v2` — the high-risk pair.** `GITHUB-LIMITS-HARDENING` is a
   LIVE ticket that FOUR other tickets depend on, and it is the current blocker for
   DONE-SH-INTEGRITY-FIX. If its branch content is NOT on master and it was reaped anyway, that is
   BLOCKING and must be surfaced immediately with the recovery command.
4. **Gitea claim re-verified?** The publication on gitea was the entire safety net. Confirm it was
   re-checked per branch rather than inherited from the earlier report.
5. **Did it delete anything remote, or touch another agent's worktree?** Both were forbidden.
6. **The `-v2`/`-rederive` explanation** — is it evidenced from the landing scripts, or asserted?

## RULES
- Do NOT delete, restore, edit, commit or push anything. Report only.
- Default to REFUTING. Every finding: branch name + evidence + severity.
- Say what you verified by RUNNING vs READING. If it is all sound, say so plainly.

## ANSWER EXPLICITLY
**"Was any work lost, and is e75155f safe to land?"** MERGE or BLOCK, with reasons.

## REPORT
Write to `/home/stack/charon-private/fleet/handoff-notes/ADVREVIEW-RIG-BRANCH-16.md`.
Reply: file path + <=10 lines (verdict, any unrecoverable loss, most dangerous finding).

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
