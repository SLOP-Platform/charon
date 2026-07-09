# WCI-METHOD — the repeatable backlog-decomposition method

**Status:** durable doctrine (mechanized). **Semantic:** RECOMMEND / ADVISORY — flag, do not
hard-block. Source: the `proxy_server.py` 25-ticket god-file decomposition (2026-07-08) and memory
`wci-ticket-decompose-method`. We kept re-deriving this insight and losing it; this doc + the
detector (`fleet/wci-contention.sh`, wired into `fleet/preflight.sh`) make it how we work.

WCI = Work-Composition Intelligence: organize any backlog so it has **no redundancy/contradiction,
maximum concurrency, and minimum dependency-coupling** before you spend wall-clock and tokens on it.

---

## Run this BEFORE opening tabs on a backlog

Before launching any droid/sub-session tabs against a set of tickets, do the WCI pass below.
The mechanized trigger is the contention detector:

```
fleet/preflight.sh detect        # surfaces the top DECOMPOSE CANDIDATES (advisory line)
fleet/wci-contention.sh [N]      # full owner lists; N = ownership threshold (default 4)
```

A file that shows up as a **DECOMPOSE CANDIDATE** means the backlog is mis-sliced against its own
contention (see Step 2). Resolve it in the plan first — don't just open N tabs that all collide on
one file.

---

## The method (5 steps)

### Step 1 — DEDUP FIRST
Before scheduling anything, shrink the set. Check each ticket for:
- **SUPERSEDED / already-landed** — the work is done in some commit (e.g. INC-401 landed in
  `307652d`; the COOLDOWN clamp landed in `f3a73f2`). Close/drop it.
- **COUPLED** — two tickets are really one unit of work. Fold them.
- **CONTRADICTORY** — one ticket deletes what another builds (e.g. a wholesale GUI rewrite deletes
  what incremental GUI tickets build). Resolve the contradiction before scheduling, don't schedule
  both.

Shrinking the set (the demo went 12 → 9) is the single cheapest optimization — you never pay to
build, review, or reconcile work that shouldn't exist. This is WCI rule #1.

### Step 2 — FIND THE CONTENTION AXIS
Collisions happen on the **`owns:` / FILE axis**, but tickets are sliced on the **FEATURE axis**.
When N tickets collide on one file, the slicing is **orthogonal to the contention** — that is a
signal that the decomposition is wrong, **not a fact of life** to be worked around with serial
queuing. The contention detector measures exactly this axis: how many tickets own each file.

### Step 3 — GOD-FILE → DECOMPOSE
A file owned by **≥ ~4 tickets is refactoring debt** (this is the detector's threshold). Split it
along its natural seams so the colliding tickets re-slice onto **disjoint modules** and parallelize
by construction:
- **behavior-preserving VERBATIM moves** — cut code out, paste it into the new module unchanged;
- **facade re-exports** — keep the old public/test import surface intact so nothing else breaks;
- **suite green per commit** — each move is independently green;
- **adversarial review on the risky / money-path module** (routing, billing, failover) — the split
  is where regressions hide.
- **KEEP genuinely-coupled work serial** — do not force-split real money-path coupling just to
  parallelize; disjoint `owns` rules out file collisions but a coupling can still be a real
  build prereq (see `disjoint-owns-not-no-dependency`).

The point: turn the collision metric into a **refactor trigger**, then the re-slice in Step 4 is free.

### Step 4 — RE-SLICE → collision-free WAVES
Re-slice the deduped set onto the decomposed modules and group into **waves of owns-disjoint lanes**,
maximizing concurrency. Per ticket assign:
- a **vehicle** — droid = product code, sub-session = rig work;
- a **right-sized model** — best model FOR THE WORK, not the biggest;
- and **preserve the quality gates** — adversarial review stays on money-path/core lanes.

No two lanes in a wave may write the same file (owns-disjoint is the wave invariant; `validate_board.sh`
enforces disjointness structurally).

### Step 5 — SEQUENCE
Order the waves:
1. **tiny urgent bleed-stoppers FIRST** (one-line fixes, red-closers);
2. **THEN structural** (the god-file decompositions from Step 3);
3. **THEN the parallel feature lanes** (which are now collision-free because of Step 3).

---

## Mechanization (so we stop re-deriving it)
- `fleet/wci-contention.sh` — scans every `board/*.md` + `*.md.parked`, parses `owns:`, counts
  tickets per file, prints any file owned by ≥ N (default 4) as a **DECOMPOSE CANDIDATE** with its
  owner list. Advisory: prints, never mutates, always exits 0.
- `fleet/preflight.sh detect` — calls the detector as a `DETECTED (unregistered)` advisory line
  (informational; does **not** fail preflight), so the manager sees god-files every preflight.
- Enforced at the **rig** level per `wci-rig-enforced-product-deferred` (advisory semantic). Product
  WCI is deferred and, when built, must be opt-in + advisory-override.

Related: `charon-work-composition-intelligence`, `disjoint-owns-not-no-dependency`,
`ds-standing-rule`, `optimize-execution-wallclock-tokens`.
