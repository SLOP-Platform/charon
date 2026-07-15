"""Tests for DEC-PLANNER (src/charon/decompose_planner.py).

The planner is the LLM splitting brain: broad ticket + change surface → N single-domain,
file-scoped sub-tickets, VALIDATED through intake.assert_disjoint_waves. The model is
always mocked here — no real network.

FAIL-ON-REVERT (WORK-DECOMPOSER accept): a mocked model returning a 3-file disjoint split
yields 3 disjoint PlanUnits that pass assert_disjoint_waves; a mocked OVERLAPPING split is
REJECTED. Reverting the assert_disjoint_waves call in plan_decomposition lets the
overlapping split slip through → test_overlapping_split_is_rejected goes RED.
"""
from __future__ import annotations

import pytest

from charon import decompose_planner as P
from charon.intake import IntakeError, PlanUnit, assert_disjoint_waves

# The R46-style broad ticket fixture: wire a BalanceTracker through several modules —
# exactly the cross-module integration that cheap models fail as one god-ticket.
R46_TICKET = P.BroadTicket(
    id="r46-wire-balance-tracker",
    goal="Wire a per-provider BalanceTracker through the gateway",
    body="Build the tracker, construct it in the server, and expose it in config.",
    product_acceptance="charon serve reports a non-None balance tracker per provider",
)

R46_SURFACE = {
    "files": [
        "src/charon/balance.py",
        "src/charon/proxy.py",
        "src/charon/config/gateway.py",
    ],
    "symbols": ["BalanceTracker", "build_server", "GatewayConfig"],
}


def _mock(units: list[dict]) -> P.ModelInvoker:
    """A fake strong model that always returns the given units payload (no network)."""

    def _ask(prompt: str) -> dict:
        return {"units": units}

    return _ask


# 3-file disjoint split: a pure unit, plus two wire-ins each depending on it.
DISJOINT_3 = [
    {
        "id": "build-balance-tracker",
        "goal": "Add BalanceTracker(provider_cfg) to balance.py",
        "owns": ["src/charon/balance.py"],
        "depends_on": [],
        "accept": ["test_build_balance_tracker returns a non-None BalanceTracker"],
    },
    {
        "id": "wire-tracker-into-server",
        "goal": "Construct the tracker in build_server",
        "owns": ["src/charon/proxy.py"],
        "depends_on": ["build-balance-tracker"],
        "accept": ["test_server_has_tracker asserts server.balance is not None"],
    },
    {
        "id": "expose-tracker-config",
        "goal": "Expose the tracker on GatewayConfig",
        "owns": ["src/charon/config/gateway.py"],
        "depends_on": ["build-balance-tracker"],
        "accept": ["test_gateway_config_balance field defaults present"],
    },
]

# Overlapping split: two units both own proxy.py yet neither depends on the other →
# they could run concurrently and collide. assert_disjoint_waves MUST reject this.
OVERLAP_2 = [
    {
        "id": "wire-tracker-a",
        "goal": "Construct the tracker in build_server",
        "owns": ["src/charon/proxy.py"],
        "depends_on": [],
        "accept": ["test_a"],
    },
    {
        "id": "wire-tracker-b",
        "goal": "Also touch build_server",
        "owns": ["src/charon/proxy.py"],
        "depends_on": [],
        "accept": ["test_b"],
    },
]


# --------------------------------------------------------- fail-on-revert: PASS path
def test_disjoint_split_emits_3_disjoint_units() -> None:
    units = P.plan_decomposition(R46_TICKET, R46_SURFACE, ask=_mock(DISJOINT_3))
    assert len(units) == 3
    assert all(isinstance(u, PlanUnit) for u in units)
    # each is single-file and file-scoped
    assert all(len(u.owned_paths) == 1 for u in units)
    # the set survives the real hard gate (i.e. the planner already proved it)
    assert_disjoint_waves(units)
    # dependency order preserved for the wire-ins
    by_id = {u.id: u for u in units}
    assert by_id["wire-tracker-into-server"].depends_on == ["build-balance-tracker"]


# --------------------------------------------------------- fail-on-revert: REJECT path
def test_overlapping_split_is_rejected() -> None:
    # The mock always returns the overlapping split, so every re-prompt still collides;
    # the planner exhausts its attempts and refuses to return a colliding plan.
    with pytest.raises(P.PlannerError):
        P.plan_decomposition(
            R46_TICKET, R46_SURFACE, ask=_mock(OVERLAP_2), max_reprompts=1
        )


def test_reprompt_recovers_from_transient_overlap() -> None:
    # First reply overlaps (rejected), second is disjoint (accepted) — proves the
    # re-prompt loop feeds the violation back and recovers.
    replies = [{"units": OVERLAP_2}, {"units": DISJOINT_3}]

    def _ask(prompt: str) -> dict:
        return replies.pop(0)

    units = P.plan_decomposition(R46_TICKET, R46_SURFACE, ask=_ask, max_reprompts=2)
    assert len(units) == 3


# --------------------------------------------------------- anti-hallucination guards
def test_owns_outside_change_surface_is_rejected() -> None:
    bad = [
        {
            "id": "touch-unknown",
            "goal": "edit a file not in the surface",
            "owns": ["src/charon/secretly_invented.py"],
            "depends_on": [],
            "accept": ["t"],
        }
    ]
    with pytest.raises(P.PlannerError):
        P.plan_decomposition(R46_TICKET, R46_SURFACE, ask=_mock(bad), max_reprompts=0)


def test_missing_acceptance_is_rejected() -> None:
    bad = [
        {
            "id": "no-accept",
            "goal": "no fail-on-revert test",
            "owns": ["src/charon/balance.py"],
            "depends_on": [],
            "accept": [],
        }
    ]
    with pytest.raises(P.PlannerError):
        P.plan_decomposition(R46_TICKET, R46_SURFACE, ask=_mock(bad), max_reprompts=0)


def test_invalid_task_id_is_rejected() -> None:
    bad = [
        {
            "id": "Bad ID With Spaces",
            "goal": "bad id",
            "owns": ["src/charon/balance.py"],
            "depends_on": [],
            "accept": ["t"],
        }
    ]
    with pytest.raises(P.PlannerError):
        P.plan_decomposition(R46_TICKET, R46_SURFACE, ask=_mock(bad), max_reprompts=0)


def test_dangling_dependency_is_rejected() -> None:
    bad = [
        {
            "id": "wire-in",
            "goal": "depends on a ghost",
            "owns": ["src/charon/proxy.py"],
            "depends_on": ["does-not-exist"],
            "accept": ["t"],
        }
    ]
    with pytest.raises(P.PlannerError):
        P.plan_decomposition(R46_TICKET, R46_SURFACE, ask=_mock(bad), max_reprompts=0)


def test_no_json_object_is_rejected() -> None:
    def _ask(prompt: str) -> None:
        return None

    with pytest.raises(P.PlannerError):
        P.plan_decomposition(R46_TICKET, R46_SURFACE, ask=_ask, max_reprompts=0)


def test_empty_surface_raises() -> None:
    with pytest.raises(P.PlannerError):
        P.plan_decomposition(R46_TICKET, {"files": []}, ask=_mock(DISJOINT_3))


# --------------------------------------------------------- detention / model-select seam
def test_default_invoker_requires_a_trusted_model(monkeypatch: pytest.MonkeyPatch) -> None:
    # No trusted models configured → the planner refuses to split (needs a strong model).
    from charon import recommend

    monkeypatch.setattr(recommend, "_find_trusted_models", lambda cd: [])
    monkeypatch.setattr(P, "recommend_default_config_dir", lambda: "/nonexistent")
    with pytest.raises(P.PlannerError):
        P.plan_decomposition(R46_TICKET, R46_SURFACE)  # no ask → default invoker


def test_detained_model_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    from charon import recommend

    monkeypatch.setattr(
        recommend,
        "_find_trusted_models",
        lambda cd: [("detained-model", "http://x", "k"), ("strong-model", "http://y", "k2")],
    )
    monkeypatch.setattr(P, "recommend_default_config_dir", lambda: "/nonexistent")
    picked = P._select_planner_model(
        config_dir=None, is_detained=lambda m: m == "detained-model"
    )
    assert picked is not None
    assert picked[0] == "strong-model"


def test_planner_never_selects_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    # SG-never-Anthropic HARD RULE (PLANNER-ONLY): the planner must NEVER select a
    # Claude/Anthropic model, whether flagged by base_url or by a claude-* model_id.
    # FAIL-ON-REVERT: removing the guard in _select_planner_model flips this RED.
    from charon import recommend

    monkeypatch.setattr(P, "recommend_default_config_dir", lambda: "/nonexistent")

    # An anthropic base_url AND a claude-* model are both present, plus a non-Claude one.
    monkeypatch.setattr(
        recommend,
        "_find_trusted_models",
        lambda cd: [
            ("claude-opus-4", "https://api.anthropic.com/v1", "k1"),
            ("some-model", "https://api.anthropic.com/v1", "k2"),
            ("gpt-style-model", "https://api.openai.com/v1", "k3"),
        ],
    )
    picked = P._select_planner_model(config_dir=None, is_detained=None)
    assert picked is not None
    assert picked[0] == "gpt-style-model"  # never the anthropic/claude candidates

    # Only an anthropic/claude model configured → no planner (None), NEVER select Claude.
    monkeypatch.setattr(
        recommend,
        "_find_trusted_models",
        lambda cd: [("claude-sonnet-4", "https://api.anthropic.com/v1", "k1")],
    )
    assert P._select_planner_model(config_dir=None, is_detained=None) is None


# --------------------------------------------------------- PLANNER env / tier override
def test_planner_env_pinned_model_wins_even_when_not_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # DECOMPOSE-MODEL-WIRING: CHARON_DECOMPOSE_PLANNER_MODEL must reorder selection so
    # the pinned model is chosen even when it is NOT the first trusted model.
    # FAIL-ON-REVERT: stripping the pinned/tier-lookup block reverts to plain first-in-
    # list order, so this test goes RED.
    from charon import recommend

    monkeypatch.setattr(P, "recommend_default_config_dir", lambda: "/nonexistent")
    monkeypatch.setenv("CHARON_DECOMPOSE_PLANNER_MODEL", "pinned-model")
    # Pinned model is SECOND in the mocked trusted list — selection must still pick it.
    monkeypatch.setattr(
        recommend,
        "_find_trusted_models",
        lambda cd: [
            ("other-model", "https://api.openai.com/v1", "k1"),
            ("pinned-model", "https://api.openai.com/v1", "k2"),
        ],
    )
    picked = P._select_planner_model(config_dir=None, is_detained=None)
    assert picked is not None
    assert picked[0] == "pinned-model"


def test_planner_tier_high_model_preferred_when_unpinned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # DECOMPOSE-MODEL-WIRING: with no CHARON_DECOMPOSE_PLANNER_MODEL set, a trusted
    # model whose id is in tiers.tier_members("high") must be selected before the
    # plain first-in-list trusted model.
    # FAIL-ON-REVERT: removing the tier-'high' lookup reverts to first-in-list order
    # and this test goes RED.
    from charon import recommend
    from charon.config import tiers as tiers_cfg

    monkeypatch.setattr(P, "recommend_default_config_dir", lambda: "/nonexistent")
    monkeypatch.delenv("CHARON_DECOMPOSE_PLANNER_MODEL", raising=False)

    # Force tier_members("high") → ["tier-high-model"], regardless of persisted tiers.json.
    monkeypatch.setattr(
        tiers_cfg, "tier_members", lambda tier, tiers=None: ["tier-high-model"]
    )
    # The tier-"high" model is SECOND in the mocked trusted list — selection must still pick it.
    monkeypatch.setattr(
        recommend,
        "_find_trusted_models",
        lambda cd: [
            ("other-model", "https://api.openai.com/v1", "k1"),
            ("tier-high-model", "https://api.openai.com/v1", "k2"),
        ],
    )
    picked = P._select_planner_model(config_dir=None, is_detained=None)
    assert picked is not None
    assert picked[0] == "tier-high-model"


def test_planner_pinned_model_ignores_anthropic_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # If a non-Claude pinned model exists alongside a Claude first-in-list, the pinned
    # model wins (the SG-never-Anthropic guard skips Claude first; pinned re-orders after).
    from charon import recommend

    monkeypatch.setattr(P, "recommend_default_config_dir", lambda: "/nonexistent")
    monkeypatch.setenv("CHARON_DECOMPOSE_PLANNER_MODEL", "pinned-gpt")
    monkeypatch.setattr(
        recommend,
        "_find_trusted_models",
        lambda cd: [
            ("claude-opus-4", "https://api.anthropic.com/v1", "k1"),
            ("pinned-gpt", "https://api.openai.com/v1", "k2"),
        ],
    )
    picked = P._select_planner_model(config_dir=None, is_detained=None)
    assert picked is not None
    assert picked[0] == "pinned-gpt"


# --------------------------------------------------------- prompt shape
def test_prompt_lists_surface_and_ticket() -> None:
    surf = P.ChangeSurface.from_facts(R46_SURFACE)
    prompt = P.build_prompt(R46_TICKET, surf)
    assert "src/charon/balance.py" in prompt
    assert R46_TICKET.goal in prompt
    assert "DISJOINT" in prompt  # the disjoint-owns instruction is present
    # feedback is injected on re-prompt
    fb = P.build_prompt(R46_TICKET, surf, feedback="you overlapped foo.py")
    assert "you overlapped foo.py" in fb


# --------------------------------------------------------- provider failover (fix B)
def _serve_candidates(
    monkeypatch: pytest.MonkeyPatch, entries: list[tuple[str, str, str]]
) -> None:
    """Point the default-invoker path at a fixed ordered candidate list (no network)."""
    from charon import recommend

    monkeypatch.setattr(P, "recommend_default_config_dir", lambda: "/nonexistent")
    monkeypatch.setattr(recommend, "_find_trusted_models", lambda cd: entries)


def test_failover_on_auth_advances_to_next_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # First candidate's key 401s (provider-level auth fault) → the planner must FAIL OVER
    # to the second candidate, which serves a valid plan. Proves it did not just re-prompt
    # the dead model. FAIL-ON-REVERT: collapse _post_chat back to a blanket None (so a 401
    # looks like an unparseable plan) and the planner never advances → this goes RED.
    monkeypatch.delenv("CHARON_DECOMPOSE_PLANNER_MODEL", raising=False)
    _serve_candidates(
        monkeypatch,
        [
            ("dead-key-model", "https://api.openai.com/v1", "bad"),
            ("live-model", "https://api.openai.com/v1", "good"),
        ],
    )

    def fake_post(model_id, base_url, api_key, prompt, timeout=60.0):
        if model_id == "dead-key-model":
            raise P.PlannerTransportError("auth", 401, "HTTP 401 from dead-key-model")
        return {"units": DISJOINT_3}

    monkeypatch.setattr(P, "_post_chat", fake_post)

    units = P.plan_decomposition(R46_TICKET, R46_SURFACE)  # default invoker → failover
    assert len(units) == 3  # served by the SECOND model


def test_pool_exhaustion_names_each_failure_and_recommends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ALL candidates 401 → PlannerError naming each model's failure class AND ending with
    # the actionable "configure a chat-capable provider" recommendation.
    monkeypatch.delenv("CHARON_DECOMPOSE_PLANNER_MODEL", raising=False)
    _serve_candidates(
        monkeypatch,
        [
            ("model-a", "https://api.openai.com/v1", "k1"),
            ("model-b", "https://api.openai.com/v1", "k2"),
        ],
    )

    def fake_post(model_id, base_url, api_key, prompt, timeout=60.0):
        raise P.PlannerTransportError("auth", 401, f"HTTP 401 from {model_id}")

    monkeypatch.setattr(P, "_post_chat", fake_post)

    with pytest.raises(P.PlannerError) as ei:
        P.plan_decomposition(R46_TICKET, R46_SURFACE)
    msg = str(ei.value)
    assert "model-a" in msg and "model-b" in msg
    assert "auth" in msg
    assert "configure a chat-capable provider" in msg


def test_garbage_body_reprompts_same_model_not_failover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A 200 with an unparseable body is a QUALITY fault of THIS model → re-prompt the SAME
    # model (return None), NOT a failover. With a single candidate and max_reprompts=1 the
    # model is asked twice, then the pool is exhausted → PlannerError. Proves transport vs
    # quality are distinguished: None never advances the candidate.
    monkeypatch.delenv("CHARON_DECOMPOSE_PLANNER_MODEL", raising=False)
    _serve_candidates(monkeypatch, [("only-model", "https://api.openai.com/v1", "k")])

    calls: list[str] = []

    def fake_post(model_id, base_url, api_key, prompt, timeout=60.0):
        calls.append(model_id)
        return None  # 200-but-garbage → quality fault → reprompt SAME model

    monkeypatch.setattr(P, "_post_chat", fake_post)

    with pytest.raises(P.PlannerError):
        P.plan_decomposition(R46_TICKET, R46_SURFACE, max_reprompts=1)
    # max_reprompts=1 → 2 attempts, ALL against the same single model (no failover).
    assert calls == ["only-model", "only-model"]


def test_ordered_candidates_pin_first_and_never_anthropic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Guards intact on the FULL ordered list: the pinned model is first, and no
    # Anthropic/claude candidate ever appears. FAIL-ON-REVERT: drop the pin/guard and this
    # goes RED.
    from charon import recommend
    from charon.config import tiers as tiers_cfg

    monkeypatch.setattr(P, "recommend_default_config_dir", lambda: "/nonexistent")
    monkeypatch.setenv("CHARON_DECOMPOSE_PLANNER_MODEL", "pinned-model")
    monkeypatch.setattr(tiers_cfg, "tier_members", lambda tier, tiers=None: ["hi-model"])
    monkeypatch.setattr(
        recommend,
        "_find_trusted_models",
        lambda cd: [
            ("claude-opus-4", "https://api.anthropic.com/v1", "k1"),
            ("some-anthropic", "https://api.anthropic.com/v1", "k2"),
            ("hi-model", "https://api.openai.com/v1", "k3"),
            ("pinned-model", "https://api.openai.com/v1", "k4"),
            ("plain-model", "https://api.openai.com/v1", "k5"),
        ],
    )
    ordered = P._ordered_planner_candidates(config_dir=None, is_detained=None)
    ids = [m for m, _, _ in ordered]
    assert ids[0] == "pinned-model"  # pin wins
    assert ids[1] == "hi-model"  # tier-high before the rest
    assert "claude-opus-4" not in ids  # never Anthropic
    assert not any("anthropic" in b.lower() for _, b, _ in ordered)


def test_intake_error_is_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    # Belt-and-braces: the planner's rejection is driven by assert_disjoint_waves raising
    # IntakeError, not by our own parsing — confirm the overlap payload parses fine but
    # is caught by the gate.
    surf = P.ChangeSurface.from_facts(R46_SURFACE)
    units = P._parse_units({"units": OVERLAP_2}, surf)
    assert len(units) == 2  # parses cleanly
    with pytest.raises(IntakeError):
        assert_disjoint_waves(units)  # the gate is what rejects it
