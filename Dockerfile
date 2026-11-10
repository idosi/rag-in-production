# syntax=docker/dockerfile:1
#
# The RAG API as a container image. Three stages, so the final image holds only
# what is needed to RUN (no uv, no build caches, no compilers):
#
#   builder   installs the dependencies and the package into /app/.venv
#   models    downloads the two ONNX models once, at BUILD time
#   runtime   the small image that ships: python + .venv + models + a non-root user
#
# Build and run (see docs/learning/03a-docker-ci.md):
#   make docker-up                       # Postgres + API
#   make docker-ingest                   # fill the index (first time only)
#
# Why a multi-stage build: the final image doesn't contain anything that exists only
# to build it. Smaller image = faster deploys and a smaller attack surface.

ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------- builder
FROM python:${PYTHON_VERSION}-slim AS builder

# uv comes from its official image (pinned): no pip install, same tool as on your laptop.
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /bin/uv

# UV_COMPILE_BYTECODE: precompile .pyc so the container starts faster.
# UV_LINK_MODE=copy:   the cache mount below is another filesystem, so hardlinks fail.
# UV_PYTHON_DOWNLOADS=never: use the Python of this image, don't download another.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Layer 1: the dependencies. Only these two files are copied, so this (slow) layer is
# rebuilt only when dependencies change, not on every edit of the source code.
# --frozen: install EXACTLY what uv.lock says, and fail if it is out of date.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --no-editable

# Layer 2: our own package. --no-editable copies it into the venv, so the runtime
# stage doesn't need the source tree.
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# ---------------------------------------------------------------- models
# A separate stage: the models are ~200MB and rarely change, so a code change must not
# re-download them. Doing it at build time means the container never needs to reach
# Hugging Face at startup (slow, and one more thing that can fail in production).
FROM builder AS models
ENV FASTEMBED_CACHE_PATH=/opt/models
RUN /app/.venv/bin/python -c "\
from fastembed import TextEmbedding; \
from fastembed.rerank.cross_encoder import TextCrossEncoder; \
from rag.config import get_settings; \
s = get_settings(); \
TextEmbedding(model_name=s.embedding_model); \
TextCrossEncoder(model_name=s.reranker_model)"

# ---------------------------------------------------------------- runtime
FROM python:${PYTHON_VERSION}-slim AS runtime

# A normal user, not root. If someone exploits the app, they don't get root inside the
# container. Many platforms (and security scanners) require this.
RUN groupadd --system app && useradd --system --gid app --home-dir /app app

WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=models --chown=app:app /opt/models /opt/models
# Where the ingest command caches the downloaded docs (a volume in docker-compose.yml).
RUN mkdir -p /app/data && chown app:app /app/data

ENV PATH="/app/.venv/bin:$PATH" \
    FASTEMBED_CACHE_PATH=/opt/models \
    PYTHONUNBUFFERED=1

USER app
EXPOSE 8000

# "Is the process alive AND can it reach the database?" /health counts the chunks.
# start-period: loading the models takes a while; failures in that window don't count.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request as u; u.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT', '8000'), timeout=4)"]

# 0.0.0.0: listen on all interfaces, otherwise the port mapping from outside can't reach it.
# No --reload: that is for development.
CMD ["sh", "-c", "exec uvicorn rag.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
