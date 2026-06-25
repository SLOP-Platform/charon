"""Charon's public Python API (ADR-0002 §2.4, surface #2).

This module + the CLI + the HTTP service are the ONLY stable surfaces. Everything
else under ``charon.*`` is private and may change without a major bump.
"""
from __future__ import annotations

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

    run_backends = _resolve_backends(backend, backends, backend_name, checks, acp_cmd)
    router = StaticRouter(backends=list(run_backends))
    fence = Fence(autonomy=Autonomy[autonomy])

    budget = Budget(max_checkpoints=max_checkpoints,
                    max_cost_usd=max_cost_usd, max_tokens=max_tokens)
    result: RunResult = _run(
        WorkUnit(task_id=task_id, goal=goal),
        run_backends, ledger, fence, router,
        reviewer=reviewer,
        max_checkpoints=max_checkpoints, budget=budget,
    )
    out = asdict(result)
    out["task_id"] = task_id
    out["target_repo"] = target
    out["state_dir"] = str(sdir)
    return out


# Provider/agent env the live ACP backend needs (its real config + a provider
# key) — merged back over the fence's scrubbed env inside the container/VM.
_ACP_PASSTHROUGH = ("HOME", "PATH", "OPENCODE_API_KEY", "OPENROUTER_API_KEY",
                    "ANTHROPIC_API_KEY", "XDG_CONFIG_HOME", "XDG_DATA_HOME")


def _acp_passthrough_env() -> dict[str, str]:
    return {k: os.environ[k] for k in _ACP_PASSTHROUGH if k in os.environ}


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
