# REDS + ARM STATUS — session agen-kolar (2026-07-24)

## ARM STATUS: **DISARMED** (unambiguous)

The rig merge gate is **NOT armed**. I made **zero** file edits this session.

- `LAND_RIG_TESTS` does **not exist on master** at all. `git grep LAND_RIG_TESTS master -- fleet/land.sh`
  returns nothing.
- It exists ONLY on the unlanded branch `fix/land-gate-rig-suite` @ `506caa1`, at
  `fleet/land.sh:321`, still `[ "${LAND_RIG_TESTS:-0}" = "1" ]` — **default 0 = DISABLED**.
- `git status --porcelain -- fleet/land.sh fleet/tests/ fleet/benchmark/ fleet/handoff-check.sh`
  is empty: I modified none of them.

No disarm was necessary because no arm ever happened. Rig landing is unaffected by this session.

**Do not arm.** The precondition (green gate on master) is far from met — see below.

---

## THE BRIEF'S BASELINE DOES NOT REPRODUCE

| | brief | actually measured |
|---|---|---|
| master | `dfdcc22` | `c155a82` |
| gate | 76 pass / **2 fail** | 68 pass / **10 fail** |
| total suites | 78 | 78 |

Verified by execution (`bash fleet/gate.sh`), **three runs, identical result each time** — so this
is stable, not flaky-at-the-summary-level.

`dfdcc22..c155a82` is **board-hygiene commits only** — no fleet script changed. So master's
movement did **not** cause the 8 extra reds. The brief's 76/2 figure could not be reproduced at
either the stated SHA's descendants or the current head; treat 76/2 as stale/unverified.

## THE 8 EXTRA REDS ARE REAL, NOT LOAD FLAKES

This is the most important finding and it **invalidates the brief's plan**. Failing suites, each
re-run **standalone** (no gate load):

| suite | standalone rc | verdict |
|---|---|---|
| assign-dispatch.test.sh | 1 | REAL red |
| capture-wiring.test.sh | 1 | REAL red |
| handoff-generated-state.test.sh | 1 | REAL red |
| handoff-mechanize.test.sh | 1 | REAL red (brief's RED 1) |
| promotion-gate.test.sh | 1 | REAL red |
| selfcheck-cycle.test.sh | 1 | REAL red |
| submit-checkin.test.sh | 1 | REAL red |
| w0b-harden.test.sh | 1 | REAL red |
| **reconcile-merged.test.sh** | **0** | load-sensitive only (brief's RED 2) |

Only `reconcile-merged` is a load artefact. The other eight fail on an idle box. The brief scoped
this session to "the last 2 gate reds"; there are in fact **9 failing suites, 8 of them genuine**.
Arming the gate now would halt all rig landing on eight standing reds.

---

## RED 1 — handoff-mechanize: **UNTOUCHED**

Not started (session budget exhausted during baseline verification). No worktree created, no edit
made. Branch `fix/handoff-gotcha-verifiable` @ `83aff37` still exists; no worktree is checked out
for it.

Note: b2/c1 fail on **master's own gate run**, not only on that branch. Verbatim from master:

```
FAIL: b2 the failure did not name 'gotchas' as missing
FAIL: c1 stripped-copy STILL FAILS the broken fixture -> the [gotchas] check appears REDUNDANT
     (some other check catches it) — review whether the check is really load-bearing or duplicate
     the assertion in another needle
```

The brief's diagnosis (document-wide `GOTCHA|avoid|DENIED` needle instead of section-scoped) is
consistent with the c1 text and is a reasonable starting hypothesis — but it is **unverified by
me**. Fix remains: scope the needle to the `[gotchas]` section, then confirm c1 genuinely goes RED
on a stripped copy.

## RED 2 — reconcile-merged: **UNTOUCHED, and the brief's numbers are wrong**

The brief says "1909ms vs a 1900ms bound ... standalone 15/15 PASS at 1419ms". None of those
numbers are in the file. Measured reality:

- The assertion is `fleet/tests/reconcile-merged.test.sh:145`, bound **5000ms**, not 1900ms.
- Standalone: **14 passed, 0 failed**, at **3594ms** — PASS.
- Under gate load: **6816ms** — FAIL.

So the *diagnosis* (a hand-typed constant overtaken by real load) is right, but the specific
figures in the brief are not from this checkout.

### ROOT CAUSE (found, not fixed) — this is the class defect

`fleet/gate.sh:44-50` forks **every** suite concurrently with **no concurrency cap**:

```sh
for test_file in "${tests[@]}"; do
  ( rc=0; bash "$test_file" >... || rc=$?; echo "$rc" >... ) &
  pids+=("$!")
done
```

78 suites launched at once on a 16-core box. The wall-clock any timing assertion sees is a
function of *how many other suites happen to be running*, which no per-test constant can encode.
Raising the 5000ms constant treats the symptom. The class fix is a **concurrency cap** in
`gate.sh` (e.g. bounded to `nproc`), which makes every timing assertion in the suite reproducible
at once. Other suites carrying timing/perf assertions, and therefore exposed to the same defect:
`reconcile-held-markers`, `parked-semantics`, `leak-guard-salvage`, `service-watchdog`, `spill-up`.

### Can `budget-derive.py` serve the other perf assertions? — **NO, not as built**

I read the whole tool. Answer is negative, and the brief's premise here is mistaken:

- It derives budgets in **seconds of LLM wall-clock**, keyed `(canonical_work_class, difficulty)`,
  for the **model-eval pipeline** (DETAIN/too-slow decisions on model runs).
- Its inputs are `model-scorecard.tsv`, dogfood `*-SUMMARY.md` result cards, and `LEG-RANK.tsv` —
  all records of *model* runs. It has **no input channel for shell-test fixture timings**.
- The reconcile-merged assertion is a **millisecond CPU budget for a bash fixture**. There is no
  work_class, no difficulty, no tok_s, no scorecard row for it.

Wiring it in would mean inventing a new timings data source and a new key space — i.e. building a
second tool, not calling the existing one. That is a genuine finding, not an evasion: **the "zero
callers" observation is correct, but the reason it has zero callers here is that it solves a
different problem.** What *is* reusable is the **rule** (p95 × 1.5 over observed good runs), not
the module. Recommended: cap gate concurrency first (removes the variance at source), and only
then, if timing assertions still need calibration, apply the p95×1.5 rule to recorded run times.

---

## RESUME ORDER FOR THE NEXT SESSION

1. **Do not arm.** Precondition is a green gate; it is 68/10.
2. Re-baseline: the brief's 76/2 is not real. Start from 68/10 at `c155a82`.
3. Triage the 8 genuine reds — they are unowned by any brief and nobody has looked at them.
4. Cap concurrency in `fleet/gate.sh` (class fix) — this alone should clear `reconcile-merged`.
5. Then `handoff-mechanize`'s section-scoped needle.
6. Arm `LAND_RIG_TESTS` only after a genuinely green `bash fleet/gate.sh` on master, and
   red-proof it by execution (red suite -> rc=4 nothing pushed; green suite -> proceeds).

## VERIFIED BY EXECUTION vs BY READING

- **By execution:** gate 68/10 stable over 3 runs; all 9 failing suites re-run standalone;
  reconcile-merged standalone 14/14 at 3594ms; box load 2.67/16 cores.
- **By reading only:** `budget-derive.py`'s input model; `gate.sh`'s unbounded fork loop;
  `LAND_RIG_TESTS` default on `506caa1`; the handoff needle hypothesis.
