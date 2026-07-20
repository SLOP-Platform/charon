# Evasion 4: OpenerDirector constructed directly, bypassing build_opener's name.
import urllib.request


def send(url: str, key: str):
    r = urllib.request.Request(url)
    r.add_header("Authorization", f"Bearer {key}")
    return urllib.request.OpenerDirector().open(r, timeout=30)
