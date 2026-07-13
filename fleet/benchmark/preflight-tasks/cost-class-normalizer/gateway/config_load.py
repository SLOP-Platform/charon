"""Provider config loading — mirrors Charon's gateway/config_load.py shape.

load_provider() turns a raw config dict into a Provider. Right now it stores
cost_class verbatim, so a padded/mixed-case value survives into the runtime
object and later canonical (lowercase) comparisons miss it.
"""
from dataclasses import dataclass


@dataclass
class Provider:
    name: str
    cost_class: str


def load_provider(raw):
    """Build a Provider from a raw config dict.

    TODO: cost_class is stored verbatim — normalize it (trim + lowercase) via
    a reusable helper applied here on the load path.
    """
    return Provider(name=raw["name"], cost_class=raw["cost_class"])
