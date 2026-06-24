# Mode B — the fenced service container (ADR-0002 §2.3).
# This is where the privileged agent-spawning loop is meant to run: isolated
# from the host (and, when embedded, from SLOP's process) so the container
# boundary is the real blast-radius limit (reconciliation BR-2).
FROM python:3.12-slim AS base

# Non-root by default; the loop should never need host root.
RUN useradd --create-home --uid 10001 charon
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir '.[service]'

USER charon
ENV CHARON_STATE_DIR=/work/.charon
WORKDIR /work

EXPOSE 8473
# Default autonomy stays L0 unless explicitly raised by the operator.
CMD ["uvicorn", "charon.service.app:app", "--host", "0.0.0.0", "--port", "8473"]
