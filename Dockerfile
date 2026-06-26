# Mode B — the fenced service container (ADR-0002 §2.3).
# This is where the privileged agent-spawning loop is meant to run: isolated
# from the host (and, when embedded, from SLOP's process) so the container
# boundary is the real blast-radius limit (reconciliation BR-2).
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

USER charon
ENV CHARON_STATE_DIR=/work/.charon
# This IS the Mode-B container boundary (ADR-0002 §2.3 / INV-B4), so L2+ autonomy
# is permitted here (Fence.assert_environment). Outside a container, L2+ refuses.
ENV CHARON_CONTAINER_VERIFIED=1
WORKDIR /work

EXPOSE 8080
# Default autonomy stays L0 unless explicitly raised by the operator.
CMD ["charon", "gateway", "--host", "0.0.0.0", "--port", "8080"]
