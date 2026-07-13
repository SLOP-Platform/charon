"""Health probe — reads timeout from config (correct; a decoy call site)."""
from gateway.settings import get_config


def probe(url):
    timeout = get_config().timeout  # correct: honors config
    return {"url": url, "timeout": timeout}
