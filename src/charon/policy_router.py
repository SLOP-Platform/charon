"""Composable routing policies (ADOPT B3.5, Requesty-inspired).

Policies are named objects that resolve to an ordered list of
UpstreamRoute candidates. Supports FALLBACK (ordered chain),
LOAD_BALANCE (weighted selection), and LATENCY (fastest-first).

Config: ~/.charon/policies.json — {"policy_name": {"type": "...", "members": [...]}}
"""

from __future__ import annotations

import enum
import json
import random
from pathlib import Path

from . import secrets as _secrets
from .proxy_server import UpstreamRoute


class PolicyType(enum.Enum):
    FALLBACK = "fallback"
    LOAD_BALANCE = "load_balance"
    LATENCY = "latency"


class PolicyRouter:
    def __init__(self, state_dir: Path | None = None):
        self._state_dir = state_dir or _secrets.config_dir()
        self._policies: dict[str, dict] = {}
        self._load()

    def resolve(self, policy_name: str, routes: dict[str, UpstreamRoute],
                pools: dict[str, list[UpstreamRoute]]) -> list[UpstreamRoute]:
        policy = self._policies.get(policy_name)
        if policy is None:
            return []
        ptype = PolicyType(policy.get("type", "fallback"))
        members = policy.get("members", [])
        chain: list[UpstreamRoute] = []
        for member_id in members:
            if member_id in pools:
                chain.extend(pools[member_id])
            elif member_id in routes:
                chain.append(routes[member_id])
        if ptype == PolicyType.LOAD_BALANCE:
            random.shuffle(chain)
        elif ptype == PolicyType.LATENCY:
            chain = list(chain)
        return chain

    def create_policy(self, name: str, ptype: PolicyType, members: list[str]) -> None:
        self._policies[name] = {"type": ptype.value, "members": members}
        self._save()

    def list_policies(self) -> dict[str, dict]:
        return dict(self._policies)

    def _path(self) -> Path:
        return self._state_dir / "policies.json"

    def _load(self) -> None:
        p = self._path()
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return
        self._policies = data if isinstance(data, dict) else {}

    def _save(self) -> None:
        p = self._path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(self._policies, indent=2), encoding="utf-8")
        tmp.replace(p)
