FROM python:3.11 AS builder

# Grab the uv binary from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# System build deps
RUN apt-get update && apt-get install -y \
    sudo \
    wget \
    vim \
    curl \
    gettext \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies via uv ──────────────
# Copy only dependency metadata first (layer cache)
COPY pyproject.toml uv.lock ./

# Create a venv and install deps — no source code needed yet
# Install deps fro lock, exclude development deps, these are install by vscode .devcontainer.json
RUN uv venv /opt/venv \
    && . /opt/venv/bin/activate \
    && uv sync --frozen --no-dev --no-install-project

ENV PATH="/app/.venv/bin:$PATH"

# ── Application code ────────────────────────
COPY . .

# Download Python source for i18n
RUN wget https://www.python.org/ftp/python/3.11.0/Python-3.11.0.tgz \
    && tar xzf Python-3.11.0.tgz \
    && mv Python-3.11.0 /usr/local/src/ \
    && rm Python-3.11.0.tgz

RUN chmod +x /usr/local/src/Python-3.11.0/Tools/i18n/msgfmt.py \
    && /usr/local/src/Python-3.11.0/Tools/i18n/msgfmt.py \
       /app/locale/de/LC_MESSAGES/base.po \
       /app/locale/de/LC_MESSAGES/base


# ──────────────────────────────────────────────
# Runtime stage
# ──────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Grab uv in the runtime image too (handy for devcontainer)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Runtime system libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxcb1 \
    libxkbcommon0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy venv + app from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/app/.venv/bin:$PATH"
COPY --from=builder /app /app


# Dev-in-container git config
RUN git config --global --add safe.directory /app
