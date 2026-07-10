# BRIEF — ADVERSARIAL REVIEW: Charon work-method vs SLOP/mediastack work-method → one portable "Do work" mechanism?

ROLE: You are an INDEPENDENT ADVERSARIAL reviewer/architect. This is READ-ONLY analysis.
Do NOT edit code, do NOT commit, do NOT push. Your only write is ONE findings file (see DELIVERABLE).

## THE QUESTION
The operator runs multiple projects, each with its own way of "doing work" (decomposing a
backlog into tickets, launching worker agents, reviewing, merging, handing off). The operator's
HYPOTHESIS: **the SLOP/mediastack method is no longer efficient/effective**, and there should be
ONE portable "Do work" mechanism — a project points at it and adopts it — so the operator
maintains/updates only ONE method across ALL projects.

Your job: evaluate this ADVERSARIALLY. Do not rubber-stamp it. Actively try to REFUTE the
premise where it is weak. Then give a decision + a concrete path.

## THE TWO METHODS TO COMPARE (read these — exact paths)

### A) CHARON method (the "fleet rig" + emerging work-engine)
- `/home/stack/charon-private/fleet/MANAGER-OPERATING-RULES.md` — coordinator doctrine (source of truth)
- `/home/stack/charon-private/fleet/COORDINATOR-DOCTRINE-v2.md` — expanded token/delegation contract
- `/home/stack/charon-private/fleet/charon-run.sh` — the worker launcher (opencode → Charon gateway → model failover chain)
- `/home/stack/charon-private/fleet/fleet-droid.sh` — the Claude-droid launcher
- `/home/stack/charon-private/fleet/board/` — tickets (FLAT `key: value` frontmatter) + briefs
- `/home/stack/charon-private/fleet/handoff-check.sh`, `validate_board.sh`, `wci-contention.sh`, `preflight.sh` — the mechanized gates
- `/home/stack/charon-private/fleet/OBOL-PHASE-1-DESIGN.md` — the ALREADY-DESIGNED portable orchestration store ("obol"), the stdlib one-store consolidation of the Droid Method (design-only, not built). THIS IS THE OPERATOR'S TARGET — assess whether it actually delivers "one method for all projects".
- `/home/stack/charon-private/fleet/ADR-DECOMPOSED-BY-DESIGN.md` — the decompose gate direction

### B) SLOP / mediastack method
- `/home/stack/code/mediastack/.claude/ROBOT.md` — the robot/autonomous work doctrine
- `/home/stack/code/mediastack/.claude/AUTONOMOUS-DEFAULTS.md`
- `/home/stack/code/mediastack/.claude/mailbox/` — the mailbox-based coordination
- `/home/stack/code/mediastack/.claude/waves/`, `run/`, `workflows/`, `worktrees/` — the wave/run machinery
- `/home/stack/code/mediastack/tracking/` — tickets in a SQLite DB (`tracking.db`/`backlog.db`) queried via `query.py` (contrast: Charon uses flat-file tickets in `board/`)

## HOW TO REVIEW (adversarial, concrete)
1. Characterize each method HONESTLY on these axes: ticket store & query; work decomposition;
   worker launch (who/what model/parallelism); coordination (mailbox vs bridge vs none);
   review/merge gates; handoff/durability; portability to a NEW project; maintenance surface
   (how many moving parts the operator must keep working).
2. REFUTE the premise: name the things the SLOP method does BETTER than Charon's (e.g. is the
   SQLite tracking.db + query.py a real advantage over flat-file tickets? is the mailbox better
   than the session-bridge for async multi-agent?). If SLOP is actually NOT obsolete, say so.
3. Judge convergence: CAN these two collapse into ONE portable mechanism without losing what
   each does well? Does the designed `obol` store actually achieve it, or does it miss something
   one of the two methods needs? What breaks on migration?
4. Beware over-abstraction: a single "one method to rule them all" can become a lowest-common-
   denominator that serves no project well. Argue BOTH sides.

## DELIVERABLE (write EXACTLY one file, then stop)
Write your findings to: `/home/stack/charon-private/fleet/reviews/METHOD-UNIFY-REVIEW-flash.md`
Structure:
- VERDICT (one line): is the SLOP method obsolete? should there be ONE portable method? (YES/NO/QUALIFIED) + confidence (low/med/high)
- SxS TABLE: the two methods across the axes above, with a ✓/✗/~ per cell.
- WHERE SLOP WINS: concrete list (the refutation).
- WHERE CHARON WINS: concrete list.
- UNIFY DECISION: one portable "Do work" mechanism — feasible? what it must include to not lose either method's strengths. Does `obol` (OBOL-PHASE-1-DESIGN.md) cover it? gaps?
- MIGRATION RISK: what breaks if mediastack adopts the Charon/obol method; the 3 biggest hazards.
- TOP 3 RECOMMENDATIONS, ranked, each with a one-line rationale.
Keep it TIGHT and decision-grade. Cite specific files/lines you read as evidence. No fluff.

## LAST STEP (required)
Confirm the findings file was written (print its path). Do NOT commit. Do NOT push. Do NOT edit any other file.
