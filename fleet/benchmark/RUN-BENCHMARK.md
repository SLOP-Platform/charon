# RUN-BENCHMARK — self-drive instructions

Kickoff (paste this into a fresh opencode tab right after picking the model
with `/model`):

```
read this and execute: /home/stack/charon-private/fleet/benchmark/RUN-BENCHMARK.md
```

Everything below is what that agent (you — running AS the model being
benchmarked) then does, with no further input from the operator.

## Instructions

You are being benchmarked. Drive the harness at
`/home/stack/charon-private/fleet/benchmark/bench.sh` end to end:

1. Run: `/home/stack/charon-private/fleet/benchmark/bench.sh start`
   Read its output — it announces which model it thinks you are, plus the
   first section's task prompt and worktree path.
2. Implement that section's task yourself, directly in the printed
   worktree, using your own tools. Do not touch any other worktree or file
   outside the one printed.
3. When you're done, run:
   `/home/stack/charon-private/fleet/benchmark/bench.sh grade`
4. If it reports a correction round FAILED, fix the SAME worktree and run
   `bench.sh grade` again (capped at 3 rounds per section — after that it
   finalizes automatically, capped below the top band).
5. Once it reports a section's FINAL score, it automatically prints the
   next section's prompt + worktree if any remain — go back to step 2. If
   that was the last section (S6), it instead prints the final tier chart
   and the run is complete.
6. Keep looping (implement -> `bench.sh grade`) through every section
   (S0-S6) without asking the operator anything in between. When the tier
   chart appears, show it — it is the deliverable of this run: the
   per-section grade table plus ONE `OVERALL TIER: <name> — rank #N of M`
   line (or `NO TIER — too weak to place` if below the lowest floor, or
   `INVALID` if the S0 sanity gate wasn't clean).

Do not hand-type the model name (auto-detected from the opencode session),
and do not shuttle between sections yourself — `bench.sh` drives the queue.
See `README.md` in this directory for the full subcommand reference, the
composite/tier-ladder formula, and the legacy manual flow.
