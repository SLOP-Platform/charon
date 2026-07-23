#!/usr/bin/env python3
"""S3 grader — CI-infra: fix broken workflow (Tier 2, work_class=ci-infra).
Three injected defects (YAML indentation, pipefail-masked shell bug, hardcoded
colliding port) + a no-weakening gate-scope guard.
Usage: python3 s3.py --worktree <dir> --baseline fixtures/sections/s3
"""
import http.server
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

CI_PATH = ".github/workflows/ci.yml"
SMOKE_PATH = "scripts/smoke.sh"
CHECK_MARKER_RE = re.compile(r"#\s*CHECK:")
HARDCODED_PORT_RE = re.compile(r"HOST_PORT\s*[:=]\s*[\"']?\$?\{?HOST_PORT?:?-?\s*(\d{4,5})\b")


def yaml_ok(worktree):
    import yaml
    path = worktree / CI_PATH
    try:
        data = yaml.safe_load(path.read_text())
    except Exception as e:
        return False, f"YAML parse error: {e}"
    if not isinstance(data, dict) or "jobs" not in data:
        return False, "YAML parses but missing 'jobs'"
    if shutil.which("actionlint"):
        proc = subprocess.run(["actionlint", str(path)], capture_output=True, text=True, cwd=str(worktree))  # noqa: E501
        if proc.returncode != 0:
            return False, f"actionlint: {proc.stdout.strip() or proc.stderr.strip()}"
    return True, "yaml valid" + (" + actionlint clean" if shutil.which("actionlint") else "")


def pipefail_static_ok(worktree):
    smoke = worktree / SMOKE_PATH
    if not smoke.exists():
        return False, "scripts/smoke.sh missing"
    text = smoke.read_text()
    bash_n = subprocess.run(["bash", "-n", str(smoke)], capture_output=True, text=True)
    if bash_n.returncode != 0:
        return False, f"bash -n failed: {bash_n.stderr.strip()}"
    if "set -o pipefail" not in text:
        return False, "set -o pipefail not present"
    return True, "bash -n clean, pipefail present"


def hardcoded_port_ok(worktree):
    ci_text = (worktree / CI_PATH).read_text() if (worktree / CI_PATH).exists() else ""
    smoke_text = (worktree / SMOKE_PATH).read_text() if (worktree / SMOKE_PATH).exists() else ""
    # a literal 4-5 digit port hardcoded directly as an assignment/default (not
    # sourced purely from env with no numeric fallback) in either file
    if re.search(r"HOST_PORT[:=]\s*[\"']?\d{4,5}\b", ci_text):
        return False, "ci.yml still hardcodes HOST_PORT literal"
    if re.search(r"HOST_PORT[:=][-\s]*[\"']?\d{4,5}\b", smoke_text) or re.search(r"HOST_PORT:-\s*\d{4,5}", smoke_text):  # noqa: E501
        return False, "smoke.sh still has a hardcoded HOST_PORT default"
    return True, "no hardcoded port literal found"


class _StubHandler(http.server.BaseHTTPRequestHandler):
    body = b'{"status":"ok"}'
    status_code = 200

    def do_GET(self):
        self.send_response(self.status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *a):
        pass


def _free_closed_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port  # nothing listens here anymore -> connection refused


def run_smoke(worktree, host_port, timeout=10):
    env = dict(os.environ)
    env["HOST_PORT"] = str(host_port)
    try:
        proc = subprocess.run(["bash", str(worktree / SMOKE_PATH)], cwd=str(worktree),
                               env=env, capture_output=True, text=True, timeout=timeout)
        return proc.returncode
    except subprocess.TimeoutExpired:
        return 124


def behavioral_masking_fixed(worktree):
    """(c) run the smoke script against a stubbed FAILING endpoint - must exit non-zero.
    Also sanity-check it still exits 0 against a genuinely healthy stub."""
    if not (worktree / SMOKE_PATH).exists():
        return False, "smoke.sh missing"

    unreachable_port = _free_closed_port()
    rc_unreachable = run_smoke(worktree, unreachable_port)

    class Handler(_StubHandler):
        body = b'{"status":"ok"}'
        status_code = 200

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        rc_healthy = run_smoke(worktree, port)
    finally:
        server.shutdown()
        t.join(timeout=5)

    if rc_unreachable == 0:
        return False, "smoke.sh exits 0 against an unreachable health endpoint (masking bug still present)"  # noqa: E501
    if rc_healthy != 0:
        return False, "smoke.sh exits non-zero even against a genuinely healthy stub (over-broken, not just fixed)"  # noqa: E501
    return True, "exits non-zero on unreachable stub, zero on healthy stub"


def markers_preserved(worktree, baseline):
    b_count = len(CHECK_MARKER_RE.findall((baseline / SMOKE_PATH).read_text()))
    w_smoke = worktree / SMOKE_PATH
    w_count = len(CHECK_MARKER_RE.findall(w_smoke.read_text())) if w_smoke.exists() else 0
    return w_count >= b_count, f"CHECK markers baseline={b_count} worktree={w_count}"


def main():
    worktree, baseline = common.parse_args(sys.argv[1:])

    ok_yaml, msg_yaml = yaml_ok(worktree)
    ok_pipefail_static, msg_ps = pipefail_static_ok(worktree)
    ok_behavioral, msg_beh = behavioral_masking_fixed(worktree)
    ok_port, msg_port = hardcoded_port_ok(worktree)
    ok_markers, msg_markers = markers_preserved(worktree, baseline)

    defect_yaml = ok_yaml
    defect_pipefail = ok_pipefail_static and ok_behavioral
    defect_port = ok_port
    defects_fixed = sum([defect_yaml, defect_pipefail, defect_port])

    reason = f"yaml={ok_yaml}({msg_yaml}); pipefail_static={ok_pipefail_static}; behavioral={ok_behavioral}({msg_beh}); port={ok_port}({msg_port}); markers={msg_markers}"  # noqa: E501

    if not ok_markers:
        score = 25 if defects_fixed > 0 else 0
        return common.emit(score, "fail", "gate weakened: an existing CHECK assertion was removed - " + reason)  # noqa: E501

    if defects_fixed == 3:
        return common.emit(100, "pass", "all 3 defects fixed, no assertions weakened - " + reason)
    if defects_fixed == 2:
        return common.emit(75, "pass", "2 of 3 defects fixed - " + reason)
    if defects_fixed == 1:
        return common.emit(50, "fail", "1 of 3 defects fixed - " + reason)
    return common.emit(0, "fail", "still red / no defects fixed - " + reason)


if __name__ == "__main__":
    main()
