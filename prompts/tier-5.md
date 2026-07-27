Make the fleet claim path data-backed by tier ranks while preserving `flock` atomicity
(DTC HARD REQ #5). Canonical tier for this ticket: **high** (mapped to fleet `opus`). Depends
on TIER-3 (merged): `charon tier ranks` emits canonical+alias rank rows. Read
`/home/stack/charon-private/fleet/DTC-tier-abstraction.md` §"Fleet consumption (preserve
flock atomicity — HARD REQ #5)" FIRST, plus the existing
`/home/stack/charon-private/fleet/claim.sh` (note the `flock 9` test-and-set at line ~17 and
the per-ticket `claims/$id` create at ~32, and the current hardwired `rank()`).

GOAL: Parse tier ranks ONCE before `flock` into a bash assoc array (`charon tier ranks`,
legacy fallback); make `rank()` a pure-bash array lookup. The `flock`/claim path stays
untouched.

DESIGN ANCHORS (cite in your review note):
- Parse `tiers.json` ranks ONCE, BEFORE `flock 9`, into a bash assoc array. `rank()` becomes
  a pure-bash array lookup (microseconds) INSIDE the locked loop — NEVER spawn Python under
  the lock (that was Stance A's contention regression).
- Exact pattern from the design:
    declare -A RANK
    if out="$(charon tier ranks 2>/dev/null)"; then        # "low 1\nmed 2\nhigh 3\nopus 3 ..."
      while read -r n r; do RANK["$n"]=$r; done <<<"$out"
    else RANK=([opus]=3 [sonnet]=2 [haiku]=1); fi           # legacy, unchanged
    rank(){ echo "${RANK[$1]:-0}"; }
    exec 9>"$LOCK"; flock 9                                  # atomic claim path UNTOUCHED
- The `flock 9` test-and-set and per-ticket `claims/$id` create are BYTE-FOR-BYTE unchanged;
  `tiers.json` read is read-only/idempotent → no new lock, no race. `meta tier` still reads
  the ticket's label; tickets may say `high` or still `opus` (alias-folded by the rank map).

BUILD:
- /home/stack/charon-private/fleet/claim.sh — load the RANK assoc array before `flock` from
  `charon tier ranks` with the legacy fallback; replace the hardwired `rank()` with the array
  lookup. Do NOT alter the locking/claim-create lines. Verify with a manual claim/release that
  ranking still drains own→lower correctly and the lock path is intact.

CONSTRAINTS: own ONLY the file in your board ticket's `owns:` line
(/home/stack/charon-private/fleet/claim.sh) — nothing else. claim.sh already exists: EDIT it.
Do NOT touch fleet-droid.sh (TIER-6) or any Charon source. Same wave as TIER-4/6/7 (disjoint
files). If your work needs a file outside `owns:`, STOP and report it with a one-line reason.
This is a fleet shell script — keep it POSIX-bash, no new deps. Keep the gate green for the
Charon repo if you touch anything there (you should not). No secrets. Conventional commits.
Write your review note as `docs/review-log/TIER-5.md` in the Charon repo (NEVER the shared
`docs/REVIEW-LOG.md`). Commit ALL work on your branch and STOP — do NOT push, do NOT open a
PR, do NOT run submit.sh; the launcher publishes after you exit.

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
