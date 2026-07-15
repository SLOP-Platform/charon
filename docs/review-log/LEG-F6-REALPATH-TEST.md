# LEG-F6-REALPATH-TEST — Review Log

## Ticket
LEG-F6-REALPATH-TEST: close the vacuous F6 fail-on-revert gap in
LEG-PREFLIGHT-CANARY's test — the F6 "verbatim to gateway" assertion only
exercised the LPF_PROBE_CMD stub argv path; the load-bearing real urllib call
(leg-preflight.sh:233 `"model": leg`) was never run.

## What was done

Added section `(i)` to `fleet/tests/leg-preflight.test.sh`. The new section
exercises the REAL `urllib.request` path in `leg-preflight.sh:232-247` (the
branch the existing (a)-(h) tests skip entirely by setting `LPF_PROBE_CMD`).

### Mechanism
- A local Python `http.server.HTTPServer` is spawned on `127.0.0.1:<random free port>`
  in a background subshell. It writes every inbound POST body to a capture file
  (`$D/real-urllib-capture.ndjson`, NDJSON) and replies with task-appropriate
  canned completions (correct `is_bal` code for the bal-parens task, `120` for
  the lcm-bound exact-answer task). Stdlib only — no `pip install`.
- `leg-preflight.sh` is then invoked with `LPF_GATEWAY_URL` pointed at the local
  server and a fake `LPF_TOKEN`; `LPF_PROBE_CMD` is explicitly UNSET so the
  script falls into the `urllib.request.Request(...)` branch, not the stub
  argv branch. (a)-(h) all use `run_lpf` which sets `LPF_PROBE_CMD` — they
  literally never reach line 233.
- Five assertions:
  1. `leg-preflight.sh` exits 0 (the urllib path drove a successful canary end-to-end).
  2. The fake gateway received ≥1 inbound POST (urllib branch was reached, not the stub).
  3. **Load-bearing PIN**: every captured body, JSON-parsed, has `model == "goodmodel-ds"`
     VERBATIM. If `leg-preflight.sh:233` is reverted to `SPLIT_MODEL` or any
     stripped/normalized value (`leg.split("-")[0]`, `leg.rsplit("-", 1)[0]`,
     `leg.replace("-ds", "")`, etc.) this assertion goes RED.
  4. **Anti-revert guard**: no captured body has `model == "goodmodel"` (the bare
     SPLIT_MODEL) — even if a future change somehow re-adds the suffix, this
     catches the most-likely careless reverts that drop the suffix outright.
  5. End-to-end: the leg's rank row in `LEG-RANK.tsv` is `HEALTHY` (proves the
     urllib path drove the canary scoring through `exec_check.py` + the exact-match
     check all the way to a verdict, not just "sent a request").

### Revert-detection verified

Tested three realistic reverts of `leg-preflight.sh:233`:
- `"model": leg.split("-")[0]` (gives `"goodmodel"`) → 2/5 (i) assertions go RED.
- `"model": leg.rsplit("-", 1)[0]` (gives `"goodmodel"`) → 2/5 (i) assertions go RED.
- `"modell": leg` (field-name typo) → 1/5 (i) assertion goes RED (the load-bearing
  one, which parses `d.get("model", "")` and expects the verbatim leg id).

In all three cases, the (a)-(h) tests still all pass — they cannot detect
this revert because they only exercise the LPF_PROBE_CMD stub argv path.

## Files
- `fleet/tests/leg-preflight.test.sh` (the ONLY file modified — matches ticket `owns:` exactly).

## Gate status
- `bash fleet/tests/leg-preflight.test.sh` → 28 passed, 0 failed (was 22 before this ticket).
- `PYTHONPATH=src python3 -m pytest -q` → 54 passed (no regression).
- Bash syntax check: `bash -n fleet/tests/leg-preflight.test.sh` → OK.

## Notes
- The 18 ruff errors and 1 mypy error visible on `master` are pre-existing and
  unrelated to this ticket; they are in `fleet/benchmark/grader-daemon.py` and
  the `tests:` namespace. Per ticket ownership, I did not touch any of them.
- The new test (i) is fully hermetic: no live network, no `~/.config/opencode/`
  reads (the script's token-fallback path is bypassed by setting `LPF_TOKEN`
  directly), no external services, no `pip install`. The local server is killed
  on EXIT via the existing `trap` (extended to also kill the server PID).
- The fake gateway's "task-appropriate" response dispatch is a simple substring
  match on the prompt text (`"is_bal" in prompt` for coding, `"divisible by both 6 and 15"`
  for the exact task). This is sufficient for the canary to score HEALTHY on
  the test leg and is hermetic — no real model is invoked.
