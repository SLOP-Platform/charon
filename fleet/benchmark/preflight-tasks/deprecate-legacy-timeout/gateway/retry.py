"""Retry wrapper — reads timeout from config (correct; a decoy call site)."""
from gateway.settings import get_config


def with_retry(request):
    timeout = get_config().timeout  # correct: honors config
    return {"retry_of": request, "timeout": timeout}
