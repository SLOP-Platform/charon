# CLASS SCAN — Enforcement checks outside the meta-gate's discovery scope

**Class:** *Enforcement checks that live OUTSIDE `fleet/checks/gate-creation-standard.sh`'s discovery
scope, and are therefore never audited for red-proof / fail-loud / non-vacuous / actually-executed.*

**Trigger instance:** the tier-drift check added as an INLINE block in `fleet/validate_board.sh`
(commit `0a759a8`, branch `feat/tier-classifier`, **unmerged** — the block is NOT on `master`).

**Scope of scan:** `/home/stack/charon-private` @ `9055478` (master), read-only. Execution evidence
was gathered in a scratch COPY of the tree; the real tree was never modified.

---

## 1. The meta-gate's REAL discovery scope

`fleet/checks/gate-creation-standard.sh` enumerates exactly four node-sets:

| § | Enumerator | Line | Population |
|---|---|---|---|
| A | `$GATES_JSON` = `/home/stack/code/charon/tools/gates.json` | 111–146 | 19 PRODUCT gate registry entries (`id`, `red_proof`) |
| B | `for f in "$CHECKS_DIR"/*.sh "$CHECKS_DIR"/*.py` | **155** | Files **directly** in `fleet/checks/` — 21 today |
| C | `$LEDGER` = `fleet/state/GATE-GAP-LEDGER.tsv` | 188–211 | Ledger rows (floor `LEDGER_MIN=8`) |
| D | `$STANDARD` = `fleet/GATE-CREATION-STANDARD.md` | 214–220 | Literal checklist-item strings in the markdown |

### What is STRUCTURALLY invisible to it

1. **Placement decides membership.** §B is a directory glob. Any enforcement logic that is not a
   file sitting *directly* in `fleet/checks/` is exempt by construction:
   - inline blocks in `fleet/validate_board.sh` (the tier-drift escape),
   - inline `*_gate()` functions in `fleet/preflight.sh` (9 of them),
   - standalone enforcement scripts at `fleet/` top level (28 candidates),
   - `fleet/hooks/*`, `fleet/watchdog/*`, `fleet/gate.sh`, `fleet/land.sh`, `fleet/land-push.sh`,
   - `.github/workflows/*.yml` steps (4 workflows — **never enumerated at all**).
2. **Non-recursive.** `"$CHECKS_DIR"/*.sh` does not descend subdirectories; a future
   `fleet/checks/foo/bar.sh` is exempt (latent, only `__pycache__` there today).
3. **S1 is satisfied by a FILE, not by an EXECUTION.** §B accepts a companion test whose *name*
   normalizes to the check's and which *contains the string* `red-proof|fail-on-revert` (lines
   169–183). It never asks whether any runner executes that test. It cannot: `fleet/gate.sh`
   globs `*.test.sh`, and CI runs a 16-entry literal allowlist in `rig-ci-scope.sh:CI_SUITES` —
   neither is modelled here.
4. **NOT-INERT is grepped, not enforced.** §D only checks that the literal strings `NOT-INERT`,
   `VERIFY-EFFECT`, etc. *appear in the markdown*. The meta-gate never asks whether any audited
   check is actually invoked by a gate / CI / land path.
5. **The meta-gate itself is in the class.** It is invoked by **nothing** — grep across
   `fleet/` + `.github/` finds only its own test as a caller; it self-reports
   `ADVISORY not-wired: validate_board.sh does not yet run this meta-gate's scan`. It is
   currently **RED with 4 findings** that no gate surfaces, and its own red-proof test
   (`fleet/tests/test_gate_creation_standard.sh`) matches neither `gate.sh`'s `*.test.sh` glob
   nor `CI_SUITES` — and currently **FAILS** (`PASS=30 FAIL=1`).

---

## 2. Every enforcement check found OUTSIDE the meta-gate's scope

Legend: **RED?** = is there a reachable failing verdict · **Fail** = OPEN / CLOSED when its own
machinery is broken or missing · **Vac?** = can it pass on zero items examined ·
**Executed?** = is it run by a gate / CI / land path · **Masked?** = failure hidden by
`| head`/`|| true`/missing `pipefail`. `[X]` = verified by EXECUTION.

### 2a. Inline `*_gate()` blocks in `fleet/preflight.sh` (outside `fleet/checks/`)

| # | Check | RED? | Fail | Vac? | Executed? | Masked? |
|---|---|---|---|---|---|---|
| 1 | `board_gate` (preflight.sh:269) | Yes — auto-registers `board-validator-red`, `cmd_scan` exits 1 | **OPEN [X]** — `[ -f "$VALIDATE_BOARD" ] \|\| return 0`; deleting `validate_board.sh` → rc 0, no red | Yes (empty board = GREEN, §2c) | Yes, every preflight `scan` | `cmd_add … >/dev/null 2>&1 \|\| true` — a failed registry append leaves the session GREEN while the gate narrates RED |
| 2 | `executor_gate` (:304) — "fleet work never routes to Anthropic" | Yes | **OPEN [X]** | n/a | Yes | same `\|\| true` mask |
| 3 | `coverage_gate` (:340) — §11 rule-coverage meta-gate | Yes | **OPEN [X]** | n/a | Yes | same |
| 4 | `handoff_gate` (:382) | Yes | **OPEN [X]** | **Yes** — no `HANDOFF-*.md` ⇒ `return 0` "skipped" | Yes | same |
| 5 | `graphify_freshness_gate` (:789) | Yes | **OPEN [X]** | n/a | Yes | same |
| 6 | `done_merge_gate` (:484) | Yes | OPEN — no `state/done/` ⇒ "clean" rc 0 | **Yes** | Yes | `can_verify=0` ⇒ every unproven marker downgraded to one advisory line |
| 7 | `hold_reason_gate` (:543) | Yes | OPEN — missing `gh-cache.sh` ⇒ rc 0; unresolvable slug ⇒ "clean" | **Yes** | Yes | gh unavailable ⇒ advisory, non-blocking |
| 8 | `detect_needs_push` (:429) | Yes | OPEN — no `state/needs-push/` ⇒ "clean" | **Yes** | Yes | `\|\| true` on close |
| 9 | `startup_budget_gate` (:859) | Yes | **CLOSED** — a MISSING budgeted file sets `fail=1` | No | Yes | its `startup_budget_selftest` is a subcommand, in no runner |

Execution proof (scratch copy, machinery deleted, gates sourced and called directly):

```
board_gate                 rc=0  board_gate: validate_board.sh not found at …
executor_gate              rc=0  executor_gate: no-claude-executor.sh not found at …
coverage_gate              rc=0  coverage_gate: rule-coverage.sh not found at …
handoff_gate               rc=0  handoff_gate: handoff-check.sh not found at …
graphify_freshness_gate    rc=0  graphify_freshness_gate: graphify-freshness.sh not found at …
```

This is *exactly* the tier-drift defect #2 ("deleting the script made the check vanish silently
GREEN"), reproduced nine times over in the rig's primary session gate.

### 2b. Runner / verdict engines

| # | Check | RED? | Fail | Vac? | Executed? | Masked? |
|---|---|---|---|---|---|---|
| 10 | `fleet/gate.sh` — the ONLY runner of the 77 `*.test.sh` red-proof suites | Yes (any suite rc≠0) | **OPEN [X]** — missing/empty `TESTS_DIR` ⇒ `tests=()` ⇒ `summary: 0 passed, 0 failed` ⇒ **exit 0** | **Yes [X]** | Only by `handoff.sh` — and **skipped entirely** when `CHARON_GATE_ACTIVE=1`. Not by `land.sh`, `land-push.sh`, or any CI job | shellcheck findings are declared ADVISORY, so lint can never RED |
| 11 | `preflight.sh cmd_scan` (reds.tsv verdict engine) | Yes | **CLOSED** — a broken `check_cmd` returns rc≠0 ⇒ STILL-RED (good) | **Yes [X]** — 0 open rows ⇒ `rc 0`. **No floor/append-only guard on `reds.tsv`**, even though the meta-gate enforces `LEDGER_MIN=8` on its own ledger | Yes | no |
| 12 | `fleet/validate_board.sh` (~20 inline checks; the tier-drift host) | Yes | Mixed: `gate-parity` and `git status` failures ⇒ RED (closed, good); `parallelizability` exception ⇒ WCI advisory (open) | **Yes [X]** — zero `board/*.md` ⇒ `GREEN board structurally valid`, rc 0. No ticket-count floor | Yes (preflight `board_gate`; `land-push.sh` on state-ful checkouts). **Not** in CI (deliberate) | no |

### 2c. INERT enforcement scripts (nothing runs them)

| # | Check | RED? | Fail | Vac? | Executed? | Masked? |
|---|---|---|---|---|---|---|
| 13 | `fleet/stale-check.sh` | Yes — **RED right now [X]**: rc 1, 4 issues incl. a 10,591 s stale claim + 3 loop-guard quarantines | n/a | No | **NO — inert.** Its own output says: *"standalone check — preflight.sh should call this; not wired in here"* | n/a |
| 14 | `fleet/reuse-check.sh` — the "non-negotiable" tool-first / anti-reinvention gate | Yes (rc 2 usage; threshold verdict) | n/a | — | **NO — inert.** Only two references in the whole rig, both PROSE in `session-ctx-preamble.sh`. No gate, no CI, no land path | n/a |
| 15 | `fleet/dark-work-check.sh` | Yes — **RED right now [X]**: rc 1, 3 dark sessions + 9 stranded jobs | **OPEN** — `discover-services.sh:132` `[ -x "$DARK_CHECK" ] \|\| { say SKIPPED; return 0; }` | No | Only via `preflight detect_service_watchdog` → `discover-services.sh --quiet \|\| true` | **Yes — `\|\| true`.** Can never block anything |
| 16 | `fleet/checks/gate-creation-standard.sh` (in §B by location, but **its own auditor of last resort is nobody**) | Yes — **RED right now**, 4 findings | n/a | No | **NO — inert.** Self-declares `not-wired`. Its red-proof test is in neither `gate.sh`'s glob nor `CI_SUITES`, and **currently fails** | n/a |

### 2d. Advisory-by-construction (can never block; not audited)

| # | Check | Executed? | Masked? |
|---|---|---|---|
| 17 | `fleet/access-check.sh` | preflight `cmd_detect` | `\|\| true` |
| 18 | `fleet/cg-drift.sh` | preflight `detect_cg_drift` | `[ -x ] \|\| return 0` + `\|\| true` |
| 19 | `fleet/config-drift.sh` | preflight `detect_config_drift` | `--advisory` forces rc 0; output piped through `grep … \|\| true` |
| 20 | `fleet/project-audit.sh` | preflight `detect_inflight_landscape` | `[ -x ] \|\| return 0`; count-only |
| 21 | `fleet/foreman.sh` (`EXIT_DEFECT` on collisions) | preflight `foreman_advisory` | `\|\| true` — its DEFECT verdict is **discarded**; only echoed as `!! … !!` |
| 22 | `fleet/wci-contention.sh` | preflight `detect_wci_contention` | `2>/dev/null`, advisory |
| 23 | `fleet/checks/parallelizability-gate.sh scan` inside `validate_board.sh:390` | Yes | exception ⇒ WCI advisory, never RED (the HARD leg lives in `fleet-droid.sh`) |

### 2e. Enforcement machinery with NO companion test at all (would be RED under §B if relocated)

`fleet/validate_board.sh`, `fleet/handoff-check.sh`, `fleet/push-verify.sh` (also missing
`set -…uo pipefail` — an S5 FAIL-LOUD violation), `fleet/release.sh`, `fleet/reap-orphans.sh`,
`fleet/lease-enqueue.sh`, `fleet/access-check.sh`, `fleet/cg-drift.sh`, `fleet/dark-work-check.sh`,
`fleet/reuse-check.sh`, `fleet/project-audit.sh`. `fleet/leak-guard.sh` also lacks the S5 set-line
(it is a sourced library, so lower severity).

### 2f. CI workflow steps under `.github/` — never enumerated by the meta-gate

| Workflow | Assessment |
|---|---|
| `bandit.yml`, `gitleaks.yml`, `semgrep.yml` | **Healthy.** Each runs its `fleet/tests/*-canary.test.sh` fail-on-revert canary as a workflow step *before* the scan, pins the tool exactly, and fails CLOSED on a shallow checkout. Not required checks (private repo, free plan ⇒ no branch protection) but `land-push.sh` reads the rollup and fails closed on red/pending/undeterminable. |
| `rig-ci.yml` / `rig-ci-scope.sh` | **Mostly healthy** — `_resolve_scope` fails CLOSED (this class was already fixed here). Residual: `CI_SUITES` is a 16-of-77 literal allowlist, so **61 red-proof suites run in no CI job**; and a check newly added to `fleet/checks/` is excluded from CI by default. |
| Git hooks `fleet/hooks/{pre-commit,commit-msg}` (installed as symlinks in both repos) | Fail CLOSED via `work-lease.sh pre-commit`; `work-lease.test.sh` is in `CI_SUITES`. Bypassable with `--no-verify` (known). Not audited by the meta-gate. |

---

## 3. Ranked by blast radius

| Rank | Instance | Why it ranks here |
|---|---|---|
| **1** | **`fleet/gate.sh` vacuous + near-inert** (#10) | It is the ONLY executor of the rig's 77 red-proof suites — work-lease double-claim, land-safety wrong-commit, leak-guard work-loss, needs-push. It runs only inside `handoff.sh`, is skipped under the reentrancy guard, and returns **exit 0 on zero tests [X]**. If `TESTS_DIR` resolution ever breaks, every red-proof in the rig silently stops proving anything and every gate reads green. Claim-and-launch + push path. |
| **2** | **Nine preflight `*_gate()` fail-OPEN [X]** (#1–8) | Deleting one check script silently GREENs the session gate. Covers the money/routing path (`executor_gate` = never burn Claude tokens), the claim-and-launch path (`board_gate`), and done-marker honesty (`done_merge_gate`). Same defect as the tier-drift finding, ×9. |
| **3** | **The meta-gate is inert AND currently RED** (#16) | 4 unsurfaced findings, incl. `reachability-gate` shipped with **no `red_proof`** into the product registry, and `large-file-guard.sh` / `rig-ci-scope.sh` with no companion test. Its own red-proof test runs nowhere and currently FAILS. The policeman of this class is in the class. |
| **4** | **`stale-check.sh` inert while RED [X]** (#13) | Claim-and-launch path: a 10,591 s stale claim + 3 loop-guard quarantines are live and invisible. Self-documents that it is unwired. |
| **5** | **`dark-work-check.sh` RED behind `\|\| true` [X]** (#15) | 3 dark sessions + 9 stranded jobs = work-loss class; reachable only through an advisory watchdog leg that also fails OPEN if the script is absent. |
| **6** | **`reuse-check.sh` inert** (#14) | The SESSION-CTX preamble calls it "non-negotiable"; it is enforced by prose alone. Directly enables the reinvention/accretion class this rig keeps paying for. |
| **7** | **`validate_board.sh` unaudited + vacuous [X]** (#12) | The tier-drift host itself. 444 lines, ~20 inline checks, no companion test under the meta-gate's own matcher, GREEN on an empty board. Gates launch and (state-fully) land. |
| **8** | **`cmd_scan` vacuous on an emptied `reds.tsv` [X]** (#11) | The rig's blocking verdict engine has no append-only floor, while the meta-gate enforces exactly such a floor on its own ledger. Truncate the registry ⇒ preflight GREEN. |
| **9** | **`handoff-check.sh` / `push-verify.sh` untested; `push-verify.sh` lacks `set -uo pipefail`** (#2e) | Push-proof and handoff-quality machinery on the sanctioned push path, with zero red-proof. |
| **10** | **`foreman.sh` DEFECT verdict discarded by `\|\| true`** (#21) | Collision detection reduced to a printed banner. |
| **11** | Cosmetic/report-only advisories (#17–20, #22–23) | Report-only by design; low blast radius. |

---

## 4. Root cause + the ONE generalization

### Root cause

**The meta-gate's population is DIRECTORY-SHAPED, not ROLE-SHAPED.**
`gate-creation-standard.sh:155` decides "is this a gate I must audit?" by asking *where the file
lives* (`"$CHECKS_DIR"/*.sh|*.py`). Membership is therefore an author's free choice: put the
enforcement anywhere else — inline in `validate_board.sh`, a function in `preflight.sh`, a
top-level `fleet/*.sh`, a CI step — and it is exempt with no override, no exemption record, and
no signal. The escape is not a bug in a rule; it is the *addressing scheme* of the rule.

A second, compounding cause: **S1 is proven by a FILE, not by an EXECUTION.** §B accepts a
companion test that merely exists and contains the string `red-proof`. Nothing links that file to
`gate.sh`'s `*.test.sh` glob or `rig-ci-scope.sh:CI_SUITES`, so a red-proof can be dead on arrival
(and the meta-gate's own is).

### The single generalization (anti-accretion compliant — no new script)

**Change `fleet/checks/gate-creation-standard.sh` §B from a directory glob to an
invocation-derived node-set, and add one execution assertion. One file changed; no new tool.**

Replace the enumerator at line 155:

1. **Enumerate by CALL SITE, not by directory.** Build the audited set as the union of
   (a) today's `"$CHECKS_DIR"/*.sh|*.py`, and (b) every script path *invoked* by the rig's
   enforcement entrypoints — `fleet/preflight.sh`, `fleet/gate.sh`, `fleet/land.sh`,
   `fleet/land-push.sh`, `fleet/validate_board.sh`, `fleet/foreman.sh`, `fleet/hooks/*`,
   `fleet/watchdog/*.sh`, `.github/workflows/*.yml`. That single change makes the tier-drift
   escape impossible: an inline block in `validate_board.sh` puts `validate_board.sh` itself into
   the audited set, and a new `fleet/*.sh` check becomes auditable the moment anything calls it.
   Anything invoked but not in the set ⇒ RED under the existing S3 UN-GAMED machinery
   (`BASELINE_CHECKS` + `check-removed`), reusing `in_list`/`norm` verbatim.

2. **Make "the red-proof must RUN" an S1 sub-assertion.** Inside the same loop, after the
   companion-test match, additionally require that the companion be reachable by a real runner:
   it must match `gate.sh`'s `*.test.sh` glob **or** appear in `rig-ci-scope.sh:CI_SUITES`.
   Otherwise ⇒ `red "unrun-red-proof: …(S1/NOT-INERT — a proof no runner executes is not evidence)"`.
   This closes the tier-drift defect "its tests were run by no gate, no CI job and no land path"
   for the whole population at once, and it immediately reds the meta-gate's own
   `test_gate_creation_standard.sh`.

3. **Prerequisite fix, not accretion:** wire `gate-creation-standard.sh` into `preflight.sh`'s
   existing gate chain using the *identical* `_*_red_ensure_open` machinery the other eight gates
   already use — but with the `[ -f … ] || return 0` fail-open replaced by fail-CLOSED
   (a missing meta-gate must be RED). The file already narrates its own `not-wired` ADVISORY, so
   this is completing an unfinished wiring, and it makes the ANTI-ACCRETION story hold: one lens,
   generalized, actually running.

**Explicitly rejected (forbidden by the anti-accretion rule):** a new `fleet/checks/inline-gate-audit.sh`,
a per-instance `tier-drift` checker, or a separate "is-it-wired" script. All three would re-create
the class one directory over.

**Note on the fail-open pattern (#1–8):** the correct remediation is likewise a *generalization*,
not nine edits — one shared helper already implied by the identical `_*_red_ensure_open` /
`_*_red_close_if_open` triplets in `preflight.sh`: replace the nine copies of
`[ -f "$CHECK" ] || { echo "…not found…"; return 0; }` with a single `_gate_run <red_id> <script> …`
that treats *missing machinery as RED*. Same lens, generalized; no new file.

---

## 5. Verified by EXECUTION vs verified by READING

### Verified by EXECUTION (scratch copy at `…/scratchpad/rigcopy`; real tree untouched)

| Claim | Evidence |
|---|---|
| Meta-gate is currently RED with 4 findings | `bash fleet/checks/gate-creation-standard.sh check` → 4 REDs incl. `unproofed-gate: 'reachability-gate'` |
| Meta-gate self-reports `not-wired` | same run, ADVISORY line |
| Meta-gate's own red-proof test currently FAILS | `bash fleet/tests/test_gate_creation_standard.sh` → `PASS=30 FAIL=1` |
| That test is in neither runner | `shopt -s nullglob; fleet/tests/*.test.sh` → 77 suites, `gate_creation` count = 0; not in `rig-ci-scope.sh suites` |
| `gate.sh` passes vacuously | `FLEET_TESTS_DIR=<empty>` and `FLEET_TESTS_DIR=<nonexistent>` → `summary: 0 passed, 0 failed`, rc 0 |
| 5 preflight gates fail OPEN | deleted `validate_board.sh`, `checks/no-claude-executor.sh`, `checks/rule-coverage.sh`, `checks/graphify-freshness.sh`, `handoff-check.sh` in the copy; sourced `preflight.sh`; all five returned rc 0 with a "not found" line and registered no red |
| `cmd_scan` passes vacuously | truncated `reds.tsv` to its header in the copy → `--- 0 open: 0 STILL-RED … ---`, rc 0 |
| `validate_board.sh` passes vacuously | empty `board/` fixture → `GREEN board structurally valid`, rc 0 |
| `stale-check.sh` is RED now | `bash fleet/stale-check.sh` → rc 1, 4 issues, self-declared unwired |
| `dark-work-check.sh` is RED now | `bash fleet/dark-work-check.sh` → rc 1 (3 dark sessions, 9 stranded jobs) |
| `reuse-check.sh` behaviour | `bash fleet/reuse-check.sh` → usage, rc 2 |
| `access-check.sh` behaviour | rc 0, advisory banner |
| Product gate registry contents | `python3 … tools/gates.json` → 19 entries; `reachability-gate` has `red_proof = None` |
| CI allowlist size | `bash fleet/checks/rig-ci-scope.sh suites` → 16 entries vs 77 `*.test.sh` |
| Git hooks installed | `ls .git/hooks` in both repos → `pre-commit`/`commit-msg` symlinks into `fleet/hooks/` |

### Verified by READING only

- The four workflow files' fail-closed/canary structure (`bandit.yml`, `gitleaks.yml`,
  `semgrep.yml`, `rig-ci.yml`) — not executed here (they require the GitHub runner).
- `land.sh` / `land-push.sh` gate assembly and their `|| true` sites.
- `done_merge_gate`, `hold_reason_gate`, `detect_needs_push`, `startup_budget_gate` fail/vacuous
  behaviour (read from source; the same `[ -f ] || return 0` idiom as the five executed).
- `foreman.sh` DEFECT verdict being discarded by `foreman_advisory`'s `|| true`.
- `discover-services.sh:132` dark-leg fail-open guard.
- The absence of companion tests for the §2e list (derived by re-implementing the meta-gate's own
  `norm()` matcher and cross-checking against its live output — the reimplementation reproduced the
  real run's findings exactly, so the derivation is trustworthy, but the individual absences were
  not each executed).
- `tier-drift` block itself: read from `git show 0a759a89` (branch `feat/tier-classifier`,
  unmerged); it is NOT present on `master`, so it was not re-executed.
