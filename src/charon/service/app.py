"""Mode B HTTP service (ADR-0002 §2.3, surface #3).

DESIGN OF RECORD (DTC, 2026-06-24 — see docs/REVIEW-LOG.md and PLAN-tier2.md §8):
the web process that SLOP reaches MUST NOT run the privileged coordinator loop
in-process. ADR-0002 §2.3 / INV-B4 require the agent-spawning loop to live in its
OWN process/container; the only real blast-radius boundary for a live
skip-permissions agent is that container, never an in-process Python guard.

Therefore this surface is **read-only** until the Tier-2b web/worker split lands
*with* its Tier-3 SLOP consumer: it serves liveness and derived ledger state, and
it explicitly **refuses** to execute runs (501) rather than running the privileged
loop in the exposed process. It imports no privileged-exec symbol (no
``coordinator``, no ``api.run_task``) — enforced structurally by
``tests/test_boundary.py``.
"""
from __future__ import annotations

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "the HTTP service needs the [service] extra: pip install 'charon[service]'"
    ) from exc

from .. import __version__, api

app = FastAPI(title="charon", version=__version__)

_RUN_NOT_IMPLEMENTED = (
    "live runs are not served by the exposed web process by design (ADR-0002 "
    "§2.3 / INV-B4): the privileged coordinator loop must run in its own "
    "no-network worker container, not in-process here. The web/worker split "
    "ships in Tier 2b together with the Tier-3 SLOP adapter. Use the CLI "
    "(`charon run`) or the Python API for runs today."
)


class RunRequest(BaseModel):
    # NOTE (DTC): the future enqueue-only surface drops `repo` from the wire
    # entirely so a caller can never direct a run at a host path; runs execute
    # only in an auto-created throwaway sandbox. Kept minimal here; the live
    # endpoint is not wired.
    goal: str
    accept: list[str]
    autonomy: str = "L0"
    budget: int = 8


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "version": __version__}


@app.post("/v1/runs", status_code=501)
def create_run(req: RunRequest) -> dict:
    # Refuse rather than run the privileged loop in the exposed process.
    raise HTTPException(status_code=501, detail=_RUN_NOT_IMPLEMENTED)


@app.get("/v1/runs/{task_id}")
def get_run(task_id: str) -> dict:
    # Read-only: derived ledger state. `task_id` is traversal-validated inside
    # the ledger boundary (ledger.validate_task_id); a bad id surfaces as a 404.
    try:
        return api.show_ledger(task_id)
    except Exception as exc:  # LedgerCorruption / invalid id / missing
        raise HTTPException(status_code=404, detail=str(exc)) from exc
