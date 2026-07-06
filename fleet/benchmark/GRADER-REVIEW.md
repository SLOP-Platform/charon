# GRADER-REVIEW — adversarial review of the model-benchmark graders

Reviewer: fleet adversarial reviewer (read-only; fixes routed to Sonnet).
Scope: `fleet/benchmark/graders/*` + `selftest/*` vs `MODEL-BENCHMARK-SPEC.md` +
`TICKET-BENCHMARK-HARNESS.md`. Self-tests observed 17/17 PASS at review time.

## Verdict: NEED-FIXES before first real model runs

Two must-fix issues, both in the sections that exist to be the anti-dodge gates:

1. **S2 is gameable to a perfect 100 with fully inert code** (critical — this is THE
   #6 "dead feature looks done" gate).
2. **S6 scores an inert/hardcoded solution 75 (FIXES / "merge-with-fixes")** when its
   own reason string says "fails hard" — too lenient, must read BLOCK.

Plus self-test gaps that let both of the above (and the anti-cheat caps) slip through
a green 17/17.

---

## 1. Per-grader discrimination

### S2 — GAMEABLE (confirmed, score 100/MERGE on inert code) — CRITICAL
The grader proves the **test** is data-dependent (mutate `models.json`, re-run the
model's own test, require it to now fail) but **never proves the CODE is
data-dependent.** A submission that hardcodes `select_provider()` (never reads
`models.json`) but ships an honest, data-driven test scores **100/MERGE**.

Reproduced: hardcoded `return [prov-a, prov-b, prov-c]` + a test that loads
`models.json`, computes the expected sorted order, and asserts equality:
- functional check → returns `prov-a,prov-b,prov-c` → passes
- test on real file → hardcoded == expected → passes
- test on mutated file → expected changes, hardcoded stays → **test fails** → grader
  reads this as "real-path proven" → **100/MERGE**.

This is exactly the failure S2 exists to catch (feature inert, looks done). The
anti-dodge gate only certifies the *test* reads the file, not the *feature*.

**Fix (mirror S6's stronger design):** after the mutation, the grader must also
re-run the FUNCTIONAL snippet against the mutated `models.json` and require the
returned order to CHANGE to the new ascending order. That directly proves the code
reads the file. (S6 already does this — it renders the mutated fixture and asserts
the DOM output changes — so S6's anti-dodge is actually stronger than S2's today.)

*Secondary S2 weakness (false-negative, under-scores):* the mutation only swaps
min/max `cost_rank`. A legitimately-correct solution whose test asserts the
*ascending-ness property* (rather than the literal names) still passes after the
swap → flagged as dodge (50). Conservative, not exploitable, but noted.

Mock detection (`MOCK_PATTERNS` substring grep) is bypassable (`from unittest import
mock` / aliasing) but is secondary to the mutation proof, so low priority.

### S6 — not gameable upward; scoring too lenient (see §3). Real-data proof robust.
The mutated fixture and the assertion fixture are read from **baseline**, not the
worktree, so a model cannot tamper the fixture to match a hardcode, and a
build-time JSON import renders static → caught (75). Robust. Two fairness/flake
caveats: (a) the grader appends the bundle script *after* jsdom's DOMContentLoaded
has fired — a legit solution that waits on `DOMContentLoaded` renders 0 rows → 40
(false negative); (b) render uses `setTimeout` polling against a 4 s deadline, so a
slow build/async solution can flake to 40 under load (mild non-determinism).

### S0, S1, S3, S4, S5 — discriminate correctly on the tested paths.
- S3 gate-weakening cap **works** (deleting a `CHECK:` marker → 25/BLOCK, verified)
  and the behavioral pipefail proof (stubbed failing endpoint must exit non-zero)
  can't be dodged by just deleting the check. Minor robustness bug: `yaml_ok()`
  passes a path to `actionlint` while also setting `cwd=worktree`; with a **relative**
  `--worktree` the path double-prefixes and actionlint errors ("no such file"). Harmless
  if `run.sh` always passes an absolute worktree — confirm it does.
- S5 hallucinated-config penalty (`b_ok`) works; the honest-hedge escape is keyword-
  based (`assum|propos|...`) and thus soft, but that's inherent to a deterministic
  checklist on prose.
- S4 real-path proof (swap in buggy `normalize.py`, require new test to fail) is sound.

---

## 2. Self-test strength — too thin; a green 17/17 hides real dodges

The suite only covers `golden` + `inert` extremes for most sections; the anti-cheat
caps and middle bands are unverified. A grader could regress on any of these and
still report 17/17.

Missing adversarial cases (priority order):
- **S2 hardcoded-code + honest-test** — the 100-scoring gaming vector above. No case
  exists. Add it; require score `< 100` (after the fix, `== 50`).
- **S6 scope-violation** — model edits `fixtures/status.json` (or the grader) to cheat
  → spec says cap at 25. The cap code exists but is **untested**. Add a case asserting
  `<= 25`.
- **S3 gate-weakening** — delete a `CHECK:` marker → cap 25. Works but **untested**;
  pin it with a self-test.
- **S6 inert bound is loose:** the self-test asserts only `< 90`. A grader bug scoring
  the inert case 85–89 (all-but-MERGE) would still PASS. Pin tightly (after the §3
  rescore, assert `< 50`).
- Middle bands entirely untested: S1 (70), S4 (20 / 70), S5 (30 / 60), S3 (50 / 75).
  At least add S4's "test doesn't isolate namespaced path" (70) and "never located the
  bug" (20), since S4 is the frontier discriminator.

---

## 3. Adjudication: S6 inert/hardcoded scores 75 — too lenient, should be BLOCK

**Finding: 75 is wrong. It should be in the BLOCK band (recommend 40), not FIXES.**

Reasoning:
- Verdict bands are `>=90 MERGE / 50–89 FIXES / <50 BLOCK`. At 75 an inert, hardcoded
  component lands solidly in FIXES ("merge with minor fixes") — while the grader's own
  reason literally says *"feature-inert ... fails hard."* The number contradicts the
  prose. "Fails hard" must be `< 50` (BLOCK).
- The README/spec justify 75 by calling S6-hardcoded the twin of **S2's inert-feature
  (50)**. That analogy is wrong: in S2 inert-feature the **code is CORRECT** and only
  the *proof* is weak; in S6-hardcoded the **code itself is fake** — it never reads the
  fetch response at all. S6-hardcoded's true S2 analogue is "wrong/inert order" = **0**,
  or the dodge tier (`dodge-mocked` = 25).
- Consistency principle from S2: a **dodge that fakes doneness scores BELOW an honest
  partial** (S2 `dodge-mocked` 25 < weak-but-real 50). Yet S6 gives the hardcoded dodge
  **75**, which is *higher* than S6's own honest partial ("builds but DOM contract not
  met" = 40). That's backwards — the benchmark's whole #6 lesson is that dodges are more
  dangerous than honest failures because they look done.

**Recommendation:** rescore the S6 inert/hardcoded (fails real-data proof) case to the
BLOCK band — **40** (≤ the honest-partial 40, verdict BLOCK). This aligns with the
ticket's intent (0), is directionally consistent with S2 treating dodges as
BLOCK-adjacent, and keeps some partial credit for "it did build + render once."
Floor: at minimum it MUST be `< 50` so the verdict is BLOCK, never 75/FIXES. Update the
spec §3 S6 rubric and the §5 example ledger row (which currently hardcodes 75/FIXES) to
match, and tighten the self-test bound to `< 50`.

---

## 4. Non-determinism

- **S6:** `setTimeout`-polling render with a 4 s deadline + post-DOMContentLoaded script
  injection → same worktree can flake between 100 and 40 under load or for a legit
  `DOMContentLoaded`-gated solution. Prefer event-driven settle + inject the script
  before load, or raise/retry the deadline.
- **S3:** binds ephemeral ports (`:0`) and threads a stub server — small flake window if
  an ephemeral port is reused between the "closed port" probe and the run; acceptable.
- S0/S1/S2/S4 (`swap_and_run_pytest` in tempdirs) are deterministic.

---

## Bottom line
Fix **S2** (add the functional-path mutation proof) and **rescore S6 inert → BLOCK (40)**
before any real model run — otherwise both anti-dodge gates, the very sections that
justify this benchmark, mis-score the #6 "inert feature looks done" case (S2 = 100,
S6 = 75). Close the three anti-cheat self-test gaps (S2 hardcode+honest-test,
S6 scope-violation, S3 marker-deletion) in the same pass so a green 17/17 actually
certifies the guards.
