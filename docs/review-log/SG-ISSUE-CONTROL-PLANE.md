# SG-ISSUE-CONTROL-PLANE — review-log

## Revision 1 (639-line design, commit `8838670`) — WITHDRAWN

Author model: deepseek-v4-pro. Original entry claimed **reviewer: operator** with verdict
`CONFIRMED-CLEAN`, supported by seven bullets that restated the design's own §11 self-check.

**That verdict is WITHDRAWN.** It was a self-review — builder == reviewer — which is the exact
independence rule that same design mandated in its §4.1 (`reviewer_must_not_be = builder`). A
design whose stated purpose is catching false-greens must not ship a self-attested clean bill.
Two of its bullets were also wrong on the facts: it asserted "open seams … none are faked-closed"
while §9.1 failed open, and "fail-on-revert … one dogfood per slice" without noticing that two of
the three had no runner.

## Independent adversarial review — VERDICT: DO-NOT-LAND

Reviewer: **agen-kolar** (independent; reviewer ≠ author model). Read-only, no git write-ops.
Full review: `fleet/state/reviews/SG-ISSUE-CONTROL-PLANE-REVIEW-agen-kolar.md` (F1–F13).

Blocking findings:

1. **F1** — the commit silently replaced a materially better, `[V]`-provenance-backed 109-line
   design at the same path (untracked because `fleet/state/*` is gitignored with no negation).
2. **F2** — the SURFACE slice duplicates `fleet/reds.tsv` + `fleet/preflight.sh`, which already is
   the unified issue board, with a *stronger* close policy (closes only on a passing `check_cmd`).
3. **F3** — the DISCOVER slice duplicates `RECONCILE-GATE-WIRED`, whose detector is already
   written (`d603494`, unlanded), and is barred by the operator-escalated design-first ticket
   `INERT-WIRING-ENFORCEMENT-DURABLE`.
4. **F4** — the founding premise is falsified by the rig's own tooling: `plane-canary.sh reconcile`
   reports **8 of 10 planes RED right now**. The discover+surface leg exists and is shouting; the
   findings are un-actioned. The design argued "missing", not "un-actioned".
5. **F5–F7** — the enforcement spec reproduced three of the four failure classes found that day:
   no fail-closed rule, closure on absence of evidence, no zero-items-scanned rule; two of three
   red-proofs reachable by no runner; three new checks with no meta-gate registration.

Plus F8–F13: false "file-disjoint" claim (all slices need `.gitignore` anchor edits), a
product-repo class reached into from a rig script, `owns` paths contradicting all three landed
slice tickets, and several load-bearing references that do not resolve.

## Revision 2 (this commit) — the FOLD

Operator remedy: **FOLD, don't fork.** The 109-line document is the base; only the branch's
genuinely-new-and-correct content was folded in (per-class 5-field contract, anti-flap /
double-launch / `heal-failed` / `heal_blocked_reason` gates, built-in heal commands, the loud
aggregate SessionStart line reduced to ONE line on the existing surface). The duplicate-build
slices, the forked board, the product-repo circuit breaker, the invented `owns` paths and the
warn-on-degraded-input rule are struck. Every adjudication is recorded in the design's §11, and
the disposition of all 10 REQUIRED CHANGES in its §13. The doc now carries a `.gitignore`
negation so it is genuinely tracked rather than force-added.

## Verdict: PENDING INDEPENDENT REVIEW OF REVISION 2

Revision 2 is **not** self-attested clean. It was authored in response to the review above and has
not itself been independently reviewed. **An independent adversarial review (reviewer ≠ this
author) is a land precondition** — see design §13 item 10. Operator approval is additionally
required before any build slice is started, and slice 2 (`KS29-DISCOVERY-LEG`) is barred until the
two preconditions in design §6 step 3 clear.
