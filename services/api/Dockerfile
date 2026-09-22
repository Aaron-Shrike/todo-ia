# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# migrate: minimal image running `alembic upgrade head`. No torch/model
# weights — those arrive in the `api` stage (Unit 8), extending this file.
FROM base AS migrate
COPY pyproject.toml ./
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install .
CMD ["alembic", "upgrade", "head"]
