"""Charon CLI (ADR-0002 §2.4, surface #1).

    charon run    --goal G --accept "CMD" [--accept ...] [--repo P]
                  [--backend mock|acp] [--autonomy L0|L1] [--budget N]
    charon ledger <task-id> [--state-dir D]
    charon doctor [--backend-cmd "<agent> acp"]
    charon version
"""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__, api
from .doctor import probe


def _cmd_run(args: argparse.Namespace) -> int:
    reviewer = None
    if args.review:
        from .adapters.review_mock import MockReviewer, ReviewMode
        reviewer = MockReviewer(ReviewMode(args.review))
    try:
        out = api.run_task(
            goal=args.goal,
            accept=args.accept,
            repo=args.repo,
            state_dir=args.state_dir,
            backend_name=args.backend,
            acp_cmd=args.acp_cmd,
            reviewer=reviewer,
            autonomy=args.autonomy,
            max_checkpoints=args.budget,
            max_cost_usd=args.max_cost_usd,
            max_tokens=args.max_tokens,
        )
    except (ValueError, RuntimeError, PermissionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2))
    return 0 if out["status"] == "complete" else 1


def _cmd_ledger(args: argparse.Namespace) -> int:
    try:
        out = api.show_ledger(args.task_id, state_dir=args.state_dir)
    except Exception as exc:  # LedgerCorruption etc. — surface loudly
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2))
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    cmd = args.backend_cmd.split() if args.backend_cmd else None
    rep = probe(cmd)
    print(json.dumps(rep.to_dict(), indent=2))
    return 0 if rep.ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="charon", description="Thin cross-vendor agent orchestrator")
    p.add_argument("--version", action="version", version=f"charon {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run a goal to executable acceptance")
    r.add_argument("--goal", required=True)
    r.add_argument("--accept", action="append", required=True,
                   help="executable acceptance check (repeatable); exit 0 == verified")
    r.add_argument("--repo", default=None, help="target git repo (default: a sandbox)")
    r.add_argument("--state-dir", default=api.DEFAULT_STATE_DIR)
    r.add_argument("--backend", default="mock",
                   help="backend name(s); comma-separated configures multiple "
                        "vendors for cross-vendor handoff (e.g. mock-a,mock-b)")
    r.add_argument("--autonomy", default="L0", choices=["L0", "L1", "L2", "L3"],
                   help="L2+ requires the Mode-B container (CHARON_CONTAINER_VERIFIED=1)")
    r.add_argument("--review", default=None, choices=["pass", "block", "error"],
                   help="consensus reviewer for L2 (demo mock; real reviewer is gated)")
    r.add_argument("--acp-cmd", default=None,
                   help="launch argv for a real ACP agent backend, e.g. 'opencode acp'")
    r.add_argument("--budget", type=int, default=8, help="max checkpoints")
    r.add_argument("--max-cost-usd", type=float, default=None,
                   help="cumulative cost cap (USD); stop before exceeding")
    r.add_argument("--max-tokens", type=int, default=None,
                   help="cumulative token cap; stop before exceeding")
    r.set_defaults(func=_cmd_run)

    lg = sub.add_parser("ledger", help="show a task's derived ledger state")
    lg.add_argument("task_id")
    lg.add_argument("--state-dir", default=api.DEFAULT_STATE_DIR)
    lg.set_defaults(func=_cmd_ledger)

    d = sub.add_parser("doctor", help="probe a real ACP backend (Tier-0)")
    d.add_argument("--backend-cmd", default=None, help='e.g. "claude-code acp"')
    d.set_defaults(func=_cmd_doctor)

    v = sub.add_parser("version", help="print version")
    v.set_defaults(func=lambda a: (print(__version__), 0)[1])
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
