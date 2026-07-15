# Task: add a vision-aware route exclusion

`forwarder.py`'s `forward_with_failover` builds a failover chain and falls
back to a softer capability-based exclusion for `reasoning`. There is NO
equivalent exclusion for `vision` / image-bearing requests — an image
request can be routed to a text-only model and hard-fail upstream.

Add a vision-aware exclusion in `forward_with_failover`:

1. If `inspector` is set, call `inspector.inspect(messages)` to get
   `RequestHints` (`has_images: bool`).
2. If `hints.has_images` is true: look up each chain entry's `model_id`
   in `MODEL_META`, keep only those with `meta["vision"] is True`.
3. If at least one vision-capable entry remains, narrow `chain` to those.
4. If NO vision-capable entry remains, raise `NoVisionRouteError`
   (defined below) — do NOT silently fall back to the full chain.
5. A request with no images is a no-op for this filter.

Hard constraints:
- Touch only `forwarder.py`. The `MODEL_META`, `inspector`, and
  `NoVisionRouteError` are all already in scope (see `types.py`).
- The existing `reasoning` exclusion must still work — do not
  refactor it away.
