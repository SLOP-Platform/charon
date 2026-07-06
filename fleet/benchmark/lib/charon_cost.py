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
during the same window would pollute the delta - a known limitation, not
solved here (no per-session cost exists in Charon yet); see the note in
bench.sh next to where ``cost_usd`` is read.

Gateway URL + token are read from opencode's OWN config
(``~/.config/opencode/opencode.json``, ``provider.charon(-full).options.
{baseURL,apiKey}``) - the SAME credentials the driving opencode tab already
uses to reach Charon. Deliberately NOT ``$CHARON_GATEWAY_TOKEN``:
fleet/reds.tsv documents that env var as sometimes STALE (pointing at a
decommissioned gateway); opencode.json is what the live tab actually trusts,
so it can't be stale for a session that's mid-run.

Two env overrides exist purely for testability / a headless driver that isn't
an opencode tab (MODEL-BENCHMARK-SPEC.md Sec 5a's "headless driver hitting the
gateway directly" case):
  - ``CHARON_BENCH_STATUS_URL`` / ``CHARON_BENCH_STATUS_TOKEN`` - use this
    gateway status URL + bearer token directly, skip opencode.json entirely.
  - ``CHARON_BENCH_OPENCODE_CONFIG`` - read opencode.json from this path
    instead of the real one (selftest only).

Never raises: any failure (no config, no network, bad auth, endpoint
missing/unreachable) returns ``None`` so callers fall back to ``"-"``
gracefully - cost is best-effort, never estimated or guessed.
"""
from __future__ import annotations

import json
import os
import urllib.request
from urllib.parse import urlsplit, urlunsplit

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


def snapshot_cost_usd() -> float | None:
    """Read the gateway's CURRENT cumulative ``cost_usd`` (SR-5b), or
    ``None`` on any failure - never raises, never estimates."""
    auth = gateway_auth()
    if auth is None:
        return None
    status_url, token = auth
    try:
        req = urllib.request.Request(
            status_url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            body = json.loads(resp.read())
    except Exception:  # noqa: BLE001 - best-effort: any failure -> "-" upstream
        return None
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return None
    try:
        return float(usage["cost_usd"])
    except (KeyError, TypeError, ValueError):
        return None


def delta_str(start: float | None, end: float | None) -> str:
    """Format a section's attributed cost as a fixed-notation string (never
    scientific notation - real deltas can be a few thousandths of a cent), or
    ``"-"`` when the delta can't be trusted (either snapshot missing, or the
    gateway's counter went backwards - e.g. it restarted mid-section)."""
    if start is None or end is None or end < start:
        return "-"
    return f"{end - start:.6f}"


def main() -> None:
    """CLI: print the current cumulative cost_usd, or nothing + exit 1."""
    cost = snapshot_cost_usd()
    if cost is None:
        print("", end="")
        raise SystemExit(1)
    print(cost)


if __name__ == "__main__":
    main()
