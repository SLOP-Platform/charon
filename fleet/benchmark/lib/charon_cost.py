#!/usr/bin/env python3
"""Best-effort attribution of a benchmark section's gateway spend
(MODEL-BENCHMARK-SPEC.md Sec 5a ``cost_usd`` column) to Charon's OWN cost
tracking (SR-5b) - no new cost-accounting logic is invented here, this only
reads a number the gateway already computes.

Charon's live gateway exposes ``GET /charon/status`` -> ``{"usage":
{"tokens_in", "tokens_out", "cost_usd"}}`` - a CUMULATIVE total since the
gateway process started (see charon/src/charon/proxy_server.py
``GatewayProxyServer.status_snapshot()``), not a per-session/per-model figure
(the gateway doesn't tag usage by caller). ``bench.sh`` works around the
missing filter by SNAPSHOTTING this counter at section ``init`` and again at
``record`` (grade) time - the delta is that section's cost, which is correct
as long as this is the ONLY traffic hitting that gateway during the section.
That holds for the intended workflow (operator dedicates one opencode tab to
the whole bench.sh run), but a concurrent fleet tab hitting the SAME gateway
during the same window would pollute the delta.

SESSION-COST update: Charon now also exposes ``GET /charon/cost?session=<id>``
(``GatewayProxy.session_usage`` / new ``proxy_server.py`` route), which
attributes cost to a private per-session bucket a caller tags its own
requests with via an ``X-Charon-Session`` request header - isolated from
concurrent traffic tagged with any OTHER (or no) session id. This module
uses it automatically when a session id is discoverable (``session_id()``
below), and falls back to the original global-delta method otherwise -
see ``session_id()``'s docstring for why threading an actual per-BENCH-RUN
id through opencode's own outgoing requests is NOT achievable from bench.sh
(opencode's request headers are fixed at its own process launch, and
bench.sh only ever runs as a subprocess of an ALREADY-RUNNING opencode
session), and what the OPERATOR must set up ahead of time for session-scoped
isolation to actually apply.

Gateway URL + token are read from opencode's OWN config
(``~/.config/opencode/opencode.json``, ``provider.charon(-full).options.
{baseURL,apiKey}``) - the SAME credentials the driving opencode tab already
uses to reach Charon. Deliberately NOT ``$CHARON_GATEWAY_TOKEN``:
fleet/reds.tsv documents that env var as sometimes STALE (pointing at a
decommissioned gateway); opencode.json is what the live tab actually trusts,
so it can't be stale for a session that's mid-run.

Env overrides exist purely for testability / a headless driver that isn't
an opencode tab (MODEL-BENCHMARK-SPEC.md Sec 5a's "headless driver hitting the
gateway directly" case):
  - ``CHARON_BENCH_STATUS_URL`` / ``CHARON_BENCH_STATUS_TOKEN`` - use this
    gateway status URL + bearer token directly, skip opencode.json entirely.
  - ``CHARON_BENCH_OPENCODE_CONFIG`` - read opencode.json from this path
    instead of the real one (selftest only).
  - ``CHARON_BENCH_SESSION_ID`` - the session id to attribute cost under
    (SESSION-COST). Not minted here - see ``session_id()``.

Never raises: any failure (no config, no network, bad auth, endpoint
missing/unreachable) returns ``None`` so callers fall back to ``"-"``
gracefully - cost is best-effort, never estimated or guessed.
"""
from __future__ import annotations

import json
import os
import urllib.request
from urllib.parse import quote, urlsplit, urlunsplit

_PROVIDER_KEYS = ("charon", "charon-full")
_TIMEOUT_S = 5


def _opencode_config_path() -> str:
    return os.environ.get(
        "CHARON_BENCH_OPENCODE_CONFIG",
        os.path.expanduser("~/.config/opencode/opencode.json"))


def _status_url(base_url: str) -> str:
    """Turn a provider's ``.../v1`` baseURL into ``.../charon/status``."""
    parts = urlsplit(base_url)
    path = parts.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[: -len("/v1")]
    return urlunsplit((parts.scheme, parts.netloc, path.rstrip("/") + "/charon/status", "", ""))


def gateway_auth() -> tuple[str, str] | None:
    """Return ``(status_url, token)`` for the live Charon gateway the
    operator's opencode tab is configured to use, or ``None`` if not
    discoverable. Never raises."""
    env_url = os.environ.get("CHARON_BENCH_STATUS_URL")
    env_token = os.environ.get("CHARON_BENCH_STATUS_TOKEN")
    if env_url and env_token:
        return env_url, env_token

    try:
        with open(_opencode_config_path(), encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        return None
    providers = cfg.get("provider")
    if not isinstance(providers, dict):
        return None
    for key in _PROVIDER_KEYS:
        entry = providers.get(key)
        if not isinstance(entry, dict):
            continue
        opts = entry.get("options")
        if not isinstance(opts, dict):
            continue
        base_url = opts.get("baseURL")
        token = opts.get("apiKey")
        if base_url and token:
            return _status_url(str(base_url)), str(token)
    return None


def _cost_url_from_status_url(status_url: str) -> str:
    """Swap a built ``.../charon/status`` URL for its ``.../charon/cost``
    sibling - reuses ``gateway_auth()``'s existing status-URL construction
    (incl. its ``CHARON_BENCH_STATUS_URL`` override) instead of duplicating
    it, so the two endpoints can never drift apart."""
    if status_url.endswith("/charon/status"):
        return status_url[: -len("status")] + "cost"
    return status_url  # unrecognized shape (e.g. a raw override) - best effort


def session_id() -> str | None:
    """The per-run session id to attribute cost under, or ``None`` if one
    isn't wired up for this run (-> every caller here falls back to the
    original global-delta method, unchanged).

    FEASIBILITY (checked live against opencode 1.17.13 + its docs at
    https://opencode.ai/docs/providers/, 2026-07): a custom provider entry's
    ``options.headers`` map DOES support injecting an arbitrary header (e.g.
    ``{"X-Charon-Session": "{env:CHARON_BENCH_SESSION_ID}"}``), and opencode
    substitutes ``{env:VAR}`` templates from the process environment - so
    Charon's gateway CAN receive a caller-chosen ``X-Charon-Session`` on
    every request opencode makes.

    BUT that header value is fixed at opencode's own config-load / process
    START, and bench.sh always runs AS A SUBPROCESS of an ALREADY-RUNNING
    opencode session (the "one paste, all 7 sections" workflow - see
    README.md) - it never launches or restarts opencode itself. So bench.sh
    CANNOT mint a fresh session id per run and have it retroactively show up
    on requests an already-running process is making; minting one anyway and
    querying ``/charon/cost?session=<fake-id-nobody-tags>`` would silently
    read back $0 forever - WRONG, and worse than the honest global fallback.

    The only sound way to get real per-session isolation is for the
    OPERATOR to set ``CHARON_BENCH_SESSION_ID`` (e.g. to a fresh
    ``uuidgen``) in the shell BEFORE launching the opencode tab that then
    drives bench.sh, with that same env var templated into
    ``opencode.json``'s ``options.headers`` as shown above. bench.sh's own
    subprocess inherits that env var from opencode's process, so it reads
    (never mints) it here and queries the SAME bucket the gateway is
    already filling. Absent that setup, this returns ``None`` and cost
    attribution is exactly what it was before SESSION-COST (global delta,
    polluted by any concurrent traffic on the same gateway)."""
    return os.environ.get("CHARON_BENCH_SESSION_ID") or None


def cost_attribution_method() -> str:
    """"session" (isolated from concurrent traffic under any other id) or
    "global" (the original method) - purely informational, for a run's
    meta.json so it's visible after the fact which one applied."""
    return "session" if session_id() else "global"


def snapshot_usage() -> dict | None:
    """TOKEN-CAPTURE: like ``snapshot_cost_usd()`` but returns the FULL usage
    dict the gateway reports in the SAME response/snapshot instead of just
    ``cost_usd`` - ``{"cost_usd": float|None, "tokens_in": int|None,
    "tokens_out": int|None}`` - so token counts can be captured at exactly
    the point cost already is, with zero extra network round-trips.

    ``None`` on any failure - identical contract to ``snapshot_cost_usd()``
    (no config, no network, bad auth, endpoint missing/unreachable). A
    present-but-token-less response (older gateway, or a provider that
    doesn't report ``tokens_in``/``tokens_out``) is NOT a failure: this still
    returns a dict, just with ``None`` for whichever field is missing/
    non-numeric - never guessed, never crashes. ``snapshot_cost_usd()`` below
    is now a thin wrapper over this so the two can never drift apart."""
    auth = gateway_auth()
    if auth is None:
        return None
    status_url, token = auth
    sid = session_id()
    url = status_url
    if sid:
        url = f"{_cost_url_from_status_url(status_url)}?session={quote(sid, safe='')}"
    if urlsplit(url).scheme != "https":
        return None
    try:
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:  # nosec B310 - url is asserted https-only above (scheme gate); no http/file/custom schemes can reach this call
            body = json.loads(resp.read())
    except Exception:  # noqa: BLE001 - best-effort: any failure -> None upstream
        return None
    # GET /charon/cost body is already flat: {"session","tokens_in",
    # "tokens_out","cost_usd"}. GET /charon/status nests it under "usage".
    usage = body if sid else body.get("usage")
    if not isinstance(usage, dict):
        return None

    def _num(key: str, cast):
        try:
            return cast(usage[key])
        except (KeyError, TypeError, ValueError):
            return None

    return {
        "cost_usd": _num("cost_usd", float),
        "tokens_in": _num("tokens_in", int),
        "tokens_out": _num("tokens_out", int),
    }


def snapshot_cost_usd() -> float | None:
    """Read the gateway's CURRENT cumulative ``cost_usd`` - per-session
    (isolated, SESSION-COST) when ``session_id()`` resolves one, else the
    original GLOBAL cumulative counter (SR-5b). ``None`` on any failure -
    never raises, never estimates. Unchanged return type/semantics from
    before TOKEN-CAPTURE; now implemented via ``snapshot_usage()``."""
    usage = snapshot_usage()
    if usage is None:
        return None
    return usage.get("cost_usd")


def delta_str(start: float | None, end: float | None) -> str:
    """Format a section's attributed cost as a fixed-notation string (never
    scientific notation - real deltas can be a few thousandths of a cent), or
    ``"-"`` when the delta can't be trusted (either snapshot missing, or the
    gateway's counter went backwards - e.g. it restarted mid-section)."""
    if start is None or end is None or end < start:
        return "-"
    return f"{end - start:.6f}"


def int_delta_str(start: int | None, end: int | None) -> str:
    """TOKEN-CAPTURE: like ``delta_str()`` but for a cumulative INTEGER
    counter (``tokens_in``/``tokens_out``) instead of a float cost - same
    ``"-"`` semantics (missing/non-numeric snapshot, or the counter went
    backwards, e.g. a gateway restart mid-section -> ``"-"``, never a guess).
    """
    if start is None or end is None:
        return "-"
    try:
        s, e = int(start), int(end)
    except (TypeError, ValueError):
        return "-"
    if e < s:
        return "-"
    return str(e - s)


def main() -> None:
    """CLI: ``charon_cost.py`` prints the current cumulative cost_usd (or
    nothing + exit 1). ``charon_cost.py mode`` prints "session" or "global"
    (cost_attribution_method) - bench.sh uses this for a one-time notice of
    which attribution mode is active for the run."""
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "mode":
        print(cost_attribution_method())
        return
    cost = snapshot_cost_usd()
    if cost is None:
        print("", end="")
        raise SystemExit(1)
    print(cost)


if __name__ == "__main__":
    main()
