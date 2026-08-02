# WCI-DEC-SRC-CHARON-PROXY-SERVER-PY — decomposition review

## Decision
Extracted two clean seams from `proxy_server.py`:
- **Session management** → `proxy_session.py` (seam C): `_SESSION_COOKIE`,
  `_SESSION_TTL`, `_GUI_ROUTES`, `_b64url`, `_b64url_decode`, `_sign_session`,
  `_verify_session`, `_resolve_session_key`, `_strip_token_from_path`
- **UpstreamRoute** → `proxy_routes.py` (seam F): the `UpstreamRoute` dataclass
  and its `label` property

## Rationale
These are the two remaining clearly separable concerns in the file after
seams A (console_assets), B (response), D+E (control-plane dispatch), and the
forwarder loop were already extracted. Session management has no dependency on
any class in proxy_server.py; UpstreamRoute depends only on `urlsplit` and
`WIRE_OPENAI`.

## Risk
None. The facade re-exports in `proxy_server.py` keep every existing import
site `from charon.proxy_server import ...` resolving unchanged. The extracted
code is verbatim — no behaviour delta.

## Verification
- `tests/test_proxy_session.py` — direct import, HMAC roundtrip, expiry, rejection
- `tests/test_proxy_routes.py` — direct import, construction, label safety
- Full gate: `pytest -q`, `ruff check`, `mypy src tests`, `check_boundary.py`,
  `check_version.py`
