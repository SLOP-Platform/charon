#!/usr/bin/env python3
"""Deterministic health check for the session-bridge (reds: bridge-daemon-down).
Exits 0 ONLY if a real register+unregister round-trip through proxy.py succeeds
against the MCP-configured socket. Exits non-zero on any failure. Not a mere
socket-exists probe."""
import json
import os
import subprocess
import sys

os.environ["BRIDGE_SOCKET"] = "/home/stack/.charon/bridge.sock"
msgs = [
    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
        "name": "register",
        "arguments": {"session_id": "healthcheck-probe", "name": "healthcheck",
                      "repo": "charon", "status": "done"}}},
    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
        "name": "unregister", "arguments": {"session_id": "healthcheck-probe"}}},
]
inp = "\n".join(json.dumps(m) for m in msgs) + "\n"
try:
    p = subprocess.run(
        ["python3", "/home/stack/.config/opencode/session-bridge/proxy.py"],
        input=inp, capture_output=True, text=True, timeout=10)
    oks = sum(
        1 for line in p.stdout.splitlines()
        if json.loads(json.loads(line)["result"]["content"][0]["text"]).get("ok") is True)
    sys.exit(0 if oks == 2 else 1)
except Exception:
    sys.exit(1)
