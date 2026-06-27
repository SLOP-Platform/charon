"""Charon's public Python API (ADR-0002 §2.4, surface #2).

This module + the CLI + the HTTP service are the ONLY stable surfaces. Everything
else under ``charon.*`` is private and may change without a major bump.
"""
from __future__ import annotations

import json
import os
import shlex
import threading
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from . import gitutil
from .acceptance import AcceptanceCheck
from .adapters.acp import AcpBackend
from .adapters.mock import MockBackend
from .coordinator import CostGate, RunResult
from .coordinator import run as _run
from .fence import Fence
from .ledger import Ledger
from .ports.agent_launch import _acp_passthrough_env, render
from .ports.backend import AgentBackend
from .ports.reviewer import Reviewer
from .router import StaticRouter
from .types import Autonomy, Budget, WorkUnit

DEFAULT_STATE_DIR = ".charon"


def make_task_id(goal: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in goal.lower())[:24].strip("-")
    return f"{slug or 'task'}-{uuid.uuid4().hex[:8]}"


# Serialize concurrent `git worktree add` against one base repo: under
# `run_parallel` N units prepare worktrees off the same `--repo` in N threads,
# and git's worktree bookkeeping (`.git/worktrees`) is not concurrency-safe.
_WORKTREE_LOCK = threading.Lock()


@dataclass
class _PreparedRepo:
    """What ``_prepare_repo`` hands back: the per-unit worktree to operate in
    plus its teardown. ``base_repo`` is the real ``--repo`` a linked worktree was
    cut from (ADR-0007 D2); it is ``None`` for the demo sandbox, which is left in
    place for inspection rather than torn down."""

    target: str
    base_repo: str | None = None

    def cleanup(self) -> None:
        """Remove a real-repo per-unit worktree on teardown (no-op for the
        sandbox). The committed objects survive in the base repo's object store;
        only the isolated working tree is reclaimed."""
        if self.base_repo is not None:
            gitutil.remove_worktree(Path(self.base_repo), Path(self.target))


def _prepare_repo(repo: str | None, state_dir: Path, task_id: str) -> _PreparedRepo:
    """Return the per-unit worktree to operate in, plus its teardown.

    D2/CONC-1 (ADR-0007): EVERY unit gets its OWN working tree nested one level
    down (``…/<task_id>/repo``) so the coordinator's ``guard_dir =
    worktree.parent`` resolves to ``…/<task_id>/`` — a directory UNIQUE to this
    unit. Sibling units in the same ``state_dir`` then never share a guard parent,
    so one unit's escape scan can never see another's legitimate writes (the
    parallel-units isolation invariant).

    - A real ``--repo`` gets a ``git worktree add`` off its current HEAD at
      ``work/<task_id>/repo`` (it was previously used AS-IS, so N units shared one
      tree + ``guard_dir``, silently defeating CONC-1 — the gap D2 closes). Charon
      refuses to reuse an existing per-unit worktree dir, so two units can never
      share one real working tree.
    - Otherwise a fresh sandbox repo is created at ``sandbox/<task_id>/repo`` (the
      demo path), left in place on teardown."""
    if repo:
        base = Path(repo).resolve()
        if not gitutil.is_repo(base):
            raise ValueError(f"--repo {base} is not a git repository")
        work = (state_dir / "work" / task_id / "repo").resolve()
        # Refuse >1 unit sharing one real working tree: an existing per-unit dir
        # means a task_id collision / leftover — isolate or fail, never share.
        if work.exists():
            raise ValueError(
                f"per-unit worktree {work} already exists; refusing to share a "
                "real working tree across units"
            )
        with _WORKTREE_LOCK:
            gitutil.add_worktree(base, work, gitutil.head(base))
        return _PreparedRepo(target=str(work), base_repo=str(base))
    sandbox = (state_dir / "sandbox" / task_id / "repo").resolve()
    sandbox.mkdir(parents=True, exist_ok=True)
    gitutil.init_repo(sandbox)
    return _PreparedRepo(target=str(sandbox))


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
    cost_gate: CostGate | None = None,
    decompose: bool = False,
) -> dict:
    """Create a Work Ledger and drive the goal to acceptance or a bounded stop.

    Backend selection (first non-None wins): an explicit ``backends`` mapping
    (multi-backend, the cross-vendor path) · a single ``backend`` · else
    ``backend_name`` parsed as a comma-separated list, each name becoming a
    satisfying mock vendor (the Tier-1/2 demo path; real ACP needs a live agent —
    see ``charon doctor``).

    ``cost_gate`` (PERF-4) is the shared, race-free aggregate budget when this run
    is one of N dispatched by ``parallel.run_parallel``; ``None`` for a solo run.
    ``decompose`` (PERF-4/D5) drives the goal through the sequential role-DAG
    (Triage→…→Close) instead of the plain single-unit loop — one ledger either way.

    Returns a JSON-serializable dict (the RunResult plus task id + lkg)."""
    if not accept:
        raise ValueError("at least one --accept executable check is required")
    sdir = Path(state_dir).resolve()
    task_id = make_task_id(goal)
    prepared = _prepare_repo(repo, sdir, task_id)
    target = prepared.target
    base_ref = gitutil.head(Path(target))

    checks = [AcceptanceCheck(id=f"a{i}", cmd=c) for i, c in enumerate(accept)]
    ledger = Ledger.create(sdir, task_id, goal, checks, target, base_ref)

    proxy_server = None
    failover_note = ""
    tier_vid = ""
    acp_names = [n.strip() for n in backend_name.split(",")]
    # Outer guard: whatever happens during setup or the run, the per-unit
    # worktree is torn down on teardown (D2 — no leaked working trees).
    try:
        if role is not None and backend is None and backends is None:
            # Tier routing (ADR-0014 D1/D2): resolve a TIER VID and build the
            # per-run gateway with a tier-vid pool, then let the gateway's own
            # vid→pool→provider failover do the selection. The engine does NO
            # provider selection of its own — it consumes the live gateway path.
            if not acp_cmd:
                raise ValueError("--role needs --acp-cmd")
            from . import config as _config
            from . import gateway as _gateway
            from .proxy import GatewayProxy
            from .proxy_server import GatewayProxyServer
            try:
                tier_vid = _config.resolve_tier(role)
            except ValueError as exc:
                raise ValueError(f"unknown tier/role {role!r}: {exc}") from exc
            # ONE ordering authority (D2): load_config compiles the registry +
            # tiers via gateway._build_routes_and_pools (free-first→cost_rank),
            # exactly as the live gateway does — never api._pool_routes.
            gw_cfg = _gateway.load_config(state_dir=sdir)
            chain = gw_cfg.pools.get(tier_vid, [])
            proxy_server = GatewayProxyServer(
                pools={tier_vid: chain}, model_ids=[tier_vid], observer=GatewayProxy())
            proxy_server.serve_in_thread()
            if not chain:
                # Dry pool — re-home the retired select_live_entry early-return
                # (ADR-0014 B4): the same {status:"exhausted", note:…} shape.
                proxy_server.shutdown()
                return {"status": "exhausted", "task_id": task_id, "checkpoints": 0,
                        "verified": [], "remaining": sorted(ledger.remaining()),
                        "note": f"tier {tier_vid!r} dry; no providers configured for this tier",
                        "target_repo": target, "state_dir": str(sdir)}
            # The agent requests the tier vid; the gateway resolves + fails over.
            run_backends: dict = {"acp": _acp_via_renderer(acp_cmd, proxy_server, tier_vid)}
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
            work_unit = WorkUnit(task_id=task_id, goal=goal)
            if decompose:
                from .decompose import run_decomposed
                result: RunResult = run_decomposed(
                    work_unit, run_backends, ledger, fence, router,
                    reviewer=reviewer, cost_gate=cost_gate,
                )
            else:
                result = _run(
                    work_unit, run_backends, ledger, fence, router,
                    reviewer=reviewer,
                    max_checkpoints=max_checkpoints, budget=budget,
                    cost_gate=cost_gate,
                )
            # Re-home the retired select_live_entry ``failover`` contract from the
            # gateway's own observability (ADR-0014 B4): served provider +
            # skipped-provider list, read BEFORE the proxy is torn down below.
            if proxy_server is not None and tier_vid:
                failover_note = _tier_failover_note(
                    proxy_server.status_snapshot(), tier_vid)
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
    finally:
        prepared.cleanup()


def _acp_via_renderer(acp_cmd: str, server, requested_model: str) -> AcpBackend:
    """Build an ACP backend whose agent routes ``requested_model`` (a tier vid)
    through the running per-run proxy ``server`` — via the product-neutral
    ``AgentLaunch`` seam (ADR-0014 D3). The engine never names the agent product;
    the renderer forces ``include_keys=False`` (D4), so the agent never sees the
    real provider key (the proxy injects it)."""
    launch = render(acp_cmd, server.url, requested_model)
    return AcpBackend(launch.argv, name="acp",
                      passthrough_env=launch.passthrough_env, observer=server.observer)


def _tier_failover_note(snapshot: dict, tier_vid: str) -> str:
    """Re-home the retired ``select_live_entry`` ``failover`` contract (ADR-0014
    B4) from the gateway's OWN observability: the served provider plus the
    skipped (failed-over) provider list, translated from
    ``GatewayProxyServer.status_snapshot()``. Empty string when nothing was
    served and nothing was skipped (no note to attach)."""
    providers = snapshot.get("providers") or {}
    served = next((label for label, s in providers.items() if s.get("served")), None)
    events = snapshot.get("recent_failovers") or []
    skipped = sorted({f.get("provider") for ev in events
                      for f in ev.get("failovers", []) if f.get("provider")})
    if not served and not skipped:
        return ""
    note = f"tier {tier_vid!r}"
    if served:
        note += f" → {served}"
    if skipped:
        note += f"; skipped {skipped}"
    return note


def _start_proxy_acp(acp_cmd: str, upstream: str, key: str, model: str):
    """Start the observing proxy in front of a single ``upstream`` and build an
    ACP backend whose agent routes all model calls through it (the ``--proxy``
    interim path). The opencode launch shape lives behind the ``AgentLaunch``
    seam now (ADR-0014 D3); this only stands up the single-upstream proxy and
    renders the launch. The proxy holds the real key (review #3 / D4).
    Returns (backend, server); the caller owns shutdown."""
    from .proxy import GatewayProxy
    from .proxy_server import GatewayProxyServer

    observer = GatewayProxy()
    server = GatewayProxyServer(upstream_base=upstream, api_key=key, observer=observer)
    server.serve_in_thread()
    backend = _acp_via_renderer(acp_cmd, server, model)
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


def list_ledgers(state_dir: str = DEFAULT_STATE_DIR) -> list[dict]:
    """Read-only summary of every task ledger under ``state_dir`` — the data
    behind the web dashboard's project/run list. Each entry derives status the
    same way the loop does (``complete`` ⇔ no acceptance checks remain), plus the
    Ledger-native cost truth and the cross-vendor handoff chain. Skips any
    directory that is not a readable ledger (e.g. the ``sandbox`` worktree dir)
    so a malformed neighbour never breaks the listing."""
    sdir = Path(state_dir).resolve()
    out: list[dict] = []
    if not sdir.is_dir():
        return out
    for child in sorted(sdir.iterdir()):
        if not child.is_dir() or not (child / "ledger.json").is_file():
            continue
        try:
            led = Ledger.load(sdir, child.name)
        except Exception:
            continue  # not a valid ledger (bad id / corrupt) — omit, don't crash
        remaining = sorted(led.remaining())
        usage = led.cumulative_usage()
        out.append({
            "task_id": led.task_id,
            "goal": led.goal,
            "status": "complete" if not remaining else "incomplete",
            "checkpoints": len(led.checkpoints()),
            "verified": sorted(led.verified()),
            "remaining": remaining,
            "lkg_ref": led.lkg_ref,
            "usage": usage.to_dict(),
            "providers": list(led.provider_history),
        })
    return out


# The models.json schema fields (pools.py). show_config projects each entry onto
# this allowlist so the no-creds-in-config invariant is STRUCTURAL: even if an
# operator fat-fingers an inline secret into models.json, it can never reach the
# read-only web surface (provider keys live in env/proxy, referenced by key_env).
_MODEL_FIELDS = ("agent", "cost_tier", "cost_rank", "code_safe", "free",
                 "upstream_base", "key_env", "upstream_model")


def show_config(state_dir: str = DEFAULT_STATE_DIR) -> dict:
    """Read-only view of the routing policy (``models.json`` registry +
    ``pools.json`` role→pool order) for the dashboard's config pane. These files
    are key-*env* references by design (the proxy/control plane holds the actual
    provider keys — INV: no creds in config); models are field-allowlisted so no
    stray value can leak even on misconfiguration."""
    sdir = Path(state_dir).resolve()

    def _read(name: str) -> dict | None:
        p = sdir / name
        if not p.is_file():
            return None
        try:
            parsed = json.loads(p.read_text())  # UnicodeDecodeError ⊂ ValueError
        except (OSError, ValueError) as exc:
            return {"error": f"{name} is not readable JSON: {exc}"}
        return parsed if isinstance(parsed, dict) else {"error": f"{name} is not an object"}

    models = _read("models.json")
    if isinstance(models, dict) and "error" not in models:
        models = {
            mid: {k: spec[k] for k in _MODEL_FIELDS if k in spec}
            for mid, spec in models.items() if isinstance(spec, dict)
        }
    return {"state_dir": str(sdir), "models": models, "pools": _read("pools.json")}
