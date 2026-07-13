"""Primary proxy path — reads timeout from config (correct; a decoy call site)."""
from gateway.settings import get_config


def send(request):
    timeout = get_config().timeout  # correct: honors config
    return {"request": request, "timeout": timeout}
