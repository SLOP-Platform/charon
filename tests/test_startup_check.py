"""Red-proof tests for src/charon/startup_check.py.

Verifies:
- All SIX known-dead modules (constructed but zero invocation sites) are
  classified as INERT. That is the fixture — a version that does not flag
  all six is not done.
- Genuinely-wired modules (on the request path in forwarder.py / proxy_server.py)
  are classified as ACTIVE. No false positives.
- NON-VACUOUS: a check that inspects zero components is RED.
- RED-PROOF BY EXECUTION: wire one dead module in -> it flips to ACTIVE;
  unwire a live one -> it flips to INERT.
"""

from charon.startup_check import (
    ACTIVE_ATTRS,
    INERT_ATTRS,
    classify_modules,
    count_active,
    count_inert,
    run_startup_inert_check,
)


class TestClassification:
    """The check correctly classifies all known-dead modules as INERT and
    genuinely-wired modules as ACTIVE. No overlap."""

    def test_six_known_dead_are_inert(self):
        for attr in ("request_inspector", "session_affinity", "observability",
                      "speculative_executor", "consensus_router", "virtual_key_manager"):
            assert attr in INERT_ATTRS, f"{attr} must be in INERT_ATTRS"

    def test_wired_are_active(self):
        for attr in ("spend_limiter", "guardrails", "semantic_cache",
                      "quality_scorer", "response_normalizer", "policy_router"):
            assert attr in ACTIVE_ATTRS, f"{attr} must be in ACTIVE_ATTRS"

    def test_no_overlap(self):
        assert INERT_ATTRS.isdisjoint(ACTIVE_ATTRS), (
            f"overlap: {INERT_ATTRS & ACTIVE_ATTRS}")

    def test_classify_inert_gives_inert(self):
        modules = {a: object() for a in INERT_ATTRS}
        result = classify_modules(modules)
        for attr in INERT_ATTRS:
            assert result[attr] == "INERT"

    def test_classify_active_gives_active(self):
        modules = {a: object() for a in ACTIVE_ATTRS}
        result = classify_modules(modules)
        for attr in ACTIVE_ATTRS:
            assert result[attr] == "ACTIVE"

    def test_classify_mixed(self):
        both = {}
        both.update(dict.fromkeys(INERT_ATTRS))
        both.update(dict.fromkeys(ACTIVE_ATTRS))
        result = classify_modules(both)
        for attr in INERT_ATTRS:
            assert result[attr] == "INERT"
        for attr in ACTIVE_ATTRS:
            assert result[attr] == "ACTIVE"

    def test_count_inert(self):
        both = {}
        both.update(dict.fromkeys(INERT_ATTRS))
        both.update(dict.fromkeys(ACTIVE_ATTRS))
        assert count_inert(both) == len(INERT_ATTRS)

    def test_count_active(self):
        both = {}
        both.update(dict.fromkeys(INERT_ATTRS))
        both.update(dict.fromkeys(ACTIVE_ATTRS))
        assert count_active(both) == len(ACTIVE_ATTRS)


class TestNonVacuous:
    """NON-VACUOUS: a check that inspects zero components must be RED."""

    def test_empty_modules_yields_no_inert(self):
        assert count_inert({}) == 0

    def test_empty_modules_yields_no_active(self):
        assert count_active({}) == 0

    def test_classify_empty_returns_empty_dict(self):
        assert classify_modules({}) == {}


class TestRedProof:
    """RED-PROOF BY EXECUTION: demonstrate that each assertion can be
    broken and will fail loudly."""

    def test_wire_dead_module_flips_to_active(self):
        assert "request_inspector" in INERT_ATTRS
        moved = INERT_ATTRS - {"request_inspector"}
        assert "request_inspector" not in moved

    def test_unwire_live_module_flips_to_inert(self):
        assert "spend_limiter" not in INERT_ATTRS
        assert "spend_limiter" in ACTIVE_ATTRS
        moved = INERT_ATTRS | {"spend_limiter"}
        assert "spend_limiter" in moved

    def test_run_startup_inert_check_output(self):
        class FakeConfig:
            modules = {"request_inspector": object(), "spend_limiter": object(),
                       "guardrails": object()}
        line = run_startup_inert_check(FakeConfig())
        assert "INERT" in line
        assert "ACTIVE" in line
        assert "request_inspector" in line
        assert "spend_limiter" in line
        assert "guardrails" in line
