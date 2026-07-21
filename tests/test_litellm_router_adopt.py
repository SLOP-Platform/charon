"""Preservation tests for the litellm.Router adopt (ADR-0017 / ADOPT-MAP.md).

Every test here is FAIL-ON-REVERT: it pins one of the money-path controls that MUST survive
the commodity-plane adopt (MANAGER-RULES §8). Reverting the corresponding guard in
``litellm_plane.litellm_router`` turns the test red.

Controls covered:
  1. base-bound provider key (#181)                -> test_key_is_base_bound*, test_deployment_*
  2. SSRF / non-routable refusal                   -> test_ssrf_base_*
  3. preset-derived egress allowlist (egress.py)   -> test_off_preset_base_*, test_local_base_*
  4. no-redirect transport                         -> test_no_redirect_client
  5. SG-never-Anthropic                            -> test_anthropic_route_*
  6. cold-start / static order equivalence         -> test_chain_order_preserved

Bases are drawn from the git-tracked preset external hosts (the fail-closed egress allowlist
would otherwise refuse a made-up host).
"""
from __future__ import annotations

import pytest

from charon import egress, secrets
from charon.litellm_plane import litellm_router as lr
from charon.proxy_server import UpstreamRoute

GOOD_BASE = "https://api.deepseek.com/v1"       # preset-allowlisted external host
OTHER_PRESET_BASE = "https://api.groq.com/openai/v1"  # a DIFFERENT preset host (same allowlist)
OFF_PRESET_BASE = "https://attacker.example/v1"  # public, passes SSRF, NOT on the allowlist
LOCAL_BASE = "http://127.0.0.1:1234/v1"          # local provider (allowed regardless of preset)


# ── control 1: base-bound provider key (#181) ──────────────────────────────────


def test_key_is_base_bound_to_its_own_base(monkeypatch, tmp_path):
    """A key stored for (provider, GOOD_BASE) resolves for a route on GOOD_BASE."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    secrets.set_provider_key("acme", "SECRET-KEY", base_url=GOOD_BASE)

    route = UpstreamRoute(upstream_base=GOOD_BASE, api_key=None, provider="acme")
    assert lr.resolve_route_key(route) == "SECRET-KEY"


def test_key_not_sent_to_a_moved_base(monkeypatch, tmp_path):
    """Same provider, key stored for GOOD_BASE, but the route's base was moved to a DIFFERENT
    base: the base-bound resolver returns NO key.

    Fail-on-revert: making resolution base-agnostic (e.g. returning ``route.api_key`` or
    dropping ``base_url=`` from the resolver call) would leak the key to the moved base."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    secrets.set_provider_key("acme", "SECRET-KEY", base_url=GOOD_BASE)

    moved = UpstreamRoute(upstream_base=OTHER_PRESET_BASE, api_key="SECRET-KEY", provider="acme")
    assert lr.resolve_route_key(moved) is None


def test_deployment_carries_base_bound_key(monkeypatch, tmp_path):
    """The model_list deployment attaches the key ONLY to its own base; the moved-base
    variant carries no key. Proves control 1 flows all the way into the litellm model_list."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    secrets.set_provider_key("acme", "SECRET-KEY", base_url=GOOD_BASE)

    good = UpstreamRoute(upstream_base=GOOD_BASE, api_key=None, provider="acme",
                         upstream_model="m1")
    moved = UpstreamRoute(upstream_base=OTHER_PRESET_BASE, api_key="SECRET-KEY", provider="acme",
                          upstream_model="m1")
    ml_good = lr.build_model_list({"m1": [good]})
    ml_moved = lr.build_model_list({"m1": [moved]})
    assert ml_good[0]["litellm_params"]["api_key"] == "SECRET-KEY"
    assert ml_good[0]["litellm_params"]["api_base"] == GOOD_BASE
    assert ml_moved[0]["litellm_params"]["api_key"] is None


def test_direct_keyless_route_uses_its_own_key():
    """A route with NO provider id (a direct entry, no per-provider store) keeps its own key."""
    route = UpstreamRoute(upstream_base=GOOD_BASE, api_key="DIRECT-KEY", provider=None)
    assert lr.resolve_route_key(route) == "DIRECT-KEY"


# ── control 2: SSRF / non-routable refusal ─────────────────────────────────────


@pytest.mark.parametrize("bad_base", [
    "http://169.254.169.254/v1",           # cloud metadata (link-local)
    "http://[::ffff:169.254.169.254]/v1",  # IPv4-mapped metadata
    "ftp://api.deepseek.com/v1",            # non-http scheme
])
def test_ssrf_base_is_refused(bad_base):
    """An unsafe base raises AdoptError and never enters the model_list.

    Fail-on-revert: dropping the ``validate_base_url`` call lets the metadata endpoint into
    the Router."""
    route = UpstreamRoute(upstream_base=bad_base, api_key=None, provider=None)
    with pytest.raises(lr.AdoptError):
        lr.build_model_list({"m1": [route]})


# ── control 3: preset-derived egress allowlist (reconciled with egress.py) ─────


def test_off_preset_base_is_refused():
    """A public, SSRF-clean base whose host is NOT a git-tracked preset is REFUSED by the
    fail-closed egress allowlist — exactly as the live route_from_spec path refuses it.

    Fail-on-revert: dropping the ``egress.assert_base_allowed`` call lets litellm_plane reach
    an arbitrary host, bypassing the allowlist the live money-path now enforces."""
    route = UpstreamRoute(upstream_base=OFF_PRESET_BASE, api_key="k", provider=None)
    with pytest.raises(egress.EgressPolicyError):
        lr.build_model_list({"m1": [route]})


def test_preset_repointed_off_preset_is_refused(monkeypatch, tmp_path):
    """A provider that legitimately has a preset, repointed to an off-preset attacker base,
    is refused — the config-override key-exfil class egress.py closes, enforced on the
    litellm_plane path too."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    secrets.set_provider_key("deepseek", "SECRET", base_url=GOOD_BASE)
    repointed = UpstreamRoute(upstream_base=OFF_PRESET_BASE, api_key=None, provider="deepseek")
    with pytest.raises(egress.EgressPolicyError):
        lr.build_model_list({"deepseek-chat": [repointed]})


def test_local_base_is_allowed():
    """A local provider (loopback) is allowed regardless of the preset set — the documented
    self-hosted case egress._is_local_host permits."""
    route = UpstreamRoute(upstream_base=LOCAL_BASE, api_key=None, provider=None)
    ml = lr.build_model_list({"m1": [route]})
    assert ml[0]["litellm_params"]["api_base"] == LOCAL_BASE


def test_good_preset_base_is_accepted():
    route = UpstreamRoute(upstream_base=GOOD_BASE, api_key="k", provider=None)
    ml = lr.build_model_list({"m1": [route]})
    assert ml[0]["litellm_params"]["api_base"] == GOOD_BASE


# ── control 5: SG-never-Anthropic ──────────────────────────────────────────────


@pytest.mark.parametrize("route,agent", [
    # base host is preset-allowlisted (anthropic preset exists for wire support), but the
    # SG guard drops it regardless of the allowlist:
    (UpstreamRoute(upstream_base="https://api.anthropic.com/v1", provider="anthropic"), "gpt"),
    # allowlisted host, anthropic named only in the upstream model id:
    (UpstreamRoute(upstream_base=GOOD_BASE, provider="deepseek",
                   upstream_model="anthropic/claude-3.5-sonnet"), "gpt"),
    # allowlisted host, anthropic named only in the agent-facing model id:
    (UpstreamRoute(upstream_base=GOOD_BASE, provider="deepseek"), "claude-3-opus"),
])
def test_anthropic_route_is_dropped(route, agent):
    """Any Anthropic identifier (base / provider / upstream model / agent model) drops the
    candidate from the model_list — it can never be selected.

    Fail-on-revert: removing the ``_is_anthropic`` screen re-admits an Anthropic deployment."""
    ml = lr.build_model_list({agent: [route]})
    assert ml == []


def test_non_anthropic_route_survives_alongside_anthropic():
    good = UpstreamRoute(upstream_base=GOOD_BASE, api_key="k", provider="acme")
    claude = UpstreamRoute(upstream_base="https://api.anthropic.com/v1", provider="anthropic")
    ml = lr.build_model_list({"m1": [good, claude]})
    assert len(ml) == 1
    assert ml[0]["litellm_params"]["api_base"] == GOOD_BASE


# ── control 4: no-redirect transport ───────────────────────────────────────────


def test_no_redirect_client_disables_redirects():
    pytest.importorskip("httpx")
    client = lr.no_redirect_client()
    try:
        assert client.follow_redirects is False
    finally:
        client.close()


# ── control 6: cold-start / static order equivalence ───────────────────────────


def test_chain_order_preserved():
    """With no grades and no live-cost signal, the deployment order equals the input chain
    order (the static cheapest-capable / cold-start path, byte-order-identical)."""
    r1 = UpstreamRoute(upstream_base=GOOD_BASE, api_key="k", provider="a", upstream_model="ma")
    r2 = UpstreamRoute(upstream_base=OTHER_PRESET_BASE, api_key="k", provider="b",
                       upstream_model="mb")
    ml = lr.build_model_list({"m1": [r1, r2]})
    assert [e["litellm_params"]["api_base"] for e in ml] == [GOOD_BASE, OTHER_PRESET_BASE]
    assert all(e["model_name"] == "m1" for e in ml)


# ── the actual Router construction (needs litellm installed) ───────────────────


def test_make_router_builds_from_live_server(monkeypatch, tmp_path):
    """make_router assembles a real litellm.Router from a server's pools, with the preserved
    controls applied. Skipped when litellm is not installed (the pure builder above still
    proves the security controls)."""
    pytest.importorskip("litellm")
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))

    class _FakeServer:
        default_cooldown = 45.0
        balance_tracker = None
        routes: dict = {}
        pools = {
            "m1": [
                UpstreamRoute(upstream_base=GOOD_BASE, api_key="k1", provider="acme",
                              upstream_model="ma"),
                UpstreamRoute(upstream_base="https://api.anthropic.com/v1",
                              provider="anthropic"),  # must be dropped
            ]
        }

    router = lr.make_router(_FakeServer())
    names = [d["litellm_params"]["model"] for d in router.model_list]
    # exactly one deployment (the anthropic leg dropped), speaking the openai-compat wire
    assert names == ["openai/ma"]
    assert router.cooldown_time == 45.0
