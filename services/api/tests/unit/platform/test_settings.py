"""Unit 6.1: `platform/settings.py` fail-fast validation. Every field with a
startup validation range in design.md's Configuration table is exercised at
its boundary; `SIMILARITY_THRESHOLD` gets the fullest coverage (task 6.1's
explicit "boundary 0 and 1 accepted" requirement, and the one field this
change's specs call out by name -- semantic-validation's "Threshold
configuration validation" x3).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.platform.settings import EmbeddingProviderName, FakeProviderSettings, Settings

pytestmark = pytest.mark.unit

_BASE_ENV: dict[str, object] = {"database_url": "postgresql+psycopg://u:p@localhost:5432/db"}


def _settings(**overrides: object) -> Settings:
    return Settings(**{**_BASE_ENV, **overrides})


class TestSimilarityThreshold:
    @pytest.mark.parametrize("value", [0.0, 1.0, 0.80])
    def test_boundary_and_default_values_accepted(self, value: float) -> None:
        assert _settings(similarity_threshold=value).similarity_threshold == value

    @pytest.mark.parametrize("value", [-0.0001, 1.0001, -1.0, 2.0])
    def test_out_of_range_rejected(self, value: float) -> None:
        with pytest.raises(ValidationError):
            _settings(similarity_threshold=value)

    def test_non_numeric_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _settings(similarity_threshold="not-a-number")


class TestOtherRanges:
    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("matches_page_size", 0),
            ("matches_page_size", 201),
            ("phrase_max_length", 0),
            ("phrase_max_length", 4001),
            ("phrases_list_limit", 0),
            ("phrases_list_limit", 1001),
            ("max_request_bytes", 4095),
            ("embedding_timeout_seconds", 0),
            ("embedding_timeout_seconds", -1.0),
            ("embedding_max_concurrency", 0),
            ("embedding_cache_size", -1),
            ("hnsw_ef_search", 0),
            ("hnsw_ef_search", 1001),
            ("lock_timeout_ms", 0),
        ],
    )
    def test_out_of_range_rejected(self, field: str, value: object) -> None:
        with pytest.raises(ValidationError):
            _settings(**{field: value})

    @pytest.mark.parametrize(
        ("field", "value"),
        [("matches_page_size", 1), ("matches_page_size", 200), ("phrases_list_limit", 1000)],
    )
    def test_boundary_values_accepted(self, field: str, value: int) -> None:
        assert getattr(_settings(**{field: value}), field) == value


class TestDatabaseUrl:
    def test_required(self) -> None:
        with pytest.raises(ValidationError):
            Settings()

    def test_wrong_scheme_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _settings(database_url="postgresql://u:p@localhost/db")


class TestEmbeddingProvider:
    def test_runtime_settings_default_is_sentence_transformers(self) -> None:
        assert _settings().embedding_provider is EmbeddingProviderName.SENTENCE_TRANSFORMERS

    def test_runtime_settings_rejects_fake(self) -> None:
        with pytest.raises(ValidationError):
            _settings(embedding_provider="fake")

    def test_fake_provider_settings_defaults_to_fake(self) -> None:
        assert FakeProviderSettings(**_BASE_ENV).embedding_provider.value == "fake"

    def test_fake_provider_settings_still_accepts_sentence_transformers(self) -> None:
        settings = FakeProviderSettings(**_BASE_ENV, embedding_provider="sentence_transformers")
        assert settings.embedding_provider.value == "sentence_transformers"


class TestCorsOrigins:
    def test_default_single_origin(self) -> None:
        assert _settings().cors_origins == ["http://localhost:3000"]

    def test_comma_separated_value_is_split(self) -> None:
        settings = _settings(cors_origins="http://a.example,http://b.example")
        assert settings.cors_origins == ["http://a.example", "http://b.example"]

    @pytest.mark.parametrize("value", ["*", "localhost:3000"])
    def test_wildcard_and_non_absolute_origins_rejected(self, value: str) -> None:
        with pytest.raises(ValidationError):
            _settings(cors_origins=value)

    def test_comma_separated_value_from_a_real_os_environment_variable_is_split(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unit 14 finding: every other test above constructs `Settings` via
        keyword args (pydantic's `InitSettingsSource`), which never exercises
        pydantic-settings' `EnvSettingsSource`. That source treats
        `list[str]` fields as "complex" and calls `json.loads` on the raw
        env string BEFORE any field validator runs, so a real
        `CORS_ORIGINS=http://localhost:3000` (not JSON) crashed
        `Settings()` with `SettingsError` on every actual container boot --
        caught only by Unit 14's real `docker compose up` against the built
        image, never by the pre-existing suite. `NoDecode` on the field
        annotation is the fix (see `platform/settings.py`)."""
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
        monkeypatch.setenv("CORS_ORIGINS", "http://a.example,http://b.example")
        settings = Settings()  # type: ignore[call-arg]
        assert settings.cors_origins == ["http://a.example", "http://b.example"]


class TestEmbeddingModelRevision:
    def test_default_is_forty_hex_characters(self) -> None:
        assert len(_settings().embedding_model_revision) == 40

    @pytest.mark.parametrize("value", ["abc", "z" * 40])
    def test_wrong_length_or_non_hex_rejected(self, value: str) -> None:
        with pytest.raises(ValidationError):
            _settings(embedding_model_revision=value)
