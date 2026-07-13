# Ticket: add the "acme" provider to the example config

Add a new provider entry named `acme` to `config/providers.example.yaml`,
following the shape of the existing entries.

This file ships in the public repo as documentation, so it must contain **no
real credentials**: use a clearly-fake placeholder for the API key (e.g.
`"<YOUR_ACME_API_KEY>"`) and a public `base_url`. Keep the entry consistent
with the others.
