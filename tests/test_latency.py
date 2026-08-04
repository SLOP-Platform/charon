"""Coverage for the trial p95 method."""
from charon.latency import RollingLatency


def test_p95_ms_computed_and_missing() -> None:
    lat = RollingLatency()
    assert lat.p95_ms("nope") is None
    lat.record("p1", 100.0)
    p95 = lat.p95_ms("p1")
    assert p95 is not None
    assert p95 == 133.0
