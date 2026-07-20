"""Provider-key exfiltration guard (SECURITY).

CONFIRMED vulnerability this locks down: repointing an existing provider's
``base_url`` while silently reusing its stored key let a caller redirect the real
provider key to an attacker host via a later keyed upstream call
(``/charon/models/import`` -> ``GET <attacker>/models`` with
``Authorization: Bearer <REAL KEY>``).

INVARIANT under test: a stored provider key must NEVER be sent to a ``base_url``
the operator has not vetted FOR THAT KEY. The fix couples key<->base_url: changing
base_url requires re-supplying/re-validating the key for the new base (HTTP path),
and the config store drops a stale key binding on a bare base_url repoint.

Reverting either half of the fix turns the exploit assertions RED.
"""
from __future__ import annotations

import http.server
import json
import threading

import pytest

from charon import config, gateway, providers, secrets
from charon.gateway import GatewayConfig

# --------------------------------------------------------------------------- helpers

class _RecordingModels(http.server.BaseHTTPRequestHandler):
    """A stand-in provider that records the Authorization header of every request
    (both the attacker host and a legit local provider use this)."""

    def log_message(self, *a):  # quiet
        pass

    def do_GET(self):
        self.server.seen_auth = self.headers.get("Authorization")  # type: ignore[attr-defined]
        body = json.dumps({"data": [{"id": "m1"}, {"id": "m2:free"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _start_server():
    srv = http.server.HTTPServer(("127.0.0.1", 0), _RecordingModels)
    srv.seen_auth = None  # type: ignore[attr-defined]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _req(url, method="GET", token=None, body=None):
    import urllib.error
    import urllib.request
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


# --------------------------------------------------------- exploit chain (HTTP surface)

def test_repoint_base_url_no_key_is_refused_and_leaks_no_key(monkeypatch, tmp_path):
    """The full exploit chain: register a provider (loopback = a legit LAN/self-hosted
    provider) with a real key, then try to repoint its base_url at an attacker host
    with NO key and trigger a keyed model-import. The repoint MUST be refused and the
    real key MUST NOT reach the attacker."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.delenv("VIC_KEY", raising=False)  # secrets.apply_to_env() uses setdefault
    legit = _start_server()
    attacker = _start_server()
    server = gateway.build_server(
        GatewayConfig(host="127.0.0.1", port=0, token="t", model_ids=[]),
        setup_dir=tmp_path)
    server.serve_in_thread()
    try:
        legit_base = f"http://127.0.0.1:{legit.server_address[1]}/v1"
        attacker_base = f"http://127.0.0.1:{attacker.server_address[1]}/v1"

        # Register a legit provider WITH its real key (probe hits legit -> 200 -> valid).
        st, body = _req(server.url + "/charon/providers", "POST", token="t", body={
            "name": "vic", "base_url": legit_base,
            "key_env": "VIC_KEY", "key": "sk-REAL-secret"})
        assert st == 200, body
        assert secrets.load_secrets().get("VIC_KEY") == "sk-REAL-secret"

        # Reset recorders so the exploit assertions are about the exploit only.
        legit.seen_auth = None
        attacker.seen_auth = None

        # EXPLOIT step 1 — repoint base_url at the attacker, no key. MUST be refused.
        st, body = _req(server.url + "/charon/providers", "POST", token="t", body={
            "name": "vic", "base_url": attacker_base})
        assert st == 400, f"repoint-without-key must be refused, got {st}: {body}"
        # The persisted base_url was NOT moved to the attacker.
        assert config.load_providers()["vic"]["base_url"] == legit_base

        # EXPLOIT step 2 — trigger the keyed import; it must go to the (unchanged)
        # legit base, never the attacker.
        st, body = _req(server.url + "/charon/models/import", "POST", token="t",
                        body={"provider": "vic"})
        assert st == 200, body
        assert attacker.seen_auth is None, \
            f"KEY EXFILTRATED: attacker received {attacker.seen_auth!r}"
        # Legit path still works: the key rode to the legit provider.
        assert legit.seen_auth == "Bearer sk-REAL-secret"
    finally:
        server.shutdown()
        legit.shutdown()
        attacker.shutdown()


def test_repoint_base_url_with_fresh_key_is_allowed(monkeypatch, tmp_path):
    """Legit reconfigure: moving a provider to a new base_url WITH a fresh key that
    validates against the new base is accepted (operator re-consent)."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.delenv("VIC_KEY", raising=False)  # secrets.apply_to_env() uses setdefault
    a = _start_server()
    b = _start_server()
    server = gateway.build_server(
        GatewayConfig(host="127.0.0.1", port=0, token="t", model_ids=[]),
        setup_dir=tmp_path)
    server.serve_in_thread()
    try:
        base_a = f"http://127.0.0.1:{a.server_address[1]}/v1"
        base_b = f"http://127.0.0.1:{b.server_address[1]}/v1"
        st, body = _req(server.url + "/charon/providers", "POST", token="t", body={
            "name": "vic", "base_url": base_a, "key_env": "VIC_KEY", "key": "sk-1"})
        assert st == 200, body
        # Repoint WITH a fresh key -> allowed, key re-validated against the new base.
        st, body = _req(server.url + "/charon/providers", "POST", token="t", body={
            "name": "vic", "base_url": base_b, "key_env": "VIC_KEY", "key": "sk-2"})
        assert st == 200, body
        assert config.load_providers()["vic"]["base_url"] == base_b
        assert secrets.load_secrets().get("VIC_KEY") == "sk-2"
    finally:
        server.shutdown()
        a.shutdown()
        b.shutdown()


def test_new_provider_aliasing_existing_key_is_refused_and_leaks_no_key(monkeypatch, tmp_path):
    """BYPASS regression: the guard is on the key<->base BINDING, not the provider
    name. Creating a NEW provider that aliases an EXISTING key_env onto an attacker
    base (no fresh key) must be refused, and the existing secret must never leak."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.delenv("VIC_KEY", raising=False)  # secrets.apply_to_env() uses setdefault
    legit = _start_server()
    attacker = _start_server()
    server = gateway.build_server(
        GatewayConfig(host="127.0.0.1", port=0, token="t", model_ids=[]),
        setup_dir=tmp_path)
    server.serve_in_thread()
    try:
        legit_base = f"http://127.0.0.1:{legit.server_address[1]}/v1"
        attacker_base = f"http://127.0.0.1:{attacker.server_address[1]}/v1"
        # Establish a legit provider + real key (secret VIC_KEY now exists).
        st, body = _req(server.url + "/charon/providers", "POST", token="t", body={
            "name": "vic", "base_url": legit_base,
            "key_env": "VIC_KEY", "key": "sk-REAL-secret"})
        assert st == 200, body
        legit.seen_auth = None
        attacker.seen_auth = None

        # EXPLOIT — a brand-NEW provider name aliasing VIC_KEY onto the attacker,
        # NO key. Must be refused (existing key not vetted for that base).
        st, body = _req(server.url + "/charon/providers", "POST", token="t", body={
            "name": "evil", "base_url": attacker_base, "key_env": "VIC_KEY"})
        assert st == 400, f"aliasing an existing key onto a new base must 400, got {st}: {body}"
        assert "evil" not in config.load_providers()

        # Even if the import is attempted, the attacker gets nothing.
        st, _ = _req(server.url + "/charon/models/import", "POST", token="t",
                     body={"provider": "evil"})
        assert attacker.seen_auth is None, \
            f"KEY EXFILTRATED via aliasing: attacker received {attacker.seen_auth!r}"
    finally:
        server.shutdown()
        legit.shutdown()
        attacker.shutdown()


def test_new_provider_with_fresh_key_is_allowed(monkeypatch, tmp_path):
    """Legit: a brand-new provider WITH a fresh key that validates against its base
    is accepted — the new-provider path must not over-block real usage."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.delenv("NEW_KEY", raising=False)
    legit = _start_server()
    server = gateway.build_server(
        GatewayConfig(host="127.0.0.1", port=0, token="t", model_ids=[]),
        setup_dir=tmp_path)
    server.serve_in_thread()
    try:
        legit_base = f"http://127.0.0.1:{legit.server_address[1]}/v1"
        st, body = _req(server.url + "/charon/providers", "POST", token="t", body={
            "name": "fresh", "base_url": legit_base,
            "key_env": "NEW_KEY", "key": "sk-fresh"})
        assert st == 200, body
        assert config.load_providers()["fresh"]["base_url"] == legit_base
        assert secrets.load_secrets().get("NEW_KEY") == "sk-fresh"
    finally:
        server.shutdown()
        legit.shutdown()


# ------------------------------------------------------ store-level coupling backstop

def test_store_drops_stale_key_on_bare_base_url_repoint(monkeypatch, tmp_path):
    """config.add_provider: repointing base_url without re-affirming key_env drops the
    stale binding (the merge that let ``{base_url: attacker}`` keep the old key_env)."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_provider("vic", base_url="http://127.0.0.1:9/v1", key_env="VIC_KEY")
    assert config.load_providers()["vic"]["key_env"] == "VIC_KEY"
    # Bare repoint, no key_env re-affirmed -> key binding cleared.
    config.add_provider("vic", base_url="http://127.0.0.1:8/v1")
    entry = config.load_providers()["vic"]
    assert entry["base_url"] == "http://127.0.0.1:8/v1"
    assert entry.get("key_env") is None, "stale key binding must be dropped on repoint"


def test_store_keeps_key_when_reaffirmed_on_repoint(monkeypatch, tmp_path):
    """Re-supplying key_env alongside the new base_url is a deliberate re-binding."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_provider("vic", base_url="http://127.0.0.1:9/v1", key_env="VIC_KEY")
    config.add_provider("vic", base_url="http://127.0.0.1:8/v1", key_env="VIC_KEY")
    assert config.load_providers()["vic"]["key_env"] == "VIC_KEY"


def test_store_drops_inherited_key_when_baseless_provider_gains_base(monkeypatch, tmp_path):
    """F2: a previously base-LESS provider that later gains a base_url without
    re-affirming key_env must not silently carry the inherited key onto that base."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_provider("vic", key_env="VIC_KEY")  # key_env, no base_url yet
    assert config.load_providers()["vic"].get("base_url") is None
    config.add_provider("vic", base_url="http://127.0.0.1:8/v1")  # base added, no key_env
    entry = config.load_providers()["vic"]
    assert entry["base_url"] == "http://127.0.0.1:8/v1"
    assert entry.get("key_env") is None, "inherited key must drop when a base is first set"


def test_store_keeps_key_on_unrelated_edit(monkeypatch, tmp_path):
    """Editing a quirk without changing base_url must NOT touch the key binding."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_provider("vic", base_url="http://127.0.0.1:9/v1", key_env="VIC_KEY")
    config.add_provider("vic", strip_v1=True)  # no base_url change
    entry = config.load_providers()["vic"]
    assert entry["key_env"] == "VIC_KEY" and entry["strip_v1"] is True


# --------------------------------------------------- metadata block, LAN still allowed

# Illustrative RFC1918 literals — this test EXISTS to prove private ranges are not
# blocked (real self-hosted providers live there), so the addresses are intentional.
@pytest.mark.parametrize("lan", [
    "http://10.0.0.5:11434/v1",       # self-hosted Ollama on a private LAN  # public-clean: allow
    "http://192.168.1.9/v1",  # public-clean: allow
    "http://127.0.0.1:8080/v1",       # loopback
    "http://172.16.0.4/v1",  # public-clean: allow
])
def test_lan_and_loopback_bases_allowed(lan):
    """The fix must NOT blanket-block private/RFC1918 ranges — real usage."""
    assert providers.validate_base_url(lan) == lan.rstrip("/")


@pytest.mark.parametrize("meta", [
    "http://169.254.169.254/latest/meta-data/",  # AWS/GCP/Azure IMDSv4 link-local
    "http://[fd00:ec2::254]/v1",                 # AWS IMDSv6
    "http://metadata.google.internal/v1",        # GCP
])
def test_cloud_metadata_hosts_refused(meta):
    with pytest.raises(ValueError):
        providers.validate_base_url(meta)
    from charon.config._store import _validate_base_url
    with pytest.raises(ValueError):
        _validate_base_url(meta)
