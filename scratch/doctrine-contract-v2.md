# Coordinator Token-Economy Doctrine — Contract v2 (Synthesis of 4 adversarial reviews)

Reconciles: `doctrine-review-tokens.md` (token accounting), `doctrine-review-latency-weakmodel.md`
(latency + weak-model), `doctrine-review-correctness.md` (output-degradation), `doctrine-measurement.md`
(empirical A/B). v1 was 8 rules + 2 caveats. This is the narrowed, scope-tagged v2.

---

## 1. VERDICT

The doctrine **holds — conditionally, and only when re-labeled for what it actually buys.** All four
lenses agree it does NOT reduce total system tokens; it usually *increases* them. What it buys is
**coordinator context-window preservation + parallelism**, which is real and large (natural experiment:
~222k tokens kept out of the coordinator, worth ~0.66M–2.2M re-billed input tokens over R=3–10 remaining
turns). The single biggest correction vs v1: **v1's delegation trigger (>1 file / >150 lines / any edit /
any grep) fires far below the break-even point** — measured break-even is ~3.3k tok residue at 1 remaining
turn, ~420 tok at 10, and the token-lens residue break-even is ~10–12.5k — so v1 *mandates net-loss spawns*
on the entire long tail of small over-threshold tasks (adds latency ~45–160s, adds total tokens, amplifies
weak-model retries). Adopt the doctrine, but ship the **inequality, not the slogan**: replace the trigger
with a residue/size floor, restrict auto-delegation to strong-model manager-scoped coordinators, carve out
the high-stakes must-read-full classes, and require backgrounding so latency ≠ slowdown. As written for a
blanket fleet rule over weak SLOP coordinators it is **refuted** (quantifiable downside on every axis).

---

## 2. NARROWED CONTRACT v2

Legend for scope tags per rule: **[U]** universal · **[CF]** Charon-fleet-specific · **[SLOP]** SLOP-specific.

**Rule 1 — Coordinator gates; it is not the sole worker. [U]**
The coordinator plans, gates, merges, and dialogues. It delegates *substantive* work. **Weak coordinators
are never the sole gate:** anything a weak coordinator would sign off on a C1–C7 class (below) requires a
strong-model gate pass or operator escalation. (Resolves the v1 R1 ⨯ caveat-(a) contradiction.) **[SLOP]**
carries the weak-coordinator clause hardest.

**Rule 2 — Delegate on an estimated-residue floor, not on file/line counts. [U]**
Delegate a task when it will likely leave **> ~10k tokens of retained context residue** in the coordinator.
Practical proxies (any one): **> ~400 lines touched, OR > 5 files, OR expected output/report > 10k tokens,
OR a repo-wide search whose raw hit-dump would exceed a screen.** Bright-line **file count (>5)** is the
weak-model-safe form. **DROP "any code edit" and "any repo-wide search" as automatic triggers** — a one-line
edit or a 5-hit grep belongs inline. Add a **wall-clock exemption:** if the inline estimate is under ~2 min,
stay inline. **Session-phase gate:** near a handoff / end of session (few coordinator turns remain), inline
regardless of size — the compounding term that pays for the spawn tax has evaporated.

**Rule 2a — Coordinator-strength gate on auto-delegation. [SLOP]** (universal principle, SLOP-critical)
Only **strong-model** coordinators auto-apply the Rule 2 residue judgment. **Weak coordinators** delegate
ONLY from a whitelist of pre-approved task shapes, or escalate to the operator; they do not self-judge
Rules 2/3/7. This is the load-bearing guardrail for SLOP, which runs weak models as top-level coordinators.

**Rule 3 — Hand the sub-session the facts, via a template. [U]**
Brief with the load-bearing facts so the sub does not re-investigate. Use a **brief template/checklist**
(weak coordinators under-specify without one). Price the brief in: if authoring a brief complete enough to
prevent re-investigation costs a meaningful fraction of doing the task inline, do it inline (the brief is
billed twice — coordinator output + sub input). Allow the sub a cheap **"insufficient facts" bounce-back**
instead of guessing.

**Rule 4 — Structured pointer-return, not a free ≤5 lines. [U]**
Sub-sessions write the full artifact to file and return `FILE:<path>` plus a **structured**
**VERDICT + CONFIDENCE + UNVERIFIED-LIST** (what was NOT checked) — never a bare prose ≤5 lines, because a
length cap silently compresses away the decisive hedge. For high-stakes classes (C1–C7) the return must be
a checklist the coordinator can independently spot-check against the artifact. **[SLOP] weak-coordinator
inversion:** the (often stronger) sub-session authors the summary in its report; the weak coordinator
forwards the pointer **verbatim** and does not re-summarize (faithful compression needs comprehension).

**Rule 5 — Targeted reads, WITH must-read-full carve-outs. [U]**
Read a report in full only when gating — EXCEPT for the high-stakes classes **C1–C7**, where the coordinator
MUST open and read the full artifact before gating (the summary is a table of contents, not the gating
input). Carve-out classes:
- **C1 Security gates** (secret-scan, public-leak audit, auth/permission, the public-clean guard)
- **C2 Money-path** (billing, cost-aware routing, provider spend, namespaced-id double-bill class)
- **C3 Adversarial-review verdicts on significant/core code**
- **C4 Merges / releases / pushes to public repos** (irreversible, wide blast radius)
- **C5 Decisions that OVERTURN an operator decision** (must be re-confirmed, not auto-reconciled)
- **C6 DTC / design-of-record gates with downstream lock-in** (ADR, pools redesign, bridge)
- **C7 Cross-sub-session consistency** (compatible assumptions across independent subs)
Test: *if a wrong answer and a right answer produce the same summary, the summary is not a valid gate input.*

**Rule 6 — Batch, parallelize, one writer per file; plus cross-cutting reconciliation. [U]**
Fan out independent work; one writer per file; one commit/push per batch. **Never chain-delegate a dependent
sequence** — collapse dependent A→B→C into ONE sub-session (chain depth capped at 1; subs may not spawn
sub-subs). **Add a cross-cutting reconciliation pass:** when ≥2 sub-sessions touch a shared
contract/interface/assumption, one designated integration pass MUST read *both* artifacts and assert their
assumptions agree before either is gated ("one writer per file" prevents file collisions, not assumption
collisions).

**Rule 7 — Right-size the model, with a FLOOR at gates. [U]**
Pick the best model *for the work* — right-sized, not biggest. But **floor, don't just cap:** C1–C7
(security, money, adversarial review of core code, merges, DTC) get the **strong** model regardless of cost.
Cheap models may draft; they may not be the last word on a high-stakes gate. Model choice changes work cost,
not the delegate-vs-inline spawn/compounding trade. Prefer a **static task-shape → model lookup table** over
coordinator judgment for weak coordinators. **[SLOP]** floor matters most.

**Rule 8 — State on disk. [U]** (unchanged)
Durable state lives on disk, not in coordinator context.

**Rule 9 — Independent re-verification for security & money. [U]**
For C1/C2 the coordinator (or a second independent strong-model sub) must **re-run or spot-verify** the
check, not accept the first sub's self-report. Content-keyed / re-executed evidence, not prose. Self-graded
"clean" is smoke-test only.

**Rule 10 — Anti-rubber-stamp forcing function. [U]**
At every C1–C7 gate, the coordinator's approval must **cite a specific detail from the full artifact** (a
line, a number, a named edge case) proving it was read. A gate that records only a summary-hash with no
artifact citation is rejected by the rig.

**Rule 11 — Backgrounding requirement so latency ≠ slowdown. [U]**
Delegations run in the **background**, concurrent with other coordinator work, so the ~24s+ (measured) /
~45–160s (estimated) round-trip is hidden. Serial/foreground delegation of a small task is ~12× slower
(measured 24.3s vs ~2s) and is disallowed except for genuine sub-minute lookups.

**Rule 12 — Enforcement hook is asymmetric + allowlisted (caveat b). [U]**
Enforce the write-to-file contract **hardest on worker→coordinator** output (reject a worker pasting a big
blob instead of a file — the real abuse). Enforce **softest on coordinator→operator** relays: **warn, don't
hard-reject**, and allowlist short fenced snippets under N lines, stack-trace/error patterns, unified-diff
hunks, and copy-pasteable shell commands (the fleet norm *requires* handing the operator literal commands).
Enforce fidelity, not a blanket code ban; false positives cost a wasted generation + retry.

**Rule 13 — Fleet-control reconciliation: sub-session ≠ droid. [CF]**
An Agent-tool **sub-session is NOT a fleet droid.** The manager may auto-delegate *manager-scoped* work
(investigate / design / review) to read-only **sub-agents** (`manager-delegates-to-subsessions`). The
manager must **never auto-launch a fleet droid** (`fleet-droid.sh` tab) — the operator opens droid tabs
(`manager-never-spawns-droids`). Rule 2 must branch on task **class**: *manager-scoped* code edits → Agent
sub-session OK; *product-feature* builds → NOT a manager sub-session, route to an operator-opened droid tab
(`dont-build-products-in-manager-session`). v2 must not muddy sub-agent (auto, fine) vs droid (operator-only).

---

## 3. DECISION TABLE

| # | Proposed narrowing | Lens(es) | Disposition | Rationale |
|---|---|---|---|---|
| 1 | Replace file/line trigger with residue/size floor (~10k residue; >400 lines / >5 files / >10k out / screen-dump grep) | Tokens (N1), Measurement, Latency | **ADOPT** | v1 trigger sits far below break-even; measured/modeled break-even 0.42–12.5k residue depending on R. Rule 2. |
| 2 | Drop "any code edit" & "any repo-wide search" as auto-triggers | Tokens (N1), Latency (§1) | **ADOPT** | One-line edit / 5-hit grep is pure spawn-tax loss; both lenses converge. Rule 2. |
| 3 | Wall-clock exemption: inline est < ~2 min stays inline | Latency (§1, item 2) | **ADOPT** | ~45–160s round-trip dwarfs the work below this. Rule 2. |
| 4 | Session-phase gate: don't delegate near handoff (small R) | Tokens (N2), Measurement | **ADOPT** | N→0 ⇒ Ω/(N·f)→∞; compounding payoff gone. Rule 2. |
| 5 | Chain-depth cap = 1; collapse dependent chains into one sub | Tokens (N4), Latency (§1/§6) | **ADOPT** | Stacked spawn tax + serialized latency + retry amplification, zero parallelism. Rule 6. |
| 6 | Structured VERDICT+CONFIDENCE+UNVERIFIED return, not free ≤5 lines | Correctness (R2), Latency (R4) | **ADOPT** | Length cap destroys the decisive hedge (F4); calibration must survive. Rule 4. |
| 7 | Must-read-full carve-outs C1–C7 at gates | Correctness (R1) | **ADOPT** | Wrong-and-right answers yield identical summaries at these gates; summary invalid as input. Rule 5. |
| 8 | Strong-model restriction on auto-delegation; weak = whitelist/escalate | Latency (§2/§6 rec 1), Correctness (R3) | **ADOPT** | Weak coordinators can't self-apply R2/R3/R7; SLOP runs weak models as coordinators. Rule 2a. |
| 9 | Model FLOOR (not just cap) at gates/security/money/review | Correctness (R3), Latency (R7) | **ADOPT** | Right-sizing DOWN a gate compounds lossy-summary risk (F2). Rule 7. |
| 10 | Cross-cutting reconciliation pass for shared contracts | Correctness (R4) | **ADOPT** | "One writer/file" stops file, not assumption, collisions (F3, disjoint-owns memory). Rule 6. |
| 11 | Backgrounding requirement so latency ≠ slowdown | Measurement, Latency | **ADOPT** | "No slowdown" is conditional on concurrency; foreground is ~12× slower. Rule 11. |
| 12 | Asymmetric + allowlisted enforcement hook (false-positive allowance) | Latency (§3) | **ADOPT** | Blunt code-detector false-fires on errors/diffs/gate-quotes/operator commands. Rule 12. |
| 13 | Independent re-verification for security & money (not self-report) | Correctness (R5) | **ADOPT** | Self-graded "clean" is smoke-test only; content-keyed evidence. Rule 9. |
| 14 | Anti-rubber-stamp: cite a specific artifact detail at gates | Correctness (R6) | **ADOPT** | No forcing function today distinguishes "read it" from "summary said fine" (F7). Rule 10. |
| 15 | Invert compression: sub writes summary, weak coordinator forwards verbatim | Latency (R4) | **ADOPT-MODIFIED** | Adopted for **weak** coordinators only ([SLOP]); strong coordinators still synthesize (they can compress faithfully). Rule 4. |
| 16 | Weak coordinator ≠ sole gate; require strong pass/operator escalation | Latency (R1 vs caveat a), Correctness (R3) | **ADOPT** | Resolves the direct R1⨯caveat-(a) contradiction. Rule 1. |
| 17 | Reconcile with fleet norms: sub-session ≠ droid; branch on class; never auto-launch droid | Latency (§5) | **ADOPT** | Preserves `manager-never-spawns-droids` + `dont-build-products-in-manager-session`. Rule 13 [CF]. |
| 18 | Price the briefing into the delegate decision | Tokens (N5) | **ADOPT-MODIFIED** | Folded into Rule 3 as a check rather than a standalone rule; genuinely load-bearing but not always decisive. |
| 19 | Reframe "token economy" → "context preservation + parallelism" | Latency (framing), Measurement, Tokens | **ADOPT** | Total tokens rise; only coordinator-context falls. Applied in Verdict + Rule 1 framing. |
| 20 | Right-size with spawn-tax Ω in view (cheap model doesn't rescue a below-break-even spawn) | Tokens (N6) | **ADOPT-MODIFIED** | Merged into Rule 2 (model choice ≠ the delegate/inline trade) + Rule 7 floor. |
| 21 | Keep rules 1, 3, 4(base), 6, 8 as written | Tokens (§4) | **ADOPT-MODIFIED** | Kept in spirit but each amended (4→structured, 6→+reconciliation, 1→+weak-gate); none survive fully unchanged except 8. |

### Inter-lens CONFLICTS surfaced and resolved

- **CONFLICT A — Break-even magnitude.** Token lens puts residue break-even at **~10–12.5k**; measurement
  puts **total-token** break-even at **~0.42–3.3k** (R-dependent), and coordinator-context break-even far
  lower (~P≈100 tok). **Resolution:** these measure *different* quantities — token lens counts retained
  *residue* (net of the ~92–98% discarded working set) against the compounding re-bill *with* cache
  discount f≈0.1; measurement counts *total* tokens without cache. Both agree the direction flips below
  their respective thresholds and that v1's trigger is below both. v2 adopts the **conservative (higher)
  ~10k-residue floor** for the delegate/inline decision, and notes coordinator-context alone breaks even
  far lower — so context-pressured sessions may delegate more aggressively (Open Decision 1).

- **CONFLICT B — Prompt caching.** Token lens says caching (f≈0.1) *discounts* the re-bill argument ~10×
  (weakening the case for delegation on small tasks) while the cold-cache spawn tax is paid full;
  measurement assumes *no* cache and treats caching as blunting-not-erasing. **Resolution:** both agree
  caching **reduces** the delegation payoff and **does not** rescue a below-break-even spawn (the spawn tax
  hits a cold cache at full rate). v2's residue floor is set with cache-on economics in mind; no rule
  conflict.

- **CONFLICT C — Who writes the summary (R4).** Latency lens says **invert** compression (sub writes, weak
  coordinator forwards verbatim); correctness lens says the coordinator must produce a **structured**
  verdict it can spot-check. **Resolution:** scope-split — **weak** coordinators forward the sub's structured
  return verbatim ([SLOP]); **strong** coordinators synthesize. Both satisfied by the structured-return
  format in Rule 4.

- **CONFLICT D — Read-back vs pointer economy (token R3 vs correctness R1).** Token lens warns that
  reading F at the gate *voids* the pointer saving; correctness lens *mandates* reading F at C1–C7 gates.
  **Resolution:** not a true conflict — they agree, and it defines the boundary. Reading F is required at
  high-stakes gates (correctness wins there); it is still economical because in the measured cases F (7k/2k/1k)
  ≪ discarded working set (84–89k), so the pointer still saved the working-set re-bill. v2 keeps the carve-out
  AND notes (Rule 5) that delegation of a must-read task pays only when report ≪ working set.

No narrowing was **REJECTED** outright; two were **ADOPTED-MODIFIED** by scoping (15, 18/20/21). The lenses
were complementary, not contradictory, once the "different quantities" and "strong vs weak coordinator"
distinctions were drawn.

---

## 4. PER-RULE SCOPE TAGS (summary)

| Rule | Scope | Note |
|---|---|---|
| 1 Coordinator gates; weak ≠ sole gate | **[U]** + weak clause **[SLOP]** | |
| 2 Residue floor trigger + phase/wall-clock gates | **[U]** | |
| 2a Strong-model auto-delegation gate; weak = whitelist | **[SLOP]** (universal principle) | Load-bearing for SLOP weak coordinators |
| 3 Hand facts via template + bounce-back | **[U]** | |
| 4 Structured VERDICT+CONFIDENCE+UNVERIFIED | **[U]**; verbatim-forward variant **[SLOP]** | |
| 5 Targeted reads + C1–C7 must-read-full | **[U]** | |
| 6 Batch/parallel/one-writer + depth cap 1 + reconciliation | **[U]** | |
| 7 Right-size with model FLOOR at gates | **[U]** | Floor matters most **[SLOP]** |
| 8 State on disk | **[U]** | |
| 9 Independent re-verify security/money | **[U]** | |
| 10 Anti-rubber-stamp artifact citation | **[U]** | Rig-mechanized |
| 11 Backgrounding requirement | **[U]** | |
| 12 Asymmetric + allowlisted hook | **[U]** | |
| 13 Sub-session ≠ droid; branch on class; never auto-launch droid | **[CF]** | Charon fleet norms only |

---

## 5. OPEN DECISIONS FOR THE OPERATOR

1. **Residue-floor number.** Reviews give a *range* (coordinator-context break-even ~100 tok; total-token
   ~0.42–3.3k; residue ~10–12.5k). v2 defaults to **~10k residue** but a context-pressured long session
   may justify a lower floor. Operator to pick the fleet default (and whether it varies by
   context-window headroom).

2. **Strong vs weak model boundary.** "Strong-model coordinator" and "model floor at gates" need a concrete
   **model → tier** mapping per rig (which SLOP models count as strong enough to auto-delegate / to gate).
   Reviews couldn't set this without the current model roster + benchmark actuals.

3. **Whitelist of pre-approved task shapes for weak coordinators** (Rule 2a) — needs authoring. Which
   task shapes are safe for a weak SLOP coordinator to self-delegate without strong-model judgment?

4. **Hook allowlist thresholds** (Rule 12): the snippet line-count N, and the exact error/diff/command
   patterns to allowlist. Mechanization detail left to the rig owner.

5. **R (remaining-turns) estimator.** The phase-gate (Rule 2) and break-even both depend on R, which is
   unknown mid-session. Do we estimate R heuristically (e.g. by session age / TODO depth), or leave it to
   coordinator judgment? Affects how mechanical the phase-gate can be.

6. **Cross-cutting reconciliation ownership** (Rule 6): who runs the integration pass — the coordinator
   itself, or a dedicated strong-model integration sub — when ≥2 subs share a contract? Cost vs safety
   trade left open.
