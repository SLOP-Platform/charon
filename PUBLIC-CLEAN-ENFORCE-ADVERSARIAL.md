# PUBLIC-CLEAN-ENFORCE — adversarial review

Target: `SLOP-Platform/charon` `feat/public-clean-enforce` @ `8563c33`
Reviewer: read-only adversarial (verified against the diff + live execution, not the self-report).

## VERDICT: SHIP-WITH-FIXES

Core enforcement is real and verified. The wiring is not a no-op: the CI `charon gate`
step runs `check_public_clean` (gate_runner.CHECKS[5]), the current tracked tree passes
(`exit 0`, 27/27 unit tests green), and a planted leak turns BOTH the repo-scan pytest and
the pre-commit hook RED (reproduced below). Registry is consistent (`check_gate_registry: OK`,
no ORPHAN-COVERS). But E (name scrub) is incomplete and there are two enforcement gaps that
weaken the "can't silently no-op" claim.

### Verification performed (empirical, in the worktree)
- `python3 tools/check_public_clean.py` → `public-clean OK` exit 0 (clean tree passes ✓).
- `git grep nnyan.tengwar@gmail.com` → **0 hits** (email scrubbed from tracked tree ✓).
- Planted `192.168.5.5` in a tracked file → `test_tracked_tree_is_public_clean` FAILS naming
  `file:1: internal IP (192.168.0.0/16)` ✓; `tools/hooks/pre-commit` exits 1 ✓; removed → green ✓.
- `python3 -m charon.cli gate` → all 6 checks OK ✓. `check_gate_registry.py` → OK ✓.

---

## HIGH

### H1 — E scrub is incomplete: personal given name "Rafael" still in 6 tracked files
The commit changed only `pyproject.toml` (`name = "Rafael"` → `"Nnyan"`). The builder's own
note frames this as removing a *personal given name* for privacy. But "Rafael" remains public in:
- `LICENSE:3` — `Copyright (c) 2026 Rafael (Nnyan)`
- `docs/adr/0001..0005` — `**Deciders:** Rafael (solo operator/operator)` (5 files)

Either "Rafael" is acceptably public (then the pyproject rename is cosmetic and fine) or it is
not (then this change is incomplete — LICENSE + 5 ADRs still leak it). The public-clean guard has
**no name pattern**, so it will never catch this. Operator must decide; this is not CI-blocking.
Fix: if privacy is the intent, scrub "Rafael" from LICENSE + ADRs (or leave pyproject as "Rafael"
and drop the rename). Directly answers attack #5.

---

## MED

### M1 — Fail-open no-op in tracked-file enumeration; the "no-op guard" test does NOT guard it
`check_public_clean.py:78-82` `_tracked_files()` returns `[]` on any non-zero `git ls-files` exit.
`scan_tracked` then returns `[]`, so `test_tracked_tree_is_public_clean` passes VACUOUSLY and the
CLI prints `public-clean OK`. Reproduced: monkeypatching `_tracked_files → []` yields zero
violations and a green scan. `test_repo_scan_catches_a_planted_leak` does **not** cover this — it
calls `_scan_rel_paths([explicit_path], …)`, bypassing `_tracked_files()` entirely. So the
builder's claim that the planted-leak test "guards against a future refactor that silently turns
scan_tracked into a no-op" is **false**: it guards the pattern-matching path, never the
git-enumeration path. If CI ever runs the gate in a non-git context / git errors, the guard passes
silently. Fix: make `_tracked_files` raise on non-zero rc (fail-closed), and add a test asserting
`len(_tracked_files()) > 0` (or that a known-tracked file like `pyproject.toml` is in the scan set).

### M2 — Pre-commit hook scans WORKING-TREE content, not the staged blob
`tools/hooks/pre-commit` collects staged names via `git diff --cached … --diff-filter=ACM`, but
`check_file` (check_public_clean.py:56 `path.read_text()`) reads the file **from disk**, not the
index. With partial staging (`git add -p`, or stage-then-edit), a leak that is *staged* but absent
from the working copy slips through the commit; conversely an *unstaged* working-tree leak
false-reds a clean commit. Fine for the common stage-all workflow, but the hook does not actually
gate what gets committed. Fix: scan staged content via `git show :<path>` / `git cat-file` against
the index.

### M3 — Blast-radius: allowlist/waiver mechanism is undocumented for contributors
The guard now runs tree-wide in CI, and the pre-existing `tools/.public-clean-exceptions.json`
already waives ~30 files of internal tokens (`4-lom`, `/home/stack/charon-private/...`,
`charon-vm`, pinned-action SHAs matching the 40-hex rule). Legitimate future commits — new
`docs/review-log/*` notes, ADRs, handoffs that reference the build rig / hosts / example IPs —
will now RED CI. `CONTRIBUTING.md` documents installing the hook but says nothing about the
exceptions ledger or the `public-clean: allow` inline waiver, so a contributor hitting a false-red
has no documented escape hatch. Fix: document both waiver mechanisms (inline comment + exceptions
file, "add only after review") in CONTRIBUTING.

---

## LOW

### L1 — The scrubbing commit re-introduces the email into history via its own Author line
`8563c33` is authored `Nnyan <nnyan.tengwar@gmail.com>`. The working-tree scrub is correct and the
builder correctly flags the history purge as a separate op, but the build-box `git config` will keep
stamping the personal gmail on every new commit. Fix local `user.email` before further commits.

### L2 — Builder self-review note committed into the public repo
`tools/PUBLIC-CLEAN-ENFORCE-REVIEW.md` (and this file) are committed under `tools/`. Per repo
convention (REVIEW-PACKET.md stripped before merge — see recent history) this note should be
stripped pre-merge; it also carries obfuscated-but-suggestive references to internal tokens.

### L3 — CI `charon gate` lints/typechecks only `src tests`, not `tools`
`gate_runner.py:7-8` runs `ruff/mypy` on `src tests`. The logic this commit adds lives in
`tools/check_public_clean.py`; a type/lint regression there is caught only by the separate manual
CONTRIBUTING step, not by CI's gate. Pre-existing gate scope, not introduced here, but relevant.

---

## Attack-by-attack summary
1. CI fails on a real leak, clean tree passes — **YES, verified** (gate + pytest both green on
   clean tree, red on planted leak). Note: the gate-run wiring predates this commit; this commit
   adds registry consistency + the pytest guard.
2. Repo-scan test honesty — **honest for the pattern path** (fails naming file:line on a real
   planted leak) but **does not cover the git-enumeration no-op** (M1).
3. Pre-commit hook — blocks a staged leak, is opt-in (`core.hooksPath`), dependency-free, does not
   hard-break normal commits (`--no-verify` bypass documented). Caveat: reads working tree not index
   (M2); setting `core.hooksPath` disables any other local hooks.
4. Blast-radius — real: tree-wide enforcement + undocumented waiver path (M3).
5. E correctness — email fully scrubbed from working tree; **name "Rafael" still leaks in
   LICENSE + 5 ADRs** (H1); history retains both (L1).
6. bash/python glue — correct; hook runs from repo root so relative paths resolve. Only defect is
   the index-vs-worktree read (M2).
