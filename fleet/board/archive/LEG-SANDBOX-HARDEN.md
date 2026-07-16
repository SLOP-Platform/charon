repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/leg-sandbox-harden
depends_on: LEG-PREFLIGHT-CANARY
real-dep: LEG-PREFLIGHT-CANARY — hardens the sandbox that ticket builds; needs it landed first.
owns: fleet/leg-preflight.sh, fleet/tests/leg-sandbox-isolation.test.sh
accept: |
  SECURITY (adversarial review of LEG-PREFLIGHT-CANARY): the canary sandbox enforces rlimits+timeout but has NO network
  or filesystem-read isolation — a hostile payload can read ~/.config/opencode/opencode.json (the GATEWAY TOKEN) and open
  outbound sockets = credential-exfil vector; FSIZE=0 blocks bytes not file CREATION. Out of the original threat model but
  REAL for a money-adjacent gate. DO: add network + fs-read isolation (unshare namespaces / seccomp / bwrap) OR, if that is
  not portable, a DOCUMENTED explicit threat-model disclaimer + minimize token exposure to the sandboxed exec.
  FAIL-ON-REVERT (fleet/tests/leg-sandbox-isolation.test.sh): a payload that reads the token file / opens a socket is BLOCKED
  (revert isolation -> exfil succeeds -> test fails).
