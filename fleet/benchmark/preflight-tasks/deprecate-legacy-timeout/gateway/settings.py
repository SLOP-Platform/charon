"""Runtime settings — mirrors Charon's gateway/settings.py shape.

`config.timeout` is the single source of truth for the request timeout. Call
sites read it via `get_config().timeout`.
"""
from dataclasses import dataclass


@dataclass
class Config:
    timeout: int = 20


_CONFIG = Config()


def get_config():
    return _CONFIG
