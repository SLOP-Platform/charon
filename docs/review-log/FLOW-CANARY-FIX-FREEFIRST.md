# FLOW-CANARY-FIX-FREEFIRST — review log

Ticket: FLOW-CANARY-FIX-FREEFIRST (fix-forward from the RETROACTIVE adversarial
review of FLOW-CANARY, which reached master unreviewed via the commit-dirty
sweep). Class: bugfix. Difficulty: 2. owns: `fleet/flow-canary.sh`,
`fleet/tests/flow-canary.test.sh`.

## Crux
The flow-canary's free-first stage hardcoded `fc∈{1,2}=free`, which is a
REIMPLEMENTATION of a policy the gateway implements differently. The live SSOT
in `charon.routing_policy._FUNDING_CLASS_ORDER` is `{1:0, 3:1, 2:2, 4:3}` → order
`1<3<2<4`. Class-3 (drain-then-park prepaid) ranks SECOND, sanctioned — meaning
a class-3 leg legitimately serving is the free-first pick when no class-1 leg is
available. The canary's hardcode would CRY-WOLF (false-RED) on that normal
operation. A proactive guard that false-REDs on normal operation is worse than
none. Three minor decorative / vacuous assertions rode along.

## FIX-1 (headline) — free-first reads the SSOT, not a hardcode
`fleet/flow-canary.sh:_funding_order_json` reads the live
`charon.routing_policy._FUNDING_CLASS_ORDER` (default path: import + JSON dump).
The free-first stage now computes the highest-priority NON-parked/keyed
candidate in the head-model pool per the SSOT order and asserts the served leg
EQUALS that best candidate (ties tolerated — the snapshot cannot expose
drain-remaining, so parking/exclusion is the load-bearing signal). A class-3
leg serving as the sole/best candidate GREENs; a lower-priority leg serving
while a higher-priority non-parked candidate was skipped REDs.

The hermetic dogfood pins `FC_FUNDING_ORDER_JSON` (hermetic pin of the SSOT's
VALUE, not a reimplementation — the live `charon` import is the preferred path
in production). If both the live import AND the override fail, the stage REDs
rather than silently defaulting to the hardcode (the defaulting is what caused
the cry-wolf).

## FIX-2 — R2 dogfood rewritten, no fake-green
The old (R2) seeded `deepseek` (fc3) serving and asserted `free-first ordering
violated` — that mirrored the canary's wrong model: a class-3 leg is NOT *per
se* a fault. (The old test happened to RED because a class-1 was also in the
pool, but its reasoning was the wrong model.)

Rewritten as two cases:
- **(R2a) REAL violation** — a class-4 PAYG leg serves while a class-1 free
  non-parked candidate is in the pool → RED (`free-first ordering violated`).
- **(R2b) NO CRY-WOLF** — a sanctioned class-3 drain-then-park leg serves as
  the only/best candidate → GREEN. This is the load-bearing assertion: the OLD
  canary (hardcoded `fc∈{1,2}`) would have RED'd this. Fail-on-revert: if
  someone re-introduces the hardcode, (R2b) goes RED and the suite fails.

## FIX-3 (minor) — meter cost-delta backstop tightened
The old `cost-delta >= 0` was near-un-failable (a funded-free leg legitimately
prices at ~0 → the assertion passed even on an inert-cost leg). Dropped the
decorative `>= 0`; now the meter stage asserts `> 0` for a DRAINING (class-3 /
drained) leg only — a paying leg that took a free ride (served advanced, cost
flat) REDs. Non-draining legs keep the served-count advance as the load-bearing
anti-inert signal. New dogfood **(M2)** seeds a class-3 leg with `cost_inert`
(served advances, cost doesn't) and proves the new `> 0` REDs where the old
`>= 0` would have GREEN'd.

## FIX-4 (minor) — park positive-GREEN must be non-vacuous
The old park stage GREEN'd whenever parked/drained providers were "EXCLUDED
from the served path" — even if the parked provider was never a candidate of
the head-model pool (not in the pool at all). That claim is vacuous: it proves
nothing about the exclusion path. The fix intersects the excluded set with the
pool; if the intersection is empty, the positive-GREEN is downgraded to a RED
("VACUOUS") so the verdict can't be misread as "exclusion proven". The healthy
baseline was adjusted so its parked provider IS a pool candidate (legitimate
non-vacuous positive). New dogfood **(P3)** seeds a parked-but-not-in-pool
provider and proves the canary REDs.

## Verification
- `bash fleet/tests/flow-canary.test.sh` → **25 passed, 0 failed** (was:
  18-then-fake-green). Adds (R2a), (R2b), (M2), (P3).
- `PYTHONPATH=src python3 -m pytest -q` → 58 passed (canary dogfood is a bash
  test, not in the pytest suite; no regressions introduced).
- `shellcheck -S warning` on both files → clean.
- `ruff check` / `mypy src tests` error counts unchanged from master (17 / 1,
  all in upstream src files I do not own; `charon-private` has no `tools/`
  checkout scripts).
- Live SSOT sanity: `python3 -c "from charon.routing_policy import
  _FUNDING_CLASS_ORDER as o; import json; print(json.dumps({str(k):v for k,v in
  o.items()}))"` → `{"1": 0, "3": 1, "2": 2, "4": 3, "None": 5}`, matching the
  hermetic pin.

## Scope
`git diff --name-only master...HEAD` → `fleet/flow-canary.sh`,
`fleet/tests/flow-canary.test.sh` — both in the ticket's `owns:`. No files
outside `owns:` were created or edited (this review-log fragment, the lone
exception, is in my own `docs/review-log/<id>.md`).

## Why no further split
`serial_justified` on the ticket: the canary fix (FIX-1) and its dogfood
rewrite (FIX-2) are one unit — splitting ships a fixed canary with a
fake-green test or vice-versa. FIX-3 and FIX-4 are minor tightenings of stages
the same dogfood exercises; folding them keeps the fail-on-revert coverage
co-located with the assertion they fix.