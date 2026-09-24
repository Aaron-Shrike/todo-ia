"""Unit tests for `GetPhrase` (`GET /phrases/{id}`)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.modules.phrases.adapters.in_memory_repository import InMemoryUnitOfWorkFactory
from app.modules.phrases.application.get_phrase import GetPhrase
from app.modules.phrases.contracts import NewPhrase, ValidationStatus
from app.modules.phrases.domain.errors import PhraseNotFound
from tests.contract_suite.vectors import PROBE


def _seed(factory: InMemoryUnitOfWorkFactory, text: str) -> int:
    with factory() as uow:
        phrase = uow.repo.add(
            NewPhrase(
                text=text,
                normalized_text=text,
                embedding=PROBE,
                similarity_score=None,
                most_similar_phrase_id=None,
                validation_status=ValidationStatus.UNIQUE,
                validated_at=datetime.now(UTC),
            )
        )
        uow.commit()
        return phrase.id


def test_returns_the_stored_phrase_by_id() -> None:
    factory = InMemoryUnitOfWorkFactory()
    phrase_id = _seed(factory, "Probar causa limeña")

    result = GetPhrase(factory)(phrase_id)

    assert result.id == phrase_id
    assert result.text == "Probar causa limeña"


def test_raises_phrase_not_found_for_an_unknown_id() -> None:
    factory = InMemoryUnitOfWorkFactory()
    phrase_id = _seed(factory, "Probar causa limeña")

    with pytest.raises(PhraseNotFound) as exc_info:
        GetPhrase(factory)(phrase_id + 1)

    assert exc_info.value.phrase_id == phrase_id + 1
