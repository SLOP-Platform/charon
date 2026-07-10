# SESSION — CI-WORKFLOW-POLICY-GATE: one executable gate for CI workflow policy

**Model:** strong tier — new gate + fixture-driven red-proof test suite (Structural Rule 3),
non-trivial YAML-lite parsing without external deps.
**Repo:** charon · **Ticket:** CI-WORKFLOW-POLICY-GATE
**Base branch/worktree:** `feat/ci-workflow-policy-gate` at
`/home/stack/code/charon-fleet-CI-WORKFLOW-POLICY-GATE` (an isolated worktree off latest
`origin/master` — do NOT work in the shared main tree `/home/stack/code/charon`).

## FIRST ACTS (mandatory)
1. `cd` into the worktree (create it off latest `origin/master` if absent).
2. `git fetch origin && git merge origin/master`; resolve conflicts; re-run tests after.
3. Register on the session-bridge (`register`: your `session_id`, `repo: "charon"`,
   `ticket: "CI-WORKFLOW-POLICY-GATE"`, `status: "in-progress"`); heartbeat via `update`.
4. Read `AGENTS.md` Structural Rule 3 ("every new gate added to tools/ must land with its
   red-proof test in tests/ in the same commit") and `tools/gates.json`'s existing entries
   (`boundary-check`, `ruff-lint`) for the registration shape before writing anything.
5. Read `tools/check_boundary.py` for the house style of a lightweight, stdlib-only, no-YAML-
   dependency source scanner — this gate should read the same way.

## FILES OWNED (touch only these)
- `tools/check_workflows.py` *(new)*
- `tools/gates.json`
- `tests/test_check_workflows.py` *(new)*

## THE TASK (what's broken)
The fragility sweep found CI workflow policy "split across comments not executable": the
action-pin split (first-party major-tag vs third-party SHA — see the separate
ACTION-PIN-POLICY ticket), the Windows-smoke fragility class (async `Start-Process`
launch-then-poll patterns that already caused rot on `windows-exe.yml`, per
HANDOFF-2026-07-04-v2 finding #2), and packaging-trigger scoping each exist ONLY as prose
comments in the workflow files a human has to remember to re-apply. Nothing catches drift
when someone adds a new workflow step, or reverts a previous fix, without re-reading every
comment.

## REQUIRED CHANGE
Write `tools/check_workflows.py`, a stdlib-only (no PyYAML — privileged core stays
stdlib-only) scanner over `.github/workflows/*.yml` enforcing THREE checks:

1. **Action-ref policy.** Every `uses:` line where the action is `actions/*` (first-party)
   must be pinned to a bare major-version tag (`@vN`, e.g. `@v4` — reject anything with a
   40-char hex SHA, and reject minor/patch-pinned tags like `@v4.4.3`). Every `uses:` line
   for a NON-`actions/*` action (`docker/*`, `actions/attest-*`, any other third-party) must
   be pinned to a full 40-char commit SHA (reject a bare tag). You do not need a real YAML
   parser — line-scan for `uses:\s*([^\s@]+)@(\S+)` the same lightweight way
   `check_boundary.py` line-scans `src/` for forbidden strings.
2. **Reject fragile Windows smoke patterns.** Flag any occurrence of `Start-Process` inside a
   `run:` block (case-insensitive) — this is the known-fragile async-launch-then-poll
   PowerShell pattern.
3. **Require a `paths:` filter for packaging-sensitive workflows.** Any workflow whose `on:`
   block has a `push:` or `pull_request:` trigger AND whose jobs build/package the product
   (heuristic: the workflow file matches `release.yml`, `windows-exe.yml`, or a job name
   containing `image-smoke`/`modeA-isolation`/`package`/`build`) must have a `paths:` key
   under that trigger. `ci.yml`'s `push`/`pull_request` triggers (which run the fast
   pytest/lint gate on every change) are exempt — this check targets HEAVY packaging builds,
   not the fast gate.

`check_workflows.py` should print one violation per offending line (file:line + reason) and
exit non-zero if any violation is found across all `.github/workflows/*.yml`, exit 0 if clean
— mirror `check_boundary.py`'s CLI shape (`python3 tools/check_workflows.py <dir>`).

Register the gate in `tools/gates.json` as a new entry (follow the existing `boundary-check`/
`ruff-lint` row shape exactly):
```json
{
  "id": "workflow-policy",
  "name": "CI workflow policy gate",
  "domain": "ci-infra",
  "enforcer": "tools/check_workflows.py",
  "covers": "action-ref pin policy, fragile Windows smoke patterns, packaging-trigger path scoping",
  "ci_step": true,
  "invariant": "Every .github/workflows/*.yml conforms to the action-pin/Windows-smoke/path-trigger policy",
  "red_proof": "tests/test_check_workflows.py"
}
```

## RED-PROOF TEST (Structural Rule 3 — mandatory, same commit)
Write `tests/test_check_workflows.py` with IN-MEMORY fixture workflow YAML strings (write
them to a `tmp_path` fixture directory, don't touch the real `.github/workflows/`) covering:
- A BAD fixture with a third-party action pinned to a bare tag (`docker/build-push-action@v6`)
  → gate must reject it.
- A BAD fixture with a first-party action pinned to a full SHA instead of a major tag
  → gate must reject it.
- A BAD fixture containing `Start-Process` in a `run:` block → gate must reject it.
- A BAD fixture that's a packaging workflow (matches the packaging heuristic) with a `push:`
  trigger and NO `paths:` key → gate must reject it.
- A GOOD fixture combining a compliant first-party major-tag, compliant third-party SHA pin,
  no `Start-Process`, and a `paths:`-scoped packaging trigger → gate must accept it (exit 0,
  no violations printed).
Per the standard "prove the gate actually gates" discipline: each BAD-fixture test must FAIL
before `check_workflows.py`'s corresponding check exists/works, and pass only once the logic
is correct — don't write a test that trivially passes regardless of the gate's real behavior.

## ACCEPTANCE CRITERIA
- `PYTHONPATH=src python3 -m pytest tests/test_check_workflows.py -q` green.
- `tools/gates.json` parses as valid JSON with the new `workflow-policy` entry present.
- Do NOT run `tools/check_workflows.py` against the LIVE `.github/workflows/*.yml` as part of
  this ticket's acceptance, and do NOT add it to `ci.yml`'s own step list or any pre-commit
  hook. The real workflow files still have first-party actions SHA-pinned today (that's
  ACTION-PIN-POLICY's job, a separate ticket with disjoint owns) — wiring this gate against
  live files before that ticket merges would redden CI on pre-existing state this ticket does
  not own and must not fix as a side effect.

## MERGE GATE (not pytest-alone)
FULL CI from the worktree, ALL green before this is merge-eligible:
`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`
Standard review — the reviewer's main job is confirming each red-proof test genuinely fails
without the corresponding check (temporarily comment out one check, confirm its test reds,
then restore).

## Dependencies & sequence
- **depends_on:** *(none)* — independently buildable, disjoint owns from ACTION-PIN-POLICY
  (that ticket owns `.github/workflows/*.yml`; this one owns `tools/`+`tests/`). The two are
  logically related (this gate enforces the split that ticket performs) but not a build
  dependency — this ticket is proven entirely against its own fixtures.
- **Out-of-band follow-up (manager, NOT this droid):** once BOTH this ticket and
  ACTION-PIN-POLICY have merged, wire `workflow-policy` into `ci.yml`'s step list (or confirm
  `ci_step: true` in `gates.json` already makes it part of the standard gate run — check
  whichever mechanism `tools/check_gate_registry.py` uses to enforce `ci_step` entries are
  actually invoked) as a separate follow-up, not part of this ticket.

## REPORT BACK (short — no diffs)
Files changed, test names, gate pass/fail, and the commit SHA.

## LAST STEP (REQUIRED) — commit, do not skip
```
git add -A && git commit -m "feat(ci): add tools/check_workflows.py action-pin/Windows-smoke/path-trigger gate"
```
Report the commit SHA back to the manager.

do NOT push, do NOT open a PR, do NOT merge — the launcher publishes; the deny-list blocks push inside the session.
