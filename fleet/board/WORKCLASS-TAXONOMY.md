tier: strong
difficulty: 3
work_class: greenfield-feature
branch: feat/workclass-taxonomy
depends_on:
owns: src/charon/capability/taxonomy.py, tools/check_no_rig_import.py, tests/test_workclass_taxonomy.py
accept: |
  Hot path classifies a task to a KNOWN work_class or `unknown` (route via safe default + log) —
  cheap, no per-request LLM. Offline crystallizer clusters the `unknown` pile into named classes.
  NEW/unknown classes default to HIGH-RISK (reds-replay/spec-floor only, no live uniform explore)
  until operator attests low-risk (red-team fix #4). Ships the CI import-guard tools/check_no_rig_import.py
  banning `import benchmark`/`grader_daemon` on the product hot path (red-team fix #2). Fail-on-revert:
  add `import benchmark` to a product module -> guard fails (test RED).
scope: GATEWAY-PROGRAM §1.9. Open append-only taxonomy; the product-boundary import-guard lives here.
ds: Wave 2. New files + one new tool. Disjoint.
