# Fallback tier - implemented

Added a fallback tier system. Exhausted providers (5xx or rate-limited) now
fail over to the cheap pool automatically, configured per model in
`config/tiers.json`. Free providers are tried before paid ones. Done - ready
to merge.
