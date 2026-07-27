# CONFIG-SSOT-CANARY-REGISTER — per-ticket review fragment
#
# Ticket:    CONFIG-SSOT-CANARY-REGISTER (charon-private; tier=strong; difficulty=2; work_class=rig-meta)
# Branch:    feat/config-ssot-canary-register
# Files:     fleet/tests/config-ssot-gate.test.sh (owned)
#            + this fragment (docs/review-log/CONFIG-SSOT-CANARY-REGISTER.md; exception to owns rule)
#
# ## What landed
#
# The config-ssot plane's dogfood_test — a hermetic, fail-on-revert fault-seed test
# proving that fleet/checks/config-ssot-gate.sh (unmodified, reused as-is) actually
# catches real manifest/reader divergences. This promotes the config-ssot gate from
# advisory-untested to REGISTERED + PROVEN under the plane-canary framework.
#
# Registry row (already seeded by PLANE-CANARY-REGISTRY):
#   config-ssot  fleet/checks/config-ssot-gate.sh  fleet/tests/config-ssot-gate.test.sh  preflight  CONFIG-SSOT-CANARY-REGISTER
#
# Test coverage (11 assertions, all PASS):
#   1. Seeded KEY-ENV mismatch (manifest="BETA_KEY", local="WRONG_KEY_ENV") -> gate RED,
#      names KEY-ENV MISMATCH on beta. Fix -> GREEN. Revert -> RED again (not a tautology).
#   2. Seeded BASE-URL mismatch on gamma -> gate RED, names BASE-URL MISMATCH.
#      Fix -> GREEN. Revert -> RED again.
#   3. Unreachable local source -> gate RED (no false-GREEN).
#
# ## Decisions
#
# 1. **KEY-ENV as the primary seeded drift class.** The ticket's accept criteria and
#    the board note both highlight key_env mismatches as "exactly the shape the egress-key
#    exfil class rides." A key_env mismatch between the manifest and a live config reader is
#    a security-relevant drift signal — the test proves the gate catches it.
#
# 2. **Hermetic-only (no live 4-LOM / ~/.charon).** Matches the pattern in
#    fleet/tests/config-ssot.test.sh: CONFIG_MANIFEST_TSV, CHARON_LOCAL_PROVIDERS, and
#    GATEWAY_PROVIDERS_RCMD env vars route everything into temp-dir fixtures. Safe to run
#    anywhere, offline.
#
# 3. **Fail-on-revert for every seeded class.** Each fault class (KEY-ENV, BASE-URL) is
#    seeded -> RED, fixed -> GREEN, re-seeded -> RED again. No assertion is a tautology.
#
# ## Out of scope (by owns rule)
#
# This ticket owns ONLY fleet/tests/config-ssot-gate.test.sh. The plane-canary registry
# row was already seeded by PLANE-CANARY-REGISTRY. The wired_in=preflight wiring (so that
# plane-canary.sh reconcile's _unwired_layers check passes) and the promotion from advisory
# BASELINE_CHECKS to a blocking gate are separate tickets — this test proves the check
# WORKS, not that it blocks landing.
#
# ## Verification
#
#   bash fleet/tests/config-ssot-gate.test.sh
#     -> 11 passed, 0 failed (all 3 seeded fault classes + fail-on-revert)
#
#   bash fleet/validate_board.sh
#     -> GREEN (structurally valid; the WARN about the test file not existing in the product
#        repo is expected — it lives in the worktree until merged)
