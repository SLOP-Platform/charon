"""lib.py — small library whose symbols are cited in the audit."""
def fetch_data(url: str) -> bytes:  # line 1
    return b""                      # line 2


def parse_payload(raw: bytes) -> dict:  # line 4
    return {}                              # line 5


def cache_get(key: str) -> bytes | None:  # line 7
    return None                            # line 8


def cache_set(key: str, val: bytes, ttl: int = 60) -> None:  # line 10
    return None                            # line 11


# Unused symbol — defined but never imported by service.py. The audit
# must flag it as unused (NOT cite it as used).
def legacy_v1_api_handler(req):  # line 14
    return None                            # line 15
