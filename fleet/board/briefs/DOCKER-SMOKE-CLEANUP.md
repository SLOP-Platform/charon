# SESSION — DOCKER-SMOKE-CLEANUP: trap-based cleanup + dynamic name/port for Docker smokes

**Model:** economy tier — small, mechanical shell-in-YAML edit to two workflow files.
**Repo:** charon · **Ticket:** DOCKER-SMOKE-CLEANUP
**Base branch/worktree:** `chore/docker-smoke-cleanup` at
`/home/stack/code/charon-fleet-DOCKER-SMOKE-CLEANUP` (an isolated worktree off latest
`origin/master` — do NOT work in the shared main tree `/home/stack/code/charon`).

## FIRST ACTS (mandatory)
1. `cd` into the worktree (create it off latest `origin/master` if absent).
2. `git fetch origin && git merge origin/master`; resolve conflicts; re-run gates after.
3. This ticket `depends_on: ACTION-PIN-POLICY` (real-dep: shared writer of release.yml and
   heavy.yml). Confirm that ticket is merged before starting; if not, this ticket is not yet
   claimable.
4. Register on the session-bridge (`register`: your `session_id`, `repo: "charon"`,
   `ticket: "DOCKER-SMOKE-CLEANUP"`, `status: "in-progress"`); heartbeat via `update`.

## FILES OWNED (touch only these)
- `.github/workflows/release.yml`
- `.github/workflows/heavy.yml`

## THE TASK (what's broken)

### release.yml (`image-smoke` job, ~lines 75-104)
Already does the RIGHT thing partially: run-scoped container name
(`charon-rel-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}`) and a kernel-assigned host port
(`-p 127.0.0.1:0:8080`, read back via `docker port`). But cleanup
(`docker rm -f "$name"`) only runs on the normal fall-through path, right before the final
`test "${ok:-0}" = "1"` line. GitHub Actions runs `run:` blocks under `bash -eo pipefail` by
default, so ANY unexpected early failure between `docker run` and that line — `docker port`
returning empty, a `curl`/`sed` crash outside the retry loop's own `|| true` — skips cleanup
entirely and leaks the container on the shared self-hosted 4-LOM runner, where it can then
collide with a LATER run's container name/port allocation.

### heavy.yml (`image-smoke` job, ~lines 58-70)
Has NEITHER protection: hardcoded `docker run -d --name charon-ci -p 127.0.0.1:8473:8473`.
Two `heavy.yml` runs (weekly schedule + on-demand `workflow_dispatch` can overlap), or a
`heavy.yml` run overlapping a leaked container from a previous failed run, collide with
"name already in use" / "port is already allocated" (exit 125).

## REQUIRED CHANGE

### release.yml
Right after `name="charon-rel-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"` is set, add:
```bash
trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT
```
so cleanup runs unconditionally on ANY exit path (success, `set -e` failure, or the final
`test` assertion's own failure). The existing explicit `docker rm -f "$name"` right before
`test "${ok:-0}" = "1"` can stay (now redundant/idempotent with the trap) or be dropped —
either is fine, just don't leave a DOUBLE trap registration.

### heavy.yml
Mirror `release.yml`'s exact pattern:
- Run-scoped name: `name="charon-ci-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"`
- Kernel-assigned host port: `-p 127.0.0.1:0:8473`, read back with
  `docker port "$name" 8473/tcp`
- Same `trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT` right after `name=` is set
- `docker rm -f "$name" >/dev/null 2>&1 || true` before `docker run` too (release.yml has
  this — belt-and-suspenders against a stale same-named leak from a prior failed run, though
  with the run-scoped name this is mostly defense in depth).
- Update the HTTP check to hit `http://127.0.0.1:${hostport}/healthz` instead of the
  hardcoded `:8473`.

### Optional (small lift only — don't block the ticket on this)
Where it's a small diff, prefer a Python stdlib `urllib.request` retry loop
(`python3 -c "..."` or a short inline script) over the `curl`+`sleep`-loop shell pattern for
the HTTP smoke check — `python3` is already on the runner, no new dependency. If it
complicates the diff or risks behavior drift, skip it and just do the trap/name/port fix.

## ACCEPTANCE CRITERIA
- `release.yml` contains `trap 'docker rm -f` (grep-verifiable).
- `heavy.yml`'s `image-smoke` job no longer contains the literal `--name charon-ci ` fixed
  name or the fixed `-p 127.0.0.1:8473:8473` port mapping — both are now run-scoped
  (`charon-ci-${GITHUB_RUN_ID}...` present, grep-verifiable).
- `heavy.yml` also has a `trap 'docker rm -f` cleanup line.
- YAML stays syntactically valid; the shell blocks stay valid bash (no unmatched quotes from
  the trap single-quote nesting — test locally with `bash -c` on the extracted `run:` block
  if unsure).

## MERGE GATE (not pytest-alone)
This ticket touches no `src/`/`tests/` Python, so the product pytest/ruff/mypy suite is
unaffected — but still run the full gate from the worktree:
`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`
Standard review, mechanical — the reviewer's main job is confirming the trap syntax is
correct bash (single-quote the trap body so `$name` expands at TRAP TIME, not at `trap`
registration time) and that the heavy.yml port/name change doesn't silently break the
`/healthz` check's host/port pairing.

## Dependencies & sequence
- **depends_on:** ACTION-PIN-POLICY (real-dep: shared writer of release.yml/heavy.yml — no
  functional coupling, purely file-collision avoidance; RELEASE-SMOKE-FIX, the only prior
  ticket that touched `release.yml`'s smoke, is DONE and not a live concern). Wave 2 relative
  to ACTION-PIN-POLICY — the fleet auto-claims this once that ticket merges+done.sh.

## REPORT BACK (short — no diffs)
Files changed and the commit SHA.

## LAST STEP (REQUIRED) — commit, do not skip
```
git add -A && git commit -m "chore(ci): trap-based Docker smoke cleanup, dynamic name/port in heavy.yml"
```
Report the commit SHA back to the manager.

do NOT push, do NOT open a PR, do NOT merge — the launcher publishes; the deny-list blocks push inside the session.
