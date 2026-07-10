# PUBLIC-CLEAN-ENFORCE — review note

Branch: `feat/public-clean-enforce`  (PUBLIC repo `SLOP-Platform/charon`)

> This note is itself public-clean: example leak tokens below are obfuscated
> (`192.168.x.y`, `10.0.1.NN`, `<personal>@gmail.com`) so the file that documents
> the guard does not itself trip the guard it wires in.

## E — author-email scrub (`pyproject.toml`)

- `authors` entry was `{ name = "<personal-given-name>", email = "<personal>@gmail.com" }`.
- Now `{ name = "Nnyan", email = "Nnyan@users.noreply.github.com" }`.
  - Email replaced with a GitHub `users.noreply` form (non-personal).
  - **NOTE / please confirm:** the *name* field held a personal given name, NOT
    the public handle the task assumed. I set it to the public handle `Nnyan`
    (privacy intent + task said "keep the name/Nnyan"). Trivial to change if you
    prefer a different display name.
- Allowlist exception: **none existed** for that email. The public-clean guard
  has no email pattern, so the address was never allowlisted and there was
  nothing to remove. (See follow-up note below.)
- The email appeared **only** in `pyproject.toml` in the working tree
  (tree-wide grep → 1 hit, now scrubbed).

### History-purge follow-up (separate op — NOT done here)
The scrub only stops the leak going forward. The personal email (and the
personal name, and any authored-commit `Author:`/`Committer:` metadata) remain
in **git history**. A history rewrite (git-filter-repo / BFG + force-push +
re-clone) is a separate, coordinated operation and was intentionally NOT run on
this branch.

## F — actually ENFORCE the guard (3 wirings)

Starting state was already partly wired by an earlier commit (`1c54ef4`):
`check_public_clean` was in `gate_runner.CHECKS` and a `.pre-commit-config.yaml`
existed. The three gaps that remained are now closed:

1. **Merge/CI gate registry** — added a `public-clean` entry to
   `tools/gates.json` (domain `public-clean`, enforcer `tools/check_public_clean.py`,
   `ci_step: true`, red_proof `tests/test_public_clean.py`), matching the
   `workflow-policy` / `check_workflows.py` pattern. Added `# @covers: public-clean`
   to `tools/check_public_clean.py` and registered `public-clean` in
   `check_gate_registry.ALL_DOMAINS` so the registry self-validator stays
   consistent (no ORPHAN-COVERS, clean coverage summary). CI already runs
   `python3 -m charon.cli gate`, which runs the `[public-clean]` check → CI now
   fails on an unallowlisted hit.

2. **Pre-commit hook** — added committed dependency-free hook
   `tools/hooks/pre-commit` (executable, mode 100755): scans **staged** files
   (`git diff --cached ... --diff-filter=ACM`) via `check_public_clean.py`.
   Enhanced `check_public_clean.main()` to accept explicit path args (staged
   files) in addition to the whole-tree scan, still honouring the exceptions
   ledger + inline waivers. One-line install documented in `CONTRIBUTING.md`:
   `git config core.hooksPath tools/hooks`. (The pre-existing
   `.pre-commit-config.yaml` is left in place for `pre-commit`-framework users.)

3. **Repo-scan test** — refactored `check_public_clean` to expose
   `scan_tracked()` / `_scan_rel_paths()` (single source of truth shared by
   `main()` and tests). Added `tests/test_public_clean.py::test_tracked_tree_is_public_clean`
   which runs the same whole-tree scan under `pytest` (hence CI) and fails,
   naming file:line, if any tracked file carries an unallowlisted token — closing
   the "tests never scan the real repo" gap. Added
   `test_repo_scan_catches_a_planted_leak` so the scan can't silently become a
   no-op.

## Fail-on-revert test

Command + result (planted a real leak into a tracked file, ran the repo-scan test):
```
printf 'internal_host = "192.168.x.y"\n' > REVERT_DEMO_LEAK.txt && git add REVERT_DEMO_LEAK.txt
PYTHONPATH=src python3 -m pytest -q tests/test_public_clean.py::test_tracked_tree_is_public_clean
  -> 1 failed  (REVERT_DEMO_LEAK.txt:1: internal IP, 192.168/16 range)   # RED with leak
git rm --cached REVERT_DEMO_LEAK.txt && rm REVERT_DEMO_LEAK.txt
PYTHONPATH=src python3 -m pytest -q tests/test_public_clean.py::test_tracked_tree_is_public_clean
  -> 1 passed                                                          # GREEN without leak
```
Interpretation: with the wiring in place a leaked token turns pytest/CI RED;
delete the wiring (this test) and the same leak sails through pytest = pass-through.
The pre-commit hook was verified the same way (staged internal-IP token
`10.0.1.NN` → hook exit 1; clean staging → hook exit 0).

## Full-gate result (the CI gate)

- `ruff check src tests tools` → **PASS**
- `mypy src/charon tools tests` → **PASS** (no issues, 199 files)
- `PYTHONPATH=src python3 -m charon.cli gate` → **PASS** (ruff, mypy, SLOP-boundary,
  version, gate-registry, public-clean all OK)
- `PYTHONPATH=src python3 -m pytest -q` → **PASS** (1414 passed, 1 xfailed, 1 xpassed)

## Recommended follow-up (out of scope, flagged not done)
- The guard has **no email-address pattern**, so it does not detect the very
  class of leak scrubbed in E. Adding one (e.g. a generic `@gmail.com` match,
  paired with the existing inline-waiver escape hatch) would close that hole —
  deferred to avoid committing a personal local-part into the public guard
  source and to keep this change in-scope.

---

## Adversarial-review follow-up (H1 + M1/M2/M3)

Branch `feat/public-clean-enforce`, applying `PUBLIC-CLEAN-ENFORCE-ADVERSARIAL.md`.

### H1 / TASK-K — personal given-name scrub + mechanized catch
- Scrubbed the personal given name from **6 tracked files**: `LICENSE:3`
  (`(c) 2026 <name> (Nnyan)` → `(c) 2026 Nnyan`) and `docs/adr/0001..0005`
  (`Deciders: <name> (…operator)` → `Nnyan (…operator)`). `git grep` now returns
  only the detection-pattern line, which is inline-waived.
- **Mechanized:** added a case-insensitive `\b<name>\b` pattern to `_PATTERNS`
  (desc `personal given name`), with the pattern line inline-waived so the guard
  source itself stays public-clean. Fail-on-revert tests: `test_flags_personal_given_name`
  (+ case-insensitive) red on plant, `test_personal_given_name_removed_is_clean`
  greens on the public handle. Verified: deleting the pattern reds the plant tests.

### M1 — fail-closed git enumeration
- `_tracked_files()` now **raises** on non-zero `git ls-files` rc AND on an empty
  result, instead of returning `[]` (which made `scan_tracked` pass vacuously).
- Test `test_tracked_files_fails_closed_outside_git` drives `_tracked_files()`
  directly (not via `_scan_rel_paths`), asserting it raises outside a repo;
  `test_tracked_files_enumeration_is_nonempty` asserts `pyproject.toml` is in the
  set. Verified: reverting to `return []` reds the fail-closed test.

### M2 — pre-commit scans the STAGED blob, not the working tree
- Added `_staged_content()` (`git show :<path>`) + `check_staged_paths()`, and a
  `--staged` mode in `main()`; the hook now calls `check_public_clean.py --staged`.
  Detection core refactored into shared `_scan_content()` so worktree and staged
  reads can't diverge. `git add -p` / stage-then-edit can no longer slip a leak
  through or false-red a clean commit.
- Tests `test_staged_scan_reads_index_not_worktree` (staged leak + clean worktree
  → flagged) and `test_staged_scan_ignores_unstaged_worktree_leak` (clean stage +
  dirty worktree → clean). Verified: reverting to a worktree read reds both.

### M3 — waiver path documented
- `CONTRIBUTING.md` gains a "Public-clean guard" section documenting both escape
  hatches (inline `public-clean: allow` + the `tools/.public-clean-exceptions.json`
  content-keyed ledger), "add only after review", with the staged-scan note.

### Full gate (this worktree)
- `ruff check src tests tools` → **All checks passed**
- `mypy src/charon tools tests` → **Success, no issues**
- `PYTHONPATH=src python3 -m charon.cli gate` → **all 6 checks OK** (public-clean OK)
- `PYTHONPATH=src python3 -m pytest -q` → **1421 passed, 1 xfailed, 1 xpassed**

Out of scope / unchanged: L1 (author-line email — build-box `git config`, operator
fix), L2 (this review note stripped pre-merge per repo convention), L3 (gate lint
scope), and the email-address pattern follow-up above.
