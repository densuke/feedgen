# Dockerイメージにするための設定です
FROM ghcr.io/astral-sh/uv:alpine AS uv-src
FROM python:3.13-alpine3.22 AS base
COPY --from=uv-src /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/
COPY . /app
WORKDIR /app
RUN uv sync --no-dev --no-cache-dir
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "feedgen.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
