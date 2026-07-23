repo: charon
tier: economy
difficulty: 1  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
eval-role: SMOKE-TEST-ONLY — non-discriminating (2026-07-13). Confirmed by
  fleet/benchmark/test-quality-gate.py: its own accept: (a bare pytest re-run) PASSES on
  unmodified origin/master, and real candidate outcomes
  (fleet/state/PATH-C-RANKING-CORRECTED.md:71) showed 5/6 clean passes with zero rank signal.
  Keep only to confirm the dogfood pipe RUNS end-to-end; never score it alone as a ranking
  signal. See fleet/state/DOGFOOD-BATTERY-DESIGN.md and fleet/state/PATH-C-EVAL-SET.md.
work_class: bugfix
branch: feat/tool-repair-mutating-gate
depends_on:
owns: src/charon/tool_repair.py, tests/test_tool_repair.py
accept: PYTHONPATH=src python3 -m pytest tests/test_tool_repair.py -v -q
prompt: /home/stack/charon-private/prompts/tool-repair-mutating.md
scope: The tool_repair module's allow_mutating flag is currently a NO-OP — it repairs
  mutating tool calls regardless of the flag's value (HANDOFF-2026-07-04-v2 §3). MUST be
  fixed BEFORE tool_repair is wired into the proxy. Add an is_mutating marker to the
  tool-call schema so the allow_mutating flag can short-circuit (skip repair on mutating
  calls when allow_mutating=False). Small, mechanical, self-contained in tool_repair.py.
  The tool_repair.py module + tests already exist on feat/tool-repair (local commit
  e06b193) — this ticket may resolve by either (a) landing that branch's content via PR,
  or (b) cherry-picking the fix. Suggested agent: DeepSeek V4-Pro (strong tier) or
  glm-5.2 (economy) — small, mechanical, no design judgement.
