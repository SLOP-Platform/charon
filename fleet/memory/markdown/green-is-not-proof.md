---
description: "A passing/green result is NOT proof unless red-proofed, non-vacuous, un-skipped, not-inert, and fail-loud — always try to make it FAIL"
metadata: 
name: green-is-not-proof
node_type: memory
originSessionId: a95dc541-223e-4053-8197-6848f0322d6b
type: feedback
tags: [test]
last_referenced: 2026-07-13
---
DIRECTIVE (2026-07-11): **never trust an unproven green.** A passing test / green gate is EVIDENCE only if ALL hold:
- **Red-proofed** — the check has demonstrably gone RED against a real failure (neuter it, prove it fails).
- **Non-vacuous** — it cannot pass with ZERO items checked (empty discovery / zero tests = RED, never a silent pass).
- **Un-skipped / un-gamed** — no `skip`/`xfail` without a linked justification; the checked node-set cannot silently shrink.
- **Not inert** — it exercises real, WIRED code (production-path=test-path; the feature is actually constructed + called), not a built-but-unwired unit.
- **Fail-loud** — a failure propagates as a NON-ZERO process exit and is NEVER masked by a pipe (`| tail`, `|| true`, missing `set -o pipefail`).

Always **independently re-verify the crux by trying to make it FAIL.**

**Why:** the Keystone Framework — built to catch built-but-inert code — was ITSELF built-but-inert (gates discovered in the wrong dir → zero gates found). Unit tests were green AND an independent `verify-self` run was green — BOTH vacuously. Only the adversarial review caught it. Then the fix-verification nearly slipped because `| tail` masked the real exit code (the pipefail trap). **No half-measures** — a deferred/half check rots and is forgotten over time.

Mechanized in KSF gates (`redproof`, `no_vacuous`, `no_skip_game`, `no_pipe_mask`, `fail_loud`, `inert-code`) and in MANAGER-OPERATING-RULES §11. Extends [[confirm-dont-trust-documentation]], [[preexisting-issues-fold-into-current-work]], [[document-model-self-report-lies]].
