#!/usr/bin/env python3
"""effort.py — the EFFORT scorer the tier rule uses instead of a breadth proxy.

WHY THIS FILE EXISTS (the measurement that killed the old rule)
--------------------------------------------------------------
`tier_classify.py` used to promote money-path work to FRONTIER on `nsurf >= 3`
alone — the count of owned non-.md paths, i.e. BREADTH used as a stand-in for
DIFFICULTY. Measured against this rig's own board (n=104 declared tiers):

    nsurf      vs declared tier   rho = +0.075   (p=0.43 — indistinguishable from noise)
    difficulty vs declared tier   rho = +0.413

Breadth is not a difficulty signal here. And a tier is a claim CEILING
(assign.py filters eligible models by the ticket's tier), so a false frontier
promotion locks that ticket to the priciest chain for its entire life. The
better-decomposed a money ticket was, the more expensive the old rule made it —
the exact inversion review finding F5 raised (FT-CATALOG-SEED: d2, three files,
priced at the top tier).

PROVENANCE — PORTED, NOT INVENTED (adopt-first)
-----------------------------------------------
The scorer below is a faithful port of the PRODUCT module
``src/charon/decompose_effort.py`` (repo /home/stack/code/charon), which already
implements exactly this: a weighted combination in which breadth is down-weighted
~13x relative to difficulty.

    effort = 2.0*difficulty + 0.15*size + 1.0*behaviours

External options were evaluated and rejected ON THIS RIG'S OWN DATA, not on
reputation: radon / lizard / scc / COCOMO all bottom out in size again
(maxCC vs SLOC rho = +0.901 on our tree — a second breadth proxy, not a
difficulty signal), and the learned routers (RouteLLM, Deep-SE) need thousands
of labelled examples; we have 104 tickets.

WHY PORTED AND NOT IMPORTED (the rig/product boundary call — option (b))
-----------------------------------------------------------------------
``decompose_effort.py`` lives in the PRODUCT repo; this classifier lives in the
RIG repo. Three options existed: (a) import the product module, (b) port the
formula, (c) extract to a shared package.

(a) is REFUSED BY EVIDENCE, not by taste. ``fleet/tests/tier-drift.test.sh`` is
on the ``fleet/checks/rig-ci-scope.sh`` CI_SUITES allowlist, so this rule is
executed by the rig's GitHub Actions CI — a checkout of charon-private ONLY,
where /home/stack/code/charon does not exist. A hard import would turn a
merge-blocking preflight into one that cannot run there; a soft
import-with-fallback would be worse, because the SAME ticket would then derive
DIFFERENT tiers on different hosts (a non-deterministic gate). (c) means
publishing a third distributable to share ~15 lines of arithmetic, which is
rig-as-product.

(b) is chosen. Its ONE real cost is duplicated logic that can drift — so the
drift is PINNED BY EXECUTION, not by comment: fleet/tests/tier-drift.test.sh
case (i) asserts these constants against the literal documented values on every
host, and additionally diffs them against the product module's own constants
whenever the product tree is resolvable (CHARON_SRC, default
/home/stack/code/charon/src). Change either side and that suite goes RED.

Pure, deterministic, stdlib-only: no network, no clock, no RNG (mirrors the rest
of fleet/capability).
"""
from __future__ import annotations

import re

# ── PORTED CONSTANTS — must equal src/charon/decompose_effort.py ─────────────
# Pinned by fleet/tests/tier-drift.test.sh case (i). Do not "tune" one side.
DIFFICULTY_WEIGHT = 2.0   # decompose_effort.DIFFICULTY_WEIGHT
SIZE_WEIGHT = 0.15        # decompose_effort.SIZE_WEIGHT
BEHAVIOR_WEIGHT = 1.0     # decompose_effort.BEHAVIOR_WEIGHT
SOFT_THRESHOLD = 10.0     # decompose_effort.DEFAULT_SOFT_THRESHOLD ("advise-split", ADVISORY)
HARD_THRESHOLD = 16.0     # decompose_effort.DEFAULT_HARD_THRESHOLD ("over-scope", the HARD call)

# The band the TIER rule promotes on. Deliberately the HARD band, not the SOFT
# one: in the product module SOFT is advisory ("warn, still admit") while HARD is
# the only band that is a clear over-scope call. A tier promotion is a HARD,
# expensive, whole-life decision (it raises the ticket's cost ceiling for good),
# so it is paired with the HARD band. Pairing it with the advisory band instead
# would promote 65 of this board's 104 tickets to frontier — re-creating the
# over-promotion F5 exists to remove, just with a different proxy.
FRONTIER_EFFORT = HARD_THRESHOLD

# F5 FLOOR (operator-approved, TIER-BALANCE OQ-1). Breadth ALONE must never
# reach frontier. Arithmetic already makes that nearly impossible (0.15/path
# means ~93 owned paths before size alone clears the band), but "nearly" is not
# an invariant, so the floor is STRUCTURAL: the effort clause cannot fire below
# this difficulty at all. That makes "breadth alone never promotes" directly
# red-proofable (tier-drift.test.sh case (h)) instead of an arithmetic accident.
EFFORT_DIFFICULTY_FLOOR = 3

_BULLET_RE = re.compile(r"^(?:[-*]\s+|\d+[.)]\s+)")


def count_behaviours(accept: object) -> int:
    """Number of distinct required behaviours declared by a ticket's ``accept``.

    Port of ``decompose_effort._split_behavior_items``: a bulleted/numbered
    block counts its bullets; a prose block falls back to sentence boundaries as
    a distinct-behaviour proxy; anything non-empty counts at least 1.
    """
    if accept is None:
        return 0
    if isinstance(accept, (list, tuple, set)):
        return len([str(x) for x in accept if str(x).strip()])
    text = str(accept).strip()
    if not text:
        return 0
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    bullets = [ln for ln in lines if _BULLET_RE.match(ln)]
    if bullets:
        return len(bullets)
    sentences = [s for s in re.split(r"(?<=[.;])\s+", text) if s.strip()]
    return len(sentences) or 1


def effort_score(difficulty: int, size: int, behaviours: int) -> float:
    """The ported combination. ``size`` is the ticket's own declared owned-path
    count (compute-free fallback branch of ``decompose_effort._size`` — this
    module never parses source), floored at 1 exactly as the product does."""
    d = max(1, min(5, int(difficulty or 1)))
    s = float(max(1, int(size or 0)))
    b = int(behaviours or 0)
    return round(d * DIFFICULTY_WEIGHT + s * SIZE_WEIGHT + b * BEHAVIOR_WEIGHT, 3)


def is_high_effort(difficulty: int, size: int, behaviours: int) -> tuple[bool, float]:
    """-> (promotes?, score). The F5 difficulty floor is applied HERE so every
    caller inherits it and no caller can opt out of it by accident."""
    score = effort_score(difficulty, size, behaviours)
    d = int(difficulty or 0)
    return (d >= EFFORT_DIFFICULTY_FLOOR and score >= FRONTIER_EFFORT), score
