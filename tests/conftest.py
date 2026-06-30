from __future__ import annotations

import http.server
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from charon import gitutil


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A fresh git repo (the 'target' worktree) with an empty base commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    gitutil.init_repo(repo)
    return repo


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    d = tmp_path / "state"
    d.mkdir()
    return d


@pytest.fixture
def mock_upstream():
    """Start a mock HTTP upstream server on a random port.

    Yields (url, server, captured_dict).  The captured dict records the
    model, messages, and Authorization header of the most recent POST.
    The server is shut down automatically after the test.
    """
    captured: dict = {}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length)
            body = json.loads(raw)
            captured["model"] = body.get("model")
            captured["messages"] = body.get("messages")
            captured["auth"] = self.headers.get("Authorization")

            resp = json.dumps({
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "model": body.get("model", "?"),
                "choices": [{"index": 0, "message": {
                    "role": "assistant", "content": "hello"}}],
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    host, bound_port = srv.server_address[:2]
    if isinstance(host, bytes):
        host = host.decode()

    url = f"http://{host}:{bound_port}/v1"
    yield url, srv, captured

    srv.shutdown()


@pytest.fixture
def _post():
    """Return a callable that POSTs a chat-completion body to url/chat/completions.

    Returns (status_code, response_json_dict).
    """
    def post(url: str, body: dict) -> tuple[int, dict]:
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            url + "/chat/completions", data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            r = urllib.request.urlopen(req, timeout=10)
            return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    return post
