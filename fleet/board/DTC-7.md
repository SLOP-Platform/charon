tier: strong
work_class: ci-infra
branch: feat/dtc-security-scan
depends_on:
owns: tools/check_security.py, tests/test_check_security.py
accept: python3 tools/check_security.py src
prompt: /home/stack/charon-private/prompts/dtc-7.md
# BACKLOG (parked) — automated security audit gate: scans for bare excepts, secrets/tokens in source, hardcoded IPs/hostnames, and dangerous eval/exec/subprocess(shell=True) patterns.
