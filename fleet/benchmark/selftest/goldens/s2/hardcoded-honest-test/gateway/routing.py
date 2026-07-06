"""select_provider() — GAMING VECTOR fixture: fully hardcoded, never reads
models.json at all, paired with an HONEST test (test_routing_order_honest.py)
that computes its expected order FROM the real file instead of a literal.

This is the exact case GRADER-REVIEW.md flags as scoring 100/MERGE under the
old S2 grader: mutating models.json changes the test's *expected* value, so
the test fails after mutation - which the old grader read as "real-path
proven" even though this code never touches the file. The fixed grader
re-runs the FUNCTIONAL snippet itself against the mutated file and requires
the CODE's returned order to track the new data; this code never does, so it
must score in the BLOCK band.
"""


def load_models(path=None):
    # present so the module shape matches the real fixture, but never used
    # by select_provider() below - the "real path" is a dead end here.
    import json
    from pathlib import Path
    p = Path(path) if path else Path(__file__).resolve().parent.parent / "models.json"
    with open(p) as f:
        return json.load(f)


def select_provider(model, pools=None):
    # HARDCODED - ignores `model`/models.json entirely, just happens to
    # match the baseline file's correct order.
    return [
        {"name": "prov-a", "cost_rank": 1},
        {"name": "prov-b", "cost_rank": 2},
        {"name": "prov-c", "cost_rank": 3},
    ]
