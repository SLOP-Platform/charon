repo: charon
tier: economy
difficulty: 2
work_class: tests
branch: fix/ft-catalog-contract-tests
owns: tests/test_provider_presets.py
depends_on:
note: FT-CATALOG-SEED (PR #135) adds 3 provider presets (github_models/featherless/ollama_cloud) but doesn't update contract tests — test_all_original_keys_present 29!=26 + 4 missing wire-shape fixtures. Update the contract tests to cover the 3 new presets, then #135 can land.
accept: |
  - test_provider_presets.py updated: original-keys count matches, wire-shape fixtures for the 3 new presets present.
  - PYTHONPATH=src python3 -m pytest -q tests/test_provider_presets.py && PYTHONPATH=src python3 -m charon.cli gate
