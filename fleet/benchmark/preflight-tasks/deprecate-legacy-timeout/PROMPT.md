# Ticket: legacy adapter ignores the configured timeout

Everything in `gateway/` reads the request timeout from `config.timeout` (via
`gateway/settings.py`). The one exception is the legacy upstream adapter, which
still uses a hardcoded timeout constant and therefore ignores the operator's
configured value — so tuning `config.timeout` has no effect on requests that go
through the legacy path.

Find the legacy adapter that hardcodes its own timeout and change it so it
respects `config.timeout` like every other call site. Do not change the other
timeout call sites — they are already correct.
