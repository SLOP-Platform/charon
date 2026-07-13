"""Header redaction — mirrors Charon's gateway/headers.py shape.

redact_auth() removes credential-bearing headers before a request is logged,
so tokens/keys never land in the logs. This function is correct; it just has
no test pinning it.
"""

# Header names we must never log (compared case-insensitively).
_SECRET_HEADERS = ("authorization", "x-api-key", "cookie")


def redact_auth(headers):
    """Return a copy of `headers` with credential headers removed.

    Keys are matched case-insensitively. Non-secret headers pass through
    unchanged and in order.
    """
    out = {}
    for key, value in headers.items():
        if key.lower() in _SECRET_HEADERS:
            continue
        out[key] = value
    return out
