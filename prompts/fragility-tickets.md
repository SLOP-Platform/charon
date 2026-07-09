# FRAGILITY-TICKETS — Turn fragility sweep findings into individual board tickets

## Context
The fragility sweep sub-session (HANDOFF-2026-07-04-v2 §"Sub-session outputs" #1) returned
a ranked list of 10 hotspots. Five of them need individual fleet board tickets created.

## Tickets to create

### 1. PROVIDER-PROBE-FIX (fragility finding #4)
- tier: strong
- owns: src/charon/gateway.py, src/charon/config.py, src/charon/providers.py
- scope: The /charon provider-add probe validates by sending a chat request with
  `"model": "."` — many providers reject this with 400 even when the key/base are valid.
  Treat successful authenticated /models as sufficient; if chat is needed, choose a real
  model from /models. Add a skip_probe path for operators with token-gated access. Keep
  SSRF/redirect guards.

### 2. ACTION-PIN-POLICY (fragility finding #3, decision #7)
- tier: economy
- owns: .github/workflows/*.yml
- scope: Allow major-version tags for trusted first-party actions/* (@v4, @v5); keep
  strict SHA pins for third-party actions (docker/*, attest/provenance). Audit existing
  pins and convert first-party to major tags. Operator-approved decision #7.

### 3. DOCKER-SMOKE-CLEANUP (fragility finding #6)
- tier: economy
- owns: .github/workflows/release.yml, .github/workflows/heavy.yml
- scope: Add `trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT` to release smoke.
  Use dynamic container name + host port in heavy.yml (mirror release.yml). Prefer Python
  stdlib HTTP smoke where easy.

### 4. CI-WORKFLOW-POLICY-GATE (fragility finding #8)
- tier: strong
- owns: tools/check_workflows.py, tools/gates.json
- scope: One gate enforcing: action-ref policy (first-party major tag OK, third-party SHA
  required), reject fragile Windows smoke patterns (no Start-Process), require path
  triggers for packaging-sensitive workflows. Register in gates.json. Red-proof test
  required (Structural Rule 3).

### 5. PROVIDER-URL-HELPER (fragility finding #9)
- tier: strong
- owns: src/charon/providers.py, src/charon/config.py, src/charon/discover.py
- scope: Deduplicate provider URL/path construction. One stdlib helper for provider
  endpoint construction: validate base, reject metadata/link-local, disable redirects,
  join endpoint paths consistently, expose models_url/chat_url.

## Dependencies & sequence
No depends_on. This is ticket-creation work, not build work. Create all five board tickets
with their own prompt files.

## Gate
The `accept` command verifies all five ticket files exist.
