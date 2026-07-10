# Adversarial Review — Coordinator Token-Economy Doctrine

**Lens:** latency + weak-model failure modes. **Stance:** refute "no downside."
**Verdict:** The doctrine is sound *for a strong coordinator running manager-scoped work*, but it is **over-scoped and unsafe as a blanket fleet rule** — especially on SLOP, where weak models act as top-level coordinators. Three structural defects: (1) the mechanical trigger taxes small tasks with pure latency + *higher* total tokens; (2) four of the eight rules require judgment weak models don't have; (3) the enforcement hook and the auto-delegation trigger collide with existing fleet-control norms. Recommend **narrowing, not adopting as-written**.

Note on framing: the doctrine is repeatedly sold as "token economy," but delegation does **not** reduce total tokens — it relocates them and usually *increases* the total (brief + re-orientation + report + gating read). What it actually buys is **coordinator context-window preservation + parallelism**. Conflating "keep the primary lean" with "cheaper/faster" is the root error the rest of this review attacks.

---

## 1. Latency cost model — where delegation slows things with zero token benefit

**Per-hop delegation overhead** (added vs. doing the work inline in an already-warm coordinator):

| Component | Inline | Delegated | Notes |
|---|---|---|---|
| Compose brief (rule 3 "hand facts") | 0 | ~10–40s model-time | must be *good* or sub-session re-works |
| Spawn + cold orientation | 0 | ~15–60s | sub-session reads brief, orients, loads context |
| Do the work `T_work` | `T_work` | `T_work` | roughly equal |
| Write report + ≤5-line summary | 0 | ~10–30s | rule 4 output contract |
| Coordinator reads report to gate (rule 5) | 0 | ~10–30s | only when gating |
| **Added round-trip tax** | **0** | **~45–160s** | pure overhead, independent of `T_work` |

**Delegation is net-positive on wall-clock ONLY when** at least one holds:
- `T_work` is large *and* multiple items run **concurrently** (parallelism amortizes the tax), OR
- inline `T_work` would blow the coordinator's context and force a compaction (whose cost exceeds the tax), OR
- the work is genuinely independent and can fan out.

**Delegation is net-NEGATIVE (latency tax, no token benefit) when:**
- **Single small task just over the mechanical trigger** — e.g. a 160-line one-file edit, or *one* repo-wide `grep` that returns in ~2–10s inline. The ~45–160s round-trip dwarfs the work, and total tokens *rise* (brief + report + re-orientation duplicate the coordinator's already-loaded context). The trigger's "**any** code edit" and "**any** repo-wide search" clauses are the worst offenders: a one-line typo fix or a single grep is forced into a spawn.
- **Sequential dependency chains (A2→#20→#26 style).** Each hop pays the round-trip *serially* and **cannot be parallelized** because it's dependent. 3 dependent hops × ~90s ≈ **~4.5 min of pure overhead** that a single inline pass (or a single sub-session doing all three steps) would not incur. The doctrine's trigger actively *encourages* fragmenting a dependent chain into multiple hops — the anti-pattern.

**Rule-of-thumb the doctrine is missing:** delegate for **context preservation + parallel fan-out**, never for a lone task whose inline estimate is under ~2 minutes, and never to split a *dependent* chain (collapse those into one sub-session).

---

## 2. Rules UNSAFE for weak models to self-apply (+ guardrail each)

The contract silently assumes a competent coordinator. SLOP runs weak models *as* the coordinator. These rules invert judgment weak models lack:

| Rule | Why unsafe for a weak coordinator | Guardrail |
|---|---|---|
| **R2** mechanical trigger / delegate-vs-inline | Bright-line parts (file count) are OK, but "~150 lines" needs counting weak models do unreliably, and "any code edit" drives **over-delegation + thrash** → latency amplification. | Make it a hard bright-line (file **count** only). Drop line-estimation and "any edit/any search" as solo triggers. Add a <~2-min inline exemption. |
| **R3** hand the facts | **Most unsafe.** A weak coordinator doesn't know which facts are load-bearing → under-specifies → sub-session does wrong work or re-investigates → **re-work + retry**. | Brief **template/checklist**; allow the sub-session a cheap "insufficient facts" bounce-back instead of guessing. Prefer strong-model coordinator for any non-templated brief. |
| **R4** faithful ≤5-line pointer synthesis | Faithful compression *requires comprehension* — exactly weak models' weakness. A misleading summary makes the operator/gate act on wrong info. | **Invert compression:** the (often stronger) sub-session writes the ≤5-line summary into its report; the weak coordinator forwards the pointer **verbatim** and does not re-summarize. |
| **R7** right-size the model | Needs a task-difficulty × model-capability map weak models aren't calibrated for → mis-size: too weak ⇒ failure/retry, too strong ⇒ cost. | Static **task-shape → model lookup table**, not coordinator judgment. |
| **R1 + caveat (a)** coordinator is the gate, but "don't trust weak models to gate/review" | **Direct contradiction.** If the top coordinator is weak and R1 makes it the gate, caveat (a) says it can't be trusted to gate — the doctrine has **no consistent story for a weak top-level coordinator**. R5's "read the report only when gating" compounds this into rubber-stamping. | Weak coordinator must **not be the sole gate**: require a strong-model gate pass (or operator escalation) for anything a weak coordinator would sign off. |

**Bottom line:** R3, R4, R7 and the R1/caveat-(a) gate contradiction are unsafe for weak self-application. R2 is safe only if reduced to a pure bright-line. R5, R6, R8 are broadly safe.

---

## 3. Structural enforcement (caveat b) — the hook breaks legitimate flows

A hook that rejects any reply "containing pasted code" has real false-positive cost:
- **Legitimate small relays the coordinator NEEDS to inline:** an error message / stack trace forwarded to a sub-session, a 2–3 line diff quoted for a gate decision, a single config line, a copy-pasteable command (fleet norm *requires* handing the operator literal commands). All look like "code."
- **Gate decisions frequently REQUIRE quoting the offending lines** — a reviewer that can't quote the 3 bad lines is degraded.
- **Post-hoc rejection wastes the generation** and forces a **retry loop** (feeds §4 amplification). Rejecting *after* the model spent tokens is itself a token/latency cost.

**Fix — asymmetric, allowlisted enforcement, not a blunt code-detector:**
- Enforce **hardest on worker→coordinator** output (reject a worker that pastes a big blob instead of writing a file — that's the actual abuse R4 targets).
- Enforce **softest on coordinator→operator** relays: **warn, don't hard-reject**; allowlist short fenced snippets under N lines, stack-trace/error patterns, unified-diff hunks, and shell commands. Enforce fidelity, not a code ban.

---

## 4. Retry amplification — delegation multiplies the failure surface where models are weakest

Weak sub-sessions fail/timeout/emit malformed output more often. With per-hop failure `p`, a chain of `k` hops succeeds ~`(1-p)^k`. At `p=0.2, k=3` ⇒ **~49%** chance at least one hop needs a retry, and each retry re-pays the full spawn+run+report tax. An inline single pass has **one** failure surface.

The perverse result: the **mechanical trigger forces the most delegation regardless of model strength**, so the **weakest models get the most-fragmented, most-retry-prone execution** — the exact opposite of what robustness wants. Background hangs also block a gating coordinator that's waiting on the report, whereas inline work fails fast and visibly. **Delegation should be *dialed down*, not up, as coordinator/worker strength drops.**

---

## 5. Conflict with established fleet-control norms

- **`manager-never-spawns-droids`:** the fleet MANAGER watches+gates ONLY and must never launch a droid (`fleet-droid.sh` tabs) — the operator opens tabs. R2's "auto-spawn a background sub-session" is *survivable* only because an Agent-tool **sub-session ≠ a fleet droid** — but **the contract never draws that line**, so as written it licenses the manager to auto-launch execution, re-collapsing oversight+execution (the `claude --bg` anti-pattern that caused the WAVE-1 collisions and the #7 wrong-base merge).
- **`dont-build-products-in-manager-session`:** R2's blanket "**any code edit → spawn a sub-session**" would pull **product-feature builds back into manager sub-agents** — explicitly the anti-pattern flagged 2026-06-27. Product builds must route to **fresh droid tabs the operator opens**, not manager sub-sessions.
- **`manager-delegates-to-subsessions`** *permits* manager-scoped work (investigate/design/review — like this very review) in sub-sessions. So the doctrine isn't wrong; it's **unclassified**: it fails to branch on task **class**.

**Required reconciliation:** R2 must (a) define **sub-session ≠ droid**, (b) branch on class — *manager-scoped* code edits → Agent sub-session OK; *product-feature* code edits → **not** a sub-session, route to an operator-opened droid tab, and (c) **never auto-launch a fleet droid** from the coordinator.

---

## 6. Concrete narrowing recommendations

1. **Gate auto-delegation on coordinator strength.** Only **strong-model** coordinators auto-delegate on the mechanical trigger. **Weak coordinators** delegate only from a **whitelist of pre-approved task shapes** (or escalate to the operator) — they do not self-judge R2/R3/R7.
2. **Harden the trigger, drop the aggressive clauses.** Remove "any code edit" and "any repo-wide search" as *solo* triggers; keep **>1 file changed** and *substantial* work. Add a **wall-clock exemption**: inline est < ~2 min ⇒ stay inline.
3. **Never chain-delegate a dependent sequence.** Collapse dependent A→B→C into **one** sub-session; fan out **only** independent work. Serial chains pay per-hop overhead for zero parallelism.
4. **Invert compression for weak coordinators** (R4): sub-session writes the ≤5-line summary; weak coordinator forwards **verbatim**.
5. **Right-size via a static table** (R7), not coordinator judgment.
6. **Enforcement hook = asymmetric + allowlisted** (§3): hard on worker→coordinator blobs; warn-only + snippet/diff/error/command allowlist on coordinator→operator relays.
7. **Reconcile with fleet norms** (§5): classify task (manager-scoped vs product), define sub-session ≠ droid, never auto-launch a droid, route product builds to operator tabs.
8. **Weak coordinator ≠ sole gate** (R1 vs caveat a): require a strong-model gate pass or operator escalation for weak-coordinator sign-offs.

**Net:** adopt the doctrine **only** for strong-model, manager-scoped coordinators with items 1–8 applied. As a blanket fleet-wide rule over weak SLOP coordinators, it *adds* latency, *adds* total tokens on small tasks, *amplifies* retries, and *conflicts* with two standing fleet-control norms. Refuted: there is a real, quantifiable downside.
