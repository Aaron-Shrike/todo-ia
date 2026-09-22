"""Hermetic environment for settings tests: clears every env var
`Settings`/`FakeProviderSettings` could read from the real process (a
shell, CI, or another test file mutating `os.environ` earlier in the same
pytest process -- see `tests/contract/conftest.py`), so `Settings()`
behavior here depends only on each test's own kwargs.
"""

from __future__ import annotations

import pytest

_SETTINGS_ENV_VARS = [
    "DATABASE_URL",
    "SIMILARITY_THRESHOLD",
    "MATCHES_PAGE_SIZE",
    "PHRASE_MAX_LENGTH",
    "PHRASES_LIST_LIMIT",
    "MAX_REQUEST_BYTES",
    "EMBEDDING_PROVIDER",
    "EMBEDDING_MODEL",
    "EMBEDDING_MODEL_REVISION",
    "EMBEDDING_DIMENSIONS",
    "EMBEDDING_TIMEOUT_SECONDS",
    "EMBEDDING_MAX_CONCURRENCY",
    "EMBEDDING_CACHE_SIZE",
    "HNSW_EF_SEARCH",
    "LOCK_TIMEOUT_MS",
    "CORS_ORIGINS",
    "LOG_LEVEL",
]


@pytest.fixture(autouse=True)
def _clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _SETTINGS_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
