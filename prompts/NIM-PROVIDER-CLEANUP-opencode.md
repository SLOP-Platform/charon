# SESSION — NIM-PROVIDER-CLEANUP: fix the provider-onboarding path (incl. a key leak)

**Model:** a NON-ANTHROPIC model through the Charon gateway (`opencode --model charon/<model>`).
Never Claude/Anthropic. Graded sample, work_class `rig-meta`.
**Repo:** charon-private (PRIVATE rig) · **Ticket:** NIM-PROVIDER-CLEANUP
**Branch:** `fix/nim-provider-cleanup`
**Worktree:** `/home/stack/charon-private-wt/NIM-PROVIDER-CLEANUP` — ISOLATED.
**Do NOT work in `/home/stack/charon-private` directly** — the manager holds that checkout.
One checkout, one agent.

## ⚠ BLOCKING PRECONDITION — CHECK THIS FIRST, DO NOT SKIP
This ticket **depends on `ADD-PROVIDER-MECHANIZE-COMPLETE`**, which owns the SAME two files
(`fleet/add-provider.sh`, `fleet/add-provider-interactive.sh`) and is **already in flight** in
worktree `/home/stack/charon-private-wt/ADD-PROVIDER-MECHANIZE-COMPLETE`.

Before writing anything, verify that ticket has LANDED on master:
```
ls /home/stack/charon-private/fleet/state/done/ADD-PROVIDER-MECHANIZE-COMPLETE 2>/dev/null && echo LANDED || echo NOT-LANDED
```
If **NOT-LANDED**: STOP. Report "blocked on ADD-PROVIDER-MECHANIZE-COMPLETE" and exit. Do not start.
Two concurrent writers of the onboarding scripts is exactly the collision the board forbids.
If **LANDED**: rebase onto it and proceed.

## FIRST ACTS
0. **Register on the session-bridge** — `session-bridge_register(session_id="<an UNUSED Jedi name;
   kit-fisto and qui-gon-jinn are taken>", name="NIM-PROVIDER-CLEANUP", repo="charon",
   ticket="NIM-PROVIDER-CLEANUP", status="in-progress", model="<your model>")`.
   **Then `session-bridge_update` every ~5 minutes as a HEARTBEAT** — the lease is 600s; a session
   that stops heartbeating is purged from the board and goes invisible to the manager.
1. `git -C /home/stack/charon-private worktree add -b fix/nim-provider-cleanup /home/stack/charon-private-wt/NIM-PROVIDER-CLEANUP master`
2. `cd /home/stack/charon-private-wt/NIM-PROVIDER-CLEANUP`
3. Read the ticket (BINDING): `fleet/board/NIM-PROVIDER-CLEANUP.md`

## THE THREE DEFECTS

**(a) FALSE FAILURE REPORT.** `fleet/add-provider.sh` step 4 does not pass `--base-url`. Adding a
NON-PRESET provider therefore reports FAILED even though the add SUCCEEDED. An operator who believes
the report re-runs it or abandons a provider that is in fact configured. A tool that lies about its
own outcome is worse than one that fails.

**(b) SECRET LEAK — the highest-value item here.** `fleet/add-provider-interactive.sh` ECHOES the API
key as it is typed. Read it without echo (`read -rs`, or `getpass` in python) and ensure it is not
printed afterwards in confirmations, logs, or error paths. Audit the WHOLE script for the key reaching
stdout/stderr — not just the prompt line. Keys in scrollback survive terminal history, screen shares
and recordings.

**(c) MISSING LIMITS.** NVIDIA NIM has no rate-limit/credit entries in the free-tier catalog, so
free-tier planning cannot see it. Add its real limits — **sourced, not guessed**, recording where each
number came from. A wrong limit is worse than a missing one, because planning will trust it.

## REQUIRED PROOF (green is not proof)
- (a) Add a non-preset provider with an explicit base-url: reports SUCCESS and the provider is present
  afterwards. Show the command and output, before and after.
- (b) **PROVE the key never reaches the terminal:** run the interactive add with an obviously-fake
  dummy key while capturing stdout+stderr to a file, then grep that capture for the dummy value and
  show ZERO hits. Assert the capture is NON-EMPTY first — grepping an empty file passes trivially.
  Also confirm no key lands in any log the script writes.
- (c) NIM entries present in the free-tier catalog with a cited source per number.
- Regression test in `fleet/tests/add-provider.test.sh` covering (a) and (b). **RED-PROOF the (b)
  test by execution:** revert the no-echo read -> test goes RED naming the leak. Report BOTH exit codes.
- **NEVER commit or print a real key.** Check your own diff for secrets before committing.
- FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail` on verification paths.
- State what you proved by RUNNING vs by READING, and which git ref you measured on.

## OWNS — do not touch anything else
`fleet/add-provider.sh`, `fleet/add-provider-interactive.sh`, `fleet/state/free_tier_catalog.json`,
`fleet/tests/add-provider.test.sh`. If the fix appears to need another file, STOP and report.

## REPORT BACK (short — no diffs)
Precondition result (LANDED / NOT-LANDED) · files changed · the zero-hit grep proof for (b) · both
exit codes from the red-proof · sources cited for the NIM limits · the commit SHA.

## LAST STEP (REQUIRED)
```
git add -A && git commit -m "NIM-PROVIDER-CLEANUP: fix false-FAILED add, stop echoing the API key, add NIM free-tier limits"
```

Do NOT push.

## Dependencies & sequence

- **Depends on: ADD-PROVIDER-MECHANIZE-COMPLETE** — TRUE single-writer sequencing (same two files,
  already in flight). Not merge order: co-writing would clobber it.
- **Concurrency safety:** rig-side, disjoint from the entire Switchboard product wave.
- **Blocks:** nothing. (b) is a real security fix and should not wait long once unblocked.
- **Wave:** parallel lane, P2.
