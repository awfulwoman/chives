FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install dependencies before copying source for layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY chives/ ./chives/
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH" \
    CHIVES_STATE_PATH=/app/state \
    CHIVES_PROFILE_PATH=/app/profile

EXPOSE 8080

CMD ["python", "-m", "chives.main"]
