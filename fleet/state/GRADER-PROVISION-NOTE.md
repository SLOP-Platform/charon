# Bench-grader provisioning — operator action (EVAL-GRADER-PROVISION)

Ticket: `fleet/board/EVAL-GRADER-PROVISION.md`. Review: `fleet/state/MODEL-TESTING-ADVERSARIAL-REVIEW.md`
§F2 — the MODEL-PREFLIGHT synthetic battery has never validly discriminated because the
OOB controls fail-closed on grader **infrastructure**, not model quality.

`bench-grader` is a dedicated, isolated unix user (per `fleet/ADR-BENCH-OOB-GRADING.md`).
Everything below needs root or the `bench-grader` login the droid does not have — this is
the operator's half of the fix. The droid's half (code) is done: see "What the droid already
fixed" below.

## Run this (idempotent — safe to re-run any time)

```
sudo /home/stack/charon-private/fleet/benchmark/bench-grader-setup.sh
```

Set `CHARON_FLEET=/path/to/fleet` first if the checkout isn't at the default location
(the script fails loud rather than guessing). It does, in order:

1. `sudo -u bench-grader python3 -c 'import pytest, hypothesis'` — if that fails,
   `apt-get install -y python3-pytest python3-hypothesis`, then re-checks and fails loud if
   still missing (this is review F2's attempt-3 gap: *"No module named pytest"* for
   `bench-grader`'s `python3`).
2. ACL grants so the daemon (`bench-grader`) can traverse into `/home/stack` and read/write
   the fleet tree, WITHOUT making `$KEYS` (the answer keys) readable to anyone else:
   `setfacl -m u:bench-grader:x /home/stack` and `setfacl -m u:bench-grader:rwx <fleet-dir>`.
3. Deploys the load-bearing graders as `bench-grader` (`deploy-preflight-graders.sh`) into
   `/home/bench-grader/keys/preflight/` (0700).
4. Starts `grader-daemon.py` under `bench-grader` if it isn't already running (detached,
   `setsid nohup`, survives the provisioning shell exiting).
5. Verifies every step and exits non-zero on any gap — this is fail-loud by design; it will
   NOT report success unless the substrate is actually usable.

If you'd rather run the steps by hand instead of the wrapper (e.g. to check one piece), the
individual commands it runs are:

```
# 1. test deps for bench-grader's own interpreter
sudo -u bench-grader python3 -c "import pytest, hypothesis" \
  || sudo apt-get update -qq && sudo apt-get install -y python3-pytest python3-hypothesis

# 2. cross-user filesystem reachability (keeps $KEYS isolated — only traverse+rwx on the
#    fleet dir itself, never on the keys dir, which stays 0700 bench-grader-owned)
sudo setfacl -m u:bench-grader:x   /home/stack
sudo setfacl -m u:bench-grader:rwx /home/stack/charon-private/fleet

# 3. deploy the graders (as bench-grader, not root/stack — keeps the keys bench-grader-owned)
sudo -u bench-grader KEYS=/home/bench-grader/keys \
  /home/stack/charon-private/fleet/benchmark/deploy-preflight-graders.sh

# 4. start the daemon (as bench-grader) if not already running
sudo -u bench-grader bash -c \
  "setsid nohup python3 /home/stack/charon-private/fleet/benchmark/grader-daemon.py \
   >/tmp/grader-daemon.log 2>&1 </dev/null &"
```

## Verify it worked

```
pgrep -u bench-grader -fa grader-daemon.py       # daemon running
sudo -u bench-grader python3 -c "import pytest, hypothesis; print('ok')"
sudo -u bench-grader test -r /home/bench-grader/keys/preflight/retry-budget-wire.py && echo deployed
python3 fleet/benchmark/selftest/test_grader_daemon.py   # isolation + versioning checks (runs as stack)
```

Then run a real preflight task through the live daemon end-to-end (no sudo needed for
this part — the spool `req/` dir is world-writable-execute (mode 1733) and `res/` is
world-readable by design, exactly so `stack` can submit/observe without ever touching
`$KEYS`):

```
WT=$(mktemp -d); cp -r fleet/benchmark/preflight-tasks/retry-budget-wire/* "$WT"/
# leave gateway/proxy.py UNMODIFIED (must-fail case) or paste the fixed dispatch()
# from selftest/test_grader_env.sh's PROXY_FIXED (must-pass case)
chmod -R o+rX "$WT"
RUN=verify_$$; python3 -c "import json; print(json.dumps({'run_id':'$RUN','model':'m','unit_id':'retry-budget-wire','kind':'preflight','worktree':'$WT'}))" \
  > /var/lib/bench-grader/spool/req/$RUN.json
sleep 3; cat /var/lib/bench-grader/spool/res/$RUN.json   # expect gate=="pass" or "fail" — NEVER a "fail-closed"/"grader internal error" reason
```

## What the droid already fixed (no sudo needed, in-repo, this branch)

Review F2 attempt 2 (`CONTROLS-STATUS.md`): a real preflight drive got a grader-side
`shutil.Error`/`PermissionError` snapshotting a `.hypothesis` cache file the agent's user
could read but the daemon's `bench-grader` user could not — this aborted the ENTIRE
snapshot (and therefore the grade) over one irrelevant cache artifact, collapsing every
model to the same fail-closed BLOCK regardless of what it actually did. Fixed in
`fleet/benchmark/grader-daemon.py` `_snapshot_worktree` (two-part): `.hypothesis` is now
excluded by name (never even attempted), and any OTHER individual unreadable file is
skipped-and-logged rather than aborting the whole snapshot. Mirrored in
`fleet/benchmark/preflight.sh` `copy_session_files`'s tar excludes. Proven by
`fleet/benchmark/selftest/test_grader_env.sh` — see its FAIL-ON-REVERT section for how to
reproduce the historical bug and confirm the fix is load-bearing.

This code fix does NOT remove the need for the sudo steps above — it only stops one class
of unreadable-cache file from taking down an otherwise-healthy grade. `bench-grader` still
needs pytest/hypothesis installed and the ACL/deploy/daemon steps done at least once per
host (or after `bench-grader`'s home / the fleet checkout is recreated).

## Current status on this box (2026-07-14, this session)

Live-verified against the ALREADY-RUNNING daemon on this box (pid confirmed via
`pgrep -u bench-grader -fa grader-daemon.py`, running since this morning) by submitting
real jobs through the spool as `stack` (no sudo): a MUST-PASS `retry-budget-wire` fixture
graded `gate=="pass"` with `"...suite green"` in the reason (proves `bench-grader` already
has pytest), and the pristine/unmodified fixture graded `gate=="fail"` with a real task
reason (not an infra reason). **On this box, steps 1-4 above already appear to have been
run and are working.** The commands above are recorded so this is reproducible on a fresh
box / after a reset, and so the operator can re-verify at any time — re-run
`bench-grader-setup.sh`, it is idempotent and will report "already running" / "ok" for
anything already provisioned.
