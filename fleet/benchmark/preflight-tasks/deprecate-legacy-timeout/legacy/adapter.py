"""Legacy upstream adapter — mirrors Charon's legacy/adapter.py shape.

THIS is the odd one out: it uses a hardcoded LEGACY_TIMEOUT instead of the
configured timeout, so operator config changes never reach the legacy path.
Every other call site reads gateway.settings.get_config().timeout.
"""

# BUG: hardcoded — ignores config.timeout. This is the site to fix.
LEGACY_TIMEOUT = 45


def send_legacy(request):
    timeout = LEGACY_TIMEOUT
    return {"legacy_request": request, "timeout": timeout}
