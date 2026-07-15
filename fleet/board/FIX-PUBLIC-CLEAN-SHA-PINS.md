repo: charon
tier: economy
difficulty: 2
work_class: ci-infra
branch: fix/public-clean-sha-pins
owns: tools/check_public_clean.py, tests/test_public_clean.py
depends_on:
note: check_public_clean.py false-positives on 40-char dependabot GitHub-Action SHA pins (blocks PR #86 CI-bump). Add an allowlist for pinned action SHAs.
accept: |
  - check_public_clean.py no longer flags 40-hex action SHA pins in .github/workflows/*.yml.
  - test proves: a workflow with a `uses: org/action@<40-hex>` pin passes; a real secret still fails.
  - PYTHONPATH=src python3 -m pytest -q tests/test_public_clean.py && PYTHONPATH=src python3 -m charon.cli gate
