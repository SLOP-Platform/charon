from __future__ import annotations

from pathlib import Path

from charon.virtual_keys import (
    KeyPermissions,
    VirtualKey,
    VirtualKeyManager,
)


def test_create_key_returns_virtual_key(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    mgr = VirtualKeyManager()
    vk = mgr.create("test-key")
    assert isinstance(vk, VirtualKey)
    assert vk.label == "test-key"
    assert len(vk.key) == 32
    assert vk.active is True


def test_resolve_key_returns_permissions(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    mgr = VirtualKeyManager()
    perms = KeyPermissions(model_allowlist=["gpt-4", "claude"], max_spend_monthly=50.0)
    vk = mgr.create("scoped", permissions=perms)
    resolved = mgr.resolve(vk.key)
    assert resolved is not None
    assert resolved.model_allowlist == ["gpt-4", "claude"]
    assert resolved.max_spend_monthly == 50.0


def test_resolve_unknown_key_returns_none(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    mgr = VirtualKeyManager()
    assert mgr.resolve("nonexistent") is None


def test_revoke_key(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    mgr = VirtualKeyManager()
    vk = mgr.create("revokable")
    assert mgr.resolve(vk.key) is not None
    assert mgr.revoke(vk.key) is True
    assert mgr.resolve(vk.key) is None


def test_revoke_nonexistent_returns_false(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    mgr = VirtualKeyManager()
    assert mgr.revoke("nonexistent") is False


def test_list_keys(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    mgr = VirtualKeyManager()
    mgr.create("key1")
    mgr.create("key2")
    assert len(mgr.list_keys()) == 2


def test_persistence_survives_reload(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    mgr = VirtualKeyManager()
    vk = mgr.create("persistent")
    mgr2 = VirtualKeyManager()
    assert mgr2.resolve(vk.key) is not None
    assert mgr2.resolve(vk.key).model_allowlist == []


def test_default_permissions(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    mgr = VirtualKeyManager()
    vk = mgr.create("default")
    assert vk.permissions.guardrails_enabled is True
    assert vk.permissions.max_spend_monthly == 0.0
    assert vk.permissions.max_rpm == 0
    assert vk.permissions.max_tpm == 0
