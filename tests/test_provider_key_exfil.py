"""Provider-key exfiltration guard (SECURITY).

CONFIRMED vulnerability this locks down: a stored provider API key was sent to an
attacker-chosen ``base_url``. Root cause was the ``key_env`` INDIRECTION —
``key_env`` is a SHARED env-var NAME, so the setup handler validated the key the
caller SUPPLIED while every send site read ``os.environ[key_env]`` (the REAL
key), and ``secrets.apply_to_env`` uses ``setdefault`` so a freshly-stored key
never became the key actually sent.

INVARIANT under test: validation and every send site resolve THE SAME value —
the per-provider secret (``secrets.get_provider_key``). ``key_env`` survives only
as a read-only fallback bound to the base its built-in preset declares, so there
is no shared namespace left to alias into.

Every exploit test here OBSERVES THE ATTACKER SOCKET: the assertion is that the
attacker host never received the real key, not merely that a status code was 400.
"""
from __future__ import annotations

import http.server
import json
import threading

import pytest

from charon import balance, config, discover, gateway, providers, secrets
from charon.gateway import GatewayConfig

REAL_KEY = "sk-REAL-secret"
VICTIM_ENV = "VIC_KEY"

# --------------------------------------------------------------------------- helpers


class _Recording(http.server.BaseHTTPRequestHandler):
    """A stand-in provider recording the Authorization header of every request.
    Serves both ``/models`` and ``/chat/completions`` so one recorder covers the
    catalog sinks and the proxy forward path."""

    def log_message(self, *a):  # quiet
        pass

    def _record_and_reply(self, body: bytes):
        srv = self.server
        srv.seen_auth = self.headers.get("Authorization")  # type: ignore[attr-defined]
        srv.seen_auths.append(srv.seen_auth)  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._record_and_reply(
            json.dumps({"data": [{"id": "m1"}, {"id": "m2:free"}]}).encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self._record_and_reply(json.dumps({
            "id": "c1", "object": "chat.completion", "model": "m1",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "balance": 5.0, "data": {"credits": 5.0},
        }).encode())


class _Redirector(http.server.BaseHTTPRequestHandler):
    """Answers every request with a 302 to ``self.server.target`` — the redirect
    hazard: urllib does NOT strip Authorization cross-host."""

    def log_message(self, *a):
        pass

    def _redirect(self):
        srv = self.server
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        # Recorded so a test can prove the key really was in flight — otherwise
        # "the attacker saw nothing" is also true of a request that never carried
        # a key, and the assertion would be vacuous.
        srv.seen_auths.append(self.headers.get("Authorization"))  # type: ignore[attr-defined]
        self.send_response(302)
        self.send_header("Location", self.server.target)  # type: ignore[attr-defined]
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_GET = do_POST = _redirect


def _start(handler=_Recording, **attrs):
    srv = http.server.HTTPServer(("127.0.0.1", 0), handler)
    srv.seen_auth = None  # type: ignore[attr-defined]
    srv.seen_auths = []  # type: ignore[attr-defined]
    for k, v in attrs.items():
        setattr(srv, k, v)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _base(srv) -> str:
    return f"http://127.0.0.1:{srv.server_address[1]}/v1"


def _origin(srv) -> str:
    return f"http://127.0.0.1:{srv.server_address[1]}"


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


def _assert_no_real_key(srv, where: str):
    """The load-bearing assertion: the attacker host never saw the victim's key."""
    seen = getattr(srv, "seen_auths", [])
    assert f"Bearer {REAL_KEY}" not in seen, \
        f"KEY EXFILTRATED via {where}: attacker received {seen!r}"


@pytest.fixture
def victim_install(monkeypatch, tmp_path):
    """An EXISTING install as the docs describe it: the real key present under a
    shared ``key_env`` in ``os.environ`` (a ``.env``-injected deployment) AND in
    the legacy ``{key_env: value}`` secrets file. This is the state that made the
    old ``setdefault`` indirection exploitable — the exploits below all run
    against it."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.setenv(VICTIM_ENV, REAL_KEY)
    secrets.set_secret(VICTIM_ENV, REAL_KEY)
    return tmp_path


def _serve(tmp_path):
    server = gateway.build_server(
        GatewayConfig(host="127.0.0.1", port=0, token="t", model_ids=[]),
        setup_dir=tmp_path)
    server.serve_in_thread()
    return server


def _add_victim(server, legit) -> None:
    """Register the legit provider with its real key, through the web handler."""
    st, body = _req(server.url + "/charon/providers", "POST", token="t", body={
        "name": "vic", "base_url": _base(legit), "key_env": VICTIM_ENV, "key": REAL_KEY})
    assert st == 200, body
    legit.seen_auth = None
    legit.seen_auths.clear()


# ------------------------------------------------- the exploit, both variants


def test_new_provider_aliasing_victim_key_env_with_own_key_leaks_nothing(victim_install):
    """THE bypass the previous fix missed: the attacker SUPPLIES a key, so any
    ``if key_env and not key`` guard is skipped entirely. The supplied key
    validates against the attacker's own host, then ``models/import`` used to read
    ``os.environ[VIC_KEY]`` — the REAL key — and ship it to the attacker."""
    legit, attacker = _start(), _start()
    server = _serve(victim_install)
    try:
        _add_victim(server, legit)
        st, body = _req(server.url + "/charon/providers", "POST", token="t", body={
            "name": "evil", "base_url": _base(attacker),
            "key_env": VICTIM_ENV, "key": "sk-attacker-own"})
        assert st == 200, body  # binding your OWN key to your OWN host is allowed
        _req(server.url + "/charon/models/import", "POST", token="t",
             body={"provider": "evil"})
        _assert_no_real_key(attacker, "models/import (aliasing + own key)")
        # …and the caller-supplied key_env was never persisted as a binding.
        assert config.load_providers()["evil"].get("key_env") is None
    finally:
        server.shutdown(), legit.shutdown(), attacker.shutdown()


def test_new_provider_aliasing_victim_key_env_without_key_leaks_nothing(victim_install):
    """The no-key variant of the same aliasing attack."""
    legit, attacker = _start(), _start()
    server = _serve(victim_install)
    try:
        _add_victim(server, legit)
        _req(server.url + "/charon/providers", "POST", token="t", body={
            "name": "evil", "base_url": _base(attacker), "key_env": VICTIM_ENV})
        _req(server.url + "/charon/models/import", "POST", token="t",
             body={"provider": "evil"})
        _assert_no_real_key(attacker, "models/import (aliasing, no key)")
    finally:
        server.shutdown(), legit.shutdown(), attacker.shutdown()


def test_repoint_existing_provider_base_url_leaks_nothing(victim_install):
    """The repoint variant: move a provider that ALREADY has a stored key onto an
    attacker base. Without a fresh key this is refused outright; the import that
    follows must still reach only the unchanged legit base."""
    legit, attacker = _start(), _start()
    server = _serve(victim_install)
    try:
        _add_victim(server, legit)
        st, body = _req(server.url + "/charon/providers", "POST", token="t", body={
            "name": "vic", "base_url": _base(attacker)})
        assert st == 400, f"repoint-without-key must be refused, got {st}: {body}"
        assert config.load_providers()["vic"]["base_url"] == _base(legit)
        st, body = _req(server.url + "/charon/models/import", "POST", token="t",
                        body={"provider": "vic"})
        assert st == 200, body
        _assert_no_real_key(attacker, "models/import (repoint)")
        assert legit.seen_auth == f"Bearer {REAL_KEY}"  # positive control
    finally:
        server.shutdown(), legit.shutdown(), attacker.shutdown()


def test_repoint_with_attacker_key_sends_only_that_key(victim_install):
    """Repointing WITH a fresh validating key is legitimate operator re-consent —
    but the key that then rides upstream must be the newly supplied one, never the
    victim's. (The old code stored the new key in the file while `setdefault` kept
    the REAL one in the env, so the real one was what got sent.)"""
    legit, attacker = _start(), _start()
    server = _serve(victim_install)
    try:
        _add_victim(server, legit)
        st, body = _req(server.url + "/charon/providers", "POST", token="t", body={
            "name": "vic", "base_url": _base(attacker), "key": "sk-attacker-own"})
        assert st == 200, body
        _req(server.url + "/charon/models/import", "POST", token="t",
             body={"provider": "vic"})
        _assert_no_real_key(attacker, "models/import (repoint with own key)")
        assert attacker.seen_auth == "Bearer sk-attacker-own"
    finally:
        server.shutdown(), legit.shutdown(), attacker.shutdown()


# ------------------------------------------------------------- one test per sink
# Once a malicious entry is persisted, these fire with NO further attacker action.


def _plant_evil(victim_install, legit, attacker):
    """Run the exploit write, then hand back a live gateway. Shared by the sink
    tests so each one exercises a DIFFERENT read site against the same setup."""
    server = _serve(victim_install)
    _add_victim(server, legit)
    st, body = _req(server.url + "/charon/providers", "POST", token="t", body={
        "name": "evil", "base_url": _base(attacker),
        "key_env": VICTIM_ENV, "key": "sk-attacker-own"})
    assert st == 200, body
    return server


def test_sink_discover_sends_no_victim_key(victim_install):
    """``discover.discover_models`` iterates PERSISTED-ONLY providers and fires on
    any discovery run — no attacker action needed."""
    legit, attacker = _start(), _start()
    server = _plant_evil(victim_install, legit, attacker)
    try:
        discover.discover_models(config_dir=victim_install)
        _assert_no_real_key(attacker, "discover.discover_models")
    finally:
        server.shutdown(), legit.shutdown(), attacker.shutdown()


def test_sink_catalog_refresh_sends_no_victim_key(victim_install):
    from charon.routing_policy import catalog_refresh

    legit, attacker = _start(), _start()
    server = _plant_evil(victim_install, legit, attacker)
    try:
        catalog_refresh._default_list_models("evil", config.load_providers()["evil"])
        _assert_no_real_key(attacker, "catalog_refresh._default_list_models")
    finally:
        server.shutdown(), legit.shutdown(), attacker.shutdown()


def test_sink_recommend_sends_no_victim_key(victim_install):
    from charon import recommend

    legit, attacker = _start(), _start()
    server = _plant_evil(victim_install, legit, attacker)
    try:
        config.add_model("evil-model", provider="evil", upstream_model="m1")
        for _mid, base, key in recommend._find_trusted_models(victim_install):
            assert not (base.startswith(_origin(attacker)) and key == REAL_KEY), \
                "KEY EXFILTRATED via recommend._find_trusted_models"
    finally:
        server.shutdown(), legit.shutdown(), attacker.shutdown()


def test_sink_forwarder_sends_no_victim_key_on_every_completion(victim_install):
    """The worst sink: ``routing_policy`` builds the upstream route for EVERY
    proxied completion, so a mis-bound key leaks on ordinary traffic."""
    legit, attacker = _start(), _start()
    server = _plant_evil(victim_install, legit, attacker)
    try:
        st, body = _req(server.url + "/charon/models", "POST", token="t", body={
            "id": "evil-model", "provider": "evil", "upstream_model": "m1"})
        assert st == 200, body
        _req(server.url + "/v1/chat/completions", "POST", token="t", body={
            "model": "evil-model", "messages": [{"role": "user", "content": "hi"}]})
        _assert_no_real_key(attacker, "forwarder (proxied completion)")
    finally:
        server.shutdown(), legit.shutdown(), attacker.shutdown()


def test_sink_balance_poller_sends_no_victim_key_off_host(victim_install, monkeypatch):
    """``balance_base_url``/``balance_key_env`` were persisted with NO validation
    at all — a second key<->base indirection. A balance endpoint on a host other
    than the provider's own must get no key."""
    legit, attacker = _start(), _start()
    try:
        tracker = balance.BalanceTracker(config={"vic": {
            "mode": "poll", "funding_class": 3,
            "base_url": _base(legit),
            "balance_base_url": _origin(attacker),
            "balance_key_env": VICTIM_ENV,
        }})
        monkeypatch.setitem(balance._POLL_ADAPTERS, "vic", balance._poll_nanogpt)
        tracker.remaining("vic")
        _assert_no_real_key(attacker, "balance poll (off-host balance_base_url)")
    finally:
        legit.shutdown(), attacker.shutdown()


class _RedirectAfterTransient(http.server.BaseHTTPRequestHandler):
    """First request → a bare ``503`` (the transient status the forwarder retries
    ONCE, ``forwarder.py`` RETRY-ONCE), every request after → a 302 at the
    attacker. Exercises the retry leg specifically: it is a SECOND key-bearing
    send, and round 4 left both legs following redirects."""

    def log_message(self, *a):
        pass

    def _reply(self):
        srv = self.server
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        srv.hits.append(self.headers.get("Authorization"))  # type: ignore[attr-defined]
        if len(srv.hits) == 1:  # type: ignore[attr-defined]
            body = b'{"error":{"message":"service unavailable"}}'
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(302)
        self.send_header("Location", self.server.target)  # type: ignore[attr-defined]
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_GET = do_POST = _reply


def test_forwarder_does_not_follow_redirect_to_attacker(victim_install):
    """F1 — the round-4 miss, and the highest-volume key-bearing send there is.

    ``_build_upstream_req`` attaches ``Authorization: Bearer <provider key>`` and
    the two sends used bare ``urllib.request.urlopen``, whose default
    ``HTTPRedirectHandler`` re-sends that header to the redirect target — urllib
    does NOT strip Authorization cross-host. A hijacked/lapsed/attacker-operated
    upstream answering 302 therefore harvested the operator's real provider key on
    EVERY proxied completion. No local access required.

    The provider here is entirely legitimate — its own base, its own real key — so
    nothing is mis-bound: the leak is purely the redirect. Both legs are covered,
    the first attempt and the RETRY-ONCE leg.
    """
    attacker = _start()
    redirector = _start(_Redirector, target=f"{_origin(attacker)}/v1/chat/completions")
    # Registered directly, as an operator install is: the setup handler's own key
    # probe refuses a redirecting base (a 302 fails validation), so going through
    # it could not produce the state under test.
    config.add_provider("vic", base_url=_base(redirector))
    secrets.set_provider_key("vic", REAL_KEY, base_url=_base(redirector))
    server = _serve(victim_install)
    try:
        # The model goes in through the handler so it lands in the LIVE routing
        # table (the provider could not: the setup probe refuses a redirecting base).
        st, body = _req(server.url + "/charon/models", "POST", token="t", body={
            "id": "vic-model", "provider": "vic", "upstream_model": "m1"})
        assert st == 200, body

        _req(server.url + "/v1/chat/completions", "POST", token="t", body={
            "model": "vic-model", "messages": [{"role": "user", "content": "hi"}]})

        # Positive control: the key really was on the wire to the (legit) upstream,
        # so this test would notice if the route silently stopped sending one.
        assert f"Bearer {REAL_KEY}" in redirector.seen_auths, \
            "route sent no key at all — the redirect assertion below is vacuous"
        _assert_no_real_key(attacker, "forwarder (302 off a proxied completion)")
    finally:
        server.shutdown(), redirector.shutdown(), attacker.shutdown()


def test_forwarder_retry_leg_does_not_follow_redirect_to_attacker(victim_install):
    """The same hazard on the RETRY-ONCE leg (``forwarder.py`` retries a transient
    503 against the SAME provider): a second key-bearing send, and a second bite at
    the key if it follows redirects."""
    attacker = _start()
    upstream = _start(_RedirectAfterTransient,
                      target=f"{_origin(attacker)}/v1/chat/completions")
    upstream.hits = []  # type: ignore[attr-defined]
    config.add_provider("vic", base_url=_base(upstream))
    secrets.set_provider_key("vic", REAL_KEY, base_url=_base(upstream))
    server = _serve(victim_install)
    try:
        # The model goes in through the handler so it lands in the LIVE routing
        # table (the provider could not: the setup probe refuses a redirecting base).
        st, body = _req(server.url + "/charon/models", "POST", token="t", body={
            "id": "vic-model", "provider": "vic", "upstream_model": "m1"})
        assert st == 200, body

        _req(server.url + "/v1/chat/completions", "POST", token="t", body={
            "model": "vic-model", "messages": [{"role": "user", "content": "hi"}]})

        # The retry leg must actually have run, or the redirect below was never
        # reached and the assertion proves nothing.
        assert len(upstream.hits) >= 2, \
            f"retry leg never fired (hits={upstream.hits!r}) — assertion is vacuous"
        assert f"Bearer {REAL_KEY}" in upstream.hits, "retry sent no key at all"
        _assert_no_real_key(attacker, "forwarder RETRY-ONCE leg (302 on retry)")
    finally:
        server.shutdown(), upstream.shutdown(), attacker.shutdown()


def test_balance_poll_does_not_follow_redirect_to_attacker(victim_install):
    """A key-bearing request must NOT follow a 302: urllib does not strip
    Authorization cross-host, so a redirecting balance endpoint would otherwise
    hand the real key to wherever it points."""
    attacker = _start()
    redirector = _start(_Redirector, target=f"{_origin(attacker)}/api/check-balance")
    try:
        for poll in (balance._poll_nanogpt, balance._poll_deepseek,
                     balance._poll_openrouter):
            poll(_origin(redirector), REAL_KEY, 5.0)
        assert attacker.seen_auths == [], \
            f"KEY EXFILTRATED via redirect: attacker received {attacker.seen_auths!r}"
    finally:
        redirector.shutdown(), attacker.shutdown()


# ------------------------------------------------------- credential destruction


def test_setup_handler_cannot_overwrite_another_providers_stored_key(victim_install):
    """DoS corollary: the same call used to write ``set_secret(key_env, key)``, so
    an unauthenticated-to-the-key caller could DESTROY any stored provider key by
    naming its ``key_env``. Writes are now namespaced per provider."""
    legit, attacker = _start(), _start()
    server = _serve(victim_install)
    try:
        _add_victim(server, legit)
        st, _ = _req(server.url + "/charon/providers", "POST", token="t", body={
            "name": "evil", "base_url": _base(attacker),
            "key_env": VICTIM_ENV, "key": "sk-attacker-own"})
        assert st == 200
        secs = secrets.load_secrets()
        assert secs[VICTIM_ENV] == REAL_KEY, "the legacy key_env secret was clobbered"
        assert secs["provider:vic"] == REAL_KEY, "the victim's provider key was clobbered"
        assert secs["provider:evil"] == "sk-attacker-own"
    finally:
        server.shutdown(), legit.shutdown(), attacker.shutdown()


def test_skip_probe_cannot_overwrite_a_providers_own_stored_key(victim_install):
    """The SAME-provider half of the destruction attack, which the cross-provider
    test above does not reach. ``skip_probe`` is read straight off the request
    payload and short-circuits validation to ``valid=True`` with no HTTP call, so a
    single POST used to replace the operator's real key with junk. An unprobed
    write may ESTABLISH a key, never REPLACE one."""
    legit = _start()
    server = _serve(victim_install)
    try:
        _add_victim(server, legit)
        st, body = _req(server.url + "/charon/providers", "POST", token="t", body={
            "name": "vic", "key": "junk", "skip_probe": True})
        assert st == 400, body
        assert secrets.load_secrets()["provider:vic"] == REAL_KEY, \
            "the provider's own stored key was destroyed via skip_probe"
    finally:
        server.shutdown(), legit.shutdown()


def test_skip_probe_cannot_repoint_a_provider_onto_an_attacker_base(victim_install):
    """``skip_probe`` also bypassed the repoint guard entirely: the guard sat in an
    ``elif`` reached only when NO key was supplied, and a supplied key + skipped
    probe counted as validation. That persisted an attacker base AND overwrote the
    key in one unauthenticated-to-the-key call."""
    legit, attacker = _start(), _start()
    server = _serve(victim_install)
    try:
        _add_victim(server, legit)
        st, body = _req(server.url + "/charon/providers", "POST", token="t", body={
            "name": "vic", "base_url": _base(attacker),
            "key": "junk", "skip_probe": True})
        assert st == 400, body
        assert secrets.same_base(
            providers.resolve("vic", config.load_providers().get("vic")).base_url,
            _base(legit)), "the attacker base was persisted"
        _req(server.url + "/charon/models/import", "POST", token="t",
             body={"provider": "vic"})
        _assert_no_real_key(attacker, "skip_probe repoint")
    finally:
        server.shutdown(), legit.shutdown(), attacker.shutdown()


def test_skip_probe_can_still_establish_a_first_key(monkeypatch, tmp_path):
    """The escape hatch itself survives: onboarding a token-gated provider whose
    key cannot be probed pre-activation still works. Only REPLACING an existing key
    and REPOINTING a base are refused."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    legit = _start()
    server = _serve(tmp_path)
    try:
        st, body = _req(server.url + "/charon/providers", "POST", token="t", body={
            "name": "vic", "base_url": _base(legit),
            "key": "sk-unprobed", "skip_probe": True})
        assert st == 200, body
        assert secrets.load_secrets()["provider:vic"] == "sk-unprobed"
    finally:
        server.shutdown(), legit.shutdown()


def test_stored_provider_key_is_bound_to_its_base(monkeypatch, tmp_path):
    """F3 — the per-provider store is base-bound too, not just the legacy fallback.

    Step 1 of the resolver used to return the stored key for ANY ``base_url`` the
    caller passed, and its only compensating control was one ``elif`` in one HTTP
    handler. Any overlooked write path to ``providers.json[name]["base_url"]`` was
    therefore an immediate full key exfil with no second line of defence."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    secrets.set_provider_key("vic", REAL_KEY, base_url="https://legit.example/v1")
    assert secrets.get_provider_key(
        "vic", base_url="https://legit.example/v1") == REAL_KEY
    # A different PATH on the bound host is the same credential scope.
    assert secrets.get_provider_key(
        "vic", base_url="https://legit.example/v2/beta") == REAL_KEY
    # A different HOST is not — this is the exfil direction.
    assert secrets.get_provider_key("vic", base_url="https://attacker.example/v1") is None
    # An entry with no recorded binding fails CLOSED (set_provider_key cannot
    # create one, so this only arises from a hand-edited/foreign secrets file).
    secrets.set_secret("STRAY", "x")  # force a rewrite that keeps provider:orphan out
    secrets._write_secret("provider:orphan", REAL_KEY)
    assert secrets.get_provider_key("orphan", base_url="https://anywhere.example/v1") is None


def test_provider_key_cannot_be_stored_unbound(monkeypatch, tmp_path):
    """The binding is mandatory — that is what lets the resolver fail closed on a
    missing one rather than having to fall open for compatibility."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    for bad in (None, "", "not-a-url", "file:///etc/passwd"):
        with pytest.raises(ValueError):
            secrets.set_provider_key("vic", REAL_KEY, base_url=bad)


def test_malformed_port_in_a_base_never_raises(monkeypatch, tmp_path):
    """F5 — ``parts.port`` sat outside the ``try``, and ``parts.port`` (not
    ``urlsplit``) is what raises. ``_validate_base_url`` accepts these URLs because
    it only reads ``.hostname``, so they are persistable: the uncaught ValueError
    surfaced as a remote 500 and could stop the gateway starting outright."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    for bad in ("https://h:99999/v1", "https://h:abc/v1", "https://h:-1/v1"):
        assert secrets._normalize_base(bad) is None
        assert secrets.same_base(bad, bad) is False
        assert secrets.same_host(bad, bad) is False
        assert secrets.get_provider_key("vic", key_env=VICTIM_ENV, base_url=bad) is None
        assert secrets._env_fallback_allowed("OPENROUTER_API_KEY", bad) is False


def test_unicode_host_folds_the_way_the_socket_folds_it():
    """A near-miss fixed as a class: ``U+212A`` KELVIN SIGN lower-cases to ``k``, so
    ``api.deepseeK.com`` compared EQUAL to the preset host under ``str.lower()``.
    That was harmless only because IDNA nameprep happens to fold it identically —
    luck, not design, since the check used ``str.lower()`` while the socket uses
    IDNA. Both sides now go through IDNA, so agreement is by construction."""
    kelvin = "https://api.deepseeK.com/v1"
    assert secrets._normalize_base(kelvin) == secrets._normalize_base(
        "https://api.deepseek.com/v1")
    assert "K" not in (secrets._normalize_base(kelvin) or "")
    # A genuinely different host still does not match.
    assert not secrets.same_host("https://api.deepseek.com.evil.example/v1",
                                 "https://api.deepseek.com/v1")


def test_provider_id_charset_matches_the_config_store(monkeypatch, tmp_path):
    """F6 — ``set_provider_key`` was stricter than ``config.add_provider``, so an id
    containing ``/`` or ``:`` could be persisted as a provider but could never hold
    a key, and any code path storing one raised mid-write."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    from charon.config import _store
    for pid in ("a/b", "a:b", "a.b", "A-B", "9x", "my_prov"):
        _store._check_id("provider", pid)          # accepted by the config store …
        secrets._check_provider_id(pid)            # … so it must be accepted here
    for bad in ("", "_weird", "/x"):
        with pytest.raises(ValueError):
            secrets._check_provider_id(bad)


def test_direct_upstream_base_entry_still_resolves_its_key(monkeypatch, tmp_path):
    """A legacy direct-model entry (``upstream_base`` + ``key_env``, no provider id)
    must keep resolving. Binding at full-path granularity meant a base differing
    from the preset by one segment silently sent NO key — a hard 401 with no
    failover and no recovery path, since a direct entry can never hold a
    per-provider key."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    preset = providers.PRESETS["openrouter"]
    monkeypatch.setenv(preset.key_env, "sk-real")
    for base in ("https://openrouter.ai/api/v1", "https://openrouter.ai/api/v1/",
                 "https://openrouter.ai/api", "https://openrouter.ai/api/v1/beta"):
        assert secrets.get_provider_key(
            None, key_env=preset.key_env, base_url=base) == "sk-real", base
    # …but a different host is still refused.
    assert secrets.get_provider_key(
        None, key_env=preset.key_env, base_url="https://openrouter.ai.evil.example/v1") is None


def test_models_import_all_sees_per_provider_keys(monkeypatch, tmp_path, capsys):
    """HIGH-3 — an unconverted sink gated on ``preset.key_env in os.environ`` while
    every onboarding path now writes only ``provider:<id>``, which ``apply_to_env``
    deliberately cannot export. Every provider was skipped silently: a fresh install
    running ``models import --all`` got "0 model(s) from 0 provider(s)"."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    preset = providers.PRESETS["openrouter"]
    monkeypatch.delenv(preset.key_env, raising=False)
    config.add_provider("openrouter")
    secrets.set_provider_key("openrouter", "sk-xyz", base_url=preset.base_url)
    from charon import cli
    seen: list[str] = []
    monkeypatch.setattr(cli, "_import_models",
                        lambda name, **k: seen.append(name) or ([], []))
    cli._import_all_models(quiet=True)
    assert "openrouter" in seen, "import --all skipped a provider that HAS a key"


# ---------------------------------------------------------------- the resolver


def test_env_fallback_is_bound_to_the_presets_base(monkeypatch, tmp_path):
    """The legacy fallback only fires at a base the preset binds that key_env to."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", REAL_KEY)
    preset = providers.PRESETS["openrouter"]
    assert secrets.get_provider_key(
        "openrouter", key_env=preset.key_env, base_url=preset.base_url) == REAL_KEY
    assert secrets.get_provider_key(
        "evil", key_env=preset.key_env, base_url="https://attacker.example/v1") is None
    # …and port/case/trailing-dot variants of the vetted base are not a way around it.
    for variant in ("https://OpenRouter.ai/api/v1", "https://openrouter.ai:443/api/v1"):
        assert secrets.get_provider_key(
            "openrouter", key_env=preset.key_env, base_url=variant) == REAL_KEY


def test_shared_key_env_preset_pair_still_resolves(monkeypatch, tmp_path):
    """``opencode-zen``/``opencode-go`` legitimately share one key_env across two
    bases — the binding check must accept EITHER, or the shipped pair breaks."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    zen, go = providers.PRESETS["opencode-zen"], providers.PRESETS["opencode-go"]
    assert zen.key_env == go.key_env
    monkeypatch.setenv(zen.key_env, REAL_KEY)
    for name, p in (("opencode-zen", zen), ("opencode-go", go)):
        assert secrets.get_provider_key(
            name, key_env=p.key_env, base_url=p.base_url) == REAL_KEY


def test_per_provider_secret_wins_over_a_stale_env_var(monkeypatch, tmp_path):
    """The root cause was ``apply_to_env``'s ``setdefault``: a freshly stored key
    never became the key sent. The per-provider secret is now authoritative."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    preset = providers.PRESETS["openrouter"]
    monkeypatch.setenv(preset.key_env, "sk-stale-env")
    secrets.set_provider_key("openrouter", "sk-fresh", base_url=preset.base_url)
    secrets.apply_to_env()
    assert secrets.get_provider_key(
        "openrouter", key_env=preset.key_env, base_url=preset.base_url) == "sk-fresh"


# ------------------------------------------------------------------ legit paths


def test_legit_add_import_and_completion_still_work(monkeypatch, tmp_path):
    """No over-blocking: the ordinary flow — add a provider with a key, import its
    catalog, proxy a completion — still reaches the provider WITH the key."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    legit = _start()
    server = _serve(tmp_path)
    try:
        st, body = _req(server.url + "/charon/providers", "POST", token="t", body={
            "name": "good", "base_url": _base(legit), "key": "sk-good"})
        assert st == 200, body
        st, body = _req(server.url + "/charon/models/import", "POST", token="t",
                        body={"provider": "good"})
        assert st == 200, body
        assert legit.seen_auth == "Bearer sk-good"
        st, body = _req(server.url + "/charon/models", "POST", token="t", body={
            "id": "m1", "provider": "good", "upstream_model": "m1"})
        assert st == 200, body
        st, body = _req(server.url + "/v1/chat/completions", "POST", token="t", body={
            "model": "m1", "messages": [{"role": "user", "content": "hi"}]})
        assert st == 200, body
        assert legit.seen_auth == "Bearer sk-good"
    finally:
        server.shutdown(), legit.shutdown()


def test_existing_install_key_env_fallback_still_resolves(monkeypatch, tmp_path):
    """Back-compat: an install written by an older version (providers.json with a
    ``key_env``, secrets.json keyed by that name, or the var injected via ``.env``)
    keeps resolving through the base-bound legacy fallback."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    preset = providers.PRESETS["openrouter"]
    config.add_provider("openrouter", key_env=preset.key_env)
    secrets.set_secret(preset.key_env, REAL_KEY)
    monkeypatch.delenv(preset.key_env, raising=False)
    assert secrets.get_provider_key(
        "openrouter", key_env=preset.key_env, base_url=preset.base_url) == REAL_KEY


def test_env_key_rotation_takes_effect(monkeypatch, tmp_path):
    """A ``.env`` key must stay ROTATABLE. An earlier revision snapshotted
    ``os.environ[key_env]`` into ``provider:<id>`` at gateway start, and that entry
    outranks the env var — so an operator who rotated a revoked key kept presenting
    the OLD one, every request 401'd (a 401 is returned as-is, never failed over),
    and nothing in the log explained it. Only deleting an entry out of secrets.json
    on the volume recovered it."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    preset = providers.PRESETS["openrouter"]
    config.add_provider("openrouter", key_env=preset.key_env)
    monkeypatch.setenv(preset.key_env, "sk-OLD")
    assert secrets.get_provider_key(
        "openrouter", key_env=preset.key_env, base_url=preset.base_url) == "sk-OLD"
    monkeypatch.setenv(preset.key_env, "sk-NEW")  # operator edits .env, restarts
    assert secrets.get_provider_key(
        "openrouter", key_env=preset.key_env, base_url=preset.base_url) == "sk-NEW"


def test_gateway_start_writes_nothing_to_the_config_dir(monkeypatch, tmp_path):
    """Gateway start must stay READ-ONLY on the config dir. It briefly promoted
    legacy secrets on startup, which turned a normal hardening choice (mounting the
    config volume ``:ro``) — or a full disk — into a crash-loop instead of a
    serving container, and persisted env-only keys to disk unasked."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.setenv(providers.PRESETS["openrouter"].key_env, "sk-env-only")

    def _explode(*a, **k):
        raise AssertionError("gateway start wrote to the secrets file")

    monkeypatch.setattr(secrets, "_write_secret", _explode)
    from charon import cli
    cli._warn_unsendable_keys()
    secrets.apply_to_env()
    assert not (tmp_path / "secrets.json").exists()


def test_balance_poll_keeps_working_for_a_same_host_balance_endpoint(victim_install):
    """The balance guard is host-scoped, not path-scoped: a provider's balance API
    on its own host (a different PATH) must still get the key."""
    legit = _start()
    try:
        secrets.set_provider_key("vic", REAL_KEY, base_url=_base(legit))
        tracker = balance.BalanceTracker(config={"vic": {
            "mode": "poll", "funding_class": 3,
            "base_url": _base(legit),
            "balance_base_url": _origin(legit),
            "balance_key_env": VICTIM_ENV,
        }})
        assert tracker._config["vic"]["api_key"] == REAL_KEY
    finally:
        legit.shutdown()


def test_balance_and_model_bases_are_validated(monkeypatch, tmp_path):
    """Both second-indirection write paths get the same SSRF/base guard ``base_url``
    already had — they used to get none at all."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    for bad in ("file:///etc/passwd", "http://169.254.169.254/latest"):
        with pytest.raises(ValueError):
            config.add_provider("p", mode="poll", balance_base_url=bad)
        with pytest.raises(ValueError):
            config.add_model("m", upstream_base=bad)
    with pytest.raises(ValueError):
        config.add_provider("p", mode="poll", balance_key_env="BAD=NAME")


def test_warn_unsendable_keys_covers_model_entries_not_just_providers(
        monkeypatch, tmp_path, capsys):
    """docs/docker.md promises a startup WARNING for a model entry carrying its own
    ``upstream_base`` + ``key_env`` pointing at a host no preset claims.

    ``_warn_unsendable_keys`` iterated providers ONLY, so models.json was never
    visited and that documented case produced no warning at all — the operator
    follows the doc, sees nothing, and the model 401s silently in production.
    """
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    # A key_env a PRESET claims, on a base that preset does not bind. An
    # UNCLAIMED key_env is deliberately sendable to any base (see
    # secrets._env_fallback_allowed), so it is specifically the claimed-env /
    # foreign-base combination that resolves to no key and hard-401s.
    preset = providers.PRESETS["openrouter"]
    monkeypatch.setenv(preset.key_env, "sk-present-but-unbound")
    config.add_model("direct-model", upstream_base="https://unclaimed.example.com/v1",
                     key_env=preset.key_env)

    from charon import cli
    cli._warn_unsendable_keys()

    err = capsys.readouterr().err
    assert "direct-model" in err, (
        "no WARNING for a model entry whose key cannot be sent — docs/docker.md "
        f"documents this case. stderr was: {err!r}")
    assert preset.key_env in err
    assert "sk-present-but-unbound" not in err, "the warning leaked the key value"
