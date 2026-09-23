"""pydantic-settings configuration (Unit 6, design.md's "Configuration").
Instantiated in `main.py` *before* the app is created, so an invalid value
exits the process non-zero and is visible in `docker compose up` output.

`Settings` is the RUNTIME class: `embedding_provider` accepts exactly ONE
value (`sentence_transformers`). `FakeProviderSettings` is a separate
subclass that additionally allows `fake`, so a misconfigured production
environment can never silently boot against the test double. Named
`FakeProviderSettings`, not the more obvious `TestSettings`: pytest's
default `python_classes = Test*` pattern tries to collect any `Test*` name
as a test class the moment a test module imports it (a real
`PytestCollectionWarning` observed during this unit's RED/GREEN cycle).

Intentionally NOT modeled here (see design.md's Configuration table):
web-only build args belong to `apps/web`; image-fixed vars
(`HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`, `SENTENCE_TRANSFORMERS_HOME`) are
baked into the Docker image; `POSTGRES_USER`/`PASSWORD`/`DB` are consumed
only by the `db` compose service -- this app only reads `DATABASE_URL`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class EmbeddingProviderName(StrEnum):
    SENTENCE_TRANSFORMERS = "sentence_transformers"


class FakeEmbeddingProviderName(StrEnum):
    SENTENCE_TRANSFORMERS = "sentence_transformers"
    FAKE = "fake"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    database_url: str
    similarity_threshold: float = 0.80
    matches_page_size: int = Field(default=50, ge=1, le=200)
    phrase_max_length: int = Field(default=280, ge=1, le=4000)
    # Max value a client's `?limit=` on `GET /phrases` may request.
    phrases_list_limit: int = Field(default=200, ge=1, le=1000)
    # Default page size for `GET /phrases` when `?limit=` is omitted.
    phrases_page_size: int = Field(default=10, ge=1, le=1000)
    max_request_bytes: int = Field(default=1_048_576, ge=4096)
    embedding_provider: EmbeddingProviderName = EmbeddingProviderName.SENTENCE_TRANSFORMERS
    embedding_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", min_length=1
    )
    embedding_model_revision: str = Field(default="0" * 40, pattern=r"^[0-9a-fA-F]{40}$")
    embedding_dimensions: int = Field(default=384, gt=0)
    embedding_timeout_seconds: float = Field(default=10.0, gt=0)
    embedding_max_concurrency: int = Field(default=2, ge=1)
    embedding_cache_size: int = Field(default=512, ge=0)
    hnsw_ef_search: int = Field(default=200, ge=1, le=1000)
    lock_timeout_ms: int = Field(default=5000, ge=1)
    # `NoDecode`: pydantic-settings' `EnvSettingsSource` otherwise treats any
    # `list[...]` field as "complex" and calls `json.loads` on the raw env
    # string BEFORE the `_split_comma_separated` validator below ever runs
    # -- crashing `SettingsError` on a real `CORS_ORIGINS=http://host:port`
    # value from an actual OS environment variable (Unit 14 finding: only
    # surfaced by a real `docker compose up`, never by a test constructing
    # `Settings(cors_origins=...)` directly via keyword args). `NoDecode`
    # keeps the raw string untouched so the `mode="before"` validator is the
    # only thing that ever parses it, on every source (env or init kwargs).
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    log_level: LogLevel = LogLevel.INFO

    @field_validator("database_url")
    @classmethod
    def _require_psycopg_scheme(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use the postgresql+psycopg:// scheme")
        return value

    @field_validator("similarity_threshold")
    @classmethod
    def _threshold_in_unit_interval(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("SIMILARITY_THRESHOLD must be within [0, 1]")
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _no_wildcard_origins(cls, value: list[str]) -> list[str]:
        for origin in value:
            if origin == "*" or not origin.startswith(("http://", "https://")):
                raise ValueError(
                    f"CORS_ORIGINS must list absolute origins, no wildcard: {origin!r}"
                )
        return value


class FakeProviderSettings(Settings):
    """The only place `EMBEDDING_PROVIDER=fake` is legal -- see module docstring."""

    # Widening the field type in a subclass is unsound for arbitrary Liskov substitution,
    # but safe here: pydantic revalidates every field, and this class exists only to
    # accept the extra `fake` value.
    embedding_provider: FakeEmbeddingProviderName = FakeEmbeddingProviderName.FAKE  # type: ignore[assignment]
