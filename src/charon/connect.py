"""``charon connect <client>`` — one-command client wiring to the local gateway.

This is the gateway-first vision's last mile: PROD-INSTALL installs Charon, but
nothing wired a *client* (opencode / omp / aider) to point at the Charon gateway.
The flow, in order:

  1. Verify the gateway FIRST (``GET /v1/models`` with the token). Never write a
     client config pointing at a dead gateway.
  2. Discover a served model (``--model`` wins, else the first advertised id).
  3. Optionally install the client (only with ``--install``); otherwise just
     detect it and print the install command (with Windows/WSL PATH guidance).
  4. Write THAT client's provider config (baseURL + token + model) — merging into
     any existing file rather than clobbering unrelated keys.
  5. Print the exact "now run: <launch cmd>" to verify end-to-end.

**Agnostic by construction**: the ONLY client-specific knowledge is the per-client
writers in the :data:`REGISTRY` below — never in the gateway/request path. Adding a
client (incl. the GUI follow-ons cline/continue) is a single ``REGISTRY`` entry.

The token is written ONLY into the client's own config file; it is never printed
or logged. Privileged core stays stdlib-only — no YAML/HTTP third-party deps.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from . import providers
from .cli import _invocation_name

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8080
_TOKEN_ENV = "CHARON_GATEWAY_TOKEN"
_MAX_MODELS_BYTES = 1_000_000  # cap the /models response (memory-DoS guard)


class GatewayUnreachable(Exception):
    """The gateway did not answer ``GET /v1/models`` (down, wrong host/port, or a
    bad/absent token). We refuse to write a client config in this case."""


# --------------------------------------------------------------- gateway probe
def discover_models(host: str, port: int, token: str | None, *,
                    timeout: float = 10.0) -> list[str]:
    """``GET http://<host>:<port>/v1/models`` with the bearer token and return the
    advertised model ids. Reuses the gateway's OpenAI ``{"data": [...]}`` shape via
    :func:`providers._parse_models`. Redirects are disabled (no cross-host token
    leak) and the body is size-capped. Raises :class:`GatewayUnreachable` on any
    transport/HTTP error so the caller can fail closed without writing config."""
    url = f"http://{host}:{port}/v1/models"
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "charon-connect/0.1")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    opener = urllib.request.build_opener(providers._NoRedirect())
    try:
        resp = opener.open(req, timeout=timeout)
        raw = resp.read(_MAX_MODELS_BYTES + 1)
    except urllib.error.HTTPError as exc:
        hint = " (token rejected?)" if exc.code in (401, 403) else ""
        raise GatewayUnreachable(
            f"gateway at {host}:{port} returned HTTP {exc.code}{hint}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise GatewayUnreachable(
            f"could not reach the gateway at {host}:{port} ({type(exc).__name__})"
        ) from exc
    if len(raw) > _MAX_MODELS_BYTES:
        raise GatewayUnreachable("gateway /v1/models response too large")
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        raise GatewayUnreachable("gateway /v1/models returned non-JSON") from exc
    return [m["id"] for m in providers._parse_models(data)]


# ------------------------------------------------------------- minimal YAML I/O
# A dependency-free top-level YAML merge: we read the file's TOP-LEVEL key blocks
# verbatim, replace only the keys we manage (re-emitted deterministically), and
# write every other block back byte-for-byte. This preserves unrelated keys (and
# their nested content/comments) without a third-party YAML parser, and is
# idempotent — re-running yields identical bytes. We only ever emit mappings of
# scalars / nested mappings of scalars, which is all our client configs need.
def _yaml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    esc = s.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{esc}"'  # always quote strings — unambiguous, safe for tokens/URLs


def _yaml_emit(key: str, value: object, indent: int = 0) -> list[str]:
    pad = "  " * indent
    if isinstance(value, Mapping):
        lines = [f"{pad}{key}:"]
        for k, v in value.items():
            lines += _yaml_emit(str(k), v, indent + 1)
        return lines
    return [f"{pad}{key}: {_yaml_scalar(value)}"]


def _split_toplevel_blocks(text: str) -> list[tuple[str | None, list[str]]]:
    """Split file text into ``(top_key_or_None, raw_lines)`` blocks. A top-level
    key is an unindented ``key:`` line; its block runs until the next top-level key.
    Lines before any key (a leading comment/blank) form a ``None`` block."""
    blocks: list[tuple[str | None, list[str]]] = []
    cur_key: str | None = None
    cur: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        is_top = (
            line[:1] not in (" ", "\t", "", "#")
            and ":" in line
            and stripped == line
        )
        if is_top:
            key = line.split(":", 1)[0].strip()
            if cur or cur_key is not None:
                blocks.append((cur_key, cur))
            cur_key, cur = key, [line]
        else:
            cur.append(line)
    if cur or cur_key is not None:
        blocks.append((cur_key, cur))
    return blocks


def yaml_merge_toplevel(path: Path, updates: Mapping[str, object]) -> None:
    """Write ``updates`` (top-level key → scalar or nested mapping) into ``path``,
    replacing those keys in place and preserving every other top-level block
    verbatim. Creates the file (and parents) if absent."""
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    blocks = _split_toplevel_blocks(existing)
    seen: set[str] = set()
    out: list[str] = []
    for key, lines in blocks:
        if key is not None and key in updates:
            if key not in seen:
                out += _yaml_emit(key, updates[key])
                seen.add(key)
            # drop the old block for this key (replaced)
        else:
            out += lines
    for key, value in updates.items():
        if key not in seen:
            out += _yaml_emit(key, value)
            seen.add(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _write_json_merge(path: Path, mutate: Callable[[dict], None]) -> None:
    """Load ``path`` as a JSON object (``{}`` if absent/garbage), apply ``mutate``
    in place, and write it back pretty-printed. Preserves unrelated keys."""
    data: object = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    if not isinstance(data, dict):
        data = {}
    mutate(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ the wiring
@dataclass(frozen=True)
class Wiring:
    """Everything a per-client writer needs: the resolved gateway endpoint, the
    bearer token, the chosen model id, and the config path to write."""
    base_url: str
    token: str | None
    model: str
    config_path: Path


def _home() -> Path:
    return Path(os.environ.get("HOME") or Path.home())


# --- per-client config paths (HOME-relative so tests can redirect via $HOME) ---
def _opencode_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else _home() / ".config"
    return root / "opencode" / "opencode.json"


def _omp_path() -> Path:
    return _home() / ".omp" / "agent" / "models.yml"


def _aider_path() -> Path:
    return _home() / ".aider.conf.yml"


def _continue_path() -> Path:
    return _home() / ".continue" / "config.json"


def _cline_path() -> Path:
    return _home() / ".cline" / "config.json"


# --- per-client config writers (the ONLY client-specific knowledge) -----------
def _write_opencode(w: Wiring) -> None:
    """``~/.config/opencode/opencode.json`` — opencode's OpenAI-compatible provider
    block. Deep-merges into ``provider.charon`` so other providers/models and the
    user's other top-level keys are preserved (idempotent)."""
    def mutate(data: dict) -> None:
        data.setdefault("$schema", "https://opencode.ai/config.json")
        provs = data.get("provider")
        if not isinstance(provs, dict):
            provs = {}
            data["provider"] = provs
        entry = provs.get("charon")
        if not isinstance(entry, dict):
            entry = {}
        entry["npm"] = "@ai-sdk/openai-compatible"
        entry.setdefault("name", "Charon")
        opts = entry.get("options")
        if not isinstance(opts, dict):
            opts = {}
        opts["baseURL"] = w.base_url
        if w.token is not None:
            opts["apiKey"] = w.token
        entry["options"] = opts
        models = entry.get("models")
        if not isinstance(models, dict):
            models = {}
        models.setdefault(w.model, {})
        entry["models"] = models
        provs["charon"] = entry

    _write_json_merge(w.config_path, mutate)


def _write_omp(w: Wiring) -> None:
    """``~/.omp/agent/models.yml`` — oh-my-pi's model registry. Charon is a single
    top-level provider entry; the top-level merge preserves the user's other
    entries verbatim."""
    yaml_merge_toplevel(w.config_path, {
        "charon": {
            "provider": "openai-compatible",
            "base_url": w.base_url,
            "api_key": w.token or "",
            "model": w.model,
        },
    })


def _write_aider(w: Wiring) -> None:
    """``~/.aider.conf.yml`` — aider reads an OpenAI-compatible endpoint from these
    flat keys (mirroring its CLI flags). The top-level merge preserves any other
    aider settings the user has."""
    yaml_merge_toplevel(w.config_path, {
        "openai-api-base": w.base_url,
        "openai-api-key": w.token or "",
        "model": f"openai/{w.model}",
    })


@dataclass(frozen=True)
class ClientSpec:
    """One supported client. ``binary`` is what we look for on ``PATH``;
    ``install`` returns the per-OS install command (``None`` if we can't advise);
    ``config_path`` / ``write`` know the on-disk format; ``launch`` is the verify
    command. ``guided`` clients emit manual instructions instead of auto-writing
    config (for GUI-only clients with no file-writable config)."""
    name: str
    binary: str
    config_path: Callable[[], Path]
    write: Callable[[Wiring], None]
    launch: Callable[[Wiring], str]
    install: Callable[[InstallEnv], str | None]
    guided: bool = False


@dataclass(frozen=True)
class InstallEnv:
    """The host facts a per-client install hint branches on."""
    system: str   # platform.system(): "Linux" | "Darwin" | "Windows"
    is_wsl: bool
    has_brew: bool
    has_npm: bool
    has_bun: bool
    has_pip: bool


def detect_env() -> InstallEnv:
    rel = platform.uname().release.lower()
    is_wsl = "microsoft" in rel or bool(os.environ.get("WSL_DISTRO_NAME"))
    return InstallEnv(
        system=platform.system(),
        is_wsl=is_wsl,
        has_brew=shutil.which("brew") is not None,
        has_npm=shutil.which("npm") is not None,
        has_bun=shutil.which("bun") is not None,
        has_pip=shutil.which("pip") is not None or shutil.which("pip3") is not None,
    )


def _write_continue(w: Wiring) -> None:
    """``~/.continue/config.json`` — Continue's config with a ``models`` array.
    Adds Charon as an OpenAI provider entry, preserving other models."""
    charon_model = {
        "title": f"Charon — {w.model}",
        "provider": "openai",
        "model": w.model,
        "apiBase": w.base_url,
    }
    if w.token is not None:
        charon_model["apiKey"] = w.token

    def mutate(data: dict) -> None:
        models = data.get("models")
        if not isinstance(models, list):
            models = []
            data["models"] = models
        replaced = False
        for i, m in enumerate(models):
            if isinstance(m, dict) and m.get("title") == charon_model["title"]:
                models[i] = charon_model
                replaced = True
                break
        if not replaced:
            models.append(charon_model)

    _write_json_merge(w.config_path, mutate)


def _write_cline(w: Wiring) -> None:
    """Cline (VS Code extension) stores settings in VS Code's settings.json,
    which is not a standalone config file we can safely auto-write. Cline's
    CLI mode uses env vars. Emit manual setup instructions instead."""
    pass  # guided mode — handled in run_connect


def _install_opencode(env: InstallEnv) -> str | None:
    if env.has_brew:
        return "brew install sst/tap/opencode"
    return "curl -fsSL https://opencode.ai/install | bash"


def _install_omp(env: InstallEnv) -> str | None:
    # oh-my-pi ships via npm/bun; prefer bun (the operator's path) when present.
    if env.has_bun:
        return "bun install -g @oh-my-pi/pi-coding-agent"
    if env.has_npm:
        return "npm install -g @oh-my-pi/pi-coding-agent"
    return ("curl -fsSL https://bun.sh/install | bash  "
            "# then: bun install -g @oh-my-pi/pi-coding-agent")


def _install_aider(env: InstallEnv) -> str | None:
    return "python -m pip install aider-install && aider-install"


def _install_continue(env: InstallEnv) -> str | None:
    if env.has_npm:
        return "npm install -g @continuedev/continue"
    return "npm install -g @continuedev/continue  # (requires npm)"


def _install_cline(env: InstallEnv) -> str | None:
    if env.has_npm:
        return "npm install -g cline"
    return "npm install -g cline  # (requires npm)"


# THE registry — the single source of truth for the supported-client list.
REGISTRY: dict[str, ClientSpec] = {
    "opencode": ClientSpec(
        name="opencode", binary="opencode", config_path=_opencode_path,
        write=_write_opencode, install=_install_opencode,
        launch=lambda w: f"opencode  # then pick model: charon/{w.model}",
    ),
    "omp": ClientSpec(
        name="omp", binary="omp", config_path=_omp_path,
        write=_write_omp, install=_install_omp,
        launch=lambda w: f"omp --model {w.model}",
    ),
    "aider": ClientSpec(
        name="aider", binary="aider", config_path=_aider_path,
        write=_write_aider, install=_install_aider,
        launch=lambda w: f"aider --model openai/{w.model}",
    ),
    "continue": ClientSpec(
        name="continue", binary="continue", config_path=_continue_path,
        write=_write_continue, install=_install_continue,
        launch=lambda w: "continue  # Charon model titled 'Charon - <model>'",
    ),
    "cline": ClientSpec(
        name="cline", binary="cline", config_path=_cline_path,
        write=_write_cline, install=_install_cline,
        launch=lambda w: (
            "# Cline stores settings in VS Code's settings.json.\n"
            "# To point Cline at Charon, add these to your VS Code settings:\n"
            f'#   "cline.apiProvider": "openai",\n'
            f'#   "cline.openaiBaseUrl": "{w.base_url}",\n'
            f'#   "cline.openaiApiKey": "{w.token or "?token=... if gateway-gated"}",\n'
            f'#   "cline.openaiModel": "{w.model}"'
        ),
        guided=True,
    ),
}


def supported_clients() -> list[str]:
    """The supported-client list — derived from :data:`REGISTRY` so it can never
    drift from the writers (acceptance: the registry is the single source)."""
    return sorted(REGISTRY)


# --------------------------------------------------------------- orchestration
def _eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def _path_gap_note(spec: ClientSpec, env: InstallEnv) -> None:
    """The omp/Windows PATH gap the operator hit: a global npm/bun bin installed on
    the Windows side isn't on the WSL ``PATH`` (and vice-versa)."""
    if env.is_wsl:
        _eprint(
            f"  note (WSL): if you installed {spec.binary!r} on Windows it won't be "
            "on your WSL PATH — install it INSIDE WSL, or add the install's bin dir "
            "to PATH.")
    elif env.system == "Windows":
        _eprint(
            f"  note (Windows): a global npm/bun install puts {spec.binary!r} in the "
            "global bin dir — ensure that dir is on your PATH (restart the shell).")


def run_connect(
    *,
    client: str,
    host: str | None = None,
    port: int | None = None,
    model: str | None = None,
    token: str | None = None,
    install: bool = False,
    yes: bool = False,
    runner: Callable[[list[str]], int] | None = None,
) -> int:
    """Drive ``charon connect <client>``. Returns a process exit code. ``runner`` is
    a test seam for the install subprocess (default shells out)."""
    spec = REGISTRY.get(client)
    if spec is None:
        _eprint(f"error: unknown client {client!r}. Supported: "
                f"{', '.join(supported_clients())}")
        return 2

    host = host or _DEFAULT_HOST
    port = port if port is not None else _DEFAULT_PORT
    tok = token or os.environ.get(_TOKEN_ENV) or None

    # 1. Verify the gateway FIRST — never write a config pointing at a dead gateway.
    try:
        ids = discover_models(host, port, tok)
    except GatewayUnreachable as exc:
        _eprint(f"error: {exc}")
        _eprint("  the Charon gateway must be running first — start it with:")
        _eprint(f"    {_invocation_name()} gateway")
        if not tok:
            _eprint("  (if your gateway needs a token, pass --token or set "
                    "CHARON_GATEWAY_TOKEN)")
        return 1

    # 2. Discover a served model (explicit --model wins).
    if model:
        chosen = model
        if ids and model not in ids:
            _eprint(f"  warning: {model!r} is not in the gateway's served list "
                    f"({len(ids)} model(s)); writing it anyway")
    elif ids:
        chosen = ids[0]
    else:
        _eprint("error: the gateway is reachable but serves no models — add one "
                f"with `{_invocation_name()} setup` / "
                f"`{_invocation_name()} models import <provider>`, then retry.")
        return 1

    # 3. Install the client if missing (only with --install); else just advise.
    env = detect_env()
    present = shutil.which(spec.binary) is not None
    if not present:
        cmd = spec.install(env)
        if install and cmd:
            if not yes and sys.stdin.isatty():
                ans = input(f"install {spec.binary!r} via `{cmd}`? [y/N]: ").strip().lower()
                if ans not in ("y", "yes"):
                    _eprint("  skipped install — writing config anyway")
                    cmd = None
            if cmd:
                _eprint(f"  installing {spec.binary!r}: {cmd}")
                rc = (runner or _shell_install)([cmd])
                if rc != 0:
                    _eprint(f"  install command exited {rc} — continuing; install "
                            f"{spec.binary!r} manually if needed")
                _path_gap_note(spec, env)
        else:
            _eprint(f"  {spec.binary!r} not found on PATH. Install it with:")
            _eprint(f"    {cmd}" if cmd else "    (see the client's docs)")
            _path_gap_note(spec, env)
            _eprint("  (re-run with --install to attempt this automatically)")

    # 4. Write the client's provider config (token goes ONLY into this file),
    #    or print manual instructions for guided (GUI-only) clients.
    base_url = f"http://{host}:{port}/v1"
    wiring = Wiring(base_url=base_url, token=tok, model=chosen,
                    config_path=spec.config_path())
    if spec.guided:
        print(f"  {spec.name} has no file-writable config (GUI-only settings).")
        print("  Manual setup:")
        print(f"  {spec.launch(wiring)}")
    else:
        spec.write(wiring)
        print(f"wired {spec.name} → {wiring.config_path}")
        print(f"  gateway: {base_url}")
        print(f"  model:   {chosen}")
        print(f"  token:   {'set (written to config)' if tok else 'none'}")
        print(f"\nnow run:  {spec.launch(wiring)}")
    return 0


def _shell_install(argv: list[str]) -> int:
    """Default install runner: run a shell command best-effort. Separated so tests
    can inject a no-op runner (acceptance never installs)."""
    try:
        return subprocess.run(argv[0], shell=True, check=False).returncode  # noqa: S602
    except OSError:
        return 1
