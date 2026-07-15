# ADD-PROVIDER-MECHANIZE — review note

## Scope verification

This ticket's `owns:` is `fleet/add-provider.sh, fleet/tests/test_add_provider.sh`.
The worktree diff against `master` is empty (HEAD = origin/master = c6f6e42;
both files already live on the branch and are identical to origin/master):

```
$ git ls-tree HEAD    -- fleet/add-provider.sh             -> 100755 117f06eb…  (matches origin/master)
$ git ls-tree HEAD    -- fleet/tests/test_add_provider.sh  -> 100755 9eb4fe19…  (matches origin/master)
$ git diff --name-only master...HEAD                       -> (empty)
$ git rev-list --left-right --count master...feat/add-provider-mechanize  -> 0\t0
```

That is **expected and correct** for this ticket: the launcher note states
the branch was "freshly created off origin/master" *after* PR #33 already
landed this work (commit a1199bf "feat(fleet): add-provider.sh — one-command
provider onboarding to the live gateway"). The branch was created from a
post-merge master, so the two `owns:` files are already present at HEAD,
identical to their merged state. No additional code change is required
on top of what PR #33 already shipped.

## Files in this ticket

- `fleet/add-provider.sh` (211 lines, mode 100755) — the operator script.
  Backups `/data/providers.json` + `/data/models.json` with timestamped
  `.bak-<UTC-ts>` copies, drives the charon CLI (`providers add` /
  `models import` / `providers test`) over `ssh` -> `docker exec -i`, pipes
  the key over stdin (never on argv / ps / logs), uses an explicit
  `python3 -c "import sys; from charon import config; config.add_model(…,
  provider=, upstream_model=, cost_rank=)"` call for any explicit
  `model:upstream` mapping (no hand-edited JSON), restarts the gateway,
  verifies GET `/v1/models` returns 200 with the bearer token from
  `opencode.json`. `--dry-run` swaps all network calls for deterministic
  logged command strings. Idempotent + fail-loud.
- `fleet/tests/test_add_provider.sh` (134 lines, mode 100755) — 21 assertions
  covering: dry-run exit code, **key VALUE absent from emitted output**
  (the FAIL-ON-REVERT sentinel), exact 7-step CLI call sequence present
  AND in order (backup < add < import < mapping < test < restart <
  verify), `stdin: <redacted, N bytes from …>` marker on the providers-add
  step, no `--key` flag on the providers-add command line, no mapping
  step when no `model:upstream` args given, four argument-validation
  failure modes (bad scheme, missing key file, bad name, too few args),
  idempotency across re-runs.

## Local verification

```
$ bash fleet/tests/test_add_provider.sh
… 21 passed, 0 failed ---
ALL ADD-PROVIDER TESTS PASS

$ PYTHONPATH=. python3 -m pytest -q
… 49 passed in 0.20s
```

Pytest still picks up the 49 repo-internal tests via `pytest.ini`'s
`norecursedirs` (skipping the `benchmark/` fixture tree). The repo's
`src/` and `tools/` trees are not in this worktree (they live in
`charon-public`, the consumer repo — see `fleet/HANDOFF.md`), so the
launcher's `ruff check ; mypy src tests ; python3 tools/check_boundary.py
src ; python3 tools/check_version.py` command is not applicable to this
worktree's surface; `fleet/tests/test_add_provider.sh` is the canonical
acceptance gate for this ticket's files.

## Fail-on-revert sentinel

The `t1` assertion (`printf '%s' "$out" | grep -qF "$SECRET"`) checks the
real KEY VALUE never appears anywhere in `--dry-run` output. Reverting the
stdin pipe to a `--key "$(cat "$KEYFILE")"` argv interpolation will cause
the emitted `docker exec … providers add … --key 'sk-TOTALLY-…'` line to
contain the secret verbatim, and `t1 key value ABSENT from emitted output`
goes RED immediately. `t2c` independently asserts the same by searching
for `--key` on any `providers add` printed command.

## What this ticket does NOT do

- Does not edit `src/`, `tests/`, `tools/`, or any other charon-public tree
  (those live in the public repo, not in this worktree).
- Does not push, open a PR, or run `submit.sh` — the launcher note
  explicitly forbids those steps.
- Does not amend or rebase PR #33 — the work is already merged on
  `master`; this branch was cut from post-merge master precisely so the
  branch label `feat/add-provider-mechanize` exists for tracking purposes.