# syntax=docker/dockerfile:1
# Charon container image — serves BOTH the default GATEWAY (the first-class
# fresh-install path) and the Mode-B fenced service (ADR-0002 §2.3).
#
# Default `docker run`/`docker compose up` brings up a token-gated, OpenAI-
# compatible GATEWAY on 0.0.0.0:8080 with PERSISTENT config on a /data volume —
# no host Python required (sidesteps the Ubuntu-22.04 / Python-3.10 / no-pip
# barrier). The Mode-B service is still reachable by overriding the command
# (see docker-compose.yml `charon-service`, profile `service`).
#
# The first-line `# syntax` directive enables the BuildKit heredoc used for the
# embedded entrypoint below — BuildKit is the default builder on Docker 23+.
#
# The base is a build-arg so the PUBLISH workflow can pin it to an immutable
# digest resolved at release time — see the `publish` job in `.gitlab-ci.yml`
# (and `.github/workflows/ci.yml` during the GitHub→GitLab transition) and
# docs/SUPPLY-CHAIN.md §5. The plain tag
# is used only for the CI build-smoke; a published image is always digest-pinned.
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE} AS base

# Non-root by default; the loop should never need host root.
RUN useradd --create-home --uid 10001 charon
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir '.[service]'

# Gateway config home (secrets.config_dir() honours $CHARON_HOME). This is the
# dir that holds providers/models/pools + the 0600 secrets.json, so it must
# PERSIST and is NEVER baked into the image — declared a VOLUME and pre-created
# owned by the runtime user so `charon setup` / `providers add` can write it.
RUN mkdir -p /data && chown charon:charon /data
ENV CHARON_HOME=/data
VOLUME /data

# Container entrypoint (POSIX sh, embedded via BuildKit heredoc so no extra file
# is needed). It guards ONLY the default gateway path: a non-loopback bind with
# no token fails with a clear message (mirroring gateway.build_server's
# GatewayBindRefused invariant) instead of a raw Python traceback. Every other
# command — `setup`, `providers add …`, any `charon` subcommand, or the Mode-B
# `uvicorn …` command — passes through untouched. `exec` keeps charon as PID 1
# so signals/shutdown behave.
COPY --chmod=0755 <<'EOF' /usr/local/bin/charon-entrypoint
#!/bin/sh
# Charon container entrypoint. Guards the default gateway path; passes all else through.
set -eu

case "${1:-}" in
    charon) shift ;;                                              # `… charon <subcmd>`
    ''|gateway|setup|providers|provider|work|models|pools|tiers|intake|version|--help|-h)
        : ;;                                                     # implicit `charon <subcmd>`
    *) exec "$@" ;;                                              # raw command (uvicorn, sh, …) → Mode-B etc.
esac

[ "$#" -eq 0 ] && set -- gateway --host 0.0.0.0 --port 8080

if [ "${1:-}" = "gateway" ]; then
    host=127.0.0.1                                               # gateway.py _DEFAULT_HOST
    has_token=0
    [ -n "${CHARON_GATEWAY_TOKEN:-}" ] && has_token=1
    prev=
    for arg in "$@"; do
        case "$arg" in
            --host=*) host=${arg#--host=} ;;
            --token=*) has_token=1 ;;
        esac
        case "$prev" in
            --host) host=$arg ;;
            --token) [ -n "$arg" ] && has_token=1 ;;
        esac
        prev=$arg
    done
    case "$host" in
        127.*|::1|localhost|0:0:0:0:0:0:0:1) loopback=1 ;;
        *) loopback=0 ;;
    esac
    if [ "$loopback" -eq 0 ] && [ "$has_token" -eq 0 ]; then
        echo "charon: refusing to start the gateway on a non-loopback host ($host) without a token." >&2
        echo "  The gateway holds your provider keys, so a non-loopback bind must be token-gated (ADR-0005 D5/R8)." >&2
        echo "  Generate one and pass it in:" >&2
        echo >&2
        echo "      export CHARON_GATEWAY_TOKEN=\$(openssl rand -hex 16)" >&2
        echo >&2
        echo "  docker compose reads it from .env (see docs/docker.md); clients send it as their API key." >&2
        exit 78                                                  # EX_CONFIG
    fi
fi

exec charon "$@"
EOF

USER charon
ENV CHARON_STATE_DIR=/work/.charon
# This IS the Mode-B container boundary (ADR-0002 §2.3 / INV-B4), so L2+ autonomy
# is permitted here (Fence.assert_environment). Outside a container, L2+ refuses.
ENV CHARON_CONTAINER_VERIFIED=1
WORKDIR /work

EXPOSE 8080

# Token-aware health probe on the gateway's real surface (GET /v1/models),
# zero-dep stdlib urllib (no curl in the slim image). A gated gateway reports
# healthy because the probe sends the token; an un-gated loopback gateway needs
# no header.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os,urllib.request as u;t=os.environ.get('CHARON_GATEWAY_TOKEN');r=u.Request('http://127.0.0.1:8080/v1/models',headers={'Authorization':'Bearer '+t} if t else {});u.urlopen(r,timeout=4).read()"]

# Default: a token-gated gateway. Override the command for Mode-B / setup / etc.
ENTRYPOINT ["/usr/local/bin/charon-entrypoint"]
# Default autonomy stays L0 unless explicitly raised by the operator.
CMD ["charon", "gateway", "--host", "0.0.0.0", "--port", "8080"]
