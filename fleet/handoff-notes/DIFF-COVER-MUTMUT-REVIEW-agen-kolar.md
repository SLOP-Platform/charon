# DIFF-COVER-MUTMUT-ADOPT — Adversarial Review (agen-kolar)

# VERDICT: DO-NOT-LAND

Branch: `feat/diff-cover-mutmut-adopt` @ `404881d`
Worktree: `/home/stack/code/charon-fleet-DIFF-COVER-FIX`
Reviewer: independent (not the builder). Review is of the branch diff + live execution, not the self-report.

**The fake-green is NOT dead.** I reproduced a green exit from a mutmut that did literally
nothing, and I reproduced a green exit from both gates when the base ref does not resolve
(the exact CI/PR condition). On top of that, the branch introduces an **unbounded recursive
process explosion** that makes the ordinary `pytest` step and `python3 -m charon.cli gate`
never terminate on any branch that has a diff.

The builder's "Executed trial" in `docs/review-log/DIFF-COVER-MUTMUT-ADOPT.md:65-68` states the
gates were validated *"on `master` with no diff"*. That is precisely the one configuration in
which both gates short-circuit and do nothing. The green that was reported is the vacuous path.

---

## Findings

### F1 — CRITICAL — Fake-green #1: unresolvable base ref ⇒ silent exit 0 (both gates)

`tools/diff_cover_gate.py:32-40,59-64` and `tools/mutmut_diff_gate.py:48-55,91-95`

Both gates shell out to `git diff <base>...HEAD` and **never check the git subprocess return
code**. When the ref does not resolve, git writes to stderr, `result.stdout` is empty, the gate
computes 0 changed lines/files, prints `WORK-UNITS: 0`, prints a "skipping" line, and returns 0.

```
$ python3 tools/diff_cover_gate.py origin/nonexistent-branch-xyz
WORK-UNITS: 0
diff-cover-gate: no changed lines in src/ tools/ tests/, skipping
EXIT=0

$ python3 tools/mutmut_diff_gate.py origin/nonexistent-branch-xyz
WORK-UNITS: 0
mutmut-diff-gate: no Python source files changed, skipping
EXIT=0
```

**Concrete failure scenario — this fires on every PR.** `.github/workflows/ci.yml:30` pins
`actions/checkout@v4` with **no `fetch-depth`**, i.e. the default depth-1 shallow fetch. On a
`pull_request` event checkout fetches only the PR merge ref; `refs/remotes/origin/master` is not
created. Both gates default to `base_branch = "origin/master"`
(`tools/diff_cover_gate.py:57`, `tools/mutmut_diff_gate.py:87`) and the CI steps
(`.github/workflows/ci.yml:57,60`) pass no argument. Result: on the pull-request runs these gates
are supposed to guard, both report `WORK-UNITS: 0` and pass green having examined nothing.
This is the identical shape of the fake-green that was reverted before.

Empty discovery must be RED, or at minimum must distinguish "git succeeded and the diff is empty"
from "git failed". It currently cannot.

*Note:* the `git init`/`fetch` needed to build a literal shallow clone is blocked by this
session's git write-op wall, so the CI leg of this scenario is established by reading
`ci.yml:30` (no `fetch-depth`) plus the executed unresolvable-ref reproduction above, not by a
literal shallow-clone run.

### F2 — CRITICAL — Fake-green #2: a no-op mutmut passes the gate

`tools/mutmut_diff_gate.py:132-135, 158-171`

The module docstring (`tools/mutmut_diff_gate.py:16-18`) explicitly claims this is defended:

> *"Empty output alone is NOT proof of pass — a missing/broken mutmut also prints nothing, so we
> additionally verify the run return code and that mutants were actually generated."*

The guard is broken. `mutated` is initialised to `None` (line 132) and only set when the regex
`\((?P<n>\d+)\s+files?\s+mutated` matches `mutmut run` stdout (line 133-135). The check at
line 166 is:

```python
if mutated == 0:
```

`None == 0` is `False`, so when the count line is **absent entirely** — the exact "broken tool"
case the docstring names — the guard is skipped and the gate falls through to
`return 0` at line 171.

**Reproduced by execution.** I put a stub `mutmut` package on `PYTHONPATH` whose `__main__`
does nothing and exits 0 (i.e. mutates nothing, tests nothing, prints nothing):

```
$ PYTHONPATH=<stub> python3 tools/mutmut_diff_gate.py origin/master
WORK-UNITS: 3
mutmut-diff-gate: files_mutated=None run_rc=0 survived=0 statuses={}
mutmut-diff-gate: OK — all mutants in the diff were killed
STUB_MUTMUT_GATE_EXIT=0
```

The gate asserts "all mutants in the diff were killed" having killed zero mutants. Fix is
`if mutated is None or mutated == 0:` — but see F3, the design is also wrong in the same place.

### F3 — HIGH — The pass signal is an absence, never a positive killed count

`tools/mutmut_diff_gate.py:115-120, 137-140`

`mutmut results` (verified in `mutmut/__main__.py:1189-1200`) prints **only non-killed** mutants;
killed mutants are silent. So the gate's GREEN condition is "no bad lines appeared", which is
indistinguishable from "results produced no output at all".

Compounding this, **`results_result.returncode` is never read anywhere in the file** — it is used
only for `.stdout` (lines 137, 151-152). A `mutmut results` that crashes with rc=1 and prints
nothing contributes an empty `status_counts` and is treated as a pass.

Also, `BAD_STATUSES` (`tools/mutmut_diff_gate.py:31`) is a hardcoded string allow-list against
mutmut's human-readable status text. Any status string mutmut adds or renames in a future release
silently becomes "not bad" ⇒ green. mutmut ships `results --all`
(`mutmut/__main__.py:1190`), which would allow asserting a positive `killed >= 1` count instead
of relying on absence. That is the fail-closed shape this gate needs.

### F4 — CRITICAL — Unbounded recursion: `pytest` and `charon gate` never terminate on any branch with a diff

`src/charon/gate_runner.py:55`, `.github/workflows/ci.yml:57`,
`tools/diff_cover_gate.py:86-90`, interacting with pre-existing
`tests/test_gate_contract.py:130-150`.

The pre-existing parametrized test `test_declared_gate_emits_a_count_at_or_above_its_minimum`
runs **every** `tools/`-rooted gate in `gates.json` as a subprocess
(`tests/test_gate_contract.py:139-143`). The new `diff-cover` entry added at
`tools/gates.json:544-556` therefore gets invoked from inside pytest. But
`tools/diff_cover_gate.py:86-90` runs **the whole pytest suite** under coverage:

```
pytest → test_gate_contract → tools/diff_cover_gate.py → coverage run -m pytest
       → test_gate_contract → tools/diff_cover_gate.py → coverage run -m pytest → …
```

On `master` (no diff) the gate short-circuits at `tools/diff_cover_gate.py:62` and the loop never
starts — which is why the builder's master-only trial did not see this. On any branch with a
diff, the loop is unbounded.

**Observed by execution, twice.** Running `python3 tools/diff_cover_gate.py origin/master` in the
worktree:

| elapsed | nested `diff_cover_gate.py` | nested `coverage run … pytest` |
|---|---|---|
| 20 s | 1 | 1 |
| 120 s | 2 | 2 |
| ~300 s | 3 | 3 |

Process tree captured mid-run:

```
1967658 python3 tools/diff_cover_gate.py origin/master
1967660  └─ /usr/bin/python3 -m coverage run --source=src -m pytest -q --tb=short
1994645     └─ /usr/bin/python3 tools/diff_cover_gate.py
1994715        └─ /usr/bin/python3 -m coverage run --source=src -m pytest -q --tb=short
```

I killed it at depth 3; it was still growing and had produced no result. Independently confirmed
from the other entry point — plain
`pytest tests/test_gate_contract.py::test_declared_gate_emits_a_count_at_or_above_its_minimum`
reached depth 2 within 100 s and was still climbing at 140 s.

**Blast radius:** this is not confined to the two new steps. It breaks
`.github/workflows/ci.yml:51` (`pytest -q -n auto`) and `.github/workflows/ci.yml:48`
(`python3 -m charon.cli gate`) — both run pytest, both now recurse. With
`timeout-minutes: 20` (`ci.yml:27`) every PR burns a full 20-minute slot on the **shared
self-hosted 4-LOM runner** and dies by timeout. Every PR in the repo, not just this one. It also
breaks any local `charon gate`. Under `-n auto` the recursion is multiplied across xdist workers.

### F5 — HIGH — `pyproject.toml` (tracked SSOT) is rewritten in place; abnormal exit leaves it corrupted

`tools/mutmut_diff_gate.py:107-123`

The gate writes a modified `pyproject.toml` over the tracked file, runs mutmut, and restores in
`finally`. The comment at lines 120-121 claims *"no window where a crash leaves pyproject.toml
corrupted."* That is only true for exceptions — `finally` does not run on SIGKILL, and does not
run on the default SIGTERM disposition either.

**Reproduced by execution.** With a stub mutmut that sleeps, I SIGKILLed the gate mid-run:

```
$ grep -n only_mutate pyproject.toml
87:only_mutate = ['src/charon/gate_runner.py', 'tools/diff_cover_gate.py', 'tools/mutmut_diff_gate.py']
$ git status --porcelain
 M pyproject.toml
```

`pyproject.toml` was left mangled with an injected `only_mutate` list. (I restored it; final
worktree is clean.)

**Concrete failure scenario:** CI `timeout-minutes: 20` (`ci.yml:27`) kills the job — and given
F4 that timeout is now the *normal* outcome — leaving a mutated `pyproject.toml` in the checkout
on the persistent self-hosted runner. Locally, a Ctrl-C'd or OOM-killed `charon gate` leaves
` M pyproject.toml` dirty, which the `--commit-dirty` landing path will happily sweep onto
master.

This is also avoidable. mutmut 3.6 accepts fnmatch-globbed mutant-name filters as positional
args to `mutmut run` (`mutmut/__main__.py:999-1002`, filtering at `__main__.py:879-885`), which
is a first-class, non-destructive way to scope a run. Rewriting the project's tracked SSOT is a
hand-rolled workaround for a scoping mechanism the adopted tool already provides.

### F6 — HIGH — diff-cover measures only `src/`; every new line in `tools/` and `tests/` is invisible to it

`tools/diff_cover_gate.py:86-90` (`--source=src`) vs `tools/diff_cover_gate.py:32-40`
(work-units counted over `src/ tools/ tests/`).

Coverage is collected with `--source=src`, so the XML contains only `src/` files; diff-cover can
only score lines present in the report. But `_diff_lines()` counts diff lines across
`src/`, `tools/` **and** `tests/`, so the gate reports a large `WORK-UNITS` number while the set
it can actually fail on is a strict subset.

**Verified by execution** — the generated coverage XML's only top-level path component is `src`,
and it contains zero entries for `diff_cover_gate` / `mutmut_diff_gate`.

The self-referential consequence: this branch's own **340 new lines of gate logic in `tools/`**
and **269 new test lines** are entirely unexaminable by the diff-coverage gate it ships. The same
hole applies to `tools/gates.json`-adjacent tooling, `tools/check_*.py`, etc. — a large and
security-relevant part of the repo's guard surface.

The mutation gate has the mirror hole: `_changed_source_files()`
(`tools/mutmut_diff_gate.py:48-55`) filters out only `tests/`, so `tools/*.py` lands in
`only_mutate`, but `source_paths = ["src"]` (`tools/mutmut_diff_gate.py:117`) means
`walk_source_files()` never visits `tools/` and those globs match nothing.

### F7 — HIGH — The mutmut gate cannot currently pass on this repo at all

Executed on the branch as CI would run it:

```
$ python3 tools/mutmut_diff_gate.py origin/master
...
ERROR collecting tests/test_boundary.py
ImportError while importing test module '.../mutants/tests/test_boundary.py'
E   ModuleNotFoundError: No module named 'tools'
failed to collect stats. runner returned 1
mutmut-diff-gate: files_mutated=1 run_rc=1 survived=0 statuses={'not checked': 278}
MUTMUT_GATE_EXIT=1
real 0m2.496s
```

mutmut's `mutants/` sandbox re-roots `sys.path` (`mutmut/__main__.py:254-265`), so the repo's
`from tools.check_boundary import scan_file` imports fail and mutmut aborts stats collection.
278 mutants come back `not checked` and the gate goes RED.

Fail-closed is the right direction here, but the consequence is that this gate is
**permanently RED** on any branch touching `src/` — including this one. As wired, it blocks every
PR, which in practice means the next person weakens it. It needs `also_copy`/`pythonpath`
configuration (mutmut supports both — see `mutmut/configuration.py:125` and the note at
`mutmut/__main__.py:900`) before it can be a required check.

### F8 — MEDIUM — Runtime: the diff-cover gate does not terminate; `.coverage` is not gitignored

- Runtime measured: mutmut gate **2.5 s** (aborts early, F7). diff-cover gate **did not
  terminate** — killed at ~5 min at recursion depth 3, still growing (F4). Even without the
  recursion, the design runs the full suite a **third** time per CI job (after
  `charon gate`'s pytest and the `pytest -n auto` step).
- `.coverage` is **not** in `.gitignore` (grepped: no `coverage` or `mutants` entry). Because
  `_cleanup_coverage_artifacts()` (`tools/diff_cover_gate.py:141-144`) runs only in `finally`,
  every killed run leaves an untracked `.coverage` in the worktree — I observed exactly this
  after killing the recursive run. Same `--commit-dirty` sweep exposure as F5.

### F9 — LOW / NIT — `_STATUS_LINE` matches any `key: value` line

`tools/mutmut_diff_gate.py:34` — `^\s*(?P<key>\S+):\s*(?P<status>.+?)\s*$` matches any colon
line, including banners or future header text, inflating `status_counts`. Harmless today because
only members of `BAD_STATUSES` are acted on, but it is loose parsing on a merge-blocking path.

### F10 — LOW / NIT — `min_work_units: 0` satisfies the anti-vacuity ratchet with prose

`tools/gates.json:553-555, 566-568`. The repo already has a ratchet requiring a written reason
for a declared zero (`tests/test_gate_contract.py:116-127`), added in response to a previously
inert gate. Both new gates declare `min_work_units: 0` with the note *"0 when there is no
diff (trunk check)"* — i.e. the escape hatch is used to legalise exactly the vacuous path F1
exploits. The framework's own warning was answered with a sentence rather than a fix.

---

## Non-findings / things that check out

- **PUBLIC REPO HYGIENE — CLEAN.** Scanned the full branch diff for `/home/stack`, `10.0.1.*`,
  `4-lom`, `charon-private`, `ghp_`, `sk-`, `Bearer`, `ssh -i`, operator name, `/data/`.
  No hits. No dev-machine paths, hostnames, IPs, tokens, or metadata leak.
- **ADOPT, NOT HAND-ROLL — mostly genuine.** Both gates shell out to the real tools:
  `shutil.which("diff-cover")` + `subprocess` (`tools/diff_cover_gate.py:73, 119-128`) and
  `python3 -m mutmut run` / `results` (`tools/mutmut_diff_gate.py:110-119`). No
  reimplementation wearing the tools' names. Declared deps `coverage>=7, diff-cover>=9,
  mutmut>=3.6` (`pyproject.toml:31`) match what is installed and what actually ran:
  **mutmut 3.6.0, diff_cover 10.3.0, coverage 7.14.1** (verified via `pip show`). The mutmut 3.6
  ground-truth comments in the docstring are accurate — I confirmed `source_paths` vs deprecated
  `paths_to_mutate` at `mutmut/configuration.py:99-103`, the `only_mutate` glob validation at
  `configuration.py:112-118`, and the `"(N files mutated"` output string at
  `mutmut/__main__.py:1026`. Two hand-rolled seams remain: the pyproject rewrite (F5, avoidable)
  and the stdout scraping (F3, partly forced but fixable with `results --all`).
- **CI wiring — WIRED, not inert.** `.github/workflows/ci.yml:57-61` (two named steps) and
  `src/charon/gate_runner.py:55-56` (CHECKS list), with matching `ci_step: true` manifest
  entries at `tools/gates.json:544-569`. Registered correctly. The problem is what happens when
  it runs, not whether it runs.
- **The builder's six red-proof tests genuinely pass.** `pytest tests/test_diff_cover_mutmut_gate.py`
  → `6 passed in 20.89s`, exit 0. The two non-vacuity guards
  (`tests/test_diff_cover_mutmut_gate.py:275-280, 358-363`) that require GREEN before asserting
  the post-revert RED are the right pattern and are real. The problem is that the fixtures are toy
  repos that structurally cannot surface F1 (their base ref always resolves), F4 (no
  `test_gate_contract.py` in the fixture), F6 (fixture has no `tools/`), or F7 (fixture has no
  cross-package imports).

---

## Verified by EXECUTION (observed exit codes)

| # | What I ran | Observed | Proves |
|---|---|---|---|
| 1 | `python3 tools/diff_cover_gate.py origin/nonexistent-branch-xyz` | `WORK-UNITS: 0`, "skipping", **exit 0** | F1 |
| 2 | `python3 tools/mutmut_diff_gate.py origin/nonexistent-branch-xyz` | `WORK-UNITS: 0`, "skipping", **exit 0** | F1 |
| 3 | `PYTHONPATH=<no-op mutmut stub> python3 tools/mutmut_diff_gate.py origin/master` | `files_mutated=None run_rc=0 statuses={}` → "OK — all mutants in the diff were killed", **exit 0** | F2 (fake-green alive) |
| 4 | `python3 tools/mutmut_diff_gate.py origin/master` (real mutmut 3.6.0, this branch) | `files_mutated=1 run_rc=1 statuses={'not checked': 278}`, **exit 1**, 2.5 s | F7 (permanently RED), and that the bad-status path does work |
| 5 | `python3 tools/diff_cover_gate.py origin/master` (real, this branch) | **did not terminate**; recursion depth 1→2 by 120 s, →3 by ~300 s; killed by me | F4 |
| 6 | `pytest tests/test_gate_contract.py::test_declared_gate_emits_a_count_at_or_above_its_minimum` | recursion depth 2 by 100 s, still climbing at 140 s; killed by me | F4 from the plain-`pytest` entry point |
| 7 | SIGKILL of the gate mid-`mutmut` (sleeping stub) | `pyproject.toml` left with injected `only_mutate`; `git status` → ` M pyproject.toml` | F5 |
| 8 | `coverage run --source=src …` + `coverage xml`, inspect report | only top-level path component is `src`; 0 entries for the new `tools/` gate scripts | F6 |
| 9 | `pytest tests/test_diff_cover_mutmut_gate.py -q` | `6 passed in 20.89s`, **exit 0** | builder's red-proofs are real (within their fixtures) |
| 10 | `pip show mutmut diff-cover coverage` | mutmut **3.6.0**, diff_cover **10.3.0**, coverage **7.14.1** | declared deps match what runs |
| 11 | `grep -nE '/home/stack\|10\.0\.1\.\|4-lom\|charon-private\|ghp_\|sk-\|Bearer\|ssh -i\|<operator>\|/data/'` over the branch diff | no hits | public-repo hygiene clean |
| 12 | `grep -n 'coverage\|mutants' .gitignore` | no hits | F8 (`.coverage` untracked-but-not-ignored) |

## Verified by READING only

- `.github/workflows/ci.yml:30` uses `actions/checkout@v4` with no `fetch-depth`, hence the
  default depth-1 shallow fetch, hence no `origin/master` on `pull_request` runs. The CI leg of
  F1 rests on this reading plus executed evidence #1/#2; a literal shallow-clone reproduction was
  blocked by this session's git write-op wall.
- mutmut internals cited from installed source: `mutmut/__main__.py:1026` (count string),
  `:254-265` (sandbox `sys.path` re-rooting), `:734-742` + `exit(1)` (early-stop path),
  `:879-885` + `:999-1002` (mutant-name glob filtering), `:1189-1200` (`results` prints only
  non-killed), `mutmut/configuration.py:99-125` (`source_paths` / `only_mutate` / `also_copy`).
- `results_result.returncode` is never referenced (F3) — read from the diff, not separately
  executed.
- Recursion under `pytest -n auto` (xdist worker multiplication) is inferred from #5/#6; I ran
  the serial case only.

---

## What would change my verdict

1. **F4 first** — the recursion makes the whole repo's CI non-terminating; nothing else matters
   until the gate stops invoking a pytest run that re-invokes the gate. (Guard env var, or
   deselect the new gates from `test_gate_contract`'s parametrization, or move diff-cover to
   consume an XML produced by the existing CI test step rather than running its own.)
2. **F1** — check the `git diff` return code; unresolvable base or git error ⇒ non-zero exit.
   Add `fetch-depth: 0` to `ci.yml` and pass the PR base ref explicitly.
3. **F2/F3** — `if mutated is None or mutated == 0:`; check `results_result.returncode`; assert a
   positive killed count via `mutmut results --all` rather than trusting absence.
4. **F5** — scope with `mutmut run <glob>` instead of rewriting `pyproject.toml`, or operate on a
   scratch copy of the tree.
5. **F7** — make mutmut's sandbox able to import the repo before this becomes a required check.
6. **F6** — extend coverage scope to `tools/`, or drop `tools/`/`tests/` from the work-unit count
   so `WORK-UNITS` stops overstating what is checked.

## Worktree state

Left exactly as found. `git -C /home/stack/code/charon-fleet-DIFF-COVER-FIX status --porcelain`
→ `?? .venv-gate/` only (pre-existing untracked). `pyproject.toml` restored bit-for-bit after the
F5 experiment; `git diff HEAD` is empty. All recursive/orphaned processes killed; stray
`.coverage` and `mutants/` artifacts removed. Nothing committed, pushed, or merged.
