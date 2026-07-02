"""Read-only work/board observability: reads durable ``.charon`` run state (the
same data ``charon runs`` aggregates) and returns structured data for the gateway
web console's work panel.

Purely read-only; no mutation; no secrets rendered.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .ledger import Ledger

logger = logging.getLogger(__name__)


def _derive_status(
    root: Path,
    checkpoints: list,
    locked: bool,
    board_state: str | None,
) -> str:
    if board_state is not None:
        if board_state == "done":
            return "complete"
        if board_state == "blocked":
            return "blocked"
        if board_state == "ready":
            return "ready"
        if board_state == "claimed":
            return "in-progress"
    if locked:
        return "in-progress"
    if not checkpoints:
        return "in-progress"
    last = checkpoints[-1]
    if not last.remaining:
        return "complete"
    return "in-progress"


def gather_runs(state_dir: str = ".charon") -> list[dict]:
    """Read ``.charon`` directory and return a list of run summaries.

    Each summary is a plain dict (no secrets) with keys: ``run_id``, ``status``,
    ``task_id``, ``goal``, ``checkpoints_count``, ``verified_count``,
    ``remaining_count``, ``usage``, ``lkg_ref``, ``provider_history``.
    """
    sdir = Path(state_dir).resolve()
    if not sdir.exists():
        return []

    board_units: dict[str, str] = {}
    board_path = sdir / "work-board.json"
    if board_path.exists():
        try:
            from .engine.board import Board

            board = Board.load(board_path)
            for u in board.units():
                board_units[u.id] = u.state
        except Exception:
            logger.exception("failed to load work-board.json")

    runs: list[dict] = []
    for entry in sorted(sdir.iterdir()):
        if not entry.is_dir():
            continue
        ledger_path = entry / "ledger.json"
        if not ledger_path.exists():
            continue
        try:
            led = Ledger.load(sdir, entry.name)
        except Exception:
            logger.exception("failed to load ledger for %s", entry.name)
            continue

        cps = led.checkpoints()
        locked = (entry / "lock").exists()
        board_state = board_units.get(entry.name)
        status = _derive_status(entry, cps, locked, board_state)

        usage = led.cumulative_usage()
        runs.append(
            {
                "run_id": led.task_id,
                "status": status,
                "task_id": led.task_id,
                "goal": led.goal,
                "checkpoints_count": len(cps),
                "verified_count": len(cps[-1].verified) if cps else 0,
                "remaining_count": len(cps[-1].remaining) if cps else 0,
                "usage": {
                    "tokens_in": usage.tokens_in,
                    "tokens_out": usage.tokens_out,
                    "cost_usd": round(usage.cost_usd, 6),
                },
                "lkg_ref": led.lkg_ref[:8] if led.lkg_ref else "",
                "provider_history": led.provider_history,
            }
        )

    return runs
