FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY api ./api
COPY database ./database
COPY packages ./packages
COPY scripts ./scripts

EXPOSE 8000

CMD ["sh", "-c", "uv run python -m scripts.migrate && exec uv run uvicorn api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
