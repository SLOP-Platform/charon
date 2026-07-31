# CLASS SCAN — build-rig leaking into the standalone PUBLIC product

Scope: `/home/stack/code/charon` (PUBLIC `SLOP-Platform/charon`) vs rig `/home/stack/charon-private`.
Mode: READ-ONLY. Nothing edited. Date 2026-07-24. `master == origin/master == 6782236`.

Class: *build-rig mechanisms, paths, identifiers or content leaking into the standalone PUBLIC
product — including leaks into the product's local git machinery, not just its tracked files.*

---

## 1. Enumerated instances

| # | Location | Type | Already public? | Severity |
|---|----------|------|-----------------|----------|
| L1 | `/home/stack/code/charon/.git/hooks/pre-commit` → `/home/stack/charon-private-wt/FLEET-DEMAND-BROKER/fleet/hooks/pre-commit` | git-machinery: rig hook installed in product repo, displaces product guard | No (local git state) | **HIGH** |
| L2 | `/home/stack/code/charon/.git/hooks/commit-msg` → same rig worktree | git-machinery: same | No | **HIGH** |
| L3 | `.git/config` remote `gitea` = `http://10.0.1.52:3000/stack/charon.git` | git-machinery: internal IP + internal host in product git config | No (local; surfaces in any pasted `git remote -v`) | MED |
| L4 | `tools/gates.json:63` `"enforcer": "../charon-private/fleet/validate_board.sh"` | tracked-content + build coupling: rig path in product gate registry | **YES — on origin/master** | MED |
| L5 | `tools/gates.json:216` `"enforcer": "../charon-private/fleet/checks/no-unreachable-paths.sh"` | tracked-content + build coupling: same | **YES — on origin/master** | MED |
| L6 | `docs/review-log/DS-PLAN-REVIEW.md:15` — `/home/stack/charon-private/fleet/board/*.md.parked`, `.../OPTIMIZATION-PASS.md` | tracked-content: absolute dev-box path + rig internals in public docs | **YES — on origin/master** | LOW-MED |
| L7 | `README.md:265`, `docs/DECISIONS.md:24`, `docs/adr/0010-...:17`, `docs/review-log/E7.md:20` — `charon-private/fleet/` | tracked-content: rig repo name; deliberate boundary documentation | YES | LOW (legitimate) |
| L8 | `docs/PLAN-tier1.md`, `docs/SUPPLY-CHAIN.md`, `tools/check_boundary.py`, `tests/test_boundary.py` — `slop`/`mediastack` | tracked-content: rig/host-project names — but these ARE the boundary guard's forbidden-token list | YES | LOW (functional, must stay) |
| L9 | `.github/workflows/{ci,heavy,release}.yml`, `.github/actionlint.yaml` — `4-lom` runner label | tracked-content: private host name in public CI | YES | LOW (functional; `CI_RUNNER` var already makes forks fall back to hosted) |
| L10 | `LICENSE:3`, 6× `docs/adr/*` `Deciders: Nnyan`, `pyproject.toml:12` | operator identifier | YES | LOW (deliberate authorship; personal given name "Rafael" already scrubbed and is now a guard pattern) |
| L11 | `docs/review-log/FB5.md:13` 40-hex `actions/upload-artifact` SHA | hex-token shape | YES | NONE (action commit pin, not a secret) |

Not found (clean): no `.gitmodules`; `core.hooksPath` unset in both repos; `.git/info/exclude` carries
only `.claude/` runtime ignores, no rig paths; **zero** hits for `rocinante`/`roci`/`tardis`/`4lom`
(bare)/`gitea` in tracked files; no real hex secrets; no tokens; no `10.0.1.*` outside the guard's own
pattern + its tests; no tracked `.claude/` files; no product code/test/CI reads a rig path at run time.

### Build/run-time coupling (category 3) — verdict: NOT broken on a fresh clone
- L4/L5 are declared `"optional": true, "ci_step": false`. `tools/check_gate_registry.py:176-180`
  prints `SKIP: <id>: optional enforcer ... not present in this checkout` rather than failing.
- Verified by execution: `/home/stack/charon-private/fleet/...` **does not exist** on this box
  (`ls` → No such file), yet `python3 -m charon.cli gate` printed `[gate-registry] OK` and
  `CHARON-GATE: all checks passed`. So the rig absence is tolerated. The leak is *string-level*
  (rig topology published in a public repo), not a fresh-clone build break.

### The displacement, precisely
- `core.hooksPath` unset in the product repo → `.git/hooks/` is the live hook dir.
- The rig planted `pre-commit`/`commit-msg` symlinks there (mtime 2026-07-24 16:30).
- The rig `pre-commit` (227 bytes) does **not** chain to the product guard — `grep` for
  `public_clean|tools/hooks|check_public` in it returns **zero hits**.
- `CONTRIBUTING.md:15` and `tools/hooks/pre-commit:8` both instruct `git config core.hooksPath tools/hooks`
  — which, if the operator ever runs it, would **disable the rig's work-lease hooks**. The two
  mechanisms are mutually exclusive by construction. That is the structural conflict.
- All ~45 linked worktrees (`/home/stack/code/charon-fleet-*`, `/home/stack/charon-wt/*`,
  `.claude/worktrees/agent-*`) share the main repo's common `.git/hooks` — `find .git/worktrees
  -name hooks` → nothing. So one displacement disables the guard for **every** worktree at once.
- Secondary hazard: the symlink target lives inside a *transient rig worktree*
  (`charon-private-wt/FLEET-DEMAND-BROKER`). Removing that worktree leaves a dangling hook and
  breaks every commit in the product repo.

---

## 2. Guard-enforcement findings

### `tools/check_public_clean.py` — **CAN GO RED. Verified by execution.**

Proof-of-RED (planted file, scratchpad):
```
$ python3 tools/check_public_clean.py <scratch>/leak_probe.py
PUBLIC-CLEAN VIOLATION — personal/internal info found:
  ...leak_probe.py:1: internal IP (10.0.0.0/8): host = "10.0.1.60"
  ...leak_probe.py:2: home path "/home/stack": path = "/home/stack/charon-private/fleet/x.sh"
EXIT=1
```
Proof-of-non-vacuous:
```
$ python3 tools/check_public_clean.py
WORK-UNITS: 486
public-clean OK: no personal/internal patterns found in tracked files   EXIT=0
```
- `tools/gates.json:164-167` — `public-clean`, `ci_step: true`, `min_work_units: 100`,
  `red_proof: tests/test_public_clean.py`. Observed 486 ≫ 100.
- Wired: `src/charon/gate_runner.py:41` `(["python3","tools/check_public_clean.py"], "public-clean")`.
  `check_gate_registry.py` fails on any `ci_step:true` enforcer missing from `CHECKS`.
- CI backstop: `.github/workflows/ci.yml:42-43` `run: python3 -m charon.cli gate` and `:55` `pytest -q -n auto`.
  No pipe, no `|| true`. **Executed here**: `charon gate` printed `[public-clean] OK` among 21 checks.
- Prior adversarial findings are now FIXED on master: `_tracked_files()` (`check_public_clean.py:160-181`)
  raises on non-zero rc **and** on empty result — fail-closed, no vacuous pass. The hook uses
  `--staged` and `check_staged_paths` reads `git show :<path>`, so partial staging cannot slip through.
- `tests/test_public_clean.py` → **39 passed**, including `test_tracked_tree_is_public_clean` and
  explicit anti-vacuity tests.
- Exceptions ledger `tools/.public-clean-exceptions.json` is keyed by exact **line content**, and
  `tests/test_public_clean.py:235` fails on stale entries — a waiver cannot silently drift.

### `tools/hooks/pre-commit` — **CORRECT BUT NOT INSTALLED. Proven inert.**
- `core.hooksPath` unset (`git config --get core.hooksPath` → exit 1) and `.git/hooks/pre-commit`
  is the rig symlink. So this hook has **never executed** in this checkout. Its logic is sound
  (`set -euo pipefail`, `exec python3 tools/check_public_clean.py --staged ...`); it is simply unreachable.

### `tools/check_no_rig_import.py` — live, `ci_step:true`, `[no-rig-import] OK` in the executed gate.
Guards only `import benchmark` / `import grader_daemon` inside `src/charon/` — it does **not** cover
rig paths in config or git machinery.

### `tools/leak-guard.sh` — **does not exist.** No such script in the repo.

### Branch `feat/public-clean-enforce` (worktree `.claude/worktrees/agent-ab00727b804e8f8db`)
- **Its enforcement content is already LANDED on master.** `git diff --stat master...feat/public-clean-enforce`
  = one file, `PUBLIC-CLEAN-ENFORCE-ADVERSARIAL.md` (107 lines) — an adversarial-review doc only.
- The branch exists on `origin` at `a18a005`. It is **not** unlanded mechanization; only the review
  write-up is unmerged. Its H1/M1/M2 findings are all resolved on master (see above).

### THE GAP
Every guard above scans **git-tracked files only**. `.git/hooks/*`, `.git/config` and worktree
registrations are untracked by definition, so **no existing guard can see L1/L2/L3 at all**. The
product's public-clean guard was silently displaced and nothing in the repo could report it.

---

## 3. Ranked blast radius

**URGENT**
1. **L1/L2 — displaced pre-commit guard.** Not a leak by itself; it is the *disabled brake*. For an
   unknown window (hooks re-pointed 16:30 today, but `core.hooksPath` was never set, so plausibly
   the product hook was never active at all), every commit across ~45 worktrees on a PUBLIC repo
   went un-scanned at commit time. Only CI stood between a leak and `origin/master`. Fix in flight
   by another sub-session.

**IMPORTANT (already public — no remediation of history requested, reporting only)**
2. **L4/L5 — `../charon-private/fleet/...` enforcer paths in `tools/gates.json` on `origin/master`.**
   Publishes rig topology and the product-vs-rig boundary breach in the product's own config.
   These pass public-clean *only because* they are allowlisted in `.public-clean-exceptions.json`.
3. **L6 — `/home/stack/charon-private/fleet/board/...` absolute dev-box path in
   `docs/review-log/DS-PLAN-REVIEW.md` on `origin/master`.** Also allowlisted.

**HYGIENE**
4. **L3 — `gitea` remote `10.0.1.52:3000` in `.git/config`.** Local only; leaks via pasted terminal
   output, not via the repo.
5. **L7–L11** — deliberate/functional (`4-lom` CI label, `slop`/`mediastack` forbidden-token list,
   authorship, action SHA pins). Leave as-is.

**No secrets, credentials or tokens are public.** Nothing in this scan requires history rewriting.

---

## 4. Root cause + ONE generalization

**Root cause.** The public-clean guard's *unit of protection* is "git-tracked file content". Its
*point of enforcement* is `.git/hooks/pre-commit`. Those are the same object in two roles, and the
guard only ever validates the first. The repo's own git machinery — the thing that decides whether
the guard runs — is outside everything the guard inspects. Worse, the documented install
(`core.hooksPath tools/hooks`, `CONTRIBUTING.md:15`) and the rig's install (symlinks into
`.git/hooks/`) occupy **mutually exclusive** slots: whichever ran last silently wins, with no
receipt either way. So the class recurs the moment any tooling touches hooks, remotes or worktrees.

**Single generalization (extends the EXISTING gate; no new script — anti-accretion respected).**
Extend `tools/check_public_clean.py` with a **git-machinery pass** inside the same enforcer,
counted into the same `WORK-UNITS` and covered by the same `red_proof` (`tests/test_public_clean.py`);
`tools/gates.json` keeps its single `public-clean` row, `gate_runner.CHECKS` keeps its single entry,
CI keeps its single `charon gate` step. The pass asserts three things about the repo's own git state:

1. **Non-displacement (fail-closed).** The effective pre-commit path must reach
   `tools/check_public_clean.py` — satisfied either by `core.hooksPath == tools/hooks`, or by a
   `.git/hooks/pre-commit` whose body invokes the product guard. A foreign hook that does neither is
   a RED naming the offending target. This makes the rig's *correct* move explicit: the rig hook must
   **chain** to `tools/hooks/pre-commit`, not replace it — which also resolves the mutual exclusion.
2. **Same-pattern scan of untracked git machinery.** Run the existing `_PATTERNS` over
   `.git/config`, hook file targets/bodies, and worktree `gitdir` registrations. That single reuse
   catches L3 today and any future rig path, internal IP or host name planted in git state.
3. **Fresh-clone tolerance.** On CI (pristine `.git/hooks`, no extra remotes) the pass is a no-op
   and stays green — so the CI role remains the tracked-content backstop while the *local* `charon
   gate` / pre-commit run becomes the machinery enforcement point, which is exactly where
   displacement happens.

Same guard, same gate row, same CI step, one widened definition of "the public repo". After this,
displacing the guard is itself a public-clean RED.

---

## 5. Verified by EXECUTION vs by READING

**By execution**
- `python3 tools/check_public_clean.py <planted file>` → exit 1 with both violations named (proof-of-RED).
- `python3 tools/check_public_clean.py` → `WORK-UNITS: 486`, exit 0 (proof-of-non-vacuous).
- `python3 -m pytest tests/test_public_clean.py -q` → 39 passed.
- `python3 -m charon.cli gate` → 21 checks, `[public-clean] OK`, `[gate-registry] OK`,
  `[no-rig-import] OK`, `CHARON-GATE: all checks passed`.
- `ls ../charon-private/fleet/validate_board.sh` → absent, yet the gate still passed (optional-skip proven).
- `git config --get core.hooksPath` → exit 1 (unset) — product hook proven inert.
- `ls -la .git/hooks/` → symlink targets read directly.
- `grep public_clean|tools/hooks|check_public <rig pre-commit>` → 0 hits (no chaining).
- `find .git/worktrees -name hooks` → none (worktrees share the displaced hooks).
- `git rev-parse master origin/master` → identical; `git show origin/master:tools/gates.json` →
  rig paths confirmed present in public history.
- `git ls-remote origin feat/public-clean-enforce` → `a18a005` (branch is on origin).
- `git diff --stat master...feat/public-clean-enforce` → 1 doc file only.
- `git grep` sweeps for `/home/stack`, `10.0.1.*`, `4-lom`, `rocinante|roci|tardis`, `charon-private`,
  `mediastack`, `gitea`, `nnyan`, `SLOP`, `fleet/`, 40+-hex, emails.

**By reading only**
- Intent/design commentary in `check_public_clean.py`, `gate_runner.py`, `check_gate_registry.py`.
- The prior adversarial write-up on `feat/public-clean-enforce` (used to confirm H1/M1/M2 are fixed
  on master — the fixes themselves were then re-verified by reading current master source, not re-run).
- The claim that the guard "has never run" in this checkout: inferred from `core.hooksPath` unset +
  current symlinks; hook-installation history was not reconstructed.
