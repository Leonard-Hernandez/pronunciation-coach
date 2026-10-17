# syntax=docker/dockerfile:1.7
#
# Pronunciation Coach image.
#   CPU (default, ~2.6 GB):   docker build -t pronunciation-coach .
#   NVIDIA CUDA 12.8:       docker build --build-arg VARIANT=cuda -t pronunciation-coach:cuda .
# The CUDA variant needs the NVIDIA Container Toolkit on the host to use the GPU.

ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------- builder
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /usr/local/bin/uv
ARG VARIANT=cpu
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv VIRTUAL_ENV=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./

# Dependencies first (cached layer). The lockfile pins CUDA wheels; the CPU variant
# installs everything else from the lock and takes torch from the CPU wheel index.
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "$VARIANT" = "cuda" ]; then \
        uv sync --frozen --no-dev --no-install-project; \
    else \
        uv venv /opt/venv \
        && uv export --frozen --no-dev --no-hashes --no-emit-project \
           | grep -vE '^(torch|triton|nvidia-|cuda-)' > /tmp/requirements.txt \
        && uv pip install -r /tmp/requirements.txt \
        && uv pip install torch --index-url https://download.pytorch.org/whl/cpu; \
    fi

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-deps .

# ---------------------------------------------------------------- runtime
FROM python:${PYTHON_VERSION}-slim-bookworm
LABEL org.opencontainers.image.title="Pronunciation Coach" \
      org.opencontainers.image.description="Local English pronunciation and writing coach for Spanish speakers" \
      org.opencontainers.image.source="https://github.com/Leonard-Hernandez/pronunciation-coach"

RUN apt-get update \
    && apt-get install -y --no-install-recommends espeak-ng ffmpeg libsndfile1 curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 coach \
    && mkdir -p /data /config && chown coach:coach /data /config
COPY --from=builder --chown=coach:coach /opt/venv /opt/venv

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PC_HOST=0.0.0.0 \
    PC_PORT=8765 \
    PC_DATA_DIR=/data \
    PC_CONFIG_DIR=/config \
    HF_HOME=/data/huggingface

USER coach
WORKDIR /home/coach
VOLUME ["/data"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8765/api/health || exit 1
CMD ["pronunciation-coach"]
