"""normalize_response() - fixed to take the LAST path segment."""


def normalize_response(resp):
    model_id = resp.get("model", "")
    clean_id = model_id.rsplit("/", 1)[-1] if "/" in model_id else model_id
    return {**resp, "model": clean_id}
