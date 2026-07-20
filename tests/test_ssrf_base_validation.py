"""SSRF base-URL validation — every encoding of the cloud-metadata address.

Round 5 (and every round before it) guarded with ``host.startswith("169.254.")``.
That is a STRING match against one spelling of an address the C resolver accepts
in at least five other spellings, so ``http://2852039166/`` — the same host —
walked straight through to 169.254.169.254 and would have been sent a provider
key. This suite pins the CLASS.

The load-bearing test here is ``test_parser_matches_inet_aton_exactly``: rather
than hand-listing encodings (which is how the original guard was written, and
which is why it only covered one), it asserts byte-for-byte agreement with
``socket.inet_aton``, the function the OS actually resolves through. A form this
parser and the resolver disagree about is either a bypass (resolver reaches an
address we cleared) or a false positive (we block something reachable).
"""
from __future__ import annotations

import socket

import pytest

from charon import netutil

# Encodings that the RESOLVER genuinely maps to 169.254.169.254. Verified with
# socket.inet_aton rather than copied from a write-up: the round-5 review's octal
# example (0250.0376.0251.0376) is actually 168.254.169.254, a different and
# routable host, so blocking it would have been a false positive.
METADATA_ENCODINGS = [
    pytest.param("169.254.169.254", id="dotted-quad"),
    pytest.param("2852039166", id="decimal"),
    pytest.param("0xA9FEA9FE", id="hex"),
    pytest.param("0251.0376.0251.0376", id="octal"),
    pytest.param("169.16689662", id="two-part-inet_aton"),
]

# Non-routable classes that no provider legitimately lives in.
# NOTE: 0.0.0.0 / :: are deliberately NOT here. They are the wildcard BIND
# address, and operators copy them out of an `ollama serve --host 0.0.0.0` or
# `vllm --host 0.0.0.0` invocation straight into a provider base_url. Master
# accepted them and Linux connects them to loopback, so blocking them was a
# regression against a common local-provider config — pinned allowed by
# test_wildcard_bind_address_is_allowed below.
NON_ROUTABLE = [
    pytest.param("224.0.0.1", id="multicast"),
    pytest.param("240.0.0.1", id="reserved"),
    pytest.param("[fe80::1]", id="ipv6-link-local"),
]

# Bases that MUST keep working. The local presets (lmstudio/jan/ollama/vllm/local)
# all ship localhost bases and a LAN Ollama box is the product's normal case, so
# these are the positive controls that stop the guard being "fixed" into a brick.
#
# The `public-clean: allow` waivers below are not leaks: this suite is ABOUT which
# address ranges are accepted, so RFC1918 literals are the fixture data itself.
# They are generic range examples, not any real host.
LEGITIMATE = [
    pytest.param("https://api.openai.com/v1", id="public-https"),
    pytest.param("https://openrouter.ai/api/v1", id="public-provider"),
    pytest.param("http://localhost:11434/v1", id="ollama-localhost"),
    pytest.param("http://127.0.0.1:1234/v1", id="lmstudio-loopback"),
    pytest.param("http://192.168.1.50:8000/v1", id="lan-rfc1918"),  # public-clean: allow
    pytest.param("http://10.0.0.7:8080/v1", id="lan-10-8"),  # public-clean: allow
]


@pytest.mark.parametrize("host", METADATA_ENCODINGS)
def test_metadata_address_is_blocked_in_every_encoding(host: str) -> None:
    """Each spelling the resolver maps to 169.254.169.254 must be refused."""
    with pytest.raises(ValueError, match="link-local"):
        netutil.validate_base_url(f"http://{host}/v1")


@pytest.mark.parametrize("host", METADATA_ENCODINGS)
def test_metadata_encodings_really_do_resolve_to_metadata(host: str) -> None:
    """Positive control for the suite above.

    Without this, a typo'd fixture would make the block test pass vacuously —
    asserting that we refuse a host that never pointed anywhere dangerous. This
    proves each fixture IS the metadata address as far as the OS is concerned.
    """
    bare = host.strip("[]")
    assert socket.inet_ntoa(socket.inet_aton(bare)) == "169.254.169.254"


@pytest.mark.parametrize("host", NON_ROUTABLE)
def test_non_routable_hosts_are_blocked(host: str) -> None:
    with pytest.raises(ValueError):
        netutil.validate_base_url(f"http://{host}/v1")


@pytest.mark.parametrize("base", [
    "http://0.0.0.0:11434/v1",   # ollama serve --host 0.0.0.0
    "http://0.0.0.0:1234/v1",    # lmstudio
    "http://0.0.0.0:8000/v1",    # vllm --host 0.0.0.0
    "http://[::]:8000/v1",       # the IPv6 spelling of the same wildcard bind
])
def test_wildcard_bind_address_is_allowed(base: str) -> None:
    """RED on revert: `0.0.0.0`/`::` in a base_url is a bind-address copy-paste
    from a local provider's launch flags, not an attack. It denotes the local
    host, master accepted it, and rejecting it broke `charon providers add` for
    a common local config with a "non-routable host" message that never
    suggested 127.0.0.1. Still refused under allow_private=False (below), which
    is where "local host" is genuinely out of policy."""
    assert netutil.validate_base_url(base) == base.rstrip("/")


@pytest.mark.parametrize("base", ["http://0.0.0.0:11434/v1", "http://[::]:8000/v1"])
def test_wildcard_bind_address_is_refused_when_private_is_disallowed(base: str) -> None:
    """The wildcard bind address is local-host-class, so the strict policy that
    refuses loopback and RFC1918 must refuse it too — otherwise `0.0.0.0` would
    be a hole straight through `allow_private=False`."""
    with pytest.raises(ValueError, match="private/loopback"):
        netutil.validate_base_url(base, allow_private=False)


@pytest.mark.parametrize("host", ["metadata.google.internal", "metadata.goog",
                                  "METADATA.GOOGLE.INTERNAL", "metadata.google.internal."])
def test_metadata_hostnames_are_blocked(host: str) -> None:
    """Case and a trailing root dot are normalised away before the comparison."""
    with pytest.raises(ValueError, match="metadata"):
        netutil.validate_base_url(f"http://{host}/v1")


@pytest.mark.parametrize("base", LEGITIMATE)
def test_legitimate_bases_still_validate(base: str) -> None:
    """LAN/loopback bases are a shipped feature, not an oversight — 5 presets use them."""
    assert netutil.validate_base_url(base) == base.rstrip("/")


@pytest.mark.parametrize("base", [  # public-clean: allow — RFC1918 literals ARE the fixture
    "http://127.0.0.1:1234/v1", "http://192.168.1.50:8000/v1"])  # public-clean: allow
def test_allow_private_false_blocks_lan_for_callers_that_want_that(base: str) -> None:
    """The strict policy is available without being the default."""
    with pytest.raises(ValueError, match="private/loopback"):
        netutil.validate_base_url(base, allow_private=False)
    assert netutil.validate_base_url(base) == base  # default is unchanged


@pytest.mark.parametrize("host", [
    "0251.0376.0251.0376", "169.254.169.254", "2852039166", "0xA9FEA9FE", "169.16689662",
    "0250.0376.0251.0376", "0169.0254.0169.0254", "169.254.16689662", "8.8.8.8",
    "0xc0.0xa8.1.1", "127.1", "010.010.010.010", "1.2.3.4.5", "999.1.1.1",  # public-clean: allow
    "0x100000000", "192.168.000001.1", "", "0", "4294967295", "4294967296",  # public-clean: allow
    "1.0x2.03.4",
])
def test_parser_matches_inet_aton_exactly(host: str) -> None:
    """Differential test against the resolver the connection actually uses.

    Any disagreement is a bug in one of two directions: a host the resolver can
    reach but we cleared (a bypass), or a host we refuse that the resolver would
    reject anyway (a false positive). Both matter, so this asserts equality
    rather than one-way containment.
    """
    try:
        expected = socket.inet_ntoa(socket.inet_aton(host))
    except OSError:
        expected = None
    parsed = netutil._parse_permissive_ipv4(host)
    assert (str(parsed) if parsed is not None else None) == expected


def test_ipv4_mapped_ipv6_is_unwrapped_before_classification() -> None:
    """``::ffff:169.254.169.254`` reports is_link_local == False as an IPv6Address.

    IPv6 link-local means fe80::/10, so classifying the wrapper alone lets the
    mapped metadata address straight through. The guard must classify the
    EMBEDDED address in its own right.
    """
    import ipaddress
    assert ipaddress.ip_address("::ffff:169.254.169.254").is_link_local is False
    for spelling in ("[::ffff:169.254.169.254]", "[::ffff:a9fe:a9fe]"):
        with pytest.raises(ValueError, match="link-local"):
            netutil.validate_base_url(f"http://{spelling}/v1")


def test_ipv6_loopback_is_allowed() -> None:
    """``ipaddress.ip_address("::1").is_reserved`` is True.

    So a blanket is_reserved check blocks the IPv6 spelling of localhost, which
    is the base five shipped presets use. The guard must exempt loopback before
    the non-routable classes are considered.
    """
    import ipaddress
    assert ipaddress.ip_address("::1").is_reserved is True
    assert netutil.validate_base_url("http://[::1]:1234/v1") == "http://[::1]:1234/v1"


def test_non_http_scheme_still_refused() -> None:
    for bad in ("file:///etc/passwd", "gopher://x/", "ftp://x/"):
        with pytest.raises(ValueError, match="scheme"):
            netutil.validate_base_url(bad)
