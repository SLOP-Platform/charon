"""Charon CLI (ADR-0002 §2.4, surface #1).

    charon run    --goal G --accept "CMD" [--accept ...] [--repo P]
                  [--backend mock|acp] [--autonomy L0|L1] [--budget N]
    charon gateway [--config charon.toml | --state-dir D] [--host H] [--port P]
                  [--token T]
    charon ledger <task-id> [--state-dir D]
    charon doctor [--backend-cmd "<agent> acp"]
    charon version
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

from . import __version__, api
from .doctor import probe


def _cmd_run(args: argparse.Namespace) -> int:
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
        )
    except (ValueError, RuntimeError, PermissionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2))
    return 0 if out["status"] == "complete" else 1


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
    return gateway.run(cfg)


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
        print("Presets:", ", ".join(sorted(providers.PRESETS)))
        added_models: list[str] = []
        while True:
            name = ask("\nAdd a provider (preset name, or a custom name; blank to finish)")
            if not name:
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
            key_env = ask("  key env-var name", preset.key_env or f"{name.upper()}_API_KEY")
            try:
                config.add_provider(name, base_url=base_url, key_env=key_env,
                                    strip_v1=(preset.strip_v1 if base_url else None))
            except ValueError as exc:
                print(f"  {exc}")
                continue
            if key_env:
                key = getpass.getpass(f"  paste the API key ({key_env}) [blank to skip]: ")
                if key:
                    secrets.set_secret(key_env, key)
                    print("  key stored (0600)")
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
    except (EOFError, KeyboardInterrupt):
        print("\nsetup needs an interactive terminal. Alternatively use "
              "`charon providers add <name>` or edit the files in "
              f"{secrets.config_dir()}.", file=sys.stderr)
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


def _cmd_doctor(args: argparse.Namespace) -> int:
    cmd = args.backend_cmd.split() if args.backend_cmd else None
    rep = probe(cmd)
    print(json.dumps(rep.to_dict(), indent=2))
    return 0 if rep.ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="charon", description="Thin cross-vendor agent orchestrator")
    p.add_argument("--version", action="version", version=f"charon {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run a goal to executable acceptance")
    r.add_argument("--goal", required=True)
    r.add_argument("--accept", action="append", required=True,
                   help="executable acceptance check (repeatable); exit 0 == verified")
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
                   help="cumulative cost cap (USD); stop before exceeding")
    r.add_argument("--max-tokens", type=int, default=None,
                   help="cumulative token cap; stop before exceeding")
    r.set_defaults(func=_cmd_run)

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

    lg = sub.add_parser("ledger", help="show a task's derived ledger state")
    lg.add_argument("task_id")
    lg.add_argument("--state-dir", default=api.DEFAULT_STATE_DIR)
    lg.set_defaults(func=_cmd_ledger)

    d = sub.add_parser("doctor", help="probe a real ACP backend (Tier-0)")
    d.add_argument("--backend-cmd", default=None, help='e.g. "claude-code acp"')
    d.set_defaults(func=_cmd_doctor)

    v = sub.add_parser("version", help="print version")
    v.set_defaults(func=lambda a: (print(__version__), 0)[1])
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
