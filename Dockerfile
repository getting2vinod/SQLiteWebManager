FROM python:3.11-slim

# Install uv binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Cache dependencies
COPY pyproject.toml .
RUN uv sync --no-cache

# Copy initial application structure
COPY app ./app

# Create mount points
RUN mkdir -p /app/data /app/current

ENV ROUTE_PATH=""
ENV DATA_DIR="/app/data"
ENV CURRENT_DIR="/app/current"

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "4012"]