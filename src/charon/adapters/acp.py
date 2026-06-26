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
import select
import subprocess
import threading
import time
from pathlib import Path

from ..proxy import GatewayProxy
from ..types import Budget, CapSet, Health, Outcome, OutcomeStatus, Tier, Usage, WorkUnit


class AcpError(RuntimeError):
    pass


class AcpBackend:
    """Drives one ACP agent subprocess.

    ``command`` is the agent's launch argv (e.g. ``["claude-code", "acp"]``).
    The agent must speak ACP over stdin/stdout.
    """

    def __init__(self, command: list[str], name: str = "acp",
                 passthrough_env: dict[str, str] | None = None,
                 observer: GatewayProxy | None = None) -> None:
        self.name = name
        self.command = command
        # The observing proxy (R1) the agent's calls flow through; it carries the
        # usage/cost OpenCode does not report over ACP. Per dispatch we emit the
        # delta so the Ledger sums real spend (INV-1, cost).
        self.observer = observer
        # Real agents need their own config/creds (e.g. ~/.config + a provider
        # key), which the fence's scrubbed env strips. Inside the Mode-B
        # container/VM — the actual isolation boundary (INV-B4) — these are merged
        # back over the scrubbed env so the agent can function; the worktree
        # escape-scan still guards the blast radius. The observing proxy (R1) is
        # what ultimately removes provider keys from the agent env entirely.
        self.passthrough_env = dict(passthrough_env or {})
        self._proc: subprocess.Popen | None = None
        self._next_id = 0
        self._lock = threading.Lock()
        self._last_usage: dict = {}
        self._buf = b""
        # Set after each session/new so probe/resume logic can surface it.
        self.last_session_id: str | None = None

    # ----------------------------------------------------------- lifecycle
    def _start(self, worktree: Path, env: dict[str, str]) -> None:
        if self._proc is not None:
            return
        merged = {**env, **self.passthrough_env}
        # Binary + unbuffered so we can `select` with a timeout (text-mode readline
        # cannot be timed out, and a hung agent — e.g. retrying a 429 — would block
        # the coordinator forever; review fix #4).
        # stderr -> DEVNULL: the agent logs there, and if we PIPE it and never
        # drain it the 64 KB pipe buffer fills, the agent blocks on write(stderr),
        # and never answers ACP — a deadlock that hung the coordinator. We read
        # only the ACP channel (stdout); the agent's logs are not ours to parse.
        self._proc = subprocess.Popen(
            self.command,
            cwd=str(worktree),
            env=merged,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        self._buf = b""

    def _readline(self, deadline: float) -> str:
        """Read one NDJSON line, bounded by ``deadline`` (monotonic). Raises
        AcpError on timeout or EOF — so a hung agent cannot block forever."""
        assert self._proc is not None and self._proc.stdout is not None
        while b"\n" not in self._buf:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AcpError("timeout waiting for agent response")
            ready, _, _ = select.select([self._proc.stdout], [], [], remaining)
            if not ready:
                raise AcpError("timeout waiting for agent response")
            chunk = self._proc.stdout.read(4096)
            if not chunk:
                raise AcpError("agent closed stream")
            self._buf += chunk
        line, _, self._buf = self._buf.partition(b"\n")
        return line.decode("utf-8", "replace")

    def _rpc(self, method: str, params: dict, timeout: float = 600.0) -> dict:
        """Send a JSON-RPC request; drain notifications until the matching
        response arrives. NDJSON: one JSON object per line. Bounded by ``timeout``."""
        if self._proc is None or self._proc.stdin is None or self._proc.stdout is None:
            raise AcpError("agent process not started")
        with self._lock:
            self._next_id += 1
            req_id = self._next_id
            msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
            self._proc.stdin.write((json.dumps(msg) + "\n").encode())
            self._proc.stdin.flush()
            deadline = time.monotonic() + timeout
            while True:
                line = self._readline(deadline)
                if not line.strip():
                    continue
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
        self.last_session_id = session_id
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
        return Outcome(OutcomeStatus.PROGRESSED, self.name, commit=commit,
                       usage=self._dispatch_usage())

    def _dispatch_usage(self) -> Usage | None:
        """Tokens/cost the proxy observed during THIS dispatch — taken atomically
        from the observer so it cannot race a concurrent dispatch (review #2)."""
        if self.observer is None:
            return None
        return self.observer.take_delta()

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
