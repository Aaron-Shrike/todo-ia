# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# migrate: minimal image running `alembic upgrade head`. No torch/model
# weights — those arrive in the `api` stage below (Unit 8).
FROM base AS migrate
COPY pyproject.toml ./
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install .
CMD ["alembic", "upgrade", "head"]

# api-builder: installs the CPU-only torch wheel (design.md: "the CPU-only
# torch wheel from the PyTorch CPU index"), then `.[embeddings]` (pip finds
# torch already satisfied and never reaches for the default index's GPU
# wheel), then bakes the pinned checkpoint into a real huggingface_hub
# cache directory via `snapshot_download` -- so a fully offline runtime
# stage (`HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1`) resolves
# `SentenceTransformer(EMBEDDING_MODEL, revision=EMBEDDING_MODEL_REVISION)`
# from the local cache with zero network calls, exactly as it would online.
# The build FAILS FAST if `EMBEDDING_MODEL_REVISION` is not a 40-hex commit
# SHA, so a rebuild can never silently pick up different weights (the SHA
# is also half of `model_id`, hence of the embedding cache key).
#
# NOT VERIFIED BY BUILDING in this batch: no `docker` is available in this
# environment (confirmed: `docker --version` -> command not found). Written
# per design.md's "Model baked at build" section and task 8.3's literal
# instructions, reviewed but not executed here -- see apply-progress.md's
# Unit 8 section, including one specific open question: `snapshot_download`
# is called with `cache_dir` (matching `SENTENCE_TRANSFORMERS_HOME`'s
# expected huggingface_hub cache LAYOUT, `models--org--name/snapshots/
# <sha>/...`) rather than `local_dir` (a flat directory `SentenceTransformer`
# would NOT recognize) -- reasoned from `sentence-transformers`/
# `huggingface_hub`'s documented caching conventions, not confirmed against
# a real build.
FROM base AS api-builder
# Unit 8's pinned Hub revision (`e8f8c21...`, verified via `curl https://
# huggingface.co/api/models/sentence-transformers/paraphrase-multilingual-
# MiniLM-L12-v2`) is cross-referenced, not re-declared, in `services/api/
# tests/unit/similarity/test_sentence_transformers.py`'s `slow`-marked
# real-model test (fix-pass finding #8: a Dockerfile ARG default cannot
# literally `import` a Python constant, so a cross-referencing comment in
# both files is the documented single source of truth instead).
ARG EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
ARG EMBEDDING_MODEL_REVISION=e8f8c211226b894fcb81acc59f3b34ba3efd5f42
# Same mixed-case pattern as `Settings.embedding_model_revision`
# (`^[0-9a-fA-F]{40}$`, `platform/settings.py`) -- fix-pass finding #6: the
# two checks previously disagreed (lowercase-only here), so an
# uppercase-containing (but still valid) Hub SHA would fail only at this
# Docker layer.
RUN echo "$EMBEDDING_MODEL_REVISION" | grep -Eq '^[0-9a-fA-F]{40}$' || \
    (echo "EMBEDDING_MODEL_REVISION must be a 40-hex commit SHA, got: '$EMBEDDING_MODEL_REVISION'" >&2 && exit 1)
# Fix-pass finding #4: `EMBEDDING_MODEL` is build-arg-controlled and gets
# interpolated into an executed Python string literal below (the
# `snapshot_download(repo_id='$EMBEDDING_MODEL', ...)` call) -- defense in
# depth, same as the revision check above, against a CI pipeline that ever
# forwards a PR-controlled `--build-arg EMBEDDING_MODEL=...` value.
# Allow-list shape: a Hugging Face Hub `org/model-name` repo id.
RUN echo "$EMBEDDING_MODEL" | grep -Eq '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$' || \
    (echo "EMBEDDING_MODEL must match 'org/model-name', got: '$EMBEDDING_MODEL'" >&2 && exit 1)
COPY pyproject.toml ./
COPY src ./src
# Fix-pass finding #5: both were previously unpinned (torch had no version
# constraint at all; `pyproject.toml`'s `sentence-transformers>=3.0` was a
# floor only) -- undermining the reproducibility the revision-SHA pin above
# is meant to guarantee, since library behaviour could still drift on every
# rebuild. Pinned to the current stable releases as of this fix-pass
# (verified against PyPI/the PyTorch CPU wheel index: torch 2.14.0 ships a
# cp311 CPU wheel; sentence-transformers 6.1.0 declares `torch>=2.2`, so the
# pair is compatible).
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.0 && \
    pip install .[embeddings]
RUN python -c "from huggingface_hub import snapshot_download; \
snapshot_download(repo_id='$EMBEDDING_MODEL', revision='$EMBEDDING_MODEL_REVISION', cache_dir='/opt/models')"

# api: runtime stage -- copies installed packages + the baked cache, no
# build tooling (no pip index access needed or wanted at this layer).
# Offline env vars forbid any network call at runtime, so a container run
# with no network reproduces exactly what was baked at build time.
FROM base AS api
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    SENTENCE_TRANSFORMERS_HOME=/opt/models
COPY --from=api-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=api-builder /usr/local/bin /usr/local/bin
COPY --from=api-builder /opt/models /opt/models
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-deps .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
