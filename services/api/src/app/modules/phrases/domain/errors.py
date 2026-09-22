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
