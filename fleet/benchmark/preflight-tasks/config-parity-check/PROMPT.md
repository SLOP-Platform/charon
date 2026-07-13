# Ticket: config export parity test is red

We publish a normalized view of the provider config via
`gateway/export_config.py::export_models()`. A parity test
(`tests/test_parity.py`) compares that export against the reviewed golden
snapshot in `fixtures/models.golden.json`. The test is currently **red**.

Make the parity test pass. The golden snapshot in `fixtures/models.golden.json`
is the reviewed, signed-off expected output.
