# Evasion 3: aliased build_opener, then .open() on the returned opener. The
# default opener set includes HTTPRedirectHandler, so this FOLLOWS 30x with the
# Authorization header still attached — the round-4 forwarder bug exactly.
from urllib.request import Request
from urllib.request import build_opener as bo


def send(url: str, key: str):
    r = Request(url)
    r.add_header("Authorization", f"Bearer {key}")
    return bo().open(r, timeout=30)
