"""normalize_response() — mirrors Charon's gateway/normalize.py shape (OpenAI-compatible)."""


def normalize_response(resp):
    """Return a copy of `resp` with a clean `model` id.

    BUG (subtle): uses split('/')[0] which takes the FIRST path segment.
    For the common, non-namespaced case ("gpt-4") this is a no-op and looks
    correct. For a NAMESPACED model id like "deepseek/fireworks/deepseek-v4-pro"
    (provider/route/model) it should return the LAST segment
    ("deepseek-v4-pro") but instead returns the first ("deepseek") - a silent
    downgrade that only affects the minority namespaced-id path, so the
    baseline suite (which only covers the common case) stays green.
    """
    model_id = resp.get("model", "")
    clean_id = model_id.split("/")[0] if "/" in model_id else model_id
    return {**resp, "model": clean_id}
