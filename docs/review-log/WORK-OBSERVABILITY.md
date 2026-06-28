# WORK-OBSERVABILITY — make a `charon work` run visible while it runs

## What shipped (the two highest-value sub-goals)
1. **Live per-unit progress.** `Scheduler` gained an opt-in `progress:
   Callable[[str], None]` sink. As it drains it emits one short line per unit
   transition on the **main thread** (serial, so lines never interleave):
   `claimed` (in `_claim`), `started` (after `pool.submit`), then at settle
   `checkpoint N (verified a0, a1)` (when N>0) followed by the terminal
   disposition word (`done` / `retry` / `blocked` / `superseded`). The worker
   payload `_execute` was widened from `(status, note)` to
   `(status, note, checkpoints, verified)` so the checkpoint summary is built
   from the `RunResult` the runner already returns — no new ledger reads, no
   coordinator changes.
   - CLI (`_cmd_work`) routes the sink to **STDERR** (`[work] <line>`, flushed);
     **stdout stays the final JSON** for piping. Gated by `--progress/--quiet`
     (`_progress_enabled`): explicit flag wins, else ON for a TTY / OFF when
     stdout is redirected. `run_work` threads `progress` to the scheduler and
     emits `land:propose|hold` per DONE unit.
2. **Aggregate run view.** New `charon runs` (`run_status()`) rolls up the WHOLE
   last run from durable `.charon` state — `work-board.json` for every unit's
   state + `depends_on`, joined with each unit's per-unit ledger. **Purely
   read-only:** verified/remaining come from the LAST recorded checkpoint, NOT
   `Ledger.verified()`, which would *re-execute* every unit's acceptance commands
   (an observability view must never run the work it observes). A unit with no
   ledger still appears with its board state + empty ledger fields.

## Hard constraints honoured
- **Anti-dilution:** all of this lives ONLY in the opt-in engine/CLI path. Zero
  bytes added to the gateway per-request hot path.
- Progress → stderr; stdout unchanged. Lines are built from ids + check ids +
  status words only — never `note`, env, or a credential (asserted by
  `test_no_secret_strings_in_emitted_lines`).
- Agent/provider-agnostic; privileged core stays stdlib-only.

## Deferred to follow-on tickets (per the spec — NOT built here)
- **ACP transcript capture** to a per-unit log: needs `adapters/acp.py` (stderr
  currently → DEVNULL) — outside this ticket's `owns:`.
- **Work/board panel in the gateway / Mode-B UI:** needs `proxy_server.py` /
  `service/` — outside `owns:` and would touch the hot-path surface.

## Tests
`tests/test_work_observability.py`: scheduler lifecycle-line order incl.
checkpoint summary; silent without a sink; blocked/zero-checkpoint variants;
no-secret assertion; the `_progress_enabled` gating matrix; `_progress_sink`
writes stderr-only (stdout clean); `run_work` streams progress + land while
returning the unchanged report; `run_status` rolls up a 3-unit run (done /
blocked / never-ran) from durable state; `charon runs` prints JSON / exits 0;
no-run is loud. Existing scheduler + `run_work` tests stay green (609 passed).
