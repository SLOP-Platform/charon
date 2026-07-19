"""Tier-routing Phase B (ADR-0014 D6) — multi-tier decompose routing + warm lifecycle.

Phase A routed ONE tier per run: a decompose run whose role-DAG stages span tiers
collapsed to a single model. Phase B builds a warm-agent-per-tier map and a
``StaticRouter.route`` that selects the backend by the dispatch's tier, so each
stage reaches ITS tier's model. These tests pin that AT THE WIRE — the mock
upstream records the (gateway-rewritten) model id per dispatch — reusing the
capture pattern from ``test_gateway_failover.py:19-31`` / ``test_run_task_routing``.

Covered:
  - a multi-tier decompose run sends each stage to its tier's model (the headline);
  - a single-tier (non-decompose) run is unchanged — Phase A's len==1 special case;
  - a warm agent reuses its subprocess across dispatches (D010 warm-pool default),
    and the per-tier map holds a DISTINCT subprocess per tier.
"""
from __future__ import annotations

import http.server
import json
import shlex
import socketserver
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from charon import api, gitutil
from charon import proxy_server as proxy_server_mod
from charon.adapters.acp import AcpBackend
from charon.decompose import decompose as decompose_stages
from charon.router import StaticRouter
from charon.types import Budget, Tier, WorkUnit

# ---------------------------------------------------------------------------
# Mock upstream — captures the (gateway-rewritten) wire model id per dispatch.
# Same shape as test_gateway_failover.py / test_run_task_routing.py.
# ---------------------------------------------------------------------------


class _Prog(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a: object) -> None:  # type: ignore[override]
        pass

    def do_POST(self) -> None:
        srv = self.server  # type: ignore[assignment]
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        srv.received.append(body.get("model"))  # type: ignore[attr-defined]
        payload = json.dumps({
            "model": body.get("model"),
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    received: list
    return_model: str


def _up() -> tuple[_Threaded, str]:
    srv = _Threaded(("127.0.0.1", 0), _Prog)
    srv.received = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]}:{srv.server_address[1]}"  # type: ignore[str-bytes-safe]


# ---------------------------------------------------------------------------
# Persistent ACP stub: speaks ACP and fires one POST per session/prompt to the
# per-run gateway proxy with the tier vid baked into OPENCODE_CONFIG_CONTENT.
# Loops (no break) so ONE warm subprocess serves MANY dispatches (D010).
# ---------------------------------------------------------------------------

_STUB = textwrap.dedent("""\
    import json, os, sys, urllib.request

    def _proxy_post():
        raw = os.environ.get("OPENCODE_CONFIG_CONTENT", "")
        if not raw:
            return
        cfg = json.loads(raw)
        prov = next(iter(cfg.get("provider", {})), None)
        if prov is None:
            return
        opts = cfg["provider"][prov]["options"]
        model = next(iter(cfg["provider"][prov]["models"]))  # the short tier vid
        base = opts["baseURL"].rstrip("/")
        body = json.dumps({"model": model}).encode()
        req = urllib.request.Request(
            base + "/chat/completions", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        method, mid = msg.get("method", ""), msg.get("id")
        if method == "session/new":
            res: dict = {"sessionId": "s1"}
        elif method == "session/prompt":
            _proxy_post()
            res = {}
        else:
            res = {}
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": res}) + "\\n")
        sys.stdout.flush()
""")


def _acp_cmd(stub: Path) -> str:
    return f"{sys.executable} {shlex.quote(str(stub))}"


def _write_two_tier_registry(state_dir: Path, charon_home: Path, upstream_base: str) -> None:
    """models.json: a 'high' and a 'med' member, each rewriting to a DISTINCT wire
    model on the SAME mock upstream; tiers.json maps high→['m-high'], med→['m-med'].
    So the upstream records WHICH tier each dispatch resolved to."""
    (state_dir / "models.json").write_text(json.dumps({
        "m-high": {"upstream_base": upstream_base, "upstream_model": "high-wire",
                   "free": True, "cost_rank": 0},
        "m-med": {"upstream_base": upstream_base, "upstream_model": "med-wire",
                  "free": True, "cost_rank": 0},
    }))
    (charon_home / "tiers.json").write_text(json.dumps({
        "order": ["low", "med", "high"],
        "members": {"low": [], "med": ["m-med"], "high": ["m-high"]},
        "aliases": {},
    }))


def _write_single_tier_two_member_registry(
    state_dir: Path, charon_home: Path, upstream_base: str
) -> None:
    """ONE tier ('high') with a 2-MEMBER pool whose members rewrite to DISTINCT
    wire models on the SAME mock upstream, so the upstream records WHICH member the
    gateway selected within the tier. The members are listed PAID-FIRST in
    tiers.json (m-paid before m-free); the gateway's shared compiler must still sort
    the FREE/cheaper member first (free-first→cost_rank), so a correct run hits
    'free-wire'. If within-tier ordering regresses, the upstream gets 'paid-wire'."""
    (state_dir / "models.json").write_text(json.dumps({
        "m-paid": {"upstream_base": upstream_base, "upstream_model": "paid-wire",
                   "free": False, "cost_rank": 10},
        "m-free": {"upstream_base": upstream_base, "upstream_model": "free-wire",
                   "free": True, "cost_rank": 0},
    }))
    (charon_home / "tiers.json").write_text(json.dumps({
        "order": ["low", "med", "high"],
        # listed paid-first on purpose — the gateway must re-sort free-first.
        "members": {"low": [], "med": [], "high": ["m-paid", "m-free"]},
        "aliases": {},
    }))


# ---------------------------------------------------------------------------
# 1. The headline: multi-tier decompose routes each stage to its tier's model.
# ---------------------------------------------------------------------------


def test_multitier_decompose_routes_each_stage_to_its_tier(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    charon_home = tmp_path / "charon_home"
    charon_home.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("CHARON_HOME", str(charon_home))

    upstream, upstream_base = _up()
    stub = tmp_path / "stub_agent.py"
    stub.write_text(_STUB)
    try:
        _write_two_tier_registry(state_dir, charon_home, upstream_base)
        # accept=['false'] keeps acceptance failing so EVERY stage dispatches
        # (a passing check would short-circuit is_complete before any dispatch).
        result = api.run_task(
            goal="multi-tier route-check",
            accept=["false"],
            role="high",
            acp_cmd=_acp_cmd(stub),
            state_dir=str(state_dir),
            autonomy="L0",
            decompose=True,
        )
    finally:
        upstream.shutdown()

    assert result.get("status") != "exhausted", result

    # Expected wire sequence = each DISPATCHED stage's tier model, computed from the
    # real DAG so the test tracks policy, not a hand-copied list. The Validate stage
    # runs executable acceptance ('false' → fails) and stops the pipeline before
    # Close, so dispatches run triage…validate.
    wire = {"high": "high-wire", "med": "med-wire"}
    policy = StaticRouter()
    stages = decompose_stages("multi-tier route-check", ["false"])
    vidx = next(i for i, s in enumerate(stages) if s.role == "validate")
    expected = [wire[policy.tier_for(s.task_class).value] for s in stages[: vidx + 1]]

    assert upstream.received == expected, (
        f"per-stage tier routing regressed: upstream got {upstream.received!r}, "
        f"expected {expected!r} (each stage must reach ITS tier's model)"
    )
    # Sanity: the run genuinely spanned BOTH tiers (not a single-tier collapse).
    assert {"high-wire", "med-wire"} <= set(upstream.received)


# ---------------------------------------------------------------------------
# 2. A single-tier (non-decompose) run is unchanged — Phase A's len==1 case.
# ---------------------------------------------------------------------------


def test_single_tier_run_unchanged(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    charon_home = tmp_path / "charon_home"
    charon_home.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("CHARON_HOME", str(charon_home))

    upstream, upstream_base = _up()
    stub = tmp_path / "stub_agent.py"
    stub.write_text(_STUB)
    try:
        _write_two_tier_registry(state_dir, charon_home, upstream_base)
        result = api.run_task(
            goal="single-tier route-check",
            accept=["false"],  # one dispatch, then L0 propose-only rolls back
            role="high",
            acp_cmd=_acp_cmd(stub),
            state_dir=str(state_dir),
            autonomy="L0",
            max_checkpoints=1,
        )
    finally:
        upstream.shutdown()

    assert result.get("status") != "exhausted", result
    # Exactly one dispatch, to the role's tier alone — the len==1 warm map. Even
    # though the default task_class ('codegen'→med) maps elsewhere, a single-backend
    # run has no tier-keyed backend, so route() falls through to it (Phase A intact).
    assert upstream.received == ["high-wire"], upstream.received


# ---------------------------------------------------------------------------
# 3. Warm-agent reuse vs relaunch (D010 warm-pool default).
# ---------------------------------------------------------------------------


def test_warm_agent_reused_across_dispatches(tmp_path: Path) -> None:
    """A warm AcpBackend reuses its ONE subprocess across dispatches (D010 reuse —
    not relaunch-per-dispatch), and two backends (the per-tier map) are DISTINCT
    subprocesses. The stub creates nothing, so commit_all is a no-op; we assert on
    process identity, which is what the warm-pool default guarantees."""
    stub = tmp_path / "stub_agent.py"
    stub.write_text(_STUB)  # loops; survives repeated dispatches
    worktree = tmp_path / "wt"
    worktree.mkdir()
    gitutil.init_repo(worktree)
    unit = WorkUnit(task_id="warm", goal="noop")

    high = AcpBackend(command=[sys.executable, str(stub)], name="acp")
    try:
        high.dispatch(unit, Tier.HIGH, Budget(), worktree, {})
        pid1 = high._proc.pid  # type: ignore[union-attr]
        high.dispatch(unit, Tier.HIGH, Budget(), worktree, {})
        pid2 = high._proc.pid  # type: ignore[union-attr]
        # Same live subprocess across both dispatches — warm reuse, not relaunch.
        assert pid1 == pid2 and high._proc is not None

        # The per-tier warm map keeps a SEPARATE subprocess per tier.
        med = AcpBackend(command=[sys.executable, str(stub)], name="acp")
        try:
            med.dispatch(unit, Tier.MED, Budget(), worktree, {})
            assert med._proc is not None and med._proc.pid != pid1
        finally:
            med.kill()
    finally:
        high.kill()


# ---------------------------------------------------------------------------
# 4. Multi-member within-tier ordering guard (TIER7B-FOLLOWUP item 1).
#    TIER7B delegates within-tier free-first/cost_rank ordering to the gateway;
#    prior tier-lifecycle tests only used SINGLE-member tier pools. This pins a
#    2-member pool through the per-tier warm-map path: the cheaper/free member
#    must be the one served. Regress the ordering → the upstream gets 'paid-wire'.
# ---------------------------------------------------------------------------


def test_within_tier_two_member_pool_selects_free_member(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    charon_home = tmp_path / "charon_home"
    charon_home.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("CHARON_HOME", str(charon_home))

    upstream, upstream_base = _up()
    stub = tmp_path / "stub_agent.py"
    stub.write_text(_STUB)
    try:
        _write_single_tier_two_member_registry(state_dir, charon_home, upstream_base)
        # One dispatch (max_checkpoints=1, accept=['false']) through the per-tier
        # warm-map path: agent requests the 'high' vid; the gateway resolves the
        # 2-member 'high' pool and serves its FIRST live entry (free-first).
        result = api.run_task(
            goal="within-tier ordering guard",
            accept=["false"],
            role="high",
            acp_cmd=_acp_cmd(stub),
            state_dir=str(state_dir),
            autonomy="L0",
            max_checkpoints=1,
        )
    finally:
        upstream.shutdown()

    assert result.get("status") != "exhausted", result
    # The cheaper/free member won within the tier — NOT the paid one, even though
    # tiers.json lists m-paid first. A within-tier ordering regression flips this.
    assert upstream.received == ["free-wire"], (
        f"within-tier ordering regressed: upstream got {upstream.received!r}, "
        f"expected ['free-wire'] (free-first/cost_rank must pick the cheaper member)"
    )


# ---------------------------------------------------------------------------
# 5. Proxy-teardown-on-setup-error hardening (TIER7B-FOLLOWUP item 2).
#    A failure in the warm-map build runs AFTER the per-run proxy starts but
#    BEFORE the run's inner try/finally. The proxy thread must still be torn
#    down — no leaked gateway thread on a setup failure.
# ---------------------------------------------------------------------------


def test_proxy_torn_down_when_warm_map_build_fails(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    charon_home = tmp_path / "charon_home"
    charon_home.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("CHARON_HOME", str(charon_home))

    upstream, upstream_base = _up()
    stub = tmp_path / "stub_agent.py"
    stub.write_text(_STUB)

    # Capture the serve thread of every per-run proxy started during the run.
    started: list = []
    real_serve = proxy_server_mod.GatewayProxyServer.serve_in_thread

    def _spy_serve(self):  # type: ignore[no-untyped-def]
        t = real_serve(self)
        started.append((self, t))
        return t

    monkeypatch.setattr(
        proxy_server_mod.GatewayProxyServer, "serve_in_thread", _spy_serve)

    # Inject a failure into the warm-map build (api._acp_via_renderer), which runs
    # after proxy-start but before the run's inner try/finally.
    def _boom(*a: object, **k: object) -> None:
        raise RuntimeError("warm-map build boom")

    monkeypatch.setattr(api, "_acp_via_renderer", _boom)

    try:
        _write_two_tier_registry(state_dir, charon_home, upstream_base)
        with pytest.raises(RuntimeError, match="warm-map build boom"):
            api.run_task(
                goal="proxy teardown guard",
                accept=["false"],
                role="high",
                acp_cmd=_acp_cmd(stub),
                state_dir=str(state_dir),
                autonomy="L0",
            )
    finally:
        upstream.shutdown()

    assert started, "expected the per-run gateway proxy to have been started"
    server, thread = started[0]
    thread.join(timeout=5)
    assert not thread.is_alive(), (
        "per-run proxy thread leaked: it was not shut down when the warm-map "
        "build failed during setup"
    )


def test_proxy_torn_down_when_router_setup_fails(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """TIER7B-FOLLOWUP nit: the residual leak window AFTER the warm-map build but
    BEFORE the run's inner try/finally — the router/fence/budget/autonomy build. A
    bad autonomy string KeyErrors at ``Autonomy[autonomy]`` once the proxy thread is
    already running; assert the per-run proxy is still reaped (no orphaned thread)."""
    charon_home = tmp_path / "charon_home"
    charon_home.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("CHARON_HOME", str(charon_home))

    upstream, upstream_base = _up()
    stub = tmp_path / "stub_agent.py"
    stub.write_text(_STUB)

    # Capture the serve thread of every per-run proxy started during the run.
    started: list = []
    real_serve = proxy_server_mod.GatewayProxyServer.serve_in_thread

    def _spy_serve(self):  # type: ignore[no-untyped-def]
        t = real_serve(self)
        started.append((self, t))
        return t

    monkeypatch.setattr(
        proxy_server_mod.GatewayProxyServer, "serve_in_thread", _spy_serve)

    # Let the warm-map build succeed cheaply (no real agent subprocess) so the run
    # REACHES the new window — the router/fence/budget/autonomy construction that sits
    # after proxy-start but before the run's inner try/finally.
    class _FakeBackend:
        name = "fake"

        def kill(self) -> None:
            pass

    monkeypatch.setattr(api, "_acp_via_renderer", lambda *a, **k: _FakeBackend())

    try:
        _write_two_tier_registry(state_dir, charon_home, upstream_base)
        # Invalid autonomy KeyErrors at Autonomy[autonomy], inside the new window.
        with pytest.raises(KeyError):
            api.run_task(
                goal="proxy teardown guard (router window)",
                accept=["false"],
                role="high",
                acp_cmd=_acp_cmd(stub),
                state_dir=str(state_dir),
                autonomy="NOT_A_REAL_AUTONOMY",
            )
    finally:
        upstream.shutdown()

    assert started, "expected the per-run gateway proxy to have been started"
    server, thread = started[0]
    thread.join(timeout=5)
    assert not thread.is_alive(), (
        "per-run proxy thread leaked: it was not shut down when the "
        "router/fence/budget/autonomy construction failed during setup"
    )
