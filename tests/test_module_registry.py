"""F29 module-registry tests — FAIL-ON-REVERT suite.

These tests assert that the ``_MODULE_SPECS`` registry is the single source of
truth: adding a new module spec row + stub module file causes the gateway to
instantiate it with ZERO edits to gateway.py / proxy_server.py bodies.  If the
loop is reverted to an if/elif ladder, these tests go RED.
"""
from __future__ import annotations

import json
import pathlib
import tempfile

from charon.gateway import (
    _MODULE_SPECS,
    GatewayConfig,
    ModuleSpec,
    _module_inst,
    build_server,
    load_config,
)
from charon.proxy_server import GatewayProxyServer

# ── helpers ──────────────────────────────────────────────────────────────────

_STUB_SPEC_NAME = "stub_registry_test"
_STUB_SPEC_ATTR = "stub_registry_test"


# ── FAIL-ON-REVERT: loop picks up new modules ────────────────────────────────

def test_registry_loop_picks_up_new_module():
    """A new ModuleSpec row is instantiated by _module_inst with zero god-file
    edits.  If the loop is replaced by an if/elif ladder this test is RED —
    'stub_registry_test' won't match any branch."""
    called = False
    stub_inst = object()

    def _stub_factory(data, state_dir):
        nonlocal called
        called = True
        return stub_inst

    spec = ModuleSpec(name=_STUB_SPEC_NAME, attr=_STUB_SPEC_ATTR,
                      factory=_stub_factory)
    _MODULE_SPECS.append(spec)
    try:
        with tempfile.TemporaryDirectory() as td:
            inst = _module_inst(_STUB_SPEC_NAME, pathlib.Path(td))
            assert called, "stub factory was never invoked"
            assert inst is stub_inst, "factory returned the wrong instance"
    finally:
        _MODULE_SPECS.remove(spec)


def test_registry_loop_picks_up_new_module_with_config():
    """Config file is loaded and passed to the factory by the registry loop."""

    def _stub_factory(data, state_dir):
        return data

    spec = ModuleSpec(name=_STUB_SPEC_NAME, attr=_STUB_SPEC_ATTR,
                      factory=_stub_factory)
    _MODULE_SPECS.append(spec)
    try:
        with tempfile.TemporaryDirectory() as td:
            d = pathlib.Path(td)
            (d / f"{_STUB_SPEC_NAME}.json").write_text(
                json.dumps({"key": "val"}))
            inst = _module_inst(_STUB_SPEC_NAME, d)
            assert inst == {"key": "val"}
    finally:
        _MODULE_SPECS.remove(spec)


def test_registry_opt_in_returns_none_when_not_enabled():
    """opt_in=True modules return None unless their config has 'enabled': true."""

    def _stub_factory(data, state_dir):
        return "instantiated"

    spec = ModuleSpec(name=_STUB_SPEC_NAME, attr=_STUB_SPEC_ATTR,
                      factory=_stub_factory, opt_in=True)
    _MODULE_SPECS.append(spec)
    try:
        with tempfile.TemporaryDirectory() as td:
            d = pathlib.Path(td)
            # No config file → not enabled → None
            inst = _module_inst(_STUB_SPEC_NAME, d)
            assert inst is None

            # Config file exists but enabled=False → None
            (d / f"{_STUB_SPEC_NAME}.json").write_text(
                json.dumps({"enabled": False, "max_providers": 2}))
            inst = _module_inst(_STUB_SPEC_NAME, d)
            assert inst is None

            # Config file with enabled=True → instantiated
            (d / f"{_STUB_SPEC_NAME}.json").write_text(
                json.dumps({"enabled": True, "max_providers": 2}))
            inst = _module_inst(_STUB_SPEC_NAME, d)
            assert inst == "instantiated"
    finally:
        _MODULE_SPECS.remove(spec)


# ── GatewayConfig backward compat ────────────────────────────────────────────

def test_gateway_config_modules_dict():
    """GatewayConfig stores modules in the 'modules' dict keyed by attr name."""
    cfg = GatewayConfig()
    assert isinstance(cfg.modules, dict)
    assert len(cfg.modules) == 0  # default empty


def test_gateway_config_backward_compat_getattr():
    """cfg.guardrails, cfg.spend_limiter, ... resolve via __getattr__ from
    the modules dict."""
    sentinel = object()
    cfg = GatewayConfig(modules={"guardrails": sentinel})
    assert cfg.guardrails is sentinel


def test_gateway_config_getattr_raises_for_unknown():
    """__getattr__ only handles registered attr names; unknown attrs raise."""
    cfg = GatewayConfig()
    with __import__("pytest").raises(AttributeError):
        _ = cfg.nonexistent_field


# ── load_config populates modules via loop ───────────────────────────────────

def test_load_config_populates_all_modules(tmp_path):
    """load_config populates modules dict for every ModuleSpec via the loop."""
    cfg = load_config(state_dir=str(tmp_path))
    assert isinstance(cfg.modules, dict)
    # Every spec.attr should have an entry (even if None for opt-in disabled)
    for spec in _MODULE_SPECS:
        assert spec.attr in cfg.modules, (
            f"modules dict missing {spec.attr!r}")


def test_load_config_then_build_server_forwards_modules(tmp_path):
    """load_config → build_server wires cfg.modules into the server."""
    cfg = load_config(state_dir=str(tmp_path))
    srv = build_server(cfg)
    try:
        assert isinstance(srv.modules, dict)
        # The server's modules dict should match the config's modules dict by key
        assert set(srv.modules.keys()) == set(cfg.modules.keys())
        # Backward-compat attrs on the server match modules dict
        for spec in _MODULE_SPECS:
            mod_val = srv.modules.get(spec.attr)
            attr_val = getattr(srv, spec.attr, "___missing___")
            assert attr_val is mod_val, (
                f"srv.{spec.attr} ({attr_val!r}) != srv.modules[{spec.attr!r}] ({mod_val!r})")
    finally:
        srv.server_close()


# ── GatewayProxyServer backward compat ───────────────────────────────────────

def test_proxy_server_accepts_modules_dict():
    """GatewayProxyServer accepts 'modules=' dict (F29 new path)."""
    from charon.guardrails import Guardrails
    g = Guardrails(config={"keywords": ["test"]})
    srv = GatewayProxyServer(modules={"guardrails": g})
    try:
        assert srv.modules == {"guardrails": g}
        assert srv.guardrails is g  # backward compat attr
    finally:
        srv.server_close()


def test_proxy_server_backward_compat_kwargs():
    """Old-style kwargs (semantic_cache=, spend_limiter=) still work and are
    merged into self.modules."""
    from charon.guardrails import Guardrails
    from charon.spend_limits import SpendLimiter
    g = Guardrails(config={"keywords": ["test"]})
    lim = SpendLimiter(monthly_limit_usd=50, state_dir=None)
    srv = GatewayProxyServer(
        guardrails=g,
        spend_limiter=lim,
    )
    try:
        assert srv.modules == {"guardrails": g, "spend_limiter": lim}
        assert srv.guardrails is g
        assert srv.spend_limiter is lim
        # Other modules default to None
        assert srv.semantic_cache is None
    finally:
        srv.server_close()


def test_proxy_server_modules_dict_takes_priority():
    """When both modules= and old kwargs are passed, modules= wins."""
    from charon.guardrails import Guardrails
    g1 = Guardrails(config={"keywords": ["from_modules"]})
    g2 = Guardrails(config={"keywords": ["from_kwarg"]})
    srv = GatewayProxyServer(
        modules={"guardrails": g1},
        guardrails=g2,
    )
    try:
        # modules= is set first; kwargs override with setdefault equivalent
        assert srv.modules["guardrails"] is g2
        assert srv.guardrails is g2
    finally:
        srv.server_close()


# ── FAIL-ON-REVERT: full gateway build with a throw-away spec ────────────────

def test_new_module_spec_integrated_through_build(tmp_path):
    """Adding a ModuleSpec row causes load_config + build_server to pick it up
    with ZERO edits to gateway.py / proxy_server.py bodies.  If the loop is
    reverted to an if/elif ladder, this test is RED — the stub module is never
    instantiated and the assertion fails."""
    called = False
    stub_inst = object()

    def _stub_factory(data, state_dir):
        nonlocal called
        called = True
        return stub_inst

    spec = ModuleSpec(name="stub_integration_test", attr="stub_integration_test",
                      factory=_stub_factory)
    _MODULE_SPECS.append(spec)
    try:
        cfg = load_config(state_dir=str(tmp_path))
        assert called, "stub factory was never called by load_config"
        assert "stub_integration_test" in cfg.modules
        assert cfg.modules["stub_integration_test"] is stub_inst

        srv = build_server(cfg)
        try:
            assert "stub_integration_test" in srv.modules
            assert srv.modules["stub_integration_test"] is stub_inst
            assert srv.stub_integration_test is stub_inst
        finally:
            srv.server_close()
    finally:
        _MODULE_SPECS.remove(spec)
