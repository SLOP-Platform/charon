#!/usr/bin/env python3
"""Per-(model,section) run state: start timestamp (for auto time_s), attempt/
correction-round counter (capped at 3 per MODEL-BENCHMARK-SPEC.md §5a), and
finalization. Used by run.sh so time_s/corrections are NEVER hand-typed.

Subcommands:
  init   <model> <section> <timebox_sec>          -> creates state, prints worktree dir path
  record <model> <section> <score> <gate>          -> updates state, prints JSON
                                                       {finalize, corrections, final_score, time_s, timed_out}
  path   <model> <section>                         -> prints the worktree dir path (no state mutation)
"""
import json
import sys
import time
from pathlib import Path

import charon_cost

RUNS = Path(__file__).resolve().parent.parent / "runs"
CORRECTIONS_CAP = 3


def state_dir(model, section):
    return RUNS / model / section


def state_path(model, section):
    return state_dir(model, section) / "meta.json"


def load(model, section):
    p = state_path(model, section)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def save(model, section, meta):
    p = state_path(model, section)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(meta, indent=2))


def cmd_init(model, section, timebox_sec):
    d = state_dir(model, section)
    worktree = d / "worktree"
    meta = {
        "model": model, "section": section,
        "start_ts": time.time(), "timebox_sec": float(timebox_sec),
        "attempts": 0, "finalized": False, "worktree": str(worktree),
        # cumulative gateway cost_usd (SR-5b, or the isolated per-session bucket
        # when SESSION-COST is wired - see charon_cost.session_id()) at section
        # start, or None if the gateway isn't reachable/discoverable - `record`
        # diffs against this to attribute the section's spend (best-effort,
        # never estimated).
        "cost_start_usd": charon_cost.snapshot_cost_usd(),
        # "session" or "global" (charon_cost.cost_attribution_method) - recorded
        # for audit: whether this section's cost delta was isolated from
        # concurrent gateway traffic or (the pre-SESSION-COST default) global.
        "cost_method": charon_cost.cost_attribution_method(),
    }
    save(model, section, meta)
    print(str(worktree))


def cmd_path(model, section):
    meta = load(model, section)
    if not meta:
        print("", end="")
        sys.exit(1)
    print(meta["worktree"])


def cmd_record(model, section, score, gate):
    meta = load(model, section)
    if meta is None:
        print(json.dumps({"error": f"no state for {model}/{section} - run `run.sh {model} --sections {section}` first"}))
        sys.exit(1)
    if meta.get("finalized"):
        print(json.dumps({"error": f"{model}/{section} already finalized - re-`--sections` to redo"}))
        sys.exit(1)

    score = int(score)
    now = time.time()
    elapsed = now - meta["start_ts"]
    timed_out = elapsed > meta["timebox_sec"]

    attempts_before = meta["attempts"]
    if timed_out:
        finalize = True
        corrections = attempts_before
        final_score = 0
    elif gate == "pass":
        finalize = True
        corrections = attempts_before
        final_score = score
    else:
        attempts_after = attempts_before + 1
        if attempts_after >= CORRECTIONS_CAP:
            finalize = True
            corrections = attempts_after
            final_score = min(score, 89)  # never land in the top/MERGE band once capped
        else:
            finalize = False
            corrections = attempts_after
            final_score = score
        meta["attempts"] = attempts_after

    # Attribute this section's gateway spend (SR-5b, MODEL-BENCHMARK-SPEC.md
    # Sec 5a): diff the gateway's cumulative cost_usd now against the snapshot
    # `init` took. "-" (never a guess) if either snapshot is missing or the
    # counter went backwards (e.g. gateway restarted mid-section).
    cost_usd = charon_cost.delta_str(
        meta.get("cost_start_usd"), charon_cost.snapshot_cost_usd())

    if finalize:
        meta["finalized"] = True
        meta["final_score"] = final_score
        meta["final_time_s"] = round(elapsed, 1)
        meta["final_corrections"] = corrections
        meta["final_cost_usd"] = cost_usd
    save(model, section, meta)

    print(json.dumps({
        "finalize": finalize,
        "corrections": corrections,
        "final_score": final_score,
        "time_s": round(elapsed, 1),
        "timed_out": timed_out,
        "cost_usd": cost_usd,
        "cost_method": meta.get("cost_method", "global"),
    }))


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(2)
    cmd = args[0]
    if cmd == "init":
        cmd_init(args[1], args[2], args[3])
    elif cmd == "path":
        cmd_path(args[1], args[2])
    elif cmd == "record":
        cmd_record(args[1], args[2], args[3], args[4])
    else:
        print(f"unknown subcommand: {cmd}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
