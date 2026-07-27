# SESSION — SW-STATIC-LEGS-RETIRE (P0): make discovery the SOLE source of pool membership

**Model:** a NON-ANTHROPIC model through the Charon gateway (`opencode --model charon/<model>`).
Never Claude/Anthropic. Graded sample, work_class `routing`, tier `frontier`.
**Repo:** charon (PUBLIC) · **Ticket:** SW-STATIC-LEGS-RETIRE · **Branch:** `feat/sw-static-legs-retire`
**Worktree:** `/home/stack/charon-wt/SW-STATIC-LEGS-RETIRE` — ISOLATED.
**Do NOT work in `/home/stack/code/charon`** (manager holds it) or any other agent's worktree.
One checkout, one agent.

## THIS IS THE PAYLOAD OF THE WHOLE WAVE — AND THE HIGHEST BLAST RADIUS
Everything else in this wave is scaffolding. This is the ticket that actually makes ADR-0011 true.
It is also the one that can strand every model in the gateway if you get it wrong: you are removing
the static fallback that currently masks any gap in discovery. **Read the safety section before you
delete anything.**

## ⚠ BLOCKING PRECONDITION
Depends on **SW-IDENTITY-FOLD** as a REAL BUILD PREREQ. Pool membership is keyed by
`_normalize_model_id` (`src/charon/proxy.py`), which `routing_policy/catalog_refresh.py:61-68`
imports directly. Retiring static legs while the identity table is still wrong bakes the orphan-pool
defect into the sole remaining membership source, with no fallback left to mask it.

Verify it landed on master:
```
git -C /home/stack/code/charon log origin/master --oneline | grep -q "SW-IDENTITY-FOLD" && echo LANDED || echo NOT-LANDED
```
If **NOT-LANDED**: STOP, report "blocked on SW-IDENTITY-FOLD", exit. Do not start.

## FIRST ACTS
0. **Claim your session name MECHANICALLY — do not invent one:**
   ```
   NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"
   echo "claimed: $NAME"
   ```
   Then `session-bridge_register(session_id="<the claimed NAME>", name="SW-STATIC-LEGS-RETIRE",
   repo="charon", ticket="SW-STATIC-LEGS-RETIRE", status="in-progress", model="<your model>")`.
   **Never reuse a name you see on the board — those sessions are LIVE.**
   Then `session-bridge_update` every ~5 min as a HEARTBEAT (600s lease, else you are purged).
1. `git -C /home/stack/code/charon fetch origin`
2. `git -C /home/stack/code/charon worktree add -b feat/sw-static-legs-retire /home/stack/charon-wt/SW-STATIC-LEGS-RETIRE origin/master`
3. `cd /home/stack/charon-wt/SW-STATIC-LEGS-RETIRE`
4. Read the ticket (BINDING): `/home/stack/charon-private/fleet/board/SW-STATIC-LEGS-RETIRE.md`
5. Read `docs/adr/0011-the-switchboard-demand-routed-no-pools.md` (Accepted) — INV-SW1/2/3.

## THE STATE (pre-verified on the live 4-LOM gateway — do NOT re-derive)
- `routing_policy/catalog_refresh.py` IS enabled: `{"enabled": true, "ttl_s": 21600}`. It polls every
  provider's `GET /models` and bridges discovered model->providers into `srv.pools`
  (`refresh_and_bridge`, ~:249).
- **4384 pools live vs 859 file entries** — discovery is already doing the work.
- RESIDUE (the target): live `/data/models.json` has **859 entries**, of which **175 carry a
  hand-pinned `upstream_model`** and **88 carry `"enabled": false`**.

The static-leg surface, end to end:
- `routing_policy/__init__.py:133` — reads `upstream_model` into the route
- `routing_policy/__init__.py:165-171` — drops `enabled: false` before pools are built
- `pools.py:82` — re-reads `upstream_model`
- `catalog_refresh.py:107-128` — the discovery source that must replace them

## THE SAFETY REQUIREMENT — DO THIS BEFORE YOU DELETE ANYTHING
Removing the static legs removes the net. Prove discovery covers what they covered:

1. **Snapshot BEFORE:** capture the full set of routable pool ids and their provider membership as it
   is today (static + discovery). Save it to a file in the worktree.
2. **Snapshot AFTER:** same capture with static legs retired (discovery only).
3. **DIFF THEM AND REPORT IT.** Any pool id that EXISTS before and is MISSING after, or any pool that
   loses its last live provider, is a **STRAND** — the exact INV-SW2 defect this wave exists to kill.
   A strand is a STOP condition, not a footnote: report it and do not proceed to delete that leg.
4. If discovery genuinely cannot reach something a static leg reached, that is a **finding about
   discovery**, not a reason to keep the leg quietly. Say so explicitly and STOP.

A net-zero or net-positive diff is the only acceptable outcome. "It looked fine" is not the diff.

## REQUIRED CHANGE
Make discovery the sole source of pool membership: retire the `upstream_model` and `enabled: false`
consumption from the selection path so a pool member exists **only** because discovery produced it.
- Do NOT add a second membership source. Do NOT add a compatibility shim that keeps reading the old
  fields "just in case" — that is the static list surviving under a new name.
- `enabled: false` may have a legitimate OPERATOR-INTENT meaning (deliberately disabled provider).
  If so, that intent must live somewhere honest (an explicit operator control), not as a silent
  membership filter. Decide, implement, and STATE which you chose. Do not delete an operator control
  by accident.
- Config files are DATA, not code: you own the code path, not `/data/models.json` on the gateway.

## REQUIRED PROOF (green is not proof)
- `tests/test_static_legs_retired.py`: assert no pool member originates from a static field.
- **RED-PROOF BY EXECUTION:** re-introduce one hand-pinned leg -> the test goes RED naming it.
  **Report BOTH exit codes.** A green you did not first make fail is not evidence.
- The before/after pool diff from the safety section, pasted in your report with counts.
- NON-VACUOUS: a test over an empty pool set must be RED, never a silent pass.
- FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail` on verification paths.
- `PYTHONPATH=src python3 -m charon.cli gate` GREEN and `PYTHONPATH=src python3 -m pytest -q` GREEN.
- State what you proved by RUNNING vs by READING, and which git ref you measured on.

## BOUNDARY
Product is PUBLIC: no `/home/stack` paths, no internal IPs or hostnames, no fleet/rig/SLOP
references, no secrets in `src/` or committed config.

## OWNS — do not touch anything else
`src/charon/routing_policy/catalog_refresh.py`, `src/charon/routing_policy/__init__.py`,
`src/charon/pools.py`, `tests/test_static_legs_retired.py`.
**`src/charon/proxy.py` is NOT yours** (SW-IDENTITY-FOLD owns it) and neither is `forwarder.py`.
If the change appears to need either, STOP and report.

## REPORT BACK (short — no diffs)
Before/after pool counts and the strand diff · what you did with `enabled: false` and why · both exit
codes from the red-proof · gate pass/fail · the commit SHA.

## LAST STEP (REQUIRED)
```
git add -A && git commit -m "SW-STATIC-LEGS-RETIRE: discovery is the sole source of pool membership"
```

Do NOT push. **NEVER use `WORK_LEASE_BYPASS=1`** — if a gate refuses your commit, STOP and report.

## Dependencies & sequence
- **Depends on: SW-IDENTITY-FOLD** (build prereq, disjoint owns — see precondition above).
- **Blocks:** SW-INV-SW2-GATE assertion 3 ("no pool member exists that discovery did not produce")
  IS this ticket's post-condition.
- **Concurrency safety:** disjoint from SECRET-HOTROTATE (`secrets.py`), SW-P2-METER-OBSERVED
  (`balance.py`) and SW-P2-CONTEXT-ADMIT (`forwarder.py`). All may run concurrently.
- **Wave:** wave 1, P0 — the payload of the Switchboard convergence.

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
