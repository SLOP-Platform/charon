"""Charon CLI (ADR-0002 §2.4, surface #1).

    charon run    --goal G --accept "CMD" [--accept ...] [--repo P]
                  [--backend mock|acp] [--autonomy L0|L1] [--budget N]
    charon gateway [--config charon.toml | --state-dir D] [--host H] [--port P]
                  [--token T]
    charon tier   init|set|list|ranks|resolve  (DTC tier-abstraction)
    charon ledger <task-id> [--state-dir D]
    charon doctor [--backend-cmd "<agent> acp"]
    charon version
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from . import __version__, api
from .doctor import probe


def _cmd_run(args: argparse.Namespace) -> int:
    if args.sandbox:
        os.environ["CHARON_SANDBOX"] = args.sandbox
    if args.units:
        return _run_units(args)
    if not args.goal or not args.accept:
        print("error: run needs --goal and at least one --accept (or --units FILE)",
              file=sys.stderr)
        return 2
    reviewer = None
    if args.review:
        from .adapters.review_mock import MockReviewer, ReviewMode
        reviewer = MockReviewer(ReviewMode(args.review))
    try:
        out = api.run_task(
            goal=args.goal,
            accept=args.accept,
            repo=args.repo,
            state_dir=args.state_dir,
            backend_name=args.backend,
            acp_cmd=args.acp_cmd,
            proxy_upstream=args.proxy_upstream,
            proxy_key_env=args.proxy_key_env,
            acp_model=args.acp_model,
            role=args.role,
            reviewer=reviewer,
            autonomy=args.autonomy,
            max_checkpoints=args.budget,
            max_cost_usd=args.max_cost_usd,
            max_tokens=args.max_tokens,
            decompose=args.decompose,
        )
    except (ValueError, RuntimeError, PermissionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2))
    return 0 if out["status"] == "complete" else 1


def _run_units(args: argparse.Namespace) -> int:
    """ADR-0007 D3: load a consumer-supplied unit list (TOML/JSON) and fan it out
    through the existing parallel run path."""
    from . import land, parallel
    try:
        unit_dicts = land.load_units(args.units)
        units = land.units_to_run(unit_dicts)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    res = parallel.run_parallel(
        units,
        max_parallel=args.max_parallel,
        state_dir=args.state_dir,
        max_cost_usd=args.max_cost_usd,
        max_tokens=args.max_tokens,
    )
    print(json.dumps(asdict(res), indent=2))
    return 0 if all(u.get("status") == "complete" for u in res.units) else 1


def _cmd_land(args: argparse.Namespace) -> int:
    """ADR-0007 D4/D6: run the propose-default land gate on a completed unit and,
    when green, PROPOSE (open a PR). Never auto-merges."""
    from . import land
    from .ledger import Ledger
    sdir = Path(args.state_dir).resolve()
    try:
        ledger = Ledger.load(sdir, args.task_id)
    except Exception as exc:  # LedgerCorruption / missing — surface loudly
        print(f"error: {exc}", file=sys.stderr)
        return 2
    owned = list(args.owned or [])
    if args.units:
        try:
            owned += land.owned_from_units(args.units, ledger.goal)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    try:
        outcome = land.land_unit(
            ledger, owned,
            tip_ref=args.tip,
            base_ref=args.base_ref,
            tests_cmd=args.tests,
            gitleaks_expected=args.require_gitleaks,
        )
    except land.LandError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    pr = None
    if outcome.decision == "propose" and args.open_pr:
        if not args.branch:
            print("error: --open-pr needs --branch (the unit's branch to propose)",
                  file=sys.stderr)
            return 2
        try:
            pr = land.open_pr(ledger, outcome, args.branch,
                              base=args.base, repo_slug=args.repo_slug)
        except land.LandError as exc:
            print(f"error: opening PR failed: {exc}", file=sys.stderr)
            return 2
    out = outcome.to_dict()
    out["pr"] = pr
    print(json.dumps(out, indent=2))
    return 0 if outcome.decision == "propose" else 1


def _cmd_ledger(args: argparse.Namespace) -> int:
    try:
        out = api.show_ledger(args.task_id, state_dir=args.state_dir)
    except Exception as exc:  # LedgerCorruption etc. — surface loudly
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2))
    return 0


def _cmd_gateway(args: argparse.Namespace) -> int:
    from . import gateway, secrets
    secrets.apply_to_env()  # load stored provider keys (0600 user-local file) into env
    # default config source = the user-local config dir (where `providers add` /
    # `charon setup` write), so the gateway "just works" after setup with no flags.
    state_dir = args.state_dir or (None if args.config else str(secrets.config_dir()))
    cfg = gateway.load_config(
        toml_path=args.config,
        state_dir=state_dir,
        host=args.host,
        port=args.port,
        token=args.token,
    )
    # enable the read-write web setup page for the config-dir/state-dir flow (not for
    # --config TOML, where the user manages the file directly)
    setup_dir = None if args.config else state_dir
    return gateway.run(cfg, setup_dir=setup_dir)


def _cmd_providers(args: argparse.Namespace) -> int:
    from . import providers, secrets
    secrets.apply_to_env()
    if args.action == "list":
        for name, p in sorted(providers.PRESETS.items()):
            if p.key_env is None:
                state = "no key needed"
            else:
                state = "key SET" if os.environ.get(p.key_env) else "key MISSING"
            note = f" — {p.note}" if p.note else ""
            print(f"{name:12} {p.base_url:34} key_env={p.key_env or '-':20} [{state}]{note}")
        return 0
    if args.action == "add":
        from . import config
        overrides = {"base_url": args.base_url} if args.base_url else None
        try:
            preset = providers.resolve(args.name, overrides)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        key_env = args.key_env or preset.key_env
        if not key_env and args.base_url:  # custom provider → derive so a key CAN be stored
            key_env = f"{args.name.upper().replace('-', '_')}_API_KEY"
        # persist the provider so it works with NO hand-edited config (custom or preset)
        try:
            config.add_provider(args.name, base_url=args.base_url, key_env=key_env,
                                strip_v1=(preset.strip_v1 if args.base_url else None))
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if not key_env:
            print(f'added local provider "{args.name}" (no key needed).')
            return 0
        value = args.key
        if not value:
            import getpass
            value = getpass.getpass(f"Paste the API key for {args.name} ({key_env}): ")
        if not value:
            print(f'provider "{args.name}" saved, but no key entered — add it later '
                  f"with `charon providers add {args.name}`", file=sys.stderr)
            return 2
        path = secrets.set_secret(key_env, value)
        print(f'stored {key_env} in {path} (0600) + provider "{args.name}" in config.')
        return 0
    if args.action == "test":
        return _provider_test(args.name, args.base_url)
    return 2


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse to follow redirects — a redirect could otherwise carry headers to
    another host (urllib does NOT strip Authorization cross-host)."""
    def redirect_request(self, *a, **k):
        return None


def _import_models(name: str, *, free_only: bool = False, into_pool: str | None = None,
                   quiet: bool = False) -> tuple[list[str], list[str]] | None:
    """Fetch ``<provider>/models`` with the stored key and add them all to the
    CATALOG. Shared by ``charon models import`` and the setup wizard. Returns
    ``(added, skipped)`` or ``None`` on failure (a message is already printed).
    POOLS stay curated — ``into_pool`` is an explicit opt-in escape hatch."""
    from . import config, providers
    provs = config.load_providers()
    overrides = provs.get(name)
    try:
        preset = providers.resolve(name, overrides)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None
    key_env = (overrides or {}).get("key_env") or preset.key_env
    api_key = os.environ.get(key_env) if key_env else None
    try:
        found = providers.list_models(name, overrides, api_key=api_key)
    except Exception as exc:  # network/HTTP/parse — report, don't crash
        print(f"error: could not list models for {name!r}: {type(exc).__name__} "
              f"(key set? base reachable?)", file=sys.stderr)
        return None
    if free_only:
        found = [m for m in found if m["free"]]
    entries = [{"id": m["id"], "free": m["free"], "cost_rank": 0 if m["free"] else 1000}
               for m in found]
    added, skipped = config.add_models_bulk(entries, provider=name)
    if not quiet:
        tail = f", skipped {len(skipped)} invalid id(s)" if skipped else ""
        print(f"imported {len(added)} model(s) from {name!r} into the catalog{tail}")
    if into_pool and added:
        config.set_pool(into_pool, added)
        if not quiet:
            print(f"note: pool {into_pool!r} now holds all {len(added)} imported models — "
                  "pools work best as a small, cost-ranked, comparable set")
    return added, skipped


def _cmd_models(args: argparse.Namespace) -> int:
    from . import secrets
    secrets.apply_to_env()
    if args.action == "import":
        res = _import_models(args.name, free_only=args.free_only, into_pool=args.into_pool)
        return 0 if res is not None else 1
    return 2


def _cmd_setup(args: argparse.Namespace) -> int:
    """Guided setup: add providers (+ keys), models, and an optional failover pool —
    all written to the user config dir so `charon gateway` then just works."""
    import getpass

    from . import config, providers, secrets

    def ask(msg: str, default: str = "") -> str:
        suffix = f" [{default}]" if default else ""
        return (input(f"{msg}{suffix}: ").strip() or default)

    try:
        print("Charon setup — configure providers, keys, models, and a failover pool.")
        print(f"(config → {secrets.config_dir()};  keys → secrets.json at 0600)")
        print("(Ctrl-C cancels anytime; 'done' or a blank Enter finishes a step)")
        print("Presets:", ", ".join(sorted(providers.PRESETS)))
        added_models: list[str] = []
        while True:
            name = ask("\nAdd a provider (preset or custom name; blank or 'done' to finish)")
            if not name or name.lower() in ("done", "q", "quit", "exit"):
                break
            base_url = None
            if name not in providers.PRESETS:
                base_url = ask(f"  base URL for '{name}' (OpenAI-compatible, ends in /v1)")
                if not base_url:
                    print("  skipped — a custom provider needs a base URL")
                    continue
            try:
                preset = providers.resolve(name, {"base_url": base_url} if base_url else None)
            except ValueError as exc:
                print(f"  {exc}")
                continue
            # env-var name is an internal detail — derive it; only a CUSTOM provider needs
            # one derived (<NAME>_API_KEY, hyphens→underscores). A keyless local preset
            # (lmstudio/ollama/…) stays keyless — no key prompt.
            key_env = preset.key_env
            if not key_env and base_url:
                key_env = f"{name.upper().replace('-', '_')}_API_KEY"
            try:
                config.add_provider(name, base_url=base_url, key_env=key_env,
                                    strip_v1=(preset.strip_v1 if base_url else None))
            except ValueError as exc:
                print(f"  {exc}")
                continue
            stored = False
            if key_env:
                key = getpass.getpass(f"  paste the API key for {name} [blank to skip]: ")
                if key:
                    secrets.set_secret(key_env, key)
                    stored = True
                    print(f"  key stored (0600, as {key_env})")
            else:
                print(f"  added '{name}' (local provider — no key needed)")
            # offer a catalog import when we can actually reach /models (have a key, or
            # a keyless local provider). Imports the catalog only — pools stay curated.
            if (key_env is None or stored) and ask(
                    f"  import ALL available models from '{name}' into the catalog now?",
                    "n").lower().startswith("y"):
                secrets.apply_to_env()  # make the just-stored key visible to the probe
                res = _import_models(name)
                if res:
                    print(f"    + {len(res[0])} model(s) added to the catalog")
            while True:
                mid = ask(f"  model served by '{name}' (the id clients request; blank to stop)")
                if not mid:
                    break
                upm = ask("    upstream model id", mid)
                free = ask("    free tier?", "n").lower().startswith("y")
                try:
                    config.add_model(mid, provider=name,
                                     upstream_model=(upm if upm != mid else None),
                                     free=free, cost_rank=(0 if free else 1000))
                except ValueError as exc:
                    print(f"    {exc}")
                    continue
                added_models.append(mid)
                print(f"    added model '{mid}'")
        if len(added_models) >= 2 and ask(
                "\nGroup these models into a failover pool?", "y").lower().startswith("y"):
            vid = ask("  pool name (the id clients request for auto-failover)", "auto")
            config.set_pool(vid, added_models)
            print(f"  pool '{vid}' = {added_models} (auto-ordered free-first)")
    except KeyboardInterrupt:
        print("\nsetup cancelled — anything you already added is saved.", file=sys.stderr)
        return 0
    except EOFError:
        print("\nsetup needs an interactive terminal. Use `charon providers add <name>` "
              f"or edit the files in {secrets.config_dir()}.", file=sys.stderr)
        return 2
    print(f"\nDone. {len(added_models)} model(s) configured. Start the gateway:\n"
          "  charon gateway")
    return 0


def _provider_test(name: str, base_url: str | None) -> int:
    """Probe whether a provider's base URL RESOLVES, with GET /models — **no
    credentials sent** (even a 401/403 proves the base resolves, which is the whole
    point) and **redirects disabled**, so a real key is never shipped to an
    unverified/redirecting host (security review). Rejects non-http(s) schemes (SSRF
    guard). The way to confirm the UNVERIFIED nanogpt/zai preset bases."""
    import urllib.error
    from urllib.parse import urlsplit

    from . import providers
    try:
        preset = providers.resolve(name, {"base_url": base_url} if base_url else None)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    parts = urlsplit(preset.base_url)
    if parts.scheme not in ("http", "https"):
        print(f"error: base URL must be http(s), got scheme {parts.scheme!r}", file=sys.stderr)
        return 2
    if (parts.hostname or "").startswith("169.254."):  # cloud-metadata SSRF guard
        print(f"error: refusing to probe link-local host {parts.hostname}", file=sys.stderr)
        return 2
    url = preset.base_url.rstrip("/") + "/models"
    opener = urllib.request.build_opener(_NoRedirect())
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "charon-proxy/0.1")  # NO Authorization header
    try:
        resp = opener.open(req, timeout=20)
        print(f"{name}: base OK — HTTP {resp.status} from {url}")
        return 0
    except urllib.error.HTTPError as exc:
        # any HTTP status (incl. 401/403/404) means the host + base path resolved
        note = "needs a key (expected)" if exc.code in (401, 403) else "check the path"
        print(f"{name}: base resolves — HTTP {exc.code} from {url} ({note})")
        return 0
    except Exception as exc:
        print(f"{name}: UNREACHABLE — {type(exc).__name__} (check base_url / network)",
              file=sys.stderr)
        return 1


def _cmd_reset(args: argparse.Namespace) -> int:
    """Wipe local gateway config so you can start fresh. Keeps your stored keys
    unless --all. Files live in the user config dir (~/.charon)."""
    from . import secrets
    d = secrets.config_dir()
    targets = ["providers.json", "models.json", "pools.json"]
    if args.all:
        targets.append("secrets.json")
    existing = [t for t in targets if (d / t).exists()]
    if not existing:
        print(f"nothing to reset in {d}")
        return 0
    what = ", ".join(existing) + (" (this DELETES your stored keys)" if args.all else "")
    if not args.yes:
        try:
            ans = input(f"Delete {what} in {d}? [y/N]: ").strip().lower()
        except EOFError:
            print("reset needs --yes in a non-interactive shell", file=sys.stderr)
            return 2
        if ans not in ("y", "yes"):
            print("aborted")
            return 1
    for t in existing:
        (d / t).unlink()
    tail = "" if args.all else "  (keys kept — add --all to remove secrets.json too)"
    print(f"reset: removed {', '.join(existing)} from {d}.{tail}")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    from .config import load_sandbox_policy
    from .fence import AutonomyPolicy
    cmd = args.backend_cmd.split() if args.backend_cmd else None
    rep = probe(cmd)
    out = rep.to_dict()
    out["sandbox_policy"] = load_sandbox_policy().value
    out["autonomy_ceiling"] = AutonomyPolicy.from_env().ceiling().name
    if cmd is None:
        out["status"] = "no backend configured"
        print(json.dumps(out, indent=2))
        return 0
    print(json.dumps(out, indent=2))
    return 0 if rep.ok else 1


# ----------------------------------------------------------------- tier config
# DTC tier-abstraction: `charon tier` subcommands wire the CLI to the TIER-1
# config API (config.load_tiers / set_tiers / resolve_tier / tier_members /
# tier_rank). Two commands are fleet-critical machine-parseable entrypoints:
#   `ranks`   — consumed by claim.sh (TIER-5) ONCE before flock; one line per
#               canonical+alias name: "<name> <rank>" (canonical AND aliases).
#   `resolve` — consumed by fleet-droid.sh (TIER-6) to turn a tier arg into the
#               cheapest Anthropic-API-runnable concrete model id for `claude -p`.
# All commands degrade gracefully: absent tiers.json → legacy behavior.


def _tier_init() -> int:
    from . import config
    try:
        config.set_tiers(
            order=["low", "med", "high"],
            members={"low": ["haiku"], "med": ["sonnet"], "high": ["opus"]},
            aliases={"opus": "high", "sonnet": "med", "haiku": "low",
                     "frontier": "high", "strong": "med", "economy": "low"},
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print("tiers initialized (low/med/high → haiku/sonnet/opus + legacy aliases)")
    return 0


def _tier_ranks() -> int:
    from . import config
    tiers = config.load_tiers()
    order = tiers.get("order", list(config.CANONICAL_TIERS))
    aliases = tiers.get("aliases", {})
    for i, t in enumerate(order, 1):
        print(f"{t} {i}")
    for alias, canon in sorted(aliases.items()):
        rank = order.index(canon) + 1 if canon in order else 0
        if rank > 0:
            print(f"{alias} {rank}")
    return 0


def _tier_list() -> int:
    from . import config
    tiers = config.load_tiers()
    order = tiers.get("order", [])
    members = tiers.get("members", {})
    aliases = tiers.get("aliases", {})
    for i, t in enumerate(order, 1):
        ms = ", ".join(members.get(t, []))
        print(f"[{i}] {t}: {ms or '(none)'}")
    if aliases:
        print("aliases:", " ".join(f"{a}→{v}" for a, v in sorted(aliases.items())))
    return 0


def _tier_resolve(tier_name: str, executor: str | None) -> int:
    from . import config
    try:
        tiers = config.load_tiers()
        members = config.tier_members(tier_name, tiers)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not members:
        print(f"error: tier {tier_name!r} has no members", file=sys.stderr)
        return 1
    models = config.load_models()

    def _is_anthropic(mid: str) -> bool:
        if mid in models:
            return models[mid].get("provider") == "anthropic"
        # not in registry → assumed native Anthropic model name (haiku/sonnet/opus)
        return True

    def _cost_key(mid: str) -> int:
        m = models.get(mid, {})
        if m.get("free"):
            return 0
        return int(m.get("cost_rank", 1000))

    candidates = list(members)
    if executor and executor.lower() == "anthropic":
        candidates = [m for m in candidates if _is_anthropic(m)]

    if not candidates:
        print(f"error: no {executor!r}-runnable member in tier {tier_name!r}",
              file=sys.stderr)
        return 1

    print(sorted(candidates, key=_cost_key)[0])
    return 0


def _tier_set(tier_name: str, members_str: str | None) -> int:
    from . import config
    try:
        tiers = config.load_tiers()
        canon = config.resolve_tier(tier_name, tiers)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    order = tiers["order"]
    cur_members = dict(tiers["members"])
    cur_aliases = tiers["aliases"]
    if members_str is not None:
        cur_members[canon] = [m.strip() for m in members_str.split(",") if m.strip()]
    try:
        config.set_tiers(order=order, members=cur_members, aliases=cur_aliases)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"tier {canon!r} updated")
    return 0


def _cmd_tier(args: argparse.Namespace) -> int:
    action = args.tier_action
    if action == "init":
        return _tier_init()
    if action == "ranks":
        return _tier_ranks()
    if action == "list":
        return _tier_list()
    if action == "resolve":
        return _tier_resolve(args.tier_name, getattr(args, "executor", None))
    if action == "set":
        return _tier_set(args.tier_name, getattr(args, "members", None))
    return 2


# ----------------------------------------------------------------- work engine
# The OPT-IN native work-engine end-to-end (ADR-0010): a unit plan → board →
# scheduler (each unit through the SINGLE fenced ``coordinator.run``) →
# propose-default land → top-level end-product validation. Everything engine-side
# is imported LAZILY inside the command body so it never lands on a module-load
# path — the gateway boundary guard (test_boundary.py) stays green and ``charon
# work`` is one more opt-in orchestrator consumer on the shared core (D001/D011).

_WORK_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug_id(title: str, used: set[str]) -> str:
    """A board/ledger-safe unit id from a free-text title, deduped against
    ``used``. Mirrors intake's id scheme for the consumer-units fallback."""
    from .ledger import validate_task_id
    base = _WORK_SLUG_RE.sub("-", title.lower()).strip("-")[:48]
    if not base or not base[0].isalnum():
        base = ("u-" + base).strip("-") or "unit"
    candidate, n = base, 2
    while candidate in used:
        candidate = f"{base[:60]}-{n}"
        n += 1
    validate_task_id(candidate)
    used.add(candidate)
    return candidate


def _load_plan(plan_path: str) -> tuple[list[dict], str]:
    """Load a unit plan into ``(units, product_acceptance)``.

    Accepts either an **intake plan JSON** (``schema: charon-intake-plan/…`` — the
    richer artifact with ids, ``owns``, ``depends_on`` and a top-level
    ``product_acceptance``), or a **consumer units file** (TOML/JSON of
    ``{goal, accept, tier, owned_paths}`` via ``land.load_units``) for which ids
    are synthesized and there is no top-level acceptance."""
    p = Path(plan_path)
    if not p.is_file():
        raise ValueError(f"plan/units file not found: {plan_path}")
    data: Any = None
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
    elif p.suffix.lower() not in (".toml",):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = None
    if isinstance(data, dict) and str(data.get("schema", "")).startswith(
        "charon-intake-plan"
    ):
        units: list[dict] = []
        for u in data.get("units", []):
            units.append({
                "id": u["id"],
                "tier": u.get("tier", ""),
                "owns": list(u.get("owns") or u.get("owned_paths") or []),
                "depends_on": list(u.get("depends_on", [])),
                "goal": u.get("goal", ""),
                "accept": list(u.get("accept", [])),
            })
        if not units:
            raise ValueError("intake plan has no loadable units")
        return units, str(data.get("product_acceptance", ""))
    # Fallback: a consumer-supplied units file (no ids/deps/top-level acceptance).
    from . import land
    used: set[str] = set()
    units = []
    for d in land.load_units(plan_path):
        units.append({
            "id": _slug_id(d["goal"], used),
            "tier": d.get("tier", ""),
            "owns": list(d.get("owned_paths", [])),
            "depends_on": [],
            "goal": d["goal"],
            "accept": list(d["accept"]),
        })
    return units, ""


def _engine_options(state_dir: Path, overrides: dict | None) -> dict:
    """Read engine options GENERICALLY (ADR-0010): an optional
    ``<state-dir>/engine.json`` object overlaid by CLI ``overrides``. Forwarded to
    the limiter + scheduler via ``.get()`` lookups, so a later ticket adds an
    option (capacity tuning, ``auto_land``, …) by writing a key — cli.py need not
    change."""
    opts: dict = {}
    p = state_dir / "engine.json"
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"engine.json is not readable JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("engine.json must be a JSON object of engine options")
        opts.update(data)
    if overrides:
        opts.update({k: v for k, v in overrides.items() if v is not None})
    return opts


def _prepare_base_repo(repo: str | None, state_dir: Path) -> Path:
    """The shared base repo per-unit worktrees are cut from. A real ``--repo`` is
    used as-is; otherwise a fresh sandbox base repo (the demo path). One shared
    object store is what lets the integrated end-product be assembled from each
    unit's blessed commit (D-E6-3)."""
    from . import gitutil
    if repo:
        base = Path(repo).resolve()
        if not gitutil.is_repo(base):
            raise ValueError(f"--repo {base} is not a git repository")
        return base
    base = (state_dir / "base" / "repo").resolve()
    if base.exists() and gitutil.is_repo(base):
        return base
    base.mkdir(parents=True, exist_ok=True)
    gitutil.init_repo(base)
    return base


def _default_backend_factory(
    backend_name: str, acp_cmd: str | None
) -> Callable[..., Any]:
    """Build the warm worker(s) for a unit by reusing the SAME backend resolution
    the ``charon run`` path uses (mock|acp|cross-vendor). A fresh instance per unit
    (CONC-3); the fenced ``CoordinatorRunner`` kills them on the way out."""
    def factory(unit: Any, checks: Any) -> Any:
        return api._resolve_backends(None, None, backend_name, checks, acp_cmd)
    return factory


def _integrate(base: Path, done_tips: list[tuple[Any, str]], state_dir: Path) -> str:
    """Assemble the integrated end-product into ONE worktree off ``base`` by
    materializing each DONE unit's blessed owned files from its commit. Owns are
    disjoint (the board/intake invariant) so there is never a conflict; a path
    absent from a commit is simply skipped."""
    from . import gitutil
    integ = (state_dir / "integration" / "repo").resolve()
    if integ.exists():
        gitutil.remove_worktree(base, integ)
    gitutil.add_worktree(base, integ, gitutil.head(base))
    for unit, tip in done_tips:
        for path in unit.owns:
            subprocess.run(
                ["git", "-C", str(integ), "checkout", tip, "--", path],
                capture_output=True, text=True,
            )
    return str(integ)


def run_work(
    plan_path: str,
    *,
    repo: str | None = None,
    state_dir: str = api.DEFAULT_STATE_DIR,
    backend_name: str = "mock",
    acp_cmd: str | None = None,
    autonomy: str = "L1",
    engine_overrides: dict | None = None,
    backend_factory: Callable[..., Any] | None = None,
    runner: Any | None = None,
) -> dict:
    """Drive the opt-in work-engine end-to-end and return a JSON-able report.

    Plan → seed :class:`engine.board.Board` → :class:`engine.scheduler.Scheduler`
    drains it, each unit driven through the SINGLE fenced ``coordinator.run`` (the
    default :class:`CoordinatorRunner`; never a second dispatch path, D008) → each
    DONE unit through the propose-default land gate → the D12 validator runs ONCE
    on the integrated end-product against the top-level acceptance (D-E6-6).

    ``runner``/``backend_factory`` are test seams; production uses the default
    fenced runner + the ``charon run`` backend resolution."""
    from . import gitutil, land
    from .engine.board import DONE, Board, Unit
    from .engine.capacity import select_limiter
    from .engine.scheduler import CoordinatorRunner, Scheduler
    from .ledger import Ledger
    from .validate import validate_product

    sdir = Path(state_dir).resolve()
    sdir.mkdir(parents=True, exist_ok=True)
    units, product_acceptance = _load_plan(plan_path)
    opts = _engine_options(sdir, engine_overrides)

    base = _prepare_base_repo(repo, sdir)
    base_head = gitutil.head(base)

    board_path = sdir / "work-board.json"
    if board_path.exists():
        board_path.unlink()
    board = Board.create(board_path)
    for u in units:
        board.add(Unit(
            id=u["id"], tier=u.get("tier", ""), owns=list(u.get("owns", [])),
            depends_on=list(u.get("depends_on", [])), goal=u.get("goal", ""),
            accept=list(u.get("accept", [])),
        ))

    def _wt(unit: Unit) -> str:
        dest = sdir / "work" / unit.id / "repo"
        if dest.exists():
            gitutil.remove_worktree(base, dest)
        gitutil.add_worktree(base, dest, base_head)
        return str(dest)

    if runner is None:
        bf = backend_factory or _default_backend_factory(backend_name, acp_cmd)
        runner = CoordinatorRunner(
            state_dir=str(sdir), backend_factory=bf, autonomy=autonomy
        )

    limiter = select_limiter(
        policy=str(opts.get("capacity_policy", "fixed")),
        caps=opts.get("caps"),
        default=int(opts.get("default_cap", 1)),
        aimd=opts.get("aimd"),
    )
    claims_dir = sdir / "claims"
    claims_dir.mkdir(parents=True, exist_ok=True)
    sched = Scheduler(
        board, claims_dir, runner, worktree_factory=_wt, state_dir=str(sdir),
        limiter=limiter, max_parallel=int(opts.get("max_parallel", 4)),
        max_cost_usd=opts.get("max_cost_usd"), max_tokens=opts.get("max_tokens"),
        max_attempts=int(opts.get("max_attempts", 1)),
    )
    drain = sched.drain()

    # ``auto_land`` is read generically for later tickets; the trust-extending
    # behavior stays gated (ADR-0010 D5), so the default reports proposals only.
    auto_land = bool(opts.get("auto_land", False))

    by_id = {r.unit_id: r for r in drain.results}
    unit_reports: list[dict] = []
    done_tips: list[tuple[Any, str]] = []
    for bu in board.units():
        res = by_id.get(bu.id)
        rep: dict = {
            "unit_id": bu.id,
            "status": res.status if res else "not-run",
            "disposition": res.disposition.value if res else "n/a",
            "board_state": bu.state,
            "note": res.note if res else "",
            "land": None,
        }
        if bu.state == DONE:
            ledger = Ledger.load(sdir, bu.id)
            rep["land"] = land.land_unit(ledger, list(bu.owns)).to_dict()
            if ledger.lkg_ref:
                done_tips.append((bu, ledger.lkg_ref))
        unit_reports.append(rep)

    integ = _integrate(base, done_tips, sdir)
    validation = validate_product(product_acceptance, integ)

    return {
        "board_path": str(board_path),
        "rounds": drain.rounds,
        "budget_capped": drain.budget_capped,
        "auto_land": auto_land,
        "product_acceptance": product_acceptance,
        "integration_worktree": integ,
        "units": unit_reports,
        "validation": asdict(validation),
    }


def _cmd_work(args: argparse.Namespace) -> int:
    if args.sandbox:
        os.environ["CHARON_SANDBOX"] = args.sandbox
    is_mock = args.backend == "mock"
    if is_mock:
        print(
            "mock backend makes no changes — pass --backend acp "
            "--acp-cmd '<agent> acp' for real work",
            file=sys.stderr,
        )
    overrides = {
        "max_parallel": args.max_parallel,
        "capacity_policy": args.capacity_policy,
        "default_cap": args.default_cap,
        "max_cost_usd": args.max_cost_usd,
        "max_tokens": args.max_tokens,
    }
    try:
        out = run_work(
            args.units,
            repo=args.repo,
            state_dir=args.state_dir,
            backend_name=args.backend,
            acp_cmd=args.acp_cmd,
            autonomy=args.autonomy,
            engine_overrides=overrides,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2))
    ok = out["validation"]["passed"] and all(
        u["status"] == "complete" for u in out["units"]
    )
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="charon", description="Thin cross-vendor agent orchestrator")
    p.add_argument("--version", action="version", version=f"charon {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run a goal to executable acceptance")
    r.add_argument("--goal", default=None,
                   help="the work goal (required unless --units is given)")
    r.add_argument("--accept", action="append", default=None,
                   help="executable acceptance check (repeatable); exit 0 == verified "
                        "(required unless --units is given)")
    r.add_argument("--units", default=None,
                   help="consumer-supplied unit list (TOML/JSON of {goal, accept, "
                        "tier, owned_paths}) fanned out through the parallel run "
                        "path (ADR-0007 D3); ignores --goal/--accept")
    r.add_argument("--max-parallel", type=int, default=4,
                   help="max concurrent units when running a --units list")
    r.add_argument("--repo", default=None, help="target git repo (default: a sandbox)")
    r.add_argument("--state-dir", default=api.DEFAULT_STATE_DIR)
    r.add_argument("--backend", default="mock",
                   help="backend name(s); comma-separated configures multiple "
                        "vendors for cross-vendor handoff (e.g. mock-a,mock-b)")
    r.add_argument("--autonomy", default="L0", choices=["L0", "L1", "L2", "L3"],
                   help="L2+ requires the Mode-B container (CHARON_CONTAINER_VERIFIED=1)")
    r.add_argument("--review", default=None, choices=["pass", "block", "error"],
                   help="consensus reviewer for L2 (demo mock; real reviewer is gated)")
    r.add_argument("--acp-cmd", default=None,
                   help="launch argv for a real ACP agent backend, e.g. 'opencode acp'")
    r.add_argument("--proxy-upstream", default=None,
                   help="route the agent's model calls through Charon's observing "
                        "proxy to this OpenAI-compat base, e.g. https://opencode.ai/zen/go/v1")
    r.add_argument("--proxy-key-env", default=None,
                   help="env var holding the upstream key (held by the proxy, not the agent)")
    r.add_argument("--acp-model", default=None,
                   help="model id the agent is pinned to through the proxy, e.g. kimi-k2.7-code")
    r.add_argument("--role", default=None,
                   help="run a role's model-pool with cost-first live failover "
                        "(from .charon/models.json + pools.json); needs --acp-cmd")
    r.add_argument("--budget", type=int, default=8, help="max checkpoints")
    r.add_argument("--max-cost-usd", type=float, default=None,
                   help="cumulative cost cap (USD). Honest guarantee is BOUNDED "
                        "OVERSHOOT: new dispatches halt once the running total "
                        "reaches the cap, so the final total can exceed it by up "
                        "to one in-flight checkpoint per active unit — not to the "
                        "cent. Across parallel units the cap is the shared set-level "
                        "total (PERF-4).")
    r.add_argument("--max-tokens", type=int, default=None,
                   help="cumulative token cap; same bounded-overshoot semantics as "
                        "--max-cost-usd")
    r.add_argument("--decompose", action="store_true",
                   help="drive the goal through the sequential role-DAG "
                        "(Triage→Plan→Implement→Review→Validate→Close) instead of "
                        "the plain single-unit loop — one ledger, role-tagged "
                        "checkpoints (PERF-4/D5)")
    r.add_argument("--sandbox", default=None,
                   choices=["hybrid", "container", "host"],
                   help="sandbox posture: hybrid (default) | container (require "
                        "CHARON_CONTAINER_VERIFIED for all rungs) | host (host ok, "
                        "loud override still required for L2+) — D013/ADR-0010")
    r.set_defaults(func=_cmd_run)

    ld = sub.add_parser("land",
                        help="run the propose-default land gate on a completed unit "
                             "and PROPOSE (open a PR); never auto-merges (ADR-0007 D4/D6)")
    ld.add_argument("task_id", help="the completed unit's ledger/task id")
    ld.add_argument("--state-dir", default=api.DEFAULT_STATE_DIR)
    ld.add_argument("--owned", action="append", default=None,
                    help="a declared owned path (repeatable); a write outside ALL "
                         "owned paths holds the unit (diff-scope guard)")
    ld.add_argument("--units", default=None,
                    help="units file to pull this unit's owned_paths from (matched "
                         "by goal), instead of repeated --owned flags")
    ld.add_argument("--tip", default=None,
                    help="commit to land (default: the ledger's lkg_ref)")
    ld.add_argument("--base-ref", default=None,
                    help="base to diff against (default: the ledger's base_ref)")
    ld.add_argument("--tests", default=None,
                    help="extra test command to run in the worktree (exit 0 == pass)")
    ld.add_argument("--require-gitleaks", action="store_true",
                    help="fail closed (hold) if gitleaks is not installed")
    ld.add_argument("--open-pr", action="store_true",
                    help="when the gate is green, open a draft PR (needs --branch); "
                         "NEVER merges")
    ld.add_argument("--branch", default=None, help="the unit's branch to propose")
    ld.add_argument("--base", default="master", help="PR base branch (default: master)")
    ld.add_argument("--repo-slug", default=None,
                    help="owner/name for `gh pr create --repo` (default: gh infers it)")
    ld.set_defaults(func=_cmd_land)

    wk = sub.add_parser(
        "work",
        help="run the OPT-IN native work-engine end-to-end: a unit plan → board → "
             "scheduler (each unit through the fenced coordinator.run) → "
             "propose-default land → end-product validation (ADR-0010; opt-in "
             "orchestrator, never on the gateway path)")
    wk.add_argument("--units", required=True,
                    help="a unit plan: an intake plan JSON (charon-intake-plan) or "
                         "a consumer units file (TOML/JSON of {goal, accept, tier, "
                         "owned_paths})")
    wk.add_argument("--repo", default=None,
                    help="git repo to cut per-unit worktrees from (default: a "
                         "sandbox base repo under the state dir)")
    wk.add_argument("--state-dir", default=api.DEFAULT_STATE_DIR)
    wk.add_argument("--backend", default="mock",
                    help="each unit's warm worker backend (mock|acp); comma-"
                         "separated configures cross-vendor handoff")
    wk.add_argument("--acp-cmd", default=None,
                    help="launch argv for a real ACP agent backend, e.g. 'opencode acp'")
    wk.add_argument("--autonomy", default="L1", choices=["L0", "L1", "L2", "L3"],
                    help="per-unit autonomy (default L1: keep + land changes; "
                         "L2+ requires the Mode-B container)")
    wk.add_argument("--max-parallel", type=int, default=None,
                    help="max concurrent units (overrides engine.json)")
    wk.add_argument("--capacity-policy", default=None, choices=["fixed", "aimd"],
                    help="per-tier capacity limiter policy (default fixed; aimd is "
                         "gated/opt-in, DECISIONS D004)")
    wk.add_argument("--default-cap", type=int, default=None,
                    help="default per-tier concurrency cap for the fixed limiter")
    wk.add_argument("--max-cost-usd", type=float, default=None,
                    help="shared (set-level) cost cap in USD; bounded-overshoot")
    wk.add_argument("--max-tokens", type=int, default=None,
                    help="shared (set-level) token cap; bounded-overshoot")
    wk.add_argument("--sandbox", default=None,
                    choices=["hybrid", "container", "host"],
                    help="sandbox posture (D013/ADR-0010)")
    wk.set_defaults(func=_cmd_work)

    g = sub.add_parser("gateway",
                       help="run the standalone OpenAI-compatible failover gateway")
    g.add_argument("--config", default=None,
                   help="charon.toml config file (takes precedence over --state-dir)")
    g.add_argument("--state-dir", default=None,
                   help="dir holding models/pools/providers.json (default: the "
                        "user config dir ~/.charon; used when --config is absent)")
    g.add_argument("--host", default=None, help="bind host (default 127.0.0.1)")
    g.add_argument("--port", type=int, default=None, help="bind port (default 8080)")
    g.add_argument("--token", default=None,
                   help="bearer token (or set CHARON_GATEWAY_TOKEN); REQUIRED to "
                        "bind a non-loopback host")
    g.set_defaults(func=_cmd_gateway)

    pv = sub.add_parser("providers",
                        help="configure providers + API keys (stored 0600, never in the repo)")
    pvsub = pv.add_subparsers(dest="action", required=True)
    pvsub.add_parser("list", help="list provider presets and which keys are set")
    pa = pvsub.add_parser("add", help="store an API key for a provider")
    pa.add_argument("name", help="preset name (openrouter, nanogpt, …) or a custom name")
    pa.add_argument("--key", help="the API key (omit to be prompted WITHOUT echo)")
    pa.add_argument("--key-env", help="override the env-var name to store the key under")
    pa.add_argument("--base-url", help="base URL for a custom (non-preset) provider")
    pt = pvsub.add_parser("test", help="probe a provider's base URL (verifies it resolves)")
    pt.add_argument("name")
    pt.add_argument("--base-url")
    pv.set_defaults(func=_cmd_providers)

    su = sub.add_parser("setup", help="guided gateway setup (providers, keys, models, pool)")
    su.set_defaults(func=_cmd_setup)

    md = sub.add_parser("models", help="manage the model catalog")
    mdsub = md.add_subparsers(dest="action", required=True)
    mi = mdsub.add_parser("import",
                          help="import a provider's full model list into the catalog")
    mi.add_argument("name", help="provider name (a preset or one you've added)")
    mi.add_argument("--free-only", action="store_true", help="import only free models")
    mi.add_argument("--into-pool", default=None,
                    help="ALSO add the imported models to this pool (opt-in; pools work "
                         "best small + cost-ranked, so this is rarely what you want)")
    md.set_defaults(func=_cmd_models)

    rs = sub.add_parser("reset",
                        help="remove local config (providers/models/pools); --all also drops keys")
    rs.add_argument("--all", action="store_true",
                    help="also delete secrets.json (your stored API keys)")
    rs.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    rs.set_defaults(func=_cmd_reset)

    lg = sub.add_parser("ledger", help="show a task's derived ledger state")
    lg.add_argument("task_id")
    lg.add_argument("--state-dir", default=api.DEFAULT_STATE_DIR)
    lg.set_defaults(func=_cmd_ledger)

    d = sub.add_parser("doctor", help="probe a real ACP backend (Tier-0)")
    d.add_argument("--backend-cmd", default=None, help='e.g. "claude-code acp"')
    d.set_defaults(func=_cmd_doctor)

    t = sub.add_parser("tier", help="manage model-tier config (low/med/high + aliases)")
    tsub = t.add_subparsers(dest="tier_action", required=True)
    tsub.add_parser("init",
                    help="seed tiers.json with backward-compat defaults "
                         "(order=low/med/high, legacy aliases, Anthropic day-one members)")
    ts = tsub.add_parser("set", help="update a tier's members")
    ts.add_argument("tier_name", help="canonical tier (low|med|high) or alias")
    ts.add_argument("--members", default=None,
                    help="comma-separated model ids (replaces current list)")
    tsub.add_parser("list", help="show tier config (human-readable)")
    tsub.add_parser("ranks",
                    help="print canonical+alias rank rows for fleet parsing, "
                         'e.g. "low 1\\nmed 2\\nhigh 3\\nopus 3\\n..." (TIER-5 contract)')
    trv = tsub.add_parser("resolve",
                          help="resolve a tier to its cheapest runnable model id "
                               "(for fleet-droid.sh TIER-6; machine-parseable stdout)")
    trv.add_argument("tier_name", help="canonical tier (low|med|high) or alias")
    trv.add_argument("--executor", default=None,
                     help="filter by executor (anthropic); exit non-zero if none found "
                          "so shell || fallbacks fire")
    t.set_defaults(func=_cmd_tier)

    v = sub.add_parser("version", help="print version")
    v.set_defaults(func=lambda a: (print(__version__), 0)[1])
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
