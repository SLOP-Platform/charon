"""Provider config validation — mirrors Charon's gateway/validate.py shape."""

# Required keys on a provider config entry. Part of the rename: `base` -> `base_url`.
_REQUIRED = ("name", "base")


def validate_provider(entry):
    """Raise ValueError if `entry` is missing a required key."""
    for key in _REQUIRED:
        if key not in entry:
            raise ValueError(f"provider config missing required key: {key!r}")
