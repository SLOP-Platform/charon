repo: charon
tier: strong
difficulty: 3
work_class: refactor
branch: refactor/f29-providers-data
depends_on:
owns: src/charon/providers.py, src/charon/provider_presets/
accept: |
  F29 slice (c) — providers.py PRESETS -> data/category files. Design of record: fleet/state/GODFILE-DECOMPOSE-REVIEW.md §1.
  The `PRESETS` static ~30-vendor dict (providers.py:60-156) IS the whole collision, and it is already pure data.
  Move it into a `provider_presets/` package of category modules (`hosted.py` / `local.py` / `anthropic.py` or similar)
  that a small registry merges at import — mirroring the existing `response_adapters._ADAPTERS` precedent. Adding a
  provider becomes a row in a category file, ZERO edit to the machinery.
  KEEP IN providers.py (do NOT move): the `ProviderPreset` dataclass (35-56), the HTTP /models fetch machinery
  (list_models/_parse_models/_extract_pricing/_is_free, 159-277) and `resolve()` (280-297). providers.py must still
  expose `PRESETS` (now assembled from the registry) so every existing `providers.PRESETS` / `resolve()` caller is
  unchanged. Pure data move.
  FAIL-ON-REVERT (add tests/test_provider_presets.py): assert the assembled PRESETS contains every vendor key it held
  before (count + spot-check a few known presets) AND that a preset added to a category module appears in PRESETS with
  ZERO edit to providers.py machinery; revert the registry-merge and the test RED (vendor keys missing / new preset absent).
  GREEN-IS-NOT-PROOF: existing test_providers.py passing is necessary but not sufficient — also REQUIRE (1) the preset
  test above and (2) a reviewer confirming NO ProviderPreset field values changed in the move (byte-for-byte data),
  only their file location. Run: PYTHONPATH=src python3 -m pytest tests/test_providers.py tests/test_provider_presets.py -q
scope: |
  F29 REVISIT — operator-approved SURGICAL un-defer (2026-07-12). The smallest independent slice (~1-2h), near-zero
  regression risk (pure data). Un-blocks the providers.py owner cluster (roadmap R19/R21/R23/R24 fan-out + the live
  PROVIDER-PROBE-FIX/PROVIDER-URL-HELPER chain) to parallelize on category files. [[charon-work-engine-vision]]
ds: FLEET Wave G (F29 surgical). depends_on EMPTY — board-unblocked, launch NOW. Runs CONCURRENTLY with
  F29-REGISTRY-SLICE + F29-CONFIG-PKG (disjoint files: providers.py only). providers.py's other live owners
  (PROVIDER-PROBE-FIX, PROVIDER-URL-HELPER) are sequenced BEHIND this via PROVIDER-PROBE-FIX's depends_on.
  MONOPOLIZES providers.py for its wave.
