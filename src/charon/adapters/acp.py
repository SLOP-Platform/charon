"""AcpBackend — a real Agent Client Protocol client (ADR-0001 §2/§3).

Charon is an ACP *client*: it speaks stdio + NDJSON JSON-RPC to an ACP *agent*
subprocess (Claude Code, Codex, Gemini CLI, OpenCode, … via their adapters).
This implements the client framing — initialize / session.new / session.prompt,
draining session.update notifications, and session.cancel.

Honesty register (reconciliation OOB-C2): this speaks the protocol, but H4
exhaustion-fidelity and resume/fork semantics differ per agent and are NOT
claimed validated until ``charon doctor`` is run green against a real agent. The
loop and invariants are proven via MockBackend; this adapter is the real-path
seam.
"""
from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

from ..types import Budget, CapSet, Health, Outcome, OutcomeStatus, Tier, WorkUnit


class AcpError(RuntimeError):
    pass


class AcpBackend:
    """Drives one ACP agent subprocess.

    ``command`` is the agent's launch argv (e.g. ``["claude-code", "acp"]``).
    The agent must speak ACP over stdin/stdout.
    """

    def __init__(self, command: list[str], name: str = "acp") -> None:
        self.name = name
        self.command = command
        self._proc: subprocess.Popen | None = None
        self._next_id = 0
        self._lock = threading.Lock()
        self._last_usage: dict = {}

    # ----------------------------------------------------------- lifecycle
    def _start(self, worktree: Path, env: dict[str, str]) -> None:
        if self._proc is not None:
            return
        self._proc = subprocess.Popen(
            self.command,
            cwd=str(worktree),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def _rpc(self, method: str, params: dict, timeout: float = 600.0) -> dict:
        """Send a JSON-RPC request; drain notifications until the matching
        response arrives. NDJSON: one JSON object per line."""
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            raise AcpError("agent process not started")
        with self._lock:
            self._next_id += 1
            req_id = self._next_id
            msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
            self._proc.stdin.write(json.dumps(msg) + "\n")
            self._proc.stdin.flush()
            while True:
                line = self._proc.stdout.readline()
                if not line:
                    raise AcpError(f"agent closed stream during {method}")
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # session/update notifications carry usage; capture for health().
                if obj.get("method") == "session/update":
                    self._absorb_update(obj.get("params", {}))
                    continue
                if obj.get("id") == req_id:
                    if "error" in obj:
                        raise AcpError(f"{method} failed: {obj['error']}")
                    return obj.get("result", {})

    def _absorb_update(self, params: dict) -> None:
        usage = params.get("usage") or params.get("tokenUsage")
        if isinstance(usage, dict):
            self._last_usage = usage

    # -------------------------------------------------------- port methods
    def dispatch(
        self,
        unit: WorkUnit,
        tier: Tier,
        budget: Budget,
        worktree: Path,
        env: dict[str, str],
    ) -> Outcome:
        self._start(worktree, env)
        self._rpc("initialize", {"protocolVersion": 1,
                                 "clientCapabilities": {}})
        session = self._rpc("session/new", {"cwd": str(worktree),
                                            "mcpServers": []})
        session_id = session.get("sessionId") or session.get("session_id")
        try:
            self._rpc(
                "session/prompt",
                {
                    "sessionId": session_id,
                    "prompt": [{"type": "text", "text": unit.goal}],
                },
            )
        except AcpError as exc:
            if "rate" in str(exc).lower() or "quota" in str(exc).lower():
                return Outcome(OutcomeStatus.EXHAUSTED, self.name, note=str(exc))
            return Outcome(OutcomeStatus.BLOCKED, self.name, note=str(exc))
        # The agent edited files in the worktree directly (PERF-1: we do not
        # relay tokens). Commit so there is a real lkg-able SHA.
        from .. import gitutil

        commit = gitutil.commit_all(worktree, f"{self.name}: {unit.task_id}")
        return Outcome(OutcomeStatus.PROGRESSED, self.name, commit=commit)

    def health(self) -> Health:
        u = self._last_usage
        remaining = u.get("remaining")
        return Health(
            budget_remaining=(remaining is None or remaining > 0),
            rate_limited=bool(u.get("rate_limited", False)),
            context_pressure=bool(u.get("context_pressure", False)),
        )

    def capabilities(self) -> CapSet:
        return CapSet(frozenset())

    def kill(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
