# PROPOSAL — Correcting the research/evaluation lens (and the class behind it)

**Status:** DRAFT → awaiting DTC · **Author:** manager session (plo-koon) · **Date:** 2026-07-31

## 0. TL;DR
Two framing errors were found in `fleet/state/agent-briefs/RESEARCH-METHOD.md`, both by the
operator, both the same class: **I substituted an easily-countable proxy for the actual objective.**
This proposal corrects the lens, re-opens the research already produced under it, and folds the
class-lesson into the operating rules so it does not recur.

## 1. Problem

### 1a. The size error
`RESEARCH-METHOD.md` states: *"A tool that is bigger than what it replaces, or is abandoned, is not
an adopt — it is a future hand-roll with extra steps."*

This is a **category error**: size is a proxy for maintenance burden, and that proxy is only valid
when WE are the maintainer. Applied to code we merely depend on, it is close to meaningless.

Cost actually scales as:
| Kind of code | Cost |
|---|---|
| Code we OWN | superlinear — understood, tested, evolved, generates rig work forever |
| Code we DEPEND ON (alive) | ≈ interface surface × coupling; **nearly independent of internal size** |
| Code we depend on that DIES | converts instantly to code we own — the worst case |

Rough exchange rate: **1 owned line ≈ 10–50 depended-on lines.** So 5K hand-rolled ≈ 50–250K
depended-on. The operator's framing — a 75K solution that *works* beats 5K of ours that keeps
generating errors — is correct and not marginal.

### 1b. The substitution-blindness error (worse)
The brief's central question was **"what of OURS would this delete?"** That question has a fatal
property: **it can only see what we HAVE; it is structurally blind to what we LACK.** A tool filling
a capability GAP scores zero, because there is nothing for it to delete.

Observed live: LANE 3 evaluated `opencode-fusion` / `keepthewhy`, concluded correctly that neither
sits at our coordination layer, and returned `ADOPT-CANDIDATES: NONE`. It applied the lens
faithfully; the lens discarded the answer. Improving what a single opencode session *does* —
consistency, reliability, reproducibility — IS improving SG/SLOP, because all our work flows
through those sessions.

### 1c. The class
| I optimized (proxy) | Actual objective |
|---|---|
| lines of code | owned complexity |
| code deleted | **SG's ability to do work with consistent quality** (the stated North Star) |

The same substitution also appears in my own `PREFLIGHT-GATE-REGISTRY` ticket (see §4).

## 2. Evidence that session-quality is the higher-value axis
Failures observed in THIS session — none fixable by deleting coordination code, all session-quality:
- 3 workers spawned and **silently failed to start** (readiness gate fired mid-attach)
- a worker shipped a **regression its own suite structurally could not catch** (test seam never
  exercised the production path)
- workers **idled ~4 days** after finishing, stranding 3 P0 fixes
- `deepseek-v4-flash` silently truncates at an upstream 48-request session cap
- free tiers pass a 1-shot probe then collapse under session load

Session quality is a **multiplier on all future work**; deleting N LOC is a **one-time gain**.

## 3. Proposed corrected lens

### 3a. Value taxonomy (replaces the deletion-only test)
| | Value type | Weight |
|---|---|---|
| **A** | **Substitution** — deletes code we own | real, one-time |
| **B** | **Leverage** — each session more capable/consistent/reliable | **highest — compounds** |
| **C** | **Verification** — catches defects we currently ship | **high** |
| **D** | **Throughput** — same work, less wall-clock/tokens | medium |
| **E** | **Product capability** — makes SG better for ITS users | high, separate track |

### 3b. Adoption predictors (replace size)
1. **Maintenance liveness** — an abandoned dep is one we now own (the real risk)
2. **Fit without bending** — if we must reshape our domain to fit it, that is the true cost
3. **Control direction** — library (we call it) vs framework (it calls us → lock-in)
4. **Exit cost** — swappable in ~a week if kept behind a thin adapter
5. **Whose 2am is it** — do we inherit its failure modes on our critical path

Size retained ONLY where it genuinely bites: supply-chain/CVE surface, and using 5% of a tool while
inheriting 100% of its config and failure modes.

### 3c. The discipline that keeps B/C honest
"It improves sessions" can justify anything. So every B/C claim must be **grounded in an observed
failure**: *"would this have prevented [incident], which cost [amount]?"* — tested against the §2
incident list. Concrete answer → ADOPT candidate. Abstract promise → WATCH.

### 3d. Standing correction
`graphify` was adopted and never threatened to become the product. The "rig became the product"
history came from **hand-rolled** rig. **Adoption is the cure for that failure mode, not a risk to
it.** Hand-rolling earns its place only in SG's differentiating core, on adopted substrate.

## 4. Self-correction in flight
`fleet/board/PREFLIGHT-GATE-REGISTRY.md` claims "377 of 969 lines (38%)" in a duplication context.
That figure is *lines inside gate functions*, NOT duplicated lines. Measured exact-duplicate
function bodies: **51 lines (5%)**. The refactor is still right, but its justification is
**contention and ownership** (a new gate stops requiring an edit to a shared file), **not** LOC
saved. Ticket must be corrected before its worker acts on the wrong rationale.

## 5. Blast-radius audit (missing abstraction), completed read-only
| File | Signal | Verdict |
|---|---|---|
| `fleet/preflight.sh` | 4× identical `_red_status`, 4× identical `_close_if_open`, 6× `_red_ensure_open` family, 9× verbatim awk block | **REAL** — variation reduces to 5 *values* |
| `src/charon/connect.py` | 5 clients × 3 ops = 15 fns | **FALSE POSITIVE** — verified: already a `Wiring` registry; bodies differ by real format (JSON/YAML/schema) |
| `src/charon/cli.py` | **2232 lines**, largest in either repo | **UNEXAMINED** — top god-file candidate |
| test files | repeated assertion shapes | **FINE** — tests should be obvious, not DRY |
| rest of `src/charon/` | no cluster >12 lines | **CLEAN** |

**Discriminator worth keeping:** does the variation reduce to **data** (→ registry) or **behavior**
(→ strategy pattern, already correct)?

**Known limits:** exact-hash matching missed the `ensure_open` family (the very thing that started
this); the looser name-shape pass caught it but produced the `connect.py` false positive. Neither
detects cross-file duplication, long-function or deep-conditional smells. This audit is a floor.

## 6. THE PLAN
| # | Action | Cost | Reversible? |
|---|---|---|---|
| P1 | Rewrite `RESEARCH-METHOD.md` §size + §lens per §3 | small | yes (doc) |
| P2 | Re-open all 5 research lanes with corrected lens; existing reports stay valid for axis A, lanes re-answer B/C/D/E | small — sessions alive & idle, context warm | yes |
| P3 | LANE 3 explicit re-ask against the §2 incident list | small | yes |
| P4 | Correct `PREFLIGHT-GATE-REGISTRY` note (§4) before its worker acts | small | yes |
| P5 | Ticket `cli.py` decomposition **assessment only** (2232 lines, product) | small | yes |
| P6 | Fold the proxy-vs-objective lesson into `MANAGER-OPERATING-RULES.md` | small | yes |

**Sequencing:** P1 → P2/P3 (parallel) ; P4 immediately (worker is live NOW) ; P5, P6 after.
**P6 is the durable fix** — P1–P4 repair one instance; P6 addresses the class.

## 7. Explicitly NOT proposed
- Not killing/restarting research lanes (context is the asset; re-open instead)
- Not re-scoping SG/product work
- Not adopting anything yet — this fixes the lens, not the verdicts
- Not touching `cli.py` (assess only)

## 8. Open questions for DTC
1. Is P2 (re-opening lanes) sound, or does re-asking an agent that already committed to `NONE`
   produce **anchored/self-justifying** output rather than genuine re-evaluation?
2. Does this plan itself violate adopt-first / anti-sprawl — i.e. is it **more rig work about how
   to do rig work**, when the answer is to ship SG?
3. Is the A–E taxonomy actually usable, or so permissive that everything becomes ADOPT?
4. Is the §5 audit's "floor not ceiling" caveat load-bearing enough to justify a deeper audit, or
   is that scope creep?
5. What is the opportunity cost of P1–P6 against simply landing the 3 in-flight P0 tickets?
