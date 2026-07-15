# item-bank/ — single item bank for the consolidated eval pipeline
# (EVAL-PIPELINE-CONSOLIDATE, review F9 + F12).
#
# Replaces the 4–5 overlapping harnesses (preflight.sh T1–T12, dogfood-eval,
# honest-battery-sweep, canary R0, bench.sh S0–S6) with ONE bank of RED-proof
# tasks, each tagged (canonical work_class, calibrated difficulty), graded
# by the ONE OOB grader-daemon path (kind=="preflight" — already OOB; the
# runner enqueues a `kind=preflight` request and the daemon dispatches
# graders.preflight.grade()).
#
# Manifest (this file's sibling, manifest.tsv) is the registry the adaptive
# runner reads. Item dirs under items/<item_id>/ are the fixtures copied
# into a fresh session worktree per attempt; graders/ holds the
# item-specific grader (one Python file per item — small, deterministic,
# never trusts model prose).
#
# EVERY canonical work_class (EVAL-TAXONOMY.md: reasoning, coding,
# translation, creative, analysis, general) has at least one discriminating
# item (fixes F5 — "the honest battery is one skill wearing three labels").
# Difficulty is an integer on a calibrated ladder; items span D1 (easy)
# through D4 (frontier) so the adaptive runner can search up/down
# meaningfully.
#
# ADAPTIVE PLACEMENT (F9): the runner places a candidate near its
# cost-band rung range (TIER-CANON.md: economy→D1–D2, strong→D1–D3,
# frontier→D1–D4) and searches up/down per-skill. Each item's
# `expected_difficulty` is the calibrated midpoint of the difficulty range
# where the MUST-PASS control clears and the MUST-FAIL control misses.
# A SaturatedCheck on every item (does the MUST-PASS control actually
# pass and the MUST-FAIL actually fail) is the discriminating proof;
# a saturated item is rejected from the bank.
#
# RED-PROOF INVARIANT (per EVAL-GRADER-PROVISION): every item's grader
# returns a JSON {"score","verdict","gate","reason"} that is derived from
# the OBJECTIVE worktree state, never from the model's prose. Graders
# live in graders/ and are OOB-graded by grader-daemon.py (kind=preflight).
# The runner enqueues an item by its `item_id` (== the `grader_key` in
# the daemon's request) and the daemon calls graders/<item_id>.py.
#
# DISGUISE INVARIANT (inherited from preflight-tasks/): the item dir copied
# into a model session worktree contains ONLY the fixture files
# (PROMPT.md + seed code). Registry metadata (this README, manifest.tsv,
# traps.tsv, the grader scripts) MUST NEVER reach the model. The runner
# enforces this with an explicit denylist on the copy.
#
# See fleet/state/EVAL-PIPELINE-DESIGN.md for the full architecture and
# the per-item calibration rationale.
