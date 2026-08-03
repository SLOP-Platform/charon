repo: charon
tier: strong
priority: 0
difficulty: 2
work_class: money-path
branch: fix/auth-302-silent-failure
depends_on:
owns: src/charon/proxy_server.py, tests/test_auth_302_silent_failure.py
serial_justified: |
  One auth branch, one decision. Splitting the browser case from the script case is how the two
  drift apart — and their INTERACTION is the entire defect.
substrate: N/A
substrate-novel: |
  No tool to adopt. This is a 5-line correction to an auth branch in our own HTTP handler; the
  correct behaviour is already implemented CORRECTLY ten lines away on the /v1/* path
  (proxy_server.py:441-443 always answers 401), so the fix is to make the console path agree
  with the data path — not to introduce anything new. RFC 7235 already says an unauthenticated
  request to a protected resource gets 401; no library is needed to follow it.
source: |
  Operator, 2026-08-02, after a manager session burned time on it - "any way to fix the trap
  that unauthenticated and stale-token requests both return 302?"
note: |
  ## THE DEFECT — `src/charon/proxy_server.py:399-405`
  ```python
  if not (authed_by_token or authed_by_session):
      if is_gui and self.command == "GET":
          self._redirect("/charon/login")     # 302, zero-byte body
      else:
          self._json(401, {"error": {"message": "missing or invalid bearer token"}})
  ```
  The redirect fires on `is_gui and GET` alone — it never asks whether the caller is a BROWSER or
  a SCRIPT. So a programmatic client hitting `/charon/status` gets a login redirect instead of an
  auth error.

  ## WHY IT IS WORSE THAN AN ERGONOMIC WART
  MEASURED 2026-08-02, all three verified live against the gateway:
    - unauthenticated `GET /charon/status` -> **302, size_download=0**
    - STALE-token `GET /charon/status`     -> **302, size_download=0**  (byte-identical)
    - `curl` exits **0** for both.
  Three distinct outcomes — no credential, wrong credential, success — collapse into one
  indistinguishable signature for any script that does not explicitly assert `%{http_code}`.
  A manager session lost real time to exactly this: it derived a token, got the 302/0-byte
  response, and could not tell "my token is stale" from "the endpoint is fine". It then
  mis-attributed the failure and moved on with a wrong conclusion.
  This is the same class as `head -c 60 && echo OK` exiting 0 on empty input, and as
  "could not check" sharing an exit code with "nothing wrong" — a failure that is
  INDISTINGUISHABLE FROM SUCCESS is the most expensive kind this rig has.
  It is money-path because `/charon/status` is how spend, pool and provider state are read; a
  script silently reading nothing will conclude "no providers parked" just as confidently as one
  that actually read the truth.

  ## THE RULE — a presented credential that is REJECTED must never be answered with a redirect
  A 302 says "go authenticate interactively". That is right for a browser with no session. It is
  WRONG for any caller that already presented a credential: that caller is programmatic by
  construction, and the honest answer is 401.
  | caller | today | required |
  |---|---|---|
  | script, NO token | 302 + 0 bytes | **401 JSON** |
  | script, STALE/invalid token | 302 + 0 bytes | **401 JSON** |
  | browser, no session | 302 login | 302 login (UNCHANGED) |
  Decision procedure, in order:
    1. `Authorization` header present but invalid -> **401 JSON, always**. No exceptions.
    2. No credential AND `Accept:` contains `text/html` -> 302 login (real browser).
    3. Otherwise -> **401 JSON**.
  Prefer the Authorization-header test as the PRIMARY signal; `Accept` is a hint and some
  browsers send `*/*`, so it must not be the only discriminator.

  ## DO NOT REGRESS THE BROWSER UX
  The redirect exists for a real reason, stated in the code: "A browser hitting the console gets a
  login page, not raw 401 JSON." Keep that. The fix NARROWS when the redirect fires; it must not
  remove it. A test must prove the browser path still redirects.

  ## RELATED, DO NOT CONFLATE
  `/v1/*` is already CORRECT (`proxy_server.py:441-443` always 401, and refuses session-cookie
  auth on the data plane entirely). Do not touch it. This ticket makes the CONSOLE path agree
  with the DATA path.
accept: |
  a. The three-branch decision above is implemented at `proxy_server.py:399-405`.
  b. RED-PROOF, each SEEN to fail then pass, hermetic (no live gateway):
       - no Authorization header + `Accept: application/json` -> 401 with a JSON error body.
       - INVALID Authorization header + any Accept -> 401. Revert -> 302, test RED.
       - no credential + `Accept: text/html` -> 302 to /charon/login (browser UX preserved).
       - valid token -> 200. ANTI-OVER-FIX: proves the change did not break the success path.
  c. Assert on the BODY as well as the status: a 401 must carry a parseable JSON error. A
     zero-byte 401 would reintroduce the same ambiguity one layer down.
  d. `/v1/*` behaviour is UNCHANGED — assert it explicitly so this fix cannot drift into the
     data plane.
  e. A client-side companion, because the server fix does not retro-fix existing scripts: add the
     status-code assertion to the rig's gateway probes so a 302 can never again read as success.
     Grep for gateway `curl` call sites that lack a `%{http_code}` / `-f` check and fix them.
scope: |
  The console auth branch and its tests, plus the rig-side probe hardening in (e). Does NOT
  change token derivation, session signing, the /v1 data plane, or any provider config.

## Dependencies & Sequence

- **depends_on: none.**
- No owns-collision: verified against the live board 2026-08-02 — no live ticket owns
  `src/charon/proxy_server.py`.
- Cheap and high-leverage: every future script that reads gateway state depends on being able to
  tell a stale token from a healthy endpoint. Land before building anything that polls
  `/charon/status` — including the cron/liveness work.
