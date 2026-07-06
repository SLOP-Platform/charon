#!/usr/bin/env python3
"""SESSION-COST self-test: proves the benchmark's per-session cost reading
(lib/charon_cost.py `session_id()` / `snapshot_cost_usd()`) is actually
ISOLATED from concurrent gateway traffic tagged with a different (or no)
session id - the exact gap this feature exists to close (bench.sh's
pre-existing global-delta method reads Charon's gateway-GLOBAL cost_usd,
which a concurrent fleet tab hitting the same gateway pollutes).

Spins up a REAL Charon GatewayProxyServer (product code, not a fake) in
front of a tiny mock upstream, drives it exactly like `lib/grade_state.py`
would (snapshot before/after via `charon_cost.snapshot_cost_usd()`), and
fires a CONCURRENT "dummy" request tagged with a different session id
in between the two snapshots - then asserts the section's read delta only
reflects the bench-tagged request(s), not the dummy one, even though the
dummy request DOES bump the gateway's global counter.

Requires the Charon product change (GatewayProxy.session_usage /
GET /charon/cost) to be importable. That change was built and committed on
branch `feat/session-cost-tracker` (not yet merged to master at the time
this self-test was written) - CHARON_SRC_DIR below defaults to trying the
main tree first, then that worktree, so this test starts passing against
the main tree the moment the product change lands with no edits needed
here. If neither has it, this exits 2 with a clear message (not a false
PASS/FAIL).

Usage: python3 selftest/session_cost_selftest.py
"""
from __future__ import annotations

import http.server
import json
import os
import socketserver
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH_DIR = HERE.parent
LIB_DIR = BENCH_DIR / "lib"

_CANDIDATE_CHARON_SRC = [
    os.environ.get("CHARON_SRC_DIR", ""),
    "/home/stack/code/charon/src",
    "/home/stack/code/charon/.worktrees/session-cost/src",
]


def _find_charon_src() -> Path | None:
    for cand in _CANDIDATE_CHARON_SRC:
        if not cand:
            continue
        p = Path(cand)
        if (p / "charon" / "proxy.py").exists():
            sys.path.insert(0, str(p))
            # Drop any previously-imported `charon` package from a DIFFERENT
            # candidate path first - importlib.reload() reloads a module from
            # the file it's already bound to, so without this a stale import
            # from an earlier (feature-less) candidate would keep shadowing
            # every later candidate even after sys.path changes.
            for mod_name in list(sys.modules):
                if mod_name == "charon" or mod_name.startswith("charon."):
                    del sys.modules[mod_name]
            try:
                import charon.proxy as proxy_mod  # noqa: PLC0415
                if hasattr(proxy_mod.GatewayProxy, "session_usage"):
                    return p
            except Exception:  # noqa: BLE001
                pass
            sys.path.pop(0)
    return None


class _Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


_COST_PER_CALL = 0.01


class _MockUpstream(http.server.BaseHTTPRequestHandler):
    """Every call succeeds with a fixed $0.01 cost - isolation is proven by
    COUNTING calls attributed per bucket, not by pricing realism."""

    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        payload = json.dumps({
            "model": body.get("model", "m"),
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                      "cost": _COST_PER_CALL},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _post(url: str, session: str | None) -> None:
    headers = {"Content-Type": "application/json"}
    if session is not None:
        headers["X-Charon-Session"] = session
    req = urllib.request.Request(
        url, data=json.dumps({"model": "m"}).encode(),
        headers=headers, method="POST")
    urllib.request.urlopen(req, timeout=10).read()


def main() -> None:
    src = _find_charon_src()
    if src is None:
        print("SKIP: Charon product SESSION-COST change not importable from "
              f"any of {[c for c in _CANDIDATE_CHARON_SRC if c]} - "
              "nothing to prove yet (not a self-test failure).")
        sys.exit(2)
    print(f"(using Charon source at {src})")

    sys.path.insert(0, str(LIB_DIR))
    import charon_cost  # noqa: E402
    from charon.proxy_server import GatewayProxyServer  # noqa: E402

    upstream = _Threaded(("127.0.0.1", 0), _MockUpstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    up_host, up_port = upstream.server_address[0], upstream.server_address[1]

    proxy = GatewayProxyServer(
        upstream_base=f"http://{up_host}:{up_port}",
        api_key="k", model_ids=["m"])
    proxy.serve_in_thread()

    failures: list[str] = []
    try:
        session = "bench-run-selftest"
        os.environ["CHARON_BENCH_STATUS_URL"] = f"{proxy.url}/charon/status"
        os.environ["CHARON_BENCH_STATUS_TOKEN"] = "unused"  # proxy has no token gate
        os.environ["CHARON_BENCH_SESSION_ID"] = session

        # sanity: session_id()/cost_attribution_method() pick up the env var
        if charon_cost.session_id() != session:
            failures.append(f"session_id() returned {charon_cost.session_id()!r}, expected {session!r}")
        if charon_cost.cost_attribution_method() != "session":
            failures.append(f"cost_attribution_method() returned "
                            f"{charon_cost.cost_attribution_method()!r}, expected 'session'")

        # `init`-equivalent snapshot for the bench "section"
        start = charon_cost.snapshot_cost_usd()
        if start is None:
            failures.append("snapshot_cost_usd() returned None at section start "
                            "(gateway unreachable? check the mock upstream/proxy setup)")
            start = 0.0

        # ONE bench-tagged request (this section's real spend)...
        _post(proxy.url + "/v1/chat/completions", session)
        # ...and a CONCURRENT "dummy" request under a DIFFERENT session id,
        # simulating another fleet tab hitting the SAME shared gateway during
        # this section's timebox. It must bump the GLOBAL counter but never
        # leak into the bench session's bucket.
        dummy_thread = threading.Thread(
            target=_post, args=(proxy.url + "/v1/chat/completions", "concurrent-dummy-tab"))
        dummy_thread.start()
        dummy_thread.join(timeout=10)
        # a third request with NO session header at all - must not leak either
        _post(proxy.url + "/v1/chat/completions", None)

        # `record`-equivalent snapshot at section end
        end = charon_cost.snapshot_cost_usd()
        if end is None:
            failures.append("snapshot_cost_usd() returned None at section end")
            end = start

        delta_str = charon_cost.delta_str(start, end)
        delta = float(delta_str) if delta_str != "-" else None
        if delta is None:
            failures.append(f"delta_str() produced '-' (untrusted) for start={start} end={end}")
        elif round(delta, 6) != _COST_PER_CALL:
            failures.append(
                f"section delta = {delta} (expected exactly {_COST_PER_CALL} for the ONE "
                f"bench-tagged request) - concurrent traffic under a different session "
                f"leaked into this section's cost, isolation is BROKEN")

        # cross-check directly against the gateway's own bookkeeping
        global_usage = proxy.observer.cumulative_usage()
        expected_global = round(3 * _COST_PER_CALL, 6)  # bench + dummy + no-session, all served
        if round(global_usage.cost_usd, 6) != expected_global:
            failures.append(
                f"gateway global cost_usd = {global_usage.cost_usd}, expected "
                f"{expected_global} (3 served requests) - test setup itself is wrong")
        dummy_usage = proxy.observer.session_usage("concurrent-dummy-tab")
        if round(dummy_usage.cost_usd, 6) != _COST_PER_CALL:
            failures.append(
                f"concurrent-dummy-tab session bucket = {dummy_usage.cost_usd}, "
                f"expected {_COST_PER_CALL} - it should hold exactly its own request")
    finally:
        proxy.shutdown()
        upstream.shutdown()
        for var in ("CHARON_BENCH_STATUS_URL", "CHARON_BENCH_STATUS_TOKEN",
                    "CHARON_BENCH_SESSION_ID"):
            os.environ.pop(var, None)

    if failures:
        print(f"SESSION-COST SELF-TEST FAILURES ({len(failures)}):")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    print("SESSION-COST SELF-TEST PASS: a concurrent request under a different "
          "session id (and one with no session at all) did NOT pollute the "
          f"bench-tagged section's cost delta (== ${_COST_PER_CALL} exactly), "
          "while the gateway's global counter summed all three - isolation proven.")


if __name__ == "__main__":
    main()
