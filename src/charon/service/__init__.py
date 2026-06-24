"""HTTP service surface (ADR-0002 §2.4 surface #3 / Mode B).

Scaffolded in Tier 1, live in Tier 2. FastAPI is an OPTIONAL dependency (extra
``[service]``) so the core install and the privileged loop carry no web
framework. Import lazily."""
from __future__ import annotations


def get_app():  # pragma: no cover - exercised in Tier 2
    from .app import app

    return app
