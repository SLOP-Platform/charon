## 2026-06-26 — feat/live-acp-handoff: integration shape (plan note, before code)

- **Branch:** `feat/live-acp-handoff`
- **Constraint:** own only `adapters/acp.py` and `doctor.py`; extend
  `tests/test_handoff_crossvendor.py` (integration/proof) and
  `tests/test_handoff.py` (unit). No other source files touched.
- **What this is NOT:** a change to coordinator, Ledger, or handoff logic — those
  are proven complete via mock. This closes the honesty gap recorded at OOB2-1:
  live ACP subprocess dispatch replaces MockBackend in the proof.

### Integration shape

**`adapters/acp.py`** — expose `last_session_id: str | None` (set after each
`session/new`). Zero behavioral change; surfaces the ACP session context for
probe reporting and future resume logic.

**`doctor.py`** — add:
- `HandoffReport` dataclass (parallel to `DoctorReport`): `cmd_a`, `cmd_b`,
  `a_dispatched`, `b_dispatched`, `handoff_completes`, `notes`, `.ok`.
- `probe_handoff(cmd_a, cmd_b, *, env_a, env_b) -> HandoffReport` — two-backend
  probe using the raw `_start`/`_rpc` surface (same depth as the existing
  single-backend `probe()`). Phase A: initialize → session/new →
  session/prompt (goal: create `handoff-a.txt`). Phase B: same on the shared
  tmp dir (goal: create `handoff-b.txt`; prompt names A's artifact so a real
  agent sees what is done). Checks both files exist. No Ledger, no git needed.

**`tests/test_handoff_crossvendor.py`** — live integration proof (two new tests):
- `test_live_acp_crossvendor_handoff`: writes two Python ACP stubs (stdlib;
  no keys) to tmp_path, creates `AcpBackend` instances pointing at them, runs
  `coordinator.run()` via real ACP subprocess dispatch. Stub A creates
  `handoff-a.txt` then emits a `session/update` with `rate_limited: true` (the
  H4 exhaustion signal absorbed by `health()`) before returning success. Stub B
  creates `handoff-b.txt` and completes. Asserts: `res.status == "complete"`,
  `led.provider_history == ["stub-a", "stub-b"]`, both files exist, `lkg_ref`
  advanced.
- `test_live_doctor_probe_handoff`: calls `probe_handoff` with the same stubs;
  asserts `rep.ok`.

**`tests/test_handoff.py`** — unit coverage for the new probe entry points:
- `test_doctor_probe_handoff_no_cmds`: `probe_handoff(None, None).ok == False`.
- `test_doctor_probe_handoff_missing_exe`: bad exe → `a_dispatched == False`.

### Why the proofs are not tautological

1. Stubs speak real ACP over stdio — distinct from the coordinator and
   exercising the actual `AcpBackend._rpc` framing.
2. Exhaustion is signalled via the `session/update` `rate_limited` field
   absorbed into `health()` — the real code path, not a `MockBackend` override.
3. `provider_history` accumulates through real `ledger.record_provider` calls.
4. `lkg_ref` advances only when both acceptance shell checks pass on disk.

### Gate (every commit)
`pytest`, `ruff check`, `mypy src/charon`,
`python3 tools/check_boundary.py src`, `python3 tools/check_version.py`.
