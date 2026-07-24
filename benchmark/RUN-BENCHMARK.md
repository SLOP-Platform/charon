# RUN-BENCHMARK — self-drive instructions

Kickoff (paste this into a fresh opencode tab right after picking the model
with `/model`):

```
read this and execute: /home/stack/charon-private/fleet/benchmark/RUN-BENCHMARK.md
```

Everything below is what that agent (you — running AS the model being
benchmarked) then does, with no further input from the operator.

**RECOMMENDED: pass `--model <id>` explicitly on `start` too** — you already
know your own model id from the `/model` the operator just ran (it's the
model you ARE). Auto-detect (`start` with no `--model`) reads
`~/.local/share/opencode/opencode.db` for the most-recently-updated
opencode session, which can misdetect whenever ANY other opencode tab is
concurrently active — most likely right after an opencode restart (a
restored prior session can look "freshest") or whenever more than one tab
is open at once (this rig's normal mode). See `bench-model-misdetect`,
`fleet/reds.tsv`, for the confirmed incident: auto-detect announced the
WRONG model, saw it already finalized, and silently skipped the run with no
error. `lib/detect_model.py` now refuses to guess when it sees this
ambiguity (fail loud instead of silently wrong) — but `--model` sidesteps
the whole class of failure and is always reliable:

```
/home/stack/charon-private/fleet/benchmark/bench.sh start --model <the model you ARE>
```

## Instructions

You are being benchmarked. Drive the harness at
`/home/stack/charon-private/fleet/benchmark/bench.sh` end to end:

1. Run: `/home/stack/charon-private/fleet/benchmark/bench.sh start --model <your-model-id>`
   (use plain `bench.sh start` with no `--model` only if you don't yet know
   your own model id — but VERIFY the result, see below).
   Read its output — it announces which model it thinks you are (the
   `ANNOUNCE: running this benchmark AS model = <id>` line, followed by a
   `STOP - VERIFY` block). **Before implementing anything, confirm `<id>`
   really is the model YOU just picked with `/model` in THIS tab.** If it is
   NOT (auto-detect guessed wrong, or refused with an "AMBIGUOUS" error),
   stop and re-run with the explicit override:
   `bench.sh start --model <your-model-id>`.
   **Remember that exact `<id>` string for the rest of this run** — you'll
   pass it back explicitly on every subsequent step (see the note on
   concurrent tabs below).
2. Implement that section's task yourself, directly in the printed
   worktree, using your own tools. Do not touch any other worktree or file
   outside the one printed.
3. When you're done, run:
   `/home/stack/charon-private/fleet/benchmark/bench.sh grade --model <id>`
   — using the EXACT model id from step 1's ANNOUNCE line, not re-typed
   from memory or guessed. (If you omit `--model`, it falls back to
   whichever model a shared on-disk pointer last recorded, which can be
   silently overwritten by a DIFFERENT concurrent bench.sh tab on this same
   box — always pass `--model` explicitly; see `fleet/reds.tsv`
   `bench-run-collision` for the incident this fixes.)
4. If it reports a correction round FAILED, fix the SAME worktree and run
   `bench.sh grade --model <id>` again (capped at 3 rounds per section —
   after that it finalizes automatically, capped below the top band).
5. Once it reports a section's FINAL score, it automatically prints the
   next section's prompt + worktree if any remain — go back to step 2. If
   that was the last section (S6), it instead prints the final tier chart
   and the run is complete.
6. Keep looping (implement -> `bench.sh grade --model <id>`) through every
   section (S0-S6) without asking the operator anything in between. When
   the tier chart appears, it is the deliverable of this run: the
   per-section grade table plus ONE `OVERALL TIER: <name> — rank #N of M`
   line (or `NO TIER — too weak to place` if below the lowest floor, or
   `INVALID` if the S0 sanity gate wasn't clean). **Paste that printed
   table/chart verbatim as your final output — do NOT re-type, reconstruct,
   or re-render your own version of it.** `bench.sh` already printed it
   exactly once, automatically, the moment the last section finalized; it
   is the single canonical source (`lib/tier_chart.py`). If you need to
   reprint it for any reason, run
   `bench.sh chart <id>` — never hand-render your own copy.

You already know the model name (it's the one you ARE, from `/model`) — pass
it via `--model` on every step per above rather than relying on auto-detect.
Do not shuttle between sections yourself — `bench.sh` drives the queue
automatically once each section is graded.

**Re-running a model that's already fully finalized** (e.g. moving it to v2
scoring): `bench.sh start`/`grade` treat 7/7 finalized sections as "run
complete" and just print the tier chart — they will NOT overwrite finalized
data. To force a clean re-run, the OPERATOR (not the agent, mid-loop) runs
`bench.sh reset --model <id>` first, which backs up then clears that one
model's state, then restarts the kickoff above. See `README.md` for the
`reset` subcommand's exact guarantees.

See `README.md` in this directory for the full subcommand reference, the
composite/tier-ladder formula, and the legacy manual flow.

## Out-of-band grading (grader-daemon) — TRUST BOUNDARY

Real-task grading (reds-replay, real sub-session actuals) is performed
OUT-OF-BAND by the **grader-daemon** running as the dedicated ``bench-grader``
unix user. You (the graded agent) are NOT the grader and CANNOT self-grade.

**The agent must NOT:**
- Read files under ``/home/bench-grader/keys/`` — permission-denied by design.
- Write to ``/var/lib/bench-grader/spool/req/`` directly — bench.sh does that.
- Append rows to ``model-scorecard.tsv`` — owned by bench-grader, unwritable
  by the agent.
- Attempt to execute graders or check_cmds — these live out of your reach.

**What the agent DOES:**
- Drive ``bench.sh start`` / ``bench.sh grade`` as before.
- ``bench.sh grade`` drops a request into the daemon's spool (write-only from
  the agent's perspective) and polls for the result. The daemon — not you —
  runs the grader, records the score, and appends to the ledger.

**Scorecard artifacts:** The daemon writes **versioned, append-only**
``scorecard.v{n}.json`` artifacts in ``fleet/benchmark/``. These are NEVER
imported by product code. Consumers read frozen artifacts only. The version
number (``scorecard.version``) increments when grading logic changes.
This is the RED-TEAM FIX #2 artifact seam — collapsing it (removing versioning
or making the artifact product-importable) breaks the trust boundary and is
caught by ``selftest/test_grader_daemon.py``.

**Daemon lifecycle:** Started by the operator as ``bench-grader`` once
(substrate setup in ``fleet/ADR-BENCH-OOB-GRADING.md`` §5). The agent never
starts, stops, or touches the daemon.
