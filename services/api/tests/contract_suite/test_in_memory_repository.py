"""Registers the in-memory adapter against the shared repository contract
suite (tasks.md 2.3). pgvector registers here too in Unit 5a/5b.
"""

from __future__ import annotations

import pytest

from app.modules.phrases.adapters.in_memory_repository import InMemoryUnitOfWorkFactory
from app.modules.phrases.contracts import UnitOfWorkFactory

from .repository_contract import RepositoryContractSuite


@pytest.mark.contract
class TestInMemoryRepositoryContract(RepositoryContractSuite):
    @pytest.fixture
    def uow_factory(self) -> UnitOfWorkFactory:
        return InMemoryUnitOfWorkFactory()
