
[W4] ATC-015  ATC-015 gateway import fix
  Goal  Move _invocation_name from cli.py to api.py (shared module) — removes CLI import from gateway
  Built moved _invocation_name to api.py, updated cli.py/connect.py/gateway.py imports
  Files src/charon/api.py src/charon/cli.py src/charon/connect.py src/charon/gateway.py
  Gate  964-pass ✓ ruff✓ mypy✓ boundary✓ version✓
