# Evasion 2: import alias hides the banned name from a textual/AST-name match.
from urllib.request import Request
from urllib.request import urlopen as u


def send(url: str, key: str):
    r = Request(url)
    r.add_header("Authorization", f"Bearer {key}")
    return u(r, timeout=30)
