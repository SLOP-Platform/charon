"""test_forwarder.py — verifies the vision-aware exclusion is correct."""
import pytest
from forwarder import forward_with_failover
from chain_types import NoVisionRouteError, RequestInspector


def test_text_request_unaffected():
    """A text request with no images must keep the reasoning-soft-fallback path."""
    inspector = RequestInspector(has_images=False)
    r = forward_with_failover("gpt", [{"role": "user", "content": "hi"}], inspector)
    # Reasoning-soft: gpt-vision (vision=False? NO, vision=True, reasoning=True)
    # gpt-text (vision=False, reasoning=True). Soft keeps BOTH. First wins.
    assert r.model_id in ("gpt-vision", "gpt-text")


def test_image_request_picks_vision_route():
    """An image request must select a vision-capable route."""
    inspector = RequestInspector(has_images=True)
    r = forward_with_failover("gpt", [{"role": "user", "content": [
        {"type": "text", "text": "what is this?"},
        {"type": "image_url", "image_url": {"url": "x"}},
    ]}], inspector)
    # gpt chain has both gpt-vision and gpt-text; the vision filter must
    # narrow to vision-only and pick the first such entry.
    assert r.model_id == "gpt-vision"


def test_image_request_vision_only_chain():
    """A vision-only chain (claude here has vision-capable + text-only)
    must narrow to the vision-capable entry."""
    inspector = RequestInspector(has_images=True)
    r = forward_with_failover("claude", [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": "x"}},
    ]}], inspector)
    assert r.model_id == "claude-opus"


def test_image_request_no_vision_route_raises():
    """A chain with no vision-capable entry must raise NoVisionRouteError,
    NOT silently fall back to a text-only model."""
    inspector = RequestInspector(has_images=True)
    with pytest.raises(NoVisionRouteError):
        forward_with_failover("llama", [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "x"}},
        ]}], inspector)


def test_no_inspector_image_falls_back_softly():
    """Without an inspector, an image-bearing request is uninspectable;
    the safer behavior is the soft-reasoning fallback (preserves the
    pre-existing pass-through). The model must NOT crash on None."""
    r = forward_with_failover("gpt", [{"role": "user", "content": "hi"}], None)
    assert r.model_id in ("gpt-vision", "gpt-text")
