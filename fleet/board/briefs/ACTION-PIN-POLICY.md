# SESSION — ACTION-PIN-POLICY: major-tag first-party actions, keep SHA pins for third-party

**Model:** economy tier — mechanical, low-risk YAML edit across four files, no product code.
**Repo:** charon · **Ticket:** ACTION-PIN-POLICY
**Base branch/worktree:** `chore/action-pin-policy` at
`/home/stack/code/charon-fleet-ACTION-PIN-POLICY` (an isolated worktree off latest
`origin/master` — do NOT work in the shared main tree `/home/stack/code/charon`).

## FIRST ACTS (mandatory)
1. `cd` into the worktree (create it off latest `origin/master` if absent).
2. `git fetch origin && git merge origin/master`; resolve conflicts; re-run gates after.
3. Register on the session-bridge (`register`: your `session_id`, `repo: "charon"`,
   `ticket: "ACTION-PIN-POLICY"`, `status: "in-progress"`); heartbeat via `update`.
4. Read `fleet/CI-ACTION-BUMP-INVESTIGATION.md` for the Dependabot SHA-tracking context this
   policy is compatible with.

## FILES OWNED (touch only these)
- `.github/workflows/ci.yml`
- `.github/workflows/heavy.yml`
- `.github/workflows/release.yml`
- `.github/workflows/windows-exe.yml`

## THE TASK (what's broken)
Every `uses:` line in all four workflow files is currently pinned to a full 40-char commit
SHA with a trailing `# vX` comment — including GitHub's OWN first-party `actions/*` steps:
```yaml
- uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5  # v4
- uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065  # v5
- uses: actions/upload-artifact@b4b15b8c7c6ac21ea08fcf65892d2ee8f75cf882  # v4.4.3
```
The fragility sweep flagged this as "overcomplicated, fails silently": a first-party SHA pin
doesn't move when GitHub patches a tag, and Dependabot's own SHA-pin tracking already follows
the moving `v4`/`v5` ref behind the scenes (see `CI-ACTION-BUMP-INVESTIGATION.md` — this is
documented as *desired* Dependabot behavior for Charon, not a bug). A stale/incorrect trailing
`# vX` comment can silently decouple from the SHA it claims to describe, and nobody notices
until something breaks.

## REQUIRED CHANGE (operator-approved split)
Convert per this policy, across all four files:
1. **First-party `actions/*` → plain major-version tag.** `actions/checkout`,
   `actions/setup-python`, `actions/upload-artifact` (and any other bare `actions/*` step) →
   `@v4`, `@v5`, `@v4` respectively (major tag only, no minor/patch pin — GitHub controls
   this trust boundary end-to-end and the whole point is to track patches automatically).
2. **Everything else stays a strict full-SHA pin, UNCHANGED.** `docker/login-action`,
   `docker/build-push-action`, `actions/attest-build-provenance` (in `release.yml`) are
   third-party / supply-chain-sensitive and keep their current SHA pins exactly as-is — do
   NOT touch these lines beyond maybe tidying a comment.
3. **Leave a one-line comment on each converted line** noting the policy, e.g.:
   ```yaml
   - uses: actions/checkout@v4  # first-party major-tag policy (ACTION-PIN-POLICY)
   ```
4. Grep every workflow file for `uses:` lines to make sure none are missed — there are ~14
   occurrences across the four files (some steps like `checkout`/`setup-python` repeat across
   multiple jobs in the same file; convert every occurrence, not just the first).

## ACCEPTANCE CRITERIA
- No first-party `actions/*` `uses:` line contains a 40-char SHA anymore — all use a bare
  `@vN` tag.
- Every third-party (`docker/*`, `actions/attest-*`) `uses:` line is UNCHANGED (still the
  exact same SHA it had before this ticket).
- `grep -rEn "uses: (docker|actions/attest)[a-zA-Z0-9._/-]*@v[0-9]" .github/workflows/*.yml`
  returns NOTHING (no third-party tag-only pin slipped in).
- `grep -rq "uses: actions/checkout@v4" .github/workflows/*.yml` succeeds.
- YAML stays syntactically valid (a workflow file with broken YAML fails silently in CI, so
  visually diff every changed line, don't just trust `sed`).

## MERGE GATE (not pytest-alone)
This ticket touches no `src/`/`tests/` Python, so the product pytest/ruff/mypy suite is
unaffected — but still run the full gate from the worktree to prove nothing else broke:
`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`
Standard review, mechanical — the reviewer's main job is confirming the third-party lines
truly didn't change (diff each one against the pre-ticket SHA) and that first-party
occurrences weren't missed.

## Dependencies & sequence
- **depends_on:** *(none)* — independently buildable, no shared files with any other live
  ticket.
- **Note:** CI-WORKFLOW-POLICY-GATE (separate ticket) will later add an automated gate that
  enforces this exact split going forward. That ticket does not block this one, but its gate
  must NOT be wired into the live CI pipeline until this ticket has merged (its own ticket
  note says so) — no action needed here, just don't be surprised if you see that ticket
  referencing this one.

## REPORT BACK (short — no diffs)
Files changed, count of lines converted per file, and the commit SHA.

## LAST STEP (REQUIRED) — commit, do not skip
```
git add -A && git commit -m "chore(ci): major-tag first-party actions, keep SHA pins for third-party"
```
Report the commit SHA back to the manager.

do NOT push, do NOT open a PR, do NOT merge — the launcher publishes; the deny-list blocks push inside the session.
