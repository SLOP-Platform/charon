# semgrep-known-bad.py — FIXTURE. NOT product code. Deliberately violates charon-policy.yml RULE 1
# (charon-no-hardcoded-anthropic-model) so the canary can prove the gate actually fires.
#
# It triggers RULE 1 ONLY (no gateway-host / dev-box-path violations here) so that neutering RULE 1
# drops the finding count to zero — that drop is what proves RULE 1 is load-bearing, not vacuous.


def pick_gateway_model():
    # VIOLATION (RULE 1): a hardcoded Anthropic/Claude model id on the gateway plane, which must
    # never route to Anthropic and must stay client-agnostic.
    model = "claude-opus-4-20250514"
    return model
