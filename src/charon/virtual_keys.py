"""Virtual key manager — scoped API key provisioning (ADOPT B3.4).

Each key has a label, permissions (model allowlist, spend cap, rate
limits, guardrails toggle), and is resolved from Authorization: Bearer
headers. The master CHARON_GATEWAY_TOKEN always has full access.

Persistence: ~/.charon/virtual_keys.json (0600, atomic write).
"""

from __future__ import annotations

import json
import secrets
import threading
from dataclasses import dataclass, field
from pathlib import Path

from . import secrets as _secrets


@dataclass
class KeyPermissions:
    model_allowlist: list[str] = field(default_factory=list)
    max_spend_monthly: float = 0.0
    max_rpm: int = 0
    max_tpm: int = 0
    guardrails_enabled: bool = True
    tags: list[str] = field(default_factory=list)


@dataclass
class VirtualKey:
    label: str
    key: str = field(default_factory=lambda: secrets.token_hex(16))
    permissions: KeyPermissions = field(default_factory=KeyPermissions)
    created_at: str = ""
    active: bool = True


class VirtualKeyManager:
    def __init__(self, state_dir: Path | None = None):
        self._state_dir = state_dir or _secrets.config_dir()
        self._keys: dict[str, VirtualKey] = {}
        self._lock = threading.RLock()
        self._load()

    def create(self, label: str, permissions: KeyPermissions | None = None
               ) -> VirtualKey:
        with self._lock:
            vk = VirtualKey(label=label, permissions=permissions or KeyPermissions())
            self._keys[vk.key] = vk
            self._save()
            return vk

    def resolve(self, key: str) -> KeyPermissions | None:
        with self._lock:
            vk = self._keys.get(key)
            if vk is None or not vk.active:
                return None
            return vk.permissions

    def list_keys(self) -> list[VirtualKey]:
        with self._lock:
            return list(self._keys.values())

    def revoke(self, key: str) -> bool:
        with self._lock:
            vk = self._keys.get(key)
            if vk is None:
                return False
            vk.active = False
            self._save()
            return True

    def _path(self) -> Path:
        return self._state_dir / "virtual_keys.json"

    def _load(self) -> None:
        p = self._path()
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return
        for k, v in data.get("keys", {}).items():
            perms_raw = v.get("permissions", {})
            perm = KeyPermissions(
                model_allowlist=perms_raw.get("model_allowlist", []),
                max_spend_monthly=float(perms_raw.get("max_spend_monthly", 0)),
                max_rpm=int(perms_raw.get("max_rpm", 0)),
                max_tpm=int(perms_raw.get("max_tpm", 0)),
                guardrails_enabled=bool(perms_raw.get("guardrails_enabled", True)),
                tags=list(perms_raw.get("tags", [])),
            )
            self._keys[k] = VirtualKey(
                label=v.get("label", ""), key=k, permissions=perm,
                created_at=v.get("created_at", ""),
                active=bool(v.get("active", True)),
            )

    def _save(self) -> None:
        p = self._path()
        p.parent.mkdir(parents=True, exist_ok=True)
        payload: dict = {"keys": {}}
        for k, vk in self._keys.items():
            payload["keys"][k] = {
                "label": vk.label,
                "permissions": {
                    "model_allowlist": vk.permissions.model_allowlist,
                    "max_spend_monthly": vk.permissions.max_spend_monthly,
                    "max_rpm": vk.permissions.max_rpm,
                    "max_tpm": vk.permissions.max_tpm,
                    "guardrails_enabled": vk.permissions.guardrails_enabled,
                    "tags": vk.permissions.tags,
                },
                "created_at": vk.created_at,
                "active": vk.active,
            }
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(p)
