Fix four fresh-user first-run UX cliffs found in the usability audit. These are SMALL, mechanical
quality-of-life fixes — better messages / exit codes / a doc example. Do NOT change core behavior
beyond what each item says. Canonical tier: **med** (fleet `sonnet`).

CONTEXT: a stranger who `pipx install`s Charon hits confusing dead-ends on the work-engine path.
Each fix below makes a command guide the user instead of dumping a scary error. Read the current
code at the cited locations first.

FIX 1 — `charon work` with the default `mock` backend reads as total failure (CLIFF 3).
- Today: `charon work --units plan.json` with the default `mock` backend exits **1**, every unit
  `"decision":"hold"` / `"holds":["no committed changes between base and tip — nothing to land"]`.
  The mock backend writes nothing, so a valid run looks broken.
- Fix (in `src/charon/cli.py`, the `work`/`run_work` path): when the backend is `mock`, print a
  one-line banner BEFORE the run, e.g. `mock backend makes no changes — pass --backend acp
  --acp-cmd '<agent> acp' for real work`. AND do not exit non-zero when the only reason for
  hold/failure is a mock no-op (a mock run that completes its units should exit 0). Keep real
  (non-mock) exit semantics unchanged.

FIX 2 — gateway returns a dead-end 502 to the client when unconfigured (ROUGH 4).
- Today: a client pointed at a fresh gateway gets `502 {"error":{"message":"no route for model
  'auto'"}}`; the remediation only appears in the server log the client user never sees.
- Fix (in `src/charon/proxy_server.py`, the no-route/error response body): append a remediation
  hint to the error message, e.g. `no route for model 'auto' — no providers configured; run
  'charon setup' or open http://127.0.0.1:8080/charon/setup`. Keep the 502 status; just enrich the
  JSON body message.

FIX 3 — `charon doctor` (no backend configured) exits 1 with scary all-false JSON (ROUGH 5).
- Today: `charon doctor` with nothing configured returns `"spawned":false,"initialized":false,…`
  and exits **1** — reads as broken when it just means "no ACP backend to probe."
- Fix (in `src/charon/cli.py`, the `doctor` command): when simply UNCONFIGURED (no backend),
  exit **0** and lead the output with a clear `"status":"no backend configured"` (keep the
  detailed fields). A genuine probe FAILURE of a configured backend still exits non-zero.

FIX 4 — README units-file example (ROUGH 6).
- Today: the README shows the units shape `{goal, accept, tier, owned_paths}` but no concrete
  example, and a user who writes `"accept":"true"` (string) is rejected with `needs a non-empty
  'accept' list of commands`.
- Fix (in `README.md`): add a short, concrete units-file example near the work-engine/`charon
  work --units` section showing `accept` as a LIST, e.g.
  `{"goal":"...","accept":["pytest -q"],"tier":"sonnet","owned_paths":["src/foo.py"]}`.

CONSTRAINTS: own ONLY src/charon/cli.py, src/charon/proxy_server.py, README.md,
tests/test_cli.py, tests/test_proxy_server.py. Add/adjust tests in those two test files to cover
the new exit codes / messages (mock-banner + exit-0, doctor exit-0-when-unconfigured, the enriched
502 body). Do NOT touch intake.py, api.py, acp.py, or any other file (other tickets own those) —
if a fix seems to need one, STOP and run release.sh with a one-line reason. Gate green every
commit (pytest, ruff, mypy src/charon, check_boundary, check_version, check_decisions). Stdlib
core only. Conventional commits. Write your review note as `docs/review-log/FR1.md`. Commit ALL
work on your branch and STOP — do NOT push / open a PR / run submit.sh; the launcher publishes
after you exit.
