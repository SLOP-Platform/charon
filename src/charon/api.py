"""Charon's public Python API (ADR-0002 §2.4, surface #2).

This module + the CLI + the HTTP service are the ONLY stable surfaces. Everything
else under ``charon.*`` is private and may change without a major bump.
"""
from __future__ import annotations

import json
import os
import shlex
import uuid
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path

from . import gitutil
from .acceptance import AcceptanceCheck
from .adapters.acp import AcpBackend
from .adapters.mock import MockBackend
from .coordinator import RunResult
from .coordinator import run as _run
from .fence import Fence
from .ledger import Ledger
from .ports.backend import AgentBackend
from .ports.reviewer import Reviewer
from .router import StaticRouter
from .types import Autonomy, Budget, WorkUnit

DEFAULT_STATE_DIR = ".charon"


def make_task_id(goal: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in goal.lower())[:24].strip("-")
    return f"{slug or 'task'}-{uuid.uuid4().hex[:8]}"


def _prepare_repo(repo: str | None, state_dir: Path, task_id: str) -> str:
    """Return a git worktree to operate in. If ``repo`` is given it must be a
    git repo; otherwise a fresh sandbox repo is created (demo path)."""
    if repo:
        p = Path(repo).resolve()
        if not gitutil.is_repo(p):
            raise ValueError(f"--repo {p} is not a git repository")
        return str(p)
    sandbox = (state_dir / "sandbox" / task_id).resolve()
    sandbox.mkdir(parents=True, exist_ok=True)
    gitutil.init_repo(sandbox)
    return str(sandbox)


def run_task(
    goal: str,
    accept: list[str],
    *,
    repo: str | None = None,
    state_dir: str = DEFAULT_STATE_DIR,
    backend: AgentBackend | None = None,
    backends: Mapping[str, AgentBackend] | None = None,
    backend_name: str = "mock",
    acp_cmd: str | None = None,
    proxy_upstream: str | None = None,
    proxy_key_env: str | None = None,
    acp_model: str | None = None,
    role: str | None = None,
    reviewer: Reviewer | None = None,
    autonomy: str = "L0",
    max_checkpoints: int = 8,
    max_cost_usd: float | None = None,
    max_tokens: int | None = None,
) -> dict:
    """Create a Work Ledger and drive the goal to acceptance or a bounded stop.

    Backend selection (first non-None wins): an explicit ``backends`` mapping
    (multi-backend, the cross-vendor path) · a single ``backend`` · else
    ``backend_name`` parsed as a comma-separated list, each name becoming a
    satisfying mock vendor (the Tier-1/2 demo path; real ACP needs a live agent —
    see ``charon doctor``).

    Returns a JSON-serializable dict (the RunResult plus task id + lkg)."""
    if not accept:
        raise ValueError("at least one --accept executable check is required")
    sdir = Path(state_dir).resolve()
    task_id = make_task_id(goal)
    target = _prepare_repo(repo, sdir, task_id)
    base_ref = gitutil.head(Path(target))

    checks = [AcceptanceCheck(id=f"a{i}", cmd=c) for i, c in enumerate(accept)]
    ledger = Ledger.create(sdir, task_id, goal, checks, target, base_ref)

    proxy_server = None
    failover_note = ""
    acp_names = [n.strip() for n in backend_name.split(",")]
    if role is not None and backend is None and backends is None:
        # Pool mode: cost-first failover across the role's pool, live.
        if not acp_cmd:
            raise ValueError("--role needs --acp-cmd")
        from .failover import select_live_entry
        from .proxy import GatewayProxy
        from .proxy_server import GatewayProxyServer
        prouter = StaticRouter.from_charon_dir(sdir)
        pool = prouter.pools.get(role)
        if not pool:
            raise ValueError(f"no pool for role {role!r} in {sdir}/pools.json")
        proxy_server = GatewayProxyServer(routes=_pool_routes(pool), observer=GatewayProxy())
        proxy_server.serve_in_thread()
        chosen = select_live_entry(prouter, role, proxy_server.observer,
                                   _http_probe(proxy_server))
        if chosen is None:
            proxy_server.shutdown()
            skipped = sorted(proxy_server.observer.exhausted_models())
            return {"status": "exhausted", "task_id": task_id, "checkpoints": 0,
                    "verified": [], "remaining": sorted(ledger.remaining()),
                    "note": f"pool for {role!r} dry; all probed models unavailable: {skipped}",
                    "target_repo": target, "state_dir": str(sdir)}
        failover_note = (f"role {role!r} → {chosen.model} ({chosen.cost_tier})"
                         + (f"; skipped {sorted(proxy_server.observer.exhausted_models())}"
                            if proxy_server.observer.exhausted_models() else ""))
        run_backends: dict = {"acp": _acp_for_proxy(acp_cmd, proxy_server, chosen.model)}
    elif proxy_upstream and backend is None and backends is None and "acp" in acp_names:
        if not acp_cmd:
            raise ValueError("--proxy with an acp backend needs --acp-cmd")
        key = os.environ.get(proxy_key_env or "", "")
        if not key:
            raise ValueError(f"proxy key env {proxy_key_env!r} is not set")
        acp_backend, proxy_server = _start_proxy_acp(
            acp_cmd, proxy_upstream, key, acp_model or "default")
        run_backends = {"acp": acp_backend}
    else:
        run_backends = _resolve_backends(backend, backends, backend_name, checks, acp_cmd)

    router = StaticRouter(backends=list(run_backends))
    fence = Fence(autonomy=Autonomy[autonomy])
    budget = Budget(max_checkpoints=max_checkpoints,
                    max_cost_usd=max_cost_usd, max_tokens=max_tokens)
    try:
        result: RunResult = _run(
            WorkUnit(task_id=task_id, goal=goal),
            run_backends, ledger, fence, router,
            reviewer=reviewer,
            max_checkpoints=max_checkpoints, budget=budget,
        )
    finally:
        # Always reap the agent subprocess(es) and the proxy (review #8 — no
        # orphaned opencode processes left holding file handles).
        for b in run_backends.values():
            try:
                b.kill()
            except Exception:
                pass
        if proxy_server is not None:
            proxy_server.shutdown()
    out = asdict(result)
    out["task_id"] = task_id
    out["target_repo"] = target
    out["state_dir"] = str(sdir)
    if proxy_upstream:
        out["proxy"] = {"upstream": proxy_upstream, "model": acp_model}
    if failover_note:
        out["failover"] = failover_note
    return out


# Env the live ACP agent needs to find its own config — merged back over the
# fence's scrubbed env (only honest inside the Mode-B container/VM, the real
# boundary). Provider KEYS are separate: with the proxy in front (R1) the agent
# must NOT get the real key (review #3) — the proxy injects it. Only the
# no-proxy path passes keys, as a documented interim.
_ACP_BASE_PASSTHROUGH = ("HOME", "PATH", "XDG_CONFIG_HOME", "XDG_DATA_HOME")
_ACP_KEY_PASSTHROUGH = ("OPENCODE_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY")


def _acp_passthrough_env(include_keys: bool = True) -> dict[str, str]:
    names = _ACP_BASE_PASSTHROUGH + (_ACP_KEY_PASSTHROUGH if include_keys else ())
    return {k: os.environ[k] for k in names if k in os.environ}


def _split_model(pool_model: str) -> tuple[str, str]:
    """A pool id ``<provider>/<model>`` → (opencode provider, the model id the
    agent sends, which the upstream natively understands). Using the REAL provider
    name (opencode-go/openrouter/…) matters: opencode's ACP mode hangs on an
    unrecognized provider. A bare id (no '/') falls back to a generic provider."""
    if "/" in pool_model:
        provider, short = pool_model.split("/", 1)
        return provider, short
    return "charon", pool_model


def _acp_for_proxy(acp_cmd: str, server, pool_model: str) -> AcpBackend:
    """Build an ACP backend whose agent routes ``pool_model`` through a running
    proxy ``server``. The agent is configured under the model's real provider and
    sends the native model id; the proxy forwards it to the right upstream."""
    provider, short = _split_model(pool_model)
    cfg = {
        "model": f"{provider}/{short}",
        "provider": {
            provider: {
                "npm": "@ai-sdk/openai-compatible",
                "name": provider,
                "options": {"baseURL": server.url + "/v1", "apiKey": "charon-proxy"},
                "models": {short: {}},
            }
        },
    }
    env = {**_acp_passthrough_env(include_keys=False),
           "OPENCODE_CONFIG_CONTENT": json.dumps(cfg)}
    return AcpBackend(shlex.split(acp_cmd), name="acp",
                      passthrough_env=env, observer=server.observer)


def _pool_routes(entries) -> dict:
    """Build the proxy's routing table from a role's pool — keyed by the model id
    the agent sends (the native id), observed back under the pool id."""
    from .proxy_server import UpstreamRoute
    routes: dict = {}
    for e in entries:
        if not e.upstream_base:
            continue
        _, short = _split_model(e.model)
        key = os.environ.get(e.key_env, "") if e.key_env else None
        routes[short] = UpstreamRoute(e.upstream_base, key, e.upstream_model, pool_id=e.model)
    return routes


def _http_probe(server):
    """A cheap pre-flight: send a 1-token completion for an entry through the proxy
    so the observer sees the live status (200/429/404) — the failover trigger."""
    import urllib.request

    def probe(entry) -> bool:
        _, short = _split_model(entry.model)
        payload = json.dumps({"model": short,
                              "messages": [{"role": "user", "content": "ping"}],
                              "max_tokens": 1}).encode()
        req = urllib.request.Request(server.url + "/v1/chat/completions", data=payload,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=25)
            resp.read()
            return resp.status == 200  # available ONLY on a positive 200
        except Exception:
            return False  # 429/404/timeout/error — unavailable (proxy logged status)
    return probe


def _start_proxy_acp(acp_cmd: str, upstream: str, key: str, model: str):
    """Start the observing proxy in front of ``upstream`` and build an ACP backend
    whose agent routes all model calls through it. Done by OVERRIDING the agent's
    provider ``baseURL`` to the proxy via inline ``OPENCODE_CONFIG_CONTENT`` (the
    mechanism proven live; a config *file* path is not honored, and streaming SSE
    must be relayed — both handled). The proxy holds the real key.
    ``model`` is ``provider/model`` (e.g. ``opencode-go/kimi-k2.7-code``).
    Returns (backend, server); the caller owns shutdown."""
    from .proxy import GatewayProxy
    from .proxy_server import GatewayProxyServer

    observer = GatewayProxy()
    server = GatewayProxyServer(upstream_base=upstream, api_key=key, observer=observer)
    server.serve_in_thread()

    provider, _, short = model.partition("/")
    if not short:  # bare model id → synthesize a provider
        provider, short, model = "charon-proxy", provider, f"charon-proxy/{provider}"
    cfg = {
        "model": model,
        "provider": {
            provider: {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Charon Proxy",
                "options": {"baseURL": server.url + "/v1", "apiKey": "charon-proxy"},
                "models": {short: {}},
            }
        },
    }
    # No real provider key in the agent env — the proxy holds it (review #3).
    env = {**_acp_passthrough_env(include_keys=False),
           "OPENCODE_CONFIG_CONTENT": json.dumps(cfg)}
    backend = AcpBackend(shlex.split(acp_cmd), name="acp",
                         passthrough_env=env, observer=observer)
    return backend, server


def _resolve_backends(
    backend: AgentBackend | None,
    backends: Mapping[str, AgentBackend] | None,
    backend_name: str,
    checks: list[AcceptanceCheck],
    acp_cmd: str | None = None,
) -> dict[str, AgentBackend]:
    if backends:
        return dict(backends)
    if backend is not None:
        return {backend.name: backend}
    names = [n.strip() for n in backend_name.split(",") if n.strip()]
    if not names:
        raise ValueError("no backend named")
    out: dict[str, AgentBackend] = {}
    for n in names:
        if n == "acp" or n.startswith("acp-"):
            if not acp_cmd:
                raise ValueError(f"backend {n!r} needs --acp-cmd (e.g. 'opencode acp')")
            out[n] = AcpBackend(shlex.split(acp_cmd), name=n,
                                passthrough_env=_acp_passthrough_env())
        else:
            out[n] = MockBackend.satisfying(checks, name=n)
    return out


def show_ledger(task_id: str, state_dir: str = DEFAULT_STATE_DIR) -> dict:
    ledger = Ledger.load(Path(state_dir).resolve(), task_id)
    return {
        "task_id": ledger.task_id,
        "goal": ledger.goal,
        "schema_version": ledger.schema_version,
        "lkg_ref": ledger.lkg_ref,
        "base_ref": ledger.base_ref,
        "provider_history": ledger.provider_history,
        "verified": sorted(ledger.verified()),
        "remaining": sorted(ledger.remaining()),
        "usage": ledger.cumulative_usage().to_dict(),  # derived cost truth (Tier 3)
        "checkpoints": [c.to_dict() for c in ledger.checkpoints()],
    }
