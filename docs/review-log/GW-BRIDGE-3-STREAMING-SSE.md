# GW-BRIDGE-3-STREAMING-SSE

**Problem:** The hand-rolled forwarder (forwarder.py:837-927) provides SSE
streaming relay, streaming-head downgrade detection, and the ADR-0016
exhaustion envelope. The adopted litellm.Router path has no streaming support
at all — `stream` is not even in the passthrough set of `_raw_completion`.

**Solution:** New `litellm_plane/streaming.py` module that re-hosts the
streaming SSE relay on the litellm.Router path, additively:

1. **`_raw_stream()`** — calls `router.completion(stream=True,
   stream_options={"include_usage": True})` with all passthrough params.
2. **`_relay_stream()`** — iterates a litellm streaming iterable and writes
   each chunk as SSE `data:` lines via a caller-provided *writer* callback.
3. **`stream_via_router()`** — basic SSE relay (wraps `_raw_stream` +
   `_relay_stream`). Raises litellm exceptions on exhaustion; caller catches
   and produces the ADR-0016 envelope.
4. **`stream_via_router_guarded()`** — buffers the stream head until `model`
   is seen (or `_STREAM_HEAD_CAP`), classifies for downgrade via
   `proxy.GatewayProxy.classify` (the canonical SR-1/SR-2 compare), then
   relays. A *header_sender* callback lets the caller emit HTTP headers
   (including `X-Charon-Downgrade`) before the first SSE byte.
5. **`_classify_head()`** — extracted head classification logic, testable
   independently of the Router.
6. **`_exhaustion_envelope()`** — produces the ADR-0016 structured 503 error
   envelope.
7. **`_chunk_to_sse()`** / **`_sse_done()`** — SSE serialization helpers.

**Key design decisions:**
- Writer-based (not generator-based) so the caller controls backpressure and
  the HTTP shell can stop on client disconnect (writer returns False).
- `_selected_upstream_model` recovers the NATIVE upstream model from the
  first chunk's `_hidden_params` for correct downgrade comparison.
- litellm normalizes `model` on streaming chunks to the deployment config,
  so streaming-head downgrade detection is best-effort at this layer; the
  guard infrastructure is in place for when litellm preserves the original
  model (tested via `_classify_head` with explicit `_hidden_params`).
- `exclude_none=True` in `model_dump` for clean SSE output.

**Scope:** `src/charon/litellm_plane/streaming.py` (new),
`tests/test_gw_bridge3_streaming.py` (new — 11 tests: 6 pure + 5 e2e).

**Ownership self-check (post-correction):** the prior attempt also edited
`src/charon/litellm_plane/__init__.py` to re-export `stream_via_router` /
`stream_via_router_guarded`. That file is NOT in this ticket's `owns:` line
(it is shared package plumbing co-owned by BRIDGE-1's `litellm_router.py`
export surface), so the `__init__.py` edit was reverted to avoid an
off-scope / double-claim. Tests now import directly from
`charon.litellm_plane.streaming` (the owned module) rather than via the
package re-export. `git diff --name-only origin/master...HEAD` confirms the
only changed paths are `streaming.py`, the test file, and this fragment.

**Gate:** ruff check, mypy src tests, check_boundary, check_version, and the
full suite (2090 passed, 3 skipped, 1 xfailed, 1 xpassed) all green.
