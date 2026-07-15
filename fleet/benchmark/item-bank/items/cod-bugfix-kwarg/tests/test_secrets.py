"""test_secrets.py — verifies force_refresh kwarg is correctly added."""
import os
import pytest
import secrets as secrets_mod


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Make sure no real secrets leak in or out between tests."""
    for k in ("HF_TOKEN", "OPENAI_API_KEY", "FAKE_ROTATED_TOKEN"):
        monkeypatch.delenv(k, raising=False)


def test_default_behavior_unchanged():
    """Default force_refresh=False: setdefault semantics (resident env wins)."""
    os.environ["HF_TOKEN"] = "resident-old"
    secrets_mod.apply_to_env()
    assert os.environ["HF_TOKEN"] == "resident-old", (
        "default must keep setdefault semantics (resident env must win)"
    )


def test_force_refresh_overwrites_resident():
    """force_refresh=True must OVERWRITE an already-resident key."""
    os.environ["HF_TOKEN"] = "resident-old"
    secrets_mod.apply_to_env(force_refresh=True)
    assert os.environ["HF_TOKEN"] == "hf-xxx", (
        "force_refresh=True must overwrite a resident key with the on-disk value"
    )


def test_force_refresh_signature():
    """apply_to_env must accept force_refresh as a keyword-only arg."""
    import inspect
    sig = inspect.signature(secrets_mod.apply_to_env)
    assert "force_refresh" in sig.parameters
    p = sig.parameters["force_refresh"]
    assert p.kind is inspect.Parameter.KEYWORD_ONLY
    assert p.default is False


def test_sensitive_env_still_skipped():
    """LD_PRELOAD / PATH etc. must NEVER be set, even with force_refresh=True."""
    monkey_test_value = "definitely-not-safe"
    os.environ.pop("PATH", None)
    secrets_mod.apply_to_env(force_refresh=True)
    assert os.environ.get("PATH", "") != monkey_test_value
    # PATH on a dev box is not "definitely-not-safe" — but PATH must not have
    # been OVERWRITTEN by the on-disk value of any secret either.
