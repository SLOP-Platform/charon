# SESSION — INERT-STARTUP-CHECK REWORK (P0): it recites the answer instead of finding it

**Model:** NON-ANTHROPIC via the Charon gateway. Never Claude/Anthropic. work_class `tests`.
**Repo:** charon (PUBLIC) · **Branch:** `feat/inert-startup-check` — CONTINUE it.
**Worktree:** `/home/stack/charon-wt/INERT-STARTUP-CHECK` — exists, at `ccb1b79`.

## FIRST ACTS
0. `NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"; echo "claimed: $NAME"`
   Then `session-bridge_register(session_id="<NAME>", name="INERT-STARTUP-CHECK rework",
   repo="charon", ticket="INERT-STARTUP-CHECK", status="in-progress", model="<your model>")`.
   If the lease expires, do NOT renew — **re-register**.
1. `cd /home/stack/charon-wt/INERT-STARTUP-CHECK && git log --oneline -1`  (expect ccb1b79)

## WHAT IS WRONG
`src/charon/startup_check.py`:
```python
INERT_ATTRS = frozenset({"request_inspector", "session_affinity", "observability",
                         "speculative_executor", "consensus_router", "virtual_key_manager"})
def classify_modules(modules):  # returns "INERT" if attr in INERT_ATTRS else "ACTIVE"
```
That is a HARDCODED LIST of the six names the ticket handed you. It does not detect inertness — it
recites it. Three consequences:
1. **It can never find a SEVENTH dead module.** The next one added is silently "ACTIVE".
2. **It fails OPEN** — anything unknown defaults to ACTIVE, on a check whose entire job is finding
   silent deadness.
3. **Your red-proof proved nothing.** Removing `request_inspector` from `INERT_ATTRS` and watching
   tests that read `INERT_ATTRS` go RED shows only that the list matches itself. A red-proof where
   YOU choose the break, and the break is a mutation of the check's own input, is self-consistency —
   not evidence.

Your session report was otherwise exemplary (14/14, gate 21/21, correct scope, two red-proofs). That
is precisely why this slipped: every surface metric was satisfied. The defect was only found by
running an EXTERNAL break the check had never been told about.

## THE FIX — DERIVE the classification
A module is INERT if it is CONSTRUCTED/REGISTERED but never INVOKED ON A REQUEST PATH. Compute that;
do not assert it.
- The request path is `forwarder.py`. Determine which `srv.<attr>` / module attributes it (and the
  handlers it calls) actually USE — method calls, attribute reads that feed behaviour — versus which
  are merely assigned in `proxy_server.py`.
- `tools/check_inert_code.py` gets this WRONG by treating `_MODULE_SPECS` registration as
  reachability. Do not repeat that. Registration is not invocation.
- Static analysis (ast) over the invocation surface is acceptable. A hand-maintained list is not.
- The six known-dead modules become a TEST FIXTURE that your derivation must independently reproduce
  — never the implementation.

## PROOF REQUIRED — the break is SPECIFIED, not yours to choose
- **EXTERNAL RED-PROOF #1 (the acceptance test):** add a genuinely NEW module — construct it in the
  module registry, store it on the server, invoke it NOWHERE — and show your check flags it INERT
  **without any change to your code or any list**. A check that needs editing to notice a new dead
  module has not been fixed.
- **EXTERNAL RED-PROOF #2:** take one currently-INERT module and WIRE it into the forwarder's request
  path; your check must flip it to ACTIVE with no list edit.
- Report BOTH exit codes for each.
- NON-VACUOUS: zero modules inspected is RED, never a silent pass.
- FAIL-CLOSED: an attribute your derivation cannot classify must be reported UNKNOWN and treated as a
  RED, never defaulted to ACTIVE.
- `PYTHONPATH=src python3 -m charon.cli gate` GREEN and `pytest -q` GREEN.

## OWNS — unchanged
`src/charon/startup_check.py`, `tests/test_startup_check.py`.
**Do NOT edit `src/charon/gateway.py`** (four claimants). Keep delivering the wiring snippet for its
owner; your previous NEXT line was correct and should carry forward.

## REPORT BACK — MECHANIZED FORMAT (required)
Validate: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>` ·
Spec: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`
```
=== SESSION REPORT v1 ===
TICKET:       INERT-STARTUP-CHECK
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha>
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> — MUST be the two EXTERNAL breaks above, not list edits
OBSERVABLE:   MET | DEFERRED — <why>
RAN:          <proved by EXECUTING>
READ:         <concluded by READING only>
BRIEF-ERRORS: none | <what this brief got wrong>
BLOCKED-BY:   none | <condition>
NEXT:         <single next action for the manager>
=== END REPORT ===
```

## LAST STEP
```
git add -A && git commit -m "INERT-STARTUP-CHECK: derive inertness from the invocation surface, not a hardcoded list"
```
Do NOT push. **NEVER use `WORK_LEASE_BYPASS=1`.**

## Dependencies & sequence
- **Depends on:** existing `ccb1b79` on this branch — continue it, do not restart.
- **Concurrency safety:** owns its module + test only. gateway.py stays untouched.
- **Wave:** gate lane, P0.
