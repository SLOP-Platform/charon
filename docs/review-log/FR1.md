# FR1 — first-run UX polish

Four fresh-user cliffs from the usability audit (2026-06-27):

1. **mock backend banner** — `charon work --backend mock` now prints a one-line banner explaining
   the mock makes no changes and how to use a real backend. NOTE: the exit code is left HONEST
   (a mock run whose validation holds still exits non-zero) — an earlier attempt to force exit 0
   broke `test_engine_e2e.py::test_work_cli_nonzero_when_validation_holds`, a deliberate
   "never report a silent pass" guard. The banner alone resolves the "looks broken" confusion
   without weakening that guard.
2. **gateway 502 hint** — the no-route 502 body now includes the remediation ("run `charon setup`
   / open `/charon/setup`"), not just the server log.
3. **`charon doctor` unconfigured** — exits 0 with `status: "no backend configured"` when no
   backend is set; a real probe failure of a configured backend still exits non-zero.
4. **README units-file example** — concrete `plan.json` with `accept` as a list.

Scope: cli.py, proxy_server.py, README.md + their tests. Boundary clean; stdlib core untouched.
