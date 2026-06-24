"""Mode B HTTP service (scaffold; live in Tier 2).

When SLOP embeds Charon (ADR-0002 Mode B), it talks to THIS surface — the
privileged agent-spawning loop stays isolated in Charon's own process/container,
behind SLOP's control-plane fence. Tier 1 ships the routes' shape only.
"""
from __future__ import annotations

try:
    from fastapi import FastAPI
    from pydantic import BaseModel
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "the HTTP service needs the [service] extra: pip install 'charon[service]'"
    ) from exc

from .. import __version__, api

app = FastAPI(title="charon", version=__version__)


class RunRequest(BaseModel):
    goal: str
    accept: list[str]
    repo: str | None = None
    autonomy: str = "L0"
    budget: int = 8


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "version": __version__}


@app.post("/v1/run")
def run(req: RunRequest) -> dict:  # pragma: no cover - Tier 2
    return api.run_task(
        goal=req.goal, accept=req.accept, repo=req.repo,
        autonomy=req.autonomy, max_checkpoints=req.budget,
    )


@app.get("/v1/ledger/{task_id}")
def ledger(task_id: str) -> dict:  # pragma: no cover - Tier 2
    return api.show_ledger(task_id)
