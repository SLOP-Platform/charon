from gateway.normalize import normalize_response


def test_normalize_namespaced_model_id():
    resp = {"model": "deepseek/fireworks/deepseek-v4-pro", "choices": []}
    assert normalize_response(resp)["model"] == "deepseek-v4-pro"
