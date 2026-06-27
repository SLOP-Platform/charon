"""The ``AgentLaunch`` renderer seam (ADR-0014 D3/D4).

The work-engine routes a *tier* by asking the gateway to resolve a **tier vid**
to a provider chain (ADR-0014 D1). To stay product-neutral it must launch the
ACP agent without naming any specific agent product: it hands this seam an
``(acp_cmd, proxy_url, requested_model)`` and gets back an ``AgentLaunch`` — the
rendered launch contract (argv + passthrough env + the model id the agent will
request on the wire). The opencode-specific launch-config shape lives *behind*
the seam in ``OpencodeRenderer``; the engine never names opencode itself.

Exactly ONE renderer ships (opencode, ADR-0014 D3/B1). A generic/``claude-code``
renderer is NOT written on spec — additional renderers are gated on a live
``charon doctor`` probe (ADR-0014 Risks) and are out of scope here.

D4 invariant: a renderer's passthrough env NEVER carries a real provider key.
Behind the per-run proxy the gateway holds the key and injects it upstream; the
agent must not see it. ``_acp_passthrough_env(include_keys=False)`` is forced by
every renderer so a future renderer cannot regress that.

Privileged-core / stdlib-only (ADR-0005 R3, ADR-0007 D11): this seam adds no
dependency — it only reshapes how the existing launch env is produced.
"""
from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass

# The seam's env contract (ADR-0014 D4, relocated from api.py with the opencode
# blob). The base set lets the agent find its own config/dirs; the KEY set is the
# forbidden set behind a proxy — the proxy injects the real key, so a renderer
# must never pass these.
_ACP_BASE_PASSTHROUGH = ("HOME", "PATH", "XDG_CONFIG_HOME", "XDG_DATA_HOME")
_ACP_KEY_PASSTHROUGH = ("OPENCODE_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY")


def _acp_passthrough_env(include_keys: bool = True) -> dict[str, str]:
    """Env merged back over the fence's scrubbed env so the agent can function.
    With ``include_keys=False`` (the renderer invariant, D4) no real provider key
    is included — the proxy holds it. The no-proxy interim path still passes keys."""
    names = _ACP_BASE_PASSTHROUGH + (_ACP_KEY_PASSTHROUGH if include_keys else ())
    return {k: os.environ[k] for k in names if k in os.environ}


@dataclass(frozen=True)
class AgentLaunch:
    """The rendered, product-neutral launch contract for one ACP agent.

    ``argv`` — the agent's launch command. ``passthrough_env`` — env merged over
    the fence's scrubbed env (NEVER a real provider key: D4). ``requested_model``
    — the model id the agent sends on the wire; for tier routing this IS the tier
    vid, which the per-run gateway resolves to a cost-ranked provider chain."""

    argv: list[str]
    passthrough_env: dict[str, str]
    requested_model: str


class AgentRenderer:
    """Renders an ``AgentLaunch`` for one agent product. Subclasses move that
    product's launch-config shape behind the seam so the engine never names it.

    ``render`` MUST build its env with ``_acp_passthrough_env(include_keys=False)``
    so the D4 key-exclusion invariant holds for every renderer, present or future."""

    name = "agent"

    def render(self, acp_cmd: str, proxy_url: str, requested_model: str) -> AgentLaunch:
        raise NotImplementedError


def _split_model(requested_model: str) -> tuple[str, str]:
    """``<provider>/<model>`` → (opencode provider, the wire model id). A bare id
    (a tier vid carries no '/') falls back to a generic provider, so the wire id
    is the vid itself — exactly what the gateway resolves vid→pool→provider.
    Using the real provider name matters: opencode's ACP mode hangs on an
    unrecognized provider (relocated from api.py with the blob)."""
    if "/" in requested_model:
        provider, short = requested_model.split("/", 1)
        return provider, short
    return "charon", requested_model


class OpencodeRenderer(AgentRenderer):
    """The one shipped renderer (ADR-0014 D3/B1).

    Moves the opencode ``OPENCODE_CONFIG_CONTENT`` blob behind the seam verbatim:
    it overrides the agent's provider ``baseURL`` to the per-run proxy (the
    mechanism proven live; a config *file* path is not honored) and pins the wire
    model id to ``requested_model`` (the tier vid). Forces ``include_keys=False``
    (D4) — the proxy holds the real key."""

    name = "opencode"

    def render(self, acp_cmd: str, proxy_url: str, requested_model: str) -> AgentLaunch:
        provider, short = _split_model(requested_model)
        cfg = {
            "model": f"{provider}/{short}",
            "provider": {
                provider: {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": provider,
                    "options": {"baseURL": proxy_url + "/v1", "apiKey": "charon-proxy"},
                    "models": {short: {}},
                }
            },
        }
        env = {**_acp_passthrough_env(include_keys=False),
               "OPENCODE_CONFIG_CONTENT": json.dumps(cfg)}
        return AgentLaunch(argv=shlex.split(acp_cmd), passthrough_env=env,
                           requested_model=short)


# The single shipped renderer instance (ADR-0014 D3/B1).
_DEFAULT_RENDERER: AgentRenderer = OpencodeRenderer()


def render(acp_cmd: str, proxy_url: str, requested_model: str,
           renderer: AgentRenderer | None = None) -> AgentLaunch:
    """Render an ACP agent launch through the seam. The engine calls this with
    ``requested_model=tier_vid`` and the per-run gateway's URL; it never names a
    concrete agent. ``renderer`` defaults to the one shipped renderer (opencode);
    a future probed renderer is injected here, not branched in the engine."""
    return (renderer or _DEFAULT_RENDERER).render(acp_cmd, proxy_url, requested_model)
