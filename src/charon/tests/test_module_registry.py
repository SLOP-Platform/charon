"""BUILD-SERVER-EPHEMERAL-PORT: module-registry tests that bind ephemeral ports.

Demonstrates that ``build_server`` (or the test harness) binds an EPHEMERAL port
(port 0 / OS-assigned) when under test, so no two runs collide on the shared
4-LOM runner.  Includes a FAIL-ON-REVERT guard: a pre-bound fixed port (8080)
must NOT cause ``build_server`` to fail when it uses port 0.
"""
from __future__ import annotations

import json
import os
import socket
import threading
from pathlib import Path

import pytest

from charon.gateway import GatewayConfig, _module_inst, build_server


# ── Module registry basics ──────────────────────────────────────────────

_MODULE_NAMES = [
    ("cache", "SemanticCache"),
    ("normalizer", "ResponseNormalizer"),
    ("guardrails", "Guardrails"),
    ("observability", "Observability"),
    ("quality", "QualityScorer"),
    ("spend", "SpendLimiter"),
    ("inspector", "RequestInspector"),
    ("session_affinity", "SessionAffinity"),
    ("vkeys", "VirtualKeyManager"),
    ("policy", "PolicyRouter"),
]


@pytest.mark.parametrize("name,cls_name", _MODULE_NAMES)
def test_module_inst_creates_instance(name, cls_name):
    inst = _module_inst(name)
    assert inst is not None, f"_module_inst({name!r}) returned None"
    assert type(inst).__name__ == cls_name, (
        f"Expected {cls_name}, got {type(inst).__name__}")


def test_module_inst_speculative_disabled_by_default():
    inst = _module_inst("speculative")
    assert inst is None


def test_module_inst_consensus_disabled_by_default():
    inst = _module_inst("consensus")
    assert inst is None


def test_module_inst_custom_config(tmp_path: Path):
    cfg_file = tmp_path / "cache.json"
    cfg_file.write_text(json.dumps({"max_size": 42}))
    inst = _module_inst("cache", state_dir=tmp_path)
    from charon.cache import SemanticCache
    assert isinstance(inst, SemanticCache)
    assert inst._max_size == 42


# ── Ephemeral port: build_server avoids fixed-port collisions ───────────

def test_build_server_ephemeral_port_param():
    """build_server accepts an explicit port=0 param → OS-assigned."""
    cfg = GatewayConfig(host="127.0.0.1", model_ids=[])
    srv = build_server(cfg, port=0)
    try:
        _, bound_port = srv.server_address[:2]
        assert bound_port != 0
        assert bound_port != 8080
        srv.serve_in_thread()
        assert bound_port > 0
    finally:
        srv.shutdown()


def test_build_server_port_param_overrides_config_port():
    """port=9999 overrides cfg.port=8080."""
    cfg = GatewayConfig(host="127.0.0.1", port=8080, model_ids=[])
    srv = build_server(cfg, port=9999)
    try:
        _, bound_port = srv.server_address[:2]
        assert bound_port == 9999
    finally:
        srv.shutdown()


def test_two_build_servers_ephemeral_no_collision():
    """Two servers on port 0 → both bind, no Address-in-use."""
    cfg = GatewayConfig(host="127.0.0.1", model_ids=[])
    srv1 = build_server(cfg, port=0)
    srv2 = build_server(cfg, port=0)
    try:
        _, p1 = srv1.server_address[:2]
        _, p2 = srv2.server_address[:2]
        assert p1 != p2
        assert p1 > 0
        assert p2 > 0
    finally:
        srv1.shutdown()
        srv2.shutdown()


def test_build_server_ephemeral_while_fixed_port_is_pre_bound():
    """FAIL-ON-REVERT: pre-bind 8080, then build_server(port=0) must succeed.

    If the fixed-port regression is re-introduced, this test turns RED because
    the server would try to bind 8080 (already taken).
    """
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", 8080))
    blocker.listen(1)

    try:
        cfg = GatewayConfig(host="127.0.0.1", model_ids=[])
        srv = build_server(cfg, port=0)
        try:
            _, bp = srv.server_address[:2]
            assert bp > 0
            assert bp != 8080
        finally:
            srv.shutdown()
    finally:
        blocker.close()


def test_build_server_ephemeral_twice_while_fixed_port_pre_bound():
    """Two ephemeral servers while 8080 is blocked → both succeed."""
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", 8080))
    blocker.listen(1)

    cfg = GatewayConfig(host="127.0.0.1", model_ids=[])
    srv1 = build_server(cfg, port=0)
    srv2 = build_server(cfg, port=0)
    try:
        _, p1 = srv1.server_address[:2]
        _, p2 = srv2.server_address[:2]
        assert p1 != p2
        assert p1 != 8080
        assert p2 != 8080
    finally:
        srv1.shutdown()
        srv2.shutdown()
        blocker.close()


def test_concurrent_thread_servers_no_port_collision():
    """Two servers in separate threads on port 0 → no OSError."""
    cfg = GatewayConfig(host="127.0.0.1", model_ids=[])
    srv1 = build_server(cfg, port=0)
    srv2 = build_server(cfg, port=0)
    t1 = srv1.serve_in_thread()
    t2 = srv2.serve_in_thread()
    try:
        t1.join(timeout=5)
        t2.join(timeout=5)
        _, p1 = srv1.server_address[:2]
        _, p2 = srv2.server_address[:2]
        assert p1 != p2
    except OSError:
        pytest.fail("Address already in use — port collision on ephemeral bind")
    finally:
        srv1.shutdown()
        srv2.shutdown()


def test_build_server_twice_same_process_no_collision():
    """Build, shutdown, rebuild on the same process → second bind succeeds.

    This mimics back-to-back test runs (``pytest -k registry`` twice in the
    same process), proving the GREEN-IS-NOT-PROOF contract — it must pass
    even with a pre-bound fixed port.
    """
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", 8080))
    blocker.listen(1)

    try:
        for _ in range(4):
            cfg = GatewayConfig(host="127.0.0.1", model_ids=[])
            srv = build_server(cfg, port=0)
            srv.shutdown()
    except OSError as e:
        pytest.fail(f"Address-in-use during back-to-back bind: {e}")
    finally:
        blocker.close()
