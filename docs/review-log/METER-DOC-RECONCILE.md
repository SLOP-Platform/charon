# METER-DOC-RECONCILE — review log

## What changed
Docs-truth reconcile on `src/charon/proxy.py` (money-path). Zero functional
edits — every change is inside comments/docstrings. The five stale blocks
claiming the per-(model, provider) cost ledger was "Wave-2 deferred" and
"EMPTY under real traffic today" were rewritten to state the ACTUAL wiring:

- **Written**: forwarder.py passes `provider=route.label` at 8 metering sites
  (581, 629, 655, 791, 797, 845, 869, 898 as of 2026-07-16).
- **Read**: cost-rank routing at forwarder.py:532
  (`live = observer.all_model_provider_costs()`), gateway status surface at
  gateway.py:477, referenced by balance.py:534.

Reader file:line citations are now IN the docstrings so future drift is
self-evident.

## Blocks corrected (pre-change line numbers)
1. `__init__` ledger comment (~308–315)
2. `observe()` `provider` param doc (~354–361)
3. `record()` `provider` param doc (~503–507)
4. `model_provider_cost()` docstring incl. KNOWN-WAVE2-GAPS header (~562–587)
5. `all_model_provider_costs()` docstring (~591–598)

Verified post-change: `grep -cE 'Wave-2|Wave 2' src/charon/proxy.py` → 0.

## Fail-on-revert tests (tests/test_meter_doc_reconcile.py)
1. **Behavior**: real mock upstream + real `GatewayProxyServer` + one real
   chat forward → `all_model_provider_costs()` non-empty, keyed
   `("m1", "prov-a")`, cost 0.25. Verified RED with
   `sed s/provider=route.label/provider=None/` on forwarder.py.
2. **Doc-drift guard**: proxy.py contains none of "EMPTY under real traffic",
   "WAVE-2 DEFERRED", "deferred to Wave 2" — enforced only while
   `all_model_provider_costs` has >=1 reader outside proxy.py (reader count
   asserted first, so deleting the readers cannot satisfy the guard).
   Verified RED by re-appending the stale string to proxy.py.

## Green-is-not-proof note
The full suite was green while the docstrings were false — docstrings are
never executed. The evidence for this ticket is the two revert experiments
above going RED, not the green run.

## Manager follow-up (NOT droid work — no file touched)
`fleet/board/METER-MODEL-PROVIDER.md.parked` is a Wave-2 BUILD ticket for
work that has ALREADY SHIPPED (the 8 write sites + live readers above). Its
premise is dead. Recommendation: **retire or rescope** — disposition owned by
the manager; this ticket did not edit/rename/park/unpark that file.

## Known intentional non-changes
- `tests/test_meter_model_provider.py:3` carries the same stale
  "wiring deferred" note — outside this ticket's `owns:`, left for a
  follow-up (the doc-drift guard covers only src/charon/proxy.py per the
  ticket's accept criteria).
- The KNOWN GAPS (negative-cost passthrough, unpriced divergence) are real
  and retained — only the "Wave-2" framing was removed.
