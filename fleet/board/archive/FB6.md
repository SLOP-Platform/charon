repo: charon
tier: sonnet
difficulty: 2  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: ci-infra
branch: feat/decisions-lint
depends_on:
owns: tools/check_decisions.py, tests/test_check_decisions.py, tools/check_boundary.py, docs/DECISIONS.md, docs/adr/0008-work-intake-ticket-plan-pipeline.md, docs/adr/0009-l3-unattended-autonomy-escalation-gate.md, docs/adr/0010-native-work-engine-substrate.md
prompt: /home/stack/charon-private/prompts/fb6.md
note: From the 2026-06-27 fragility audit THEME 9 (docs/decision-register governance has no
  mechanical backstop). Creates the lint script; FB5 wires it into CI (FB5 depends_on FB6).
