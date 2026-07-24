#!/usr/bin/env python3
"""Per-(model,section) run state: start timestamp (for auto time_s), attempt/
correction-round counter (capped at 3 per MODEL-BENCHMARK-SPEC.md §5a), and
finalization. Used by run.sh so time_s/corrections are NEVER hand-typed.

Subcommands:
  init      <model> <section> <timebox_sec>        -> creates state, prints worktree dir path
  record    <model> <section> <score> <gate>       -> updates state, prints JSON
                                                       {finalize, corrections, final_score, time_s, timed_out}
  path      <model> <section>                      -> prints the worktree dir path (no state mutation)
  is_active <model> <section>                       -> prints "true"/"false" - is this section's on-disk
                                                       state a genuinely still-in-flight run (not finalized,
                                                       and within its own round's timebox), or STALE
                                                       (abandoned - past its timebox with nobody actively
                                                       extending round_start_ts via `record`)? bench.sh's
                                                       `section_in_progress` uses this instead of a bare
                                                       file-existence check (bench-run-collision, P1 - see
                                                       module docstring below for the incident).

BENCH-RUN-COLLISION (P1, fleet/reds.tsv) HARDENING: state used to be keyed
by bare model name with no lock and no staleness check, so a NEW run could
silently `path`/resume a PRIOR (possibly abandoned hours ago, possibly
belonging to an entirely different model due to a since-fixed bench.sh
`.current_model` mislabel - see bench.sh) run's meta.json, inheriting its
stale `start_ts` verbatim - every section then forced score=0 via the
timeout path the instant `record` ran, no matter how fast the NEW run
actually was. Two independent, complementary fixes below:

  1. STALENESS: `is_active` (used by bench.sh before deciding to resume vs.
     re-`init` fresh) treats a non-finalized section as ACTIVE only while
     `now - round_start_ts <= timebox_sec` - once a round's own timebox has
     elapsed with no `record` call extending it, the section is presumed
     ABANDONED and bench.sh will `init` it fresh (new worktree, new
     start_ts/round_start_ts, attempts reset to 0) instead of resuming
     poisoned state. This is the fix for the ACTUAL observed incident
     (a stuck run's ~25h-old start_ts poisoning a new one).
  2. LOCK + ACTIVE-RUN GUARD (defense in depth, for genuinely simultaneous
     double-invocation - e.g. two tabs racing the TOCTOU window between
     bench.sh's `is_active` check and its `init` call): `init`/`record` each
     hold a non-blocking `flock` on `<state_dir>/.lock` for their own brief
     critical section, failing fast with a clear message if another process
     holds it RIGHT NOW. `init` additionally refuses (when the caller opts
     in via `BENCH_GUARD_ACTIVE_RUN=1` - bench.sh sets this; run.sh/
     run-many.sh deliberately do NOT, preserving their existing always-reset
     PREPARE-mode contract) to clobber an existing ACTIVE (not stale) section
     at all, rather than silently re-initializing over live state.

RESIDUAL CLOSED (harness-hardening adversarial review, fleet/scratch/
harness-hardening-review.md must-fix #1): the staleness gate above only
protected `start`/`init` (via `is_active`/`section_in_progress`) - `record`
itself had NO equivalent gate, so a `grade`/`record` call that landed on
STALE state ANYWAY (e.g. bench.sh's `--model`-omitted fallback resolving to
some OTHER model's abandoned section - see bench.sh's
`refuse_if_stale_fallback`) would still silently compute `timed_out=True`
and finalize a poisoned score=0/huge-`time_s` row - reproducing the exact
deepseek-v4-pro incident under a plausible "the driving LLM forgot
`--model`" mistake. `cmd_record` now runs the SAME `is_active` predicate
(via `_is_active_meta`, sharing `is_section_active`'s logic against the
already-loaded `meta` - no extra disk read) before doing anything else, and
REFUSES (prints a JSON `{"error": ...}` to stdout, exits 1) instead of
scoring, whenever state is already stale at record-time. This is a
deliberate behavior change from before: a section that's gone stale is no
longer silently auto-scored 0 by whichever `record` call happens to land on
it next - the caller must explicitly `bench.sh start --model <id>` to get a
fresh round (which itself re-`init`s over stale state, per the fix above) -
so this can't reproduce the incident's poisoned/misattributed row. A
caller whose own run is still genuinely active (round elapsed <= timebox)
is completely unaffected.

Also: `record`'s TIMEOUT check is computed from `round_start_ts`, not the
section's original `start_ts` - `round_start_ts` resets at the top of every
NEW correction round (see `cmd_record`) so a model that legitimately spends
most of a section's total wall-clock across 2-3 correction rounds is judged
against a FRESH per-round budget each time, not a cumulative one - it is
never false-zeroed just because the sum across rounds exceeds one round's
timebox_sec (bench-run-collision ticket's "cap elapsed to the active work
period" ask). The reported `time_s` in the ledger is still measured from
the section's overall `start_ts` (unchanged) - that is deliberately the
TOTAL time spent on the section end to end, an audit/reporting figure, not
the timeout basis.
"""  # noqa: E501
import contextlib
import json
import os
import sys
import time
from pathlib import Path

import charon_cost

try:
    import fcntl
except ImportError:  # pragma: no cover - POSIX-only harness (Linux dev/CI box)
    fcntl = None

RUNS = Path(__file__).resolve().parent.parent / "runs"
CORRECTIONS_CAP = 3


def state_dir(model, section):
    return RUNS / model / section


def state_path(model, section):
    return state_dir(model, section) / "meta.json"


def lock_path(model, section):
    return state_dir(model, section) / ".lock"


@contextlib.contextmanager
def exclusive_lock(model, section):
    """Non-blocking advisory lock on this (model, section)'s state dir for
    the duration of the caller's own critical section - held only across a
    single `init`/`record` invocation (each is its own short-lived process;
    there is no long-lived daemon holding this across the minutes a model
    spends actually writing code between `init` and `record`, so this is a
    narrow but real defense against literally-simultaneous double
    invocation, not a substitute for the staleness check above). Raises
    SystemExit(1) with a clear stderr message if another process holds it
    right now."""
    d = state_dir(model, section)
    d.mkdir(parents=True, exist_ok=True)
    p = lock_path(model, section)
    fh = open(p, "a+")
    try:
        if fcntl is not None:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                sys.stderr.write(
                    f"error: another process is ACTIVELY using {model}/{section}'s "
                    f"state right now (lock held on {p}) - refusing to touch it "
                    f"concurrently. This is either a genuine simultaneous double "
                    f"invocation (re-run in a moment) or a leftover lock from a "
                    f"process that crashed while holding it (remove {p} if you've "
                    f"confirmed nothing is actually running).\n")
                sys.exit(1)
        yield
    finally:
        if fcntl is not None:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def load(model, section):
    p = state_path(model, section)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def save(model, section, meta):
    p = state_path(model, section)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(meta, indent=2))


def _round_elapsed(meta):
    """Seconds since the CURRENT correction round started - `round_start_ts`
    if present (post bench-run-collision fix), else `start_ts` (older
    meta.json predating this field - never crashes reading one)."""
    round_start = meta.get("round_start_ts", meta.get("start_ts", 0))
    return time.time() - round_start


def _is_active_meta(meta):
    """Same predicate as `is_section_active`, given an ALREADY-loaded meta
    dict (or None) rather than re-reading it from disk - used by `cmd_record`
    so its staleness gate is provably the identical check `is_active`/
    `section_in_progress` already use, against the exact meta this call is
    about to act on (no TOCTOU between a second load() and the mutation
    below - the caller already holds the exclusive lock)."""
    if meta is None or meta.get("finalized"):
        return False
    timebox = meta.get("timebox_sec", 0)
    return _round_elapsed(meta) <= timebox


def is_section_active(model, section):
    """True if (model, section) has non-finalized state AND is still within
    its current round's timebox - i.e. genuinely in flight, safe to resume.
    False if there's no state at all, it's already finalized, OR it's
    STALE (past its round's timebox with nobody extending it via `record`) -
    callers should treat False as "safe/expected to re-`init` fresh", not as
    an error."""
    return _is_active_meta(load(model, section))


def cmd_is_active(model, section):
    print("true" if is_section_active(model, section) else "false")


def cmd_init(model, section, timebox_sec):
    d = state_dir(model, section)
    worktree = d / "worktree"
    with exclusive_lock(model, section):
        # bench-run-collision GUARD (opt-in via BENCH_GUARD_ACTIVE_RUN=1 -
        # bench.sh sets this; run.sh/run-many.sh deliberately don't, so their
        # existing always-reset PREPARE-mode contract is unchanged): refuse
        # to clobber state that is genuinely ACTIVE (not stale) rather than
        # silently re-initializing over a still-in-flight run. bench.sh
        # itself normally never reaches here for an active section (its own
        # `section_in_progress`/`is_active` check keeps it on the RESUME
        # path instead) - this is the last-line defense for the TOCTOU
        # window between that check and this call.
        if os.environ.get("BENCH_GUARD_ACTIVE_RUN") == "1" and is_section_active(model, section):
            existing = load(model, section)
            sys.stderr.write(
                f"error: {model}/{section} already has an ACTIVE run in progress "
                f"(round elapsed {_round_elapsed(existing):.0f}s <= timebox "
                f"{existing.get('timebox_sec')}s) - refusing to re-initialize and "
                f"clobber it. If you're certain that run is actually abandoned, "
                f"wait for its timebox to lapse (it will then be treated as "
                f"stale and reset automatically) or remove its state dir "
                f"({d}) by hand.\n")
            sys.exit(1)
        # TOKEN-CAPTURE: one snapshot call captures cost_usd + tokens_in/out
        # together (charon_cost.snapshot_usage()) - same network round-trip that
        # used to fetch cost_usd alone, nothing new hit twice. `None` (whole dict
        # or any individual field) when the gateway/field isn't
        # reachable/reported - `record` below diffs against whichever of these
        # snapshotted, falling back to "-" per-field, never a guess.
        usage_start = charon_cost.snapshot_usage()
        now = time.time()
        meta = {
            "model": model, "section": section,
            # bench-run-collision: ALWAYS a fresh timestamp for THIS init call
            # - never inherited from any prior/other run's state (a prior
            # meta.json, if any, is fully replaced below, not merged into).
            "start_ts": now,
            # round_start_ts: the clock `record`'s TIMEOUT decision is actually
            # judged against - resets at the top of every new correction round
            # (see cmd_record) so multi-round work gets a fresh per-round
            # budget instead of accumulating against this section-wide start.
            "round_start_ts": now,
            "timebox_sec": float(timebox_sec),
            "attempts": 0, "finalized": False, "worktree": str(worktree),
            # cumulative gateway cost_usd (SR-5b, or the isolated per-session bucket
            # when SESSION-COST is wired - see charon_cost.session_id()) at section
            # start, or None if the gateway isn't reachable/discoverable - `record`
            # diffs against this to attribute the section's spend (best-effort,
            # never estimated).
            "cost_start_usd": usage_start.get("cost_usd") if usage_start else None,
            # TOKEN-CAPTURE: same idea, for cumulative tokens_in/tokens_out at
            # section start. Absent (None) on any older/incompatible gateway
            # response - additive fields, never required.
            "tokens_in_start": usage_start.get("tokens_in") if usage_start else None,
            "tokens_out_start": usage_start.get("tokens_out") if usage_start else None,
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
    with exclusive_lock(model, section):
        meta = load(model, section)
        if meta is None:
            print(json.dumps({"error": f"no state for {model}/{section} - run `run.sh {model} --sections {section}` first"}))  # noqa: E501
            sys.exit(1)
        if meta.get("finalized"):
            print(json.dumps({"error": f"{model}/{section} already finalized - re-`--sections` to redo"}))  # noqa: E501
            sys.exit(1)

        # bench-run-collision RESIDUAL (see module docstring above): refuse
        # to grade/finalize against state that is already STALE (past its
        # own round's timebox with nobody extending it via a live `record`
        # call) instead of silently computing timed_out=True and landing a
        # poisoned score=0/huge-time_s row - the exact incident this whole
        # fix line exists for, reproducible via a misattributed/omitted
        # --model fallback landing on some OTHER (possibly long-abandoned)
        # model/section's state. A caller whose own run is still genuinely
        # active (round elapsed <= timebox) never reaches this branch.
        if not _is_active_meta(meta):
            stale_elapsed = _round_elapsed(meta)
            print(json.dumps({
                "error": (
                    f"{model}/{section}'s state is STALE (round elapsed "
                    f"{stale_elapsed:.0f}s > timebox {meta.get('timebox_sec')}s "
                    f"with no active `record` call extending it) - refusing to "
                    f"grade/finalize a score against abandoned state instead of "
                    f"silently emitting a poisoned score=0 row (bench-run-collision, "
                    f"fleet/reds.tsv). If this is genuinely YOUR OWN run and you just "
                    f"ran long, re-run `bench.sh start --model {model}` to get a fresh "
                    f"round for this section (you will need to redo the work in the "
                    f"new worktree). If you did NOT expect this model/section, you "
                    f"likely omitted --model and picked up a stale/misattributed "
                    f"pointer - re-run `grade` with the EXACT --model <id> from your "
                    f"own start's ANNOUNCE line."
                ),
                "stale": True,
            }))
            sys.exit(1)

        score = int(score)
        now = time.time()
        # `elapsed`: TOTAL time since this section's overall (fresh, per
        # cmd_init above - never a foreign run's) start_ts - reported in the
        # ledger as an audit/"how long did the whole section take" figure,
        # unchanged from before bench-run-collision.
        elapsed = now - meta["start_ts"]
        # `round_elapsed`/`timed_out`: bench-run-collision fix - the TIMEOUT
        # decision is judged against `round_start_ts` (this round's OWN
        # clock, reset below whenever a new correction round begins), not
        # the cumulative `elapsed` above, so 2-3 legitimate correction
        # rounds that together exceed one round's timebox_sec don't get
        # false-zeroed - each round gets its own fresh budget.
        # `.get(..., meta["start_ts"])` keeps this reading an older
        # meta.json (pre-fix) working unchanged.
        round_start_ts = meta.get("round_start_ts", meta["start_ts"])
        round_elapsed = now - round_start_ts
        timed_out = round_elapsed > meta["timebox_sec"]

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
                # NEW correction round starts now - reset the round clock so
                # this round gets its own fresh timebox_sec budget rather
                # than being judged against the section's original
                # start_ts cumulatively.
                meta["round_start_ts"] = now
            meta["attempts"] = attempts_after

        # Attribute this section's gateway spend (SR-5b, MODEL-BENCHMARK-SPEC.md
        # Sec 5a): diff the gateway's cumulative cost_usd now against the snapshot
        # `init` took. "-" (never a guess) if either snapshot is missing or the
        # counter went backwards (e.g. gateway restarted mid-section).
        # TOKEN-CAPTURE: ONE snapshot_usage() call at record-time supplies the
        # cost_usd end-value too (previously a separate snapshot_cost_usd() call
        # here) - same single network round-trip as before this change, tokens
        # just ride along on the same response.
        usage_end = charon_cost.snapshot_usage()
        cost_usd = charon_cost.delta_str(
            meta.get("cost_start_usd"), usage_end.get("cost_usd") if usage_end else None)
        tokens_in = charon_cost.int_delta_str(
            meta.get("tokens_in_start"), usage_end.get("tokens_in") if usage_end else None)
        tokens_out = charon_cost.int_delta_str(
            meta.get("tokens_out_start"), usage_end.get("tokens_out") if usage_end else None)

        if finalize:
            meta["finalized"] = True
            meta["final_score"] = final_score
            meta["final_time_s"] = round(elapsed, 1)
            meta["final_corrections"] = corrections
            meta["final_cost_usd"] = cost_usd
            # TOKEN-CAPTURE: additive fields, "-" when unavailable - never crashes
            # a reader of an OLDER meta.json that predates these keys (.get()
            # with a default everywhere they're read).
            meta["final_tokens_in"] = tokens_in
            meta["final_tokens_out"] = tokens_out
        save(model, section, meta)

        print(json.dumps({
            "finalize": finalize,
            "corrections": corrections,
            "final_score": final_score,
            "time_s": round(elapsed, 1),
            "timed_out": timed_out,
            "cost_usd": cost_usd,
            "cost_method": meta.get("cost_method", "global"),
            # TOKEN-CAPTURE: new keys, additive - existing readers pick specific
            # keys by name (e.g. bench.sh's `jget`) so this can't break them.
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
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
    elif cmd == "is_active":
        cmd_is_active(args[1], args[2])
    else:
        print(f"unknown subcommand: {cmd}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
