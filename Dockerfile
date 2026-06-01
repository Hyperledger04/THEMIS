FROM python:3.12-slim

# WHY: uv is 10-100× faster than pip and respects pyproject.toml exactly.
# Installing it as a layer separate from app code avoids reinstalling on every
# source change (only reinstalls when pyproject.toml / uv.lock change).
COPY --from=ghcr.io/astral-sh/uv:0.4 /uv /uvx /usr/local/bin/

WORKDIR /app

# Install deps before copying source so Docker layer cache is preserved when
# only source files change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy source
COPY lexagent/ ./lexagent/

# Expose FastAPI control plane port
EXPOSE 8000

CMD ["uv", "run", "uvicorn", "lexagent.gateway.control_plane:app", "--host", "0.0.0.0", "--port", "8000"]
