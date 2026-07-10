# Adversarial Review — Coordinator Token-Economy Doctrine

**Lens:** CORRECTNESS / OUTPUT-QUALITY DEGRADATION (does saving context cost us right answers?)
**Verdict:** REFUTE "no downside." The contract is correct for *cost* and correct for the *median* task, but it is **structurally unsafe for a specific, enumerable set of high-stakes decisions** where the coordinator gates on a lossy summary it never verified. Adopt with the carve-outs in §3, or the doctrine will silently degrade exactly the decisions that matter most.

The core defect: **Rule 4 (≤5-line pointer-return) + Rule 5 (read a report only when gating) create an information bottleneck at the precise moment — the gate — where full fidelity is most needed.** A ≤5-line summary is a lossy compression of the artifact; the coordinator then makes an irreversible decision on the compression, not the artifact. For most work the loss is immaterial. For the classes below, the loss is the decision.

---

## 1. Decision classes where pointer-returns / not-reading are UNSAFE (must-read-full carve-outs)

A "must-read-full" decision is one where (a) the cost of a wrong gate is high or irreversible, AND (b) the failure is *invisible in a favorable summary* — a sub-session that got it wrong (or was adversarially/accidentally lenient) produces a summary indistinguishable from one that got it right. The summary cannot be trusted as a proxy because the summary is exactly what a wrong answer would also produce.

| # | Decision class | Why ≤5 lines is categorically insufficient |
|---|---|---|
| C1 | **Security gates** (secret-scan, public-repo leak audit, auth/permission changes, the public-clean guard already in this repo) | A "no secrets found" summary is unfalsifiable from the summary alone; a missed secret and a clean tree produce identical 5-line returns. Fail-open is silent and irreversible once pushed. This repo already learned this (public-clean exceptions made content-keyed, fail-safe — commit cfa3159). A pointer-return re-introduces the human trust in a summary that content-keying was built to remove. |
| C2 | **Money-path / billing / routing-cost decisions** (the namespaced-id double-bill class, cost-aware routing, provider spend) | Off-by-one or unit errors (per-token vs per-1k, namespace double-count) do not surface in prose. The silent-downgrade double-bill (proxy.py:209) was a *summary-invisible* bug. A coordinator gating "billing looks correct" on 5 lines cannot catch it. |
| C3 | **Adversarial-review verdicts on significant/core code** | See §"integrity" below. A delegated review returning "looks fine" is the single most dangerous pointer-return: it launders an un-scrutinized artifact through a trusted-sounding summary. The review discipline's entire value is in the *reasoning*, which is what the ≤5-line cap discards. |
| C4 | **Merges / releases / pushes to public repos** (irreversible, blast-radius wide) | The coordinator is the last gate before an irreversible public action. Gating a merge on a summary means the merge rests on the sub-session's judgment, not the coordinator's — but the coordinator is the one with cross-cutting context (other in-flight work, prior decisions) the sub-session lacks. |
| C5 | **Decisions that OVERTURN an operator decision** (per your own standing rule: review/DTC overriding the operator must be re-confirmed, not auto-reconciled) | A summary that says "reconciled X" can hide that an operator decision was silently dropped — this is literally how the engine decision got lost (memory: adversarial-review-must-not-silently-override-operator). Must read the full reasoning to see *what* was overridden. |
| C6 | **DTC / design-of-record gate decisions with downstream lock-in** (ADR acceptance, pools redesign, bridge design) | A design accepted on a lossy summary propagates the un-caught flaw into everything built on it. The DTC-reject of obol v1 (7 blockers) required holding all 7 in context simultaneously — a 5-line summary cannot carry a 7-blocker refutation faithfully. |
| C7 | **Cross-sub-session consistency checks** — any decision that depends on whether two independent sub-sessions made compatible assumptions | Structurally impossible to catch from two separate summaries (see §"cross-cutting" below). Requires the coordinator to hold both artifacts' details at once. |

**Rule of thumb for the carve-out:** *If a wrong answer and a right answer would produce the same 5-line summary, the summary is not a valid gating input — read the artifact.* Security "clean," review "fine," billing "correct," and merge "ready" all fail this test.

---

## 2. Concrete failure scenarios (coordinator gates wrong because the summary was lossy)

**F1 — Fail-open security gate.** Sub-session runs a leak audit, misses a hostname in a config comment (or its grep pattern was wrong), returns `FILE: audit.md` + "No secrets or personal info found; tree clean." Coordinator, honoring Rule 5 (don't read unless gating) and Rule 4 (trust the summary), approves the push. The `/home/stack` path / IP ships to the public repo. The summary was *correct about what the sub-session found* and *wrong about what was there* — indistinguishable at the gate. (Directly contradicts memory: public-repo-no-personal-info.)

**F2 — Laundered rubber-stamp review.** Core routing code (failover, cooldown clamp) is delegated to a review sub-session running a *right-sized = cheaper/weaker* model (Rule 7). The weak model misses a fallback edge case, returns "Reviewed; logic sound, tests pass." Coordinator merges on the 5-line return. The failover bug (exhausted providers didn't fail over — memory: charon-failover-bug) is exactly this shape: plausible-looking code, summary says fine, behavior is wrong. Rule 7 + Rule 4 + Rule 5 compound: weak model → lossy summary → unread artifact → bad merge.

**F3 — Contradictory assumptions across sub-sessions.** Sub-session A implements the capability/grades engine assuming grades are 0-100; sub-session B implements ticket-assignment consuming grades as 0-1. Each returns a clean summary ("engine done, tests green" / "assignment wired, tests green"). Both are internally correct. The *contradiction between them* appears in neither summary because neither sub-session can see the other's artifact. The coordinator — the only party positioned to catch it — deliberately holds neither in context. Integration breaks in production, not at the gate. (This is the ONE-engine-drives-both risk in memory: charon-pools-redesign.)

**F4 — Over-confident summary hides a hedge.** Sub-session's full report says "likely correct, BUT I could not verify the concurrency path under load." The ≤5-line cap forces compression to "Correct; tests pass." The hedge — the single most decision-relevant sentence — is dropped by the length limit itself. Rule 4's cap *actively destroys calibration information*. The coordinator gates with false confidence the artifact did not actually claim.

**F5 — Money-path unit error.** Cost-aware routing sub-session returns "Cheapest-first routing implemented; verified cheaper than baseline." The per-1k-vs-per-token bug (or namespace double-count) is not visible in prose and was not in scope of "verified cheaper." Coordinator ships; spend anomaly discovered later from actuals. Exactly the class of bug the actuals-ledger pivot (memory: benchmark-not-a-valid-ranker) exists to catch *after the fact* — the gate should have caught it before.

**F6 — DTC accept on compressed refutation.** A design returns "DTC passed, minor notes." The full artifact actually lists 3 unresolved blockers demoted to "notes" by an optimistic sub-session. Coordinator accepts as design-of-record. Everything downstream inherits the 3 blockers. (obol v1's 7 blockers would have been invisible under a 5-line "mostly fine.")

**F7 — Rubber-stamp drift.** Over weeks, Rule 5 ("read only when gating") + habitual clean summaries train the coordinator to approve without reading even at gates, because "the summary is always fine." The doctrine has no forcing function to distinguish "I read the artifact and it's fine" from "the summary said fine." Silent red rots forever (memory: never-ignore-preexisting-issues).

---

## 3. Narrowing recommendations (rules that need a "high-stakes → read full + verify" exception)

The contract is **kept**, with targeted exceptions. These are minimal and mechanizable.

**R1 — Amend Rule 5 with a MUST-READ-FULL carve-out.** For decision classes C1–C7 (security gates, money-path, adversarial-review verdicts, merges/releases/public pushes, operator-overrides, DTC/design-of-record, cross-session consistency), the coordinator MUST open and read the full artifact before gating — the summary is a table-of-contents, not the gating input. Rule 5's "read only when gating" is fine for *informational* reads; it must not apply to *irreversible/high-blast-radius* gates.

**R2 — Amend Rule 4: pointer-return is the DEFAULT, not the ceiling, for high-stakes artifacts.** Sub-sessions producing security/review/money/design artifacts must still write the full report to file (good), but the ≤5-line cap must not be read as "the coordinator's decision basis." Add: for these classes the summary MUST include an explicit **VERDICT + CONFIDENCE + UNVERIFIED-LIST** (what the sub-session did NOT check). Never allow the length cap to compress away a hedge (fixes F4). Better: for these classes, replace the free-form 5-line summary with a **structured checklist return** the coordinator can independently spot-check against the artifact.

**R3 — Caveat (a) becomes a hard rule for C1–C7: never right-size DOWN for gates/reviews/security/money.** Rule 7 ("right-size model") must be floored, not just capped: adversarial review of core code, security audits, and money-path work get the *strong* model regardless of cost. Cheap models may draft; they may not be the last word on a high-stakes gate (fixes F2). This aligns with memory: subsession-model-and-token-policy ("best model FOR THE WORK... never degrade quality") and don't-trust-weak-models-with-gate.

**R4 — Add an explicit cross-cutting reconciliation step (closes the C7/F3 gap Rule 6 opens).** When ≥2 sub-sessions touch a shared contract/interface/assumption, one designated integration pass MUST read *both* artifacts and assert their assumptions agree, before either is gated. "One writer per file" prevents *file* collisions but not *assumption* collisions (memory: disjoint-owns-not-no-dependency makes exactly this point). Delegation fragments the global view; this rule restores it at the seam.

**R5 — Independent verification for security & money, not trust.** For C1/C2 the coordinator (or a second, independent sub-session with a strong model) must *re-run the check or spot-verify the artifact*, not accept the first sub-session's self-report. A self-graded "clean" is smoke-test only (memory: benchmark-not-a-valid-ranker's core lesson — self-graded ≠ valid). Content-keyed / re-executed evidence, not prose.

**R6 — Forcing function against rubber-stamping (F7).** At every C1–C7 gate the coordinator's approval must cite a *specific detail from the full artifact* (a line, a number, a named edge case), proving it was read — not "summary looks fine." Mechanize in the rig: a gate that records only a summary-hash, no artifact citation, is rejected.

**Bottom line:** ship the doctrine for throughput on ordinary work; gate it with R1–R6 so that the four categories it is *wrong* for — security, money, adversarial review, and irreversible merges/designs — force a full read + independent verification. The contract's own caveats (a: distrust weak models; b: enforce structurally) already point here; they must be promoted from caveats to hard, enumerated carve-outs or the cost win comes straight out of correctness on the decisions that can't be undone.
