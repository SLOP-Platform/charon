repo: charon-private
tier: strong
difficulty: 1
work_class: ci-infra
branch: feat/leg-f6-realpath-test
depends_on: LEG-PREFLIGHT-CANARY
real-dep: LEG-PREFLIGHT-CANARY — closes a test gap in that ticket's own test; needs it landed first.
owns: fleet/tests/leg-preflight.test.sh
accept: |
  Close the VACUOUS fail-on-revert gap found in LEG-PREFLIGHT-CANARY review: the F6 "verbatim to gateway" assertions only
  exercise the LPF_PROBE_CMD stub argv path; the load-bearing real urllib call (leg-preflight.sh:233 `"model": leg`) is never
  run — stripping the suffix there still passes 22/22. DO: add an assertion that exercises the REAL urllib request path (or a
  fixture that captures the actual outbound payload) so reverting line 233's verbatim pin goes RED. Code is correct today; the
  GUARANTEE is what's missing.
