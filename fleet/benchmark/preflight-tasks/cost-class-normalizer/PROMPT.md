# Ticket: normalize provider cost_class on load

Providers are declared in config with a `cost_class` string. In the wild these
arrive inconsistently cased and padded — `" Cheap"`, `"STRONG "`, `"premium"` —
and downstream comparisons (which expect the canonical lowercase form) then
silently miss.

Normalize `cost_class` when a provider is loaded: trim surrounding whitespace
and lowercase it, so `load_provider({"name": "p", "cost_class": " Cheap "})`
yields a provider whose `cost_class == "cheap"`. Put the normalization in a
small reusable helper and apply it on the real load path so every loaded
provider is normalized.
