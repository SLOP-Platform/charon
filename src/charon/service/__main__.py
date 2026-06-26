"""Run the read-only Charon web service: ``python -m charon.service``.

Honest deploy guard (ADR-0004 D7): the dashboard is single-operator and the
container is the security boundary. This entrypoint **refuses a non-loopback bind
without ``CHARON_SERVICE_TOKEN``** — the bind address is only known here, so this
is where the "VPS-exposed ⇒ must be token-gated" rule belongs (the app's
``require_token`` then enforces it per request). Behind a reverse proxy + HTTPS.

    CHARON_SERVICE_HOST   bind host   (default 127.0.0.1)
    CHARON_SERVICE_PORT   bind port   (default 8001)
    CHARON_SERVICE_TOKEN  bearer token (required for a non-loopback host)
"""
from __future__ import annotations

import os
import sys

from ..netutil import is_loopback as _is_loopback


def main(argv: list[str] | None = None) -> int:
    host = os.environ.get("CHARON_SERVICE_HOST", "127.0.0.1")
    port = int(os.environ.get("CHARON_SERVICE_PORT", "8001"))
    token = os.environ.get("CHARON_SERVICE_TOKEN", "")
    if not _is_loopback(host) and not token:
        print(
            f"refusing to bind a non-loopback host ({host}) without "
            f"CHARON_SERVICE_TOKEN set — the exposed dashboard must be token-gated "
            f"(ADR-0004 D7). Set the token, or bind 127.0.0.1 for local use.",
            file=sys.stderr,
        )
        return 2
    try:
        import uvicorn
    except ImportError:  # pragma: no cover
        print("the web service needs the [service] extra: pip install 'charon[service]'",
              file=sys.stderr)
        return 2
    if not token:
        print(f"charon web (loopback, UNGATED) on http://{host}:{port}", file=sys.stderr)
    else:
        print(f"charon web (token-gated) on http://{host}:{port}", file=sys.stderr)
    uvicorn.run("charon.service.app:app", host=host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
