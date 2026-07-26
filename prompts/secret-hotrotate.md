# SESSION — SECRET-HOTROTATE (P0): make provider-key rotation take effect without a restart

**Model:** a NON-ANTHROPIC model through the Charon gateway (`opencode --model charon/<model>`).
Never Claude/Anthropic. Graded sample, work_class `bugfix`.
**Repo:** charon (PUBLIC product) · **Ticket:** SECRET-HOTROTATE · **Branch:** `fix/secret-hot-rotation`
**Worktree:** `/home/stack/charon-wt/SECRET-HOTROTATE` — ISOLATED.
**Do NOT work in `/home/stack/code/charon`** (manager holds it) or in
`/home/stack/charon-wt/SW-IDENTITY-FOLD` (another agent). One checkout, one agent.

## FIRST ACTS
0. **Register on the session-bridge** — `session-bridge_register(session_id="<an UNUSED Jedi name;
   kit-fisto and qui-gon-jinn are taken>", name="SECRET-HOTROTATE", repo="charon",
   ticket="SECRET-HOTROTATE", status="in-progress", model="<your model>")`. MCP is already configured.
   **Then call `session-bridge_update` every ~5 minutes as a HEARTBEAT** — the lease is 600s and a
   session that stops heartbeating is purged from the board and becomes invisible to the manager.
1. `git -C /home/stack/code/charon fetch origin`
2. `git -C /home/stack/code/charon worktree add -b fix/secret-hot-rotation /home/stack/charon-wt/SECRET-HOTROTATE origin/master`
3. `cd /home/stack/charon-wt/SECRET-HOTROTATE`
4. Read the ticket (BINDING): `/home/stack/charon-private/fleet/board/SECRET-HOTROTATE.md`

## PRIOR ART — READ THIS BEFORE WRITING ANYTHING
Eleven models already attempted this ticket in dogfood-eval runs. Their diffs were nearly lost and are
now committed at:
`/home/stack/charon-private/fleet/handoff-notes/salvage-reap-2026-07-26/dogfood-SECRET-HOTROTATE-*.diff`
(plus `.BRIEF.md` files). Read them. They are PRIOR ART, not authority: never reviewed, never landed,
and some runs in that batch produced empty diffs. Compare approaches, then derive and prove your own.
State in your report which prior diffs you looked at and what you took or rejected from them.

## THE DEFECT (pre-verified — do not re-derive)
`src/charon/secrets.py` — `apply_to_env()` uses `os.environ.setdefault`. That is a structural no-op for
any key ALREADY resident in the process environment. So rotating a provider key on disk
(`secrets.json`, or via the gateway host's `/data/rotate-hf.py` helper) does NOT take effect in a
running gateway — only a container restart picks it up.

**Why this is P0:** a rotation you can only perform by restarting is a rotation you will not perform
under pressure — exactly when a key is believed compromised. The security value of rotation is in it
being fast and safe to do.

## REQUIRED CHANGE
Add a force-refresh mode that OVERWRITES already-resident keys so rotation is hot. Coordinate with the
existing `/data/rotate-hf.py` helper on the gateway host (it writes the new token to secrets.json today
and still needs the restart this ticket removes). Do not add a second secrets path — extend the one
that exists (anti-accretion).

## REQUIRED PROOF (green is not proof)
- `tests/test_secrets.py`: a test proving a key already present in `os.environ` IS updated by the
  force-refresh path, and that the default path still respects existing values where that is intended.
- **OBSERVABLE:** rotate a provider key and show the NEW key is used **without a container restart** —
  name the provider, show before/after. If you cannot reach the live gateway, say so explicitly and
  show the strongest in-process equivalent; do not silently downgrade the claim.
- **RED-PROOF BY EXECUTION:** revert to `setdefault` semantics -> the new test goes RED naming the
  stale-key case. **Report BOTH exit codes.** A green you did not first make fail is not evidence.
- **NEVER print, log, or commit a real key value** — not in test output, not in an error path, not in
  your report. Use obviously-fake dummy values. Check your own diff for leaked secrets before
  committing.
- FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail` on verification paths.
- State what you proved by RUNNING vs by READING, and which git ref you measured on.

## GATE (both, from the worktree)
- `PYTHONPATH=src python3 -m charon.cli gate`
- `PYTHONPATH=src python3 -m pytest -q`
- Ticket's own line: `PYTHONPATH=src python3 -m pytest tests/test_secrets.py -v -q`

## BOUNDARY
Product is PUBLIC: no `/home/stack` paths, no internal IPs or hostnames, no fleet/rig/SLOP references,
no secrets in `src/` or committed config. The salvage diffs live in the PRIVATE rig — read them there,
never copy rig paths into product code or comments.

## OWNS — do not touch anything else
`src/charon/secrets.py`, `tests/test_secrets.py`. If the fix appears to need another file, STOP and
report.

## REPORT BACK (short — no diffs)
Files changed · which prior-art diffs you read and what you took/rejected · test names · both exit
codes from the red-proof · gate pass/fail · how you proved hot-rotation observably · the commit SHA.

## LAST STEP (REQUIRED)
```
git add -A && git commit -m "SECRET-HOTROTATE: force-refresh so provider-key rotation takes effect without a restart"
```

Do NOT push. **NEVER use `WORK_LEASE_BYPASS=1`** — if any gate refuses your commit, STOP and report rather than bypassing it.

## Dependencies & sequence

- **Depends on: NOTHING. Startable immediately.** Product-side, owns `src/charon/secrets.py` +
  `tests/test_secrets.py`, which no other live board ticket owns.
- **Concurrency safety:** disjoint from the entire Switchboard wave — SW-IDENTITY-FOLD owns
  `proxy.py`, SW-STATIC-LEGS-RETIRE owns `routing_policy/`, SW-P2-* own `forwarder.py`/`balance.py`.
  No shared file, so this runs fully concurrent with all of them.
- **Blocks:** nothing on the board. Operationally it unblocks safe key rotation, which is why the
  operator raised it to P0.
- **Wave:** parallel lane, P0.
