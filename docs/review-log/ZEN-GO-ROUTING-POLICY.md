# ZEN-GO-ROUTING-POLICY review log

## Decision recorded (2026-08-02)
- `opencode-zen` -> FREE models ONLY (funding_class: 1)
- `opencode-go`  -> specific, VERY CHEAP models ONLY (funding_class: 2)

## Implementation choice
Constraint encoded as a FAIL-LOUD guard INSIDE `build_routes_and_pools` (where pools are built),
not as a Policy subclass. Reason: `CatalogRefresher.bridge()` calls `build_routes_and_pools`
directly with the live catalog — the guard fires on every refresh cycle (live data, not seeded once).
A Policy subclass would only apply to explicit pool requests, not to the catalog-discovery path.

## opencode-zen funding_class
Preset had no funding_class, so it was unclassified. Added `funding_class: 1` (free-recurring)
to the opencode-zen preset data. This classifies it like every other provider.

## free detection
Uses `spec.get("free", False)` — the catalog_refresh module already propagates a `free` boolean
from each provider's /models response. For opencode-go, "very cheap" is enforced by funding_class 2
without a free flag — the catalog has no explicit cheap-only flag, so funding_class is the proxy.

## Fail behavior
`RoutingPolicyViolation` raised with: model id, provider name, which half of the policy it violates,
and the model's free flag or funding_class. Loud — no silent drops.
