repo: charon-private
tier: frontier
difficulty: 5
work_class: greenfield-feature
branch: feat/eval-pipeline-consolidate
depends_on: EVAL-TAXONOMY-ALIGN, EVAL-GRADER-PROVISION, EVAL-DERIVED-BUDGETS, EVAL-LATENCY-GATE, LEG-PREFLIGHT-CANARY
dep-kind: build
serial_justified: this IS the single-pipeline consolidation — the item-bank, the adaptive runner, and the retirement of the duplicate batteries are one coherent architecture; splitting re-creates the multi-harness fork it removes. (Decompose into build-chunks at start per project-start-audit, but it is one owner.)
owns: fleet/benchmark/preflight.sh, fleet/benchmark/dogfood-eval.sh, fleet/benchmark/item-bank/, fleet/board/MODEL-PREFLIGHT.md, fleet/state/EVAL-PIPELINE-DESIGN.md
accept: |
  Review F9 + F12 (folds operator ask #2 + the per-(model×skill) ladder + the staged elimination design in
  MODEL-PREFLIGHT.md): collapse the 4-5 overlapping harnesses (preflight.sh T1-12, dogfood-eval, honest-battery-sweep,
  canary R0, bench.sh S0-S6) into ONE pipeline. See the consolidated design in MODEL-TESTING-ADVERSARIAL-REVIEW.md §F12.
  DO:
  - ONE item-bank (fleet/benchmark/item-bank/): merge the SURVIVING non-saturated tasks (discriminating T-tasks + the
    honest briefs + any S-section that discriminates), each tagged (canonical work_class, CALIBRATED difficulty), each
    RED-proof, graded by the ONE OOB grader-daemon path. Retire S0-S6 + T1-12 as separate batteries (keep S0 as smoke).
    Every semantic work_class from EVAL-TAXONOMY.md has >=1 discriminating item (fixes F5 — the "3 skills are 1 skill").
  - ONE adaptive runner (F9): places each candidate near its expected tier and searches up/down (adaptive, not
    everyone-climbs-from-R1); item difficulty steps sized so each rung eliminates a meaningful fraction (IRT/binary-search
    style); produces the per-(model × work_class) CEILING grade; eliminates PER-SKILL (peak in one skill, keep testing
    others). Budgets per run come from EVAL-DERIVED-BUDGETS (token/tok_s-normalized, not flat 3/6/10). The runner is the
    SOLE writer of source=live scorecard rows via one capture path (removes the dogfood/preflight/sweep fork).
  - Write fleet/state/EVAL-PIPELINE-DESIGN.md (the one-pipeline architecture) and reconcile MODEL-PREFLIGHT.md to point
    at it (this ticket supersedes MODEL-PREFLIGHT's flat battery; keep MODEL-PREFLIGHT as the candidate-slate list).
  FAIL-ON-REVERT: the adaptive runner places a strong-MUST-PASS control high and a weak-MUST-FAIL control low in <= the
  same #runs as fixed-climb (adaptivity proven); every canonical work_class has a discriminating item (a saturated item
  is rejected from the bank); exactly ONE capture path writes source=live (grep proves no second writer). Run at least S0
  smoke + one full placement on the deepseek-v4-flash MUST-FAIL control end-to-end.
