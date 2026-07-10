# Adversarial review — ADR-DECOMPOSED-BY-DESIGN.md

**Reviewer:** independent adversarial sub-session (read-only; no edits/commits).
**Date:** 2026-07-09
**Target:** `/home/stack/charon-private/fleet/ADR-DECOMPOSED-BY-DESIGN.md`
**Verdict:** **REVISE (minor / near-ratify).** Core (Lever 1 + Lever 2 line gate) is sound and
build-ready; two fixable blocking issues in Lever 2 (hot-file ratchet trap; owner-dimension
penalizes the wrong ticket) must be addressed before Phase 2 flips to HARD.

---

## Ground-truth verification (I tried to catch the author lying; mostly they didn't)

Verified against the live tree — the ADR's factual base holds:

- **File sizes exact.** `wc -l src/charon/*.py`: cli.py **2043**, land.py 861, intake.py 738,
  proxy_server.py 725, gateway.py 623, config.py 623 → **6 files > 600 HARD**; plus connect.py 550,
  api.py 493, proxy.py 480, forwarder.py 408 in the 400–600 WARN band (~10 files touched by WARN).
  The claimed bimodal distribution is real: well-shaped modules (router 98, failover 141, pools 130,
  translate 142, observability 148) do cluster < ~200; everything ever decomposed sits > 600.
  **Thresholds 400/600 are genuinely calibrated to this repo, not arbitrary.** (Credit.)
- **Lever 1 is a REAL mirror, not vapor.** `validate_board.sh` (Python-embedded despite `.sh`) has
  the `_DS` check at lines 245–255: it opens each live ticket's `prompt:` file and regexes
  `##\s*dependencies\s*&\s*sequence`. Lever 1's `## Module Layout` check is a copy-paste of a
  working pattern — cheap and feasible exactly as described. (Credit.)
- **`size` domain is free.** `ALL_DOMAINS` = {boundary, security, arch, test, test-patterns, lint,
  type, version, registry, gate, fleet, docs, decisions}. No collision; registry mechanically
  supports the add (dup-domain guard + `@covers` scan confirmed in check_gate_registry.py).
- **Owner threshold pinned to wci-contention N=4** — accurate; wci-contention.sh default N=4, exits 0
  always (advisory by design). work_class taxonomy in `capability/grades.py` includes
  `greenfield-feature` and `refactor` as claimed.

No material factual misrepresentation found. That is unusual and earns the ADR a near-ratify floor.

---

## Attack results

### 1. Prevents god-files, or just relocates friction? Would it have stopped cli.py?
**On SIZE: yes, genuinely.** A *new* file HARD-fails at 600, so cli.py could never have silently
reached 2043 — it would have red at the 600 line and forced a split. That is the core win and it is
real. **On SEAMS: no** — and the ADR honestly concedes this (§8: "cannot mechanically guarantee good
seams"). So the honest claim is: **it prevents unbounded size; it does not prevent bad
decomposition.** The ADR's summary language ("prevents… both") slightly over-claims; downgrade the
prose to "prevents size-class god-files; seam quality remains review-owned (Lever 1)."

### 2. False-positive blast radius
- 400/600 defensible (see calibration above). Over-fragmentation risk is acknowledged and guarded
  (ceiling-not-target, scaffolder floor, `seams` field), but the fragmentation guard is deferred
  (Q3) — acceptable for Phase 1.
- **Real FP #1 (BLOCKING): the hot-file ratchet trap.** "Fail only if it GREW beyond baseline"
  sounds gentle, but cli.py is *the CLI* — the single most-edited file. The **first net-additive
  edit** (a bugfix that adds a branch, 5 lines) goes RED. The author of an unrelated bugfix is then
  forced to either (a) big-bang-decompose a 2043-line file inside a bugfix ticket, or (b) game it by
  trimming comments/whitespace to stay under baseline. The ADR's "no big-bang, monotonic
  convergence" selling point is **false for hot files**: the big bang is merely deferred onto
  whoever next touches the file for an unrelated reason. This is the strongest attack on Lever 2 and
  is fixable (below), not fatal.

### 3. Gaming
- **599+599 near-god-files:** nothing mechanical stops splitting one 1200-line god-file into two
  599-line near-god-files. Only Lever 1's human review (one-responsibility / why-new) catches it.
  Strictly better than 2043, but the "decomposed-by-design" promise is review-load-bearing, not
  mechanization-load-bearing. State this plainly.
- **`accretion-ok:` and `## Module Layout` as rubber-stamps:** real risk. Acceptance criterion #4
  (<20% override rate before promoting Lever 3 to HARD) is **trivially satisfied by always marking**
  — it measures override *frequency*, not override *honesty*, so it is not a real quality gate.
  Consistent with the existing `real-dep:` pattern (auditable-in-ticket, not machine-judged), so not
  a regression — but don't sell the criterion as protection it doesn't provide.

### 4. Grandfather / ratchet soundness
- **Day-one green: verified true** (baseline snapshots all 6 over-HARD files; new/healthy files
  HARD at 600). Good.
- **Convergence: NOT gentle** — see FP #1. It converges only under pressure that lands on the wrong
  (unrelated) tickets. For the five files at 1.0–1.4× ceiling (land/intake/proxy_server/config/
  gateway) normal touches can plausibly shrink them; for cli.py at **3.4×** it will red almost every
  future CLI touch. The ratchet does not "let cli.py rot forever" — the opposite failure: it taxes
  every future cli.py touch until someone pays the split.

### 5. Cost/complexity vs payoff — which levers are load-bearing
- **Load-bearing, build first:** Lever 2 **line** budget + baseline/ratchet (with FP#1 fix) and
  Lever 1 Module-Layout section. Both cheap (sub-second; copy an existing check), high leverage, and
  the actual size-god-file preventers.
- **Redundant / keep advisory — consider cutting from scope:** Lever 2 **owner** dimension as a new
  HARD RED (see #6 — duplicates wci-contention and penalizes the wrong ticket).
- **Most FP-prone / lowest value:** Lever 3 accretion lint (`git diff` column-0 def/class count
  misfires on reorders, in-place function-splits, and cross-file moves). Keep permanently advisory
  or defer; it is the least load-bearing.
- **Nice-to-have, defer (already Phase 3):** Lever 4 scaffolder — highest code cost, lowest urgency,
  cuttable for MVP.

### 6. Enforcement gaps / interaction
- **Owner-dimension penalizes the wrong ticket (BLOCKING for the HARD flip).** Owner-count is a
  property of the *whole board*, not of the ticket being authored. HARD-failing the **4th** ticket
  for a mis-slice created by tickets 1–3 blocks a blameless author, and it **duplicates** what the
  advisory `wci-contention.sh` already surfaces at the same N=4. It also tensions with the standing
  decision (`wci-rig-enforced-product-deferred`: rig WCI *semantic* stays advisory). Recommend: keep
  owner-count **ADVISORY** (as it already is) — do not add a new HARD RED on it.
- **Rig Python unguarded until Phase 3** (capability/*.py, benchmark/*.py). Minor; note it.
- Line-gate scope `src/charon/*.py` is non-recursive — fine today (flat tree), note for subpackages.
- Registry/gate wiring (new domain, gates.json entry, gate_runner CHECKS, ci_step:true) is
  mechanically supported and consistent with existing gates. No gap.

### 7. Open question Q2 (cli.py) — my position
**Force-decompose cli.py NOW via a dedicated ticket; do NOT rely on the ratchet.** (a) At 3.4× the
ceiling and being the hottest file, the ratchet will red nearly every future CLI touch — "gentle
convergence" is a fiction for this file; pay the split once on a ticket scoped to absorb it rather
than taxing every unrelated ticket. (b) It is the reference case the whole ADR is motivated by;
decomposing it proves the doctrine and removes the biggest ratchet-trap. **Baseline-and-ratchet the
other five** (land/intake/proxy_server/config/gateway, all 1.0–1.4×) which can shrink under normal
touches.

---

## Blocking issues (ranked)

1. **Hot-file ratchet trap (Lever 2 baseline).** First net-additive edit to a baseline file (esp.
   cli.py, the CLI) goes RED, forcing big-bang refactor inside unrelated tickets or gaming. Fix:
   (a) force-decompose cli.py now (Q2 above), AND (b) add a per-touch grace to the ratchet — either
   allow `baseline + small delta`, or apply the grow-fail only to `work_class ∈ {greenfield-feature,
   refactor}` and let `bugfix` net-add within a bounded allowance, OR pair each remaining baseline
   file with a scheduled decompose ticket so the pressure lands where it can be absorbed.
2. **Owner-dimension HARD penalizes the wrong ticket & duplicates wci-contention.** Keep owner-count
   advisory; do not add a HARD RED. Removes a false-friction source and a conflict with the
   rig-advisory standing decision.
3. **Over-claimed prevention + rubber-stampable acceptance criterion #4.** Downgrade prose to "size
   god-files prevented; seams review-owned." Replace/augment criterion #4 with something that
   samples override *honesty* (e.g. spot-audit N `accretion-ok:` reasons per wave), since frequency
   alone is gameable.

## Recommended build order
- **Phase 1 (build now, warn-only):** Lever 1 `## Module Layout` required check (mirror `_DS`) +
  Lever 2 **line** budget + baseline snapshot. Cheap, high-leverage, low-risk.
- **Before Phase 2 HARD:** land the Q2 cli.py decompose + the ratchet grace fix (#1); drop the
  owner-dimension HARD (#2).
- **Defer:** Lever 3 (permanently advisory unless FP-honesty measured) and Lever 4 scaffolder
  (Phase 3, as the ADR already schedules).

Net: the ADR is honest, well-grounded, and its core two levers are ready to build. It is **not**
sound-as-written only because the HARD-flip path (Lever 2 ratchet on hot files + owner HARD) will
generate misdirected false-friction. Both are fixable without redesign → **REVISE, not reject.**
