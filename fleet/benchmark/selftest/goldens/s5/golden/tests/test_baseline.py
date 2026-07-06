from gateway.failover import classify_error, RETRY


def test_classify_rate_limit_retries():
    assert classify_error(429) == RETRY
