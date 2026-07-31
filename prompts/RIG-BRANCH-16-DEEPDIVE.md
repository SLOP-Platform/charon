# SESSION — RIG-BRANCH-16-DEEPDIVE (P0): verify then reap 16 rig branches

**Model:** a NON-ANTHROPIC model through the Charon gateway. Never Claude/Anthropic.
Graded sample, work_class `rig-meta`.
**Repo:** charon-private (PRIVATE rig) · **Ticket:** RIG-BRANCH-16-DEEPDIVE
**Branch:** `fix/rig-branch-16-deepdive`
**Worktree:** `/home/stack/charon-private-wt/RIG-BRANCH-16-DEEPDIVE` — ISOLATED.
**Do NOT work in `/home/stack/charon-private`** — the manager holds it.

## ⚠ THIS SESSION DELETES THINGS. READ THE SAFETY RULES FIRST.
The operator approved reaping **only branches with no useful work**, verified per branch. A wrong
delete loses work that may exist nowhere else. **Skipping costs nothing. Deleting is irreversible.**
Earlier today a reap nearly destroyed the ONLY copies of 11 implementations — they survived because
the session salvaged first. Behave the same way.

## FIRST ACTS
0. **Claim your session name MECHANICALLY:**
   ```
   NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"
   echo "claimed: $NAME"
   ```
   Then `session-bridge_register(session_id="<the claimed NAME>", name="RIG-BRANCH-16-DEEPDIVE",
   repo="charon", ticket="RIG-BRANCH-16-DEEPDIVE", status="in-progress", model="<your model>")`.
   If your lease expires, do NOT renew — **re-register**.
1. `git -C /home/stack/charon-private worktree add -b fix/rig-branch-16-deepdive /home/stack/charon-private-wt/RIG-BRANCH-16-DEEPDIVE master`
2. `cd /home/stack/charon-private-wt/RIG-BRANCH-16-DEEPDIVE`
3. **Acquire the lease FROM INSIDE THIS WORKTREE** (it binds to the acquiring worktree; running it
   from charon-private leases the wrong path and your commit is refused — that cost a session today):
   ```
   bash /home/stack/charon-private/fleet/work-lease.sh acquire RIG-BRANCH-16-DEEPDIVE
   ```
   **NEVER use `WORK_LEASE_BYPASS=1`.**
4. Read the ticket (BINDING): `fleet/board/RIG-BRANCH-16-DEEPDIVE.md`
5. Read the prior reap's backup: `fleet/handoff-notes/REAP-BACKUP-2026-07-26.md`

## THE COHORT (16 branches, each 1-6 commits NOT reachable from origin/master)
```
feat/substrate-first-gate            feat/substrate-first-gate-v2
feat/coverage-meta-gate              feat/coverage-meta-gate-rederive
feat/semgrep-ci-v2                   feat/semgrep-ci-required-check
feat/stranded-work-detect            feat/stranded-work-detect-v2
feat/github-limits-hardening         feat/github-limits-hardening-v2
feat/session-end-push-gate           feat/session-end-push-gate-v2
salvage/preflight-verify-merged-ghcache-wip
design/unified-reconciliation-gate   doctrine/adopt-substrate-first
chore/gitignore-state-negations
```
The claim to test: they landed **by re-derivation** — content byte-identical to master, SHAs differ —
and all 16 are published on `gitea` at their exact local SHA.

## VERIFY PER BRANCH — a narrative is not evidence
"They all landed by re-derivation" is a story. A diff is proof. For EACH of the 16:
- **CONTENT comparison against origin/master.** `git diff origin/master..<branch>` empty, or a
  file-level diff proving each unique commit's content is already present. **A commit-count
  comparison is NOT content evidence.**
- **Re-verify the gitea publication yourself** — `git branch -r --contains <sha>`, naming the remote
  ref. That publication is the ENTIRE safety net for this operation; do not inherit the claim from
  the earlier report.
- Verdict: **EQUIVALENT / NOT-EQUIVALENT / AMBIGUOUS.**

⚠️ **`feat/github-limits-hardening` and `-v2` need extra care:** `GITHUB-LIMITS-HARDENING` is a LIVE
board ticket that four other tickets depend on. If its branch content is NOT on master, that is real
unlanded work blocking a live dependency chain — surface it loudly, do not reap it.

## THEN, AND ONLY THEN, REAP
For branches verified EQUIVALENT **and** confirmed on gitea:
- **Record every SHA in the ruling file BEFORE deleting.** A deletion with no recorded SHA is
  unrecoverable — do not perform one.
- Delete **locally only**. Never delete a remote branch.
- NOT-EQUIVALENT or AMBIGUOUS → **SKIP**, describe the unlanded content, author a follow-up ticket.

## ALSO EXPLAIN THE PATTERN (the "deep dive" half)
Five pairs exist as `-v2`/`-rederive` duplicates. Something in the landing flow makes people re-cut a
branch rather than continue the original. **Explain WHY, with evidence from the landing scripts**
(`fleet/land.sh`, `fleet/land-push.sh`). That mechanism is the prime suspect for the wider sprawl
(164 rig + 90 product branches) — fixing it is worth more than deleting these 16. Cross-reference
`fleet/board/BRANCH-SPRAWL-ROOT-CAUSE.md`; do not duplicate its scope.

## RULES
- A zero-hit grep is NOT evidence — read the diffs.
- FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail` on verification paths.
- NON-VACUOUS: a ruling covering fewer than 16 branches is incomplete, not partial credit.
- Do NOT touch `/home/stack/code/charon`, `/home/stack/charon-wt/*` or any other agent's worktree.
- State what you verified by RUNNING vs by READING.

## REPORT BACK (short)
Per-branch verdict table (16 rows) · how many reaped / skipped and why · the `-v2` pattern
explanation · confirmation every deleted SHA was recorded first · the commit SHA.

## LAST STEP (REQUIRED)
```
git add -A && git commit -m "RIG-BRANCH-16-DEEPDIVE: per-branch equivalence ruling + verified reaps"
```
Do NOT push.

## Dependencies & sequence
- **Depends on: NOTHING. Startable immediately.** Owns one new state file; deletes only local refs.
- **Related:** BRANCH-SPRAWL-ROOT-CAUSE owns the general cause — share findings, do not re-derive.
- **Wave:** parallel lane, P0.

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
