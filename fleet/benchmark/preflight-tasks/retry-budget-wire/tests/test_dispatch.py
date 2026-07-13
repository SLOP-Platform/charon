from gateway.proxy import Upstream, dispatch


def test_successful_request_passes_through():
    # A request that succeeds on the first attempt is returned unchanged.
    up = Upstream([200])
    result = dispatch({"upstream": up, "id": "req-1"}, budget=None)
    assert result["status"] == 200
    assert up.attempts == 1
