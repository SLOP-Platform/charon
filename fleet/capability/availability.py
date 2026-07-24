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
import os
import subprocess
import sys
import urllib.request

PROXY_PATH = "/home/stack/.config/opencode/session-bridge/proxy.py"
FREE_STATUSES = ("pending", "done")
BUSY_STATUSES = ("in-progress", "blocked")

# CRIPPLE #2 (FLEET-DEMAND-DRIVEN-ROUTING): the availability vocabulary now
# carries a proactive-exclusion status, "capped", DISTINCT from session-bridge
# "busy". "busy" = a droid session is already running that model right now
# (transient, contention). "capped" = the gateway's OWN park/cooldown/balance
# state says every provider that can serve this model is parked (funding drain
# / free-tier window closed), drained, or in litellm cooldown — so a call would
# burn the full request timeout (~1800s) before failing over to nothing. Both
# are UNAVAILABLE for assignment; assign.py excludes either (see UNAVAILABLE
# below and assign.py's exclusion branch). "unknown" still passes through — we
# only exclude a model we can POSITIVELY prove is contended or capped.
CAPPED = "capped"

# The gateway's read-only status panel (drain-and-park + litellm cooldown +
# balance) is the SINGLE SOURCE for capped/parked/over-quota state — the same
# /charon/status snapshot fleet/failover-canary.sh already consults. We REUSE
# it here rather than hand-rolling a second availability tracker (per the
# no-stiff-single-provider / adopt-don't-hand-roll rig doctrine).
GATEWAY_URL_ENV = "CHARON_GATEWAY_URL"
GATEWAY_URL_DEFAULT = "http://10.0.1.60:8080"
GATEWAY_TOKEN_ENVS = ("CHARON_GATEWAY_TOKEN", "CHARON_API_KEY", "OPENAI_API_KEY")
# Test/cache seam: when set, read the /charon/status snapshot from this JSON file
# instead of the network. Lets the dispatcher's capped-filter (fleet-droid.sh) and
# its tests drive capped state deterministically with ZERO network dependency —
# and lets an operator feed a cached snapshot. Same fail-open shape as the HTTP
# path: a missing/bad file yields _error -> every model 'unknown' (kept, never spilled).
GATEWAY_STATUS_FILE_ENV = "CHARON_GATEWAY_STATUS_FILE"


class AvailabilityProvider:
    def status(self, model: str) -> str:
        """Returns 'free' | 'busy' | 'capped' | 'unknown'."""
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


def _strip_gateway_prefix(model: str) -> str:
    """`charon/glm-5.2` -> `glm-5.2`. The rig hands the gateway `charon/<id>`
    but /charon/status keys its `pools` on the bare model id, so normalize
    before the lookup (idempotent for an already-bare id)."""
    return model.split("/", 1)[1] if model.startswith("charon/") else model


class GatewayStatusAvailability(AvailabilityProvider):
    """CRIPPLE #2 fix — proactively resolve capped/parked/over-quota models
    from the gateway's OWN state, so assign() never picks a model whose only
    providers are parked/drained/cooled (which would burn the full request
    timeout before failing over).

    Data source is the gateway's read-only /charon/status snapshot — the SAME
    endpoint fleet/failover-canary.sh consults — which unifies (a) drain-and-park
    balance state (`balance[provider].parked / .drained`), (b) litellm-router
    cooldown (`cooldown_seconds[provider]`), and (c) the model->provider chain
    (`pools[model]`). We do NOT hand-roll a new tracker; we read the gateway's
    published state (reuse, per rig doctrine).

    Resolution, per model id:
      * unknown provider chain (model not in `pools`) -> 'unknown' (never wrongly
        excluded — same fail-open stance SessionBridgeAvailability takes).
      * at least ONE provider in the chain is live (not parked/drained/cooled)
        -> 'free'.
      * EVERY provider in the chain is parked OR drained OR in cooldown
        -> 'capped' (proactively excluded by assign()).

    Advisory + fail-open: any error (gateway unreachable, no token, bad shape)
    yields 'unknown' for every model and a diagnostic note() — this can never
    make assign() worse than the pre-fix pass-through behavior."""

    def __init__(self, url: str | None = None, token: str | None = None, timeout: float = 8.0):
        self.url = (url or os.environ.get(GATEWAY_URL_ENV) or GATEWAY_URL_DEFAULT).rstrip("/")
        self.token = token or next((os.environ[e] for e in GATEWAY_TOKEN_ENVS if os.environ.get(e)), None)
        self.timeout = timeout
        self._snapshot: dict | None = None
        self._error: str | None = None
        # provider label -> True when parked/drained/cooled (unavailable NOW)
        self._provider_down: dict[str, bool] = {}
        self._pools: dict[str, list[str]] = {}

    def _load(self) -> None:
        if self._snapshot is not None or self._error is not None:
            return
        status_file = os.environ.get(GATEWAY_STATUS_FILE_ENV)
        if status_file:  # test/cache seam — read the snapshot from a file, no network
            try:
                with open(status_file, "r", encoding="utf-8") as fh:
                    self._snapshot = json.loads(fh.read())
            except Exception as e:  # missing / unreadable / bad shape -> fail open
                self._snapshot = {}
                self._error = str(e)
                return
        else:
            req = urllib.request.Request(f"{self.url}/charon/status")
            req.add_header("Accept", "application/json")
            if self.token:
                req.add_header("Authorization", f"Bearer {self.token}")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    self._snapshot = json.loads(resp.read().decode("utf-8"))
            except Exception as e:  # gateway down / 401 / bad shape
                self._snapshot = {}
                self._error = str(e)
                return
        snap = self._snapshot or {}
        self._pools = {k: list(v) for k, v in (snap.get("pools") or {}).items()}
        cooldown = snap.get("cooldown_seconds") or {}
        balance = snap.get("balance") or {}
        labels: set[str] = set(cooldown) | set(balance)
        for chain in self._pools.values():
            labels.update(chain)
        for label in labels:
            b = balance.get(label) or {}
            cooled = float(cooldown.get(label) or 0.0) > 0.0
            self._provider_down[label] = bool(
                b.get("parked") or b.get("drained") or cooled
            )

    def status(self, model: str) -> str:
        self._load()
        if self._error is not None:
            return "unknown"
        chain = self._pools.get(_strip_gateway_prefix(model))
        if not chain:
            return "unknown"  # model unknown to the gateway pool config — fail open
        # capped only when EVERY provider that can serve this model is down.
        if all(self._provider_down.get(p, False) for p in chain):
            return CAPPED
        return "free"

    def note(self) -> str:
        self._load()
        if self._error:
            return (f"gateway /charon/status unreachable ({self._error}) at {self.url} — "
                    f"treating all models as availability=unknown (no proactive capped-exclusion)")
        down = sorted(p for p, d in self._provider_down.items() if d)
        return (f"gateway {self.url}: {len(self._pools)} pooled model(s), "
                f"{len(down)} provider(s) parked/drained/cooled"
                + (f" ({', '.join(down)})" if down else ""))


def main(argv: list[str] | None = None) -> int:
    """CLI seam for the dispatcher's CAPPED-filter step (CRIPPLE #2/#3).

      availability.py filter-capped MODEL [MODEL ...]

    Instantiates GatewayStatusAvailability ONCE (a single /charon/status read —
    or the CHARON_GATEWAY_STATUS_FILE snapshot in tests) and prints, one per
    line, the models that are NOT gateway-capped, order preserved. Exit 0 when
    at least one survives; exit 7 when EVERY model is capped (the tier-exhausted
    signal fleet-droid.sh's resolver spills up on). Fail-open: an unreachable
    gateway / bad snapshot makes every model 'unknown' -> all KEPT, exit 0 (we
    never escalate to a paid tier merely because the status endpoint is down)."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "filter-capped":
        models = [m for m in argv[1:] if m]
        prov = GatewayStatusAvailability()
        kept = [m for m in models if prov.status(m) != CAPPED]
        for m in kept:
            print(m)
        note = prov.note()
        if note:
            print(note, file=sys.stderr)
        if not models:
            return 0  # nothing to filter -> not an "all-capped" signal
        return 0 if kept else 7
    print("usage: availability.py filter-capped MODEL [MODEL ...]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
