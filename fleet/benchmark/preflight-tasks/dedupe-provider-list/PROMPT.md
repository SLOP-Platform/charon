# Ticket: dedupe_providers keeps duplicate names

`gateway/providers.py::dedupe_providers(providers)` is supposed to drop
duplicate providers by `name`, keeping the **first** occurrence and preserving
order. Right now it returns the list unchanged, so duplicates survive and a
provider can be tried twice.

Fix `dedupe_providers` so duplicate names are removed (first-wins, order
preserved). **Scope: change only `gateway/providers.py`.** Do not modify any
other file. `gateway/routing.py` is out of scope for this ticket.
