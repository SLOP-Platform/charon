# BOUNCE-1: Egress Key Canary (REAL-SUT rebuild)

## Background

Rebuild of the rejected EGRESS-KEY-CANARY (2026-07-24). Prior attempt used a
hermetic stdlib fake decoupled from `src/charon` — it could not exercise the
actual header-forwarding exfil path. Re-briefed as BOUNCE-1 with a REAL-SUT
mandate.

## Implementation

**Owns:** `fleet/checks/egress-key-canary.sh`, `fleet/tests/egress-key-canary.test.sh`

### fleet/checks/egress-key-canary.sh

Spins up a real `src/charon` gateway subprocess (not a Docker container — Docker
daemon was not available; subprocess runs identical Python code). Attempts to
repoint a built-in preset provider (openrouter) to a non-preset external host
(`evil-regression-test.example.com`). Asserts `assert_base_allowed` rejects the
request with 400. Verdict `GREEN` on rejection, `RED` on acceptance.

### fleet/tests/egress-key-canary.test.sh

- **(H)** Healthy: runs the canary against real master — GREEN (allowlist blocks)
- **(R1)** Patches `egress.is_allowed_base` / `assert_base_allowed` to always
  allow (simulates reverting #181), starts a sink that records Authorization
  headers, creates a preset provider pointing at the sink, runs `models/import`,
  asserts the key reaches the sink — RED proof
- **(R1-revert)** Restores allowlist — GREEN again
- 7/7 pass, 0 fail

### Key design decisions

1. **REAL SUT**: Gateway runs as `python -m charon.cli gateway` subprocess
   (real `src/charon` code, not a mock/fake)
2. **NO hermetic decoupling**: The egress allowlist (`assert_base_allowed`) is
   exercised through real gateway.py:618 code path
3. **Fault simulation**: `charon.egress.is_allowed_base` monkey-patched to always
   return True, plus `assert_base_allowed` replaced with no-op — this exactly
   inverts the #181 allowlist guard
4. **Sink server**: Python stdlib HTTP server records Bearer tokens, responds
   with valid OpenAI `/v1/models` and `/v1/chat/completions` responses so the
   key validation probe does not fail
5. **skip_probe not needed**: The sink responds to both GET and POST, so the
   key probe succeeds naturally

## Adversarial review required

Security/key-exfil canary. Reviewer != builder. A false-GREEN here means the
standing regression guard for a provider-key exfil is itself broken.
