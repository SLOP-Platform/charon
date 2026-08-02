"""Red-proof tests for src/charon/startup_check.py.

Verifies that the classification is DERIVED from the invocation surface
(forwarder.py + chain_for), not recited from a hand-maintained list.

- DERIVATION IS PROVEN AGAINST SYNTHETIC SOURCE: ``_parse_module_attr_names``
  is pointed at a temp .py file the parser has never seen, holding SIX
  PHANTOM module names that appear nowhere in the real codebase. All six
  must come back, and nothing else. A hand-maintained list cannot pass this.
  (This deliberately does NOT depend on any particular dead module still
  existing in proxy_server.py — dead code is what this detector exists to get
  DELETED, so anchoring the proof to it would make cleanup break the proof.)
- SIX known-dead modules (constructed but zero invocation sites) are
  classified as INERT. This is a TEST FIXTURE — the six names appear ONLY
  in the tests, never in the implementation. Names already deleted from
  proxy_server.py stay in the fixture: an unknown, uninvoked attr must still
  classify INERT.
- SIX genuinely-wired modules (on the request path) are classified as ACTIVE.
  These are also the NON-VACUITY anchor for the derived module set.
- NON-VACUOUS: zero modules inspected → RED (empty classification).
- RED-PROOF BY EXTERNAL BREAK: the break is SPECIFIED, not chosen.
  #1: a genuinely NEW module (phantom), invoked nowhere → INERT (no list edit).
  #2: wire a currently-INERT module via a custom invoked set → ACTIVE.
- FAIL-CLOSED: an attr whose classification cannot be determined is UNKNOWN
  (RED), never defaulted to ACTIVE.
"""

import charon.startup_check as startup_check
from charon.startup_check import (
    _INVOKED_ATTRS,
    _MODULE_ATTRS,
    classify_modules,
    count_active,
    count_inert,
    run_startup_inert_check,
)

# ── test fixture: the six known-dead modules ──────────────────────────
# These names appear ONLY in the test — the implementation must reproduce
# this classification independently through AST analysis (never from a list).
_INERT_FIXTURE = frozenset({
    "request_inspector",
    "session_affinity",
    "observability",
    "speculative_executor",
    "consensus_router",
    "virtual_key_manager",
})

# ── test fixture: SIX phantom module names ────────────────────────────
# These strings appear NOWHERE in src/ — they exist only inside a synthetic
# source file written at test time. They are the proof that _MODULE_ATTRS is
# genuinely PARSED out of source, not recited.
_PHANTOM_FIXTURE = (
    "phantom_alpha",
    "phantom_beta",
    "phantom_gamma",
    "phantom_delta",
    "phantom_epsilon",
    "phantom_zeta",
)

_SYNTHETIC_PROXY_SERVER = '''
class SyntheticServer:
    def __init__(self):
        _mod_param_names = (
            "phantom_alpha", "phantom_beta", "phantom_gamma",
            "phantom_delta", "phantom_epsilon", "phantom_zeta")
        for _mn in _mod_param_names:
            self.modules[_mn] = None
'''

# ── test fixture: the six known-wired modules ─────────────────────────
_ACTIVE_FIXTURE = frozenset({
    "spend_limiter",
    "guardrails",
    "semantic_cache",
    "quality_scorer",
    "response_normalizer",
    "policy_router",
})


class TestModuleAttrsDerived:
    """The module attribute set (_MODULE_ATTRS) is DERIVED by AST-parsing
    ``_mod_param_names`` out of proxy_server.py, never hand-maintained.

    Proven two ways:
    - ``test_parses_six_phantom_names_from_synthetic_source``: point the parser
      at a synthetic source file it has never seen, containing SIX phantom
      names that exist nowhere in src/. All six must come back and nothing
      else. Only a real parser can pass this; a hardcoded list cannot.
    - ``test_contains_all_six_active_fixture``: the live derived set is
      non-empty and still contains the six genuinely-wired modules
      (non-vacuity, anchored to wired code rather than to dead code).
    """

    def test_parses_six_phantom_names_from_synthetic_source(self, tmp_path,
                                                            monkeypatch):
        """RED-PROOF: derivation is real parsing, not recital.

        The six phantom names appear in NO real source file, so a
        hand-maintained/hardcoded implementation cannot produce them.
        """
        synthetic = tmp_path / "synthetic_proxy_server.py"
        synthetic.write_text(_SYNTHETIC_PROXY_SERVER, encoding="utf-8")
        monkeypatch.setattr(startup_check, "_PROXY_SERVER_PATH", str(synthetic))

        parsed = startup_check._parse_module_attr_names()

        for name in _PHANTOM_FIXTURE:
            assert name in parsed, (
                f"{name} must be derived by parsing _mod_param_names "
                f"from the synthetic source; got {sorted(parsed)}")
        assert len(parsed) == 6, (
            f"expected exactly the 6 phantom names, got {sorted(parsed)}")

    def test_module_attrs_nonvacuous(self):
        """NON-VACUITY: the live derived set is non-empty and contains the six
        genuinely-wired modules. Anchored to WIRED code, so deleting dead code
        (this detector's whole purpose) can never make the proof fail."""
        assert _MODULE_ATTRS, "_MODULE_ATTRS must be non-empty"
        for attr in _ACTIVE_FIXTURE:
            assert attr in _MODULE_ATTRS, (
                f"{attr} must be in _MODULE_ATTRS (derived from _mod_param_names)")

    def test_contains_all_six_active_fixture(self):
        for attr in _ACTIVE_FIXTURE:
            assert attr in _MODULE_ATTRS, (
                f"{attr} must be in _MODULE_ATTRS (derived from _mod_param_names)")


class TestInvocationDerived:
    """The invoked set is derived from forwarder.py + chain_for, not from a list."""

    def test_invoked_is_nonempty(self):
        assert _INVOKED_ATTRS, "invoked set must be nonempty"

    def test_invoked_is_subset_of_module_attrs(self):
        assert _INVOKED_ATTRS <= _MODULE_ATTRS, (
            "_INVOKED_ATTRS must be a subset of _MODULE_ATTRS")

    def test_all_six_active_fixture_are_invoked(self):
        for attr in _ACTIVE_FIXTURE:
            assert attr in _INVOKED_ATTRS, (
                f"{attr} must be in _INVOKED_ATTRS (derived from invocation surface)")

    def test_all_six_inert_fixture_are_not_invoked(self):
        for attr in _INERT_FIXTURE:
            assert attr not in _INVOKED_ATTRS, (
                f"{attr} must NOT be in _INVOKED_ATTRS (no invocation sites)")


class TestClassification:
    """The classification correctly classifies all known-dead modules as INERT
    and genuinely-wired modules as ACTIVE. No overlap."""

    def test_no_overlap(self):
        inert_from_analysis = _MODULE_ATTRS - _INVOKED_ATTRS
        assert _INVOKED_ATTRS.isdisjoint(inert_from_analysis), (
            f"overlap: {_INVOKED_ATTRS & inert_from_analysis}")

    def test_six_known_dead_are_inert(self):
        for attr in _INERT_FIXTURE:
            assert attr not in _INVOKED_ATTRS, (
                f"{attr} must be classified as INERT by the derivation")

    def test_six_wired_are_active(self):
        for attr in _ACTIVE_FIXTURE:
            assert attr in _INVOKED_ATTRS, (
                f"{attr} must be classified as ACTIVE by the derivation")

    def test_classify_inert_gives_inert(self):
        modules = {a: object() for a in _INERT_FIXTURE}
        result = classify_modules(modules)
        for attr in _INERT_FIXTURE:
            assert result[attr] == "INERT", (
                f"{attr} expected INERT, got {result[attr]}")

    def test_classify_active_gives_active(self):
        modules = {a: object() for a in _ACTIVE_FIXTURE}
        result = classify_modules(modules)
        for attr in _ACTIVE_FIXTURE:
            assert result[attr] == "ACTIVE", (
                f"{attr} expected ACTIVE, got {result[attr]}")

    def test_classify_mixed(self):
        both: dict[str, object] = {}
        both.update(dict.fromkeys(_INERT_FIXTURE))
        both.update(dict.fromkeys(_ACTIVE_FIXTURE))
        result = classify_modules(both)
        for attr in _INERT_FIXTURE:
            assert result[attr] == "INERT"
        for attr in _ACTIVE_FIXTURE:
            assert result[attr] == "ACTIVE"

    def test_count_inert(self):
        both: dict[str, object] = {}
        both.update(dict.fromkeys(_INERT_FIXTURE))
        both.update(dict.fromkeys(_ACTIVE_FIXTURE))
        assert count_inert(both) == len(_INERT_FIXTURE)

    def test_count_active(self):
        both: dict[str, object] = {}
        both.update(dict.fromkeys(_INERT_FIXTURE))
        both.update(dict.fromkeys(_ACTIVE_FIXTURE))
        assert count_active(both) == len(_ACTIVE_FIXTURE)


class TestNonVacuous:
    """NON-VACUOUS: zero modules inspected → RED (empty classification)."""

    def test_empty_modules_yields_no_inert(self):
        assert count_inert({}) == 0

    def test_empty_modules_yields_no_active(self):
        assert count_active({}) == 0

    def test_classify_empty_returns_empty_dict(self):
        assert classify_modules({}) == {}


class TestRedProofExternal:
    """The break is SPECIFIED, not ours to choose. These are EXTERNAL red-proofs:
    the check must respond to a genuinely NEW dead module (proof #1) and to a
    newly-wired formerly-INERT module (proof #2) — with no list edit."""

    def test_red_proof_1_new_phantom_module_is_inert(self):
        """RED-PROOF #1: a genuinely NEW module, constructed but invoked
        NOWHERE, must be classified as INERT without any edit to the check."""
        modules = {**dict.fromkeys(_INERT_FIXTURE),
                   **dict.fromkeys(_ACTIVE_FIXTURE),
                   "phantom_module": object()}
        result = classify_modules(modules)
        # phantom_module is not in any hardcoded list and is not on the
        # invocation surface → INERT (the derivation determines this).
        assert result["phantom_module"] == "INERT", (
            f"phantom_module expected INERT, got {result['phantom_module']}")
        # Existing modules are untouched.
        for attr in _INERT_FIXTURE:
            assert result[attr] == "INERT"
        for attr in _ACTIVE_FIXTURE:
            assert result[attr] == "ACTIVE"
        # No UNKNOWN — the derivation fully classified everything.
        assert "UNKNOWN" not in set(result.values())

    def test_red_proof_2_wire_inert_flips_to_active(self):
        """RED-PROOF #2: take a currently-INERT module and WIRE it into the
        invocation surface; the check must flip it to ACTIVE with no list edit.
        Demonstrated by supplying a custom invoked set that includes the
        formerly-INERT module."""
        # request_inspector is INERT by default.
        assert "request_inspector" in _INERT_FIXTURE
        assert "request_inspector" not in _INVOKED_ATTRS

        # Simulate wiring: include it in the invoked set.
        wired_invoked = _INVOKED_ATTRS | {"request_inspector"}
        modules = {"request_inspector": object(), "spend_limiter": object()}
        result = classify_modules(modules, invoked=wired_invoked)

        assert result["request_inspector"] == "ACTIVE", (
            "wired module must flip to ACTIVE")
        assert result["spend_limiter"] == "ACTIVE"


class TestFailClosed:
    """FAIL-CLOSED: an attr whose derivation cannot classify must be reported
    UNKNOWN and treated as RED, never defaulted to ACTIVE."""

    def test_unknown_attribute_is_not_active(self):
        """If an attr IS on the invocation surface (_ALL_SRV_ATTRS) but NOT in
        the known module set (_MODULE_ATTRS), it must be UNKNOWN — not ACTIVE."""
        # Use a custom small module_attrs and include an attr that IS in
        # all_srv_attrs but NOT in our shrunken module_attrs.
        small_modules = frozenset({"spend_limiter", "guardrails"})
        custom_all = frozenset({"spend_limiter", "guardrails", "policy_router"})
        result = classify_modules(
            {"policy_router": object(), "spend_limiter": object()},
            module_attrs=small_modules,
            all_srv_attrs=custom_all,
        )
        # policy_router is in all_srv_attrs but NOT in module_attrs → UNKNOWN
        assert result["policy_router"] == "UNKNOWN", (
            f"policy_router expected UNKNOWN, got {result['policy_router']}")
        # spend_limiter IS in module_attrs and in invoked → ACTIVE
        assert result["spend_limiter"] == "ACTIVE"

    def test_unknown_is_not_counted_as_inert(self):
        """UNKNOWN modules are neither INERT nor ACTIVE."""
        small_modules = frozenset({"spend_limiter"})
        custom_all = frozenset({"spend_limiter", "policy_router"})
        modules = {"policy_router": object(), "spend_limiter": object()}
        result = classify_modules(
            modules,
            module_attrs=small_modules,
            all_srv_attrs=custom_all,
        )
        assert result["policy_router"] == "UNKNOWN"
        assert count_inert(modules, module_attrs=small_modules,
                           all_srv_attrs=custom_all) == 0, (
            "UNKNOWN must not count as INERT")
        assert count_active(modules, module_attrs=small_modules,
                            all_srv_attrs=custom_all) == 1


class TestRunStartupInertCheck:
    """The diagnostic string produced by run_startup_inert_check."""

    def test_output_format(self):
        class FakeConfig:
            modules = {"request_inspector": object(), "spend_limiter": object(),
                       "guardrails": object()}
        line = run_startup_inert_check(FakeConfig())
        assert "INERT" in line
        assert "ACTIVE" in line
        assert "request_inspector" in line
        assert "spend_limiter" in line
        assert "guardrails" in line
        assert "startup inert check" in line
