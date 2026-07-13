"""Streaming path — reads timeout from config (correct; a decoy call site)."""
from gateway.settings import get_config


def open_stream(request):
    timeout = get_config().timeout  # correct: honors config
    return {"stream": request, "timeout": timeout}
