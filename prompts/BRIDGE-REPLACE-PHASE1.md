# SESSION — BRIDGE-REPLACE-PHASE1 (P0): land the control-plane adapter

**Model:** NON-ANTHROPIC via the Charon gateway. Never Claude/Anthropic. Graded sample.
**Repo:** charon-private (PRIVATE rig) · **Ticket:** BRIDGE-REPLACE-PHASE1
**Worktree:** `/home/stack/charon-private-wt/BRIDGE-REPLACE-PHASE1` — ISOLATED. Do NOT work in `/home/stack/code/charon`
(manager's checkout) or any other agent's worktree. One checkout, one agent.

## FIRST ACTS
0. `NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"; echo "claimed: $NAME"`
   Then `session-bridge_register(session_id="<NAME>", name="BRIDGE-REPLACE-PHASE1", repo="charon", ticket="BRIDGE-REPLACE-PHASE1",
   status="in-progress", model="<your model>")`. Never reuse a name on the board.
   If the lease expires, do NOT renew — **re-register**.
1. `git -C /home/stack/charon-private fetch origin`
2. `git -C /home/stack/charon-private worktree add -b $(grep '^branch:' /home/stack/charon-private/fleet/board/BRIDGE-REPLACE-PHASE1.md | cut -d' ' -f2) /home/stack/charon-private-wt/BRIDGE-REPLACE-PHASE1 master`
3. `cd /home/stack/charon-private-wt/BRIDGE-REPLACE-PHASE1`
4. **Read the ticket — it is BINDING and contains the full rationale, evidence and done-contract:**
   `/home/stack/charon-private/fleet/board/BRIDGE-REPLACE-PHASE1.md`
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
git add -A && git commit -m "BRIDGE-REPLACE-PHASE1: build the gate + red-proof its assertions"
```
Do NOT push. **NEVER use `WORK_LEASE_BYPASS=1`** — if a gate refuses your commit, STOP and report.

## EXTRA — start from the spike, do not rebuild
`fleet/session-ctl.sh` already exists on branch `spike/session-ctl` @ `c74e85b`
(worktree /home/stack/charon-private-wt/D24-SESSION-CTL-SPIKE). Read the spike report first:
`fleet/handoff-notes/SPIKE-SESSION-CTL-2026-07-26.md`. Cherry-pick or copy it forward; do not
re-derive the verbs — they are already VERIFIED.

## ACQUIRE THE LEASE FROM INSIDE YOUR WORKTREE (it binds to the acquiring worktree)
```
bash /home/stack/charon-private/fleet/work-lease.sh acquire BRIDGE-REPLACE-PHASE1
```

## Dependencies & sequence
- **Depends on: D24-SESSION-CTL-SPIKE** — build prereq; it owns `fleet/session-ctl.sh`, the file this
  ticket lands and extends. Do not re-create it.
- **Concurrency safety:** owns the new adapter, the UNOWNED `fleet/summary.sh`, and a new test.
  Deliberately does NOT touch `fleet-droid.sh` (5 owners), `end-session.sh` (4), `droid-bridge.sh` (2)
  or `handoff.sh` (1) — those migrate inside their own owners' tickets in a later phase. If the work
  appears to need any of them, STOP and report.
- **Blocks:** BRIDGE-REPLACE-PHASE2 and eventual deletion of the bridge.
- **Wave:** migration lane, P0 — but fire it in a QUIET WINDOW (see below).

## ⚠ FIRE ONLY IN A QUIET WINDOW
This ticket exercises `stop`/`interrupt` against real opencode sessions. Do NOT run it while the
fleet is busy: an interrupt aimed at the wrong session id kills live work. Before starting, confirm
with `ps -eo pid,etime,args | grep '[o]pencode --model'` and only proceed when the fleet is idle or
the operator has explicitly cleared the window. List PIDs before and after and prove none were touched.
