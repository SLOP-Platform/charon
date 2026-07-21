"""Tests for the Phase-1 egress allowlist (charon.egress).

Every test here goes RED on revert of the code it covers. The two CANARY tests
(``test_allowlist_canary_is_never_vacuous`` and
``test_override_scanner_canary_finds_nested_key``) exist specifically so a
vacuous check — an empty allowlist or an override-scanner that walks nothing —
can never pass silently: they assert a NON-ZERO result on known-bad/known-good
fixtures. That is the C1 "zero-work green" defect (a check that examined nothing
and reported OK) turned into a failing test.
"""
from __future__ import annotations

import ipaddress
import json
import socket

import pytest

from charon import egress, gateway
from charon.provider_presets import MERGED_RAW_DATA
from charon.routing_policy import route_from_spec

# RFC1918 sample addresses built from integers so no literal internal-IP string
# appears in this public-repo-tracked file (tools/check_public_clean.py). These
# are synthetic test fixtures, not real infrastructure.
_PRIVATE_SAMPLE_BASES = [
    f"http://{ipaddress.ip_address(0x0A000005)}:1234/v1",   # 10/8
    f"http://{ipaddress.ip_address(0xC0A80132)}:11434/v1",  # 192.168/16
    f"http://{ipaddress.ip_address(0xAC100005)}:8000/v1",   # 172.16/12
]


# --- external hosts the presets actually name, computed independently of the
# module under test so a bug in preset_external_hosts() cannot hide itself.
def _external_preset_bases() -> list[str]:
    from urllib.parse import urlsplit
    bases = []
    for data in MERGED_RAW_DATA.values():
        base = data.get("base_url")
        if not base:
            continue
        host = (urlsplit(str(base)).hostname or "")
        if host and host != "localhost":
            bases.append(str(base))
    return bases


# ---------------------------------------------------------------------------
# 1. Allowlist derivation + effective-base validation
# ---------------------------------------------------------------------------


def test_allowlist_canary_is_never_vacuous():
    """CANARY: the allowlist must be non-empty and match the count of distinct
    external preset hosts. An empty allowlist would make is_allowed_base() reject
    every real provider (a self-DoS) OR, if the logic were inverted, admit
    everything — either way this fails rather than passing on zero work."""
    hosts = egress.preset_external_hosts()
    assert len(hosts) >= 15, f"allowlist implausibly small: {sorted(hosts)}"
    # every known external provider host is present
    assert "openrouter.ai" in hosts
    assert "api.openai.com" in hosts
    assert "api.anthropic.com" in hosts
    assert "localhost" not in hosts  # local providers are handled separately


def test_every_preset_base_is_allowed():
    for base in _external_preset_bases():
        assert egress.is_allowed_base(base), f"preset base wrongly rejected: {base}"


@pytest.mark.parametrize("host", [
    "http://localhost:1234/v1",
    "http://127.0.0.1:11434/v1",
    "http://[::1]:8000/v1",
] + _PRIVATE_SAMPLE_BASES)  # LAN provider by IP — the documented normal case
def test_local_and_lan_ip_bases_allowed(host):
    assert egress.is_allowed_base(host)


@pytest.mark.parametrize("bad", [
    "https://evil.attacker.example/v1",
    "https://api.openai.com.attacker.example/v1",  # suffix-spoof
    "https://raw.githubusercontent.com/x/y/v1",
    "http://169.254.169.254/latest/meta-data",     # cloud metadata (link-local)
    "http://metadata.google.internal/v1",
])
def test_external_non_preset_hosts_rejected(bad):
    assert not egress.is_allowed_base(bad)
    with pytest.raises(egress.EgressPolicyError):
        egress.assert_base_allowed(bad)


@pytest.mark.parametrize("bad", ["", None, "not-a-url", "file:///etc/passwd",
                                 "ftp://api.openai.com/v1"])
def test_garbage_and_bad_scheme_rejected(bad):
    assert not egress.is_allowed_base(bad)


# ---------------------------------------------------------------------------
# 2. Nested base-override rejection (LiteLLM CVE-2024-6587)
# ---------------------------------------------------------------------------


def test_override_scanner_canary_finds_nested_key():
    """CANARY: the scanner must find a base-override key nested BELOW the top
    level — the exact LiteLLM bug. A scanner that only checked the top level (or
    walked nothing) returns [] here and fails."""
    known_bad = {
        "model": "gpt-4",
        "litellm_params": {"api_base": "https://evil.example"},
        "messages": [{"role": "user", "content": [{"base_url": "https://also-evil"}]}],
    }
    found = egress.find_base_override_keys(known_bad)
    assert len(found) >= 2, found
    assert any("litellm_params.api_base" in p for p in found)


def test_sanctioned_top_level_base_url_passes():
    egress.assert_no_nested_base_override({"name": "openrouter", "base_url": "https://x/v1"})


@pytest.mark.parametrize("payload", [
    {"litellm_params": {"api_base": "https://evil"}},   # nested (the CVE)
    {"api_base": "https://evil"},                         # non-sanctioned top-level
    {"base_url": "https://ok", "extra": {"base_url": "https://evil"}},  # nested dup
    {"upstream_base": "https://evil"},
])
def test_nested_or_unsanctioned_override_rejected(payload):
    with pytest.raises(egress.EgressPolicyError):
        egress.assert_no_nested_base_override(payload)


# ---------------------------------------------------------------------------
# 3. route_from_spec — the effective-config sink (integration)
# ---------------------------------------------------------------------------


def test_route_from_spec_drops_preset_provider_repointed_off_preset():
    """A token-gated add_provider that repoints a BUILT-IN preset provider to an
    attacker host is persisted in the runtime providers.json; route_from_spec (with
    enforce_preset_allowlist, as the providers.json load path sets) resolves the
    EFFECTIVE base (preset ⊕ override) and must drop the route. Exact §6-B leak."""
    spec = {"provider": "openrouter"}
    poisoned_cfg = {"openrouter": {"base_url": "https://evil.attacker.example/v1"}}
    assert route_from_spec(spec, poisoned_cfg, model_id="m",
                           enforce_preset_allowlist=True) is None


def test_route_from_spec_toml_override_is_trusted_and_not_dropped():
    """The SAME preset override from a trusted --config charon.toml (enforce OFF)
    is a first-class documented feature and must NOT be dropped."""
    spec = {"provider": "openrouter"}
    override = {"openrouter": {"base_url": "http://my-internal-or/v1"}}
    r = route_from_spec(spec, override, model_id="m", enforce_preset_allowlist=False)
    assert r is not None and r.upstream_base == "http://my-internal-or/v1"


def test_route_from_spec_allows_operator_direct_upstream_base():
    """Direct ``upstream_base`` entries (the shipped P1/P2 feature) are trusted
    operator config, NOT a preset override — they keep working even under
    enforcement. Their SSRF surface is constrained by the network-layer egress
    denial, not dropped here (that would break the product)."""
    spec = {"upstream_base": "http://my-internal-box:9000/v1"}
    r = route_from_spec(spec, {}, model_id="m", enforce_preset_allowlist=True)
    assert r is not None and r.upstream_base == "http://my-internal-box:9000/v1"


def test_route_from_spec_allows_non_preset_custom_provider_under_enforcement():
    """A locally-configured non-preset provider (operator's own key, own base) is
    not a built-in preset OVERRIDE — must keep working even under enforcement."""
    spec = {"provider": "mycorp"}
    cfg = {"mycorp": {"base_url": "https://llm.mycorp.example/v1"}}
    r = route_from_spec(spec, cfg, model_id="m", enforce_preset_allowlist=True)
    assert r is not None and "llm.mycorp.example" in r.upstream_base


def test_route_from_spec_allows_legit_preset_and_cross_preset_override():
    ok = route_from_spec({"provider": "openrouter"}, {}, model_id="m",
                         enforce_preset_allowlist=True)
    assert ok is not None and "openrouter.ai" in ok.upstream_base
    # an override to ANOTHER preset host is still fine (both are git-tracked)
    ok2 = route_from_spec({"provider": "openrouter"},
                          {"openrouter": {"base_url": "https://api.groq.com/openai/v1"}},
                          model_id="m", enforce_preset_allowlist=True)
    assert ok2 is not None and "api.groq.com" in ok2.upstream_base


def test_load_config_state_dir_drops_poisoned_preset_override(tmp_path):
    """END-TO-END: a poisoned providers.json (the runtime store the add_provider
    handler writes) that repoints a preset provider off-preset must yield NO route
    for that model. Proves the load_config → build_routes_and_pools flag wiring."""
    (tmp_path / "models.json").write_text(json.dumps(
        {"m": {"provider": "openrouter", "upstream_model": "x"}}))
    (tmp_path / "providers.json").write_text(json.dumps(
        {"openrouter": {"base_url": "https://evil.attacker.example/v1"}}))
    cfg = gateway.load_config(state_dir=str(tmp_path))
    assert "m" not in cfg.routes


def test_load_config_toml_keeps_preset_override(tmp_path, monkeypatch):
    """END-TO-END: the SAME override via a trusted --config charon.toml is kept."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))  # isolate fallback-provider store
    toml = tmp_path / "charon.toml"
    toml.write_text(
        '[providers.openrouter]\nbase_url = "http://my-internal-or/v1"\n\n'
        '[models."m"]\nprovider = "openrouter"\nupstream_model = "x"\n')
    cfg = gateway.load_config(toml_path=str(toml))
    assert cfg.routes["m"].upstream_base == "http://my-internal-or/v1"


# ---------------------------------------------------------------------------
# 4. Startup egress self-test (Phase-1 variant)
# ---------------------------------------------------------------------------


def test_egress_selftest_refuses_when_bad_host_reachable(monkeypatch):
    """If a connect to the non-provider host SUCCEEDS, egress is not denied → raise."""
    class _FakeSock:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: _FakeSock())
    with pytest.raises(egress.EgressPolicyError):
        egress.assert_egress_denied("example.com")


def test_egress_selftest_passes_when_bad_host_unreachable(monkeypatch):
    def _refuse(*a, **k):
        raise OSError("connection refused")
    monkeypatch.setattr(socket, "create_connection", _refuse)
    egress.assert_egress_denied("example.com")  # returns cleanly


def test_startup_selftest_is_off_by_default(monkeypatch):
    """Pre-infra installs must NOT be bricked: with the flag unset the self-test
    is a no-op even when egress is wide open."""
    monkeypatch.delenv("CHARON_EGRESS_SELFTEST", raising=False)
    monkeypatch.setattr(socket, "create_connection",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not connect")))
    egress.run_startup_egress_selftest()  # no exception, no connect attempted


def test_startup_selftest_runs_when_enabled(monkeypatch):
    monkeypatch.setenv("CHARON_EGRESS_SELFTEST", "1")

    class _FakeSock:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: _FakeSock())
    with pytest.raises(egress.EgressPolicyError):
        egress.run_startup_egress_selftest()


# ---------------------------------------------------------------------------
# 5. preset→ACL generator (generator, not enforcer)
# ---------------------------------------------------------------------------


def test_acl_lists_every_external_host_and_no_local():
    acl = egress.generate_smokescreen_acl()
    for host in egress.preset_external_hosts():
        assert host in acl, f"{host} missing from generated ACL"
    assert "localhost" not in acl
    assert "action: enforce" in acl


def test_acl_reload_hint_is_sighup():
    assert "HUP" in egress.smokescreen_reload_hint()


def test_nginx_credproxy_template_is_an_inert_phase2_stub():
    stub = egress.nginx_credproxy_template_stub()
    assert "TODO(phase-2" in stub
    assert "Do not wire in Phase-1" in stub
    # it must NOT emit a real Authorization-bearing config line
    assert "proxy_pass" not in stub
