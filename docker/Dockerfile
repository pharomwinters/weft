# Build context: the repository root.

# --- Frontend: built once, only its output reaches the final image -----------
FROM node:22-slim AS frontend
WORKDIR /build
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# --- App: Python dependencies from the lockfile, then the code ---------------
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings \
    FRONTEND_DIST=/app/frontend_dist
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/ ./backend/
COPY --from=frontend /build/dist ./frontend_dist/
COPY docker/entrypoint.sh /app/entrypoint.sh

RUN useradd --system --no-create-home app
USER app
EXPOSE 8000
ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
