# Doc-update: workhorse-scrub + quality-equivalent tier-redundancy rule

Date: 2026-07-08 · DOCS-ONLY (no board `owns` changes, no commit).

---

## TASK 1 — Scrub the stale "gpt-5.4 is the workhorse" assumption

**Finding:** the stale framing does NOT live in `fleet/` — it lives in top-level
`/home/stack/charon-private/scratch/` (the cost-analysis working docs). The `fleet/`
"workhorse" hits are unrelated: they are role/tier-slot labels for the *open-model bulk
workhorse* (DeepSeek/GLM) or generic writer-role phrasing — NOT the gpt-5.4 claim — so
they were left untouched.

**8 gpt-5.4-as-chosen-workhorse mentions reframed** to "incumbent-under-test / observed
dominance = ONE long Build-test session, not a choice / NO model finalized for ANY tier /
per-tier selection PENDING real-code testing + real-outcomes benchmark (#26)". Surrounding
analysis preserved verbatim; only framing corrected.

| File | Lines reframed | Was → Now |
|---|---|---|
| `scratch/usage-profile.md` | 4 (TL;DR L9, interpretation L46, pool-map row L79, confidence L97) | "one workhorse dominates / de-facto sole workhorse / (the workhorse)" → "incumbent-under-test; dominance = one long test session, no tier finalized". Added an explicit framing caveat to the TL;DR. |
| `scratch/best-stack-recommendation.md` | 2 (§2 catch L29, rationale L84) | "The workhorse is gpt-5.4" → "the incumbent-under-test is gpt-5.4 (not a finalized pick)" |
| `scratch/premium-model-cheapest-providers.md` | 1 (L46) | "operator's live workhorse" → "in-window incumbent-under-test — not a finalized workhorse; selection pending #26" |
| `scratch/board-apply-changelog.md` | 1 (L100) | "the live workhorse is gpt-5.4" → "the live in-window incumbent (incumbent-under-test, not finalized)" |

**Left intentionally unchanged (already correctly framed):**
`scratch/featherless-onboarding-checklist.md` already frames gpt-5.4 as an "escape hatch,
NOT the default", cutover "UNPROVEN", owned by the #26/#25 benchmark. That is already the
new framing — no reframe needed. Its other "workhorse" uses are the open-model tier-slot
label. Same for `HANDOFF.md:271` ("OpenRouter free tier is not a workhorse" = generic).

---

## TASK 2 — Quality-equivalent, drain-ordered tier-redundancy requirement

Folded into `fleet/POOLS-REDESIGN-ADR-v2.md`, section **"## Salvaged design ideas"**
(the tier-composition/requirements area), **replacing** the prior thin one-liner
*"Operator directive (2026-07-08) — multiple members per tier"* — so the two are
consistent, not duplicated. New block is titled **"Operator requirement (2026-07-08) —
quality-equivalent, drain-ordered tier redundancy"** and explicitly states it
SUPERSEDES/refines the one-liner.

The rule, spelled out to be buildable:
- Each tier carries **~2–4 QUALITY-EQUIVALENT models, independent provider/quota,
  drain-ordered** → drain any one leg = NO stoppage, NO quality drop.
- "Equivalent" = equivalent **for the operator's real code**, proven by real-code testing +
  the real-outcomes benchmark (#26) — not "both are good models". Tested equivalence is what
  makes the switch seamless.
- Grades job = find **CLUSTERS of ~2–4 equivalents per tier**, not just a #1 (ties into the
  existing "seeded, then refined" stance).
- Independent-quota clause (two aliases of one balance = ONE leg; cites the usage-profile
  shared-`[nanogpt, openrouter]`-chain single-failure finding).
- Pipeline mechanics: **METER-MODEL-PROVIDER** (draining-leg detect) →
  **FREE-TIER-QUOTA-SPILL / PFF-P2** (cross-**model** substitution to next equivalent) →
  transparent to the agent (same alias).
- Switch-timing note: cleanest at TASK boundaries; mid-session swaps carry context but can
  shift style even between equivalents — tighter equivalence = more seamless.
- Testing-scope implication: trial enough candidates per tier to find 2–4 that hold on real
  code (sizes the trial pool).
- Cross-refs (all verified as real board tickets): METER-MODEL-PROVIDER,
  FREE-TIER-QUOTA-SPILL/PFF-P2, BENCH-REGROUND-LIVE (#26/#25), DRAIN-ROUTING/COST-RANK-AUTO.

---

## TASK 3 — SMART switch-timing requirement (coordinator follow-up, 2026-07-08)

Added in TWO places (consistent wording), then `fleet/validate_board.sh` re-run → **GREEN
(exit 0)**. Not committed.

1. **`fleet/POOLS-REDESIGN-ADR-v2.md`** — replaced the prior thin "switch-timing note" bullet
   inside the tier-redundancy block with a full **"SMART switch-timing requirement"** bullet:
   net rule = *switch at the least-disruptive boundary that still avoids running dry*, with
   sub-points (a) prefer TASK boundaries, (b) PREDICT exhaustion from the meter (not the 402),
   (c) RIDE IT OUT to task/session end when headroom is sufficient, (d) NEVER run dry mid-task
   → switch at task start/last-safe-boundary. Signal = METER-MODEL-PROVIDER; actuator = PFF-P2.
2. **`fleet/board/FREE-TIER-QUOTA-SPILL.md.parked`** — appended the same SMART SWITCH-TIMING
   (a)-(d) rule to the `scope:` field as an explicit REQUIREMENT (not just spill-on-error),
   cross-referencing METER-MODEL-PROVIDER (sensor) + PFF-P2 (actuator) and the ADR
   tier-redundancy section. Only board writer this pass; no `owns` change; validator GREEN.
