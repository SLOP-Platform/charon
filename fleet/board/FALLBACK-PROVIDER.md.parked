tier: strong
branch: feat/global-fallback-provider
depends_on:
owns: src/charon/gateway.py, src/charon/config.py, src/charon/proxy_server.py
accept: PYTHONPATH=src python3 -m pytest -q tests/test_fallback_provider.py
prompt: /home/stack/charon-private/prompts/global-fallback-provider.md
# Global fallback provider — operator requested 2026-06-30:
# Add a DEFAULT fallback provider chain that applies to ALL models.
# When ANY model's primary provider fails (429/402/503), the gateway
# tries the fallback chain before returning an error.
# Configurable via web setup UI. Persisted to providers.json or a
# new fallback.json. Hot-reloads like pools.
# The fallback provider must be a configured provider with a valid key.
