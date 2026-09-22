"""Text normalization: display form and comparison form.

Pure, framework-free, per `specs/phrase-management/spec.md`'s "Text
normalization" requirement. `display_form` -> `text` (casing/whitespace
preserved); `comparison_form` -> `normalized_text` (casefolded, collapsed).
Both idempotent. Length/emptiness validation is owned by Unit 3.
"""

from __future__ import annotations

import re
import unicodedata

# Step 1: whitespace controls mapped to a single space (separates words).
_WHITESPACE_CONTROLS = frozenset("\t\n\r\v\f\u001c\u001d\u001e\u001f\u0085")

# Step 2: invisible chars stripped outright (U+200B ZERO WIDTH SPACE, U+2060
# WORD JOINER, U+FEFF BOM), plus every remaining Cc control.
_ZERO_WIDTH_STRIP = frozenset("​⁠﻿")

# Step 4: trimmed from both ends with whitespace. ZWJ (U+200D)/ZWNJ (U+200C)
# are only stripped at the edges — kept inside the text (emoji sequences,
# Persian/Indic shaping).
_EDGE_TRIM_PATTERN = re.compile(r"^[\s‌‍]+|[\s‌‍]+$")


def display_form(raw: str) -> str:
    """Derive the display form: trimmed, NFC, control/zero-width-stripped."""
    whitespace_mapped = "".join(
        " " if ch in _WHITESPACE_CONTROLS else ch for ch in raw
    )
    control_stripped = "".join(
        ch
        for ch in whitespace_mapped
        if ch not in _ZERO_WIDTH_STRIP and unicodedata.category(ch) != "Cc"
    )
    composed = unicodedata.normalize("NFC", control_stripped)
    return _EDGE_TRIM_PATTERN.sub("", composed)


def comparison_form(display: str) -> str:
    """Derive the comparison form: casefolded, re-NFC'd, whitespace-collapsed."""
    casefolded = display.casefold()
    # Casefolding can de-normalize (e.g. U+01F0 -> "j" + COMBINING CARON), so
    # NFC is re-applied here.
    renormalized = unicodedata.normalize("NFC", casefolded)
    return " ".join(renormalized.split())
