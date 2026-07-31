CI-robustness fix (test-only). The gateway tests bind a FIXED port (8080), so on the shared 4-lom
self-hosted runner they fail with `OSError: [Errno 98] Address already in use` whenever ANYTHING
else holds 8080 — a leftover `charon gateway`, a running Docker container, or a concurrent CI job.
This already bit the #65 (RELEASE-SMOKE-FIX) and #66 (DOCS-TWO-MODE) CI runs; freeing 8080 by
`docker compose down` on 4-lom unblocked them, but that is a manual band-aid, not a fix. Make the
tests bind an EPHEMERAL port so they can NEVER collide on a shared runner.

ROOT CAUSE: `GatewayConfig.port` defaults to `_DEFAULT_PORT = 8080` (`src/charon/gateway.py`), and
the offending tests construct a server WITHOUT overriding the port — so `build_server` →
`GatewayProxyServer` calls `super().__init__((host, 8080), …)` and binds the fixed port. The fix is
to bind port 0 (the OS assigns a free ephemeral port) and read the ACTUALLY-bound port back via
`server.server_address[1]`. The plumbing for this ALREADY EXISTS: `GatewayProxyServer.url`
(`src/charon/proxy_server.py` ~:790) already computes its URL from `self.server_address[1]`, and
the tests already reach the live server through `server.url` (not a hardcoded `:8080`), so once the
config asks for port 0 the rest flows through unchanged. (The mock UPSTREAM helper `_mk_upstream`
in `tests/test_gateway.py` already does exactly this — `_Threaded(("127.0.0.1", 0), …)` then
`srv.server_address[1]` — mirror that pattern for the gateway server too.)

READ FIRST (master, by `git show origin/master:<path>`):
- `tests/test_gateway.py` — `_mk_upstream`/`_req` helpers (already port-0 for the upstream) and the
  two offenders `test_models_endpoint_and_token_gate` (builds `GatewayConfig(token=…, routes=…,
  model_ids=…)` then `gateway.build_server(cfg)` + `server.serve_in_thread()`) and
  `test_gateway_forwards_chat_completions_end_to_end` (same shape, with `_mk_upstream`).
- `tests/test_gateway_tiers.py` — `test_setup_tiers_branch_persists_and_reloads`, which gets its cfg
  from `gateway.load_config(state_dir=home)` (so it inherits the 8080 default) then
  `gateway.build_server(cfg, setup_dir=home)`.
- `src/charon/gateway.py` — `_DEFAULT_PORT`, `GatewayConfig` (regular mutable dataclass), `build_server`.
- `src/charon/proxy_server.py` — `GatewayProxyServer.__init__` (binds `(host, port)`) and the `url`
  property (reads `server_address[1]`).

BUILD — own ONLY the test files (`tests/test_gateway.py`, `tests/test_gateway_tiers.py`; add a tiny
`tests/conftest.py` helper ONLY if it removes real duplication — PROVISIONAL, prefer editing the
tests directly):
- For the three offenders, make the gateway server bind port 0:
  - `test_models_endpoint_and_token_gate` + `test_gateway_forwards_chat_completions_end_to_end`:
    pass `port=0` into the `GatewayConfig(...)` constructor.
  - `test_setup_tiers_branch_persists_and_reloads`: the cfg comes from `load_config`; override the
    port before `build_server` (e.g. set `cfg.port = 0`, the dataclass is mutable — confirm it is
    not frozen).
- Do NOT change any `:8080` literal into another fixed number — the point is port 0 + read-back.
- Every assertion must keep reaching the server via `server.url` (which already resolves the bound
  ephemeral port). Do NOT hardcode `localhost:8080` anywhere.
- Sweep both files (and grep the rest of `tests/`) for any OTHER spot that builds a gateway/proxy
  server on a fixed port and give it the same port-0 treatment; if you find none beyond these three,
  say so in the review note.

CONSTRAINTS:
- TEST-ONLY. Do NOT touch `src/` or any product file — `_DEFAULT_PORT` stays 8080 (that is the
  correct PRODUCT default; only the TESTS must not pin it). If a green fix appears to need a src/
  change, STOP and surface it with a reason — do not edit src/.
- No SLOP / fleet / rig / `charon-private` leak into the repo.
- Agent/provider-agnostic; minimal diff.
- Tests must still pass. Gate green: `pytest`, `ruff`, `mypy`, `check_*`. Conventional commits.
- Review note → `docs/review-log/TEST-PORT-FLAKE.md` (note the #65/#66 8080 collision this fixes).
- Commit ALL work and STOP — no push / PR / submit.sh (the manager gates + merges).

## REPORT BACK — MECHANIZED FORMAT (required)
End your session by emitting EXACTLY this block. Fixed fields, one line each, no diffs or logs.
Validate it before you finish: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Full spec + rationale: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`

```
=== SESSION REPORT v1 ===
TICKET:       <ticket-id>
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha> | none
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> is owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> | n/a — <why> | NOT-DONE
OBSERVABLE:   MET | DEFERRED — <what could not be observed and why>
RAN:          <what you proved by EXECUTING>
READ:         <what you concluded by READING only>
BRIEF-ERRORS: none | <what this brief got factually wrong>
BLOCKED-BY:   none | <ticket or condition>
BUDGET:       ok | TRUNCATED — <what you could not finish and why>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
