# DOGFOOD-SALVAGE — unlanded content rescued before the 27-worktree reap

**Session:** agen-kolar · **Date:** 2026-07-24 · **Ticket:** INERT-INSTANCE-DETECT (decision #3)

Two of the 27 `charon-fleet-dogfood-*` worktrees hold work that exists **nowhere else** —
neither on product master nor on any open branch. Both were dogfood-eval runs whose output was
never committed (the change sits as an UNCOMMITTED working-tree modification on a
`dogfood-eval/<ticket>/<model>` branch pinned at an old base). Reaping the worktrees deletes it.

Captured here so the bulk reap is non-destructive. **No worktree was deleted by this session.**

## 1. RFL-3 — vision-aware route exclusion (wires `RequestInspector.inspect()`)

### Provenance

| field | value |
|---|---|
| worktree | `charon-fleet-dogfood-RFL-3-deepseek-v4-pro-20260715T001840Z` |
| branch | `dogfood-eval/RFL-3/deepseek-v4-pro-20260715T001840Z` |
| base sha | `b7aa4c880a89917898bc3ff22f00b313f536cfe1` (`Merge pull request #126 from SLOP-Platform/chore/gitignore-tooldirs`) |
| state | UNCOMMITTED working-tree change + 1 untracked test file |
| board ticket | `fleet/board/RFL-3.md.parked` (PARKED, not archived — still live work) |
| brief | `fleet/board/briefs/RFL-3-eval.md` |

### Why this matters to INERT-INSTANCE-DETECT

RFL-3 is the **only real planned consumer of `RequestInspector` anywhere on the board.** Its brief
(`briefs/RFL-3-eval.md`, "Required change") explicitly instructs:

> 1. If `srv.request_inspector` is set, call `.inspect(orig_bj.get("messages") or [])` to get
>    `RequestHints`.

**6 of the 8 RFL-3 dogfood attempts actually produced that call site** in
`src/charon/forwarder.py` (deepseek-v4-flash, deepseek-v4-pro, free-mistral-code, glm-5.2,
kimi-k2.6, minimax-m3-together; gemma-4-31b-cb and minimax-m2.7 produced nothing). That is 6
independent models converging on the same wiring — strong evidence the intervention is real,
small, and buildable, not aspirational.

Consequence for the disposition pass: **`RequestInspector` is `wire`, not `retire`** — it has a
named consumer with a written brief and six working drafts. The other five of the six inert
gateway modules have no equivalent.

### Diff (uncommitted, `src/charon/forwarder.py`, +28)

```diff
diff --git a/src/charon/forwarder.py b/src/charon/forwarder.py
index dff1064..66b7324 100644
--- a/src/charon/forwarder.py
+++ b/src/charon/forwarder.py
@@ -292,6 +292,34 @@ def forward_with_failover(handler, srv) -> None:
                 "Capability exclusion would strand request (model=%s cap=%s); "
                 "using full chain instead.", requested, cap)
 
+    # ── vision-aware route exclusion ─────────────────────────────────
+    # If the request carries images, drop chain entries whose registry model
+    # metadata does not mark them as vision-capable.  Unlike the softer
+    # reasoning-capability heuristic (which falls back), this is a HARD
+    # exclusion: sending an image to a text-only model will 400/fail upstream
+    # regardless, so fail cleanly with a 502 rather than call an incapable
+    # provider.  The same hook shape is open for "audio" (metadata key already
+    # exists) but scoped to images only for this change.
+    inspector = getattr(srv, "request_inspector", None)
+    if inspector is not None and chain:
+        hints = inspector.inspect(orig_bj.get("messages") or [])
+        if hints.has_images:
+            model_meta = getattr(srv, "model_meta", {}) or {}
+            vision_capable = []
+            for r in chain:
+                mid = r.model_id
+                if mid and model_meta.get(mid, {}).get("vision"):
+                    vision_capable.append(r)
+            if vision_capable:
+                chain = vision_capable
+            else:
+                # HARD exclusion — never silently fall back to the text-only chain
+                srv.observer.observe(requested, 502, {}, {}, count_usage=False)
+                handler._json(502, {"error": {"message": (
+                    f"image request for model {requested!r} — "
+                    "no vision-capable provider available")}})
+                return
+
     # ── R7 capability-engine: max_context / max_concurrency eligibility ───
     # Compute a single pre-flight token estimate (reused by spend cap above).
     est_tokens = max(len(raw_body) // 4, 100)
```

### Untracked companion test — `tests/test_image_routing.py` (does not exist on master)

```python
"""RFL-3 — vision-aware route exclusion.

Image-bearing requests must be routed only to vision-capable providers.
A text-only provider in the same chain is excluded and never receives the request.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.request

from charon.proxy_server import GatewayProxyServer, UpstreamRoute
from charon.request_inspector import RequestInspector


class _Prog(http.server.BaseHTTPRequestHandler):
    """Programmable mock upstream."""

    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        srv = self.server  # type: ignore[assignment]
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        srv.received.append(body.get("model"))      # type: ignore[attr-defined]
        payload = json.dumps({
            "model": srv.return_model,                # type: ignore[attr-defined]
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                      "cost": srv.cost},             # type: ignore[attr-defined]
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _up(return_model="m", cost=0.0):
    srv = _Threaded(("127.0.0.1", 0), _Prog)
    srv.return_model, srv.cost = return_model, cost  # type: ignore[attr-defined]
    srv.received = []  # type: ignore[attr-defined]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]}:{srv.server_address[1]}"


def _req(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read()), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read()), dict(exc.headers)


def test_image_request_excludes_text_only_model():
    """An image-bearing request routes ONLY to the vision-capable provider,
    skipping the text-only provider in the same chain."""
    text_only, base_text = _up(return_model="text-only-model")
    vision_capable, base_vision = _up(return_model="vision-model")
    gw = GatewayProxyServer(
        pools={"v": [
            UpstreamRoute(base_text, "ka", upstream_model="text-only-model",
                          provider="text-only", model_id="text-only"),
            UpstreamRoute(base_vision, "kb", upstream_model="vision-model",
                          provider="vision", model_id="vision"),
        ]},
        model_ids=["v"],
        model_meta={
            "text-only": {"vision": False},
            "vision": {"vision": True},
        },
    )
    gw.request_inspector = RequestInspector()
    gw.serve_in_thread()
    try:
        status, body, hdrs = _req(
            gw.url + "/v1/chat/completions",
            {"model": "v", "messages": [
                {"role": "user", "content": [
                    {"type": "text", "text": "Describe this image"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
                ]}
            ]}
        )
        assert status == 200
        assert body["choices"][0]["message"]["content"] == "ok"
        # text-only provider was proactively excluded — never called
        assert text_only.received == []
        # vision-capable provider served the request
        assert vision_capable.received == ["vision-model"]
    finally:
        gw.shutdown()
        text_only.shutdown()
        vision_capable.shutdown()


def test_non_image_request_unaffected():
    """A non-image request is completely unaffected — the full chain is
    still considered in its normal cost/cooldown order."""
    text_only, base_text = _up(return_model="text-only-model")
    vision_capable, base_vision = _up(return_model="vision-model")
    gw = GatewayProxyServer(
        pools={"v": [
            UpstreamRoute(base_text, "ka", upstream_model="text-only-model",
                          provider="text-only", model_id="text-only"),
            UpstreamRoute(base_vision, "kb", upstream_model="vision-model",
                          provider="vision", model_id="vision"),
        ]},
        model_ids=["v"],
        model_meta={
            "text-only": {"vision": False},
            "vision": {"vision": True},
        },
    )
    gw.request_inspector = RequestInspector()
    gw.serve_in_thread()
    try:
        status, body, hdrs = _req(
            gw.url + "/v1/chat/completions",
            {"model": "v", "messages": [
                {"role": "user", "content": "Hello"}
            ]}
        )
        assert status == 200
        assert body["choices"][0]["message"]["content"] == "ok"
        # No image → no vision filtering → normal ordering, first provider used
        assert text_only.received == ["text-only-model"]
        assert vision_capable.received == []
    finally:
        gw.shutdown()
        text_only.shutdown()
        vision_capable.shutdown()


def test_image_request_no_vision_capable_provider_fails_502():
    """An image request where NO chain entry is vision-capable fails with
    a clear 502 error — the text-only upstream must NEVER be silently called."""
    text_only, base_text = _up(return_model="text-only-model")
    gw = GatewayProxyServer(
        pools={"v": [
            UpstreamRoute(base_text, "ka", upstream_model="text-only-model",
                          provider="text-only", model_id="text-only"),
        ]},
        model_ids=["v"],
        model_meta={
            "text-only": {"vision": False},
        },
    )
    gw.request_inspector = RequestInspector()
    gw.serve_in_thread()
    try:
        status, body, hdrs = _req(
            gw.url + "/v1/chat/completions",
            {"model": "v", "messages": [
                {"role": "user", "content": [
                    {"type": "text", "text": "Describe this image"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
                ]}
            ]}
        )
        assert status == 502, f"expected 502, got {status}"
        assert "vision" in body.get("error", {}).get("message", "").lower()
        # text-only provider was never called
        assert text_only.received == []
    finally:
        gw.shutdown()
        text_only.shutdown()
```

**Caveat for whoever lands this:** the draft calls `srv.observer.observe(...)` on the no-vision-route
path. `srv.observer` is `GatewayProxy` (WIRED), **not** the inert `Observability` module — the two
are easy to confuse by name. Verify the `observe()` signature against current master before reuse;
this diff is pinned to a July-15 base and `forwarder.py` has moved since.

---

## 2. SECRET-HOTROTATE — `force_refresh` on `secrets.apply_to_env()`

### Provenance

| field | value |
|---|---|
| worktree | `charon-fleet-dogfood-SECRET-HOTROTATE-deepseek-v4-pro-20260714T232603Z` |
| branch | `dogfood-eval/SECRET-HOTROTATE/deepseek-v4-pro-20260714T232603Z` |
| base sha | `b7aa4c880a89917898bc3ff22f00b313f536cfe1` (`Merge pull request #126 from SLOP-Platform/chore/gitignore-tooldirs`) |
| state | UNCOMMITTED working-tree change (src + tests) |
| absent from master | `grep -rn force_refresh src/charon/` on product master -> **0 hits** |

Selected from 11 SECRET-HOTROTATE worktrees as the most complete attempt (4 `force_refresh`
references incl. tests; the weakest attempt, minimax-m2.7, produced 0). Behaviour: today
`apply_to_env()` uses `os.environ.setdefault`, so a **rotated key never takes effect in a running
process** — a stale env var wins forever until restart. The diff adds an opt-in `force_refresh=True`
that overwrites the resident value, keeping the safe default unchanged, and keeps the
loader-sensitive-var denylist intact.

### Diff (uncommitted)

```diff
diff --git a/src/charon/secrets.py b/src/charon/secrets.py
index 9bf96bc..a8c1872 100644
--- a/src/charon/secrets.py
+++ b/src/charon/secrets.py
@@ -87,11 +87,20 @@ def set_secret(key_env: str, value: str) -> Path:
     return p
 
 
-def apply_to_env() -> None:
-    """Load stored secrets into ``os.environ`` without overriding anything already
-    set — an explicit environment variable always wins. Only well-formed key-env
-    names are loaded, and loader-sensitive vars (PATH, LD_PRELOAD, …) are never
-    injected from the file (defense-in-depth)."""
+def apply_to_env(*, force_refresh: bool = False) -> None:
+    """Load stored secrets into ``os.environ``.
+
+    * Default (``force_refresh=False``): without overriding anything already set —
+      an explicit environment variable always wins.
+    * ``force_refresh=True``: overwrite an already-resident key with the current
+      on-disk value, so a rotated key takes effect live.
+
+    Only well-formed key-env names are loaded, and loader-sensitive vars (PATH,
+    LD_PRELOAD, …) are never injected from the file (defense-in-depth).
+    """
     for k, v in load_secrets().items():
         if _KEY_ENV_RE.match(k) and k not in _SENSITIVE_ENV:
-            os.environ.setdefault(k, v)
+            if force_refresh:
+                os.environ[k] = v
+            else:
+                os.environ.setdefault(k, v)
diff --git a/tests/test_secrets.py b/tests/test_secrets.py
index c33b6f8..3c8af2b 100644
--- a/tests/test_secrets.py
+++ b/tests/test_secrets.py
@@ -119,6 +119,28 @@ def test_providers_add_unknown_without_base_url_errors(monkeypatch, tmp_path):
     assert cli.main(["providers", "add", "totally-unknown"]) == 2
 
 
+def test_apply_to_env_force_refresh_overwrites_resident(monkeypatch, tmp_path):
+    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
+    secrets.set_secret("CHARON_TEST_FR_KEY", "rotated")
+    try:
+        monkeypatch.setenv("CHARON_TEST_FR_KEY", "stale")
+        secrets.apply_to_env(force_refresh=True)
+        assert os.environ["CHARON_TEST_FR_KEY"] == "rotated"
+    finally:
+        os.environ.pop("CHARON_TEST_FR_KEY", None)
+
+
+def test_apply_to_env_no_force_refresh_stale_wins(monkeypatch, tmp_path):
+    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
+    secrets.set_secret("CHARON_TEST_FR_KEY", "rotated")
+    try:
+        monkeypatch.setenv("CHARON_TEST_FR_KEY", "stale")
+        secrets.apply_to_env()
+        assert os.environ["CHARON_TEST_FR_KEY"] == "stale"
+    finally:
+        os.environ.pop("CHARON_TEST_FR_KEY", None)
+
+
 def test_providers_add_custom_with_base_url(monkeypatch, tmp_path):
     monkeypatch.setenv("CHARON_HOME", str(tmp_path))
     rc = cli.main(["providers", "add", "mygw", "--base-url", "http://localhost:9/v1",
```

---

## Reap clearance

Every other `charon-fleet-dogfood-*` worktree was checked for unlanded content and holds none that
this file does not now carry. With this file committed, the bulk reap of all 27 is
**non-destructive**. Re-apply either diff with `git apply` from a fresh worktree on current master;
both are pinned to a mid-July base and will need a rebase, not a clean apply.
