# AUDIT — tests and checks that NO RUNNER EXECUTES

Read-only inventory. Scope: rig `/home/stack/charon-private` @ `master`, product
`/home/stack/code/charon` @ `master`. Nothing renamed, moved, or fixed.

Thesis under test: *a test no runner executes is not evidence — it is decoration that reads
as safety.* The seed instances (5, found 2026-07-24) were not a coincidence; they are one
class with a measurable population.

**Headline:** **33 test-like files in the rig are executed by NO runner** — proven by
collection-rule mismatch, not inferred. **1 product gate (`reachability-gate`) has never run
and cannot run: its enforcer does not exist on disk in either repo.** 6 of the 33 guard
data-loss / claim-and-launch / gate surfaces.

---

## 1. RUNNER COLLECTION RULES (quoted, verbatim)

Every mechanism in either repo that actually *executes* a test.

### R1 — `fleet/gate.sh` (rig, the fleet suite)

```bash
TESTS_DIR="${FLEET_TESTS_DIR:-$FLEET/tests}"
shopt -s nullglob
tests=("$TESTS_DIR"/*.test.sh)      # gate.sh:33
shopt -u nullglob
```
Collects: `fleet/tests/*.test.sh` **only**. Suffix glob — `test_foo.sh` and `test_foo.py`
match nothing. Today: **77 files collected**.

**Who invokes R1:** `fleet/handoff.sh:355` — and nothing else.
`fleet/land.sh:290-301`'s auto-detect ladder picks `bash $REPO/fleet/validate_board.sh` for the
rig (the `-f "$REPO/fleet/validate_board.sh"` branch), *not* `gate.sh`. So R1 fires at
handoff time only; it is not on the land path and not in CI.

### R2 — `fleet/checks/rig-ci-scope.sh:CI_SUITES` (rig CI, `.github/workflows/rig-ci.yml`)

```bash
# ---- CI TEST ALLOWLIST (ALLOWLIST, NOT AN EXCLUDE-LIST) ---------------------
# ... CI therefore names its suites LITERALLY: anything added to fleet/tests/ later is
# excluded BY DEFAULT ... NEVER replace this with a `for t in fleet/tests/*.test.sh` sweep.
CI_SUITES=( priority-validator.test.sh rig-ci.test.sh work-lease.test.sh
  substrate-first-gate.test.sh rule-coverage.test.sh base-integrity.test.sh
  board-correctness.test.sh parked-semantics.test.sh log-prune.test.sh
  land-push-ci-gate.test.sh land-safety.test.sh sync-checkouts.test.sh
  stranded-work.test.sh flow-canary.test.sh )
```
Executed by `cmd_tests`: `bash "$ROOT/fleet/tests/$s"`. **14 literal names.** Deliberate
allowlist — correctly reasoned (grader suites can block for hours), but it means R2 covers
14/77 = 18% of the R1 population and 0% of anything R1 misses.

### R3 — `.github/workflows/gitleaks.yml:77`, `semgrep.yml:69` (rig)
`run: bash fleet/tests/gitleaks-canary.test.sh` / `semgrep-canary.test.sh`. Two files, named
literally. (`bandit.yml` runs the check, not the canary.)

### R4 — product pytest (`pyproject.toml`)
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = [".", "src"]
```
Collects `tests/**` under pytest's default `python_files = test_*.py`. **148 files.**
Invoked by `.github/workflows/ci.yml` (`pytest -q -n auto`) and by
`gate_runner.CHECKS` (`["python3","-m","pytest","-q"]`).

### R5 — product `charon gate` → `src/charon/gate_runner.py:CHECKS`
A hardcoded 22-entry list of argv tuples (ruff, mypy, `tools/check_*.py` ×15, pytest,
render_review_log, check_decisions). `_verify_gate_registry_wired` asserts one direction only:
*every `ci_step:true` enforcer in `gates.json` must be wired into `CHECKS`*. There is no
converse assertion, and no assertion that a gate with `ci_step:false` runs anywhere at all.

### R6 — product `tools/check_redproof.py` → `tools/_vendor/ksf_gates/redproof.py`
```python
proofs_dir = repo_root / ".ksf" / "gates"
rp_test = proofs_dir / f"test_redproof_{gate_name}.py"
if not rp_test.exists(): gaps.append("never-gone-red")
rc = _run_pytest(rp_test)     # the red-proof must itself PASS
```
This is the ONLY runner for `.ksf/gates/test_redproof_*.py` (they are outside
`testpaths=["tests"]`, so R4 never sees them). It IS wired: `CHECKS` → `charon gate` →
`ci.yml`. **These 5 files are fine** — reported here only because the naive glob would
mis-flag them.

### R7 — `fleet/benchmark/selftest/run_selftests.py`
Grader discrimination self-tests. Its `CASES` list names **grader scripts and golden fixture
dirs**; it does not import, collect, or subprocess any sibling `selftest/test_*.py`. It is
itself invoked by nothing — its own docstring says `Usage: python3 selftest/run_selftests.py`.

### NOT runners (checked and excluded)
`fleet/preflight.sh` (references tests only in comments), `fleet/checks/selfcheck-cycle.sh`
(builds a *call graph* over `*.test.sh` — same suffix assumption, so orphans are invisible to
the fork-bomb analysis too), `fleet/validate_board.sh`, `Makefile`, `heavy.yml`, `release.yml`,
`windows-exe.yml`. The rig has **no** `pytest.ini` / `pyproject.toml` / `tox.ini` — so every
`python3 -m pytest fleet/...` line in a rig file is a comment telling a human what to type.

---

## 2. BUCKET (a) — NEVER RUN. Proven non-collection.

Proof method for every row: the file's basename is checked against **every** rule in §1, and
the whole repo is grepped for the basename in an executable position (`bash X`, `pytest X`,
`python3 X`, workflow `run:`). All 33 rows returned **zero executable references** — the only
hits are the file's own `# Run: ...` header comment and prose in `.md`.

### 2a — `fleet/tests/test_*` (16 files) — inside the runner's own directory, invisible to its glob

`gate.sh:33` globs `*.test.sh` (suffix). These use the pytest-style `test_*` **prefix**. They
sit in `fleet/tests/`, next to 77 files that do run, which is exactly why this reads as safe.

| File | Why not collected | What it guards | Blast radius |
|---|---|---|---|
| `test_land_safe_sync.sh` | prefix≠`*.test.sh`; not in CI_SUITES | "land.sh's step-7 base sync must NEVER destroy uncommitted or unpushed work" | **CRITICAL — data loss.** The only proof of a HARD invariant on the land path every droid uses. |
| `test_droid_reap.sh` | same | `reap-orphans.sh` + `leak-guard.sh` P0#4 **branch preservation** | **CRITICAL — data loss.** Reaper deleting a live droid's branch is unguarded. |
| `test_detention.sh` | same | DETENTION-REDLINE: scorecard→assignment guardrail in `model-detention.sh` **and `fleet-droid.sh`** | **HIGH — claim-and-launch + routing.** Redline mis-computation silently re-admits a detained model. |
| `test_gate_creation_standard.sh` | same | the rig **META-GATE** `fleet/checks/gate-creation-standard.sh` | **HIGH — gate surface.** See §2d: currently *failing*, and the gate it proves is itself invoked by nothing. |
| `test_wci_strict.sh` | same (renamed on an unlanded branch) | `wci-contention.sh --strict` HARD gate | **HIGH — gate surface.** 5 assertions that had never executed. |
| `test_claim_decompose_perf.sh` | same | `claim.sh` + `decompose.sh` fast **and behavior-preserving** | **HIGH — claim-and-launch.** Guards double-claim-adjacent behavior. |
| `test_github_limits.sh` | same | GITHUB-LIMITS-HARDENING / `gh-cache` (zero-gh-call contract in `done.sh`) | MED-HIGH — rate-limit exhaustion strands every session. |
| `test_auto_append.py` | prefix AND `.py`: no rig pytest config exists | `fleet/capability/auto_append.py` scorecard append validation | MED-HIGH — corrupt ledger rows feed `assign()` routing. |
| `test_capture_pipeline.py` | same | grader-daemon capture handler + ledger discrepancy computation | MED-HIGH — grading/ledger integrity. |
| `test_preflight_runner.sh` | prefix | `fleet/benchmark/preflight.sh` (MODEL-PREFLIGHT runner) | MED — preflight admission decisions. |
| `test_dec_driver.sh` | prefix | `fleet/decompose.sh` | MED — work composition. |
| `test_decompose_e2e.sh` | prefix | full decomposer → disjoint-wave pipeline | MED — work composition. |
| `test_foreman_wire.sh` | prefix | `preflight.sh scan` actually runs `foreman.sh` | MED — a wiring proof, i.e. the anti-inert check, itself inert. |
| `test_foreman_triggers.sh` | prefix | all 4 foreman-cadence triggers surface STARVE | MED. |
| `test_graphify_freshness.sh` | prefix | `fleet/checks/graphify-freshness.sh` 5 contracts | LOW-MED — gate surface, advisory. |
| `test_add_provider.sh` | prefix | `fleet/add-provider.sh` `--dry-run` contract | LOW-MED — provider onboarding → gateway config. |

### 2b — `fleet/benchmark/selftest/` (15 files) — no runner exists for this directory at all

R7 does not collect them; nothing else references them. Every one is a self-declared
FAIL-ON-REVERT proof.

| File | What it guards | Blast radius |
|---|---|---|
| `test_real_shell_injection.py` | reds-replay grader runs a `check_cmd` template over **untrusted** input | **CRITICAL — security.** A shell-injection proof that has never executed. |
| `test_grader_daemon.py` | grader-daemon OOB **trust-boundary** invariants (incl. path-traversal rejection, `test_F1_path_traversal_rejected`) | **CRITICAL — security.** Also the only file dual-mode (`pytest` OR script) — and neither mode is wired. |
| `test_reachability_paths.py` | grader-daemon must not hardcode a dev-box `FLEET_DIR` | **HIGH.** This is the red-proof for the product's `reachability-gate` (§2c) — *both ends are dead*. |
| `test_preflight_graders.py` | the LOAD-BEARING MODEL-PREFLIGHT graders | HIGH — admission/promotion decisions. |
| `test_stage_demux.py` | phase/trust demux in grader-daemon | HIGH — trust boundary. |
| `test_quality_gate_selftest.py` | test-quality-gate against frozen real captures | MED-HIGH — grading validity. |
| `test_preflight_dispatch.py` | PREFLIGHT-CHUNK0 dispatch seam | MED. |
| `test_dogfood_attribution.sh` | dogfood failure-attribution classifier | MED — `[[monitored-preflight-failure-attribution]]`. |
| `test_grader_env.sh` | Chunk-D grader env control panel | MED. |
| `test_grep_code_only.sh` | `lib/grep-code-only.sh` | LOW-MED. |
| `run_selftests.py` | grader discrimination (**"the most important deliverable of the benchmark harness"**, its own words) | **HIGH — the ledger's validity.** Manual-only: `Usage: python3 selftest/run_selftests.py`. |
| `run_isolation_selftest.py` | sandbox isolation | HIGH — security. Manual-only. |
| `efficiency_selftest.py` | efficiency scoring | MED. Manual-only. |
| `session_cost_selftest.py` | session cost accounting | **MED-HIGH — money path.** Manual-only. |
| `token_capture_selftest.py` | token capture | **MED-HIGH — money path.** Manual-only. |

### 2c — `fleet/capability/` (2 files)

| File | Why not collected | What it guards | Blast radius |
|---|---|---|---|
| `capability/selftest.py` | no runner; header says PROOF-OF-EFFECT gate | `assign()` proof-of-effect — the anti-inert check for the router's own assignment | **HIGH — routing.** The anti-inert gate is inert. |
| `capability/tests/test_tsv_append_unify.py` | outside `fleet/tests/`; rig has no pytest config | TSV-APPEND-UNIFY: one validate+append implementation for `model-scorecard.tsv` | **HIGH — the ledger.** `[[scorecard-live-lane-is-the-ledger]]`: the scorecard IS the ledger. |

### 2d — the product gate that cannot run at all

`tools/gates.json` registers:
```json
{"id":"reachability-gate","optional":true,"domain":"reachability",
 "enforcer":"../charon-private/fleet/checks/no-unreachable-paths.sh",
 "ci_step":false,"red_proof":null}
```
`fleet/checks/no-unreachable-paths.sh` **does not exist** in either repo. Verified live:
```
$ python3 tools/check_gate_registry.py
SKIP: reachability-gate: optional enforcer '.../no-unreachable-paths.sh' not present in this checkout
check_gate_registry: OK   (rc=0)
```
So the registry reports domain `reachability` as *covered* (it appears in the 19-domain
coverage summary), `ci_step:false` keeps it out of `CHECKS`, `optional:true` downgrades a
missing enforcer to a SKIP, and `red_proof:null` means nothing proves it ever went red. Its
would-be red-proof (`test_reachability_paths.py`, §2b) is also unreachable. **A registry row
standing in for a gate that has never existed.** This is the worst single instance in the
audit because it is the *only* one that produces an affirmative green receipt.

### 2e — the meta-gate itself (context for §6)

`fleet/checks/gate-creation-standard.sh` is invoked by **nothing** (grep across `fleet/` +
`.github/`: only its own never-run test names it). It self-reports the fact and is RED today
with findings no runner surfaces:
```
$ bash fleet/checks/gate-creation-standard.sh scan
GATE-STANDARD-ADVISORY: not-wired: validate_board.sh does not yet run this meta-gate's scan
GATE-STANDARD-ADVISORY: unproofed-gate: 'reachability-gate' has no red_proof
GATE-STANDARD-ADVISORY: no-red-proof-test: large-file-guard.sh has no companion test
GATE-STANDARD-ADVISORY: no-red-proof-test: rig-ci-scope.sh has no companion test
== GATE-STANDARD scan: 4 finding(s) (advisory — always exit 0) ==
```
Note the *third* naming-glob escape hiding here: `rig-ci-scope.sh` **does** have a companion
(`rig-ci.test.sh`, in CI_SUITES, described there as "this gate's own fail-on-revert tests"),
but the meta-gate's basename normalization (`s="${s%.test.sh}"`) maps it to `rig-ci` ≠
`rig-ci-scope`, so it reports a false gap. Same root mechanism, opposite sign.

---

## 3. BUCKET (b) — ran once, not lately. **Weaker evidence — stated as such.**

There is **no run-history artifact** in either repo: `fleet/state/` holds no gate/test result
cache, and rig CI is ~5 days old. Everything below is inference from collection topology and
`git log`, not from an observed last-run timestamp. Treat as *suspicion*, not proof.

**(b1) The 63 `.test.sh` files outside `CI_SUITES`.** Their only runner is R1, and R1 fires
only from `handoff.sh:355`. They therefore run when an operator ends a session with
`handoff.sh` and at no other time — not on `land.sh`, not on any PR. A branch can be built,
gated, landed and pushed without any of the 63 executing. Confidence: **high on the
topology**, unknown on actual frequency.

**(b2) Test-vs-subject drift** (test file older than the script it names, among the 63):

| Test (last touched) | Subject (last touched) | Note |
|---|---|---|
| `gate.test.sh` (07-10) | `gate.sh` (07-15) | The runner's own test predates the 07-15 fork-bomb reentrancy rewrite. **And it cannot ever catch this audit's class:** its fixtures are literally `alpha.test.sh`/`bravo.test.sh` — it bakes in the very naming assumption under investigation. |
| `reconcile-merged.test.sh` (07-15) | `reconcile-merged.sh` (07-22) | 7 days of subject change unexercised in CI. |
| `leg-preflight.test.sh` (07-14) | `leg-preflight.sh` (07-15) | |
| `claim-jedi-name.test.sh` (07-23) | `claim-jedi-name.sh` (07-24) | claim-and-launch path. |
| `foreman.test.sh` (07-19) | `foreman.sh` (07-19) | same-day, low signal. |

**(b3) Bucket-(a) files by age** — the ones written long ago and never once executed are the
worst of the never-run set, because the code beneath them has moved for two weeks with zero
coverage: `test_add_provider.sh`, `test_dec_driver.sh`, `test_decompose_e2e.sh`,
`test_detention.sh`, `test_land_safe_sync.sh`, `test_preflight_runner.sh`, `test_wci_strict.sh`
(all 2026-07-12), `test_auto_append.py` (07-11).

---

## 4. COLLECTED BUT SKIPPED / VACUOUS

### 4a — Product: skips that hide real gaps

| Location | Mechanism | Verdict |
|---|---|---|
| `tests/test_provider_presets.py:156-163` | `pytest.skip("<name>: preset not yet in providers.PRESETS (FT-CATALOG-SEED PR #135 not yet merged)")` | **VACUOUS — confirmed live.** `github_models`, `featherless`, `ollama_cloud` are all absent from `providers.PRESETS` (26 presets, none of the three). Written 2026-07-15; **PR #135 is still `open`, unmerged**. Three tests that have asserted nothing for 9 days, reported as passes. |
| `tests/test_provider_response_contract.py:180,195` | `pytest.mark.xfail(..., strict=False)` on every native-wire preset **and** on `cline` | Non-strict xfail: a preset whose adapter starts working XPASSes and never fails, so the contract can silently become stale in either direction. Reason strings are linked and specific (Phase-2 / RESPONSE-ADAPTER-UNIVERSAL) — the justification exists; the `strict=False` does not. |
| `tests/test_land_secret_allowlist.py:17` | module-level `skipif(not shutil.which("gitleaks"))` | **Security path.** Whole module vanishes where gitleaks is absent, with no floor assertion that it ran somewhere. |
| `tests/test_gate_runner_fail_closed.py:94` | `pytest.skip("filesystem permissions not enforced for this user")` | The **fail-closed gate's own proof** skips when run as root/in a container that ignores mode bits. |
| `tests/test_scanners.py:550,563` | `skipif(ruff --version != 0)` | Justified; low risk (CI installs ruff). |
| 7 files, 22 sites | `pytest.importorskip("litellm"/"fastapi"/"httpx")` — `test_gw_bridge2_metering`, `..3_streaming`, `..4_park_cooldown`, `test_litellm_router_e2e`, `..._downgrade_guard_e2e`, `test_litellm_router_adopt`, `test_service_api/ui` | **Money path.** `ci.yml` installs `.[dev,service,router]` explicitly so these RUN in CI — the header comment says exactly why. But **locally** (`charon gate`, `land.sh`) they skip silently, so a money-path regression is invisible until the PR opens. Not vacuous in CI; vacuous on the developer's gate. |

### 4b — Rig: no skip-to-green found (good)

The three security canaries fail LOUD rather than fake a pass — `semgrep-canary.test.sh:28`,
`gitleaks-canary.test.sh:28`, `bandit-canary.test.sh:30` all `exit 2` with
*"REFUSING to fake a green"* when the engine is missing. This is the correct pattern and the
product's `importorskip`/`skipif` sites should be measured against it.

### 4c — Vacuous by construction

Every file in §2 is *maximally* vacuous: zero items examined, zero assertions evaluated, and
no output at all — they do not even produce a skip line for a human to notice. This is
strictly worse than a `SKIPPED` marker, which at least appears in the report.

---

## 5. RANKED BLAST RADIUS

| # | Item | Surface | Why it ranks here |
|---|---|---|---|
| 1 | **`reachability-gate`** (product `gates.json`) | gate / registry | The only item that emits an affirmative green. Enforcer file does not exist; `optional:true` turns "missing" into SKIP; `red_proof:null`; its red-proof (`test_reachability_paths.py`) is itself never run. Registry says domain covered. **Pure false receipt.** |
| 2 | `test_land_safe_sync.sh` | data loss / land path | Sole proof that `land.sh` step-7 never destroys uncommitted work. Every droid lands through it. |
| 3 | `test_droid_reap.sh` | data loss | Sole proof of branch preservation in the reaper + leak-guard. |
| 4 | `test_real_shell_injection.py`, `test_grader_daemon.py` | **security** | Shell-injection and path-traversal proofs on the OOB grader trust boundary. Never executed once. |
| 5 | `test_gate_creation_standard.sh` + `gate-creation-standard.sh` | gate | The meta-gate is invoked by nothing, is RED with 4 unsurfaced findings, and its red-proof both fails to run *and* (per the prior scan) fails when run. The auditor is unaudited. |
| 6 | `test_detention.sh`, `test_claim_decompose_perf.sh`, `capability/selftest.py` | claim-and-launch / routing | Detention redline feeds `fleet-droid.sh` assignment; `assign()`'s own proof-of-effect gate is inert. |
| 7 | `capability/tests/test_tsv_append_unify.py`, `test_auto_append.py`, `session_cost_selftest.py`, `token_capture_selftest.py` | **money / ledger** | The scorecard IS the ledger; append-validation and cost/token capture proofs all unwired. |
| 8 | `run_selftests.py`, `run_isolation_selftest.py`, `test_preflight_graders.py` | grading validity | The harness's self-declared "most important deliverable" is manual-only. |
| 9 | `test_provider_presets.py` ×3 | routing config | Vacuous-but-reported-green for 9 days on an unmerged PR. |
| 10 | The other 14 bucket-(a) files | composition / advisory | Real but bounded. |

**Plainly: 6 never-run tests protect something that matters a lot** — two data-loss
invariants (`land_safe_sync`, `droid_reap`), two security trust-boundary proofs
(`real_shell_injection`, `grader_daemon`), one gate meta-surface (`gate_creation_standard`),
one claim-and-launch guardrail (`detention`) — **plus** the one registry row
(`reachability-gate`) that is worse than all of them because it reports success.

---

## 6. ROOT CAUSE + ONE GENERALIZATION

### Root cause (precise)

Every runner in both repos defines its population by **matching a name or listing one
literally** — `*.test.sh` (R1), a 14-name array (R2), two workflow `run:` lines (R3),
`testpaths=["tests"]` + `test_*.py` (R4), a hardcoded `CHECKS` list (R5). **Not one of them
enumerates the test-like files that exist and asserts that each is claimed by some runner.**
Authorship is therefore the only thing standing between a proof and oblivion: a file whose
name lands one character outside a glob is silently dropped, in the same directory as 77
files that run.

Three compounding factors make it self-concealing:
1. **No inverse assertion.** `_verify_gate_registry_wired` checks registry→CHECKS. Nothing
   checks files→runner. Coverage is asserted in the direction that cannot detect an orphan.
2. **The runner's own test bakes in the assumption.** `gate.test.sh` builds fixtures named
   `alpha.test.sh`/`bravo.test.sh`. It can never notice a file the glob misses.
3. **Existence is accepted as execution.** `gate-creation-standard.sh:168-183` accepts a
   companion test that *exists* and *contains the string* `red-proof|fail-on-revert`. It
   never asks whether a runner runs it. That is why the meta-gate reports 15/16 checks
   "proofed" while its own proof has never executed.

An orphaned test is strictly worse than a missing one: a missing test is a visible gap, an
orphaned test is a gap wearing a green shirt.

### The single generalization — **extend `gate-creation-standard.sh`, compose with the ticket that already exists. No new script.**

`fleet/board/META-GATE-REDPROOF-REACHABLE.md` (priority 1, `depends_on:
META-GATE-CALLSITE-ENUM`, branch `feat/meta-gate-redproof-reachable`, unclaimed) **already
specifies half of this fix** and specifies it well:

> **A.** after a companion is matched, additionally require it be REACHABLE BY A REAL RUNNER
> — basename matches `gate.sh`'s `*.test.sh` glob, OR appears in `rig-ci-scope.sh suites`
> (read by INVOKING it, never re-parsing the array) … else RED `unrun-red-proof`.
> **B.** fail closed if the runner lookup is unresolvable (`runner-set-unresolvable`).
> **C.** RED if the resolved runner set is empty (`runner-set-vacuous`).
> **D.** the assertion must bite its author first.

**Do not duplicate that. Extend it by one assertion in the same loop.** Ticket A/B/C/D is
*check→companion→runner*: it walks the 21 files in `fleet/checks/` and asks whether each
one's proof runs. That direction catches `test_gate_creation_standard.sh` and
`test_graphify_freshness.sh` — **2 of the 33**. It cannot catch the other 31, because their
subjects are `land.sh`, `reap-orphans.sh`, `decompose.sh`, `claim.sh`, `grader-daemon.py` —
scripts that are not in `fleet/checks/` and so are not in the meta-gate's population at all.

**The generalization (one added sub-assertion, same gate, same resolved-runner-set helper
that A/B/C introduces):**

> **A′ — ORPHANED-TEST (the converse of A).** Using the *same* runner set A resolves
> (`gate.sh`'s glob ∪ `rig-ci-scope.sh suites` ∪ the literal `run: bash fleet/tests/…` lines
> in `.github/workflows/*.yml`), enumerate every test-like file in the rig —
> `fleet/**/test_*.{sh,py}`, `fleet/**/*.test.sh`, `fleet/**/*_selftest.py`,
> `fleet/**/selftest.py` — and RED any file matched by **no** runner:
> `orphaned-test: <file> is a test that no runner executes (S1/NOT-INERT — a proof no
> runner executes is not evidence)`.
> Reuses B (fail-closed lookup) and C (non-vacuous: empty file population OR empty runner set
> is RED) verbatim. Exemptions are named literally in a `GCS_ORPHAN_EXEMPT` list with a
> ledger row each — placement can never be an exemption again.

Why this is the right shape:
- **Anti-accretion.** No new script, no new runner, no new workflow. One `for` loop and one
  `red` call inside a gate that already exists, already has the ledger, already has a
  hermetic test harness, and already resolves the runner set for A.
- **It makes the escape impossible rather than fixing 33 instances.** Renaming the 16
  `test_*.sh` files fixes today; A′ fixes the next one, which will be named
  `check_foo_test.sh` or dropped in `fleet/checks/sub/`.
- **It bites its author.** On the real tree A′ goes RED immediately with 33 findings, which
  is the point: the gate must fail before it is trusted. Sequence the renames as
  `GCS_ORPHAN_EXEMPT` entries burned down over one wave, not as a precondition for landing.
- **It closes the false-negative too.** While touching the basename normalization for A′, the
  `rig-ci-scope.sh` ↔ `rig-ci.test.sh` mismatch in §2e should be fixed in the same edit —
  same normalization, same loop, one writer.

Two items A′ does **not** cover, needing one line each in the same wave:
- **Product side:** `reachability-gate`'s missing enforcer. The minimal fix is in
  `tools/check_gate_registry.py` — `optional:true` must not swallow an enforcer that exists
  **nowhere**; a registered gate that has never had a runnable enforcer should RED, not SKIP.
  (One condition, in a checker that already loads every gate.)
- **Product vacuous-skip:** `test_provider_presets.py`'s three PR-gated skips should carry an
  expiry, exactly as `rule-coverage.test.sh` already does for exemptions on the rig.

**Single-line statement of the fix:** *`gate-creation-standard.sh` must enumerate test files
and assert each is claimed by a runner, not enumerate checks and assert each has a file.*

---

## 7. EXECUTION vs READING

| Evidence | How obtained |
|---|---|
| R1 glob, R2 allowlist, R4 testpaths, R5 CHECKS, R6 redproof loop | **Read** (quoted verbatim above, file:line). |
| Non-collection of all 33 bucket-(a) files | **Executed**: `git ls-files` enumeration × repo-wide grep for each basename in an executable position; every hit classified. |
| `CI_SUITES` = 14 entries | **Executed**: `bash fleet/checks/rig-ci-scope.sh suites \| wc -l` → 14. |
| 77 `.test.sh`, 16 `test_*` in `fleet/tests/` | **Executed**: `git ls-files` counts. |
| `reachability-gate` enforcer absent + SKIP-to-green | **Executed**: `ls` (ENOENT) + `python3 tools/check_gate_registry.py` → `SKIP: reachability-gate …` / `check_gate_registry: OK` rc=0. |
| Meta-gate RED with 4 findings, invoked by nothing | **Executed**: `bash fleet/checks/gate-creation-standard.sh scan` (advisory mode, exit 0 by design) + repo-wide grep for callers. |
| `test_provider_presets.py` skips are live today | **Executed**: `python3 -c "from charon import providers; ..."` → all three absent, 26 presets. |
| PR #135 still open | **Executed**: `gh api repos/:owner/:repo/pulls/135` → `open false`. |
| Bucket (b) drift table | **Executed**: `git log -1 --format=%at` per test vs per subject, over the 63 non-CI suites. |
| Rig canaries fail loud (`exit 2`) | **Read** at `semgrep-canary.test.sh:28`, `gitleaks-canary.test.sh:28`, `bandit-canary.test.sh:30`. |
| `test_gate_creation_standard.sh` currently FAILS (PASS=30 FAIL=1) | **Read** from the prior scan `fleet/state/reviews/CLASS-SCAN-UNAUDITED-GATES-agen-kolar.md` — **not re-executed here** (read-only remit; no fleet test was run). |

**Not executed, deliberately:** no `charon gate` on any branch (per the diff-cover recursion
constraint), no fleet `*.test.sh`, no `handoff.sh`, no `land.sh`. Nothing was renamed, moved,
or fixed; no board file touched.
