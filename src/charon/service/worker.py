"""Mode B privileged worker: drains the job queue and runs the coordinator loop.

This is the ONLY process/container that may call api.run_task (the privileged
coordinator loop). The exposed web process (service/app.py) enqueues jobs to
the filesystem queue; this worker picks them up, runs them in isolation, and
archives results. The queue directory is shared between the web process and this
worker via a mounted volume; both sides are filesystem-only, no broker needed.

Queue layout (all under CHARON_QUEUE_DIR):
  pending/<job_id>.json   written by web process; awaits pickup
  running/<job_id>.json   moved atomically by worker on pickup (rename)
  done/<job_id>.json      archived on success (result field added)
  failed/<job_id>.json    archived on error   (error field added)

Rename-to-running is the atomic claim: if two worker instances race for the
same file, only one rename wins; the loser catches OSError and skips. This
gives at-most-once execution per job without a broker.

Environment variables:
  CHARON_QUEUE_DIR    queue root (required; same path as the web process)
  CHARON_STATE_DIR    .charon state root (default: ~/.charon)
  CHARON_POLL_SECS    poll interval in seconds (default: 2)

Run: python -m charon.service.worker
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from .. import api as _api

_QUEUE_DIR_ENV = "CHARON_QUEUE_DIR"
_STATE_DIR_ENV = "CHARON_STATE_DIR"
_POLL_SECS_ENV = "CHARON_POLL_SECS"
_DEFAULT_STATE_DIR = str(Path.home() / ".charon")


def _process_one(job_path: Path, state_dir: str) -> dict:
    """Read one job file and run it via the privileged loop. Returns the result dict."""
    job = json.loads(job_path.read_text())
    return _api.run_task(
        goal=job["goal"],
        accept=job["accept"],
        autonomy=job.get("autonomy", "L0"),
        max_checkpoints=int(job.get("budget", 8)),
        state_dir=state_dir,
        backend_name="acp",
    )


def _poll_once(queue_dir: Path, state_dir: str) -> bool:
    """Attempt to process one pending job. Returns True if a job was claimed."""
    pending = queue_dir / "pending"
    if not pending.is_dir():
        return False
    for job_path in sorted(pending.iterdir()):
        if job_path.suffix != ".json":
            continue
        running_dir = queue_dir / "running"
        running_dir.mkdir(parents=True, exist_ok=True)
        run_path = running_dir / job_path.name
        try:
            job_path.rename(run_path)
        except OSError:
            continue  # another worker claimed it first
        try:
            job_text = run_path.read_text()
        except OSError:
            run_path.unlink(missing_ok=True)
            return True  # claimed but unreadable; skip
        job_rec: dict = {}
        try:
            job_rec = json.loads(job_text)
            result = _process_one(run_path, state_dir)
            job_rec["result"] = result
            done_dir = queue_dir / "done"
            done_dir.mkdir(parents=True, exist_ok=True)
            (done_dir / run_path.name).write_text(json.dumps(job_rec))
        except Exception as exc:
            job_rec["error"] = str(exc)
            fail_dir = queue_dir / "failed"
            fail_dir.mkdir(parents=True, exist_ok=True)
            (fail_dir / run_path.name).write_text(json.dumps(job_rec))
        finally:
            run_path.unlink(missing_ok=True)
        return True
    return False


def main(argv: list[str] | None = None, *, _once: bool = False) -> int:
    queue_str = os.environ.get(_QUEUE_DIR_ENV, "")
    if not queue_str:
        print(
            f"error: {_QUEUE_DIR_ENV} is not set — "
            "the worker requires the path to the shared queue directory",
            file=sys.stderr,
        )
        return 2
    queue_dir = Path(queue_str)
    state_dir = os.environ.get(_STATE_DIR_ENV, _DEFAULT_STATE_DIR)
    poll_secs = float(os.environ.get(_POLL_SECS_ENV, "2"))

    print(
        f"charon worker: queue={queue_dir} state={state_dir} poll={poll_secs}s",
        file=sys.stderr,
    )

    while True:
        try:
            _poll_once(queue_dir, state_dir)
        except Exception as exc:
            print(f"worker poll error (continuing): {exc}", file=sys.stderr)
        if _once:
            break
        time.sleep(poll_secs)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
