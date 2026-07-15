"""service.py — the file under audit. Uses fetch_data, parse_payload,
cache_get, cache_set. Does NOT use legacy_v1_api_handler."""
from lib import fetch_data, parse_payload, cache_get, cache_set


def handle(req):
    raw = fetch_data(req.url)
    parsed = parse_payload(raw)
    blob = parsed.get("payload", b"")
    cache_set(req.key, blob, ttl=300)
    if cache_get(req.key) is not None:
        return {"ok": True, "size": len(blob)}
    return {"ok": False}
