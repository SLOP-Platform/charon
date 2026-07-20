# Evasion H2: the old linter exempted any path ENDING in `charon/netutil.py`, so
# a file at src/charon/adapters/charon/netutil.py scanned clean while containing
# the exact literal shapes the linter did catch elsewhere. This fixture lives at
# .../key_egress/should_flag/nested_charon_netutil/netutil.py — note the parent
# directory is deliberately NOT named `charon`, because the replacement rule
# pins the ONE real choke-point path rather than matching a suffix. A sibling
# case with a literal `charon/` parent is exercised in the gate test.
import urllib.request


def send(url: str, key: str):
    r = urllib.request.Request(url)
    r.add_header("Authorization", f"Bearer {key}")
    return urllib.request.urlopen(r, timeout=30)
