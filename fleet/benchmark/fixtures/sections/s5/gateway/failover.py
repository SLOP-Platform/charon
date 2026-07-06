"""classify_error() - mirrors Charon's gateway/failover.py shape."""

RETRY, FAILOVER, FATAL = "RETRY", "FAILOVER", "FATAL"


def classify_error(status, body=None):
    if status in (429, 503):
        return RETRY
    if status in (401, 402, 403, 404):
        return FAILOVER
    if status >= 500:
        return FAILOVER
    return FATAL
