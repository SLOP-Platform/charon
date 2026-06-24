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
