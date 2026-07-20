# Evasions 5-8: the header NAME is never an ast.Constant "Authorization", so the
# old linter's `isinstance(first, ast.Constant)` arm never fired. Concatenation,
# f-string, variable indirection, and a dict() call rather than a dict literal.
import urllib.request

H = "Authorization"


def concat(url: str, key: str):
    r = urllib.request.Request(url)
    r.add_header("Auth" + "orization", f"Bearer {key}")
    return r


def fstring(url: str, key: str):
    r = urllib.request.Request(url)
    r.add_header(f"Authorization", f"Bearer {key}")  # noqa: F541
    return r


def variable(url: str, key: str):
    r = urllib.request.Request(url)
    r.add_header(H, f"Bearer {key}")
    return r


def dict_call(url: str, key: str):
    return urllib.request.Request(url, headers=dict([("Authorization", f"Bearer {key}")]))
