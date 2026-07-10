
[W4] ATC  ATC adversarial audit fixes
  Goal  10 findings from ATC audit across cli/connect/secrets/gitleaks/intake/recommend
  Built body-drop, token-mask, blocklist, gitleaks-tighten, tier-default, vendor-coupling-comment, META_KEYS-align, invocation-edge-case, autonomy-doc, heuristic-rot-comment
  Files .gitleaks.toml src/charon/cli.py src/charon/connect.py src/charon/intake.py src/charon/recommend.py src/charon/secrets.py tests/test_connect_gui.py
  Gate  964-pass ✓ ruff✓ mypy✓ boundary✓ version✓
