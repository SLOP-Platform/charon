"""Close the tier-routing reviewer gap: no test verified that api.run_task(role=…)
routes through the full glue chain at the wire.

The gap: the suite can stay green while the tier vid is absent from the
gateway pools, the dry-pool early-return fires, and tests exercising
components in isolation (renderer, gateway) still pass.

This file pins BOTH the happy path AND the exact regression mode the
reviewers named: tiers.json/models.json mismatch (vid not a pool key)
→ dry-pool early-return → {status:"exhausted"}.

Glue verified end-to-end:
  config.resolve_tier(role) → gateway.load_config(state_dir).pools[tier_vid]
  → per-run GatewayProxyServer → AcpBackend(OpencodeRenderer) → mock upstream

The mock-upstream capture pattern is from test_gateway_failover.py:19-31.
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

from charon import api

# ---------------------------------------------------------------------------
# Mock upstream — captures wire model ids (test_gateway_failover.py:19-31)
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
            "model": srv.return_model,  # type: ignore[attr-defined]
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


def _up(return_model: str = "m") -> tuple[_Threaded, str]:
    """Start a mock upstream; return (server, base_url)."""
    srv = _Threaded(("127.0.0.1", 0), _Prog)
    srv.return_model = return_model
    srv.received = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]}:{srv.server_address[1]}"  # type: ignore[str-bytes-safe]


# ---------------------------------------------------------------------------
# Stub ACP agent (written to a temp file at test time).
# Speaks ACP JSON-RPC and fires one POST to the per-run gateway proxy.
# The proxy URL and wire model id are extracted from OPENCODE_CONFIG_CONTENT,
# which OpencodeRenderer injects when rendering the AgentLaunch (ADR-0014 D3).
# The wire model is the short key (the tier vid itself), not "provider/vid".
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
        # baseURL is proxy_url + "/v1"; models dict key is the short tier vid.
        opts = cfg["provider"][prov]["options"]
        model = next(iter(cfg["provider"][prov]["models"]))
        base = opts["baseURL"].rstrip("/")
        body = json.dumps({"model": model}).encode()
        req = urllib.request.Request(
            base + "/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
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
        if method == "initialize":
            res: dict = {}
        elif method == "session/new":
            res = {"sessionId": "s1"}
        elif method == "session/prompt":
            _proxy_post()
            res = {}
        else:
            res = {}
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": res}) + "\\n")
        sys.stdout.flush()
""")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_registry(state_dir: Path, upstream_base: str, upstream_model: str) -> None:
    """Write models.json: one model in the 'high' tier pointed at the mock upstream."""
    (state_dir / "models.json").write_text(json.dumps({
        "test-high": {
            "upstream_base": upstream_base,
            "upstream_model": upstream_model,
            "free": True,
            "cost_rank": 0,
        }
    }))


def _write_tiers(charon_home: Path, high_members: list) -> None:
    """Write tiers.json in CHARON_HOME with 'high' tier → high_members."""
    (charon_home / "tiers.json").write_text(json.dumps({
        "order": ["low", "med", "high"],
        "members": {"low": [], "med": [], "high": high_members},
        "aliases": {},
    }))


def _acp_cmd(stub: Path) -> str:
    """Build an acp_cmd string safe for shlex.split (quoted stub path)."""
    return f"{sys.executable} {shlex.quote(str(stub))}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_run_task_role_routes_to_upstream_at_the_wire(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Happy path: the full glue chain fires and the upstream receives the right model.

    Registry: models.json has 'test-high' → mock upstream (upstream_model='wire-model').
    Tiers:    tiers.json has 'high' → ['test-high'].

    After run_task(role='high', ...):
    - result.status must NOT be 'exhausted' (pool was non-empty, proxy served).
    - upstream.received must be ['wire-model'] — proving resolve_tier →
      load_config → pool → GatewayProxyServer → OpencodeRenderer → stub POST all
      connected, and the gateway's upstream_model rewrite reached the wire.
    """
    charon_home = tmp_path / "charon_home"
    charon_home.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("CHARON_HOME", str(charon_home))

    upstream, upstream_base = _up(return_model="wire-model")
    stub = tmp_path / "stub_agent.py"
    stub.write_text(_STUB)
    try:
        _write_registry(state_dir, upstream_base, "wire-model")
        _write_tiers(charon_home, ["test-high"])

        result = api.run_task(
            goal="route-check",
            accept=["false"],  # starts failing → coordinator dispatches rather than short-circuit
            role="high",
            acp_cmd=_acp_cmd(stub),
            state_dir=str(state_dir),
            autonomy="L0",
            max_checkpoints=1,
        )
    finally:
        upstream.shutdown()

    # The dry-pool early-return (B4) must NOT have fired — routing happened.
    assert result.get("status") != "exhausted", (
        f"got {result.get('status')!r}; expected routing but got dry-pool return: {result}"
    )
    # The mock upstream captured the upstream_model — proves the whole glue chain:
    # resolve_tier('high') → 'high' vid → load_config pool → proxy → upstream rewrite.
    assert upstream.received == ["wire-model"], (
        f"upstream received {upstream.received!r}; expected ['wire-model']; "
        "the resolve_tier→load_config→pool→proxy glue may have regressed"
    )


def test_run_task_role_mismatch_surfaces_exhausted(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Regression: tiers.json/models.json mismatch → empty pool → status:exhausted.

    Tiers:    tiers.json says 'high' → ['ghost-model'].
    Registry: models.json has 'real-model' only (no 'ghost-model').

    'ghost-model' is not a key in the compiled routes, so _build_routes_and_pools
    produces an empty chain for the 'high' vid.  The dry-pool early-return in
    api.run_task must surface {status:'exhausted'} and must NOT hit the upstream —
    pinning the exact failure mode tier-routing reviewers flagged ('suite stays green
    while nothing routes').
    """
    charon_home = tmp_path / "charon_home"
    charon_home.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("CHARON_HOME", str(charon_home))

    upstream, upstream_base = _up()
    stub = tmp_path / "stub_agent.py"
    stub.write_text(_STUB)
    try:
        # 'real-model' is in the registry but 'ghost-model' (the tier member) is not.
        (state_dir / "models.json").write_text(json.dumps({
            "real-model": {
                "upstream_base": upstream_base,
                "free": True,
                "cost_rank": 0,
            }
        }))
        _write_tiers(charon_home, ["ghost-model"])  # vid not a pool key → empty chain

        result = api.run_task(
            goal="mismatch-check",
            accept=["true"],
            role="high",
            acp_cmd=_acp_cmd(stub),
            state_dir=str(state_dir),
            autonomy="L0",
        )
    finally:
        upstream.shutdown()

    assert result["status"] == "exhausted", (
        f"expected 'exhausted' for empty tier pool, got {result.get('status')!r}: {result}"
    )
    # No routing happened — the upstream must be untouched.
    assert upstream.received == [], (
        f"upstream was hit despite empty pool: {upstream.received!r}"
    )
