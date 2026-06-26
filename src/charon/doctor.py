"""`charon doctor` — the runnable Tier-0 backend probe (reconciliation OOB-C2).

Rather than DEFER the "verify ACP backends expose usage/resume cleanly" question
(ADR-0001 §9 Tier 0), Charon ships it as a command. Given a real ACP agent
command, it checks: can we spawn it, does it answer ``initialize``, does it
report usage (H4 fidelity), does it expose session resume/fork. It reports gaps
honestly — H4 is only as truthful as the signal.

With no agent configured it reports what WOULD be probed and exits non-zero, so
"the backend assumptions are validated" is never silently assumed.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

from .adapters.acp import AcpBackend, AcpError


@dataclass
class DoctorReport:
    backend_cmd: list[str] = field(default_factory=list)
    spawned: bool = False
    initialized: bool = False
    reports_usage: bool = False
    supports_resume: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.spawned and self.initialized

    def to_dict(self) -> dict:
        return {
            "backend_cmd": self.backend_cmd,
            "spawned": self.spawned,
            "initialized": self.initialized,
            "reports_usage": self.reports_usage,
            "supports_resume": self.supports_resume,
            "h4_truthful": self.reports_usage,
            "notes": self.notes,
        }


def probe(backend_cmd: list[str] | None) -> DoctorReport:
    rep = DoctorReport(backend_cmd=backend_cmd or [])
    if not backend_cmd:
        rep.notes.append(
            "No ACP agent configured. Tier-1 proof runs on MockBackend; the real "
            "ACP path is UNVALIDATED until you run: charon doctor --backend-cmd "
            "'<agent> acp'. Would probe: spawn, initialize, session/new, "
            "usage-reporting fidelity (H4), resume/fork (H3)."
        )
        return rep

    exe = backend_cmd[0]
    if shutil.which(exe) is None and not Path(exe).exists():
        rep.notes.append(f"agent executable not found on PATH: {exe!r}")
        return rep

    backend = AcpBackend(command=backend_cmd)
    with TemporaryDirectory() as td:
        wt = Path(td)
        try:
            backend._start(wt, {"PATH": __import__("os").environ.get("PATH", "")})
            rep.spawned = True
            result = backend._rpc("initialize",
                                  {"protocolVersion": 1, "clientCapabilities": {}},
                                  timeout=30)
            rep.initialized = True
            caps = json.dumps(result).lower()
            rep.reports_usage = "usage" in caps or "token" in caps
            rep.supports_resume = "resume" in caps or "fork" in caps or "load" in caps
            if not rep.reports_usage:
                rep.notes.append(
                    "initialize result advertises no usage/token reporting — H4 "
                    "exhaustion detection may be inference-only for this agent."
                )
        except (AcpError, OSError) as exc:
            rep.notes.append(f"probe failed: {exc}")
        finally:
            backend.kill()
    return rep


@dataclass
class HandoffReport:
    """Result of a two-backend cross-vendor handoff probe."""

    cmd_a: list[str] = field(default_factory=list)
    cmd_b: list[str] = field(default_factory=list)
    a_dispatched: bool = False
    b_dispatched: bool = False
    handoff_completes: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.a_dispatched and self.b_dispatched and self.handoff_completes

    def to_dict(self) -> dict:
        return {
            "cmd_a": self.cmd_a,
            "cmd_b": self.cmd_b,
            "a_dispatched": self.a_dispatched,
            "b_dispatched": self.b_dispatched,
            "handoff_completes": self.handoff_completes,
            "ok": self.ok,
            "notes": self.notes,
        }


def probe_handoff(
    cmd_a: list[str] | None,
    cmd_b: list[str] | None,
    *,
    env_a: dict[str, str] | None = None,
    env_b: dict[str, str] | None = None,
) -> HandoffReport:
    """Drive two ACP subprocess backends through the cross-vendor handoff contract.

    Uses the raw ``_start``/``_rpc`` surface (same depth as ``probe()``), so no
    Ledger or git repo is required. Phase A: initialize → session/new →
    session/prompt (goal: create ``handoff-a.txt``). Phase B: same on the shared
    tmp dir. Both files must exist for ``ok`` to be True.

    For real agents: pass their ACP commands; they must inspect the worktree and
    create both files. For CI (no live agents): point at a Python stdlib stub
    — see ``tests/test_handoff_crossvendor.py`` for the reference implementation.
    """
    import os

    rep = HandoffReport(cmd_a=cmd_a or [], cmd_b=cmd_b or [])
    if not cmd_a or not cmd_b:
        rep.notes.append(
            "Need two ACP agent commands for handoff probe. Would probe: both "
            "spawn, partial-progress handoff (A creates handoff-a.txt, B creates "
            "handoff-b.txt), combined acceptance. Run: charon doctor --handoff "
            "--backend-cmd-a '<agentA> acp' --backend-cmd-b '<agentB> acp'"
        )
        return rep

    _path = os.environ.get("PATH", "")
    base_env: dict[str, str] = {"PATH": _path}

    for label, cmd in (("A", cmd_a), ("B", cmd_b)):
        exe = cmd[0]
        if shutil.which(exe) is None and not Path(exe).exists():
            rep.notes.append(f"backend-{label} executable not found: {exe!r}")
            return rep

    backend_a = AcpBackend(command=cmd_a, name="probe-a",
                           passthrough_env={**base_env, **(env_a or {})})
    backend_b = AcpBackend(command=cmd_b, name="probe-b",
                           passthrough_env={**base_env, **(env_b or {})})

    with TemporaryDirectory() as td:
        wt = Path(td)
        probe_env: dict[str, str] = {}

        # Phase A — vendor A initialises and creates handoff-a.txt.
        try:
            backend_a._start(wt, probe_env)
            backend_a._rpc("initialize",
                           {"protocolVersion": 1, "clientCapabilities": {}},
                           timeout=30)
            sess_a = backend_a._rpc("session/new",
                                    {"cwd": str(wt), "mcpServers": []},
                                    timeout=30)
            sid_a = sess_a.get("sessionId") or sess_a.get("session_id", "probe-a")
            backend_a._rpc(
                "session/prompt",
                {
                    "sessionId": sid_a,
                    "prompt": [{"type": "text", "text":
                                "Create a file named handoff-a.txt in the current "
                                "directory with any content."}],
                },
                timeout=60,
            )
            rep.a_dispatched = True
        except (AcpError, OSError) as exc:
            rep.notes.append(f"backend-A probe failed: {exc}")
        finally:
            backend_a.kill()

        if not rep.a_dispatched:
            return rep

        # Phase B — vendor B takes over the shared worktree and creates handoff-b.txt.
        try:
            backend_b._start(wt, probe_env)
            backend_b._rpc("initialize",
                           {"protocolVersion": 1, "clientCapabilities": {}},
                           timeout=30)
            sess_b = backend_b._rpc("session/new",
                                    {"cwd": str(wt), "mcpServers": []},
                                    timeout=30)
            sid_b = sess_b.get("sessionId") or sess_b.get("session_id", "probe-b")
            backend_b._rpc(
                "session/prompt",
                {
                    "sessionId": sid_b,
                    "prompt": [{"type": "text", "text":
                                "handoff-a.txt already exists (created by vendor A). "
                                "Create a file named handoff-b.txt in the current "
                                "directory with any content."}],
                },
                timeout=60,
            )
            rep.b_dispatched = True
        except (AcpError, OSError) as exc:
            rep.notes.append(f"backend-B probe failed: {exc}")
        finally:
            backend_b.kill()

        if rep.b_dispatched:
            a_ok = (wt / "handoff-a.txt").exists()
            b_ok = (wt / "handoff-b.txt").exists()
            rep.handoff_completes = a_ok and b_ok
            if not a_ok:
                rep.notes.append("handoff-a.txt not found after backend-A prompt")
            if not b_ok:
                rep.notes.append("handoff-b.txt not found after backend-B prompt")

    return rep
