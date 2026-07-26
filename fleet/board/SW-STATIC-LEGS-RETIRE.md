repo: charon
tier: frontier
difficulty: 4
work_class: routing
priority: 0
branch: feat/sw-static-legs-retire
depends_on: SW-IDENTITY-FOLD
real-dep: SW-IDENTITY-FOLD — REAL BUILD PREREQ, not merge order. Pool membership is keyed by
  `_normalize_model_id` (src/charon/proxy.py:269), which `routing_policy/catalog_refresh.py:61-68`
  imports directly. Retiring the static legs while the identity table is still wrong bakes the
  orphan-pool defect into the sole remaining membership source, with no static fallback left to
  mask it. Owns are DISJOINT (this ticket does not touch proxy.py) — the dep is build-order.
dep-kind: build
owns: src/charon/routing_policy/catalog_refresh.py, src/charon/routing_policy/__init__.py,
  src/charon/pools.py, tests/test_static_legs_retired.py
serial_justified: |
  ONE seam: the three files are the static-leg surface end to end — `__init__.py:133` reads
  `upstream_model` into the route, `__init__.py:165-171` drops `enabled: false` before pools are
  built, `pools.py:82` re-reads `upstream_model`, and `catalog_refresh.py:107-128` is the discovery
  source that must replace them. Splitting them ships a half-retired selection path where the
  static legs still win for some ids — the exact silent-divergence class under repair.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session (charon/* gateway model), NOT Claude.
  The run IS a graded sample: record it into the model scorecard (fleet/model-scorecard.tsv) under
  work_class `routing`. One checkout, one agent — own git worktree of the product repo.
source: |
  Switchboard-convergence investigation, 2026-07-26 (manager session). Live state verified on the
  4-LOM gateway, image v0.6.0 build 289cf93 — do NOT re-derive.
note: |
  ## WHAT ADR-0011 REQUIRES
  `docs/adr/0011-the-switchboard-demand-routed-no-pools.md` (**Accepted**) — "The Switchboard":
  no pools, no lists, no static candidate slate. INV-SW1 no list; INV-SW2 never falsely exhausted;
  INV-SW3 cheapest-capable-WITH-CONTEXT-and-available.

  ## WHAT IS ACTUALLY LIVE (verified, do not re-derive)
  - `src/charon/routing_policy/catalog_refresh.py` IS enabled on 4-LOM: `{"enabled": true, "ttl_s": 21600}`.
    It bridges discovered model->providers into `srv.pools` (`refresh_and_bridge`, :249).
  - **4384 pools live vs 859 file entries** — discovery is already doing the work.
  - RESIDUE, and the whole point of this ticket: live `/data/models.json` still has **859 entries**,
    of which **175 carry a hand-pinned `upstream_model`** and **88 carry `"enabled": false`**.
    Those are the static "legs": a hand-maintained candidate slate that ADR-0011 says must not exist.

  ## THE WORK
  Make `catalog_refresh` the **SOLE source of pool membership**, and remove the static legs from the
  SELECTION path:
  1. `routing_policy/__init__.py:133` + `pools.py:82` — a hand-pinned `upstream_model` must no longer
     override the discovered upstream id. Discovery already carries the real advertised id
     (`catalog_refresh.py:120` `"upstream_model": e.upstream_model`). Decide and DOCUMENT the one case
     that may still need a pin (a provider whose advertised id genuinely differs from what it accepts on
     the wire) — if that case is real, it belongs in the provider preset, not in a 175-row model file.
  2. `routing_policy/__init__.py:165-171` — `"enabled": false` currently silently drops a model from
     routes AND pools. That is a static de-selection: it is how a funded leg becomes invisible, i.e. an
     INV-SW2 false-exhaustion vector. Replace it with a demand-time disposition that is LOUD and
     attributable (parked / drained / unfunded / operator-held), or remove it. Silence is the defect.
  3. Retire the 175 pins and 88 disables from the live catalog as a DEPLOY step, sequenced only after
     the code above proves discovery covers them. **HAZARD, already ruled on:** see
     `ADR0016-DEPLOY-PRICED-COMPLETENESS` — purging static entries can collapse an unpriced model to the
     fixed 1000 cost fallback and route to a PRICIER provider. Do not purge live catalog rows until that
     guard exists or you have proven priced-completeness for every affected id. Say which you did.

  ## WHAT THIS TICKET IS NOT
  - NOT a rewrite of discovery. `catalog_refresh` works; this REMOVES the thing competing with it.
  - NOT the identity fix (SW-IDENTITY-FOLD owns proxy.py) and NOT the ADR bookkeeping (SW-ADR0016-SETTLE).
accept: |
  DONE-CONTRACT (observable on the LIVE gateway, not "code written"):
  - Pool membership on 4-LOM derives 100% from discovery: with the static catalog's `upstream_model`
    pins and `enabled:false` flags REMOVED from the selection path, live pool count and membership are
    unchanged-or-larger vs the recorded 4384 baseline, and NO previously-reachable model becomes
    unreachable. Publish the before/after pool count and the diff of lost/gained routable ids.
  - A leg that was hidden by `"enabled": false` is either reachable again, or its exclusion is reported
    with an attributable reason visible in `/charon/status` — never a silent absence.
  - `tests/test_static_legs_retired.py`, FAIL-ON-REVERT and red-proofed by execution: (a) a registry
    entry carrying a hand-pinned `upstream_model` no longer changes the selected upstream id; revert ->
    RED. (b) an entry with `"enabled": false` no longer vanishes silently; revert -> RED. Report BOTH
    exit codes. Non-vacuous: zero fixtures examined is RED.
  - Deploy step, if taken, states explicitly whether the priced-completeness hazard above was guarded or
    avoided. "I purged it and pools looked fine" is NOT an acceptable disposition.
  - `PYTHONPATH=src python3 -m charon.cli gate` GREEN + `pytest -q` GREEN from the worktree.
  - ADVERSARIAL REVIEW (reviewer != builder). This is the routing hot path with money exposure.

## Dependencies & sequence

- **Depends on: SW-IDENTITY-FOLD** (real build prereq — see `real-dep:` above). Startable the moment
  the anchor lands.
- **Wave:** wave 1, PHASE 1. Runs CONCURRENTLY with SW-ADR0016-SETTLE (disjoint owns: code vs docs)
  and with the whole of PHASE 2 (SW-P2-CONTEXT-ADMIT, SW-P2-METER-OBSERVED, SW-P2-GRADE-PLANE-SETTLE).
- **Blocks:** SW-P2-CONTEXT-ADMIT — real build prereq, see that ticket's `real-dep:`. Nothing else.
- **Concurrency safety:** all four owned paths are owned by NO other live board ticket (verified against
  the full `owns:` set of `fleet/board/*.md`, 2026-07-26). `routing_policy/cost_rank.py` is deliberately
  NOT owned here — it belongs to `ADR0016-DEPLOY-PRICED-COMPLETENESS`; coordinate, do not edit it.
- **Related, do NOT duplicate:** `PRICE-TRACKED-INVENTORY-AUTOSWAP` also names catalog_refresh in prose
  but does not own it; check its branch before landing. `ADR0016-DEPLOY-PRICED-COMPLETENESS` owns the
  purge safety guard referenced in step 3.
