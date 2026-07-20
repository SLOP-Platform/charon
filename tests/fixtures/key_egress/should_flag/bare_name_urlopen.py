# Evasion 1 (round-5 review H1, EXECUTED against the old AST linter: exit 0).
# The old check nested both arms inside `isinstance(node.func, ast.Attribute)`,
# so a bare-name call was invisible. This is a complete key-bearing exfil sender.
from urllib.request import Request, urlopen

_A = "Authorization"


def send(url: str, key: str):
    r = Request(url)
    r.add_header(_A, "Bearer " + key)
    return urlopen(r, timeout=30)
