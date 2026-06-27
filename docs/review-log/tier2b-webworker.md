## 2026-06-26 — Tier 2b: web/worker split — queue/worker boundary (plan note, before code)

Scope: `src/charon/service/app.py` (enqueue) + new `src/charon/service/worker.py`
(privileged drain). Reconciled HERE before any implementation commits, per
ADR-0002 §2.3 / INV-B4 / PLAN-tier2.md §8.

**What is being built:**
- `POST /v1/runs` graduates from 501 → 202 Accepted. The web process validates
  the request (Pydantic), writes one JSON job file into a filesystem queue
  (`CHARON_QUEUE_DIR/pending/<job_id>.json`), and returns the job id.
- `service/worker.py` is a separate process that polls `queue/pending/`, moves
  each job to `queue/running/`, calls `api.run_task`, and archives the result to
  `queue/done/` (or `queue/failed/`). This is the ONLY process that may call
  `run_task` / `coordinator`.

**Boundary invariant (INV-B4, structural):** `service/app.py` must NEVER
reference `run_task`, `coordinator`, or `dispatch` as AST Name or Attribute
nodes. `tests/test_boundary.py::test_service_app_runs_no_privileged_loop_in_process`
enforces this on every gate run. The new enqueue code uses only `uuid`,
`json`, `pathlib.Path`, and `os.environ` — zero privileged-exec symbols.

**Queue design (filesystem, stdlib-only, no broker):**

```
CHARON_QUEUE_DIR/
  pending/<job_id>.json    — written by web process; job awaits pickup
  running/<job_id>.json    — moved atomically by worker on pickup (rename)
  done/<job_id>.json       — written by worker on success (result folded in)
  failed/<job_id>.json     — written by worker on error (error field added)
```

Rename-to-running is the atomic claim: if two worker instances race for the
same file, only one rename wins; the loser catches `OSError` and skips to the
next file. This gives at-least-once semantics under a single worker and safe
no-duplicate execution under multiple workers without a broker.

**Job record schema (web process writes; worker reads):**
```json
{ "job_id": "<hex32>", "goal": "...", "accept": ["..."],
  "autonomy": "L0", "budget": 8 }
```
`repo` is deliberately absent: the worker always runs in an auto-created sandbox
(`api.run_task` with `repo=None`), so a caller cannot direct a run at an
arbitrary host path. This is the path narrowing called out in PLAN-tier2.md §8
("request shape drops `repo`").

**503 when queue not configured:** If `CHARON_QUEUE_DIR` is unset, the web
process returns 503 (queue not configured) rather than silently falling back to
a default path; the operator must configure the shared volume path explicitly.
This avoids a split-brain where the web process and worker use different dirs.

**Security surface review (self-review):**

- **[INV] No privileged symbols in web process** — structural (AST gate). ✓
- **[MED] Job file path traversal** — job_id is `uuid4().hex` (hex chars only,
  32 chars), written directly as the filename by the web process. The worker
  reads from the queue dir only; it never interpolates job fields into
  filesystem paths outside the queue. No traversal vector.
- **[MED] Goal/accept injection** — `goal` and `accept` are passed through
  verbatim to `api.run_task`. Acceptance checks already run with `shell=False`
  (AcceptanceCheck design); the worker is the privileged process by design (it's
  behind the network boundary, not exposed). No new injection surface vs the CLI.
- **[LOW] Queue dir permissions** — `CHARON_QUEUE_DIR` is operator-configured;
  should be mode 0700, writable only by the service user. Not enforced in code
  (same posture as `.charon/` state dir). Document in deploy guidance.
- **[LOW] Result file bloat** — done/failed files accumulate indefinitely.
  Acceptable for Tier 2b (single operator, bounded volume); a pruner is future
  work. Worker logs a warning if queue exceeds a threshold (future).
- **Verified-correct (kept):** token gate on POST /v1/runs unchanged (existing
  `require_token` dependency); `autonomy` field validated by existing Pydantic
  model; no new network calls in the web process; no secrets written to queue.

**Test coverage plan:**
- `test_service_api.py`: `_enqueue` writes correct job file; unique job_ids;
  503 when queue dir absent; HTTP 202 round-trip (requires `[service]` extra,
  guarded with `pytest.importorskip`).
- `test_service_main.py`: worker `main()` exits 2 without `CHARON_QUEUE_DIR`;
  `_poll_once` on empty queue returns False; `_poll_once` picks up a job, calls
  run_task (mocked), archives to done/; `_poll_once` tolerates a malformed
  job record (moves to failed/, does not crash).

**Files touched:** `service/app.py`, new `service/worker.py`,
`tests/test_service_api.py`, `tests/test_service_main.py`,
`docs/REVIEW-LOG.md`. No other files.

- **Net:** plan accepted. Gate follows after implementation. All boundary
  invariants preserved by design (structural AST check + no new imports of
  privileged symbols in the web process).
