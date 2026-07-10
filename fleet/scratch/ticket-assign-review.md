# Adversarial review — #14 ticket-assignment engine (shared capability brain)

Reviewer: read-only pass, no edits/push. `selftest.py` RUN: **all 8 checks PASS, exit 0**
(reproduced locally, not just trusting the report).

## VERDICT: SHIP-WITH-FIXES

Engineering is solid and unusually honest. Interface seam is clean, D&S gate is
correct, blast radius is rig-only, and the two known gaps are disclosed rather than
hidden. The one substantive issue is the **grade math's small-N over-trust** — and it
matters *more* here than usual because grades.py is the shared brain the gateway
routing will inherit, and today's data is almost entirely n=1.

---

## Q1 — Grades scoring soundness: the real problem

`score = merge% − block%` is a defensible *direction*, and routing FIXES→0 (partial
credit, not a clean win) is a good call. **But there is no min-sample floor / confidence
shrinkage, and the data is n=1 in almost every cell** (verified: every model×work_class
has exactly 1 row except glm-5.2/routing which has 3). Consequences on REAL data:

- With n=1, `score` collapses to the single verdict: 100 (MERGE), 0 (FIXES), −100 (BLOCK).
  A single lucky MERGE is indistinguishable from a 20/20 MERGE record.
- **Demonstrated inversion:** glm-5.2/routing has n=3 with a *real observed BLOCK*
  (score 33.3) and ranks **below** kimi/gpt/hy3 which each have n=1 MERGE (score 100).
  More evidence + a real failure → *lower* rank. That is exactly the MIN_FIELD_SIZE
  small-N trap the benchmark-v2 math review flagged, reproduced here.
- `n` is carried on `Grade` and shown in the summary, but the ranking never uses it and
  the rationale never warns on low n → **silent over-trust**, not just an untuned knob.

No-data-for-class → generalist aggregate (flagged `fallback_used`), which is honest, but
it is then ranked head-to-head against direct-class scores as an equal — mild
apples/oranges. Ties: deterministic chain (bench→cost→time→id), fine.

## Q2 — Interface abstraction: clean, genuine swap

`assign()` only touches `GradesProvider.grade()/all_models()` and generic `Grade` rank
keys (score, mean_bench_score, mean_cost_usd, mean_time_s). No scorecard specifics leak
into assign(). A future pools grades-table provider swaps with zero caller change. Watch
item: `Grade`'s merge/block/fixes/n fields are scorecard-shaped — the future provider
must synthesize them or the score formula moves into it. Seam is right; the *formula's*
home is the thing to get right (see Q1).

## Q3 — assign() logic: sound, honest

Blockers → `refused` returned *first*, before any grading/pick. Never assigns a blocked
ticket. Excluded-but-higher-scoring models are surfaced in the rationale
(`NOTE: X scored >= pick but was EXCLUDED`), so it never silently picks a worse model
without showing why. Good.

## Q4 — Proof-of-effect gate: real but data-coupled

It genuinely proves differentiation (3 distinct winners), the BLOCK-penalty (money-path
ranks hy3 last), availability-changes-pick, and D&S refusal — and would catch a
regression to "everyone → same model" via the ≥2-distinct check. **Weaknesses:** (a) the
pinned assertions (`ci-infra==glm-5.2`, money-path ranking) run against the *live*
`model-scorecard.tsv`, so appending real rows can false-fail the gate and can't separate
a code regression from a data change — freeze a fixture TSV. (b) No coverage of the
tier-exclusion path or the generalist-fallback path.

## Q5 — Two known gaps: correctly scoped, honestly surfaced

Both disclosed in report + docstrings. work_class-absent prints a NOTE and defaults to
generalist (not a silent misassign). Live-availability is wired but inert today (no
model-tagged sessions); the selftest itself prints the injected-fake caveat rather than
faking a live assertion. This is genuinely honest — no overclaim of "fully automatic."

## Q6 — Blast radius: rig-only, safe

All files under `fleet/`; only src/ touch is a read-only `import charon.model_catalog`
wrapped in try/except. Confirmed no writes. Nit: `sys.path.insert(0, charon/src)` is a
global mutation that could shadow bare-name imports — low risk in this standalone CLI.

(Note: `assign.sh` lives at `fleet/assign.sh`, not `fleet/capability/assign.sh` as the
brief's path implied — the wrapper exists and is correct.)

---

## Must-fix before landing
1. **Small-N over-trust (blocker before the GATEWAY consumer inherits grades.py; for the
   rig-assignment MVP, at minimum surface + ticket).** Add a min-sample floor or
   confidence shrinkage (Laplace/Wilson lower bound) so n=1 100% doesn't outrank an
   n=3 model with a real BLOCK, and expose a LOW-CONFIDENCE flag on `Grade` + in the
   rationale so neither consumer silently over-trusts one sample. Same trap benchmark-v2
   flagged.

## Should-fix
2. Freeze a fixture TSV for selftest's pinned assertions (currently coupled to live data)
   and add tier-exclusion + generalist-fallback coverage.
3. Give the generalist fallback a small penalty or segregate it from direct-class scores
   in ranking (currently compared as equals).

## Defer / nits
4. Lockstep test for the bash↔Python duplications (WORK_CLASSES, tier aliases, TSV column
   layout); grades.py's opus/sonnet/haiku aliases are extra vs config's _LEGACY_ALIASES.
5. sys.path bare-name shadow risk.
