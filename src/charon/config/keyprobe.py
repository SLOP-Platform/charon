"""Provider key validation (SSRF-guarded probe)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from ..netutil import BROWSER_UA

_VALIDATE_TIMEOUT = 15.0
# Browser-like UA (P5): Cloudflare-fronted providers (groq/cerebras/together)
# 403/"1010" a non-browser UA, wrongly failing key validation. Shared constant.
_VALIDATE_UA = BROWSER_UA


def validate_provider_key(name: str, base_url: str | None, api_key: str) -> dict:
    """Probe a provider with a real chat-completion request to validate the key.
    Returns ``{valid, message, models_count}`` — never echoes the key. On success
    also returns the number of models available (if /models is reachable).

    Security: non-http(s) bases and link-local/metadata hosts are refused (SSRF
    guard). Redirects are disabled (no cross-host key leak)."""
    from urllib.parse import urlsplit

    parts = urlsplit(base_url or "")
    if parts.scheme not in ("http", "https"):
        return {"valid": False, "message": f"invalid base URL scheme {parts.scheme!r}"}
    host = parts.hostname or ""
    if host.startswith("169.254.") or host == "metadata.google.internal":
        return {"valid": False, "message": "refusing link-local / metadata host"}

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):  # noqa: ANN002, ANN003
            return None

    opener = urllib.request.build_opener(_NoRedirect())
    raw_base = base_url.rstrip("/") if base_url else ""

    # Probe 1: GET /models — cheap, tells us the key works + model count
    models_count = 0
    try:
        req = urllib.request.Request(raw_base + "/models", method="GET")
        req.add_header("User-Agent", _VALIDATE_UA)
        req.add_header("Authorization", "Bearer " + api_key)
        resp = opener.open(req, timeout=_VALIDATE_TIMEOUT)
        raw = resp.read(200_000)
        data = json.loads(raw.decode("utf-8", "replace"))
        items = data.get("data") if isinstance(data, dict) else data
        if isinstance(items, list):
            models_count = len(items)
    except Exception:
        pass  # fall through to the completion probe

    # Probe 2: POST /chat/completions — universal fallback
    try:
        body = json.dumps({
            "model": ".",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1,
        }).encode()
        req = urllib.request.Request(raw_base + "/chat/completions", data=body, method="POST")
        req.add_header("User-Agent", _VALIDATE_UA)
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + api_key)
        resp = opener.open(req, timeout=_VALIDATE_TIMEOUT)
        resp.read(1024)
        return {"valid": True, "message": "key validated — chat probe succeeded",
                "models_count": models_count}
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return {"valid": False, "message": f"key rejected (HTTP {exc.code})"}
        return {"valid": False, "message": f"probe failed (HTTP {exc.code})"}
    except Exception:  # noqa: BLE001
        if models_count > 0:
            # /models worked but /completions didn't — common for some APIs
            return {"valid": True, "message": "key validated via /models",
                    "models_count": models_count}
        return {"valid": False, "message": "provider unreachable or probe timed out"}
