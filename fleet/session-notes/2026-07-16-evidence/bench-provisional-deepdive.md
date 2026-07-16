# BENCH-PROVISIONAL-SCORING (#20) — Claude adversarial deep-dive

VERDICT: **DESIGN-NEEDS-REVISION** (its central verdict must be INVERTED)

The design's *facts* are largely accurate (citations spot-check clean). Its
*conclusions* are wrong in a money-path way. It certifies as working
("already BUILT", "No blocker", "#26 unblocked the moment this lands") a
mechanism that is **inert on the live lane**. Acting on it ships untrusted
scores into budget + routing.

---

## 0. The brief's premise is INVERTED (correct the record)

Manager brief: "Every row a tool emits defaults `stage=provisional`."
**FALSE.** Every writer defaults **`active`**:

| Writer | file:line | default |
|---|---|---|
| `model-scorecard.sh cmd_append` | `fleet/model-scorecard.sh:84` | `${CHARON_SCORECARD_STAGE:-active}` |
| `auto_append.py` (fn) | `fleet/capability/auto_append.py:86` | `stage: str = "active"` |
| `auto_append.py` (CLI) | `fleet/capability/auto_append.py:162` | `--stage default="active"` |
| `bench.sh::unit_stage` units.tsv-miss | `fleet/benchmark/bench.sh:88-92` | `END { if(!f) print "active" }` |
| `pipeline.py enqueue-live` | `fleet/benchmark/item-bank/pipeline.py:897` | `--stage default="active"` |
| `grades.py` empty-col reader | `fleet/capability/grades.py:481` | `_ACTIVE_STAGE` |

The design documents this correctly (§4.3, Q2) — and then **DECIDES TO KEEP
it** (Q2 "DECIDED — keep"). That is a direct contradiction of the ticket's
own accept bullet: *"fail-closed default (unknown/unpaired → provisional,
never active)"*. The design endorses fail-OPEN and calls it fail-closed.

---

## 1. PROMOTION RULE: UNSOUND. The live lane can ONLY produce `active`.

`fleet/benchmark/grader-daemon.py:410` — the capture handler hardcodes the
literal `"active"` into column 16:

```python
row = [
    today, "live", ref, work_class, difficulty, model,
    actual_verdict, actual_gate, str(score),
    "-", "-", "-", note, "-", "-", "active",     # <-- line 410
]
```

`_handle_capture` (`grader-daemon.py:452`) **never reads `req["stage"]`**.
Its two-phase protocol keys on `actual_verdict` presence, per its own
docstring:

> - PROVISIONAL (actual_verdict absent/null): store for later pairing.
> - FINAL (actual_verdict present): pair ... append a `source=live` row.

### The root defect the design MISSES: `stage` is OVERLOADED

`stage` means two different things in two subsystems, and nobody noticed:

- **Spool protocol** (`enqueue-capture.sh:46,123`; daemon): a *phase* flag —
  provisional = "don't write yet", active = "write the row now".
- **Ledger column 16** (`grades.py`, `budget-derive.py`): a *trust* axis —
  provisional = "collected but must not steer a live number".

`pipeline.py:601` computes `stage` as a **trust** decision
(`stage = "provisional" if any_unsaturated else "active"` — calibration
debt) and passes it via `--stage`. The daemon reads that same field as a
**phase** flag and then hardcodes the ledger's trust column to `active`.

Consequences:
1. A capture the pipeline marks `provisional` (untrusted, calibration debt)
   still lands `stage=active` — the trust decision is **silently discarded**.
2. There is **no code path** by which the live lane can write a
   `source=live / stage=provisional` row. Only two outcomes exist: row
   dropped (no verdict), or row written **active**.
3. `provisional` rows on the live lane are **not "collected but excluded"**
   (the design's core promise, §2) — they are **never written at all**.

**Ledger proof (`fleet/model-scorecard.tsv`, this box): 46/46 rows are
`live / active`. Zero provisional, ever.** The gate has never excluded a
single row. This is the [[charon-meter-inert]] pattern exactly: wired-looking,
inert in production. (Design says 43 rows — stale.)

### FALSE-SUCCESS is written as trusted

`fleet/tests/test_capture_pipeline.py:160-165` asserts a row with
`verdict=BLOCK`, `gate=fail`, `score=15`, `note` containing `FALSE-SUCCESS`
(a caught model lie, per [[document-model-self-report-lies]]) gets
`r[15] == "active"`. The test **enshrines** unconditional `active`.

That same test is why the gap is invisible: phase-1 spools
`"stage": "provisional"` (:122) but ALSO omits `actual_verdict`. The two
correlate by accident, so the test passes for the wrong reason and proves
nothing about stage handling. **No test anywhere asserts the daemon honors a
requested stage.**

### Enumerated: every path an UNTRUSTED score reaches `active`

| # | Path | Evidence |
|---|---|---|
| 1 | **Daemon hardcode** — every live capture, unconditionally | `grader-daemon.py:410` |
| 2 | **Default value** — any caller omitting the env/flag | `model-scorecard.sh:84`, `auto_append.py:86,162`, `pipeline.py:897` |
| 3 | **Second writer** — `auto_append.py --source live --stage active` bypasses pipeline+daemon+promote.py entirely | `auto_append.py:162` |
| 4 | **Shell CLI** — `model-scorecard.sh append … live …` free-form | `model-scorecard.sh:84` |
| 5 | **Documented manual re-run** — the generated script's OWN header instructs the operator to promote by re-running with `CHARON_SCORECARD_STAGE=active` | `dogfood-to-scorecard.sh:28,112` |
| 6 | **7 ad-hoc scripts** in `fleet/state/scorecard-append-pathc-*.sh` (newest 20260716) — operator-runnable direct appenders | `fleet/state/` |
| 7 | **units.tsv-miss** → active (design's own Q1) | `bench.sh:91` |
| 8 | **run.sh synthetic** — sets NO stage → S0-S6 bench rows default active | `run.sh:140`, 0 hits for `CHARON_SCORECARD_STAGE` |

Path 5 alone falsifies the design's §3: *"Who MAY promote: `promote.py --apply`
and only that tool."* The design even contradicts **itself** — Q6 says "the
operator promotes it manually via `pipeline._enqueue_capture`", while §3 says
only `promote.py`. Both cannot be true; in code, neither is.

### "SOLE writer of source=live" is FALSE

Design §1/§3/§7 lean hard on the F12 "single-capture-path guarantee". Note
this is the **one claim in the whole design with no line citation** — just a
`§`-reference. It is a docstring assertion (`pipeline.py:643`), not an
enforced invariant. Actual `source=live` writers:

- `grader-daemon.py:418`
- `dogfood-to-scorecard.sh:165`
- `reviewer-dogfood.sh:366`
- `auto_append.py` CLI, `model-scorecard.sh` CLI
- 7 × `fleet/state/scorecard-append-pathc-*.sh`

Nothing in code enforces a chokepoint.

---

## 2. STANDING-RULE VIOLATIONS

### [[benchmark-not-a-valid-ranker]] — **VIOLATED, on the money path**

Two conflicting definitions of "real outcome" **under the same variable name**:

```
fleet/capability/grades.py:339      _REAL_OUTCOME_SOURCES = frozenset({"live"})
fleet/benchmark/budget-derive.py:245 _REAL_OUTCOME_SOURCES = {"live", "bench", "bench2"}
```

`budget-derive.py:249-259` gates on the **wide** set:
```python
if cols[_SC_SOURCE] not in _REAL_OUTCOME_SOURCES: return False   # :254
...
stage = cols[_SC_STAGE] if ... else "active"
return stage == "active"                                          # :259
```

So a synthetic **S0-S6 `bench` row** with `verdict=MERGE` is KNOWN-GOOD for
budget. And it reaches `active` trivially: `run.sh:140` appends bench rows
with **no** `CHARON_SCORECARD_STAGE` (grep count 0) → defaults `active`
(`model-scorecard.sh:84`); `units.tsv:18-24` grandfathers S0-S6 `active` anyway.

**Result: synthetic smoke-test scores steer the real p95 budget ceiling.**
The rule says S0-S6 "must never rank models"; here they set spend.

The design **never audits `budget-derive.py`** — despite the ticket naming
budget as the money path, and the manager's brief citing `budget-derive.py:29`
as the canonical consumer. Design §3's consumer table lists only `grades.py`,
`tier_chart.py`, `close_season.py`. Its §7 claim that "a row must pass ALL of
(source allow-list, stage=active, real-only filter, control panel)" is **false
for budget-derive**, which has no live-only filter and no control panel.

### [[scorecard-live-lane-is-the-ledger]] — **RESPECTED**

No parallel ledger. `model-scorecard.tsv` source=live remains the store.
Design Q6 (Path-C stays provisional, promoted after human diff-confirm)
correctly answers the open refinement (2) this memory left deferred. Good.

### [[no-workhorse-finalized]] — **BRUSHES, flag for operator**

`promote.py:81-82` hardcodes `DEFAULT_CONTROL_PASS = "strong-control"` and
`DEFAULT_CONTROL_FAIL = "deepseek-v4-flash"`. These are control roles, not
tier assignments, so not a strict violation — but there is a **circularity**
the design never addresses: unit trust is proven by designated models' scores,
while model grades depend on trusted units. A hardcoded model-quality
assumption sits underneath the promotion gate while "no model is chosen for
any tier". Operator should confirm the control designation is intentional.

### [[latency-is-a-failure-class]] — **RESPECTED**

`dogfood-to-scorecard.sh` emits `gamma-model BLOCK … attribution=too-slow
(latency-budget-exceeded)`; `budget-derive.py:250-251` explicitly excludes the
too-slow tail from raising p95. Correct.

---

## 3. ACCEPT-BULLET SCORING

| accept bullet | verdict | evidence |
|---|---|---|
| Design first: who/what may PROMOTE (trusted OOB/live grade, never self-reported/dogfood), where enforced, fail-closed default, composes with #26 | **NOT-MET** | All four sub-parts are *addressed* but *answered wrongly*: "promote.py only" false (`grader-daemon.py:410`, `dogfood-to-scorecard.sh:112`); fail-closed default is fail-open and Q2 keeps it; #26 composition rests on the false F12 sole-writer premise |
| Rewire grade_state.record + append + bench.sh to carry stage, with fail-on-revert test — provisional NEVER influences budget/routing | **NOT-MET** | Design asserts already-built. Live lane cannot emit provisional at all (`grader-daemon.py:410`); no test asserts the daemon honors requested stage; `budget-derive.py:245` lets synthetic active rows steer budget |
| Decision recorded so #26 can rebase | **PARTIAL** | Recorded and well-organized, but on false premises — #26 would rebase onto a broken contract |

---

## 4. DECOMPOSITION / OVERLAP

- **Not accretion** — design correctly reuses `promote.py`, `grades.py`,
  `units.tsv`, `model-scorecard.sh`. No new subsystem. Credit where due.
- **PR #85 (EVAL-PROMOTION-GATE, MERGED)** — `promote.py` + `grades.py` +
  `promotion-gate.test.sh`. Design treats F10/F13 as landed; **consistent**,
  no contradiction.
- **PR #99 (TSV-APPEND-UNIFY, OPEN)** — makes `auto_append.py` delegate to
  `model-scorecard.sh`. **Directly overlaps** the dual-writer problem (paths
  3+4 above) and is the right direction, but the design **never mentions
  #99**. Any stage-default change must coordinate with #99 or the two will
  collide on `auto_append.py` + `model-scorecard.sh`.
- **Duplication found:** the two `_REAL_OUTCOME_SOURCES` definitions (§2
  above) are a genuine same-name/different-value trap.

---

## 5. IS THE DESIGN REAL? — Yes, but credulous

Not fabricated. It is a real 425-line doc; spot-checked citations
(`model-scorecard.sh:77-85`→84 ✓, `grades.py:481` ✓, `bench.sh:79-92` ✓,
`units.tsv:1-24` ✓, `promote.py:1-82` ✓) are accurate. The droid read the
code.

Its failure is **method, not honesty**: it verified that the plumbing *exists*
and trusted each module's **docstring** for what the plumbing *does*. It never
traced a row end-to-end through the daemon, and never opened `budget-derive.py`.
The one claim it could not cite by line (F12 sole-writer) is precisely the one
that is false — a reliable tell. Per [[confirm-dont-trust-documentation]], it
recommended from docstrings, not facts.

Crash debris `bc15076` swept in `fleet/board/REVIEWER-DOGFOOD-REDS.md` —
outside `owns:`. Not part of the design; split it out.

---

## 6. WHAT TO DO

Keep §1 (inventory), §2 (state machine), §3's two-axis concept. **Invert the
verdict** from "built, no blocker" to "wired but inert on the live lane".
Add the phase-vs-trust demux, the budget-derive audit, and a writer census.

### Build tickets implied

1. **STAGE-DEMUX** *(money-path, do first)* — split the spool `phase` field
   from the ledger `stage` (trust) field; daemon must persist the requested
   stage instead of `grader-daemon.py:410`'s hardcode. Fail-on-revert test:
   spool `--stage provisional` + a real verdict ⇒ row lands `provisional` and
   is excluded from grades/budget. This is what makes #20's accept true.
2. **STAGE-FAILCLOSED** — flip default `active`→`provisional` across
   `model-scorecard.sh:84`, `auto_append.py:86,162`, `bench.sh:91`,
   `pipeline.py:897`, `enqueue-capture.sh`. Keep the legacy <16-col reader
   defaulting `active` (Q2 is right about history). **Sequence with PR #99.**
3. **BUDGET-SOURCE-RECONCILE** *(money-path)* — `budget-derive.py:245`
   admits `bench`/`bench2`; either narrow to `{"live"}` or have the operator
   justify. Rename one of the colliding `_REAL_OUTCOME_SOURCES`.
4. **RUNSH-STAGE** — `run.sh:140` sets no stage; synthetic S0-S6 rows land
   `active`. Fold into #2.
5. **WRITER-CHOKEPOINT** — enforce the F12 claim in code or delete the claim.
   Retire/relocate the 7 `fleet/state/scorecard-append-pathc-*.sh` ad-hoc
   writers. Fold into PR #99.
6. **FALSE-SUCCESS-STAGE** — decide whether a caught `FALSE-SUCCESS` row is
   trustworthy enough to be `active` (`test_capture_pipeline.py:165`).

### #26 (BENCH-OOB-GRADING) sequencing

The design says #26 is unblocked on sign-off. **It is not.** #26's whole
premise is that the OOB grader's verdict is what earns `active` — but the
daemon writes `active` regardless of who graded, so #26 would land on a
contract that cannot distinguish it. **STAGE-DEMUX must land before #26
rebases**, or #26 inherits a trust axis that is inert.

---

## 7. Unblocks

Correcting this design + landing STAGE-DEMUX/STAGE-FAILCLOSED unblocks
**BENCH-OOB-GRADING (#26)** → **MODEL-PREFLIGHT** + **GRADER-SECFIX-RECONCILE**.
BUDGET-SOURCE-RECONCILE is independently urgent: synthetic scores are steering
real spend **today**, and does not need to wait on #26.
