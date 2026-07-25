# SCORECARD FALSE-BLOCK AUDIT — rc=127 launcher fault mis-booked as model quality

Session: agen-kolar · 2026-07-25 (UTC) · READ-ONLY audit, nothing written outside this file.
Grader daemon pid 180289 (user `bench-grader`) was live throughout; no grader-owned state touched.

## VERDICT (one paragraph)

24 false BLOCK enqueues were attempted against the four `strong`-chain models by run
`strong-3436392`. **8 of them reached the grader spool; 0 of them reached
`fleet/model-scorecard.tsv` or `scorecard.v1.json`.** Two independent guards stopped
them — one at the writer, one at the daemon. **Live routing is NOT affected right now:**
detained lists are empty for every work_class, the `strong` chain is unchanged, and
`capability/grades.py` currently returns `None` for every model anyway. Run
`strong-4010362` contributed **zero** false BLOCKs — it fail-closed at the capped-filter
before ever calling `charon-run.sh`.

**But the audit turned up a pre-existing red the brief did not know about: one false
BLOCK from this same defect class IS already merged into the live scorecard** —
`model-scorecard.tsv:36`, `kimi-k2.6` / `FLEET-DEMAND-DRIVEN-ROUTING`, booked from
`rc=134` (SIGABRT, a process crash). See §5.

---

## 1. Where BLOCK entries land — path and owner

| item | value |
|---|---|
| enqueue writer | `/home/stack/charon-private/fleet/capture/enqueue-capture.sh` (runs as `stack`) |
| spool req dir | `/var/lib/bench-grader/spool/req` — `drwx-wx-wt` (1733 maildrop), owner `bench-grader` |
| spool res dir | `/var/lib/bench-grader/spool/res` — `drwxr-xr-x`, **world-readable** |
| spool work dir | `/var/lib/bench-grader/spool/work` — `drwx------`, unreadable to `stack` |
| consumer | `fleet/benchmark/grader-daemon.py` (pid 180289, user `bench-grader`) |
| merged ledger | `fleet/model-scorecard.tsv` — owner `bench-grader`, world-READABLE |
| merged artifact | `fleet/scorecard.v1.json` — owner `bench-grader`, world-READABLE |
| enqueued filename | `capture-<model>-<REF>.<stage>.<pid>.<nanos>.json` (`enqueue-capture.sh:152-153`) |

`req/` is a **write-only maildrop for `stack`** (`-wx`, no read bit): I can create and
`stat` an exact path but **cannot enumerate it**. Confirmed by execution:
`ls /var/lib/bench-grader/spool/req` → `Permission denied`. I did **not** attempt to read
it as another user. The operator command to enumerate is in §6.

`res/` IS readable, and that is what made this audit decisive — see §3.

---

## 2. How many false entries, which models, which runs

### Root cause (proved by production log, not by reading)

`fleet/charon-run.sh:48-65` `is_infra_fault()` special-cases exactly **one** exit code
(`rc=3`, line 60) and otherwise matches only **stdout TEXT**. `rc=127` (`timeout: failed
to run command 'opencode': No such file or directory`) matches no text pattern, so the
predicate returns false at `:181` and control falls to `:187-191`, which calls
`cap "$M" "FAIL" "BLOCK" "fail" …`.

Production evidence, `fleet/state/agent-logs/strong-3436392-*.txt`:

```
timeout: failed to run command 'opencode': No such file or directory
[charon-run] model 'minimax-m3-free' exited nonzero (rc=127, not a limit, not an infra fault) -> failing over
```

That line is emitted **only** from the `:187` branch — the same branch that fires `cap …
BLOCK`. This is execution evidence from the real run, stronger than a synthetic red-proof.

### Counts

Source: `fleet/provider-exhaustion-ledger.tsv`, rows where `event == error-failover`
(the *only* event that reaches `cap … BLOCK`).

**rc=127, all from `strong-3436392`, 2026-07-25T05:14:49Z → 05:15:07Z — 24 events:**

| model | events | of which reached the spool |
|---|---|---|
| minimax-m3-free | 6 | 2 |
| deepseek-v4-flash | 6 | 2 |
| glm-5.2 | 6 | 2 |
| gpt-5.4-mini | 6 | 2 |
| **total** | **24** | **8** |

By job (each ticket was attempted twice by the launcher's retry, 4 models per attempt):

| job | work_class | events | reached spool? |
|---|---|---|---|
| `strong-3436392-LENS-REGISTRY-AND-REPORT` | `rig-meta` | 8 | **NO** — writer rejected |
| `strong-3436392-DROID-BRIDGE-REGISTER` | `rig-meta` | 8 | **NO** — writer rejected |
| `strong-3436392-FORGE-PRIMARY-GITEA` | `ci-infra` | 8 | YES (4 distinct run_ids, written twice each) |

**Guard #1 (writer):** `enqueue-capture.sh:77` `VALID_WORK_CLASSES` does not contain
`rig-meta` (the brief-declared class of the other two tickets, `state/agent-briefs/
strong-3436392-{LENS-REGISTRY-AND-REPORT,DROID-BRIDGE-REGISTER}.md:57`). Those 16
enqueues exited 1 at `enqueue-capture.sh:105` and never created a spool file. `cap()`
swallows the failure (`|| true`, `charon-run.sh:84`), so the run log shows nothing.

### `strong-4010362` — ZERO false BLOCKs

All 9 of its ledger events are `capped-filter-unavailable` / `DETAINED (fail closed, no
spill-up)` at 05:24:0[2-6]Z. It never reached `charon-run.sh`, so `cap()` was never
called. The brief's "then a gateway-token failure" is correct as a *cause* but it
manifested **before** dispatch, at the capped-exclusion preflight, which failed closed
correctly. **No scorecard damage from run 2.**

### Genuine vs false — kept separate

Of the 24: **24 false (infra), 0 genuine.** Every one is `rc=127 / opencode binary absent
from PATH`. There is no model-attributable failure anywhere in run `strong-3436392` —
no model was ever contacted.

---

## 3. Already folded into `model-scorecard.tsv`? — NO. Decisive proof.

**Guard #2 (daemon), `grader-daemon.py:630-632`** — the FLAW-3 unpaired-FINAL provenance
check:

```python
if not paired and not _model_used_matches(stored_ref, stored_model):
    log(f"capture: REJECTED unpaired FINAL {run_id} -- model {stored_model!r} not confirmed by state/model-used/{stored_ref}")
    return False
```

Because `opencode` never ran, no PROVISIONAL was ever stored (`cap` with a verdict skips
the provisional stage), and `fleet/state/model-used/<ref>` was never written. Verified by
execution — all six candidate ref spellings ABSENT:

```
ABSENT DROID-BRIDGE-REGISTER          ABSENT strong-3436392-DROID-BRIDGE-REGISTER
ABSENT FORGE-PRIMARY-GITEA            ABSENT strong-3436392-FORGE-PRIMARY-GITEA
ABSENT LENS-REGISTRY-AND-REPORT       ABSENT strong-3436392-LENS-REGISTRY-AND-REPORT
```

The daemon's own result files in the world-readable `res/` spool state the outcome
explicitly — `/var/lib/bench-grader/spool/res/capture-<model>-FORGE-PRIMARY-GITEA.json`,
all four, written 2026-07-24T22:15:09Z local:

```json
{ "run_id": "capture-glm-5.2-FORGE-PRIMARY-GITEA", "model": "glm-5.2",
  "unit_id": "CAPTURE-FORGE-PRIMARY-GITEA", "kind": "capture",
  "success": true, "appended": false, "record": {} }
```

`"appended": false` is `_handle_capture()`'s return value — **no ledger row was written.**

Corroborating negative checks (both run, both zero):

```
grep -qE 'DROID-BRIDGE-REGISTER|FORGE-PRIMARY-GITEA|LENS-REGISTRY-AND-REPORT' model-scorecard.tsv  -> ZERO MATCHES
grep -qE 'DROID-BRIDGE-REGISTER|FORGE-PRIMARY-GITEA|LENS-REGISTRY-AND-REPORT' scorecard.v1.json    -> ZERO MATCHES
```

### Current standing of the four models (live `model-scorecard.tsv`, 65 rows)

| model | total rows | BLOCK rows | ci-infra n / block | detention status (all work_classes) |
|---|---|---|---|---|
| minimax-m3-free | 17+ | **0** | 17 / 0 | OK |
| deepseek-v4-flash | 15+ | 1 (`MODEL-GRADE-PRESEED`, rc=1 — see §5) | 10 / 0 | OK |
| glm-5.2 | 10+ | **0** | 5 / 0 | OK |
| gpt-5.4-mini | 1 | **0** | 1 / 0 | OK |

`./model-detention.sh detained <wc>` returns **empty** for `ci-infra`, `money-path`,
`routing`, `greenfield-feature`, `refactor`, `bugfix`, `tests`. `check <model> <wc>`
exits 0 (eligible) for all four models. Run, not read.

---

## 4. Blast radius

**Nothing downstream is consuming a degraded ranking. A droid launched right now is NOT
steered away from these four models.**

| consumer | reads | state now | would it have been affected? |
|---|---|---|---|
| `fleet/model-detention.sh` | `model-scorecard.tsv` | all classes OK, no detentions | see near-miss below |
| `fleet/fleet-droid.sh:115-128` `detention_filter_chain` | `model-detention.sh` | full chain kept | **only HARD drops a model.** HARD requires FABRICATION (`gate=pass AND verdict=BLOCK`, `model-detention.sh:52`). These rows are `gate=fail` → they can **never** produce HARD, only ADVISORY, which *keeps* the model in the chain with a warning (`:122`). Ceiling of the damage is a loud warning, not exclusion. |
| `fleet/capability/grades.py` | `model-scorecard.tsv` | `grade()` returns `None` for **every** model incl. `deepseek-v4-pro`, `kimi-k2.6`, `strong-control` | no — see separate red below |
| `fleet/capability/assign.py:319` | `grades.grade()` | receives `None` for everything | no |
| `fleet/tier-models.tsv:54` | static file, **not** scorecard-derived | `strong` = `minimax-m3-free,deepseek-v4-flash,glm-5.2,gpt-5.4-mini` | no — a chain change requires editing this file |

### Near-miss, quantified

Had the 8 spooled entries merged, the counterfactual detention math
(`model-detention.sh:_status_for`, ≥50 % block over n≥3) is:

| model | ci-infra now | +2 BLOCK | block % | outcome |
|---|---|---|---|---|
| minimax-m3-free | n=17 b=0 | n=19 b=2 | 10 % | OK |
| deepseek-v4-flash | n=10 b=0 | n=12 b=2 | 16 % | OK |
| glm-5.2 | n=5 b=0 | n=7 b=2 | 28 % | OK |
| **gpt-5.4-mini** | **n=1 b=0** | **n=3 b=2** | **66 %** | **ADVISORY-DETAINED** |

`gpt-5.4-mini` has exactly **one** scorecard row, so two false BLOCKs would have flipped
it advisory-detained on `ci-infra` on the spot. The thin-evidence models are the ones
this defect can actually move.

### Separate pre-existing red (NOT this defect, reported not fixed)

`capability/grades.py` returns `None` for **every** model × **every** work_class,
including the designated controls. The EVAL-PROMOTION-GATE admission gate
(`grades.py:44-60`) admits nothing, so the whole real-outcome grading layer feeding
`assign.py` is currently **inert**. This is consistent with memory
`charon-eval-system-under-repair`. It is *why* the false BLOCKs could not have reached
assignment — but it is a red in its own right and should not be counted as protection.

---

## 5. The CLASS — every infra exit code that can be mis-booked as a model BLOCK

`is_infra_fault()` is a **text-first predicate with a single rc special-case**. Its regex
(`charon-run.sh:61-63`) matches 5xx / bad gateway / service unavailable / gateway timeout
/ connection reset|refused / econnreset|econnrefused / context deadline exceeded /
database is locked / UnknownError / internal server error. **Any fault whose only
signature is an EXIT CODE, or whose text is not in that list, is booked as a model
BLOCK.** rc=127 is one instance of that class.

Full enumeration against what `( cd "$CWD" && timeout ${T} opencode run … )` can produce:

| rc | meaning | today | correct |
|---|---|---|---|
| 0 | success | SUCCESS | ok |
| 1 | opencode generic error — **incl. auth failures (401/403, invalid/expired API key, unauthorized)** and `cd "$CWD"` failing on a reaped worktree | **BLOCK** | ambiguous: infra unless the tail carries model output |
| 2 | CLI usage error / shell misuse | **BLOCK** | INFRA |
| 3 | opaque UnknownError | infra (handled, `:60`) | ok |
| 124 | `timeout` fired | handled 3-way (`:125-180`) | ok |
| 125 | **`timeout` itself failed** | **BLOCK** | INFRA — 6 observed in ledger |
| 126 | binary found but **not executable** (perm denied) | **BLOCK** | INFRA |
| 127 | **binary not found** | **BLOCK** | INFRA — 24 observed, this incident |
| 130 | SIGINT (128+2) — Ctrl-C, session kill | **BLOCK** | INFRA |
| 131 | SIGQUIT | **BLOCK** | INFRA |
| 132 | SIGILL (128+4) | **BLOCK** | INFRA — **4 observed** 2026-07-16 |
| 134 | SIGABRT (128+6) — node/bun abort, V8 OOM | **BLOCK** | INFRA — **18 observed** 2026-07-16 |
| 135 | SIGBUS | **BLOCK** | INFRA |
| 137 | SIGKILL (128+9) — **OOM-killer**, `kill -9` | **BLOCK** | INFRA |
| 139 | SIGSEGV (128+11) | **BLOCK** | INFRA |
| 141 | SIGPIPE | **BLOCK** | INFRA |
| 143 | SIGTERM (128+15) — systemd stop, droid reap | **BLOCK** | INFRA |

Historical `error-failover` rc histogram over the whole ledger, excluding the
`job=out`/`model=my-model` test harness rows:

```
   5  rc=1     24  rc=127     4  rc=132    18  rc=134
```

**→ 46 real BLOCK enqueues in the ledger's lifetime; 42 of them (127/132/134) are
provably infra.**

### ONE already-merged false BLOCK from this class

`fleet/model-scorecard.tsv:36`:

```
2026-07-16	live	FLEET-DEMAND-DRIVEN-ROUTING	routing	-	kimi-k2.6	BLOCK	fail	0	-	-	-	ref=…; evidence=opencode exited rc=134 (non-limit, non-infra failure, self-evident at run time)	-	-	active
```

`rc=134` is SIGABRT — the `opencode`/node process **crashed**. That is never a model-quality
signal. It merged (unlike today's batch) because a `state/model-used/` anchor existed for
that ref. The other 21 signal-death enqueues of 2026-07-16 did not merge.

**Its live effect:** `kimi-k2.6` × `routing` currently has n=3, block=1 → 33 %, status OK.
One more `routing` BLOCK takes it to 2/4 = 50 % → **ADVISORY**. The row is a half-loaded
gun, not currently firing.

### The class fix (recommendation only — I changed nothing)

Two lines in `is_infra_fault`, plus one non-vacuity guard that **reuses a primitive
already in the same file**:

1. rc allowlist — `case "$rc" in 3|125|126|127) return 0 ;; esac` and
   `[ "$rc" -ge 128 ] && [ "$rc" -le 165 ] && return 0`.
2. add auth terms to the regex: `401|403|unauthorized|invalid api key|authentication|api key`.
3. **the real class fix:** never `cap … BLOCK` when the attempt produced **zero model
   output**. The rc=124 branch already computes exactly this (`OPCODE_TAIL`,
   `charon-run.sh:170-171`) — hoist it. A fault with no model output cannot be a
   model-quality verdict, whatever the exit code. This closes the class instead of
   adding rc=127 to a list that will be incomplete again next week.

Belongs as an extension of `charon-run.sh` + a case in the existing
`benchmark/lib/dogfood-attribution.sh` taxonomy. **No new script.**

---

## 6. OPERATOR REMEDIATION — exact commands

The grader runs as its own unix user; the operator executes these, the audit did not.
Run from any cwd. **A → B are verification/cleanup for this incident; C → D concern the
already-merged row and are an operator decision.**

### A. Confirm what is actually left in the spool (settles the one thing I could not read)

```bash
sudo -u bench-grader ls -la /var/lib/bench-grader/spool/req | grep -E 'FORGE-PRIMARY-GITEA|LENS-REGISTRY-AND-REPORT|DROID-BRIDGE-REGISTER'
```

Expected: **no output.** The daemon owns the `req/` directory, and the sticky bit permits
the *directory owner* to unlink, so `_delete_req_safe` (`grader-daemon.py:926-936`)
should have removed them despite its comment claiming otherwise. If rows DO appear,
run B — otherwise B is a no-op and nothing further is needed for the four models.

### B. Drop any surviving stale capture requests for this incident

```bash
sudo -u bench-grader find /var/lib/bench-grader/spool/req -maxdepth 1 -name 'capture-*-FORGE-PRIMARY-GITEA.active.*.json' -newermt '2026-07-25 05:00' ! -newermt '2026-07-25 05:30' -print -delete
```

**Why this matters even though nothing merged:** the daemon's `seen` set is in-memory. If
monit restarts it (`watchdog/monit.d/grader-daemon.conf` restarts on a 5400 s scorecard
staleness) *and* a later successful run writes `state/model-used/FORGE-PRIMARY-GITEA`
naming one of these four models, the stale FINAL would then **pass** the provenance guard
and land as a real BLOCK. Deleting the files removes that latent path.

### C. Back up the ledger before touching the already-merged row (§5)

```bash
sudo -u bench-grader cp -a /home/stack/charon-private/fleet/model-scorecard.tsv \
  /home/stack/charon-private/fleet/model-scorecard.tsv.bak-$(date -u +%Y%m%dT%H%M%SZ)
```

### D. Remove the merged false BLOCK — `kimi-k2.6` / rc=134 / SIGABRT (OPERATOR DECISION)

Removing a row from a grader-owned ledger is a policy call, not an audit finding. Only
after C, and only if the operator accepts that a SIGABRT crash is not a model verdict:

```bash
sudo -u bench-grader sed -i '/^2026-07-16\tlive\tFLEET-DEMAND-DRIVEN-ROUTING\trouting\t-\tkimi-k2\.6\tBLOCK\tfail\t0\t/d' \
  /home/stack/charon-private/fleet/model-scorecard.tsv
# verify: expect 64 rows and exactly ONE remaining BLOCK (deepseek-v4-flash / MODEL-GRADE-PRESEED)
wc -l /home/stack/charon-private/fleet/model-scorecard.tsv
awk -F'\t' '$7=="BLOCK"' /home/stack/charon-private/fleet/model-scorecard.tsv | cut -f3,6,7
```

The remaining BLOCK — `deepseek-v4-flash` / `MODEL-GRADE-PRESEED` / `rc=1`
(`model-scorecard.tsv:55`) — is **left alone deliberately**: `rc=1` is genuinely ambiguous
(could be model failure, could be auth), and the ledger does not record enough to
classify it. Do not delete it.

### E. Nothing to do for the four models

No row for `minimax-m3-free`, `deepseek-v4-flash`, `glm-5.2` or `gpt-5.4-mini` from
`strong-3436392` exists in `model-scorecard.tsv` or `scorecard.v1.json`. No revert, no
parole, no re-grade needed.

---

## What was proved by EXECUTION vs by READING

- **Executed:** spool/ledger/scorecard permission + content checks; `model-detention.sh
  check/detained` for 4 models × 7 work_classes; `capability/grades.py` `grade()` for 8
  models; ledger rc histograms; `res/` result-file inspection (`"appended": false`);
  counterfactual detention math; `state/model-used/` presence checks.
- **Read only:** `charon-run.sh` branch structure, `grader-daemon.py` guard logic,
  `enqueue-capture.sh` validation, `fleet-droid.sh:detention_filter_chain`. The rc=127 →
  BLOCK-branch path is nonetheless *execution*-proved by the production run log line,
  which only that branch emits.
- **Could not do:** enumerate `/var/lib/bench-grader/spool/req` (write-only maildrop for
  `stack`) or read `spool/work/` (mode 0700). Command A hands that to the operator.
  I did not attempt to read either as another user.
