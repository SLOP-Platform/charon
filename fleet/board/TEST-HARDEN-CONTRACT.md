tier: strong
work_class: tests
branch: feat/test-harden-contract
depends_on:
owns: tests/conftest.py, tests/test_provider_response_contract.py, tools/check_test_patterns.py, tests/test_check_test_patterns.py
accept: PYTHONPATH=src python3 -m pytest tests/test_provider_response_contract.py tests/test_check_test_patterns.py -q
prompt: /home/stack/charon-private/scratch/briefs/TEST-HARDEN-CONTRACT.md
scope: Kill the self-mirroring-mock blind spot (conftest.py:54-60 + ~14 inline handlers all return canonical OpenAI shape, so foreign-envelope bugs are invisible — why the cline defect passed green). Add (1) a parametrized provider-contract test over every ProviderPreset asserting the CLIENT response has top-level choices + usage (cline-pass marked xfail strict=False, no dep on Fix 4); (2) a self-mirroring-mock lint rule in check_test_patterns.py + coverage in test_check_test_patterns.py; (3) conftest.py updates only as needed for the fixture.
note: Standard review (test harness, not money-path). Wave 1. check_test_patterns.py + test_check_test_patterns.py were DTC-8's; DTC-8 is DONE (state/done marker) so this is now their sole live owner (done/live hand-off = INFO, not RED).
