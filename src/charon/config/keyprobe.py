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


def validate_provider_key(
    name: str, base_url: str | None, api_key: str, *,
    skip_probe: bool = False,
) -> dict:
    """Probe a provider with a real chat-completion request to validate the key.
    Returns ``{valid, message, models_count, skipped}`` — never echoes the key. On
    success also returns the number of models available (if /models is reachable).
    ``skipped`` is True only when ``skip_probe=True`` (no HTTP calls made).

    Validation logic (PROVIDER-PROBE-FIX):
    - A successful authenticated ``GET /models`` (200 + parseable list) is sufficient
      on its own — the chat probe is a fallback, not the gate.
    - When the chat probe DOES run, pick a real model id from /models if any were
      returned (instead of the placeholder ``"."``) so chat-capable providers that
      reject nonsense model ids aren't penalised.
    - On a non-401/403 HTTPError from the chat probe, fall back to the /models
      result (the prior behaviour for timeouts/network errors). A 401/403 always
      means the key is rejected, regardless of /models.
    - ``skip_probe=True`` persists the provider unvalidated, for operators with
      token-gated/limited-access keys where even /models isn't reachable pre-
      activation. The returned ``skipped=True`` lets the caller/UI surface a
      "not validated" state instead of silent success.

    Security: non-http(s) bases and link-local/metadata hosts are refused (SSRF
    guard). Redirects are disabled (no cross-host key leak)."""
    from urllib.parse import urlsplit

    if skip_probe:
        return {"valid": True, "message": "probe skipped by operator request",
                "models_count": 0, "skipped": True}

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
    models_ok = False
    first_model_id: str | None = None
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
            models_ok = True
            for item in items:
                if isinstance(item, dict):
                    mid = item.get("id")
                    if isinstance(mid, str) and mid:
                        first_model_id = mid
                        break
    except Exception:
        pass  # fall through to the completion probe

    # If /models already proved the key works, that's sufficient — return early
    # before the chat probe can wrongly reject a real model id. (PROVIDER-PROBE-FIX:
    # a 200 + parseable list IS the validation signal.)
    if models_ok:
        return {"valid": True,
                "message": "key validated via /models",
                "models_count": models_count}

    # Probe 2: POST /chat/completions — universal fallback
    chat_model = first_model_id or "."
    try:
        body = json.dumps({
            "model": chat_model,
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
        # Non-401/403 on the chat probe. /models was unreachable/unparseable
        # (or we'd have returned above), so we cannot rescue via models_count.
        return {"valid": False, "message": f"probe failed (HTTP {exc.code})"}
    except Exception:  # noqa: BLE001
        # Network / timeout / DNS / TLS failure on the chat probe. The /models
        # short-circuit above means we got here only when /models also failed
        # (or wasn't parseable), so we cannot cross-check via models_count.
        return {"valid": False, "message": "provider unreachable or probe timed out"}
