# STARTUP-CONTEXT-DIET review-log

**Date:** 2026-07-15
**Deliverable:** Startup context byte-budget measurement + concrete cuts + fail-on-revert budget gate

## Before/after measurement

| File | Before (bytes) | After (bytes) | Saved | % |
|---|---|---|---|---|
| MANAGER-OPERATING-RULES.md | 29,218 | 24,487 | 4,731 | 16% |
| START-SESSION.md | 6,010 | 2,617 | 3,393 | 56% |
| handoff.sh | 18,389 | 16,505 | 1,884 | 10% |
| handoff-check.sh | 6,238 | 6,238 | 0 | 0% |
| preflight.sh | 31,554 | 35,375 | -3,821* | -12% |
| **TOTAL** | **91,409** | **85,222** | **6,187** | **6.7%** |

*preflight.sh grew because the `startup_budget_gate` enforcement mechanism (~3,800 bytes of gate code) was added to it. The startup-ingested artifacts (rules, session, handoff output) shrank by 10,008 bytes (~2,500 tokens).

## Concrete cuts applied

1. **MANAGER-OPERATING-RULES.md ($12):** Collapsed 22 verbose session-directive bullets into 10 compact bullets. Removed 5 duplicates already covered in $3-$11. Added $13 STARTUP CONTEXT BUDGET (3 lines) that points to the mechanized enforcement in preflight.sh.

2. **handoff.sh:** Removed the 7-line "Context discipline" block from the Bootstrap section (duplicated MANAGER-OPERATING-RULES.md $9). Shortened 4 auto-generated section header comments.

3. **START-SESSION.md:** Replaced 5-line CONTEXT DISCIPLINE paragraph with 1-line pointer to MANAGER-OPERATING-RULES.md $9. Collapsed FIRST ACTS list. Removed stale CURRENT STATE section (referenced wave-1 tickets FB1/E1 that shipped months ago). Shortened SESSION CLOSE and THE LOOP sections.

## Budget gate

Added `startup_budget_gate` to `preflight.sh`:
- Per-file byte budgets for the 5 tracked artifacts
- Total budget: 89,500 bytes
- Auto-registers `startup-budget-exceeded` blocking red in reds.tsv
- Self-closes when all files drop back within budget
- Self-test (`startup-budget-selftest`) verifies the gate fires on over-budget files (fail-on-revert proof)

## Decision notes

- **handoff-check.sh kept unchanged.** At 127 lines / 6,238 bytes, its density is already high — every line is a check or assertion. Further cuts would remove actual checks.
- **preflight.sh grew.** The cost of mechanizing the budget gate is ~3,800 bytes in preflight.sh. This is an acceptable trade-off: the gate is enforcement code (like the board/executor/handoff gates), not narrative overhead.
- **Budget headroom.** Current total (85,222) is 4,278 bytes below budget (89,500). Each file has 500-2,500 bytes of headroom for small additions.
