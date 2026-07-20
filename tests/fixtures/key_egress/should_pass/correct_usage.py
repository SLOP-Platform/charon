# The sanctioned shape: build through the choke point, send through the choke
# point. Proves the rule does not simply flag every outbound call site, which
# would make it unlandable and get it switched off.
from charon import netutil


def send(url: str, key: str):
    req = netutil.keyed_request(url, api_key=key)
    return netutil.open_keyed(req, timeout=30)


def unkeyed_probe(url: str):
    req = netutil.keyed_request(url)
    return netutil.open_keyed(req, timeout=10)


HEADER_REDACTION_MAP = {"authorization": "***", "x-api-key": "***"}
"""A redaction table is NOT an egress. The old linter's ast.Dict arm flagged any
dict literal with an `authorization` key and had no suppression path, so this
shape would have red-lined the merge gate with no way out (round-5 regression
review, MEDIUM). The replacement rule requires an actual send or request-build."""
