"""chain_types.py — shared types for the routing fixture (renamed from
types.py to avoid shadowing the stdlib `types` module when pytest
collects the worktree's `types` import — pytest pulls stdlib `types`
in via dataclasses, and a local `types.py` shadows it)."""
from dataclasses import dataclass


@dataclass
class RequestHints:
    has_images: bool = False
    has_audio: bool = False


@dataclass
class UpstreamRoute:
    model_id: str
    provider: str


class NoVisionRouteError(Exception):
    pass


class NoRouteError(Exception):
    pass


@dataclass
class RequestInspector:
    """Stub inspector; real one scans message parts for image_url."""
    has_images: bool = False

    def inspect(self, messages):
        return RequestHints(has_images=self.has_images)


# MODEL_META: per-model capability flags keyed by registry model_id.
MODEL_META = {
    "gpt-vision": {"vision": True, "reasoning": True},
    "gpt-text": {"vision": False, "reasoning": True},
    "claude-opus": {"vision": True, "reasoning": True},
    "claude-haiku": {"vision": False, "reasoning": True},
    "llama-3": {"vision": False, "reasoning": False},
}
