# NORMALIZE-CASE-QUANT-FIX — case/quant-insensitive model-id compare

**Money-path.** `_normalize_model_id` (proxy.py) compared the final path segment
verbatim, so a 200 echoing the SAME model under a cosmetic surface variance —
case (`Kimi-K2.7-Code` vs pool `kimi-k2.7-code`) or a quant tag (`GLM-5.2-FP8` vs
`glm-5.2`) — diffed from the expected id, was classified `pseudo_success`, recorded
as a quality FAILURE (forwarder.py) and served a spurious `X-Charon-Downgrade`.
That is why a working provider (NeuralWatt) scored 0/4.

## Change
- Normalization now lower-cases the final path segment and strips a trailing
  quantization suffix (`-fp8/-fp16/-fp32/-bf16/-int8/-int4/-q<n>[_…]`), repeatedly,
  on BOTH the expected and returned id. The SR-1 final-segment (namespace) rsplit
  is preserved — the quant/case fold is applied AFTER it, so the double-bill guard
  is untouched.
- `tools/check_catalog_case_quant.py`: detector that asserts every curated catalog
  id is already canonical (bare, lower-case, quant-free) and that no two entries
  collide under normalization. Pure `find_mismatches()` + a `main()` gate entry.

## Why quant tokens (not a blanket last-segment strip)
Stripping any trailing `-<token>` would eat legitimate model-name segments
(`-code`, `-pro`). The suffix set is an explicit allow-list of quant tokens, so
`kimi-k2.7-code` and `deepseek-v4-pro` are preserved while `-fp8`/`-q4_k_m` fold.

## Guardrails proven RED-on-revert
- `test_quant_case_variant_is_not_downgrade` — client-observable: case+quant
  variants of the same model give `pseudo_success is False` (no downgrade header).
  RED today, GREEN with the fix, RED on revert.
- `test_genuine_family_difference_still_flags_downgrade` — opus→haiku still fails
  over; the fold does NOT blind real downgrade detection.

## Ownership note — gate wiring DEFERRED (not skipped)
The brief asked to wire the detector into `gates.json` / `charon.cli gate`. Both
`tools/gates.json` and `src/charon/gate_runner.py` are OUTSIDE this ticket's
`owns:` (`proxy.py`, `tests/test_normalize_model_id.py`,
`check_catalog_case_quant.py`). Editing them would (a) fail the pre-PR scope
self-check and (b) risk double-claiming a file another ticket may own. Per the
ownership rule (`owns:` is the single source of truth), the wiring line is left
for a follow-up that owns the gate registry. The detector is fully functional and
gate-ready: it exits 0/1/2 and is covered by seeded-mismatch unit tests, so
appending `("python3", "tools/check_catalog_case_quant.py"), "catalog-case-quant"`
to `gate_runner.CHECKS` (plus a `gates.json` entry) is a one-line follow-up.
