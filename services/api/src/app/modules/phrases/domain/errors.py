"""Domain-level phrase errors.

Raised by the phrase-management application use cases (Unit 3). Plain,
framework-free exceptions — `platform/errors.py` (Unit 6) maps each to HTTP
422 `VALIDATION_ERROR` per design.md's "API Contract and Error Mapping".
"""

from __future__ import annotations


class EmptyPhraseText(Exception):
    """Phrase text is empty, or empty after normalization (whitespace-only
    or zero-width/control-only input)."""


class PhraseTooLong(Exception):
    """Phrase text exceeds `PHRASE_MAX_LENGTH` (post-normalization) or the
    raw `4 * PHRASE_MAX_LENGTH` pre-normalization cap."""

    def __init__(self, *, max_length: int) -> None:
        super().__init__(f"phrase text exceeds the maximum length of {max_length} code points")
        self.max_length = max_length


class PhraseNotFound(Exception):
    """`GET /phrases/{id}` requested an id that does not exist in the
    store. `platform/errors.py` maps this to HTTP 404 `PHRASE_NOT_FOUND`."""

    def __init__(self, *, phrase_id: int) -> None:
        super().__init__(f"no phrase with id {phrase_id}")
        self.phrase_id = phrase_id


class PhraseMetadataInvariantViolation(ValueError):
    """A `NewPhrase` violates one of migration 0001's paired-metadata CHECK
    constraints. Raised by `PhraseRepository.add` implementations BEFORE any
    write, so every adapter (in-memory now, pgvector in 5a/5b) fails the
    same way instead of relying on the database to catch it:

    - `phrases_metadata_paired`: `similarity_score IS NULL` iff
      `most_similar_phrase_id IS NULL` (score and neighbour are recorded as
      a pair or not at all).
    - `phrases_confirmed_has_neighbor`: a `duplicate_confirmed` row MUST
      carry both `similarity_score` and `most_similar_phrase_id`.
    """
