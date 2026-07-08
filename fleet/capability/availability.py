"""Availability signal for assign() — is a candidate model/agent live and
free right now, per the session-bridge (register/board/claim/nudge)?

KNOWN GAP (documented, not hidden): a session-bridge record has NO `model`
field (register()'s schema is session_id/name/ticket/repo/status/blockers —
confirmed by reading /home/stack/.config/opencode/session-bridge/proxy.py's
_TOOLS schema). Sessions are tagged by an operator/tier-chosen id ("yoda",
"sonnet-24601"), not by the specific external model a droid is running. So
today, live availability-by-model is a best-effort SUBSTRING match against
each session's name/session_id/ticket text, not a guaranteed mapping. A
model with no textual match is "unknown" (never wrongly treated as busy).

This is why the PROOF-OF-EFFECT self-test (capability/selftest.py) exercises
availability-changes-the-pick against an injected StaticAvailability fake
rather than the live board: as of this build, the live board carries zero
model-tagged sessions (only the manager "yoda"), so it would not itself
demonstrate differentiation — see the build report for the honest breakdown.
"""
from __future__ import annotations

import json
import subprocess

PROXY_PATH = "/home/stack/.config/opencode/session-bridge/proxy.py"
FREE_STATUSES = ("pending", "done")
BUSY_STATUSES = ("in-progress", "blocked")


class AvailabilityProvider:
    def status(self, model: str) -> str:
        """Returns 'free' | 'busy' | 'unknown'."""
        raise NotImplementedError

    def note(self) -> str:
        return ""


class StaticAvailability(AvailabilityProvider):
    """Dependency-injectable fake — used by the self-test and by callers that
    already have their own availability data (e.g. a manager session that
    just ran board() itself and wants to pass the result straight in)."""

    def __init__(self, statuses: dict[str, str] | None = None, note: str = ""):
        self._statuses = statuses or {}
        self._note = note

    def status(self, model: str) -> str:
        return self._statuses.get(model, "unknown")

    def note(self) -> str:
        return self._note


class SessionBridgeAvailability(AvailabilityProvider):
    """Live implementation: shells to the session-bridge MCP proxy the same
    JSON-RPC-over-stdio way fleet/checks/bridge-health.py does (this script
    is not itself an MCP client, so it cannot call the mcp__session-bridge__*
    tools directly — it talks to the same underlying proxy those tools wrap)."""

    def __init__(self, repo: str = "charon", proxy_path: str = PROXY_PATH, timeout: float = 10.0):
        self.repo = repo
        self.proxy_path = proxy_path
        self.timeout = timeout
        self._sessions: list[dict] | None = None
        self._error: str | None = None

    def _load(self) -> None:
        if self._sessions is not None or self._error is not None:
            return
        req = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "board", "arguments": {"repo": self.repo}},
        }
        try:
            p = subprocess.run(
                ["python3", self.proxy_path],
                input=json.dumps(req) + "\n",
                capture_output=True, text=True, timeout=self.timeout,
            )
            line = [ln for ln in p.stdout.splitlines() if ln.strip()][-1]
            payload = json.loads(json.loads(line)["result"]["content"][0]["text"])
            self._sessions = payload.get("board", {}).get("sessions", [])
        except Exception as e:  # bridge down / socket missing / bad output shape
            self._sessions = []
            self._error = str(e)

    def status(self, model: str) -> str:
        self._load()
        needle = model.lower()
        for s in self._sessions or []:
            haystack = " ".join(str(s.get(k, "")) for k in ("name", "session_id", "ticket")).lower()
            if needle in haystack:
                st = s.get("status")
                if st in BUSY_STATUSES:
                    return "busy"
                if st in FREE_STATUSES:
                    return "free"
        return "unknown"

    def note(self) -> str:
        self._load()
        if self._error:
            return f"session-bridge unreachable ({self._error}) — treating all models as availability=unknown"
        return (f"{len(self._sessions or [])} live session(s) on board (repo={self.repo}); "
                f"model status resolved by best-effort name/ticket substring match")
