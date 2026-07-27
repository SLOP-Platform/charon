# SESSION — SW-INV-SW2-GATE (P0 gate)

**Model:** NON-ANTHROPIC via the Charon gateway. Never Claude/Anthropic. Graded sample.
**Repo:** charon (PUBLIC) · **Ticket:** SW-INV-SW2-GATE
**Worktree:** `/home/stack/charon-wt/SW-INV-SW2-GATE` — ISOLATED. Do NOT work in `/home/stack/code/charon`
(manager's checkout) or any other agent's worktree. One checkout, one agent.

## FIRST ACTS
0. `NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"; echo "claimed: $NAME"`
   Then `session-bridge_register(session_id="<NAME>", name="SW-INV-SW2-GATE", repo="charon", ticket="SW-INV-SW2-GATE",
   status="in-progress", model="<your model>")`. Never reuse a name on the board.
   If the lease expires, do NOT renew — **re-register**.
1. `git -C /home/stack/code/charon fetch origin`
2. `git -C /home/stack/code/charon worktree add -b $(grep '^branch:' /home/stack/charon-private/fleet/board/SW-INV-SW2-GATE.md | cut -d' ' -f2) /home/stack/charon-wt/SW-INV-SW2-GATE origin/master`
3. `cd /home/stack/charon-wt/SW-INV-SW2-GATE`
4. **Read the ticket — it is BINDING and contains the full rationale, evidence and done-contract:**
   `/home/stack/charon-private/fleet/board/SW-INV-SW2-GATE.md`
   Read it before writing anything. Do not re-derive the facts it states.
5. Read `docs/adr/0011-the-switchboard-demand-routed-no-pools.md` (Accepted) — INV-SW1/2/3.

## WHY THESE THREE GATES EXIST (shared context)
On 2026-07-26 five tickets merged; THREE had done-contracts requiring proof on the LIVE gateway and
none delivered it. The deployed gateway was 15 commits behind master and the orphan pool the anchor
"fixed" was still present in production. A full day of green unit tests, and the observable half of
every contract went unpaid — caught by the operator asking, not by any gate.
You are building the thing that makes that impossible to repeat.

## NON-NEGOTIABLE RULES
- **A gate that is not INVOKED is not a gate.** Prove yours runs by pasting real gate output showing
  it execute — a passing `pytest` is not that proof.
- **NON-VACUOUS:** zero inputs must be RED, never a silent pass. Prove it by running that case.
- **RED-PROOF BY EXECUTION:** break each asserted effect in turn, observe RED naming that effect,
  and **report ALL exit codes** — the green run and every deliberately-broken run. A green you did
  not first make fail is not evidence.
- **FAIL-LOUD:** no `| tail`, `| head`, `|| true`; `set -o pipefail` on every verification path.
- **A mocked assertion of a mocked path is the theater these gates exist to end.** Assert observable
  effects on the surfaces an operator would actually inspect.
- Stay strictly inside the ticket's `owns:`. If the work appears to need another file, **STOP and
  report** — several files here are claimed by up to four live tickets.
- A zero-hit grep is NOT evidence of absence — read the call sites.
- State what you proved by RUNNING vs by READING, and which git ref you measured on.

## BOUNDARY
Product is PUBLIC: no `/home/stack` paths, no internal IPs or hostnames, no fleet/rig/SLOP
references, no secrets in `src/` or committed config.

## GATE (both, from the worktree)
- `PYTHONPATH=src python3 -m charon.cli gate`
- `PYTHONPATH=src python3 -m pytest -q`

## REPORT BACK (short — no diffs)
What the gate asserts · proof it is INVOKED (real gate output) · ALL red-proof exit codes ·
non-vacuity proof · anything you refused to do and why · the commit SHA.

## LAST STEP (REQUIRED)
```
git add -A && git commit -m "SW-INV-SW2-GATE: build the gate + red-proof its assertions"
```
Do NOT push. **NEVER use `WORK_LEASE_BYPASS=1`** — if a gate refuses your commit, STOP and report.

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
