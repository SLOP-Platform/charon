# SESSION — NIM-PROVIDER-CLEANUP: fix the provider-onboarding path (incl. a key leak)

**Model:** a NON-ANTHROPIC model through the Charon gateway (`opencode --model charon/<model>`).
Never Claude/Anthropic. Graded sample, work_class `rig-meta`.
**Repo:** charon-private (PRIVATE rig) · **Ticket:** NIM-PROVIDER-CLEANUP
**Branch:** `fix/nim-provider-cleanup`
**Worktree:** `/home/stack/charon-private-wt/NIM-PROVIDER-CLEANUP` — ISOLATED.
**Do NOT work in `/home/stack/charon-private` directly** — the manager holds that checkout.
One checkout, one agent.

## ⚠ BLOCKING PRECONDITION — CHECK THIS FIRST, DO NOT SKIP
Defects (a) and (b) of this ticket were ALREADY FIXED by `ADD-PROVIDER-MECHANIZE-COMPLETE`
(`d7e03ab`), reviewed and landed 2026-07-26. **Your scope is now (c) ONLY — the free-tier catalog.**

Verify that landing is actually present before you start (a CONTENT check, not a marker file):
```
grep -q 'read -rs' /home/stack/charon-private/fleet/add-provider-interactive.sh && echo LANDED || echo NOT-LANDED
```
If **NOT-LANDED**: STOP, report "blocked — ADD-PROVIDER-MECHANIZE-COMPLETE not merged", exit.
If **LANDED**: proceed with (c) only. Do NOT re-fix (a) or (b) — re-fixing landed work is how a
merge gets clobbered. If you believe (a) or (b) is still broken, STOP and report; do not edit.

## FIRST ACTS
0. **Register on the session-bridge** — `session-bridge_register(session_id="<an UNUSED Jedi name;
   kit-fisto and qui-gon-jinn are taken>", name="NIM-PROVIDER-CLEANUP", repo="charon",
   ticket="NIM-PROVIDER-CLEANUP", status="in-progress", model="<your model>")`.
   **Then `session-bridge_update` every ~5 minutes as a HEARTBEAT** — the lease is 600s; a session
   that stops heartbeating is purged from the board and goes invisible to the manager.
1. `git -C /home/stack/charon-private worktree add -b fix/nim-provider-cleanup /home/stack/charon-private-wt/NIM-PROVIDER-CLEANUP master`
2. `cd /home/stack/charon-private-wt/NIM-PROVIDER-CLEANUP`
3. Read the ticket (BINDING): `fleet/board/NIM-PROVIDER-CLEANUP.md`

## YOUR SCOPE — ONE DEFECT

**(c) MISSING LIMITS.** NVIDIA NIM has no rate-limit/credit entries in the free-tier catalog, so
free-tier planning cannot see it. Add its real limits — **sourced, not guessed**, recording where each
number came from. A wrong limit is worse than a missing one, because planning will trust it.

## REQUIRED PROOF (green is not proof)
- NIM entries present in the free-tier catalog with a cited source per number.
- Regression test in `fleet/tests/add-provider.test.sh` asserting the NIM catalog entries exist and parse. RED-PROOF by execution: remove an entry -> test goes RED naming it. Report BOTH exit codes.
- **NEVER commit or print a real key.** Check your own diff for secrets before committing.
- FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail` on verification paths.
- State what you proved by RUNNING vs by READING, and which git ref you measured on.

## OWNS — do not touch anything else
`fleet/state/free_tier_catalog.json`, `fleet/tests/add-provider.test.sh` ONLY.
The two add-provider scripts are NO LONGER yours — they landed via ADD-PROVIDER-MECHANIZE-COMPLETE. If the fix appears to need another file, STOP and report.

## REPORT BACK (short — no diffs)
Precondition result (LANDED / NOT-LANDED) · files changed · the zero-hit grep proof for (b) · both
exit codes from the red-proof · sources cited for the NIM limits · the commit SHA.

## ⚠ BEFORE YOUR FIRST COMMIT — ACQUIRE THE WORK LEASE
The rig refuses commits from a worktree holding no lease. Run this once, before you start:
```
bash /home/stack/charon-private/fleet/work-lease.sh acquire NIM-PROVIDER-CLEANUP
```
**NEVER use `WORK_LEASE_BYPASS=1`.** The refusal message advertises that bypass; it exists for
emergencies, not for getting past your own commit. Using it defeats a safety gate and will fail
review. If the lease cannot be acquired, STOP and report — do not bypass.

## LAST STEP (REQUIRED)
```
git add -A && git commit -m "NIM-PROVIDER-CLEANUP: add NVIDIA NIM rate-limit/credit entries to the free-tier catalog"
```

Do NOT push.

## Dependencies & sequence

- **Depends on: ADD-PROVIDER-MECHANIZE-COMPLETE** — TRUE single-writer sequencing (same two files,
  already in flight). Not merge order: co-writing would clobber it.
- **Concurrency safety:** rig-side, disjoint from the entire Switchboard product wave.
- **Blocks:** nothing. (b) is a real security fix and should not wait long once unblocked.
- **Wave:** parallel lane, P2.
