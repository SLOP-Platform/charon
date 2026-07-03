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
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import __version__, api
from .doctor import probe


def _invocation_name() -> str:
    """The name the user invoked this process as (sys.argv[0]), defaulting to
    'charon' in non-interactive/test environments where argv[0] is 'pytest' or
    similar."""
    name = sys.argv[0]
    base = os.path.basename(name)
    if base.startswith("python") or "/pytest" in name or base == "pytest" or base == "-c":
        return "charon"
    return name


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


def _cmd_gate(args: argparse.Namespace) -> int:
    from .gate_runner import run_gate
    return run_gate()


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
                  f"with `{_invocation_name()} providers add {args.name}`", file=sys.stderr)
            return 2
        path = secrets.set_secret(key_env, value)
        print(f'stored {key_env} in {path} (0600) {_mask_key(value)}'
              f' + provider "{args.name}" in config.')
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
    _META_KEYS = ("context_window", "max_tokens", "reasoning", "vision", "audio")
    entries = []
    for m in found:
        entry = {"id": m["id"], "free": m["free"],
                 "cost_rank": 0 if m["free"] else 1000}
        for k in _META_KEYS:
            if k in m:
                entry[k] = m[k]
        entries.append(entry)
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


def _import_all_models(free_only: bool = False, into_pool: str | None = None,
                       quiet: bool = False) -> dict[str, tuple[list[str], list[str]] | None]:
    """Import models from every configurable provider that has an API key set
    (or is a localhost provider needing no key). Returns ``{provider: result}``."""
    from . import config, providers
    results: dict[str, tuple[list[str], list[str]] | None] = {}
    all_presets = set(providers.PRESETS)
    custom = set(config.load_providers())
    candidates = all_presets | custom
    for name in sorted(candidates):
        try:
            preset = providers.resolve(name, config.load_providers().get(name))
        except ValueError:
            continue
        if preset.key_env and preset.key_env not in os.environ:
            continue  # no key set — skip silently
        res = _import_models(name, free_only=free_only, into_pool=None, quiet=True)
        if res is not None:
            results[name] = res
    if into_pool and results:
        all_added: list[str] = []
        for v in results.values():
            if v is not None:
                all_added.extend(v[0])
        if all_added:
            config.set_pool(into_pool, all_added)
            if not quiet:
                print(f"pool {into_pool!r} now holds all {len(all_added)} imported models "
                      "— pools work best as a small, cost-ranked, comparable set")
    if not quiet:
        total_added = sum(len(v[0]) for v in results.values() if v)
        total_skipped = sum(len(v[1]) for v in results.values() if v)
        print(f"import-all: {total_added} model(s) from {len(results)} provider(s)"
              + (f", skipped {total_skipped} invalid id(s)" if total_skipped else ""))
    return results


def _cmd_models(args: argparse.Namespace) -> int:
    from . import secrets
    secrets.apply_to_env()
    if args.action == "import":
        if args.all:
            all_results = _import_all_models(free_only=args.free_only, into_pool=args.into_pool)
            return 0 if all_results else 1
        if not args.name:
            print("error: specify a provider name or use --all", file=sys.stderr)
            return 2
        res = _import_models(args.name, free_only=args.free_only, into_pool=args.into_pool)
        return 0 if res is not None else 1
    return 2


def _ansi_emph(text: str) -> str:
    """Bold-cyan ``text`` for an interactive TTY; plain on ``NO_COLOR`` (any value),
    a non-TTY stdout, or ``TERM=dumb``. Stdlib-only — no new dependency."""
    if os.environ.get("NO_COLOR") is not None:
        return text
    if os.environ.get("TERM") == "dumb":
        return text
    if not sys.stdout.isatty():
        return text
    return f"\x1b[1;36m{text}\x1b[0m"


def _mask_key(key: str) -> str:
    """Safe representation: length + last 4 chars. Short keys echo in quotes."""
    if not key:
        return ""
    if len(key) <= 4:
        return f"({len(key)} chars, ends in {key!r})"
    return f"({len(key)} chars, ends in ...{key[-4:]})"


def _probe_key(preset: object, api_key: str) -> str | None:
    """Probe a provider with a minimal chat completion to validate the key.
    Returns None on success, or an error message string on failure.
    Security: refuses non-http(s) and link-local bases (SSRF guard)."""
    import urllib.error
    import urllib.request
    from urllib.parse import urlsplit

    base = getattr(preset, "base_url", None)
    if not base:
        return None
    parts = urlsplit(base)
    if parts.scheme not in ("http", "https"):
        return f"refusing non-http(s) base {parts.scheme!r}"
    host = parts.hostname or ""
    if host.startswith("169.254.") or host == "metadata.google.internal":
        return "refusing link-local / metadata host"

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener(_NoRedirect())
    raw_base = base.rstrip("/")
    body = json.dumps({
        "model": ".",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
    }).encode()
    try:
        req = urllib.request.Request(raw_base + "/chat/completions", data=body, method="POST")
        req.add_header("User-Agent", "charon-proxy/0.1")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + api_key)
        resp = opener.open(req, timeout=15.0)
        resp.read(1024)
        return None  # success
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return f"key rejected (HTTP {exc.code})"
        return f"probe failed (HTTP {exc.code})"
    except Exception:  # noqa: S112 — network probe, any transport error is handled
        return "provider unreachable or probe timed out"


def _cmd_setup(args: argparse.Namespace) -> int:
    """Guided setup: add providers (+ keys), models, and an optional failover pool —
    all written to the user config dir so `charon gateway` then just works."""
    import getpass

    from . import config, providers, secrets

    def ask(msg: str, default: str = "") -> str:
        suffix = f" [{default}]" if default else ""
        return (input(f"{msg}{suffix}: ").strip() or default)

    def catalog_for(provider: str) -> list[str]:
        """Model ids already in the CATALOG (models.json) for ``provider`` — exactly
        what ``_import_models`` writes. The required, offline source of truth."""
        return [m for m, e in config.load_models().items()
                if isinstance(e, dict) and e.get("provider") == provider]

    try:
        print("Charon setup — configure providers, keys, models, and a failover pool.")
        print(f"(config → {secrets.config_dir()};  keys → secrets.json at 0600)")
        print("(Ctrl-C cancels anytime; 'done' or a blank Enter finishes a step)")
        print(_ansi_emph("Presets: " + ", ".join(sorted(providers.PRESETS))))
        added_models: list[str] = []
        configured: list[str] = []  # providers added this run (for the 0-served guard)
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
            configured.append(name)
            stored = False
            if key_env:
                key = getpass.getpass(f"  paste the API key for {name} [blank to skip]: ")
                if key:
                    secrets.set_secret(key_env, key)
                    stored = True
                    print(f"  key stored (0600, as {key_env}) {_mask_key(key)}")
                    err = _probe_key(preset, key)
                    if err:
                        print(f"  WARNING: key check failed — {err}", file=sys.stderr)
                    else:
                        print("  key validated")
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
            # surface what the catalog already holds for this provider so the user
            # picks from REAL ids instead of typing one blind, and offer a one-shot
            # "serve all" that wires them into the served set (TIER-RECS Phase A).
            catalog = catalog_for(name)
            if catalog:
                models_now = config.load_models()
                shown = catalog[:20]
                print(f"  {len(catalog)} model(s) imported for '{name}':")
                for m in shown:
                    free = bool((models_now.get(m) or {}).get("free"))
                    print(f"    - {m}{' (free)' if free else ''}")
                if len(catalog) > len(shown):
                    print(f"    … and {len(catalog) - len(shown)} more")
                if ask(f"  serve all {len(catalog)} imported model(s)? "
                       "(else pick/enter ids below)", "y").lower().startswith("y"):
                    for m in catalog:
                        if m not in added_models:
                            added_models.append(m)
                    print(f"    serving {len(catalog)} model(s) from '{name}'")
                    continue  # served whole catalog — skip the manual id loop
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
        # 0-served guard: never finish on a silently non-serving gateway. If nothing
        # was wired into the served set, offer to serve the catalog imported above.
        if not added_models:
            pending = [m for p in configured for m in catalog_for(p)]
            if pending and ask(
                    f"\n⚠ 0 models served. Serve all {len(pending)} imported model(s) now?",
                    "y").lower().startswith("y"):
                for m in pending:
                    if m not in added_models:
                        added_models.append(m)
                print(f"  serving {len(added_models)} model(s)")
        if len(added_models) >= 2 and ask(
                "\nGroup these models into a failover pool?", "y").lower().startswith("y"):
            vid = ask("  pool name (the id clients request for auto-failover)", "auto")
            config.set_pool(vid, added_models)
            print(f"  pool '{vid}' = {added_models} (auto-ordered free-first)")
    except KeyboardInterrupt:
        print("\nsetup cancelled — anything you already added is saved.", file=sys.stderr)
        return 0
    except EOFError:
        print(f"\nsetup needs an interactive terminal. "
              f"Use `{_invocation_name()} providers add <name>` "
              f"or edit the files in {secrets.config_dir()}.", file=sys.stderr)
        return 2
    if not added_models:
        # The gateway serves EVERY model in the catalog (models.json) by id, so a
        # non-empty catalog means clients CAN still reach a model — the loud "won't
        # respond" warning would be wrong. Only warn when there's truly nothing to
        # serve (empty catalog); otherwise print an accurate note.
        catalog_n = sum(1 for e in config.load_models().values()
                        if isinstance(e, dict))
        if not catalog_n:
            print(f"\n⚠ 0 models served — your gateway won't respond to requests.\n"
                  f"  Import a provider's catalog with "
                  f"`{_invocation_name()} models import <provider>`, "
                  f"or\n  re-run `{_invocation_name()} setup` "
                  f"and serve a model when prompted.",
                  file=sys.stderr)
            return 0
        print(f"\n{catalog_n} model(s) in your catalog are served by id; no failover "
              "pool set — clients can request them directly.")
        return 0
    print(f"\nDone. {len(added_models)} model(s) configured. Start the gateway:\n"
          f"  {_invocation_name()} gateway")
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


def _cmd_connect(args: argparse.Namespace) -> int:
    """`charon connect <client>` — verify the gateway, discover a model, optionally
    install the client, and write its provider config pointing at the gateway."""
    from . import connect, secrets
    secrets.apply_to_env()  # let a stored CHARON_GATEWAY_TOKEN resolve like elsewhere
    return connect.run_connect(
        client=args.client,
        host=args.host,
        port=args.port,
        model=args.model,
        token=args.token,
        install=args.install,
        yes=args.yes,
    )


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
        # Vendor-specific executor filter — this is the only executor currently
        # supported. Replace with a generic executor-registry lookup when more
        # executor backends are added (ATC-009).
        if mid in models:
            return models[mid].get("provider") == "anthropic"
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


def _tier_recommend(provider_name: str) -> int:
    """Recommend tier assignments for a provider's live model catalog using
    LLM-judge consensus from already-configured trusted models."""
    from . import config, providers, recommend, secrets
    secrets.apply_to_env()

    try:
        catalog = providers.list_models(provider_name)
    except Exception as exc:
        print(f"error: cannot reach {provider_name} — {exc}", file=sys.stderr)
        return 2
    if not catalog:
        print(f"no models found for provider '{provider_name}'")
        return 1

    print(f"Fetched {len(catalog)} models from {provider_name}")
    print("Asking trusted models to rank the catalog…")

    recs = recommend.recommend_tiers(provider_name, catalog)

    tier_order = ["high", "med", "low"]
    proposal: dict[str, list[str]] = {}
    for r in recs:
        if r.tier in tier_order and r.model_ids:
            proposal[r.tier] = r.model_ids

    if not any(proposal.values()):
        print("no recommendations produced")
        return 1

    for tier in tier_order:
        ids = proposal.get(tier, [])
        if ids:
            print(f"\n  {tier.upper()} ({len(ids)} models):")
            for mid in ids[:15]:
                print(f"    - {mid}")
            if len(ids) > 15:
                print(f"    … and {len(ids) - 15} more")

    try:
        ans = input("\nAccept these tier assignments? [Y/n/each]: ").strip().lower()
    except EOFError:
        print("recommend needs an interactive terminal", file=sys.stderr)
        return 2
    if ans == "" or ans.startswith("y"):
        tiers = config.load_tiers()
        for canon in tier_order:
            ids = proposal.get(canon, [])
            if ids:
                existing = list(tiers.get("members", {}).get(canon, []))
                for mid in ids:
                    if mid not in existing:
                        existing.append(mid)
                tiers.setdefault("members", {})[canon] = existing
        config.set_tiers(
            order=tiers.get("order", list(config.CANONICAL_TIERS)),
            members=tiers.get("members", {}),
            aliases=tiers.get("aliases", {}),
        )
        print("tiers updated")
    elif ans == "each":
        tiers = config.load_tiers()
        for canon in tier_order:
            ids = proposal.get(canon, [])
            if not ids:
                continue
            try:
                tier_ans = input(
                    f"  accept {canon} tier ({len(ids)} models)? [Y/n]: ").strip().lower()
            except EOFError:
                print("aborted", file=sys.stderr)
                return 2
            if tier_ans == "" or tier_ans.startswith("y"):
                existing = list(tiers.get("members", {}).get(canon, []))
                for mid in ids:
                    if mid not in existing:
                        existing.append(mid)
                tiers.setdefault("members", {})[canon] = existing
        config.set_tiers(
            order=tiers.get("order", list(config.CANONICAL_TIERS)),
            members=tiers.get("members", {}),
            aliases=tiers.get("aliases", {}),
        )
        print("tiers updated")
    else:
        print("aborted")
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
    if action == "recommend":
        return _tier_recommend(args.provider)
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
                "body": u.get("body", ""),
            })
        if not units:
            raise ValueError(_no_units_reason(data))
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
            "body": d.get("body", ""),
        })
    return units, ""


def _no_units_reason(data: dict) -> str:
    """Explain WHY an intake plan has no loadable units, surfacing the review-item
    and issue reasons instead of the dead-end ``no loadable units`` (CLIFF 2). A
    ticket with no executable ``accept:`` (and owned paths) stays propose-only by
    design (ADR-0011) — this tells the user exactly what to add to make it run."""
    review = data.get("review_items") or []
    issues = data.get("issues") or []
    parts: list[str] = []
    if review:
        n = len(review)
        detail = "; ".join(
            f"{r.get('id', '?')}: {r.get('reason') or r.get('kind', '')}"
            for r in review[:5]
        )
        more = "" if n <= 5 else f" (+{n - 5} more)"
        parts.append(
            f"{n} item(s) need an executable `accept:` command (and owned `files:`/"
            f"`owns:`) to become runnable — {detail}{more}"
        )
    if issues:
        parts.append(
            "; ".join(str(i.get("message", "")) for i in issues[:5])
        )
    if not parts:
        return "intake plan has no loadable units"
    return "intake plan has no runnable units: " + " | ".join(parts)


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


@dataclass
class _ReviewingRunner:
    """A work-path :class:`engine.scheduler.FencedRunner` that drives each unit
    through the SAME single fenced ``coordinator.run`` the default
    ``CoordinatorRunner`` uses, but ALSO threads a ``reviewer`` into it — so the
    work path gets the real cross-model review gate (consulted at L2+, recorded for
    the audit trail at every level), not just the acceptance checks.

    It lives here rather than in the scheduler so the wiring stays in the
    orchestrator layer (the scheduler is unchanged; the fence choke-point — D008,
    every unit through ``coordinator.run`` — is preserved). All engine/core
    imports are LAZY (inside ``__call__``) so engine never lands on cli.py's
    module-load path (the gateway boundary guard stays green)."""

    state_dir: str
    backend_factory: Callable[..., Any]
    reviewer: Any
    autonomy: str = "L1"
    max_checkpoints: int = 8

    def __call__(self, unit: Any, worktree: str, *, cost_gate: Any) -> Any:
        from . import coordinator, gitutil
        from .acceptance import AcceptanceCheck
        from .fence import Fence
        from .ledger import Ledger, LedgerCorruption
        from .router import StaticRouter
        from .types import Autonomy, Budget, WorkUnit
        checks = [
            AcceptanceCheck(id=f"a{i}", cmd=c) for i, c in enumerate(unit.accept)
        ]
        sdir = Path(self.state_dir).resolve()
        base_ref = gitutil.head(Path(worktree))
        try:
            ledger = Ledger.create(
                sdir, unit.id, unit.goal, checks, str(worktree), base_ref
            )
        except LedgerCorruption:
            # already exists → a RETRY: resume the durable ledger (mirrors the
            # default CoordinatorRunner, so retries are not dead).
            ledger = Ledger.load(sdir, unit.id)
        backends = self.backend_factory(unit, checks)
        router = StaticRouter(backends=list(backends))
        fence = Fence(autonomy=Autonomy[self.autonomy])
        budget = Budget(max_checkpoints=self.max_checkpoints)
        # Same bearings the default CoordinatorRunner carries: goal + body + the
        # gate's own accept checks (joined), so the work path's reviewed runner
        # hands the agent full context too — one source of truth with the gate.
        work_unit = WorkUnit(
            task_id=unit.id,
            goal=unit.goal,
            body=unit.body,
            accept_text="\n".join(unit.accept),
        )
        try:
            return coordinator.run(
                work_unit, backends, ledger, fence, router,
                reviewer=self.reviewer,
                max_checkpoints=self.max_checkpoints, budget=budget,
                cost_gate=cost_gate,
            )
        finally:
            for b in backends.values():
                try:
                    b.kill()
                except Exception:
                    pass


def build_work_runner(
    state_dir: str,
    backend_factory: Callable[..., Any],
    autonomy: str,
    *,
    reviewer: Any | None = None,
    max_checkpoints: int = 8,
) -> Any:
    """Construct the work path's fenced runner with the REAL gateway reviewer
    threaded in (ADR-0010 Tier-4). Mirrors how ``charon run`` wires a reviewer,
    but uses the loopback-gateway :class:`adapters.review.GatewayReviewer` (NOT the
    demo ``MockReviewer``): it routes via the local gateway, composing with the
    forwarded provider credentials (WORK-GATEWAY-WIRE)."""
    from .adapters.review import GatewayReviewer
    if reviewer is None:
        reviewer = GatewayReviewer()
    return _ReviewingRunner(
        state_dir=state_dir, backend_factory=backend_factory,
        reviewer=reviewer, autonomy=autonomy, max_checkpoints=max_checkpoints,
    )


def _progress_enabled(flag: bool | None, *, stdout_isatty: bool) -> bool:
    """Decide whether `charon work` emits live progress (WORK-OBSERVABILITY).

    ``--progress`` → ``True``; ``--quiet`` → ``False`` (the ``flag`` is the
    explicit choice). With neither (``flag is None``) progress is ON only for an
    interactive TTY and OFF when stdout is redirected/piped — so a piped final
    JSON is never polluted and a human at a terminal gets the running view."""
    if flag is not None:
        return flag
    return stdout_isatty


def _progress_sink() -> Callable[[str], None]:
    """A progress sink that writes one `[work] <line>` per event to STDERR (never
    stdout — stdout stays the final machine-readable JSON), flushed so the view is
    live as the run drains."""
    def emit(line: str) -> None:
        print(f"[work] {line}", file=sys.stderr, flush=True)
    return emit


def run_status(state_dir: str = api.DEFAULT_STATE_DIR) -> dict:
    """Roll up a WHOLE work run from the durable ``.charon`` state (the aggregate
    view behind ``charon runs``, WORK-OBSERVABILITY). Reads ``work-board.json`` for
    every unit's coordination state + dependencies and joins each unit's per-unit
    ledger (checkpoints / verified / remaining / lkg_ref) — the run-level summary
    the per-unit ``charon ledger <id>`` cannot give.

    PURELY read-only: verified/remaining come from the LAST recorded checkpoint
    (durable state), NOT from ``Ledger.verified()`` — which would re-EXECUTE every
    unit's acceptance commands. An observability view must never run the work it
    observes. A unit with no readable ledger (never claimed, or corrupt) still
    appears with its board state + empty ledger fields, so the rollup never
    crashes on a partial run."""
    from .engine.board import Board
    from .ledger import Ledger

    sdir = Path(state_dir).resolve()
    board_path = sdir / "work-board.json"
    if not board_path.exists():
        raise FileNotFoundError(
            f"no work run found at {board_path} (run `charon work --units …` first)"
        )
    board = Board.load(board_path)
    units: list[dict] = []
    totals: dict[str, int] = {}
    for u in board.units():
        entry: dict = {
            "unit_id": u.id,
            "tier": u.tier,
            "state": u.state,
            "depends_on": list(u.depends_on),
            "checkpoints": 0,
            "verified": [],
            "remaining": [],
            "lkg_ref": "",
        }
        try:
            led = Ledger.load(sdir, u.id)
            cps = led.checkpoints()
            entry["checkpoints"] = len(cps)
            if cps:  # last recorded verdict — durable, no command re-execution
                entry["verified"] = sorted(cps[-1].verified)
                entry["remaining"] = sorted(cps[-1].remaining)
            entry["lkg_ref"] = led.lkg_ref
        except Exception:
            pass  # never claimed / not a readable ledger — board state still stands
        totals[u.state] = totals.get(u.state, 0) + 1
        units.append(entry)
    return {"board_path": str(board_path), "totals": totals, "units": units}


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
    reviewer: Any | None = None,
    open_pr: bool = False,
    pr_opener: Callable[..., str] | None = None,
    pr_base: str = "master",
    pr_repo_slug: str | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """Drive the opt-in work-engine end-to-end and return a JSON-able report.

    Plan → seed :class:`engine.board.Board` → :class:`engine.scheduler.Scheduler`
    drains it, each unit driven through the SINGLE fenced ``coordinator.run`` (the
    default :class:`CoordinatorRunner`; never a second dispatch path, D008) → each
    DONE unit through the propose-default land gate → the D12 validator runs ONCE
    on the integrated end-product against the top-level acceptance (D-E6-6).

    ``autonomy`` (default L1, partial trust) controls the review gate: L0
    (manual) and L1 (single-model) run WITHOUT cross-model adversarial review
    (by-design — the agent's own output is trusted). L2+ threads a second model's
    GatewayReviewer into the runner (ADR-0010 Tier-4).

    ``runner``/``backend_factory``/``reviewer``/``pr_opener`` are test seams;
    production uses the default fenced runner + the ``charon run`` backend
    resolution.

    ``progress`` (WORK-OBSERVABILITY) is an opt-in sink for human-readable
    lifecycle lines (claimed/started/checkpoint/land/done) the scheduler + land
    loop emit AS the run drains; the caller routes it to stderr so stdout stays
    the final JSON. ``None`` (default) keeps the run silent until the end.

    ``open_pr`` (OFF by default, fail-closed) closes the loop: a unit the gate
    PROPOSES is published as a DRAFT PR (branch+push+PR via ``land.propose_pr``).
    When off, the work path stays read-only — no push, no PR — exactly as before.
    It NEVER auto-merges (ADR-0010 D5 propose-default)."""
    from . import gitutil, land
    from .engine.board import DONE, Board, Unit
    from .engine.capacity import select_limiter
    from .engine.scheduler import Scheduler
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
            body=u.get("body", ""),
        ))

    def _wt(unit: Unit) -> str:
        dest = sdir / "work" / unit.id / "repo"
        if dest.exists():
            gitutil.remove_worktree(base, dest)
        gitutil.add_worktree(base, dest, base_head)
        return str(dest)

    if runner is None:
        bf = backend_factory or _default_backend_factory(backend_name, acp_cmd)
        # Thread the REAL gateway reviewer into the fenced runner (ADR-0010
        # Tier-4) instead of the default reviewer-less CoordinatorRunner — the
        # work path now carries the cross-model review gate, additive to the
        # acceptance checks.
        runner = build_work_runner(str(sdir), bf, autonomy, reviewer=reviewer)

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
        progress=progress,
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
            "pr": None,
        }
        if bu.state == DONE:
            ledger = Ledger.load(sdir, bu.id)
            outcome = land.land_unit(ledger, list(bu.owns))
            rep["land"] = outcome.to_dict()
            if progress is not None:
                progress(f"{bu.id}: land:{outcome.decision}")
            # Close the loop (ADR-0010): when --open-pr is armed, a unit the gate
            # PROPOSES becomes a DRAFT PR (branch+push+PR). OFF by default →
            # read-only, exactly as before. NEVER auto-merges (D5).
            if open_pr and outcome.decision == "propose":
                opener = pr_opener or land.propose_pr
                try:
                    rep["pr"] = opener(
                        ledger, outcome, base=pr_base, repo_slug=pr_repo_slug
                    )
                except land.LandError as exc:
                    rep["note"] = (rep["note"] + "; " if rep["note"] else "") \
                        + f"pr not opened: {exc}"
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
        "open_pr": open_pr,
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
    progress = (
        _progress_sink()
        if _progress_enabled(args.progress, stdout_isatty=sys.stdout.isatty())
        else None
    )
    try:
        out = run_work(
            args.units,
            repo=args.repo,
            state_dir=args.state_dir,
            backend_name=args.backend,
            acp_cmd=args.acp_cmd,
            autonomy=args.autonomy,
            engine_overrides=overrides,
            open_pr=args.open_pr,
            pr_base=args.base,
            pr_repo_slug=args.repo_slug,
            progress=progress,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2))
    ok = out["validation"]["passed"] and all(
        u["status"] == "complete" for u in out["units"]
    )
    return 0 if ok else 1


def _cmd_runs(args: argparse.Namespace) -> int:
    """`charon runs` — the aggregate run view (WORK-OBSERVABILITY): roll up the
    WHOLE last work run from durable ``.charon`` state, where ``charon ledger
    <id>`` only shows ONE unit."""
    try:
        out = run_status(state_dir=args.state_dir)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # corrupt board etc. — surface loudly
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2))
    return 0


def _default_plan_path(src: str) -> Path:
    """Default plan-JSON destination for ``intake import``: the source file with a
    ``.plan.json`` suffix (``backlog.md`` → ``backlog.plan.json``)."""
    p = Path(src)
    return p.with_name(p.stem + ".plan.json")


def _cmd_intake(args: argparse.Namespace) -> int:
    """`charon intake import` — induct an external work-list into a reviewable
    Charon plan (the non-coder front door, ADR-0008/0011). Default posture: write
    the plan JSON + print the human-readable markdown, then STOP. ``--run`` is an
    explicit opt-in that chains into the work-engine (see the trust note below)."""
    from . import intake as intake_mod
    try:
        plan = intake_mod.intake_file(args.file, fmt=args.fmt)
    except (intake_mod.IntakeError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    out_path = Path(args.out) if args.out else _default_plan_path(args.file)
    try:
        plan.write(out_path)
    except OSError as exc:
        print(f"error: cannot write plan to {out_path}: {exc}", file=sys.stderr)
        return 2
    print(plan.to_markdown())
    print(f"plan written to {out_path}", file=sys.stderr)

    if not args.run:
        # Phase-1 posture: a proposal a human approves/edits before any run.
        return 0

    # --run (opt-in): chain into the existing work path. SECURITY: this EXECUTES
    # each unit's `accept` string in a worktree — importing-then-running EXTERNAL
    # tickets runs commands the ticket author wrote. Only --run tickets you trust.
    if not plan.units:
        print(
            f"error: {_no_units_reason(plan.to_dict())}",
            file=sys.stderr,
        )
        return 1
    if args.backend == "mock":
        print(
            "mock backend makes no changes — pass --backend acp "
            "--acp-cmd '<agent> acp' for real work",
            file=sys.stderr,
        )
    try:
        out = run_work(
            str(out_path),
            repo=args.repo,
            state_dir=args.state_dir,
            backend_name=args.backend,
            acp_cmd=args.acp_cmd,
            autonomy=args.autonomy,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2))
    ok = out["validation"]["passed"] and all(
        u["status"] == "complete" for u in out["units"]
    )
    return 0 if ok else 1


# Help epilog documenting the enrichment convention + the --run trust boundary.
_INTAKE_IMPORT_EPILOG = """\
input: a markdown work-list — one `#`-heading per work item, plus an optional
`## Product acceptance` section for the whole-product done-check.

enrichment convention (how a ticket becomes RUNNABLE, not just propose-only):
  add to an item's body, one field per line —
    id:     TICKET-42            # the source ticket's own id (preserved on import,
                                 #   so completion can be reported back to it later)
    files:  src/x.py tests/x.py  # (or `owns:`) the paths the unit owns
    accept: `pytest -q tests/x`  # an EXECUTABLE check; exit 0 == verified
    tier:   high                 # optional model tier
    depends_on: other-item       # optional ordering by id/title
  An item WITH both `accept:` and owned paths becomes a runnable unit. WITHOUT
  them it stays a propose-only review item (correct, ADR-0011) — that is how you
  opt in to runnable.

posture: default writes the plan + stops for human review (Phase-1, ADR-0008).
  --run is OFF by default.

SECURITY (--run): --run EXECUTES each unit's `accept` command in a worktree.
  Importing then running an EXTERNAL work-list runs commands the ticket author
  wrote — only --run input you trust. Without --run, intake reads input as DATA
  and merely emits an artifact; it never runs anything.
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="charon",
        description="Charon — a local AI gateway with automatic failover across "
                    "providers, plus optional coding-agent automation.")
    p.add_argument("--version", action="version", version=f"charon {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    su = sub.add_parser("setup", help="Guided first-time setup (providers, keys, models)")
    su.set_defaults(func=_cmd_setup)

    gt = sub.add_parser("gate",
                        help="Run all validation checks (ruff, mypy, boundary, "
                             "version, gate-registry)")
    gt.set_defaults(func=_cmd_gate)

    g = sub.add_parser("gateway",
                       help="Start the local API gateway your apps point at")
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
                        help="Add AI providers and their API keys")
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

    md = sub.add_parser("models", help="Manage your available models")
    mdsub = md.add_subparsers(dest="action", required=True)
    mi = mdsub.add_parser("import",
                          help="import a provider's full model list into the catalog")
    mi.add_argument("name", nargs="?", default=None,
                    help="provider name (omitted when --all)")
    mi.add_argument("--all", action="store_true",
                    help="import from every provider with a key set")
    mi.add_argument("--free-only", action="store_true", help="import only free models")
    mi.add_argument("--into-pool", default=None,
                    help="ALSO add the imported models to this pool (opt-in; pools work "
                         "best small + cost-ranked, so this is rarely what you want)")
    md.set_defaults(func=_cmd_models)

    t = sub.add_parser("tier",
                       help="Choose which models to use for each tier (low / med / high)")
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
    trec = tsub.add_parser("recommend",
                           help="recommend tier assignments from a provider's live "
                                "model catalog")
    trec.add_argument("provider", help="provider to query for models")
    t.set_defaults(func=_cmd_tier)

    r = sub.add_parser("run", help="Run a coding goal until it passes its tests")
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

    wk = sub.add_parser(
        "work",
        help="Run a whole job end-to-end: plan → build → open a PR")
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
    wk.add_argument("--open-pr", action="store_true",
                    help="for each unit the gate PROPOSES, open a DRAFT PR "
                         "(branch+push+PR); OFF by default (read-only, no push). "
                         "NEVER merges — a human/other-agent merges (ADR-0010 D5)")
    wk.add_argument("--base", default="master",
                    help="[--open-pr] PR base branch (default: master)")
    wk.add_argument("--repo-slug", default=None,
                    help="[--open-pr] owner/name for `gh pr create --repo` "
                         "(default: gh infers it)")
    wkpg = wk.add_mutually_exclusive_group()
    wkpg.add_argument("--progress", dest="progress", action="store_true",
                      default=None,
                      help="stream per-unit lifecycle lines (claimed/started/"
                           "checkpoint/land/done) to STDERR as the run drains "
                           "(default: ON for a TTY, OFF when stdout is piped)")
    wkpg.add_argument("--quiet", dest="progress", action="store_false",
                      help="suppress live progress; stdout still gets the final JSON")
    wk.set_defaults(func=_cmd_work)

    rn = sub.add_parser(
        "runs",
        help="Roll up the whole last work run (every unit's status) from state")
    rn.add_argument("--state-dir", default=api.DEFAULT_STATE_DIR)
    rn.set_defaults(func=_cmd_runs)

    ld = sub.add_parser("land",
                        help="Open a pull request for finished work (never auto-merges)")
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

    ik = sub.add_parser(
        "intake",
        help="Turn a backlog or to-do list into a runnable plan")
    iksub = ik.add_subparsers(dest="intake_action", required=True)
    ii = iksub.add_parser(
        "import",
        help="induct a work-list (markdown) → write a plan JSON + print it for "
             "human review; default writes + stops (--run to chain into the engine)",
        epilog=_INTAKE_IMPORT_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ii.add_argument("file", help="the work-list to induct")
    ii.add_argument("--out", default=None,
                    help="write the plan JSON here (default: <file>.plan.json)")
    ii.add_argument("--format", dest="fmt", default="markdown",
                    help="input adapter (default: markdown — the only v1 adapter)")
    ii.add_argument("--run", action="store_true",
                    help="DANGER: after writing the plan, EXECUTE its runnable units "
                         "via the work-engine. This runs each unit's `accept` command "
                         "in a worktree — only --run input you trust (OFF by default)")
    ii.add_argument("--repo", default=None,
                    help="[--run] git repo to cut per-unit worktrees from "
                         "(default: a sandbox base repo)")
    ii.add_argument("--state-dir", default=api.DEFAULT_STATE_DIR)
    ii.add_argument("--backend", default="mock",
                    help="[--run] each unit's warm worker backend (mock|acp)")
    ii.add_argument("--acp-cmd", default=None,
                    help="[--run] launch argv for a real ACP backend, e.g. 'opencode acp'")
    ii.add_argument("--autonomy", default="L1", choices=["L0", "L1", "L2", "L3"],
                    help="[--run] per-unit autonomy (default L1)")
    ii.set_defaults(func=_cmd_intake)

    lg = sub.add_parser("ledger", help="Show a task's progress and history")
    lg.add_argument("task_id")
    lg.add_argument("--state-dir", default=api.DEFAULT_STATE_DIR)
    lg.set_defaults(func=_cmd_ledger)

    from . import connect
    cn = sub.add_parser(
        "connect",
        help="Wire a client (opencode/omp/aider) to your local Charon gateway")
    cn.add_argument("client", choices=connect.supported_clients(),
                    help="the client to wire (the writer registry is the source of "
                         "this list)")
    cn.add_argument("--host", default=None, help="gateway host (default 127.0.0.1)")
    cn.add_argument("--port", type=int, default=None, help="gateway port (default 8080)")
    cn.add_argument("--model", default=None,
                    help="served model id to pin (default: the first one the "
                         "gateway advertises)")
    cn.add_argument("--token", default=None,
                    help="gateway bearer token (or set CHARON_GATEWAY_TOKEN); written "
                         "ONLY into the client's config, never printed")
    cn.add_argument("--install", action="store_true",
                    help="attempt to install the client if it's missing (best-effort, "
                         "per-OS); without this we only print the install command")
    cn.add_argument("--yes", action="store_true",
                    help="skip the install confirmation prompt")
    cn.set_defaults(func=_cmd_connect)

    d = sub.add_parser("doctor", help="Check that your coding-agent setup works")
    d.add_argument("--backend-cmd", default=None, help='e.g. "claude-code acp"')
    d.set_defaults(func=_cmd_doctor)

    rs = sub.add_parser("reset",
                        help="Clear local config (--all also removes saved keys)")
    rs.add_argument("--all", action="store_true",
                    help="also delete secrets.json (your stored API keys)")
    rs.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    rs.set_defaults(func=_cmd_reset)

    v = sub.add_parser("version", help="Show the Charon version")
    v.set_defaults(func=lambda a: (print(__version__), 0)[1])
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
