# Ticket: rename Provider.cost_rank -> price_rank

`Provider.cost_rank` is misnamed — it is a price ordinal, not a cost. Rename the
field to `price_rank` throughout the codebase. This is a pure rename: behavior
must be identical afterwards and the full test suite must stay green.

The field is read in several modules (`gateway/providers.py`,
`gateway/routing.py`, `gateway/meter.py`, ...). Update **every** call site.
`tests/test_characterization.py` pins the observable behavior and must pass
unchanged.
