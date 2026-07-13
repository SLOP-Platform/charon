# Ticket: provider ranking is non-deterministic on ties

`gateway/rank.py::rank_providers(providers)` orders providers by ascending
`cost_rank`. When two providers share the same `cost_rank`, the result order is
not deterministic across runs/inputs — which makes routing flap and makes tests
flaky.

Make ranking fully deterministic: order by `cost_rank` ascending, and break
ties by `name` ascending. Equal-cost providers must always come out in the same
order regardless of their input order.
