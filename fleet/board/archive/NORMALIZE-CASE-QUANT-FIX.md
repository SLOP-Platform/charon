tier: frontier
difficulty: 5  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: money-path
branch: fix/normalize-case-quant
depends_on:
owns: src/charon/proxy.py, tests/test_normalize_model_id.py, tools/check_catalog_case_quant.py
accept: PYTHONPATH=src python3 -m pytest tests/test_normalize_model_id.py -q
prompt: /home/stack/charon-private/scratch/briefs/NORMALIZE-CASE-QUANT-FIX.md
scope: _normalize_model_id (proxy.py:247, rsplit("/",1)[-1]) is case-sensitive and keeps quant suffixes, so `Kimi-K2.7-Code` vs pool `kimi-k2.7-code` or `GLM-5.2-FP8` vs `glm-5.2` is false-flagged pseudo_success -> recorded as a FAILURE (forwarder.py:312) and served a spurious X-Charon-Downgrade (why NeuralWatt scores 0/4 while working). Make the compare case-insensitive + quant-suffix aware (strip -FP8/-FP16/-BF16/-Q4../-INT8) on both expected and returned id, WITHOUT breaking the SR-1 namespaced-id final-segment compare. Add tools/check_catalog_case_quant.py detector wired into gates.json/charon.cli gate (mechanizes #30).
note: Money-path — ADVERSARIAL review before merge. Wave 1. New test file is deliberately NOT test_proxy_downgrade.py (SR-1's) to avoid a test-file collision.
