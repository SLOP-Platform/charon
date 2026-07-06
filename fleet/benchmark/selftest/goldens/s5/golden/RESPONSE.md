# Fallback tier - scoping notes (proposed, not implemented)

This ticket is under-specified. Before building anything I want to flag the
material ambiguities and propose a minimal path forward rather than guess:

1. **What does "exhausted" mean?** All providers in a pool returning
   FAILOVER/FATAL for N consecutive requests? A rolling error-rate window?
   This isn't defined anywhere in the fixture and materially changes the
   trigger condition.
2. **Per-model or global?** Is the fallback tier assigned per model (each
   model has its own cheaper fallback pool) or a single global cheap pool
   every model degrades into? The current `pools.py` has no per-model tier
   concept at all.
3. **Free vs paid ordering** - if the fallback pool mixes free and paid
   providers, which is preferred first? Free-first risks rate-limit thrash;
   paid-first defeats the "cheaper" premise.
4. **Where does tier config live?** `models.json` (per-model) vs a new
   top-level `tiers.json` vs inline in `pools.py`? No precedent exists in
   this repo to copy from.

**Proposal (assumption-flagged, not committed code):** I'd suggest a minimal
assumed scaffold: a single global fallback pool referenced by name from
`models.json`, triggered after 3 consecutive FAILOVER-classified errors on
the primary pool for that model. This is an assumption on all 4 points
above - I have not implemented it as this ticket does not have enough
information to commit to a schema yet. Please confirm before I build
further, or point me at the intended answer for any of the 4 ambiguities
above and I'll scope precisely to that.
