# AUDIT — LATENCY / WALL-CLOCK BUDGET BREACHES

**Date:** 2026-07-24 · **Session:** agen-kolar · **Scope:** rig `/home/stack/charon-private` + product `/home/stack/code/charon` · **Mode:** READ-ONLY (nothing edited; no budget bumped)

**Standing rule this audit serves:** slowness is a FAILURE CLASS. The response to a breach is never a bigger number — it is the attribution and the class fix. No timeout in either repo was changed.

---

## 0. Headline

Three findings, in order of severity.

1. **`fleet/validate_board.sh:390-399` is the silent-degrade archetype and it is BREACHING TODAY.**
   The parallelizability gate is run under a hardcoded `timeout=15`, and its expiry is caught into
   the `wci` (advisory) list, which **does not affect the exit code** (`validate_board.sh:442`).
   Measured: **13.9 s idle / 15.7 s warm** against a **15 s** budget — already over the line — and
   under moderate load it hard-breaches. Reproduced verbatim:
   `BREACH: TimeoutExpired at 15s -> validate_board would emit 'parallelizability-check-failed' as WCI-ADVISORY (board still GREEN)`.
   **A budget overrun has converted a gate into a no-op while the board reports GREEN.**

2. **`fleet/gate.sh:45-51` launches all 77 `*.test.sh` concurrently with NO concurrency cap on a
   16-core box.** This is the single root cause behind every "passes standalone, fails under the
   runner" report. Proven by measurement: `reconcile-merged.test.sh`'s perf assertion runs
   **2 636 ms standalone → 46 597 ms under 48-way CPU contention (17.7×)**, against a hand-typed
   5 000 ms bound. The failure is LOUD but **misattributed** — the test prints
   `"re-scan regression?"`, accusing product code of a perf regression that does not exist.

3. **`fleet/benchmark/budget-derive.py` — the correct, tested, p95-derived budget mechanism — is
   INERT.** It has no shell caller anywhere in the rig (only its own test), and its output file
   `budgets.tsv` **does not exist anywhere on disk**. Every live latency budget in the eval path is
   still a hand-typed constant. The answer to "where should budgets come from" is already built
   and already unwired.

---

## 1. Budget inventory

### 1a. Rig — subprocess / check budgets (the gate path)

| file:line | budget | guards | breach path |
|---|---|---|---|
| `fleet/validate_board.sh:393` | `timeout=15` | `checks/parallelizability-gate.sh scan` | **WCI-ADVISORY → exit 0. SILENT.** |
| `fleet/validate_board.sh:408` | `timeout=30` | `checks/gate-parity.sh scan` | `red` → exit 1. LOUD (fail-closed by design) |
| `fleet/validate_board.sh:425` | `timeout=10` | `git status --porcelain -- src/` | `red` → exit 1. LOUD |
| `fleet/checks/substrate_first_gate.py:309` | `timeout=15` | `git check-ignore` | `except → _IGNORE_CACHE=True` = "ignored". **SILENT** |
| `fleet/checks/substrate_first_gate.py:319` | `timeout=30` | every `git` call in the gate | `return None` → `changed_files()=None` → `:844-846` prints INFO "no diff range resolvable (RIG_CI_BASE unset)" and **returns 0 = PASS. SILENT + MISATTRIBUTED** |
| `fleet/checks/config-ssot-gate.sh:117` | `timeout 15 … \|\| true` | remote providers.json read | empty → `UNREACHABLE` → hard RED. LOUD, misattributed (timeout reads as "unreachable") |
| `fleet/checks/bridge-health.py:24` | `timeout=10` | session-bridge probe | `except → sys.exit(1)`. LOUD |
| `fleet/config-drift.sh:54` | `timeout 15 bash -c "$cmd" 2>/dev/null` | per-source config read | → `reachable=0` → WARN + `sys.exit(1)` at `:197`. LOUD, misattributed |
| `fleet/capability/availability.py:78` | `timeout=self.timeout` (10.0, `:60`) | session-bridge board call | `except → sessions=[]`, `_error` surfaced via `note()`. SEMI-LOUD (advisory string only) |
| `fleet/watchdog/watchdog-lib.sh:37,61` | `WD_TCP_TIMEOUT=3` | TCP connect probe | returns 1 → LOUD |
| `fleet/watchdog/monit-selfwatch.sh:67` | `timeout 10` | `monit status` | `alive=0` → LOUD |

### 1b. Rig — session/land path budgets

| file:line | budget | guards | breach path |
|---|---|---|---|
| `fleet/end-session.sh:342` | `END_SESSION_PUSH_TIMEOUT=120` | `land-push.sh` | `:347` `124`/`137` **refused LOUDLY, never silently closed**. Exemplary |
| `fleet/sync-checkouts.sh:38,61` | `SYNC_CHECKOUTS_FETCH_TIMEOUT=20` (`-k 5`) | `git fetch` | `:76-78` prints `TIMED OUT … — SKIP`, returns 1; `sync_one` does `\|\| return 0`; `preflight.sh:38` `return 0` unconditionally. **Prints, but exit-clean → checkout silently left stale. SILENT at the gate level** |
| `fleet/handoff.sh:336` | `HANDOFF_STATE_TIMEOUT=15` | `gh pr list` | `\|\| echo "(gh unavailable / timed out …)"`. **SILENT — handoff PR list silently becomes empty** |
| `fleet/handoff-generated-state.sh:32,43,56,63,79` | `HANDOFF_STATE_TIMEOUT=15` | `git ls-remote`, `gh pr list`, `git worktree list` | degrades to blank/partial GENERATED-STATE. **SILENT** |
| `fleet/deploy-session-end.sh:50` | `SESSION_END_LOOKUP_TIMEOUT=15` | session lookup | — |
| `fleet/handoff.sh:377` | *(no timeout)* `validate_board.sh 2>&1 \|\| true` | board validation | **`\|\| true` masks a RED board inside the handoff.** MASKED |

### 1c. Rig — eval / model-run budgets (all hand-typed)

| file:line | budget | note |
|---|---|---|
| `fleet/charon-run.sh:114` | `CHARON_RUN_TIMEOUT_S:-1800` | **Exemplary breach path** — see §4 |
| `fleet/benchmark/dogfood-eval.sh:92` | `DOGFOOD_LATENCY_BUDGET_S:-900` | hand-typed "15 min for a D1 ticket" |
| `fleet/benchmark/reviewer-dogfood.sh:61` | `REVIEWER_LATENCY_BUDGET_S:-300` | hand-typed |
| `fleet/review-pool.sh:212` | `CHARON_RUN_TIMEOUT_S:-300` | **caller shrinks the 1800 default 6× with no derivation** |
| `fleet/benchmark/honest-battery-sweep.sh:45` | `SWEEP_LATENCY_BUDGET_S:-480` | the exact 480 s `budget-derive.test.sh:121-123` pins as "must NOT be the hardcoded value" |
| `fleet/benchmark/budget-derive.py:47` | `wall = p95 × 1.5`; zero-data default `900.0` | **the correct mechanism — INERT, see §5** |
| `fleet/flow-canary.sh:76,77` | `FC_REQ_TIMEOUT_S=45`, `FC_STATUS_TIMEOUT_S=8` | LOUD |
| `fleet/failover-canary.sh:98,99` | `FO_REQ_TIMEOUT_S=20`, `FO_STATUS_TIMEOUT_S=8` | LOUD — `:320,:387` explicitly red a hang |
| `fleet/balance-canary.sh:137,156` | `FC_REQ_TIMEOUT_S:-45` | LOUD |
| `fleet/benchmark/test-quality-gate.py:179,182` | `timeout=timeout_s` → returns `124` | structured, LOUD |

### 1d. Rig — perf assertions inside tests (hand-typed wall-clock bounds)

| file:line | bound | measured standalone |
|---|---|---|
| `fleet/tests/reconcile-merged.test.sh:145` | `< 5000 ms` | **2 636 ms** (53 % consumed) |
| `fleet/tests/sync-checkouts.test.sh:125` | `≤ 20 s` | not measured |
| `fleet/tests/sync-checkouts.test.sh:178,184` | `≤ 15 s` (3 s budget + 12 s slack) | not measured |
| `fleet/tests/leg-preflight.test.sh:185` | `< 30 s` | not measured |
| `fleet/tests/end-session-push.test.sh:317` | `< 20 s` | not measured |

### 1e. CI workflow budgets

Every job in both repos carries `timeout-minutes`; **no job is exposed to the 360-min default**.

| file:line | value | job |
|---|---|---|
| `charon-private/.github/workflows/bandit.yml:47` | 10 | `bandit` |
| `charon-private/.github/workflows/gitleaks.yml:46` | 10 | `gitleaks` |
| `charon-private/.github/workflows/rig-ci.yml:55` | 10 | `rig-ci` |
| `charon-private/.github/workflows/rig-ci.yml:96` | **8 (step)** | "Rig test suites (ALLOWLIST only)" — the ONLY step-level timeout in 8 workflows |
| `charon-private/.github/workflows/semgrep.yml:45` | 10 | `semgrep` |
| `code/charon/.github/workflows/ci.yml:28` | 20 | `gate` |
| `code/charon/.github/workflows/ci.yml:72` | 10 | `wheel-smoke` |
| `code/charon/.github/workflows/heavy.yml:23,56,84` | 20/20/10 | `modeA-isolation`, `image-smoke`, `supply-chain-audit` |
| `code/charon/.github/workflows/release.yml:40,69,114` | 20/20/15 | `gate`, `image-smoke`, `publish` |
| `code/charon/.github/workflows/windows-exe.yml:20` | 15 | `build-exe` |

No `timeout <N>` shell call appears inside any `run:` block in either repo, so **no rc=124 can arise
in CI** and the `|| true` masking below cannot swallow a timeout kill. A `timeout-minutes` expiry
SIGKILLs the step and fails the job — not swallowable. **All CI timeouts are LOUD.**

**pytest has NO time budget of any kind.** `code/charon/.github/workflows/ci.yml:55` and
`release.yml:62` run `pytest -q -n auto` with no `--timeout`; `pyproject.toml:74-82` has no
`addopts` / `timeout`; `pytest-timeout` is not a dependency in either repo;
`charon-private/pytest.ini` has only `norecursedirs`.

### 1f. Product — src/ budgets (selection; full list in §2 evidence)

Largest first: `land.py:402` `_run_tests(timeout=1800)`; `acceptance.py:49` `verify(timeout=600)`;
`land.py:232` gitleaks `timeout=300`; `adapters/acp.py:131` `_rpc(timeout=600.0)`;
`proxy_server.py:473` `fwd_timeout=180.0`; `litellm_plane/litellm_router.py:215-326` and
`streaming.py:66-208` and `metering.py:152,179` all `timeout=180.0`; `routing_proxy.py:106`
`timeout=300`; `land.py:197,463,657` `timeout=120`; `scanners.py:221` `timeout_per_scanner=60`
with `:295` `fut.result(timeout=60+5)`; `decompose_planner.py:373` `timeout=60.0`;
`recommend.py:168,222` `timeout=30.0`; `speculative_execution.py:56` `timeout_ms=30000`;
`doctor.py:72,169,198` `timeout=30`, `:182,212` `timeout=60`; `adapters/review.py:83` `30.0`;
`providers.py:242` / `balance.py:295,556` / `cli.py:731` `timeout=20`;
`config/keyprobe.py:10` `_VALIDATE_TIMEOUT=15.0`; `discover.py:24,132,257` / `connect.py:56`
`timeout=10`; `observability.py:112,148` `timeout=5`; `egress.py:248` `timeout=3.0`;
`adapters/acp.py:235` `wait(timeout=10)`; `routing_policy/catalog_refresh.py:288` `join(timeout=1.0)`.

Time-window constants (not timeouts, but duration-vs-constant): `quality_scorer.py:21`
`_LATENCY_THRESHOLD_MS = 30_000`; `ledger.py:29` `_LOCK_TTL_SECONDS = 900`; `failover.py:90`
`cooldown_s=60.0`; `session_affinity.py:16` `ttl=300.0`; `balance.py:140` `_DEFAULT_POLL_TTL=300.0`;
`proxy_server.py:483` `max_cooldown_s=120.0`; `quota.py:74-100` rolling windows 60/86400/604800.

Perf assertions in product tests — only two: `tests/test_scanners.py:167`
`assert elapsed < delay*1.6` (**< 0.24 s**) and `:190` `assert elapsed < delay*2.0` (**< 0.24 s**).

No `signal.alarm` / `SIGALRM` / `asyncio.wait_for` anywhere in the product. No rc=124 handling
anywhere in the product (`src/`, `tests/`, `tools/`, `Makefile`, `install.sh`, `packaging/`).

---

## 2. Breached / near-breached — measured

All measurements taken on this box (16 cores, 15.9 GB, load ~idle unless stated). Method noted per row.

| # | budget | value | measured | util | verdict |
|---|---|---|---|---|---|
| B1 | `validate_board.sh:393` parallelizability scan | **15 s** | **13.9 s** cold-idle; **15.7 s** warm; **BREACH (TimeoutExpired)** under 16 CPU burners | 93–105 %+ | **BREACHED — SILENT** |
| B2 | `validate_board.sh:408` gate-parity scan | **30 s** | **13.1 s** idle | 44 % | NEAR-BREACH (same O(n²) engine as B1 — breaches under the same load) |
| B3 | `reconcile-merged.test.sh:145` perf bound | **5 000 ms** | **2 636 ms** standalone → **46 597 ms** under 48-way load | 53 % → **932 %** | **BREACHED under the runner — LOUD but MISATTRIBUTED** |
| B4 | `test_scanners.py:167,190` parallelism | **0.24 s** | passed standalone (0.43 s file) and under 32 CPU burners (0.83 s file) | — | HOLDING; contention-fragile by construction |
| B5 | `ci.yml:28` gate job | **20 min** | full `pytest -q -n auto`: **22.9 s** (2 353 passed) | 2 % | HEALTHY |
| B6 | `rig-ci.yml:96` rig test step | **8 min** | not measured (would require running the full concurrent suite — declined, see §6) | — | UNMEASURED. `checks/rig-ci-scope.sh:302-314` runs each allowlisted suite with **no per-suite `timeout`**, so one hung suite consumes the whole step |
| B7 | `charon-run.sh:114` model run | **1800 s** | operator-observed `rc=124` / `pool-exhausted-timeout` | — | BREACHED in the field — **LOUD and correctly attributed** |
| B8 | `checks/rule-sync.sh scan` | *(no budget)* | **10.0 s** | — | unguarded; would breach a 15 s-class budget if one were added |
| B9 | `checks/gate-creation-standard.sh scan` | *(no budget)* | **3.0 s** | — | healthy |
| B10 | `checks/gpt55-primary.sh scan` | *(no budget)* | **3.4 s**, rc=1 | — | healthy runtime |

Growth curve for B1 (synthetic board copies, same gate binary):

| board size | elapsed |
|---|---|
| 50 tickets | **5.25 s** |
| 113 tickets (live) | **15.71 s** |

n ratio 2.26× → time ratio **2.99×**. Superlinear. Linear would predict 2.26×, pure O(n²) 5.11×.
Per-ticket cost rose from 105 ms to 139 ms. The live board crossed the 15 s line somewhere around
n ≈ 105–110 and **is now permanently at or over it**.

---

## 3. Attribution

### (ii) BUDGET SET ARBITRARILY, overtaken by growth — the dominant cause

- **`validate_board.sh:393` `timeout=15`.** No derivation exists in the file, the commit message,
  or `GATE-PARITY-LAND-VS-LAUNCH.md`. It is a round number. The board grew to 113 tickets and the
  scan grew superlinearly past it. Evidence: the growth table in §2 plus the reproduced breach.
- **`validate_board.sh:408` `timeout=30`.** Same class — 30 is 2× the 15 next to it, not a measurement.
- **`reconcile-merged.test.sh:142-145` `5000 ms`.** The comment self-declares it arbitrary:
  *"5s is a generous bound for the test (even on a slow CI host the index+5 done.sh <1s…)"* — a
  hand-typed guess with a hand-typed safety factor, and the guess is 2× reality on an idle box.
- **`review-pool.sh:212` `CHARON_RUN_TIMEOUT_S:-300`** vs `charon-run.sh:114` default `1800`. The
  same operation carries a 6× different budget depending on caller. At most one is right.
- **`dogfood-eval.sh:92` `900`, `reviewer-dogfood.sh:61` `300`, `honest-battery-sweep.sh:45` `480`.**
  Three different hand-typed wall-clocks for the same class of model run. `budget-derive.py`'s own
  test (`fleet/tests/budget-derive.test.sh:121-123`) explicitly pins that **480 must not be the
  answer** — yet 480 is still what the live sweep uses.
- **`test_scanners.py:167,190` `delay*1.6` / `delay*2.0`.** The multipliers are chosen to
  distinguish parallel from serial, not derived from observed scheduling jitter.

### (iii) RESOURCE CONTENTION — fine standalone, dies under the runner

- **`fleet/gate.sh:45-51` is the source.** 77 test files launched with a bare `&` and no cap, each
  spawning bash/python3/git/mktemp subtrees, on 16 cores. There is no `-P`, no job-slot loop, no
  `xargs`, no semaphore. This is a deliberate 2026-07-13 "GATE-PERF" change (`gate.sh:4-11`) that
  replaced a serial loop with unbounded fan-out — it removed the serialisation without adding a bound.
- **Direct measurement:** `reconcile-merged.test.sh` perf assertion **2 636 ms → 46 597 ms** (17.7×)
  under 48-way CPU contention. This reproduces the operator's reported `perf 8.7s` exactly
  (8.7 s ≈ 3.3× the standalone 2.6 s, i.e. the 77-way regime).
- **`fork: Resource temporarily unavailable`** is the same mechanism at its extreme. `ulimit -u` on
  this box is 63 481 — the ceiling is not process count but memory + scheduler thrash from an
  unbounded fan-out of subprocess-heavy bash.
- **Secondary hazard in the same file:** `gate.sh:76` `rc="$(cat "$WORK/$test_name.rc")"` runs
  under `set -e`. If a subshell is killed before writing its `.rc` (exactly what fork exhaustion
  does), the command substitution fails and **gate.sh aborts mid-report with a bare non-zero exit** —
  the resource failure is reported as a gate failure with no message.

### (iv) PATHOLOGICAL — accidental superlinearity + missing cache

- **`checks/parallelizability-gate.sh:91-102` `is_decomposed()` re-walks the entire board for
  every candidate ticket**, and each walk calls `field()` (`:50-53`), which forks a `grep` **and**
  a `sed` per lookup. Board-wide that is O(n²) file reads and ~4 forks per inner iteration. There
  is no memoised `parent:` index, even though one pass over the board would build it.
- **`checks/gate-parity.sh:126-147` multiplies it.** `cmd_scan` loops every live ticket and, per
  ticket, `exec`s `parallelizability-gate.sh check <id>` (`:67-68`) — a fresh bash process that
  **re-does the whole `is_decomposed` board walk from scratch**. Two independent O(n²) engines run
  back-to-back inside one `validate_board` invocation, sharing nothing.
- Both are pure recomputation with a trivially cacheable key. This is why the constant in (ii) was
  overtaken so fast: the work per ticket is itself growing.

### (i) GENUINELY SLOW WORK

- **`charon-run.sh:114` at 1800 s** — a real 30-minute model run. The budget is honest.
- **`checks/rule-sync.sh scan` at 10.0 s** — real cross-referencing work, currently ungated.
- No other confirmed instance. Notably `pytest -q -n auto` at **22.9 s against a 20-minute budget**
  means the product suite is nowhere near its ceiling; the CI risk there is a *hang*, not slowness.

---

## 4. SILENT-DEGRADE LIST — breaches that disable a check with no red

**This is the headline of the audit.** Ordered by blast radius.

| # | site | what the breach does | why it is silent |
|---|---|---|---|
| **S1** | `fleet/validate_board.sh:390-399` | Parallelizability gate stops running entirely | `except Exception → wci.append(...)`; `wci` is printed but **`validate_board.sh:442` exits on `red` only**. Board prints GREEN. **Currently breaching.** |
| **S2** | `fleet/checks/substrate_first_gate.py:319-321` → `:360-363` → `:843-846` | A 30 s git timeout makes `changed_files()` return `None`; the gate prints `INFO … not applicable` and **`return 0` = PASS** | Message blames `RIG_CI_BASE unset`, so the operator reads a real timeout as a config no-op |
| **S3** | `fleet/checks/substrate_first_gate.py:309-312` | A 15 s `git check-ignore` timeout caches the path as **ignored**, silently shrinking the gate's coverage | `except (OSError, SubprocessError) → True` — no log, no note |
| **S4** | `fleet/sync-checkouts.sh:76-78` + `fleet/preflight.sh:34-39` | A fetch timeout leaves a checkout stale; `sync_one` swallows it with `\|\| return 0` and `run_sync_checkouts` returns 0 unconditionally. **Every downstream preflight gate then evaluates a stale tree** | Prints a line into a long scan; exit status stays clean |
| **S5** | `fleet/handoff.sh:336` and `fleet/handoff-generated-state.sh:43,56,63,79` | A 15 s `gh`/`git ls-remote` timeout empties the handoff's open-PR list and GENERATED-STATE | `\|\| echo "(gh unavailable / timed out …)"` — reads as "nothing open" |
| **S6** | `src/charon/speculative_execution.py:159` | `except TimeoutError: pass` after `as_completed(timeout=30 s)`; empty `completed` → **returns `None`**, identical to "speculation disabled" | Bare `pass`, no log, no metric — while the *same file* logs a warning for an invalid base at `:60-66` |
| **S7** | `src/charon/discover.py:50` (fanned out at `:177`) | A 10 s provider timeout makes that provider **silently vanish from the model catalog** | `except Exception: return None` |
| **S8** | `src/charon/balance.py:73,96,124` | A 20 s poll timeout returns `None` = "provider exposes no balance". With the 300 s cache TTL (`:140,:305`) a stale balance persists then silently becomes `None` | `except Exception: return None` — money-path |
| **S9** | `src/charon/config/keyprobe.py:75` then `:110` | A 15 s probe timeout is reported to the operator as **`valid: False`** — a network problem presented as a bad key | `except Exception: pass` then a hedged message with an unhedged boolean |
| **S10** | `src/charon/observability.py:113,149` | Telemetry loss on a 5 s timeout is completely invisible — no counter, no log | `except Exception: pass  # noqa: BLE001 — non-blocking by design` (documented, but unmeasured) |
| **S11** | `src/charon/cli.py:739` | Preset base probe timeout prints `UNREACHABLE` but **returns exit 0** | print without a non-zero exit |
| **S12** | `src/charon/routing_policy/catalog_refresh.py:288` | `t.join(timeout=1.0)` with no `is_alive()` check — a stuck catalog-refresh thread is abandoned | no post-join assertion |

### Loud-but-misattributed (not silent, still wrong)

These fail visibly but name the wrong cause, which costs an investigation each time:

- `fleet/tests/reconcile-merged.test.sh:146` — prints `"re-scan regression?"` when the real cause is
  `gate.sh` fan-out. **Currently firing.**
- `fleet/checks/config-ssot-gate.sh:117-121` and `fleet/config-drift.sh:54,66-70` — a 15 s timeout
  is reported as `UNREACHABLE`, indistinguishable from a genuinely down source.
- `src/charon/land.py:405` `except subprocess.TimeoutExpired: return False` — a 30-minute test-suite
  timeout is indistinguishable from a *failing* suite. Fails closed (good) but attributes to the code.
- `src/charon/acceptance.py:59` — same shape at 600 s.
- `fleet/gate.sh:76` under `set -e` — fork exhaustion surfaces as a bare non-zero exit.

### The exemplary counter-pattern (what "right" looks like)

`fleet/charon-run.sh:125-177` disambiguates a single `rc=124` **three ways** — `pool-exhausted-timeout`
(provider-side), `too-slow-failover` (model-attributable), `leg-fault-failover` (infra hang) — each
with a distinct verbatim marker, each written to the ledger, none silent.
`fleet/end-session.sh:335,347` does the same for `124`/`137` ("refused LOUDLY, never silently closed").
`src/charon/scanners.py:100,126,151,177` returns a first-class `"timeout"` status that `land.py:378`
fails closed on. These three prove the rig already knows the right shape; it just is not enforced.

### Masking inventory (`|| true`, `| tail`, missing pipefail)

- `fleet/handoff.sh:377` — `validate_board.sh 2>&1 || true` **masks a RED board** inside the handoff.
- `fleet/config-drift.sh:66,72` — `fetch … || true` (compensated by the `reachable=0` branch).
- `fleet/checks/config-ssot-gate.sh:117` — `|| true` (compensated by the empty-`raw` RED).
- `fleet/gate.sh:72,93` — `wait "$pid" || true` (compensated: rc captured per file).
- `code/charon/.github/workflows/heavy.yml:93` — `pip-audit || true`, the **only permanently-green
  step in either repo** (deliberate, documented advisory at `:78-79`).
- `set -o pipefail` is present in only 2 of the 8 workflows (`bandit.yml:67`, `gitleaks.yml:66`).
  Every other multi-line `run:` uses GitHub's default `bash -e {0}` — errexit on, **pipefail off**.
  All such pipelines were checked and are compensated by explicit `test`/`exit 1` assertions
  (`heavy.yml:75`, `release.yml:106`), so no CI breach is currently masked.
- `fleet/checks/*.sh` all carry `set -uo pipefail`, already enforced as item **S5 FAIL-LOUD** by
  `fleet/checks/gate-creation-standard.sh:23`.

---

## 5. Root cause + the ONE generalization

### Root cause

Two independent defects compound:

1. **Budgets are hand-typed constants with no derivation and no re-derivation**, so every one of
   them is a countdown to a false failure as the board/repo grows. The rig already knows this is
   wrong — `budget-derive.py:14-22` states the rule and its own test pins that the hardcoded 480
   must not survive — but the mechanism is unwired.
2. **A budget breach is allowed to land in a non-blocking sink.** `validate_board.sh:398-399` catches
   `Exception` (which includes `TimeoutExpired`) into `wci`, a list the exit code ignores. Nothing
   anywhere enforces that a *check-runner* budget expiry must reach `red`. Compare `:414-415`
   immediately below, which does exactly the right thing for gate-parity — the correct pattern is
   already in the same file, six lines apart, and nothing makes the two agree.

### The single generalization — extend `gate-creation-standard.sh`, item S5

`fleet/checks/gate-creation-standard.sh` is already the META-GATE over every `fleet/checks/*.sh` and
every `tools/gates.json` entry, and it already owns exactly the right doctrine class:

> `gate-creation-standard.sh:23` — **S5 FAIL-LOUD** — every `fleet/checks/*.sh` carries
> `set -...uo pipefail` (fail-quiet-pipe-mask class: validate_board's historic green-on-double-claim).

**Extend S5 from "fail-quiet pipe" to "fail-quiet budget" — same item, same meta-gate, same
`GATE-GAP-LEDGER` root_class, no new file.** S5 becomes: *a gate must not be silenceable, by a
masked pipe **or by a budget expiry***. Concretely, S5 additionally RED-flags:

- any `subprocess.run(..., timeout=N)` in `validate_board.sh` / `fleet/checks/*` whose `except`
  branch appends to a **non-blocking** sink (`wci`, `warn`, `info`) rather than `red` — S1 today;
- any `except (TimeoutExpired|TimeoutError|SubprocessError)` in `fleet/checks/*` that returns a
  **PASS-shaped** value (`0`, `True`, `None`, `set()`) instead of a distinct `timeout` status —
  S2/S3 today;
- any `timeout <N>` in `fleet/*.sh` whose `124`/`137` case is not handled in a branch distinct from
  the generic failure branch — S4/S5 today. `charon-run.sh:125-177` and `end-session.sh:347` already
  pass this and become the reference red-proofs.

This composes rather than accretes: the existing companion-test convention (`fleet/tests/`) supplies
the red-proof, the existing `GATE-GAP-LEDGER.tsv` records the miss, and `gate-creation-standard.sh scan`
is already wired as an advisory surface. **No new standalone script.** It runs in 3.0 s (§2 B9), so
adding these predicates is affordable.

### Where budgets should COME FROM

**`fleet/benchmark/budget-derive.py` already is the answer and is INERT.** It implements
`wall_budget_s = p95(known-good completions) × 1.5` (`:47`, `:14-22`) plus per-leg normalisation
`token_budget / measured tok_s + fixed_overhead` (`:17`), with a safe `900.0` zero-data default
(`fleet/tests/budget-derive.test.sh:175`). It is fully tested. It has **no shell caller anywhere in
the rig** (verified: the only non-test reference is `capability/grades.py:342`, a comment), and its
output **`budgets.tsv` does not exist anywhere on disk** (verified by `find`). Its sole consumer,
`fleet/benchmark/item-bank/pipeline.py:369-370`, therefore silently falls through `_load_budgets`'s
`if not path.exists(): return out` (`:229-231`) to an empty dict.

The rule to adopt, stated once and applied everywhere:

> **A wall-clock budget is `p95(measured) × 1.5`, re-derived on a cadence and written to a file the
> consumers read. A hand-typed constant is permitted only as the zero-data fallback, and must be
> labelled as such.**

Three consequences, in dependency order:

1. **Emit `budgets.tsv`.** Run `budget-derive.py` on the existing foreman/graphify cadence
   (`fleet/foreman-cadence.sh` already owns interval-gated periodic work — add a row, not a script).
2. **Point the live consumers at it**, replacing `dogfood-eval.sh:92` (900), `reviewer-dogfood.sh:61`
   (300), `honest-battery-sweep.sh:45` (480), `review-pool.sh:212` (300) with a read of the derived
   value and the constant demoted to fallback.
3. **Extend the same derivation to the check-runner budgets** — `validate_board.sh:393` (15) and
   `:408` (30) should be `p95(scan time) × 1.5` over the last N preflights, not literals. On today's
   numbers that is ≈ 21 s and ≈ 20 s, and it would have *grown with the board* instead of being
   overtaken by it. **Deriving is the fix; typing a bigger literal is not** — and per the standing
   rule, the real fix for B1/B2 is the missing `parent:` index in `is_decomposed()` (§3-iv), which
   removes the O(n²) and drops the scan back under any honest budget.

**Bounded fan-out (the (iii) class fix).** `fleet/gate.sh:45-51` must cap concurrency at
`$(nproc)`-ish job slots rather than launching all 77 test files at once. That single change removes
the contention that produces the `perf 8.7s` misattribution, the `fork: Resource temporarily
unavailable` failures, and the standalone-passes-under-runner-fails reports for `reconcile-merged`
and `balance-canary` — without touching a single perf bound. It also belongs to the same
anti-accretion posture: modify the existing runner loop, add no new harness.

---

## 6. Execution vs reading

**Executed (measured, not inferred):**

- `fleet/checks/parallelizability-gate.sh scan` — timed cold (13.90 s) and warm (15.71 s) on the live
  113-ticket board; re-timed against synthetic 50-ticket and 113-ticket board copies in a scratch dir
  (`PARALLEL_GATE_BOARD` seam) to derive the growth curve.
- The **exact** B1 breach reproduced in Python with `subprocess.run(..., timeout=15)` under 16 CPU
  burners, confirming `TimeoutExpired` and therefore the `wci` path.
- `fleet/checks/gate-parity.sh scan` — 13.10 s, rc=0.
- All 12 `fleet/checks/*.sh scan` entry points timed individually under `timeout 90`.
- `fleet/tests/reconcile-merged.test.sh` — standalone (2 636 ms) and under 48 CPU burners
  (46 597 ms, FAIL). Burners were `timeout 60`-bounded and reaped.
- Product `pytest -q -n auto` — full suite, 2 353 passed in 22.91 s (25.3 s wall).
- `tests/test_scanners.py -k parallel` — standalone and under 32 CPU burners; both passed.
- `find` for `budgets.tsv` (absent) and `grep` for `budget-derive` callers (none outside its test).
- System facts: `nproc=16`, `ulimit -u=63481`, 15.9 GB RAM, 113 live board tickets, 77 rig test
  files, 76 `fleet/*.sh`.

**Read only, not executed — and why:**

- **`fleet/gate.sh` itself was NOT run.** Running the concurrent 77-test suite is the exact
  fork-exhaustion condition under audit; triggering it to measure it would be the fleet-selfcheck
  fork-bomb class. Its behaviour was derived from the source (`:45-51`, `:72-76`) plus the
  contention measurement on a single representative test.
- **`charon gate` was NOT run** on any branch, per the standing instruction about diff-cover
  recursion. Product-gate timings come from the pytest run and the workflow files.
- **`rig-ci.yml:96`'s 8-minute step (B6) was NOT measured** — measuring it means running the full
  concurrent allowlisted suite, i.e. the same hazard as above. Reported as UNMEASURED rather than
  guessed.
- **CI job budgets (§1e) were not exercised** — they are GitHub-side and cannot be measured locally.
  Their *breach paths* were determined by reading, and the reading is conclusive: a
  `timeout-minutes` expiry SIGKILLs the step, so no `|| true` can swallow it.
- **Network-dependent budgets** (`flow-canary`, `failover-canary`, `balance-canary`,
  `handoff-generated-state`, `config-drift`, `config-ssot-gate`) were not exercised against the live
  gateway — a live-traffic probe is out of scope for a read-only audit and would have perturbed the
  very system being measured. Their budgets and breach paths are from source.
- **Product `src/` runtime budgets (§1f)** are from source reading (delegated sweep), not execution;
  exercising `land.py:402`'s 1800 s path or `acp.py:131`'s 600 s RPC requires a live agent run.
