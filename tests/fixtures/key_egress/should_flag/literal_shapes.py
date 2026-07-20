# The two spellings the OLD linter did catch. Kept as fixtures so the
# replacement rule is proven not to have REGRESSED the coverage it replaced.
import urllib.request


def literal_add_header(url: str, key: str):
    r = urllib.request.Request(url)
    r.add_header("Authorization", f"Bearer {key}")
    return urllib.request.urlopen(r, timeout=30)


def literal_dict(url: str, key: str):
    return urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
