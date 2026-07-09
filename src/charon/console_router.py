"""Control-plane dispatch for the gateway proxy console (seam E).

The console/setup/discovery half of the request handler, extracted verbatim
from _ProxyHandler._handle. ``try_handle_control_plane`` returns True when it
has fully served the request (caller returns); False means fall through to the
data-plane forwarder. Shared HTTP emit/auth helpers stay on the handler and are
called through the passed handler instance. No logic change.
"""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

from .proxy_console_assets import _CONSOLE_HTML, _SETUP_HTML, _WORK_HTML


def try_handle_control_plane(handler, srv) -> bool:
    """Serve the control-plane routes (models/status/cost/console/setup/work).

    Returns True when the request was fully served here; False to fall through
    to the data-plane forwarder."""
    # Aggregated model list (gateway mode). Served locally — never forwarded —
    # and field-allowlisted to ids only (no key_env/upstream_base leak, ADR R4).
    # Pool virtual IDs (e.g. auto, tier names) are EXCLUDED — they are internal
    # routing concepts, not real models (MODEL-DISCOVERY).
    path_only = urlsplit(handler.path).path.rstrip("/")
    if (handler.command == "GET" and srv.model_ids is not None
            and path_only in ("/v1/models", "/models")):
        # Exclude pool virtual IDs that are NOT also concrete models
        # (a model named "auto" or "low" is a real model, not a pool).
        pool_only = set(srv.pools.keys()) - set(srv.routes.keys())
        exposed = [m for m in srv.model_ids if m not in pool_only]
        entries: list[dict] = []
        for m in exposed:
            entry: dict = {"id": m, "object": "model", "owned_by": "charon"}
            meta = srv.model_meta.get(m, {})
            for k in ("context_window", "max_tokens", "reasoning", "vision", "audio"):
                if k in meta:
                    entry[k] = meta[k]
            entries.append(entry)
        handler._json(200, {"object": "list", "data": entries})
        return True

    # Gateway console + status (P4) — gateway mode only, token-gated above.
    if handler.command == "GET" and srv.model_ids is not None:
        if path_only == "/charon/status":
            handler._json(200, srv.status_snapshot())
            return True
        # Read-only per-session cost exposure (SESSION-COST): a caller that
        # tags its own requests with X-Charon-Session can read back exactly its
        # own cumulative cost, isolated from concurrent gateway traffic tagged
        # with a different (or no) session id. No session= -> the global
        # cumulative counter (same numbers as /charon/status's "usage"), so
        # this endpoint degrades gracefully for a caller that never adopted
        # sessions. Never a billing change — read-only view over existing
        # cost_usd bookkeeping.
        if path_only == "/charon/cost":
            qs = parse_qs(urlsplit(handler.path).query)
            session_vals = qs.get("session") or []
            session_q: str | None = session_vals[0] if session_vals else None
            u = (srv.observer.session_usage(session_q) if session_q
                 else srv.observer.cumulative_usage())
            handler._json(200, {"session": session_q, "tokens_in": u.tokens_in,
                             "tokens_out": u.tokens_out,
                             "cost_usd": round(u.cost_usd, 6)})
            return True
        if path_only in ("", "/charon"):
            handler._html(_CONSOLE_HTML)
            return True

    # Web setup (read-WRITE) — only when a setup handler is wired (gateway mode,
    # token-gated above). A CSRF/Origin guard backs the token gate on writes.
    if srv.setup_handler is not None and srv.model_ids is not None:
        if handler.command == "GET" and path_only == "/charon/setup":
            handler._html(_SETUP_HTML)
            return True
        if handler.command == "GET" and path_only == "/charon/config":
            status, obj = srv.setup_handler("summary", {})
            handler._json(status, obj)
            return True
        if handler.command == "POST" and path_only in (
                "/charon/providers", "/charon/models", "/charon/models/import",
                "/charon/pools", "/charon/tiers", "/charon/fallback",
                "/charon/enable", "/charon/disable", "/charon/remove"):
            host = handler.headers.get("Host", "")
            origin = handler.headers.get("Origin")
            if origin and urlsplit(origin).netloc != host:  # CSRF: cross-origin write
                handler._json(403, {"error": {"message": "cross-origin write refused"}})
                return True
            sfs = handler.headers.get("Sec-Fetch-Site")
            if sfs and sfs not in ("same-origin", "none"):
                handler._json(403, {"error": {"message": "cross-site write refused"}})
                return True
            length = int(handler.headers.get("Content-Length") or 0)
            if length > srv.max_body_bytes:
                handler._json(413, {"error": {"message": "request body too large"}})
                return True
            raw = handler.rfile.read(length) if length else b""
            try:
                payload = json.loads(raw) if raw else {}
            except Exception:  # noqa: BLE001
                handler._json(400, {"error": {"message": "invalid JSON"}})
                return True
            if not isinstance(payload, dict):
                handler._json(400, {"error": {"message": "expected a JSON object"}})
                return True
            try:
                status, obj = srv.setup_handler(path_only[len("/charon/"):], payload)
            except ValueError as exc:
                handler._json(400, {"error": {"message": str(exc)}})  # validation msg only
                return True
            except Exception:
                handler._json(400, {"error": {"message": "setup write failed"}})  # no path leak
                return True
            handler._json(status, obj)
            return True

    # Work/board panel (P5, WORK-OBSERVABILITY follow-on) — read-only,
    # token-gated above. /charon/work returns HTML; add ?json=1 for raw JSON.
    if handler.command == "GET" and path_only == "/charon/work":
        from . import console_work
        try:
            runs = console_work.gather_runs()
        except Exception:  # noqa: BLE001
            runs = []
        qs = parse_qs(urlsplit(handler.path).query)
        if qs.get("json") == ["1"]:
            handler._json(200, {"runs": runs})
        else:
            handler._html(_WORK_HTML)
        return True
    return False
