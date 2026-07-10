# SESSION — PROVIDER-PROBE-FIX: stop the /charon provider-add probe rejecting valid keys

**Model:** strong tier — targeted logic fix in a security-sensitive path (SSRF guard stays
intact), moderate size.
**Repo:** charon · **Ticket:** PROVIDER-PROBE-FIX
**Base branch/worktree:** `fix/provider-probe-validation` at
`/home/stack/code/charon-fleet-PROVIDER-PROBE-FIX` (an isolated worktree off latest
`origin/master` — do NOT work in the shared main tree `/home/stack/code/charon`).

## FIRST ACTS (mandatory)
1. `cd` into the worktree (create it off latest `origin/master` if absent).
2. `git fetch origin && git merge origin/master`; resolve conflicts; re-run tests after.
3. This ticket `depends_on: RESPONSE-ADAPTER-UNIVERSAL` (real-dep: shared gateway.py/
   providers.py writer) — confirm that ticket is merged before starting; if not, this ticket
   is not yet claimable.
4. Register on the session-bridge (`register`: your `session_id`, `repo: "charon"`,
   `ticket: "PROVIDER-PROBE-FIX"`, `status: "in-progress"`); heartbeat via `update`.

## FILES OWNED (touch only these)
- `src/charon/gateway.py`
- `src/charon/config.py`
- `src/charon/providers.py`
- `tests/test_config.py`

## THE TASK (what's broken)
`config.validate_provider_key` (config.py:448-508) is the probe behind `/charon provider-add`
(wired from `gateway.py`'s `make_setup_handler`, `providers` action, ~gateway.py:448-482).
It runs two probes:
1. `GET /models` (config.py:469-482) — counts `models_count` on success, but SWALLOWS any
   failure (`except Exception: pass`) and falls through regardless of outcome.
2. `POST /chat/completions {"model": ".", ...}` (config.py:484-508) — the REAL gate. Many
   providers correctly reject an unknown model id `"."` with HTTP 400 even when the key and
   base are perfectly valid.

The bug is in the `except urllib.error.HTTPError` branch (config.py:499-502):
```python
except urllib.error.HTTPError as exc:
    if exc.code in (401, 403):
        return {"valid": False, "message": f"key rejected (HTTP {exc.code})"}
    return {"valid": False, "message": f"probe failed (HTTP {exc.code})"}   # <-- BUG
```
A 400 (or any non-401/403 HTTP error) from the CHAT probe returns `valid: False`
UNCONDITIONALLY — even when `/models` already proved (via a 200 + parseable list) that the
key and base are completely valid. The generic `except Exception` branch below (line 503-508)
DOES check `models_count > 0` as a fallback, but that branch only fires for non-HTTPError
exceptions (timeouts, connection errors) — never for an `HTTPError` like the 400 this finding
is about. So a provider with a valid key that simply doesn't like `model="."` gets rejected,
and the operator is pushed toward an unsafe live bypass (skip validation entirely by editing
config files directly).

## REQUIRED CHANGE
1. **Treat a successful authenticated `/models` as sufficient validation on its own.**
   Restructure `validate_provider_key` so that if the `/models` probe returns HTTP 200 with a
   parseable model list (`models_count >= 0` from a well-formed response — don't require
   `> 0`, some providers return an empty catalog for a scoped key), that alone returns
   `valid: True` without needing the chat probe at all.
2. **Only run the chat probe as a fallback** when `/models` is unreachable/non-200/
   unparseable — and when it does run, pick a REAL model id from the `/models` response
   (if any were returned) instead of the placeholder `"."`, so a chat-capable provider isn't
   penalized for rejecting a nonsense model id.
3. **Fix the `except urllib.error.HTTPError` branch** so a non-401/403 chat-probe error
   (e.g. 400/404) checks `models_count` before declaring `valid: False` — mirror the existing
   `except Exception` branch's fallback logic (config.py:503-508) so both exception paths are
   consistent.
4. **Add an explicit `skip_probe` path.** In `gateway.py`'s `providers` action
   (~gateway.py:448-482) and in `config.validate_provider_key`'s caller, accept a
   `skip_probe: true` payload flag that bypasses BOTH probes entirely and persists the
   provider unvalidated — for operators with token-gated/limited-access keys where even
   `/models` isn't reachable pre-activation. Surface this in the returned `probe` dict (e.g.
   `{"skipped": True}`) so the caller/UI can show a "not validated" state, not silence.
5. **Do not touch the SSRF/redirect guards** (link-local/metadata host refusal at
   config.py:456-460, the `_NoRedirect` opener at config.py:462-466) — those stay exactly as
   they are. This is a validation-LOGIC fix, not a security-boundary change.

## ACCEPTANCE CRITERIA
- `PYTHONPATH=src python3 -m pytest tests/test_config.py tests/test_gateway.py tests/test_providers.py -q` green.
- **FAIL-ON-REVERT test (required):** a test that stubs an upstream returning 200 + a valid
  model list on `/models` but a 400 on `/chat/completions` (simulating a real provider that
  rejects `model="."`), and asserts `validate_provider_key` returns `valid: True`. It must be
  RED today (current code returns `valid: False` on the chat-probe 400), GREEN only with the
  fix, and RED again if the fix is reverted.
- A second test covering `skip_probe: true` end-to-end through the `providers` gateway action:
  provider is added with no network call made, and the response marks the probe as skipped.
- Existing tests for the 401/403 "key genuinely rejected" path must still pass unchanged —
  this fix narrows the false-negative, it does not weaken real-rejection detection.

## MERGE GATE (not pytest-alone)
FULL CI from the worktree, ALL green before this is merge-eligible:
`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`
Standard review (not money-path, but touches an auth/validation path — be precise about what
each probe branch returns).

## Dependencies & sequence
- **depends_on:** RESPONSE-ADAPTER-UNIVERSAL (real-dep: shared writer of gateway.py and
  providers.py — no functional coupling, purely file-collision avoidance). Confirm that
  ticket's merge before claiming this one.
- **Downstream:** PROVIDER-URL-HELPER `depends_on` THIS ticket (same real-dep pattern — it
  edits the same config.py URL-construction region this ticket touches). Land this cleanly so
  it can build on top.

## REPORT BACK (short — no diffs)
Files changed, test names, gate pass/fail, and the commit SHA.

## LAST STEP (REQUIRED) — commit, do not skip
```
git add -A && git commit -m "fix(gateway): treat successful /models probe as sufficient provider validation"
```
Report the commit SHA back to the manager.

do NOT push, do NOT open a PR, do NOT merge — the launcher publishes; the deny-list blocks push inside the session.
